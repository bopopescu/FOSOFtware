from __future__ import division
import serial
import pandas as pd

_DEFAULT_FILE_LOCATION_ = "C:/DEVICEDATA/"
info_file = pd.read_csv(_DEFAULT_FILE_LOCATION_ + "flowcontroller.csv")
ch1_default_setpoint = info_file["Charge Exchange Default Setpoint"].values[0]
ch2_default_setpoint = info_file["Detector Default Setpoint"].values[0]

class MKSFlowController(object):

    def __init__(self, setpoint1 = None, setpoint2 = None, is_on = -1):
        ''' Class to control and monitor the gas flow on the MKSPR4000B-F.
        '''
        # Initialization, system reset and force remote mode
        self.device = serial.Serial("COM",
                                    parity = serial.PARITY_ODD,
                                    baudrate = 9600,
                                    bytesize = serial.SEVENBITS,
                                    stopbits = serial.STOPBITS_ONE,
                                    timeout = 1)
        self.device.write("RE\r")
        self.device.readline()
        self.device.write("RT,ON\r")
        self.device.readline()
        self.device.write("?ID\r")
        self.id = self.device.readline()

        print("MKS Flow Controller ID: "+self.id)

        # Setting flow scales to SCCM
        self.device.write("RG1,10.0,12\r")
        self.device.readline()
        self.device.write("RG2,10.0,12\r")
        self.device.readline()

        # Creating and setting the setpoints for both channels
        if self.is_setpoint(setpoint1):
            self.ch1_setpoint = round(setpoint1,1)
        else:
            self.ch1_setpoint = ch1_default_setpoint

        if self.is_setpoint(setpoint2):
            self.ch2_setpoint = round(setpoint2,1)
        else:
            self.ch2_setpoint = ch2_default_setpoint

        self.device.write("SP1,"+str(self.ch1_setpoint)+"\r")
        self.device.readline()
        self.device.write("SP2,"+str(self.ch2_setpoint)+"\r")
        self.device.readline()

        # Turning on channels specified as on
        if isinstance(is_on,int) and -1 <= is_on <= 2:
            self.is_on = is_on
        else:
            self.is_on = -1

        if self.is_on == -1:
            self.device.write("VL0,OFF\r")
            self.device.readline()
        elif self.is_on == 0:
            self.device.write("VL0,ON\r")
            self.device.readline()
        elif self.is_on == 1:
            self.device.write("VL1,ON\r")
            self.device.readline()
            self.device.write("VL2,OFF\r")
            self.device.readline()
        elif self.is_on == 2:
            self.device.write("VL1,OFF\r")
            self.device.readline()
            self.device.write("VL2,ON\r")
            self.device.readline()

        return

    def is_setpoint(self, sp):
        ''' Make sure that the setpoint is properly formatted, i.e. within the
        range and a floating point number.
        '''
        if isinstance(sp,float) and 0.0 <= sp <= 5.0:
            return True
        return False

    def set_setpoint(self, setpoint, channel):
        ''' Change the setpoint of either or both channels.'''
        if self.is_setpoint(sp) and isinstance(channel,int):
            if channel == 0:
                self.ch1_setpoint = round(setpoint, 1)
                self.ch2_setpoint = round(setpoint, 1)

                self.device.write("SP1,"+str(self.ch1_setpoint)+"\r")
                self.device.readline()
                self.device.write("SP2,"+str(self.ch2_setpoint)+"\r")
                self.device.readline()
            elif channel == 1:
                self.ch1_setpoint = round(setpoint, 1)

                self.device.write("SP1,"+str(self.ch1_setpoint)+"\r")
                self.device.readline()
            elif channel == 2:
                self.ch2_setpoint = round(setpoint, 1)

                self.device.write("SP2,"+str(self.ch2_setpoint)+"\r")
                self.device.readline()
            else:
                return False

            return True

        return False

    def get_setpoint(self, channel):
        ''' Read the setpoint of either or both channels.'''
        if isinstance(channel, int):
            if channel == 0:
                self.device.write("?SP1\r")
                sp1 = self.device.readline()[:-1]

                self.device.write("?SP2\r")
                sp2 = self.device.readline()[:-1]

                return "Channel 1: " + sp1 + "\nChannel 2: " + sp2
            elif channel == 1:
                self.device.write("?SP1\r")
                sp = self.device.readline()[:-1]

                return "Channel 1: " + sp
            elif channel == 2:
                self.device.write("?SP2\r")
                sp = self.device.readline()[:-1]

                return "Channel 2: " + sp

        return None

    def get_actualvalue(self, channel):
        ''' Read the actual flow rate of either or both channels.'''
        if isinstance(channel, int):
            if channel == 0:
                self.device.write("?AV1\r")
                av1 = self.device.readline()[:-1]

                self.device.write("?AV2\r")
                av2 = self.device.readline()[:-1]

                return "Channel 1: " + sp1 + "\nChannel 2: " + sp2
            elif channel == 1:
                self.device.write("?AV1\r")
                sp = self.device.readline()[:-1]

                return "Channel 1: " + sp
            elif channel == 2:
                self.device.write("?AV2\r")
                sp = self.device.readline()[:-1]

                return "Channel 2: " + sp

        return None

    def flow_on(self, channel):
        ''' Turn on either or both channels.'''
        if isinstance(channel, int):
            if channel == 0:
                self.device.write("VL0,ON\r")
                self.device.readline()

                return True
            elif channel == 1:
                self.device.write("VL1,ON\r")
                self.device.readline()

                return True
            elif channel == 2:
                self.device.write("VL2,ON\r")
                self.device.readline()

                return True

        return False

    def flow_off(self, channel):
        ''' Turn off either or both channels.'''
        if isinstance(channel, int):
            if channel == 0:
                self.device.write("VL0,OFF\r")
                self.device.readline()

                return True
            elif channel == 1:
                self.device.write("VL1,OFF\r")
                self.device.readline()

                return True
            elif channel == 2:
                self.device.write("VL2,OFF\r")
                self.device.readline()

                return True

        return False
