from UM.Platform import Platform


if Platform.isLinux():
    import dbus
    
    class PowerManagement():
        def __init__(self):
            self.suspendInhibition = None
            try:
                devobj = dbus.SessionBus().get_object('org.kde.kded',
                                                      '/org/kde/Solid/PowerManagement/PolicyAgent')
                self.solid_session = dbus.Interface (devobj,
                                                     "org.kde.Solid.PowerManagement.PolicyAgent")
            except:
                self.solid_session = None

            self.dbus_session = dbus.SessionBus().get_object("org.freedesktop.PowerManagement",
                                                             "/org/freedesktop/PowerManagement/Inhibit")

        def setSuspendInhibited(self, state):
            if state:
                if self.solid_session:
                    self.suspendInhibition = self.solid_session.addInhibition(1, "Cura", "Test")
                self.suspendInhibition = self.dbus_session.Inhibit("Cura", "Printing via USB")
            else:
                if self.solid_session:
                    return self.solid_session.ReleaseInhibition(self.suspendInhibition)
                return self.dbus_session.UnInhibit(self.suspendInhibition)

        def hasSuspendInhibition(self):
            return self.dbus_session.HasInhibit()

        def isSuspendInhibited(self):
            return bool(self.suspendInhibition)

elif Platform.isWindows():
    import ctypes

    class PowerManagement():
        def __init__(self):
            print(dir(ctypes.windll.kernel32))

        def setSuspendInhibited(self, state):
            """
            Function used to prevent the computer from going into sleep mode.
            :param prevent: True = Prevent the system from going to sleep from this point on.
            :param prevent: False = No longer prevent the system from going to sleep.
            """
            ES_CONTINUOUS = 0x80000000
            ES_SYSTEM_REQUIRED = 0x00000001
            #SetThreadExecutionState returns 0 when failed, which is ignored. The function should be supported from windows XP and up.
            if state:
                ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED) #@UndefinedVariable
            else:
                ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS) #@UndefinedVariable
else:
    raise ImportError("Your OS is currently not supported!")

if __name__ == "__main__":
    pm = PowerManagement()
    pm.setSuspendInhibited(True)
    input("Wait!")
    pm.setSuspendInhibited(False)
