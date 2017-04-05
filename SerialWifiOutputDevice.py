# Copyright (c) 2016 Ultimaker B.V.
# Cura is released under the terms of the AGPLv3 or higher.

from UM.i18n import i18nCatalog
from UM.Application import Application
from UM.Logger import Logger
from UM.Signal import signalemitter

from UM.Message import Message

from cura.PrinterOutputDevice import PrinterOutputDevice, ConnectionState

from PyQt5.QtCore import QUrl, QTimer, QThread, pyqtSignal, pyqtProperty, pyqtSlot, QCoreApplication #@UnresolvedImport
from PyQt5.QtWidgets import QMessageBox #@UnresolvedImport

import time
import socket
import queue
import collections

from . import GCodeLibrary

i18n_catalog = i18nCatalog("cura")

class WifiConnectionFactory():
    connection = None
    buffer = ""

    def isConnected(self):
        return bool(self.connection)
    
    def connect(self, ip, port):
        self.connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.connection.connect((ip, port),)
        self.connection.setblocking(0)
        #print("FAMILY: ", self.connection.family)
        #print("PROTO: ", self.connection.proto)
        #print("TYPE: ", self.connection.type)
        return self.connection
            
    def disconnect(self):
        self.connection.close()
        self.connection = None
        
    def send(self, data):
        #Logger.log("e", "Sending: %s", data)
        #if type(data) == str:
        #    data = data.encode("utf-8")
        if not type(data) is bytes:
            data = bytes(data)
        
        if b'\n' not in data:
            data += b'\n'
        
        try:
            self.connection.send(data)
            return True
        except Exception:
            Logger.logException("e", "An exception occured while sending data!")
            self.connection = None
            return False
    
    def receive(self):
        try:
            return self.connection.recv(1).decode("utf-8")
        except BlockingIOError:
            return None
        except Exception:
            Logger.logException("e", "An exception occured while receiving data!")
            self.connection = None
            return None
    
    def receiveLine(self):
        data = self.receive()
        if data:
            self.buffer += data
        
        if "\n" in self.buffer:
            line = self.buffer[:self.buffer.find("\n")]
            self.buffer = self.buffer[self.buffer.find("\n")+1:]
            return line

class SerialOutputDevice(PrinterOutputDevice):
    def __init__(self, name):
        super().__init__(name)
        self.setName(name)
        self.setIconName("print")

        self.serial_connection = None
        self.serial_connector = None
        
        # Send and receive
        self._sent_lines_since_injected = 0
        self._sent_command = None
        self._sent_command_time = None
        self._send_timeout = 10 # s
        self._send_injected_every = 4 # lines
        self._send_is_blocked = False
        self._send_is_blocked_since = None
        self._receive_mode = "normal"

        # Cached status
        self._sd_card_status = None

        # Queues
        #self.queue_gcode = queue.Queue()
        self.queue_gcode = collections.deque()
        self.queue_gcode_size = None
        self.queue_gcode_begin = None
        self.queue_injected = queue.Queue()
        self.queue_frequently = []
        self.queue_frequently_last = None
        
        # Connect thread
        self._connect_thread = QThread()
        self._connect_thread.run = self._connect
        
        # Start print thread
        self._print_thread = QThread()
        self._print_thread.run = self._print
        
        # Receive thread
        self._receive_thread = QThread()
        self._receive_thread.run = self._receive
        
        # Send thread
        self._send_thread = QThread()
        self._send_thread.run = self._send
        
        # Update thread - for everything else than receive and send
        self._update_timer = QTimer()
        self._update_timer.setInterval(1000)
        self._update_timer.setSingleShot(False)
        self._update_timer.timeout.connect(self._update)
        
        self.threads = (self._connect_thread,
                        self._print_thread,
                        self._receive_thread,
                        self._send_thread,
                        self._update_timer,
                        )
        
    
    def __del__(self):
        #super().__del__()
        for thread in self.threads:
            Logger.log("", "Waiting for thread %s to exit..." %repr(thread))
            thread.wait()

    ##  Stop requesting data from printer
    def disconnect(self):
        Logger.log("d", "Connection with printer %s with ip %s stopped", self._key, self._address)
        self.serial_connection.disconnect()
        self.serial_connection = None
        self.setConnectionState(ConnectionState.closed)
        self.close()

    def connect(self):
        if not self._connect_thread.isRunning():
            self._connect_thread.start()
    
    def _connect(self):
        if self.serial_connector is None:
            raise ValueError("serial_connector not given!")
        
        if self.connectionState == ConnectionState.connected:
            self.disconnect()  # Ensure that previous connection (if any) is killed.

        # Beginning to connect to printer
        self.setConnectionState(ConnectionState.connecting)
        Logger.log("e", "Starting connection with %s at %s:%s" %(self.getName(), self.getAddressIp(), self.getAddressPort()))

        # Establish connection to printer...
        self.serial_connection = self.serial_connector()
        self.serial_connection.connect(self.getAddressIp(), self.getAddressPort())
        self.setConnectionState(ConnectionState.connected)
        Logger.log("e", "Connected with %s at %s:%s" %(self.getName(), self.getAddressIp(), self.getAddressPort()))

        # Start send/receive threads
        self._receive_thread.start()
        self._send_thread.start()
        
        # IO threads are up. Ready for printing...
        self._updateJobState("ready")

    def _receive(self):
        while self.connectionState == ConnectionState.connected:
            received_line = self.serial_connection.receiveLine()
            
            if received_line:
                Logger.log("d", "Received new line: %s", repr(received_line))
                
                if not self._sent_command is None:
                    self._sent_command.parseAnswer(received_line)

                # Different answers
                if received_line == "echo:SD card ok":
                    self._sd_card_status = "ok"

                if received_line in ("echo:SD init fail", "Error:volume.init failed"):
                    self._sd_card_status = "failed"

            if self._sent_command and self._sent_command_time:
                timeout = self._send_timeout
                if self._sent_command.recommendedTimeOut:
                    timeout = self._sent_command.recommendedTimeOut
                if timeout != -1:
                    if timeout <= time.time() - self._sent_command_time:
                        self._sent_command.hasTimedOut(True)

            #print_information = Application.getInstance().getPrintInformation()

    def _send(self):
        while self.connectionState == ConnectionState.connected:
            if not self._sent_command is None:
                if not (self._sent_command.hasFinished() or self._sent_command.hasTimedOut()):
                    #Logger.log("d", "Wait for command to be processed...")
                    continue
            
            # First: injected lines, eg. for changing temperature
            if not self.queue_injected.empty():
                    self._sent_command = self.queue_injected.get()
                    self.serial_connection.send(self._sent_command)
                    self._sent_command_time = time.time()
                    continue
            
            # Regulary: GCode queue
            if self.queue_gcode and not self._send_is_blocked:
                self._updateJobState("printing")
                
                if self.queue_gcode_size == len(self.queue_gcode):
                    self.queue_gcode_begin = time.time()

                #self._sent_command = self.queue_gcode.get()
                self._sent_command = self.queue_gcode.popleft()
                if self._sent_command:
                    self._sent_command.setDryRun(True)
                    if self._receive_mode == "ok" and not type(self._sent_command) in (GCodeLibrary.RepRapCommands().M28, GCodeLibrary.RepRapCommands().M29):
                        self._sent_command.isOkCommand(True)
                    self.serial_connection.send(self._sent_command)
                    if type(self._sent_command) is GCodeLibrary.RepRapCommands().M28:
                        Logger.log("d", "Writing file. All answers are now 'ok'")
                        self._receive_mode = "ok"
                    if type(self._sent_command) is GCodeLibrary.RepRapCommands().M29:
                        Logger.log("d", "Writing file has finished. All answers are now normal")
                        self._receive_mode = "normal"
                    self._sent_command_time = time.time()
                if not self.queue_gcode_size is None:
                    Logger.log("d", "Sending line from G-Code queue: %s/%s", len(self.queue_gcode), self.queue_gcode_size)
                    self.setProgress(100.-100./self.queue_gcode_size*len(self.queue_gcode))
                    self._updateJobState("ready")
            else:
                if not self.queue_gcode_begin is None:
                    Logger.log("d", "Sending the G-Code queue took: %ss", time.time() - self.queue_gcode_begin)
                self.queue_gcode_begin = None
                self.queue_gcode_size = None
    
            #print_information = Application.getInstance().getPrintInformation()
    
    def injectCommand(self, command, wait = False):
        self.queue_injected.put(command)
        if wait:
            while not (command.hasFinished() or command.hasTimedOut()):
                time.sleep(0.125)

    def requestWrite(self, nodes, file_name = None, filter_by_machine = False, file_handler = None):
        if self._progress != 0:
            self._error_message = Message(i18n_catalog.i18nc("@info:status",
                                                             "Unable to start a new print job because the printer is busy. Please check the printer.")
                                          )
            self._error_message.show()
            return

        #if self._printer_state != "idle":
        #    self._error_message = Message(i18n_catalog.i18nc("@info:status",
        #                                                     "Unable to start a new print job, printer is busy. Current printer status is %s.") % self._printer_state
        #                                  )
        #    self._error_message.show()
        #    return

        if self._print_thread.isRunning():
            Logger.log("i", "Print is already going to be prepared!")
            return

        if not self.connectionState == ConnectionState.connected:
            Logger.log("e", "Printer not connected!")
            return

        Application.getInstance().showPrintMonitor.emit(True)

        self._print_thread.start()
        
    def _print(self):
        """ # - shouldn't happen
        while self._connect_thread.isAlive():
            Logger.log("e", "_connect_thread is alive!")
            time.sleep(1)
        """

        if self.queue_gcode:
            Logger.log("w", "Queue is not empty! Clearing...")
            self.queue_gcode.clear()
        
        # Procedure before filling the queue
        self._print_pre_fill_gcode()
        
        # Threads are very fastttt....
        self._send_is_blocked = True
        
        # Fill queue with lines
        self._print_fill_with_gcode()
        
        # Let get Thread send our lines!
        self._send_is_blocked = False
        
        # Procedure after filling the queue
        self._print_post_fill_gcode()

    def _print_pre_fill_gcode(self):
        Logger.log("w", "SerialOutputDevice._print_pre_fill_gcode")

    def _print_fill_with_gcode(self):
        Logger.log("w", "SerialOutputDevice._print_fill_with_gcode")
        # Get G-Code from application
        gcode_list = getattr(Application.getInstance().getController().getScene(), "gcode_list")
        
        # Fill queue with G-Code
        Logger.log("d", "Fill queue with G-Code")
        for entry in gcode_list:
            splitted_entries = entry.split("\n")
            for splitted_entry in splitted_entries:
                if splitted_entry:
                    #Logger.log("w", "Parsing into queue: %s", repr(splitted_entry))
                    #self.queue_gcode.put(GCodeLibrary.identifyLine(splitted_entry))
                    #Logger.log("w", "Adding to queue: %s", repr(splitted_entry))
                    #self.queue_gcode.put(splitted_entry)
                    self.queue_gcode.append(GCodeLibrary.identifyLine(splitted_entry))
        
    def _print_post_fill_gcode(self):
        Logger.log("w", "SerialOutputDevice._print_pre_fill_gcode")
        self.queue_gcode_size = len(self.queue_gcode)

    ##  Request data from the connected device.
    def _update(self):
        return

@signalemitter
class SerialWifiCommonOutputDevice(SerialOutputDevice):
    def __init__(self, name, address, properties):
        super().__init__(name)
        self._address_ip = address
        self._address_port = 23
        self._properties = properties  # Properties dict as provided by zero conf

        self.setPriority(2) # Make sure the output device gets selected above local file output
        self.setShortDescription(i18n_catalog.i18nc("@action:button Preceded by 'Ready to'.", "Print via WiFi"))
        self.setDescription(i18n_catalog.i18nc("@properties:tooltip", "Print on '%s' [CuraBridge]") %name)
        self.setConnectionText(i18n_catalog.i18nc("@properties:tooltip", "Connected to '%s'") %name)

        # Serial connector
        self.serial_connector = WifiConnectionFactory

        self._error_message = None
    
    def getProperties(self):
        return self._properties

    def getProperty(self, key):
        if type(key) is bytes:
            key = key.encode("utf-8")
        
        if key in self._properties:
            return self._properties.get(key, b"").decode("utf-8")
        else:
            return ""

    def getAddressIp(self):
        return self._address_ip   

    def getAddressPort(self):
        return self._address_port

# Direct printing via WiFi
class SerialWifiOutputDevice(SerialWifiCommonOutputDevice):
    def __init__(self, name, address, properties):
        super().__init__(name, address, properties)
        self.setShortDescription(i18n_catalog.i18nc("@action:button Preceded by 'Ready to'.", "Print via WiFi"))

class SerialWifiSDOutputDevice(SerialWifiCommonOutputDevice):
    _temp_file_name = "temp.gco"
    _sd_card_slot = 0
    
    def __init__(self, name, address, properties):
        super().__init__(name, address, properties)
        self.setShortDescription(i18n_catalog.i18nc("@action:button Preceded by 'Ready to'.", "Print via WiFi (cached)"))
    
    def _print_pre_fill_gcode(self):
        Logger.log("w", "SerialWifiOutputDevice._print_pre_fill_gcode")
        sd_init_tries = 0
        
        initializeSDcard = GCodeLibrary.RepRapCommands().M21()
        initializeSDcard.setSdSlot(self._sd_card_slot)
        
        while not initializeSDcard.isSDCardInitialized() and not sd_init_tries >= 3:
            initializeSDcard.reset()
            self.injectCommand(initializeSDcard, wait = True)
            if initializeSDcard.isSDCardInitialized() is None:
                Logger.log("i", "Printer seems to be in write mode. Trying to close the file..")
                self.injectCommand(GCodeLibrary.RepRapCommands().M29(), wait = True)
            sd_init_tries += 1
            
        if self._sd_card_status != "ok":
            raise Exception("Problems initializing SD card")
        
        super()._print_pre_fill_gcode()
    
    def _print_fill_with_gcode(self):
        Logger.log("w", "SerialWifiOutputDevice._print_fill_with_gcode")

        # Begin writing
        beginWriteFile = GCodeLibrary.RepRapCommands().M28()
        beginWriteFile.setFile(self._temp_file_name)
        #self.queue_gcode.put(beginWriteFile)
        self.queue_gcode.append(beginWriteFile)
        
        # Fill in the original GCode lines
        super()._print_fill_with_gcode()
        
        # Let the temp file remove itself
        removeFile = GCodeLibrary.RepRapCommands().M30()
        removeFile.setFile(self._temp_file_name)
        #self.queue_gcode.put(removeFile)
        self.queue_gcode.append(removeFile)
        
        # Stop writing to SD
        endWriteFile = GCodeLibrary.RepRapCommands().M29()
        endWriteFile.setFile(self._temp_file_name)
        #self.queue_gcode.put(endWriteFile)
        self.queue_gcode.append(endWriteFile)
        
        # Select the temp file
        selectFile = GCodeLibrary.RepRapCommands().M23()
        selectFile.setFile(self._temp_file_name)
        #self.queue_gcode.put(selectFile)
        self.queue_gcode.append(selectFile)
        
        # Start SD printing
        startPausePrint = GCodeLibrary.RepRapCommands().M24()
        #self.queue_gcode.put(startPausePrint)
        self.queue_gcode.append(startPausePrint)
        























