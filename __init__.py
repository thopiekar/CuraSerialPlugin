# Copyright (c) 2015 Ultimaker B.V.
# Cura is released under the terms of the AGPLv3 or higher.
from . import SerialWifiOutputDevicePlugin #@UnresolvedImport
from UM.i18n import i18nCatalog
catalog = i18nCatalog("cura")

def getMetaData():
    return {
        "plugin": {
            "name": "Wifi-Serial-Bridge",
            "author": "Thomas Karl Pietrowski",
            "description": catalog.i18nc("@info:whatsthis", "Plugin which enables printing via Wifi."),
            "version": "0.1",
            "api": 3
        }
    }

def register(app):
    return { "output_device": SerialWifiOutputDevicePlugin.SerialWifiOutputDevicePlugin(),
            }