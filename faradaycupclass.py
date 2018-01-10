import u3
import LabJackPython
import fosof_qol as qol
import pandas as pd

_DEFAULT_FILE_LOCATION_ = "C:/DEVICEDATA/"
info_file = pd.read_csv(_DEFAULT_FILE_LOCATION_ + "faradaycup.csv")
info_file = info_file.set_index("F-Cup ID")

class FaradayCup(object):

    def __init__(self):

        self.device = u3.U3(autoOpen = False)
        self.device.open(serial = 320044118)
        self.device.getCalibrationData()
        self.device.configU3(FIOAnalog = 255, EIOAnalog = 255)

        self.is_open = True

    def open(self):
        if not self.is_open:
            self.device = u3.U3(autoOpen = False)
            self.device.open(serial = 320044118)
            self.device.getCalibrationData()
            self.device.configU3(FIOAnalog = 255, EIOAnalog = 255)
            self.is_open = True

    def close(self):
        if self.is_open:
            self.device.close()
            LabJackPython.Close()
            self.is_open = False

    def get_current(self, fcid):
        """ Returns the current from the Faraday cup in uA."""

        if fcid in info_file.index:
            return self.device.getAIN(int(info_file.ix[fcid]["AIN Pin"]))*10
        elif fcid == "all":
            return [self.device.getAIN(int(info_file.ix[id]["AIN Pin"]))*10 \
                    for id in info_file.index]
        else:
            raise qol.Travisty("No such f-cup ID.")