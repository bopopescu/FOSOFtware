import pandas as pd
import numpy as np
import fosof_qol as qol
import generator
import time
import digitizer
import quench
import generator
from datetime import datetime as dt
from acquisition import Acquisition
import traceback as tb
import faradaycupclass
import visa
import B_field_control as bfc
import sys

# Run Dictionary Keys
# Experiment Name = string
# Experiment Name Addon = string
# Number of Repeats = int > 0
# Number of Averages = int > 0
# Number of Traces Between Switching Configurations = int, divisor of Number of Averages
# Waveguide Electric Field [V/cm] = int 30 > x > 0 (depends on calibration)
# Offset Frequency [Hz] = int <= 1000, separate multiple values with commas
# Frequency Scan Range = small, medium, large, extralarge
# Number of Frequency Steps = int > 0 (41 is a full scan)
# B_x Min [Gauss] = float
# B_x Max [Gauss] = float
# Number of B_x Steps = int
# B_y Min [Gauss] = float
# B_y Max [Gauss] = float
# Number of B_y Steps = int
# Pre-Quench 910 On/Off = bool
# Pre-Quench 910 On Number of Digitizer Samples = int (see Digitizer Manual)
# Digitizer Address for Detector = A or B
# Digitizer Channel for Detector = 1 or 2
# Digitizer Channel Range [V] = int (see Digitizer Manual)
# Digitizer Sampling Rate [S/s] = int (see Digitizer Manual)
# Number of Digitizer Samples = int (see Digitizer Manual)
# Power Combiner on Detector Digitizer = R or I
# Quenches = filename
# Binary Traces = bool

independent_rd_location = qol.path_file['Run Queue'] + \
                          'waveguide_calibration_DEFAULT.rd'

class FOSOFAcquisition(Acquisition):

    # This init header should not be changed. The function should always take
    # self and three queues.
    def __init__(self, queue_in, queue_out, queue_err):
        super(FOSOFAcquisition, self).__init__(queue_in, queue_out, \
                                               queue_err)

    # Define required functions

    def initialize_acquisition(self):
        # Initialize all global variables here, including the 'progress'
        # variable.

        self.progress = 'Printing data.txt comment header'

        self.comments = qol.make_comment_string(self.run_dictionary, \
                                                self.run_dictionary['Order'] \
                                                    .values)

        data_file = open(self.folder + 'data.txt', 'w')
        data_file.write(self.comments)
        data_file.close()

        self.progress = 'Reading quench parameters'

        self.quench_file = pd.read_csv(self.run_dictionary.ix['Quenches'].Value)
        self.quench_file = self.quench_file.set_index('Quench Name')

        self.progress = 'Setting up quenches'

        # Open the quench manager (u3, u6, usb synthesizers)
        self.qm = quench.QuenchManager()

        # Determine which quenches to turn on, off, etc.
        quench_arrays = qol.quench_arrays(self.quench_file)

        self.open_quenches = quench_arrays[0]
        self.quench_is_on = quench_arrays[1]
        self.off_quenches = quench_arrays[2]
        self.initial_atten_vs = quench_arrays[3]

        self.progress = 'Opening quenches'

        # Open the USB synthesizers and ensure quenches are set as requested
        self.qm.open_quenches(self.open_quenches, \
                              atten_v = self.initial_atten_vs, \
                              is_on = self.quench_is_on)
        self.qm.cavities_off(self.off_quenches)

        # Make sure 910s are off to start
        self.qm.cavities_off(['pre-quench_910','post-quench_910'])

        self.progress = 'Opening digitizer'

        self.num_samples = int(self.run_dictionary \
                                   .ix['Number of Digitizer Samples'].Value)
        self.sampling_rate = int(self.run_dictionary \
                                     .ix['Digitizer Sampling Rate [S/s]'].Value)
        self.trace_length_s = float(self.num_samples) / \
                              float(self.sampling_rate)
        self.ch_range = int(self.run_dictionary \
                                .ix['Digitizer Channel Range [V]'].Value)
        self.digi_addr = self.run_dictionary \
                             .ix['Digitizer Address for Detector'] \
                             .Value
        self.other_addr = ['A','B']
        self.other_addr.remove(self.digi_addr)
        self.other_addr = self.other_addr[0]

        self.digi1 = digitizer.Digitizer(self.digi_addr, \
                                         ch1_range = self.ch_range, \
                                         ch2_range = self.ch_range, \
                                         sampling_rate = self.sampling_rate, \
                                         num_samples = self.num_samples,
                                         timeOut = 30)
        self.digi2 = digitizer.Digitizer(self.other_addr, \
                                         ch1_range = self.ch_range, \
                                         ch2_range = self.ch_range, \
                                         sampling_rate = self.sampling_rate, \
                                         num_samples = self.num_samples,
                                         timeOut = 30)
        self.digi_det = int(self.run_dictionary.ix['Digitizer Channel ' + \
                                                   'for Detector'].Value) - 1
        self.digi_c1 = 1 - self.digi_det # Combiner channels
        self.digi_c2 = self.digi_det

        # Sync the digitizers (to a signal from digi1 when digi1 is initialized)
        self.digi1.sync('master')
        self.digi2.sync('slave')

        self.progress = 'Opening generator'

        self.wg_efield = int(self.run_dictionary \
                                 .ix['Waveguide Electric Field [V/cm]'].Value)

        # Preparing multiple offset frequencies
        self.offset_frequencies = self.run_dictionary \
                                      .ix['Offset Frequency [Hz]'].Value
        self.offset_frequencies = self.offset_frequencies.split(',')
        self.offset_frequencies = [int(of) for of in self.offset_frequencies]
        self.num_offset_frequencies = len(self.offset_frequencies)
        self.offset_frequencies_randomized = \
            np.random.permutation(self.offset_frequencies)

        # Preparing list of indices for scanning the carrier frequency
        self.scan_range = self.run_dictionary \
                              .ix['Frequency Scan Range'].Value
        self.n_freqs = int(self.run_dictionary \
                               .ix['Number of Frequency Steps'].Value)

        if 41 >= self.n_freqs > 1:
            if 40 % (self.n_freqs - 1) == 0:
                self.factor = 40/(self.n_freqs - 1)
            else:
                raise qol.Travisty("Number of frequency steps cannot be" + \
                                   " matched up to  waveguide power" + \
                                   " calibration file.")

            self.freq_ind = np.arange(0,41,self.factor)
            print(self.freq_ind)
            self.freq_ind_randomized = np.random.permutation(self.freq_ind)

        elif self.n_freqs == 1: # Not sure why we'd want to do this
            self.freq_ind = np.array([0])
            self.freq_ind_randomized = self.freq_ind
        else:
            raise qol.Travisty("Number of frequency steps cannot be matched" + \
                               " up to  waveguide power calibration file.")

        # Setting up the generator (use first offset_frequency as default start)
        self.gen = generator.Generator(calib = False,
                                       offset_freq = self.offset_frequencies[0],
                                       scan_range = self.scan_range,
                                       e_field = self.wg_efield)

        # Initializing Faraday cup labjack
        self.progress = 'Setting up Faraday cup(s)'
        self.fcup = faradaycupclass.FaradayCup()

        # Setting up magnetic field control
        self.progress = 'Initializing magnetic field parameters.'

        self.num_b_x = int(self.run_dictionary.ix['Number of B_x Steps'].Value)
        self.min_b_x = float(self.run_dictionary.ix['B_x Min [Gauss]'].Value)
        self.max_b_x = float(self.run_dictionary.ix['B_x Max [Gauss]'].Value)

        self.num_b_y = int(self.run_dictionary.ix['Number of B_y Steps'].Value)
        self.min_b_y = float(self.run_dictionary.ix['B_y Min [Gauss]'].Value)
        self.max_b_y = float(self.run_dictionary.ix['B_y Max [Gauss]'].Value)

        if self.num_b_x <= 1 or self.min_b_x == self.max_b_x:
            self.b_x_list = np.array([self.min_b_x])
        else:
            self.b_x_list = np.linspace(self.min_b_x,
                                        self.max_b_x,
                                        self.num_b_x)

        if self.num_b_y <= 1 or self.min_b_y == self.max_b_y:
            self.b_y_list = np.array([self.min_b_y])
        else:
            self.b_y_list = np.linspace(self.min_b_y,
                                        self.max_b_y,
                                        self.num_b_y)

        self.b_x_list = np.array([('x',b,'y',0.0,'x') for b in self.b_x_list])
        self.b_y_list = np.array([('x',0.0,'y',b,'y') for b in self.b_y_list])

        # Check to see if both lists are the same. This occurs only when neither
        # x nor y fields are to be scanned.
        check_same = True
        arr = (self.b_x_list == self.b_y_list)
        for element in arr[0,:4]:
            check_same = check_same and element
        if check_same:
            self.b_list = np.array([('x',b,'y',0.0,'')])
        elif self.num_b_x == 1:
            self.b_list = self.b_y_list
        elif self.num_b_y == 1:
            self.b_list = self.b_x_list
        else:
            self.b_list = np.concatenate((self.b_x_list, self.b_y_list),
                                         axis=0)

        self.b_list_randomized = np.random.permutation(self.b_list)
        self.num_b = len(self.b_list)

        self.progress = 'Initializing magnetic field control.'
        self.rm = visa.ResourceManager()
        self.bfield_control = bfc.BFieldControl(self.rm)
        self.bfield_control.set_B_field(0.0, "x")
        self.bfield_control.set_B_field(0.0, "y")

        # Setting up pre-quench 910 on/off states
        self.progress = 'Initializing 910 switching parameters.'

        self.pre910_on_off = eval(self.run_dictionary \
                                      .ix['Pre-Quench 910 On/Off'].Value)
        if self.pre910_on_off == True:
            self.pre910_states = ['on', 'off']
            self.pre910_num_samples = int(self.run_dictionary.ix['Pre' + \
                                                                 '-Quench' + \
                                                                 ' 910 On ' + \
                                                                 'Number ' + \
                                                                 'of ' + \
                                                                 'Digitizer' + \
                                                                 ' Samples'] \
                                              .Value)
        else:
            self.pre910_states = ['off']

        self.pre910_states_randomized = np.random \
                                          .permutation(self.pre910_states)
        self.num_910_states = len(self.pre910_states)

        self.progress = 'Setting up data table'

        self.max_rep = int(self.run_dictionary.ix['Number of Repeats'].Value)
        self.max_avg = int(self.run_dictionary.ix['Number of Averages'].Value)
        self.traces_btwn_switch = int(self.run_dictionary \
                                          .ix['Number of Traces Between ' + \
                                              'Switching Configurations'].Value)

        p_comb = self.run_dictionary \
                     .ix['Power Combiner on Detector Digitizer'].Value
        p_comb_2 = ['R','I']
        p_comb_2.remove(p_comb)
        p_comb_2 = p_comb_2[0]

        cols = ['Repeat',
                'Average',
                'Configuration',
                'Waveguide Carrier Frequency [MHz]',
                "B_x [Gauss]",
                "B_y [Gauss]",
                "Offset Frequency [Hz]",
                "Pre-Quench 910 State",
                "Waveguide A Power Reading  [V]",
                "Waveguide B Power Reading [V]",
                "Time",
                "Detector Trace Filename",
                "RF Power Combiner " + p_comb + " Digi 1 Trace Filename",
                "RF Power Combiner " + p_comb_2 + " Trace Filename",
                "RF Power Combiner " + p_comb + " Digi 2 Trace Filename",
                "fc1a [uA]",
                "fc1b [uA]",
                "fc1c [uA]",
                "fc1d [uA]",
                "fc2i [uA]",
                "fc2ii [uA]",
                "fc2iii [uA]",
                "fc2iv [uA]",
                "fc3 [uA]",
                "fccentre [uA]"]

        for q in self.open_quenches:
            cols.append(qol.formatted_quench_name(q) + \
                        ' Power Detector Reading [V]')
            cols.append(qol.formatted_quench_name(q) + \
                        ' Attenuator Voltage Reading [V]')

        # Write column headers
        self.data = pd.DataFrame(columns = cols)
        data_file = open(self.folder + 'data.txt', 'a')
        self.data.to_csv(data_file, index = False)
        data_file.close()
        print('\t'.join(self.data.columns))

        self.rep = 0
        self.avg = 0
        self.switch_iterator = 0
        self.gen_f_iterator = 0
        self.ab_iterator = 0
        self.b_iterator = 0
        self.offset_frequency_iterator = 0
        self.pre910_state_iterator = 0

        self.pre910_state = None
        self.b_field = np.array([None, None, None, None, None])
        self.offset_frequency = None
        self.ab = 'N'
        self.gen_frequency = self.gen.get_rf_generator_frequency("A")
        self.gen_f_ind = None

        self.ab_list = ['A', 'B']
        self.ab_list_randomized = np.random.permutation(self.ab_list)

        self.total_traces = self.max_rep * self.max_avg * self.n_freqs * \
                            self.num_offset_frequencies * 2 * self.num_b * \
                            self.num_910_states
        self.num_complete = 0

        self.progress = 'Initialization complete'
        self.start_time = time.time()
        print('Beginning acquisition...')

        return

    def acquire(self):

        gen_f_ind = self.freq_ind_randomized[self.gen_f_iterator]
        pre910_state = self.pre910_states_randomized[self.pre910_state_iterator]
        b_field = self.b_list_randomized[self.b_iterator]
        offset_frequency = \
            self.offset_frequencies_randomized[self.offset_frequency_iterator]

        print("Entering loop")

        t_s = time.time()
        # Change the RF frequency if needed
        if self.gen_f_ind != gen_f_ind:
            self.gen_f_ind = gen_f_ind
            self.gen.set_rf_frequency(gen_f_ind, self.ab)
            self.gen_frequency = self.gen.get_rf_generator_frequency("A")
            print("Gen frequency changed")

        # Change the magnetic field coil current if needed
        if (self.b_field != b_field).any():
            self.b_field = b_field

            # The type of all elements in a numpy array must be the same. Since
            # the b_field values are in an array with strings, they are also
            # strings
            print(self.b_field)
            self.bfield_control.set_B_field(float(b_field[1]), "x")
            self.bfield_control.set_B_field(float(b_field[3]), "y")
            print("B field changed.")

        # Change the offset frequency if needed
        if self.offset_frequency != offset_frequency:
            self.offset_frequency = offset_frequency
            self.gen.set_offset_frequency(self.offset_frequency)
            print("Offset frequency changed.")

        # Change the state of the 910 cavity if needed
        if self.pre910_state != pre910_state:
            self.pre910_state = pre910_state

            if pre910_state == 'on':
                self.qm.cavity_on('pre-quench_910')
                self.digi1.set_numsamples(self.pre910_num_samples)
                self.digi2.set_numsamples(self.pre910_num_samples)
                self.trace_length_s = float(self.pre910_num_samples) / \
                                      float(self.sampling_rate)
            else:
                self.qm.cavity_off('pre-quench_910')
                self.digi1.set_numsamples(self.num_samples)
                self.digi2.set_numsamples(self.num_samples)
                self.trace_length_s = float(self.num_samples) / \
                                      float(self.sampling_rate)
            print("910 state switched.")
        t_f = time.time()
        print("Time to enter loop: " + str(t_f - t_s))

        while self.avg < self.max_avg:

            self.ab_iterator = 0
            self.ab_list_randomized = np.random.permutation(self.ab_list)

            while self.ab_iterator < 2:
                self.switch_iterator = 0
                ab = self.ab_list_randomized[self.ab_iterator]

                # Switch offset channel if necessary
                if self.ab != ab:
                    self.ab = ab
                    self.gen.set_rf_frequency(gen_f_ind, self.ab)
    
                while self.switch_iterator < self.traces_btwn_switch:

                    self.progress = 'Repeat ' + str(self.rep + 1) + '\n' + \
                                    'Generator Frequency: ' + \
                                    str(round(self.gen_frequency,2)) + \
                                    ' MHz\n' + \
                                    'Configuration ' + self.ab + '\n' + \
                                    'Average ' + str(self.avg + \
                                                     self.switch_iterator + \
                                                     1) + '\n' + \
                                    'Complete: ' + \
                                    str(int(100. * self.num_complete/ \
                                                self.total_traces)) + '%'

                    t_s = time.time()
                    # Initialize trace acquisition
                    self.digi2.initialize()
                    time.sleep(0.05) # Needs a delay to sync properly
                    self.digi1.initialize()
                    time_init = time.time()

                    # Read measured values other than digitizer traces while
                    # waiting for the acquisition
                    atten_vs_read = self.qm.get_dac_voltages(self.open_quenches)
                    powers = self.qm.get_cavity_powers(self.open_quenches)

                    wg_A_power = self.gen.get_wg_power('A')
                    wg_B_power = self.gen.get_wg_power('B')

                    fc_currents = np.array(self.fcup.get_current("all"))

                    # Save the traces from the last acquisition
                    if self.num_complete > 0:
                        self.save_traces(self.filenames)

                    # Generate filenames from the current acquisition
                    d1c1_filename = self.make_filename(1)
                    d1c2_filename = self.make_filename(2)
                    d2c1_filename = self.make_filename(3)
                    d2c2_filename = self.make_filename(4)

                    self.filenames = np.array([d1c1_filename, d1c2_filename,
                                               d2c1_filename, d2c2_filename])

                    # Prepare the array to append to the main DataFrame
                    data_to_append = np.array([int(self.rep) + 1,
                                               int(self.avg) + \
                                               self.switch_iterator + 1,
                                               self.ab,
                                               self.gen_frequency,
                                               b_field[1],
                                               b_field[3],
                                               offset_frequency,
                                               pre910_state,
                                               wg_A_power,
                                               wg_B_power,
                                               time.time(),
                                               d1c1_filename,
                                               d1c2_filename,
                                               d2c1_filename,
                                               d2c2_filename])

                    data_to_append = np.append(data_to_append, fc_currents)

                    for quench_index in self.open_quenches:
                        this_quench = [powers[quench_index],
                                       atten_vs_read[quench_index]]
                        data_to_append = np.append(data_to_append, this_quench)

                    # Append the current data
                    print('\t'.join(list(map(str,data_to_append))))
                    self.data = self.data \
                                    .append(pd.Series(data_to_append,
                                                      name = len(self.data),
                                                      index = self.data.columns
                                                      )
                                            )
                    t_f = time.time()
                    print("Time to initialize and prepare: " + str(t_f - t_s))

                    # If necessary, wait for the trace to finish acquiring
                    # NOTE 01/03/2017: Perhaps in the future, we can use a
                    # separate thread to acquire the digitizer traces and just
                    # use a 'join' function here on the thread.
                    t_dif = time.time() - time_init
                    print("TRACE LENGTH: " + str(self.trace_length_s))
                    if t_dif < self.trace_length_s:
                        print("sleeping " + str(self.trace_length_s - t_dif + 0.1))
                        time.sleep(self.trace_length_s - t_dif + 0.1)
                    else: print("Not sleeping. t_dif is "+str(t_dif))

                    t_s = time.time()
                    V1 = self.digi1.read()
                    t_f = time.time()
                    print("Time to read from digitizer 1: " + str(t_f - t_s))
                    t_s = time.time()
                    self.V_det = V1[self.digi_det]
                    self.V1_c1 = V1[self.digi_c1]
                    t_f = time.time()
                    print("Time to separate channels 1: " + str(t_f - t_s))

                    t_s = time.time()
                    V2 = self.digi2.read()
                    t_f = time.time()
                    print("Time to read from digitizer 1: " + str(t_f - t_s))
                    t_s = time.time()
                    self.V2_c1 = V2[self.digi_c1]
                    self.V2_c2 = V2[self.digi_c2]
                    t_f = time.time()
                    print("Time to separate channels 2: " + str(t_f - t_s))

                    self.switch_iterator += 1
                    self.num_complete += 1
                self.ab_iterator += 1
            self.avg += self.traces_btwn_switch

        data_file = open(self.folder + 'data.txt', 'a')
        data_out = self.data.iloc[-2*self.max_avg:] \
                            .set_index(['Repeat',
                                        'Average',
                                        'Configuration',
                                        'Waveguide Carrier Frequency [MHz]'])
        data_out.to_csv(data_file, header = False)
        data_file.close()

        self.avg = 0
        self.pre910_state_iterator += 1

        # Check if the 910 state list has been exhausted
        # If so, change the offset frequency
        if self.pre910_state_iterator == self.num_910_states:
            self.pre910_state_iterator = 0
            self.pre910_states_randomized = \
                np.random.permutation(self.pre910_states)
            self.offset_frequency_iterator += 1

        # Check if the list of offset frequencies has been exhausted
        # If so, change the magnetic field setting
        if self.offset_frequency_iterator == self.num_offset_frequencies:
            self.offset_frequency_iterator = 0
            self.offset_frequencies_randomized = \
                np.random.permutation(self.offset_frequencies)
            self.b_iterator += 1

        # Check if the list of magnetic fields has been exhausted
        # If so, change the carrier frequency
        if self.b_iterator == self.num_b:
            self.b_iterator = 0
            self.b_list_randomized = np.random.permutation(self.b_list)
            print("Iterating f index")
            self.gen_f_iterator += 1
            print("NOW " + str(self.gen_f_iterator))

        # Check if the list of carrier frequencies has been exhausted
        # If so, begin the next repeat
        if self.gen_f_iterator == self.n_freqs:
            print(str(self.gen_f_iterator) + " = " + str(self.n_freqs))
            self.gen_f_iterator = 0
            self.freq_ind_randomized = np.random.permutation(self.freq_ind)
            self.rep += 1

        # Check if all repeats have been completed
        # If so, end the acquisition and notify the manager
        if self.rep == self.max_rep:
            self.save_traces(self.filenames)
            self.progress = 'Finished'
            self.end_time = time.time()
            print("Total time elapsed [s]: " + str(self.end_time - self.start_time))
            print("")
            self.acquisition_complete = True

        return

    def save_traces(self, filenames):
        vlist = [self.V_det, self.V1_c1, self.V2_c2, self.V2_c1]
        for i in range(4):
            np.save(self.bin + filenames[i] + ".digi",
                    np.frombuffer(vlist[i], dtype = np.dtype('i2')))

    def make_filename(self, num):
        r_name = "r" + "0" * (3 - len(str(self.rep+1))) + str(self.rep+1)
        a_name = "a" + "0" * (3 - len(str(self.avg+self.switch_iterator+1))) + \
                 str(self.avg+self.switch_iterator+1)
        freq = str(round(self.gen_frequency, 4))
        f_name = "f" + "0" * (9 - len(freq)) + freq

        of_name = ''
        if self.num_offset_frequencies > 1:
            of_name += 'of' + str(self.offset_frequency)

        b_name = ''
        if self.num_b > 1:
            if self.b_field[4] == 'x':
                b_name += 'Bx' + str(round(float(self.b_field[1]),1))

            if self.b_field[4] == 'y':
                b_name += 'By' + str(round(float(self.b_field[3]),1))

        p910_name = ''
        if self.num_910_states > 1:
            p910_name += '_910' + self.pre910_state

        name = r_name + a_name + f_name + of_name + b_name + "ch" + self.ab + \
               p910_name + "_0" + str(num)

        return name

    def pause(self):
        # Perform any shutdown/disconnect actions you want here before
        # communicating with the manager.

        self.progress = 'Paused... \n' + \
                        'Complete: ' + \
                        str(int(100. * self.num_complete/self.total_traces)) + \
                        '\%'
        self.close_instruments()
        super(FOSOFAcquisition, self).pause()

        return

    def resume(self):
        # Perform any re-initialization actions you want here before
        # communicating with the manager.

        self.progress = 'Resuming'

        # Setting up quenches
        self.qm = quench.QuenchManager()
        self.qm.open_quenches(self.open_quenches, \
                              atten_v = self.initial_atten_vs, \
                              is_on = self.quench_is_on)
        self.qm.cavities_off(self.off_quenches)
        self.qm.cavities_off(["pre-quench_910","post-quench_910"])

        # Setting up digitizers
        self.digi1 = digitizer.Digitizer(self.digi_addr, \
                                         ch1_range = self.ch_range, \
                                         ch2_range = self.ch_range, \
                                         sampling_rate = self.sampling_rate, \
                                         num_samples = self.num_samples)
        self.digi2 = digitizer.Digitizer(self.other_addr, \
                                         ch1_range = self.ch_range, \
                                         ch2_range = self.ch_range, \
                                         sampling_rate = self.sampling_rate, \
                                         num_samples = self.num_samples)

        self.digi1.sync('master')
        self.digi2.sync('slave')

        # Configure digitizers & quenches for last pre-quench 910 state
        if self.pre910_state == 'on':
            self.qm.cavity_on("pre-quench_910")
            self.digi1.set_numsamples(self.pre910_num_samples)
            self.digi2.set_numsamples(self.pre910_num_samples)

        # Setting up the generator
        self.gen = generator.Generator(calib = False,
                                       offset_freq = self.offset_frequency,
                                       scan_range = self.scan_range,
                                       e_field = self.wg_efield)
        self.gen.set_rf_frequency(self.gen_f_ind, self.ab)

        # Setting up magnetic field control
        self.progress = 'Initializing magnetic field control.'
        self.rm = visa.ResourceManager()
        self.bfield_control = bfc.BFieldControl(self.rm)
        self.bfield_control.set_B_field(0.0, "x")
        self.bfield_control.set_B_field(0.0, "y")

        # Setting up Faraday cup(s)
        self.fcup = faradaycupclass.FaradayCup()

        super(FOSOFAcquisition, self).resume()

        return

    def shut_down(self):
        # Perform any shutdown/disconnect actions you want here before
        # communicating with the manager.

        self.progress = 'Shutting down'
        self.close_instruments()
        super(FOSOFAcquisition, self).shut_down()

        return

    def close_instruments(self):
        ''' Closes all instruments associated with the acquisition.'''

        try:
            self.progress = 'Closing quenches'
            self.qm.off_and_close()
        except Exception as e:
            sys.stderr.write(tb.format_exc())

        try:
            self.progress = 'Closing digitizers'
            self.digi1.close()
            self.digi2.close()
        except Exception as e:
            sys.stderr.write(tb.format_exc())

        try:
            self.progress = 'Closing generator'
            self.gen.close()
        except Exception as e:
            sys.stderr.write(tb.format_exc())

        try:
            self.progress = 'Closing faraday cup'
            self.fcup.close()
        except Exception as e:
            sys.stderr.write(tb.format_exc())

        try:
            self.progress = 'Closing b field control'
            self.bfield_control.set_B_field(0.0, "x")
            self.bfield_control.set_B_field(0.0, "y")
            self.bfield_control.close()
        except Exception as e:
            sys.stderr.write(tb.format_exc())

# This function must always be included. This function is what the Manager
# will call. It must always take these three arguments in this order.
def begin(queue_in, queue_out, queue_err):
    acq = FOSOFAcquisition(queue_in, queue_out, queue_err)

    return

def main():
    queue_in = mp.queues.Queue()
    queue_out = mp.queues.Queue()
    queue_err = mp.queues.Queue()

    queue_in.put(independent_rd_location)

    acq = PhaseMonitor(queue_in, queue_out, queue_err)

if __name__ == '__main__':
    main()