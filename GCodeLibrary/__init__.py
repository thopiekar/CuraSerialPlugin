'''
Created on 18.11.2016

@author: thopiekar
'''

class GCodeFlavors():
    FiveD = 0
    Teacup = 1
    Sprinter = 2
    Marlin = 3
    Repetier = 4
    Smoothie = 5
    RepRapFirmware = 6
    Machinekit = 7
    Makerbot = 8
    gbrl = 9
    Redeem = 10
    MK4duo = 11
    MarlinBQ = 12
    
    def getFlavour(self, name):
        try:
            return getattr(self, name)
        except Exception:
            return None

class GCodeOptions():
    LETTER_G = "G"
    LETTER_M = "M"
    LETTER_T = "T"
    LETTER_S = "S"
    LETTER_P = "P"
    LETTER_X = "X"
    LETTER_Y = "Y"
    LETTER_Z = "Z"
    LETTER_U = "U"
    LETTER_V = "V"
    LETTER_W = "W"
    LETTER_I = "I"
    LETTER_J = "J"
    LETTER_D = "D"
    LETTER_H = "H"
    LETTER_F = "F"
    LETTER_R = "R"
    LETTER_Q = "Q"
    LETTER_E = "E"
    LETTER_ASTERISK = "*"

    
    Standard = LETTER_G
    RepRap = LETTER_M
    Tool = "T"
    Time = "S" # second  
    Temperature = "S" 
    Voltage = "S"
    Parameter = "P"
    MilliTime = "P" # milliseconds
    Proportional = "P"  # Kp in PID Tuning
    X_Axis = "X"
    Y_Axis = "Y"
    Z_Axis = "Z"
    U_Axis = "U"
    V_Axis = "V"
    W_Axis = "W"
    X_Offset = "I" # in arc move;
    Integral = "I" # Ki in PID Tuning
    Y_Offset = "J" # in arc move
    Diameter = "D"
    Derivative = "D" #(Kd) in PID Tuning
    Heater = "H" # heater number in PID Tuning
    Feedrate = "F"
    StandbyTemperature = "R"
    #Q - not used
    Extrudate = "E"
    LineNumber = "N"
    CheckSum = LETTER_ASTERISK

class CodeCommand(object):
    command_family = None
    command_class = None
    
    line_number = None
    line_passed = None # line provided by __init__
    
    okCommand = None
    dryRun = False
    
    supportedOptions = None
    
    recommendedTimeOut = None

    def __init__(self, line = None, verifyCheckSum = True):
        if self.command_family is None:
            raise ValueError("command_family not set!")
        self.command_class = int(self.__class__.__name__[1:])
        
        self.finished = False
        self.timedOut = False
                
        self.checksum = None
        
        self.comment = None
        
        if type(self.supportedOptions) is list:
            self.options = {}
        elif type(self.supportedOptions) is str:
            self.options = {}
        else: 
            self.options = None
                
        if line:
            if type(line) == str:
                line = line.split()
            self.parseLine(line)
            if self.hasCheckSum() and verifyCheckSum:
                self.verifyCheckSum()
        
        return
    
    def isOkCommand(self, mode = None):
        if self.okCommand is None:
            raise NotImplementedError("Not implemented!")
        if not mode is None:
            self.okCommand = mode
        return self.okCommand

    def _parseLine(self, line):
        # Parse comment
        for block in line:
            if block.startswith(";"):
                comment_pos = line.index(block)
                self.comment = line[comment_pos+1:]
                line = line[:comment_pos]
                
        # Parse line number
        if line[0].startswith(GCodeOptions.LineNumber):
            self.setLineNumber(line[0][1:])
            del line[0]

        # Parse checksum
        if line[-1][0] == GCodeOptions.CheckSum:
            self.setCheckSum(line[-1][1:])
            del line[-1]
        
        return line
    
    def parseLine(self, line):      
        raise NotImplementedError("Not implemented!")
    
    def parseOptions(self, options):
        if type(self.supportedOptions) is None:
            raise NotImplementedError("Supported options not set!")
        
        elif type(self.supportedOptions) is list:
            option_letters = [] 
            for option in options:
                option_letters.append(option[0])
            
            unsupported_commands = set(option_letters) - set(self.supportedOptions + [self.command_family]) 
            if unsupported_commands:
                raise ValueError("Unknown options passed: %s" %list(unsupported_commands))
            
            for letter in option_letters:
                for option in options:
                    if option[0] == letter:
                        self.addOption(letter, option[1:])
                        continue

        elif type(self.supportedOptions) is str:
            self.options = options
            
    def parseAnswer(self, answer):
        if self.isOkCommand() and answer == "ok":
            self.finished = True
    
    def hasFinished(self):
        if not self.isOkCommand():
            return True
        return self.finished
    
    def hasTimedOut(self, state = None):
        if not state is None:
            self.timedOut = state 
        return self.timedOut
    
    def reset(self):
        self.finished = False
        self.timedOut = False
    
    def addOption(self, letter, value):
        if not type(self.options) is dict:
            raise ValueError("Options are not a dict!") 
        self.options[letter] = value
    
    def hasOption(self, letter):
        if not type(self.options) is dict:
            raise ValueError("Options are not a dict!") 
        return letter in self.options.keys()
    
    def getOption(self, letter):
        if not type(self.options) is dict:
            raise ValueError("Options are not a dict!") 
        return self.options[letter]
    
    def setOptions(self, options):
        self.options = options
        return
    
    def getOptions(self):
        return self.options
    
    def removeOption(self, letter):
        self.options.pop(letter)
    
    
    def setCheckSum(self, checksum):
        self.checksum = checksum
        return
    
    def hasCheckSum(self):
        return not self.checksum is None
    
    def getCheckSum(self):
        if not self.checksum is None:
            raise ValueError("Checksum unknown!") 
        return self.checksum

    def setDryRun(self, mode):
        self.dryRun = mode
        return

    def getDryRun(self):
        return self.dryRun

    def setLineNumber(self, number):
        if type(number) is float:
            raise ValueError("Line number is float! That doesn't make any sense!")
        if type(number) is str and "." in number:
            raise ValueError("Line number includes a '.'. I've never seen a 1.245 line!")
        if type(number) == str:
            number = int(number)

        self.line_number = number
        return
    
    def hasLineNumber(self):
        return not self.line_number is None
    
    def getLineNumber(self):
        return self.line_number


    def line(self, with_line_number = True):
        line = ""
        
        # Prefixes:
        if self.hasLineNumber() and with_line_number:
            line += "%s%s " %(GCodeOptions.LineNumber, self.line_number)
        
        # GCode command
        line += "%s%s" %(self.command_family, self.command_class)
        
        # Suffixes // Options
        if type(self.options) is dict:
            for key in sorted(self.options.keys()):
                if key == "E" and self.dryRun: # Prevent extrusion in dryRun
                    continue
                line += " %s%s" %(key, self.options[key])
        if type(self.options) is str:
            line += " " + self.options
        
        return line

    def __str__(self):
        return str(self.line())
    
    def __bytes__(self):
        return bytes(self.__str__().encode(encoding='utf_8'))

"""class CodeOkCommand():
    def isOkCommand(self):
        return True

class CodeNormalCommand():
    def isOkCommand(self):
        return False

"""
class GCodeCommonCommand(CodeCommand):
    command_family = GCodeOptions.Standard
    
    def parseLine(self, line):
        line = CodeCommand._parseLine(self, line)
        
        # Parse line number
        if not line[0].startswith(GCodeOptions.Standard):
            raise ValueError("Passed line is not a standard GCode command!")
        del line[0]
        
        # Parse left options
        self.parseOptions(line)
        
class GCodeNormalCommand(GCodeCommonCommand):
    okCommand = False 

class GCodeOkCommand(GCodeCommonCommand):
    okCommand = True

class GCodeCommands():
    class G0(GCodeOkCommand):
        supportedOptions = [GCodeOptions.X_Axis,
                            GCodeOptions.Y_Axis,
                            GCodeOptions.Z_Axis,
                            GCodeOptions.Extrudate,
                            GCodeOptions.Feedrate,
                            GCodeOptions.LETTER_S]
    
    class G1(GCodeOkCommand):
        supportedOptions = [GCodeOptions.X_Axis,
                            GCodeOptions.Y_Axis,
                            GCodeOptions.Z_Axis,
                            GCodeOptions.Extrudate,
                            GCodeOptions.Feedrate,
                            GCodeOptions.LETTER_S]
        pass
    
    class G28(GCodeOkCommand):
        pass
    
    class G92(GCodeOkCommand):
        supportedOptions = [GCodeOptions.X_Axis,
                            GCodeOptions.Y_Axis,
                            GCodeOptions.Z_Axis,
                            GCodeOptions.Extrudate
                            ]

class RepRapCommonCommand(CodeCommand):
    command_family = GCodeOptions.RepRap

    def parseLine(self, line):
        line = CodeCommand._parseLine(self, line)
        
        # Parse line number
        if not line[0].startswith(GCodeOptions.RepRap):
            raise ValueError("Passed line is not a standard GCode command!")
        del line[0]
        
        # Parse left options
        self.parseOptions(line)

class RepRapNormalCommand(RepRapCommonCommand):
    okCommand = False

class RepRapOkCommand(RepRapCommonCommand):
    okCommand = True

class RepRapCommands():
    class M21(RepRapOkCommand):
        supportedOptions = [GCodeOptions.LETTER_P]
        sd_card_initialized = None

        def parseAnswer(self, answer):
            super().parseAnswer(answer)

            if answer == "echo:SD card ok":
                self.sd_card_initialized = True
            elif answer in ["echo:SD init fail", "Error:volume.init failed"]:
                self.sd_card_initialized = False
        
        def isSDCardInitialized(self):
            """E.g. when our printer is still in file writing mode,
            it will only answer 'ok' and write our sent line.
            """
            return self.sd_card_initialized
        
        def setSdSlot(self, slot = None):
            if slot == None:
                del self.options[GCodeOptions.LETTER_S]
            self.options[GCodeOptions.LETTER_P] = slot
        
        def getSdSlot(self):
            return self.options[GCodeOptions.LETTER_P]
    
    class M22(RepRapOkCommand): # TOOD: Commonize with M21
        supportedOptions = [GCodeOptions.LETTER_P]
        
        def setSdSlot(self, slot = None):
            if slot == None:
                del self.options[GCodeOptions.LETTER_S]
            self.options[GCodeOptions.LETTER_P] = slot
        
        def getSdSlot(self):
            return self.options[GCodeOptions.LETTER_P]
    
    class M23(RepRapOkCommand):
        "Select SD file"
        supportedOptions = str()
        
        def setFile(self, file):
            self.setOptions(file)
        
        def getFile(self):
            return self.getOptions()
    
    class M24(RepRapOkCommand):
        "Start/resume SD print"
        supportedOptions = []
    
    class M25(RepRapOkCommand):
        "Pause SD print"
        supportedOptions = []
    
    class M26(RepRapOkCommand):
        "Set SD position"
        supportedOptions = [GCodeOptions.LETTER_S]
        
    class M27(RepRapOkCommand):
        "Status of SD printing"
        
        "Not SD printing" # Answer 
        supportedOptions = []
    
    class M28(RepRapOkCommand):
        "Begin write to SD card"
        supportedOptions = str()
        
        """
        echo:SD card ok
        file to open: temp.gcode
        echo:Now fresh file: temp.gcode
        open failed, File: temp.gcode.
        ok
        file to open: temp.gco
        echo:Now fresh file: temp.gco
        Writing to file: temp.gco
        ok
        """

        def setFile(self, file):
            self.setOptions(file)

        def getFile(self):
            return self.getOptions()

    class M29(RepRapOkCommand):
        "Stop writing to SD card"
        supportedOptions = str()

        def setFile(self, file):
            self.setOptions(file)

        def getFile(self):
            return self.getOptions()

    class M30(RepRapOkCommand):
        "Delete a file on the SD card"
        supportedOptions = str()

        def setFile(self, file):
            self.setOptions(file)

        def getFile(self):
            return self.getOptions()

    class M31(RepRapOkCommand):
        "Output time since last M109 or SD card start to serial"
        "echo:54 min, 38 sec" # Answer

    class M32(RepRapOkCommand):
        "Select file and start SD print"
        supportedOptions = []

    class M104(RepRapOkCommand):
        supportedOptions = [GCodeOptions.LETTER_S]
        
        def setDryRun(self, mode):
            self.options[GCodeOptions.LETTER_S] = 50
            return super().setDryRun(mode)
    
    class M105(RepRapOkCommand):
        "ok T:24.0 /0.0 B:0.0 /0.0 T0:24.0 /0.0 @:0 B@:0"
        supportedOptions = [GCodeOptions.LETTER_S]
    
    class M106(RepRapOkCommand):
        supportedOptions = [GCodeOptions.LETTER_S]
    
    class M107(RepRapOkCommand):
        supportedOptions = [GCodeOptions.LETTER_S]
    
    class M109(RepRapOkCommand):
        "T:24.0 E:0 W:?"
        supportedOptions = [GCodeOptions.LETTER_S]
        recommendedTimeOut = -1

        def setDryRun(self, mode):
            self.options[GCodeOptions.LETTER_S] = 50
            return super().setDryRun(mode)
    
    class M117(RepRapOkCommand):
        supportedOptions = str()
        
        def setText(self, text):
            self.setOptions(text)
        
        def getText(self):
            return self.getOptions()
    
    class M140(RepRapOkCommand):
        "ok"
        supportedOptions = [GCodeOptions.LETTER_S]

        def setDryRun(self, mode):
            self.options[GCodeOptions.LETTER_S] = 50
            return super().setDryRun(mode)

    class M800(RepRapOkCommand):
        supportedOptions = []
        recommendedTimeOut = -1

    class M801(RepRapOkCommand):
        supportedOptions = []

def identifyLine(line):
    line = line.split()
    if not line:
        return None
    current_pos = 0
    if line[current_pos].startswith("N"):
        current_pos += 1
    elif line[current_pos][0] is GCodeOptions.Standard:
        command = getattr(GCodeCommands(), line[current_pos])(line = line)
        return command
    elif line[current_pos][0] is GCodeOptions.RepRap:
        command = getattr(RepRapCommands(), line[current_pos])(line = line)
        return command
    elif line[current_pos][0] == ";":
        return None

if __name__ == "__main__":
    test_gcode = open("/home/thopiekar/Desktop/BH2_Origami_2.gcode").read()
    test_gcode = test_gcode.split("\n")
    for line in test_gcode:
        print(repr(line))
        command = identifyLine(line)
        if command:
            command.setDryRun(True)
            print(command)
            #print(command.isOkCommand())
            #print(command.hasFinished())
    """temp_file = "temp.gcode"
    initializeSDcard = RepRapCommands().M21()
    initializeSDcard.setSdSlot(0)
    print(initializeSDcard)
    beginWriteFile = RepRapCommands().M28()
    beginWriteFile.setFile(temp_file)
    print(beginWriteFile)
    removeFile = RepRapCommands().M30()
    removeFile.setFile(temp_file)
    print(removeFile)
    endWriteFile = RepRapCommands().M29()
    endWriteFile.setFile(temp_file)
    print(endWriteFile)
    selectFile = RepRapCommands().M23()
    selectFile.setFile(temp_file)
    print(selectFile)
    startPausePrint = RepRapCommands().M24()
    print(startPausePrint)
    releaseSDcard = RepRapCommands().M22()
    releaseSDcard.setSdSlot(0)
    print(releaseSDcard)
    """
