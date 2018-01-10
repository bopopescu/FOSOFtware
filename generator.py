import sys
import serial
import numpy as np
import pandas as pd
import u3
import u6
import os
import LabJackPython
import struct
import time

_DEFAULT_FILE_LOCATION_ = "C:/DEVICEDATA/"
info_file = pd.read_csv(_DEFAULT_FILE_LOCATION_ + "generator.csv")
_OFFSET_DEFAULT_ = int(info_file['Default Offset Frequency [Hz]'].values[0])
_RANGE_DEFAULT_ = info_file['Default Scan Range'].values[0]
_E_FIELD_DEFAULT_ = int(info_file['Default Peak Electric Field Amplitude [V/cm]'] \
                                 .values[0])

_GPIB_ = int(info_file["GPIB Address"].values[0])
_COM_ = int(info_file["COM Port"].values[0])
_KEITHLEY_COM_ = int(info_file["Keithley COM Port"].values[0])
_CALIBRATION_FOLDER_ = info_file["Calibration Folder"].values[0]
_BLIND_FILE_ = info_file["Blind File"].values[0]
_JITTERS_FILE_ = info_file["Jitters File"].values[0]
_KEITHLEY_CH_A_ = int(info_file["Keithley Channel A"].values[0])
_KEITHLEY_CH_B_ = int(info_file["Keithley Channel B"].values[0])

class Generator(object):
    ''' A class to control the RF generator for the FOSOF waveguides in the
    hydrogen experiment. The purpose of this class is to clean up the code
    for FOSOF acquisition and to block access to the blind file. This should
    lower the chances of accidentally printing the blind.

    This class is far from complete in regards to all of the functions offered
    by the generator, but we can add them as they become important to our data
    acquisition.
    '''

    def __init__(self, calib = False, offset_freq = _OFFSET_DEFAULT_, \
                 scan_range = _RANGE_DEFAULT_, e_field = _E_FIELD_DEFAULT_, \
                 a_on = True, b_on = True):
        ''' Opens the generator using the COM port specified in the global
        variables. The 'calib' variable controls whether or not the blind
        offset is applied to the frequency and whether the user can change the
        power directly or if they must specify an electric field amplitude to
        use.
        '''

        self.gpib_address = _GPIB_
        self.com_port = _COM_
        self.keithley_com = _KEITHLEY_COM_

        if isinstance(calib, bool):
            self.calib_mode = calib

        if isinstance(a_on, bool):
            self.a_on = a_on

        if isinstance(b_on, bool):
            self.b_on = b_on

        # Does not set the offset frequency if the generator is in calibration
        # mode.
        if isinstance(offset_freq, int):
            if not self.calib_mode:
                self._offset_freq = float(offset_freq) / 10**6
            else:
                self._offset_freq = 0.0
        else:
            print("Offset frequency specified is not an int. Setting to " + \
                  "the default of 625 Hz.")
            self._offset_freq = 625. / 10**6 # [MHz]

        # Both the blind and the jitters are applied on top of the set RF
        # frequency. Both have a magnitude of up to 100 kHz. The blind is stored
        # as a numpy file so as to prevent the blind from being observed. DO NOT
        # PRINT THE BLIND. The frequency jitters were a random set of numbers
        # generated using numpy. There are enough jitters so as to apply a
        # different value to every carrier frequency. They protect us from
        # seeing the blind if we were to look at the generator output. In
        # addition to the jitters, the generator display is blanked (see below).
        self.blind = np.load(_BLIND_FILE_) # [MHz]
        self.jitters = np.loadtxt(_JITTERS_FILE_) # [MHz]

        # The waveguide calibration files should be generated previously and
        # placed in the location listed in the global variables. The scan
        # ranges are listed as small, medium, large and extra large.
        if not self.calib_mode:
            ranges = info_file["Scan Ranges"].values[0].split(";")
            if isinstance(scan_range, str):
                if scan_range in ['small', 'medium', 'large', 'extralarge']:
                    self.scan_range = scan_range
                    if scan_range == 'small':
                        self.f_min_max = [ranges[0], ranges[1]]
                    if scan_range == 'medium':
                        self.f_min_max = [ranges[2], ranges[3]]
                    if scan_range == 'large':
                        self.f_min_max = [ranges[4], ranges[5]]
                    if scan_range == 'extralarge':
                        self.f_min_max = [ranges[6], ranges[7]]
                    print("Scan range set to " + self.scan_range)
                else:
                    print("Scan range must be \'small\', \'medium\', \'large\' " + \
                        "or \'extralarge\'. Cannot open generator.")
                    return
            else:
                print("Scan range must be \'small\', \'medium\', \'large\' " + \
                    "or \'extralarge\'. Cannot open generator.")
                return

            # Finding the list of electric field amplitudes for which there is
            # a calibration file in the scan range folder
            e_field_values = []
            calibration_files = os.listdir(_CALIBRATION_FOLDER_ + \
                                        self.scan_range + "/")
            for flname in calibration_files:
                if flname.find('E=') > -1:
                    e_field_values.append(int(flname[flname.find('E=')+2: \
                                                    flname.find('.txt')]))

            # Checking the value given for electric field. Must be an integer and
            # must have a calibration file for the scan range specified.
            if isinstance(e_field, int):
                if e_field in e_field_values:
                    self.e_field = e_field
                    print("Electric field set to " + str(e_field) + "V/cm.")
                    self.calibration_files = [fl for fl in calibration_files \
                                            if fl.find(str(e_field)) > -1]
                else:
                    print("Cannot find a calibration file for the electric " + \
                        "field given.")
                    return
            else:
                print("Invalid electric field given. Must be an integer")
                return

            # Open the calibration files as pandas dataframes. Hopefully one day
            # soon, we'll update this system to just have one file with many
            # frequencies and powers.
            if self.calibration_files[0].find("Waveguide_A"):
                self.calib_A = pd.read_csv(_CALIBRATION_FOLDER_ + \
                                        self.scan_range + "/" + \
                                        self.calibration_files[0], sep = "\t")
                self.calib_B = pd.read_csv(_CALIBRATION_FOLDER_ + \
                                        self.scan_range + "/" + \
                                        self.calibration_files[1], sep = "\t")
            else:
                self.calib_A = pd.read_csv(_CALIBRATION_FOLDER_ + \
                                        self.scan_range + "/" + \
                                        self.calibration_files[1], sep = "\t")
                self.calib_B = pd.read_csv(_CALIBRATION_FOLDER_ + \
                                        self.scan_range + "/" + \
                                        self.calibration_files[0], sep = "\t")
    
            self.calib_A = self.calib_A.set_index("Frequency [MHz]")
            self.calib_B = self.calib_B.set_index("Frequency [MHz]")

            # Create a list of frequencies for this data set
            self.frequencies = np.linspace(round(float(self.f_min_max[0]),1), \
                                        round(float(self.f_min_max[1]),1), \
                                        num = 41)

        # Open the generator
        self.generator = serial.Serial("COM"+str(self.com_port), timeout = 5,
                                       baudrate = 9600, \
                                       bytesize = serial.SEVENBITS, \
                                       parity = serial.PARITY_EVEN, \
                                       stopbits = serial.STOPBITS_ONE)

        # Setup the USB-to-serial converter
        print(self.gpib_address)
        self.generator.write("++addr "+`self.gpib_address`+"\n")
        self.generator.write("++auto 1\n")

        # Blanking the generator display to protect us from seeing the blind.
        if not self.calib_mode:
            self.generator.write("SOURCE A; BLANK:ON \n")
            self.generator.write("SOURCE B; BLANK:ON \n")

        # Modulation setup: OFF
        self.generator.write("SOURCE A; MOD:OFF; AM:OFF \n")
        self.generator.write("SOURCE B; MOD:OFF; AM:OFF \n")

        # Turn on the generator and set the frequency to 910.0 MHz
        self.set_rf_frequency(20, 'N')
        print("RF Generator on and set to 910.0 MHz.")

        # Set up the Keithley logger to read the power detectors for the
        # waveguides
        self.logger = serial.Serial("COM"+str(self.keithley_com), timeout = 3, \
                                    xonxoff = 0, rtscts = 1, \
                                    baudrate = 9600, bytesize = 8, \
                                    parity = 'N', stopbits = 1)

    def is_open(self):
        return isinstance(self.generator, serial.Serial)

    def get_wg_power(self, channel):
        ''' Reads the waveguide power from the power detectors attached to the
        Keithley logger.
        '''

        if channel == 'A':
            self.logger.write("MEASure:VOLTage? (@" + \
                             str(_KEITHLEY_CH_A_) + \
                             ")\n")
        else:
            self.logger.write("MEASure:VOLTage? (@" + \
                              str(_KEITHLEY_CH_B_) + \
                              ")\n")

        rf_sensor_voltage = self.logger.readline()
        rf_sensor_voltage = float(rf_sensor_voltage[:rf_sensor_voltage \
                                                     .find('VDC')])

        return rf_sensor_voltage

    def power_off(self, channel):
        ''' Turns the RF level to off for the specified channel.'''

        if channel in ["A", "B"]:
            self.generator.write("SOURCE " + channel + "; RFLV:OFF \n")
        else:
            print("Please select generator channel A or B.")
            return

        if channel == "A":
            self.a_on = False
        else:
            self.b_on = False

        print("Channel " + channel + " off.")

    def power_on(self, channel):
        ''' Turns the RF level to on for the specified channel.'''

        if channel in ["A", "B"]:
            self.generator.write("SOURCE " + channel + "; RFLV:ON \n")
        else:
            print("Please select generator channel A or B.")
            return

        if channel == "A":
            self.a_on = True
        else:
            self.b_on = True

        print("Channel " + channel + " on.")

    def power_low(self, channel):
        ''' Turns the RF level to -140 dBm for the specified channel.'''

        if channel in ["A", "B"]:
            self.generator.write("SOURCE " + channel + "; RFLV:VALUE " + \
                                 "-140DBM \n")
        else:
            print("Please select generator channel A or B.")
            return

        print("Channel " + channel + " power set to -140 DBM.")

    def set_offset_frequency(self, offset_freq):
        ''' Changes the offset frequency setting if the generator object is not
        in calibration mode.
        '''

        # Error check the offset frequency given. Must be an integerin Hz.
        if isinstance(offset_freq, int):
            if not self.calib_mode:
                self._offset_freq = float(offset_freq) / 10**6
            else:
                self._offset_freq = 0.0
        else:
            print("Offset frequency specified is not an int. Setting to " + \
                  "the default of 625 Hz.")
            self._offset_freq = 625. / 10**6

        # Keep the current offset channel, frequency, and power. Change only
        # the offset frequency.
        self.set_rf_frequency(self._freq_or_ind, self.offset_channel)

    def get_offset_frequency(self):
        ''' Get method for offset frequency variable.'''

        return self._offset_freq

    def set_rf_frequency(self, freq_or_ind, offset_channel):
        ''' A function to change the frequency on the generator and change the
        power accordingly if the generator is not in calibration mode. This
        function applies the blind, jitters, and offset frequency.
        '''

        # Set up both frequencies and apply the blind/jitters and offset if
        # necessary
        if offset_channel in ['A', 'B', 'N']:
            self.offset_channel = offset_channel
        else:
            print("Generator channel specified is not valid.")
            return

        if not self.calib_mode:
            self._freq = self.frequencies[freq_or_ind] + \
                         self.jitters[freq_or_ind]
            self._freq_or_ind = freq_or_ind

            if offset_channel == 'A':
                a_freq = self._freq + self.blind + self._offset_freq
                b_freq = self._freq + self.blind
            elif offset_channel == 'B':
                a_freq = self._freq + self.blind
                b_freq = self._freq + self.blind + self._offset_freq
            elif offset_channel == 'N':
                a_freq = self._freq + self.blind
                b_freq = self._freq + self.blind

        else:
            self._freq = freq_or_ind
            self._freq_or_ind = freq_or_ind
            if offset_channel == 'A':
                a_freq = self._freq + self._offset_freq
                b_freq = self._freq
            elif offset_channel == 'B':
                a_freq = self._freq
                b_freq = self._freq + self._offset_freq
            elif offset_channel == 'N':
                a_freq = self._freq
                b_freq = self._freq
            else:
                print("Generator channel specified is not valid.")
                return

        # Change the power as well if not in calibration mode.
        if not self.calib_mode:
            a_power = str(round(self.calib_A.ix[round(a_freq,1)].values[0],1))
            b_power = str(round(self.calib_B.ix[round(b_freq,1)].values[0],1))

            if self.a_on:
                self.generator.write("SOURCE A; RFLV:VALUE " + a_power +  \
                                     " DBM; CFRQ:VALUE " + \
                                     str(round(a_freq,6)) + " MHz \n")
            if self.b_on:
                self.generator.write("SOURCE B; RFLV:VALUE " + b_power + \
                                     " DBM; CFRQ:VALUE " + \
                                     str(round(b_freq,6)) + " MHz \n")
        else:
            if self.a_on:
                self.generator.write("SOURCE A; CFRQ:VALUE " + \
                                     str(round(a_freq,6)) + \
                                     " MHz \n")
            if self.b_on:
                self.generator.write("SOURCE B; CFRQ:VALUE " + \
                                     str(round(b_freq,6)) + \
                                     " MHz \n")

        time.sleep(0.6)

    def set_rf_power(self, channel, power):
        ''' Sets the power on the specified channel to the power given (in dBm).
        Will protect against powers over 0.0 dBm and will not allow the user to
        change the power if the generator is not in calibration mode.
        '''


        if not isinstance(power, float):
            print("Power specified must be a float.")
            return

        if not (-140.0 <= power <= 0.0):
            print("Power specified must lie between -140.0 and 0.0 dBm.")
            return

        if self.calib_mode:
            if channel in ["A", "B"]:
                self.generator.write("SOURCE " + channel + "; RFLV:VALUE " + \
                                     str(power) +" dBm; \n")
                print("Power set on channel " + channel + ": " + str(power) + \
                      "dBm")
            else:
                print("Please select generator channel A or B.")
                return
        else:
            print("Cannot freely change generator power. Generator is not " + \
                  "in calibration mode.")

    def get_rf_generator_power(self, channel):
        ''' Queries the generator for the RF power on the specified channel and
        returns it in dBm.
        '''

        if channel in ["A", "B"]:
            self.generator.write("SOURCE " + channel + "; :RFLV? \n")
            rflv = self.generator.readline()
            rflv = rflv.split(";")[2]
            rflv = float(rflv[rflv.find(" ")+1:])
        else:
            print("Please select generator channel A or B.")
            return

        return rflv

    def get_rf_generator_frequency(self, channel):
        ''' Queries the generator for the RF frequency on the specified channel
        returns it in MHz. This only works if the generator is in calibration
        mode (AKA the generator frequency does not include the blind).
        '''

        if self.calib_mode:
            if channel in ["A", "B"]:
                self.generator.write("SOURCE " + channel + "; CFRQ? \n")
                freq = self.generator.readline()
                freq = float(freq[freq.find(" ")+1:freq.find(";")])/10**6
            else:
                print("Please select generator channel A or B.")
                return
        else:
            return self._freq

        return freq

    def close(self, keep_on = True):
        ''' Closes the generator and the Keithley logger. If keep_on is set to
        true, it does not change the generator power to -140 dBm. This should
        keep the RF phase difference between the RF power combiners relatively
        constant.
        '''

        # Change the frequency back to 910 MHz to continue taking data
        if not self.calib_mode:
            self.set_rf_frequency(21,"A")

        self.generator.write(":SOURCE A;:CFRQ:VALUE 910MHZ;\n")
        self.generator.write(":SOURCE B;:CFRQ:VALUE 910MHZ;\n")

        if not keep_on:
            self.generator.write(":SOURCE A;:RFLV:VALUE -140DBM;\n")
            self.generator.write(":SOURCE B;:RFLV:VALUE -140DBM;\n")

        self.generator.write(":BLANK:OFF;\n")

        self.generator.close()
        self.generator = None
        print("IFR Generator closed.")

        self.logger.close()
        self.logger = None
        print("Keithley logger for generator power closed.")
