from UM.OutputDevice.OutputDevicePlugin import OutputDevicePlugin
from . import SerialWifiOutputDevice #@UnresolvedImport

from zeroconf import Zeroconf, ServiceBrowser, ServiceStateChange, ServiceInfo
from UM.Logger import Logger
from UM.Signal import Signal, signalemitter
#from UM.Application import Application
#from UM.Preferences import Preferences

import time

import socket

@signalemitter
class SerialWifiOutputDevicePlugin(OutputDevicePlugin):
    _mdnsName = u'_cura-serialwifi._tcp.local.'
    
    def __init__(self):
        super().__init__()
        self._zero_conf = None
        self._browser = None
        self._printers = {}

        # Because the model needs to be created in the same thread as the QMLEngine, we use a signal.
        self.addPrinterSignal.connect(self.addOutputDevice)
        self.removePrinterSignal.connect(self.removePrinter)

        # Get list of manual printers from preferences
        #self._preferences = Preferences.getInstance()

    addPrinterSignal = Signal()
    removePrinterSignal = Signal()

    ##  Start looking for devices on network.
    def start(self):
        # Make sure we start a new session.
        self.stop()
        
        # After network switching, one must make a new instance of Zeroconf
        # On windows, the instance creation is very fast (unnoticable). Other platforms?
        self._zero_conf = Zeroconf()
        self._browser = ServiceBrowser(self._zero_conf, self._mdnsName, [self._onServiceChanged])

    ##  Stop looking for devices on network
    def stop(self):
        # ZeroconfBrowser
        if self._browser:
            self._browser.cancel()
            self._browser = None
            self._old_printers = [printer_name for printer_name in self._printers]
            self._printers = {}
        
        # Zeroconf
        if self._zero_conf is not None:
            self._zero_conf.close()
        

    def _is_valid_ip(self, address):
        try:
            socket.inet_aton(address)
            return True
        except socket.error:
            return False

    def _resolve_dns(self, address):
        try:
            return socket.gethostbyname(address)
        except socket.gaierror:
            return None
    
    ##  Handler for zeroConf detection
    def _onServiceChanged(self, zeroconf, service_type, name, state_change):
        if state_change == ServiceStateChange.Added:
            Logger.log("d", "Bonjour service added: %s" % name)

            # First try getting info from zeroconf cache
            info = ServiceInfo(service_type, name, properties = {})
            for record in zeroconf.cache.entries_with_name(name.lower()):
                info.update_record(zeroconf, time.time(), record)

            for record in zeroconf.cache.entries_with_name(info.server):
                info.update_record(zeroconf, time.time(), record)
                if info.address:
                    break

            # Resolve server address if possible
            if info.server:
                ip_address = None
                if not self._is_valid_ip(info.server):
                    ip_address = self._resolve_dns(info.server)
                else:
                    ip_address = info.server
            
            Logger.log("d", "ip_address is: %s" %repr(ip_address))
            # Request more data if info is not complete
            #if not ip_address:
            #    Logger.log("d", "Trying to get address of %s", name)
            #    info = zeroconf.get_service_info(service_type, name)
            #Logger.log("d", "Info2: %s" %repr(info))

            if ip_address:
                printer_name = name[:-(len(info.type)+1)]
                self.addPrinterSignal.emit(printer_name, ip_address, info.properties)
                Logger.log("d", "Adding printer: %s" %printer_name)
            else:
                Logger.log("w", "Can not verify: %s" %repr(info))

        elif state_change == ServiceStateChange.Removed:
            Logger.log("d", "Bonjour service removed: %s" % name)
            self.removePrinterSignal.emit(str(name))

    ##  Because the model needs to be created in the same thread as the QMLEngine, we use a signal.
    def addOutputDevice(self, name, address, properties):
        if not name in self._printers.keys():
            printer = SerialWifiOutputDevice.SerialWifiOutputDevice(name, address, properties)
            printer.connect()
            self._printers[printer.getName()] = printer
            self.getOutputDeviceManager().addOutputDevice(printer)

    def removePrinter(self, name):
        printer = self._printers.pop(name, None)
        if printer:
            if printer.isConnected():
                printer.disconnect()
            self.getOutputDeviceManager().removeOutputDevice(printer)
