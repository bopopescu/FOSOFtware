import sys
import serial
import numpy as np
import pandas as pd
import u3
import u6
import LabJackPython
import struct
import time
from LabJackPython import LabJackException
import traceback as tb

_DEFAULT_FILE_LOCATION = "C:/DEVICEDATA/"
_SLEEP_TIME = 0.01

quench_info = pd.read_csv(_DEFAULT_FILE_LOCATION + "quench.csv") \
                .set_index("Cavity")

def isfreq(f):
    ''' Check to see if the parameter f has the properties of a frequency that
    the USBSynth can produce. The value must be a float between the values of
    34.4 and 4400.0; these are units of MHz.
    '''

    if isinstance(f, float) and 34.4 <= f <= 4400.0: return True

    return False

def ispower(p):
    ''' Check to see if the parameter p has the properties of a power setting
    for a USBSynth. Must be an integer; either 0 or 1.
    '''

    if isinstance(p,int) and (p == 0 or p == 1): return True

    return False

def isamp(a):
    ''' Check to see if the parameter p has the properties of a power setting
    for a USBSynth. Must be an integer from 0 to 3.
    '''

    if isinstance(a,int) and 0 <= a <= 3: return True

    return False

def isattenv(v):
    ''' Check to see if the parameter v has the properties of a DAC voltage
    that will be useful for the voltage attenuators. These attenuators respond
    to voltages between 0.0 and +8.0 V.
    '''

    if isinstance(v, float) and 0.0 <= v <= 8.0: return True

    return False

class QuenchError(Exception):
    ''' A custom error class to deal with all exceptions from
    opening and/or controlling quench cavities. Could contain LabJackExceptions,
    TypeErrors, ValueErrors, or other errors specific to this application.
    '''

    def __init__(self, errorString):
        self.errorString = errorString

    def __str__(self):
        return self.errorString

class Quench(object):
    ''' This class allows for the use of a single quench cavity. It provides
    easy access to all of the properties and functionality of a quench cavity
    while protecting the values that should not be changed (i.e. nominal pi
    pulse attenuator voltage).

    This class will use the LabJackPython module, as well as the Serial module
    to access the Windfreak USBSynths, the voltage attenuators (via LabJack) and
    the power detectors (via LabJack). The nominal values cannot be changed
    through this python module, but must be accessed in the csv file located
    on the Lamb Shift Google Drive.

    List of functions:
        __init__(self, com_port, cavity, freq, dio_pin, dac, dac_ain, ain_pin, \
                 **args)
        usb_on(self)
        usb_off(self)
        get_usb_status(self)
        set_frequency(self,f)
        set_usb_power(self,m)
        set_usb_amplitude(self,n)
        close_usb(self)
        open_usb(self)
        toDouble(self, buffer)
        voltageLJTDAConvert(self, voltage)
        setLJTDAVoltage(self, **args)
        getLJTDACcalibConstants(self)
        set_dac_voltage(self, dac_v)
        get_dac_voltage(self)
        get_power_v(self)
        cavity_on(self)
        cavity_off(self)
        close(self)
    '''

    def __init__(self, com_port, cavity, freq, dio_pin, dac, dac_ain, ain_pin, \
                 **args):
        ''' Initialize and open a quench cavity. args can be one of the
        following items. The default values are marked with an asterisk.

        is_on = True, False*
        - Should the quench cavity be turned on right away?

        atten_v = nominal value from file*, (float 0.0 to 8.0)
        - What voltage should be applied to the voltage attenuator for this
        quench cavity?

        u3_handle = None*, passed u3.U3() object
        - If this quench cavity is being managed by a QuenchManager, the u3
        handle associated with that QM should be passed to avoid errors due to
        opening one LabJack interface more than once.

        u6_handle = None*, passed u6.U6() object
        - If this quench cavity is being managed by a QuenchManager, the u3
        handle associated with that QM should be passed to avoid errors due to
        opening one LabJack interface more than once.
        '''
        self.dio_pin = dio_pin # DIO Pin for LJDAC
        self.dac = dac # DACA or DACB
        self.dac_ain = dac_ain # AIN Pin for reading DAC set voltage
        self.ain_pin = ain_pin # AIN Pin for reading power detector
        self.freq = freq # Frequency (MHz)
        self.cavity = cavity # Cavity name
        self.pi_pulse = quench_info['LJDAC Pi Pulse Voltage [V]'].ix[cavity]
        self.com_port = com_port

        # Check arguments to see if options are special
        if 'is_on' in args.keys():
            try:
                if isinstance(args['is_on'], bool):
                    self.is_on = args['is_on']
                else:
                    raise TypeError
            except TypeError as err:
                print("The value entered for is_on was not a bool.")
                print("Cavity will not be turned on.")
                self.is_on = False
        else:
            self.is_on = False

        # If no option specified for attenuation voltage, set the cavity
        # to pi pulse
        if 'atten_v' in args.keys():
            try:
                if isinstance(args['atten_v'], float):
                    self.atten_v = args['atten_v']
                    print("Attenuation voltage will be set to: " + \
                            str(self.atten_v) + " V")
                else:
                    raise TypeError
            except TypeError as err:
                print("The value entered for atten_v was not a float.")
                print("Cavity will be set to pi pulse.")
                self.atten_v = quench_info['LJDAC Pi Pulse Voltage [V]'] \
                                          .ix[self.cavity]
        else:
            self.atten_v = quench_info['LJDAC Pi Pulse Voltage [V]'] \
                                        .ix[self.cavity]

        # If no LabJack U3 handle is specified, a new instance will be opened.
        # This will prevent any other quenches from opening this u3.
        if 'u3_handle' in args.keys():
            if isinstance(args['u3_handle'], u3.U3):
                print("LabJack U3 inherited.")
                self.u3_handle = args['u3_handle']
                self.u3_passed = True
            else:
                raise QuenchError("TypeError: The u3_handle passed was" + \
                                  " not a U3 object. This quench cavity" + \
                                  " will not continue the __init__ routine."
                                  )
        else:
            try:
                self.u3_passed = False
                self.u3_handle = u3.U3(autoOpen = False)
                self.u3_handle.open(serial = 320044466)
                print("U3 handle opened.")
                self.u3_handle.configIO(FIOAnalog = 255)
                print("U3 FIO ports configured for analog input.")
            except LabJackException as err:
                sys.stderr.write("U3 error:")
                sys.stderr.write(tb.format_exc())
                return

        # If no LabJack U6 handle is specified, a new instance will be opened.
        # This will prevent any other quenches from opening this u6
        if 'u6_handle' in args.keys():
            if isinstance(args['u6_handle'], u6.U6):
                print("LabJack U6 inherited.")
                self.u6_handle = args['u6_handle']
                self.u6_passed = True
            else:
                raise QuenchError("TypeError: The u6_handle passed was" + \
                                  " not a U6 object. This quench cavity" + \
                                  " will not continue the __init__ routine."
                                  )
        else:
            try:
                self.u6_passed = False
                self.u6_handle = u6.U6(autoOpen = False)
                self.u6_handle.open(serial = 360007343)
                print("U6 handle opened.")
            except LabJackException as err:
                sys.stderr.write("U6 error:")
                sys.stderr.write(tb.format_exc())
                return

        # Get calibration constants for the LJTDAC
        self.calib_constants = self.getLJTDACcalibConstants()

        # Copied from synthusb.py
        self.open_usb()

        self.usb_device.write("+")
        self.model = self.usb_device.readline()[:-1]

        self.usb_device.write("-")
        self.serial_number = self.usb_device.readline()[:-1]

        self.usb_device.id = '-'.join([str(self.model),str(self.serial_number)])

        if self.is_on:
            print("Turning on cavity.")
            self.cavity_on()

    def usb_on(self):
        '''Turn on the USB synthesizer.'''
        self.usb_device.write("o1")

    def usb_off(self):
        '''Turn off the USB synthesizer. Note this does not close the COM port.
        '''
        self.usb_device.write("o0")

    def get_usb_status(self):
        '''Obtain current settings of the USB synth: frequency, amplitude, power
        and on/off status.
        '''

        status_list = []

        self.usb_device.write("f?")
        status_list.append( "Frequency: " + self.usb_device.readline() + "kHz \n" )
        self.usb_device.write("a?")
        status_list.append( "Amplitude: " + self.usb_device.readline() )
        self.usb_device.write("h?")
        status_list.append( "Power setting: " + self.usb_device.readline() )
        self.usb_device.write("o?")
        status_list.append( "On: " + self.usb_device.readline() )
        return status_list

    def set_frequency(self,f):
        ''' Set the frequency (in MHz) of the USB synthesizer. Can be from
        34.4 to 4400.0.
        '''

        if isfreq(f):
            self.freq = f
            self.usb_device.write("f"+`f`)
        else:
            raise QuenchError("Invalid frequency provided. See docs.")
        time.sleep(_SLEEP_TIME)

    def set_usb_power(self,m):
        ''' Set the power of the USB synthesizer. Can be 0 (low) or 1 (high).'''

        if ispower(m):
            self.usb_device.write("h"+`m`)
        else:
            raise QuenchError("Invalid value for power. See docs.")
        time.sleep(_SLEEP_TIME)

    def set_usb_amplitude(self,n):
        ''' Set the electric field amplitude of the USB synthesizer. Can be any
        integer from 0 (lowest) to 3 (highest).
        '''

        if isamp(n):
            self.usb_device.write("a"+`n`)
        else:
            raise QuenchError("Invalid value for amplitude. See docs.")
        time.sleep(_SLEEP_TIME)

    def close_usb(self):
        ''' Close the USB synthesizer and, if not inherited, the LabJacks.
        Note this does not turn off the synthesizer or change any of the LabJack
        settings.
        '''
        self.usb_device.close()
        self.usb_device = None

    def open_usb(self):
        ''' Opens a serial communication line to the SynthUSB.'''

        self.usb_device = serial.Serial(self.com_port,timeout=1)

    def toDouble(self, buffer):
        ''' Name: toDouble(buffer)
        Args: buffer, an array with 8 bytes
        Desc: Converts the 8 byte array into a floating point number.
        '''

        if type(buffer) == type(''):
            bufferStr = buffer[:8]
        else:
            bufferStr = ''.join(chr(x) for x in buffer[:8])
        dec, wh = struct.unpack('<Ii', bufferStr)
        return float(wh) + float(dec)/2**32

    def voltageLJTDAConvert(self, voltage):
        ''' Converts the voltage for LJTDAC into readable format'''

        return ( self.calib_constants['a_slope'] * voltage ) + \
                 self.calib_constants['a_offset']

    def setLJTDAVoltage(self, **args):
        ''' Sets the selected channel (DACA or DACB) to the specified voltage
        '''

        # Address for the accessing the DAC on the LJTDAC
        # Information is available at
        # https://labjack.com/support/datasheets/accessories/ljtick-dac
        DAC_ADDRESS = 0x12

        # SCL = pin clock for i2c communication. Set to DIOA
        # SDA = pin for data for i2c communication. Set to DIOB = DIOA+1
        sclPin = self.dio_pin # DIOA
        sdaPin = sclPin + 1 # DIOB

        # Setting the channel_address for i2c communication
        if self.dac == 'DACA':
            channel_address = 48
        elif self.dac == 'DACB':
            channel_address = 49

        # Converting voltage for i2c communication
        if 'atten_v' in args:
            converted_voltage = \
                self.voltageLJTDAConvert(args['atten_v'])
        else:
            converted_voltage = \
                self.voltageLJTDAConvert(self.atten_v)

        # Set the LJTDAC channel to the voltage
        self.u6_handle.i2c(DAC_ADDRESS, [channel_address, \
                                         int(converted_voltage/256), \
                                         int(converted_voltage%256)], \
                                         SDAPinNum = sdaPin, \
                                         SCLPinNum = sclPin)

    def getLJTDACcalibConstants(self):
        ''' Get calibration constants from LJTDAC
        '''

        # Address for the EEPROM on the LJTDAC to access its calibration
        # constants.
        # Information is available at
        # ttps://labjack.com/support/datasheets/accessories/ljtick-dac
        EEPROM_ADDRESS = 0x50

        # SCL = pin clock for i2c communication. Set to DIOA
        # SDA = pin for data for i2c communication. Set to DIOB = DIOA+1

        sclPin = self.dio_pin # DIOA
        sdaPin = sclPin + 1 # DIOB

        # Access EEPROM. Retrieve calibration constants
        calib_data = self.u6_handle.i2c(EEPROM_ADDRESS, [64], \
                                        NumI2CBytesToReceive=36, \
                                        SDAPinNum = sdaPin, SCLPinNum = sclPin
                                       )

        # Extract calibration constants
        response = calib_data['I2CBytes']

        #DACA calibration constants
        a_slope = self.toDouble(response[0:8]) # slope
        a_offset = self.toDouble(response[8:16]) # offset

        #DACB calibration constants
        b_slope = self.toDouble(response[16:24]) # slope
        b_offset = self.toDouble(response[24:32]) # offset

        return {'a_slope': a_slope, 'a_offset': a_offset,'b_slope': b_slope, \
                'b_offset': b_offset}

    def set_dac_voltage(self, dac_v):
        ''' Changes the atten_v variable and sets the DAC voltage to the new
        setting.
        '''

        if isattenv(dac_v):
            self.atten_v = dac_v

            # Set the LJDAC voltage
            self.setLJTDAVoltage()

    def get_dac_voltage(self):
        ''' Read the voltage on the DAC.'''
        return self.u6_handle.getAIN(self.dac_ain)

    def get_power_v(self):
        ''' Read the voltage from the power detector.'''
        return self.u3_handle.getAIN(self.ain_pin)

    def cavity_on(self):

        # Turn on the synthesizer.
        self.usb_on()

        # Set the synthesizer to HIGH power output mode
        self.set_usb_power(1)

        # Set the output level of the synthesizer to 3 = MAX (about 1dBm of
        # output power)
        self.set_usb_amplitude(3)

        # Set the RF frequency of the synthesizer [MHz] to whatever the current
        # setting is
        self.set_frequency(self.freq)

        # Read the settings of the synthesizer
        print('\n'.join(self.get_usb_status()))

        # Voltage to apply to the RF attenuator [V]
        print(self.cavity + ': RF attenuator set voltage [V]: ' + \
              str(self.atten_v))

        # Set the LJDAC voltage
        self.setLJTDAVoltage()

        # Reading the voltage set for the DAC channel. For testing purposes
        print(self.cavity + ' RF attenuator measured control voltage [V]: ' + \
              str(self.get_dac_voltage()) + '\n')

        self.is_on = True

    def cavity_off(self):
        ''' Turns off the USB synthesizer and sets the LJTDAC voltage to 0.0.'''

        # USB off
        self.usb_off()

        # Set the LJDAC voltage
        self.setLJTDAVoltage(atten_v = 0.0)

        self.is_on = False

    def close(self):
        ''' Closes all connections to the USB and, if not inherited, to the
        LabJacks. In addition to closing the LabJacks, this will use the
        LabJackPython.Close() function to allow another Python kernel to open
        these LabJacks.
        '''

        try:
            self.close_usb()
        except:
            sys.stderr.write(tb.format_exc())

        if not self.u3_passed:
            try:
                self.u3_handle.close()
                print("U3 closed.")
            except:
                sys.stderr.write(tb.format_exc())
        if not self.u6_passed:
            try:
                self.u6_handle.close()
                print("U6 closed.")
            except:
                sys.stderr.write(tb.format_exc())

        if not (self.u3_passed or self.u6_passed):
            try:
                LabJackPython.Close()
                print("LabJacks freed for use in other kernels.")
            except:
                sys.stderr.write(tb.format_exc())

class QuenchManager(object):
    ''' This class allows the user access to the quench cavities. With the
    current setup, all cavities share two common LabJacks for input/output to
    the voltage attenuators and power detectors. This QuenchManager class will
    allow the user to seemlessly access the data for all cavities without
    experiencing issues related to opening the same LabJack from multiple
    unrelated objects.

    In short: unless you really only want to use one quench cavity, use a
    QuenchManager object to control the quenches.

    Some specs on the WindFreak SynthUSBII:
    - Frequency can be anywhere from 34.4 MHz to 4.4 GHz. Frequency resolution
    is 0.1 MHz. The frequency should be specified as a float in MHz.
    - The power setting is an integer; either 0 (low power) or 1 (high power).
    As a reference, the maximum output power (p = 0, amplitude = 3) is about
    1 dBm.
    - The amplitude setting also changes the power and can be an integer from 0
    to 3.

    List of functions:
        open_quench(self, cavity, **args)
        get_usb_status(self, cavity)
        print_usb_status(self, cavity)
        get_usb_id(self, cavity)
        print_usb_id(self, cavity)
        set_frequency(self, cavity, freq)
        set_usb_power(self, cavity, power_setting)
        set_usb_amplitude(self, cavity, amp_setting)
        set_dac_voltage(self, cavity, dac_v)
        close_quench(self, cavity)
        cavity_on(self, cavity)
        cavity_off(self, cavity)
        get_dac_voltage(self, cavity)
        print_dac_voltage(self, cavity)
        get_cavity_power(self, cavity)
        print_cavity_power(self, cavity)
        get_statuses(self, cavities)
        get_usb_ids(self, cavities)
        get_dac_voltages(self, cavities)
        get_cavity_powers(self, cavities)
        get_power_detector_dc_in(self)
        cavities_on(self, cavities)
        cavities_off(self, cavities)
        close_quenches(self, cavities)
        close(self)
        off_and_close(self)
    '''

    def __init__(self):
        ''' Initializing the a QuenchManager involves reading the hardware data
        for the quenches from quench.csv, and opening the relevant LabJacks.
        This will not work for more than one instance of a QuenchManager since
        LabJacks cannot be opened from more than one Python kernel at a time.
        '''

        # Open quench information file.
        self.quench_info = quench_info
        num_quenches = len(self.quench_info.index)

        # Create new columns specifically for this instance of a QuenchManager.
        self.quench_info["Is Open"] = [ False for i in range(num_quenches) ]
        self.quench_info["Is On"] = [ False for i in range(num_quenches) ]
        self.quench_info["Handle"] = [ None for i in range(num_quenches) ]

        # Open the relevant LabJacks.
        try:
            self.quench_u3 = u3.U3(autoOpen = False)
            self.quench_u3.open(serial = 320044466)
            self.quench_u3.configIO(FIOAnalog = 255)
        except LabJackException as err:
            print("U3 error:")
            print(err.__str__)
            raise err
        finally:
            print("U3 opened")

        try:
            self.quench_u6 = u6.U6(autoOpen = False)
            self.quench_u6.open(serial = 360007343)
        except LabJackException as err:
            print("U6 error:")
            print(err.__str__)
            raise err
        finally:
            print("U6 opened")

    def is_open(self):
        return (isinstance(self.quench_u3, u3.U3) and isinstance(self.quench_u6,
                                                                 u6.U6))

    def open_quench(self, cavity, atten_v = None, is_on = None):
        ''' Open access to one quench cavity. The default values are marked
        with an asterisk.

        is_on = True, False*
        - Should the quench cavity be turned on right away?

        atten_v = nominal value from file*, (float 0.0 to 8.0)
        - What voltage should be applied to the voltage attenuator for this
        quench cavity?
        '''

        # First, check to make sure that the cavity specified exists
        if cavity in self.quench_info.index and \
           not self.quench_info["Is Open"].ix[cavity]:
            com_port = "COM"+str(self.quench_info["COM Port"].ix[cavity])

            # Check arguments to see if options are special
            if is_on:
                try:
                    # Fixing a mistake I made in creating the .quench files
                    # Status is passed as the is_on variable, and the values for
                    # Status are strings, not booleans.
                    if is_on == 'on':
                        is_on = True
                    elif is_on == 'off':
                        is_on = False

                    if isinstance(is_on, bool):
                        if is_on == True:
                            print("Cavity will be turned on after opening.")
                        else:
                            print("Cavity will remain off after opening.")
                    else:
                        raise TypeError
                except TypeError as err:
                    print("The value entered for is_on was not a bool.")
                    print("Cavity will not be turned on.")
                    is_on = False
            else:
                is_on = False

            # If no option specified for attenuation voltage, set the cavity
            # to pi pulse
            if atten_v:
                try:
                    if isinstance(atten_v, float):
                        print("Attenuation voltage will be set to: " + \
                              str(atten_v) + " V")
                    else:
                        raise TypeError
                except TypeError as err:
                    print("The value entered for atten_v was not a float.")
                    print("Cavity will be set to pi pulse.")
                    atten_v = float(self \
                                    .quench_info['LJDAC Pi Pulse Voltage [V]'] \
                                    .ix[cavity])
            else:
                atten_v = float(self.quench_info['LJDAC Pi Pulse Voltage [V]'] \
                                    .ix[cavity])

            # Other info (does not change)
            dio_pin = int(self.quench_info["LJDAC DIO Pin"].ix[cavity])
            dac = self.quench_info["LJDAC"].ix[cavity]
            dac_ain = int(self.quench_info["LJDAC AIN Pin"].ix[cavity])
            ain_pin = int(self.quench_info["LJ IN_POWER AIN"].ix[cavity])
            freq = round(float(self.quench_info["Frequency [MHz]"].ix[cavity]),3)

            # Try to open the quench cavity.
            quench = None
            try:
                quench = Quench(com_port, cavity, freq, dio_pin, dac, dac_ain, \
                                ain_pin, atten_v = atten_v, is_on = is_on, \
                                u3_handle = self.quench_u3, \
                                u6_handle = self.quench_u6)
            except QuenchError as err:
                print(err.__str__)
            finally:
                self.quench_info["Handle"].ix[cavity] = quench
                self.quench_info["Is Open"].ix[cavity] = True
                print(cavity + ' opened.')
        elif cavity in self.quench_info.index and \
             self.quench_info["Is Open"].ix[cavity]:
            print("Cavity " + cavity + " already open.")
        else:
            raise QuenchError("The cavity specified does not exist. Check " + \
                              "the documentation for the list of cavity names.")

    def get_usb_status(self, cavity):
        ''' Wrapper method for Quench object referred to by 'cavity'.'''

        if cavity in self.quench_info.index:
            if self.quench_info['Is Open'].ix[cavity]:
                return self.quench_info['Handle'].ix[cavity].get_usb_status()
            else:
                print("Cavity " + cavity + " not open.")
        else:
            print("Invalid cavity.")

    def print_usb_status(self, cavity):
        ''' Print the formatted output of the get_usb_status method for the
        Quench object referred to by 'cavity'.
        '''

        if cavity in self.quench_info.index:
            if self.quench_info['Is Open'].ix[cavity]:
                print('\n'.join(self.quench_info['Handle'].ix[cavity] \
                                    .get_usb_status()))
            else:
                print("Cavity " + cavity + " not open.")
        else:
            print("Invalid cavity.")

    def get_usb_id(self, cavity):
        ''' Return the USBSynth model and serial number.'''

        if cavity in self.quench_info.index:
            if self.quench_info['Is Open'].ix[cavity]:
                return self.quench_info['Handle'].ix[cavity].usb_device.id
            else:
                print("Cavity " + cavity + " not open.")
        else:
            print("Invalid cavity.")

    def print_usb_id(self, cavity):
        ''' Print the USBSynth model and serial number.'''

        if cavity in self.quench_info.index:
            if self.quench_info['Is Open'].ix[cavity]:
                print(self.quench_info['Handle'].ix[cavity].usb_device.id)
            else:
                print("Cavity " + cavity + " not open.")
        else:
            print("Invalid cavity.")

    def set_frequency(self, cavity, freq):
        ''' Set the frequency of the USBSynth output. The frequency must be
        between 34.4 and 4400.0 (MHz).
        '''

        if cavity in self.quench_info.index:
            if self.quench_info['Is Open'].ix[cavity]:
                try:
                    self.quench_info['Handle'].ix[cavity].set_frequency(freq)
                except QuenchError as err:
                    print(err.__str__)
                    print("Frequency not changed.")
                finally:
                    print("Frequency changed")
            else:
                print("Cavity " + cavity + " not open.")
        else:
            print("Invalid cavity.")

    def set_usb_power(self, cavity, power_setting):
        ''' Set the power of the USBSynth output. The power must be an
        integer; either 0 or 1.
        '''

        if cavity in self.quench_info.index:
            if self.quench_info['Is Open'].ix[cavity]:
                try:
                    self.quench_info['Handle'].ix[cavity].set_usb_power(power_setting)
                except QuenchError as err:
                    print(err.__str__)
                    print("Power not changed.")
                finally:
                    print("Power changed.")
            else:
                print("Cavity " + cavity + " not open.")
        else:
            print("Invalid cavity.")

    def set_usb_amplitude(self, cavity, amp_setting):
        ''' Set the amplitude of the USBSynth output (effectively changes
        power). Must be an integer from 0 to 3.
        '''

        if cavity in self.quench_info.index:
            if self.quench_info['Is Open'].ix[cavity]:
                try:
                    self.quench_info['Handle'].ix[cavity].set_usb_amplitude(amp_setting)
                except QuenchError as err:
                    print(err.__str__)
                    print("Amplitude not changed.")
                finally:
                    print("Amplitude changed.")
            else:
                print("Cavity " + cavity + " not open.")
        else:
            print("Invalid cavity.")

    def set_dac_voltage(self, cavity, dac_v):
        ''' DAC/Attenuator voltage. Can be any float from 0.0 to 8.0 V.
        '''

        if cavity in self.quench_info.index:
            if self.quench_info['Is Open'].ix[cavity]:
                try:
                    self.quench_info['Handle'].ix[cavity].set_dac_voltage(dac_v)
                except QuenchError as err:
                    print(err.__str__)
                    print("Attenuator voltage not changed.")
                finally:
                    print("Attenuator voltage changed.")
            else:
                print("Cavity " + cavity + " not open.")
        else:
            print("Invalid cavity.")

    def close_quench(self, cavity):
        ''' Closes the SynthUSB associated with 'cavity'. By closing only the
        synth and not releasing the Quench object, we can still easily check
        the DAC voltage and power detector reading. In order to release the
        Quench object itself, just get rid of the reference in the quench_info
        DataFrame.
        '''

        if cavity in self.quench_info.index:
            if self.quench_info['Is Open'].ix[cavity] == True:
                self.quench_info['Handle'].ix[cavity].close_usb()
                self.quench_info['Is Open'].ix[cavity] = False
                print(cavity + " closed.")
            else:
                print(cavity + " not currently open. Cannot close.")
        else:
            print("Invalid cavity.")

    def cavity_on(self, cavity):
        ''' Turns on the power for the quench cavity. If the cavity is already
        on, nothing will change.
        '''

        if cavity in self.quench_info.index:
            if self.quench_info['Is Open'].ix[cavity]:
                handle = self.quench_info['Handle'].ix[cavity]
                handle.cavity_on()
                self.quench_info['Is On'].ix[cavity] = handle.is_on
            else:
                print("Cavity " + cavity + " not open.")
        else:
            print("Invalid cavity.")

    def cavity_off(self, cavity):
        ''' Turns off the power for the quench cavity. If the cavity is already
        off, nothing will change.
        '''

        if cavity in self.quench_info.index:
            if self.quench_info['Is Open'].ix[cavity]:
                handle = self.quench_info['Handle'].ix[cavity]
                handle.cavity_off()
                self.quench_info['Is On'].ix[cavity] = handle.is_on
                print(cavity + " off")
            else:
                print("Cavity not open.")
        else:
            print("Invalid cavity.")

    def get_dac_voltage(self, cavity):
        ''' Returns the voltage set on the DAC (for voltage attenuators).'''

        # Even if the USB is not open, we can still get the DAC voltage
        if cavity in self.quench_info.index:
            if not self.quench_info['Handle'].ix[cavity] == None:
                return self.quench_info['Handle'].ix[cavity].get_dac_voltage()
            else:
                return self.quench_u6.getAIN(int(self \
                                                 .quench_info['LJDAC AIN Pin'] \
                                                 .ix[cavity]))
        else:
            print("Invalid cavity.")

    def print_dac_voltage(self, cavity):
        ''' Prints the voltage set on the DAC (for voltage attenuators).'''

        # Even if the USB is not open, we can still get the DAC voltage
        if cavity in self.quench_info.index:
            if not self.quench_info['Handle'].ix[cavity] == None:
                print(str(self.quench_info['Handle'].ix[cavity] \
                            .get_dac_voltage()) + " V")
            else:
                print(self.quench_u6.getAIN(int(self \
                                                .quench_info['LJDAC AIN Pin'] \
                                                .ix[cavity]) + " V"))
        else:
            print("Invalid cavity.")

    def get_cavity_power(self, cavity):
        ''' Returns the power detector reading for the cavity.'''

        # Even if the USB is not open, we can still read the power detector
        if cavity in self.quench_info.index:
            if not self.quench_info['Handle'].ix[cavity] == None:
                return self.quench_info['Handle'].ix[cavity].get_power_v()
            else:
                return self.quench_u3 \
                           .getAIN(int(self \
                           .quench_info['LJ IN_POWER AIN'] \
                           .ix[cavity]))
        else:
            print("Invalid cavity.")

    def print_cavity_power(self, cavity):
        ''' Prints the power detector reading for the cavity.'''

        # Even if the USB is not open, we can still read the power detector
        if cavity in self.quench_info.index:
            if not self.quench_info['Handle'].ix[cavity] == None:
                print(str(self.quench_info['Handle'].ix[cavity] \
                            .get_power_v()) + " V")
            else:
                print(self.quench_u3 \
                          .getAIN(int(self \
                          .quench_info['LJ IN_POWER AIN'] \
                          .ix[cavity]) + " V"))
        else:
            print("Invalid cavity.")

    # Functions for multiple SynthUSBs. These are just convenience functions.
    # If multiple quenches are opened at once, they will not be turned on
    # immediately and all will be set to pi_pulse.

    def open_quenches(self, cavities, atten_v = None, is_on = None):
        ''' Opens multiple cavities.
        - atten_v must be a list or numpy array of floats the same length
          as 'cavities'.
        - is_on must be a list or numpy array of bools the same length as
          'cavities'.
        '''

        try:
            if atten_v:
                assert isinstance(atten_v, list) or isinstance(atten_v, \
                                                               np.ndarray)
                assert len(cavities) == len(atten_v)
            if is_on:
                assert isinstance(is_on, list) or isinstance(is_on, \
                                                             np.ndarray)
                assert len(cavities) == len(atten_v)

            attenv = None
            ison = None
    
            for i in range(len(cavities)):
                cav = cavities[i]
                if atten_v:
                    attenv = eval(atten_v[i])
                if is_on:
                    ison = is_on[i]
                if isinstance(cav, str):
                    if cav in self.quench_info.index:
                        if self.quench_info['Is Open'].ix[cav] == True:
                            print('Quench cavity ' + cav + ' already open.')
                        else:
                            self.open_quench(cav, atten_v = attenv, is_on = ison)
                    else:
                        print('Invalid cavity: ' + cav)
                        print(self.quench_info.index)
                else:
                    print('The cavity name must be a string.')
        except Exception as e:
            sys.stderr.write(tb.format_exc())

    def get_statuses(self, cavities):
        ''' Obtain status of multiple cavities. The variable cavities should be
        a list of cavity names. Returns a dictionary with keys equal to the
        cavities list, and values are the returned status lists.
        '''

        s = {}

        for cav in cavities:
            cav_status = self.get_usb_status(cav)
            s[cav] = cav_status

        return s

    def print_statuses(self, cavities):
        ''' Print the status of multiple usb cavities at once.'''

        for cav in cavities:
            self.print_usb_status(cav)

    def get_usb_ids(self, cavities):
        ''' Obtain ID of multiple cavities. The variable cavities should be
        a list of cavity names. Returns a dictionary with keys equal to the
        cavities list, and values are the returned ids.
        '''

        s = {}

        for cav in cavities:
            cav_id = self.get_usb_id(cav)
            s[cav] = cav_id

        return s

    def get_dac_voltages(self, cavities):
        ''' Obtain DAC voltage of multiple cavities. The variable cavities
        should be a list of cavity names. Returns a dictionary with keys equal
        to the cavities list, and values are the returned dac_voltages.
        '''

        s = {}

        for cav in cavities:
            cav_dac = self.get_dac_voltage(cav)
            s[cav] = cav_dac

        return s

    def get_cavity_powers(self, cavities):
        ''' Obtain power detector readings of multiple cavities. The variable
        cavities should be a list of cavity names. Returns a dictionary with
        keys equal to the cavities list, and values are the returned
        dac_voltages.
        '''

        s = {}

        for cav in cavities:
            cav_p = self.get_cavity_power(cav)
            s[cav] = cav_p

        return s

    def get_power_detector_dc_in(self):
        ''' Obtains the DC input voltage from the power detector supply. '''

        return self.quench_u6.getAIN(8)

    def cavities_on(self, cavities):
        ''' Turn on multiple cavities at once.'''

        for cav in cavities:
            self.cavity_on(cav)
            print(cav + " on.")

    def cavities_off(self, cavities):
        ''' Turn off multiple cavities at once. This does not close cavities.'''

        for cav in cavities:
            self.cavity_off(cav)

    def close_quenches(self, cavities):
        ''' Close multiple (but not all) SynthUSBs.'''

        for cav in cavities:
            if cav in self.quench_info.index:
                if self.quench_info['Is Open'].ix[cav] == True:
                    self.close_quench(cav)
                    self.quench_info['Is Open'].ix[cav] = False
                else:
                    print(cav + " not open.")
            else:
                print('Invalid cavity: ' + cav)
                print(self.quench_info.index)

    def close(self):
        ''' Close connections to all cavities as well as connections to the
        LabJacks. This does not turn off any of the cavities.
        '''

        # Close all quenches.
        try:
            self.close_quenches(self.quench_info.index)
        except:
            sys.stderr.write(tb.format_exc())

        # Close both LabJacks
        try:
            self.quench_u3.close()
            print("U3 closed.")
        except:
            sys.stderr.write(tb.format_exc())

        try:
            self.quench_u6.close()
            print("U6 closed.")
        except:
            sys.stderr.write(tb.format_exc())

        # Free LabJacks from this kernel/thread
        try:
            LabJackPython.Close()
            print("All LabJacks freed for use in other threads.")
        except:
            sys.stderr.write(tb.format_exc())

    def off_and_close(self):
        ''' Turn off all SynthUSBs, change all DAC voltages to 0, and close all
        connections to everything.
        '''

        # Turn off all power in all quenches.
        self.cavities_off(self.quench_info.index)

        # Close all quenches.
        self.close_quenches(self.quench_info.index)

        # Close both LabJacks.
        self.quench_u3.close()
        print("U3 closed.")

        self.quench_u6.close()
        print("U6 closed.")

        # Free LabJacks from this kernel/thread.
        LabJackPython.Close()
        print("All LabJacks freed for use in other threads.")
