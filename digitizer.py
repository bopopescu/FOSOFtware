# Talk to Keysight/Agilent L4532A
# version 1
# 2014-08-07

# Update: 2017-09-26
# Note on the save format: in this version of the digitizer code, we have
# adopted the .npy file format, as outlined here:
# https://docs.scipy.org/doc/numpy/neps/npy-format.html
# Just in case this site goes down, I've saved the webpage in the instrument
# control folder as npyformat.html.

from __future__ import division
import sys
import os
import visa
import pyvisa
import pandas as pd
import numpy as np
import pylab as plt
import time
import binary as b

_DEFAULT_FILE_LOCATION_ = "C:/DEVICEDATA/"
info_file = pd.read_csv(_DEFAULT_FILE_LOCATION_ + 'digitizer.csv')
addr_A = info_file['Address A'].ix[0]
addr_B = info_file['Address B'].ix[0]
ch_range = int(info_file['Channel Range'].ix[0])
s_rate = int(info_file['Sampling Rate'].ix[0])
n_samps = int(info_file['Number of Samples'].ix[0])
trig_ch = int(info_file['Trigger Channel'].ix[0])
t_out = int(info_file['Timeout'].ix[0])

# The following methods make sure there are no errors in the given digitizer
# settings
def is_digirange(rng):
    ''' Checks to see if the given digitizer range is a float or int that can
    be used by the digitizer. See the manual for details.
    '''

    if isinstance(rng, int) or isinstance(rng, float):
        if rng in [0.25,0.5,1,2,4,8,16,32,64,128,256]:
            return True

    return False

def is_samplingrate(srate):
    ''' Checks to see if the given sampling rate is an int that can
    be used by the digitizer. See the manual for details.
    '''

    if isinstance(srate, int):
        if srate in [1e3, 2e3, 5e3, 1e4, 2e4, 5e4, 1e5, 2e5, 5e5, 1e6, 2e6, \
                     5e6, 1e7, 2e7]:
            return True

    return False

def is_numsamples(nsamp):
    ''' Checks to see if the given number of samples is an int that can
    be used by the digitizer. See the manual for details.
    '''

    # Max number of samples per channel is 32MSa. We do not have the "deep
    # memory" upgrade.
    if isinstance(nsamp, int):
        if nsamp % 4 == 0 and nsamp <= 32e6:
            return True

    return False

def is_trigch(trigch):
    ''' Check if the given trigger channel is valid. Select 1 or 2 for CH1 or
    CH2, respectively. The user can also select 0 to trigger from the computer.
    '''

    if isinstance(trigch, int):
        if 0 <= trigch <= 2:
            return True

    return False

class Travisty(Exception):
    def __init__(self, msg):
        self.message = msg

class Digitizer:
    ''' A class created to control the Keysight/Agilent Digitzers used in the
    hydrogen experiment. This code was revised to follow PEP-8 and some
    functionality was patched & added. The default settings are now stored
    in a file with this code. This way, we usually don't have to specify any
    settings for the digitizer. We should, however, refrain from changing the
    defaults instead of modifying our code when necessary. That defeats the
    purpose of having default settings stored somewhere.
    '''

    def __init__(self, address, timeOut = t_out, ch1_range = ch_range, \
                 ch2_range = ch_range, sampling_rate = s_rate, \
                 num_samples = n_samps, trigger_channel = trig_ch,
                 clocked = True):
        ''' Error check provided values and initialize a Digitizer object.'''

        # Must use pyVISA because of the driver for the digitizer. It does not
        # create a virtual COM port.
        rm = visa.ResourceManager()

        # Select the proper address
        if address == 'A':
            self.device = rm.open_resource(addr_A, timeout = timeOut)
        elif address == 'B':
            self.device = rm.open_resource(addr_B, timeout = timeOut)
        else:
            raise Travisty("Incorrect channel specified. Must be A or B.")

        # Query the digitizer for an ID and clear the buffer.
        self.name = self.device.query("*idn?")
        self.device.write("*CLS")

        # Check and set the sampling rate
        if not is_samplingrate(sampling_rate):
            raise Travisty("Oops! Incompatible sampling rate. Check docs " + \
                           "for allowed values.")

        self._sampling_rate = sampling_rate
        self.device.write("CONFigure:ACQuisition:SRATe " + \
                          `self._sampling_rate`)

        # Make sure there is only one record per acquisition. Consecutive
        # records must be triggered one after another.
        self.device.write("CONF:ACQ:RECords 1")

        # Check and set number of samples
        if is_numsamples(num_samples) == False:
            raise Travisty("Oops! Incompatible number of samples")

        self._num_samples = num_samples
        self.device.write("CONF:ACQ:SCO " + `self._num_samples`)

        # Check and set digitizer ranges
        if not is_digirange(ch1_range):
            raise Travisty("Oops! Incompatible digitizer range for CH1.")
        if not is_digirange(ch2_range):
            raise Travisty("Oops! Incompatible digitizer range for CH2.")

        self._ch1_range = ch1_range
        self._ch2_range = ch2_range
        self.device.write("CONF:CHANnel:RANGe (@1), " + `self._ch1_range`)
        self.device.write("CONF:CHANnel:RANGe (@2), " + `self._ch2_range`)

        self.device.write("CONF:CHANnel:COUPling (@1,2), DC") # DC coupling

        # Check and set trigger channel
        if not is_trigch(trigger_channel):
            raise Travisty("Invalid trigger channel selected. Must be 0, 1 " + \
                           "or 2.")

        if trigger_channel > 0:
            self.device.write("CONFigure:TRIGger:SOURce CHANnel")
            self.device.write("CONFigure:TRIGger:SOURce:CHANnel:EDGE (@" + \
                              `self._trigger_channel` + "),0,POS")
        else:
            self.device.write("CONFigure:TRIGger:SOURce IMMediate")

        # Format the output of the data
        self.device.write("FORMat:DATA:REAL REAL,64") # Default is 32 bit
        self.device.write("FORMat:DATA:INTeger INTeger") # Default is 16 bit

        # Little-endian processor
        if sys.byteorder=="little":
            self.device.write("FORM:BORD SWAP")

        if clocked:
            self.device.write("CONFigure:CHANnel:FILTer (@1,2), LP_200_KHZ")
        
            # Set the digitizer to external reference oscillator
            self.device.write("CONF:ROSC EXT")
            time.sleep(1)
            self.device.write("CONF:ROSC?")
            digi_clock = self.device.read()
            print("Digitizer " + address + " locked to clock:"+str(digi_clock))
        
            # Set the digitizer in the continuous time stamping mode.
            self.device.write("CONF:TRIG:TIM CONT")

    def sync(self, type):
        ''' Sync the digitizer to begin acquisition when a signal is received on
        the external trigger. If the type is 'master', emit the signal when the
        'INITIALIZE' command is received. If the type is 'slave', wait for the
        trigger signal to begin an acquisition.
        '''

        # Set the digitizer to trigger to positive edge of the external trigger
        # signal.
        self.device.write("CONF:EXT:INP POS")

        # Set the digitizers to have their external triggers to drive a 50Ohm
        # load.
        self.device.write("CONF:EXT:TRIG:OUTP NONE, POS_50")

        if type == 'slave':
            # Set the slave digitizer to wait for external trigger pulses to
            # which it can synchronize
            self.device.write("SYST:SYNC:EXT PEND")
            time.sleep(0.5)
            digi_synchronize_Q = self.device.ask("SYST:SYNC:EXT?")
            print("Slave digitizer synchronization status: " + \
                  str(digi_synchronize_Q))

            # Configure the trigger options for the slave digitizer. It is set
            # to accept a positive trigger pulse and trigger to that pulse.
            self.device.write("CONF:ARM:SOUR IMM")
            self.device.write("CONF:TRIG:SOUR EXT")
            self.device.write("CONF:EXT:INP POS")
        elif type == 'master':
            # Set the master digitizer to output synchronizing trigger pulses to
            # itself and other devices connected to its trigger port.
            self.device.write("SYST:SYNC:EXT SYNC")
            time.sleep(0.5)

            # Check if the digitizers are properly synchronized
            digi_synchronize_Q = self.device.ask("SYST:SYNC:EXT?")
            print("Master digitizer synchronization status: " + \
                  str(digi_synchronize_Q))

            # Configure the trigger options for the master digitizer. It is set
            # to output a positive trigger pulse for a 50Ohm load
            self.device.write("CONF:ARM:SOUR IMM")
            self.device.write("CONF:TRIG:SOUR IMM")

            self.device.write("CONF:EXT:TRIG:OUTP TRIG, POS_50")

    def initialize(self):
        ''' Initialize the beginning of an acquisition on the digitizer.'''

        self.device.write("INITIATE")

    def read(self, channel = None, read_type = 'INT', ret_bin = True):
        ''' Reads the waveform voltage from the digitizer. These will be
        returned as numpy arrays of 64-bit floats or 16-bit integers, or binary
        numbers (depending on the return_bin and read_type params). Note that
        the method read_raw collects the data as binary values. This is
        necessary to avoid errors from the digitizer when the channel range is
        not high enough for the FLOAT type.

        This function error checks the data and throws away any trailing bits
        that are not enough to make a 64-bit number. This may result in some
        lost data. As a result, an error code is also returned. If 0, no bits
        were lost. Otherwise, will return 1.

        Tested the timing. It takes 0.180 s to read two channels of data that
        have 1e5 samples.
        '''

        err = 0 # Error flag

        if read_type == 'INT':
            dt = 'i2'
            cmd = 'ADC'
            n = 2
        elif read_type == 'FLOAT':
            dt = 'float64'
            cmd = 'VOLTage'
            n = 8
        else:
            raise Travisty('Invalid read type. Must be INT or FLOAT.')

        # Return data from both channels
        if channel == None:
            # Read the digitizer traces together in raw format:
            # Characters 0 to 10: header containing number of samples to expect
            # Characters 11 through N+11: Data (alternating channels)
            # Character N+12: newline character
            t_s = time.time()
            self.device.write("FETCH:WAVeform:" + cmd + "? (@1, 2)")
            data = self.device.read_raw(size = n*2*self._num_samples + 100)
            print(time.time()-t_s)

            header = data[:11]

            # Error check
            t_s = time.time()
            if len(data[11:-1]) % n == 0:
                V = data[11:-1]
            else:
                err = 1
                extra = len(data[11:-1]) % n
                V = data[11:-(extra+1)]
            print(time.time()-t_s)

            t_s = time.time()
            # Separate channel data
            #V1 = np.array([V[n*2*i:n*(2*i+1)] for i in range(int(len(V)/(2*n)))])
            #V2 = np.array([V[n*(2*i+1):n*(2*i+2)] for i in range(int(len(V)/(2*n)))])
            V = np.array(list(V)).reshape((self._num_samples,n*2))
            V1 = V[:,:n].flatten()
            V2 = V[:,n:2*n].flatten()
            print("To split")
            print(time.time()-t_s)

            # Convert to non-binary
            if not ret_bin:
                V1 = np.frombuffer(V1, dtype = np.dtype(dt))
                V2 = np.frombuffer(V2, dtype = np.dtype(dt))

            return V1, V2, err

        elif channel == 1:
            self.device.write("FETCH:WAVeform:" + cmd + "? (@1)")
            data = self.device.read_raw(size = n*self._num_samples + 100)

            header = data[:11]

            if len(data[11:-1]) % n == 0:
                V = data[11:-1]
            else:
                err = 1
                extra = len(data[11:-1]) % n
                V = data[11:-(extra+1)]

            if not ret_bin:
                V = np.frombuffer(V, dtype = np.dtype(dt))

            return V, err

        elif channel == 2:
            self.device.write("FETCH:WAVeform:" + cmd + "? (@2)")
            data = self.device.read_raw(size = n*self._num_samples + 100)

            header = data[:11]

            if len(data[11:-1]) % n == 0:
                V = data[11:-1]
            else:
                err = 1
                extra = len(data[11:-1]) % n
                V = data[11:-(extra+1)]

            if not ret_bin:
                V = np.frombuffer(V, dtype = np.dtype(dt))

            return V, err
        else:
            raise Travisty("Oops! Invalid channel selected. Must be 1 or 2.")

    def read_save(self, f_names, channel = None, read_type = 'INT',
                  ret = False, ret_bin = False):
        ''' Reads the data from the digitizer and saves the binary conversion to
        a file specified in f_names. INT will convert to 16-bit binary integer,
        while FLOAT will convert to 64-bit binary floating point value. If ret
        is True, will return the data in a readable format. If ret_bin is True,
        will return the data as binary. If both are True, data is returned as
        binary to save time.

        Tested the timing. It takes 0.184 s to read and save two channels of
        data that have 1e5 samples.

        2017-09-27. Comment (Nikita). Possible reason for the read operation to
        take so long is because read_raw() function reads data in chunks. The
        chunk size can be accessed by looking at device.chunk_size attribute.
        Also read_raw() = read_raw(size = NONE). So we can set it to read data
        in exactly one go by making size or chunk_size = expected number of
        bytes from the digitizer.
        '''

        # Return data from both channels
        if channel == None:
            V1, V2, err = self.read(channel = channel, read_type = read_type,
                                    ret_bin = True)

            # Save to files
            np.save(f_names[0], np.frombuffer(V1, dtype = np.dtype(dt)))
            np.save(f_names[1], np.frombuffer(V2, dtype = np.dtype(dt)))

            if ret and not ret_bin:
                # Separate channel data and return
                V1 = np.frombuffer(V1[:len(V1)-len(V1) % n],
                                   dtype = np.dtype(dt))
                V2 = np.frombuffer(V2[:len(V2)-len(V2) % n],
                                   dtype = np.dtype(dt))
            elif ret_bin: pass
            else: return err

            return V1, V2, err

        elif channel == 1 or channel == 2:

            V, err = self.read(channel = channel, read_type = read_type,
                               ret_bin = True)

            # Save to files
            np.save(f_names[0], np.frombuffer(V, dtype = np.dtype(dt)))

            if ret and not ret_bin:
                # Convert to float or int
                V = np.frombuffer(V, dtype = np.dtype(dt))
            elif ret_bin: pass
            else: return err

            return V, err
        else:
            raise Travisty("Oops! Invalid channel selected. Must be 1 or 2.")

    def ini_read(self, channel = None, read_type = 'INT', ret_bin = True):
        ''' Initializes, waits and returns digitizer data.'''

        self.initialize()
        time.sleep(self._num_samples/self._sampling_rate + 0.100)
        return self.read(channel = channel,
                         read_type = read_type,
                         ret_bin = ret_bin)

    def ini_read_save(self, f_names, channel = None, read_type = 'INT', \
                      ret = False, ret_bin = False):
        ''' Initializes, waits, saves and possibly returns data.'''

        self.initialize()
        time.sleep(self._num_samples/self._sampling_rate + 0.100)
        return self.read_save(f_names,
                              channel = channel,
                              read_type = read_type,
                              ret = ret,
                              ret_bin = ret_bin)

    def get_chrange(self, chnum):
        ''' Returns the range of the digitizer channel specified.'''
        if chnum == 1:
            return self.__ch1_range
        elif chnum == 2:
            return self.__ch2_range
        else:
            raise Travisty("Oops! Can't find range for specified channel.")

    def get_samplingrate(self):
        ''' Returns the sampling rate of the digitizer.'''
        return self._sampling_rate

    def get_numsamples(self):
        ''' Returns the number of samples per acquisition for the digitizer.'''
        return self._num_samples

    def set_chrange(self, chnum, rng):
        ''' Sets the voltage range of the specified channel to rng, if it is
        an appropriate value.
        '''

        if not is_digirange(rng):
            raise Travisty("Oops! Incompatible digitizer range.")

        if chnum == 1:
            self._ch1_range = rng
            self.device.write("CONF:CHANnel:RANGe (@1), " + str(self._ch1_range))
        elif chnum == 2:
            self._ch2_range = rng
            self.device.write("CONF:CHANnel:RANGe (@2), " + str(self._ch2_range))
        else:
            raise Travisty("Oops! Incorrect channel specified.")

        time.sleep(0.25)
        return True

    # Setters
    def set_samplingrate(self, srt):
        ''' Sets the sampling rate of the digitizer if appropriate.'''

        if not is_samplingrate(srt):
            raise Travis("Oops! Incompatible sampling rate.")

        self._sampling_rate = srt
        self.device.write("CONFigure:ACQuisition:SRATe " + str(int(self._sampling_rate)))

        time.sleep(0.25)
        return True

    def set_numsamples(self, nsamp):
        ''' Sets the number of samples per acquisition for the digitizer if
        appropriate.
        '''

        if not is_numsamples(nsamp):
            raise Travisty("Oops! Incompatible number of samples.")

        self._num_samples = nsamp
        self.device.write("CONF:ACQ:SCO " + str(int(self._num_samples)))

        time.sleep(0.25)
        return True

    def set_ch_filter(self, chnum, filt_type='20 MHz'):
        ''' Sets a two-pole Bessel filter for a given channel

            :chnum: channel number. 1 or 2.
            :filt_type: Low pass filter cut-off frequency. Possible values:
                        '20 MHz'
                        '2 MHz'
                        '200 kHz'
        '''
        filter_type_dict = {'20 MHz':'LP_20_MHZ','2 MHz':'LP_2_MHZ','200 kHz':'LP_200_KHZ'}
        if filt_type in filter_type_dict.keys():
            self.write('CONFigure:CHANnel:FILTer (@' + str(chnum) + '),'+filter_type_dict[filt_type])
        else:
            raise Travisty("Oops! This filter setting does not exist.")
        self.device.write()



    def close(self):

        # Desynchronize the digitizer
        self.device.write("SYST:SYNC:EXT NONE")

        # Set the trigger of the digitizer to immediate
        self.device.write("CONF:TRIG:SOUR IMM")

        # Set the digitizer to output no external trigger pulse
        self.device.write("CONF:EXT:TRIG:OUTP NONE, OFF")

        # Set the digitizer to internal reference oscillator
        self.device.write("CONF:ROSC INT")

        # Set the digitizer to non-continuous time stamping mode
        self.device.write("CONF:TRIG:TIM INIT")

        # Disable the low pass filter
        self.device.write("CONFigure:CHANnel:FILTer (@1,2), LP_20_MHZ")

        self.device.write("*RST")
        self.device.close()
        self.device = None
        print("Digitizer closed")

    def is_open(self):
        return isinstance(self.device, pyvisa.resources.usb.USBInstrument)

def test(address):
    os.chdir("c:/Google Drive/logs")

    digi = Digitizer(address,num_samples=10000)
    print digi.id
    print "Number of samples = ",digi.device.ask("CONF:ACQ:SCO?")

    digi.device.write("CONFigure:TRIGger:SOURce IMMediate")     # software trigger
    digi.device.write("CONF:CHANnel:RANGe (@1), 5")
    digi.device.write("CONF:CHANnel:RANGe (@2), 5")

    V1,V2 = digi.read()
    digi.close()
    t = np.linspace(1/digi.__sampling_rate,digi.__num_samples/digi.__sampling_rate, num=len(V1))

    plt.figure()
    plt.plot(t,V1,color='red',alpha=0.7,lw=2)
    plt.plot(t,V2,color='blue',alpha=0.7,lw=2)
    plt.show()
    plt.close()