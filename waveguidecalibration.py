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

# Run Dictionary Keys
# Experiment Name = string
# Experiment Name Addon = string
# Number of Repeats = int > 0
# Number of Averages = int > 0
# Waveguide Power (Start) [dBm] = float -140.0 <= x <= 0.0
# Waveguide Power (Stop) [dBm] = float -140.0 <= x <= 0.0
# Waveguide Frequency (Start) [MHz] = float 0.010 <= x <= 2400.0
# Waveguide Frequency (Stop) [MHz] = float 0.010 <= x <= 2400.0
# Number of Power Scan Steps = int > 0
# Number of Frequency Scan Steps = int > 0
# Digitizer Address = A or B
# Digitizer Channel Range [V] = int (see Digitizer Manual)
# Digitizer Sampling Rate [S/s] = int (see Digitizer Manual)
# Number of Digitizer Samples = int (see Digitizer Manual)
# Digitizer Channel for Detector = 1 or 2
# Quenches = filename
# Waveguide to Scan = A, B or BOTH
# Binary Traces = bool

independent_rd_location = qol.path_file['Run Queue'] + \
                          'waveguide_calibration_DEFAULT.rd'

class WaveguideCalibration(Acquisition):

    # This init header should not be changed. The function should always take
    # self and three queues.
    def __init__(self, queue_in, queue_out, queue_err):
        super(WaveguideCalibration, self).__init__(queue_in, queue_out, \
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

        self.qm = quench.QuenchManager()

        quench_arrays = qol.quench_arrays(self.quench_file)

        self.open_quenches = quench_arrays[0]
        self.quench_is_on = quench_arrays[1]
        self.off_quenches = quench_arrays[2]
        self.initial_atten_vs = quench_arrays[3]
        self.on_quenches = quench_arrays[4]

        self.progress = 'Opening quenches'

        self.qm.open_quenches(self.open_quenches, \
                              atten_v = self.initial_atten_vs, \
                              is_on = self.quench_is_on)
        self.qm.cavities_off(self.off_quenches)

        self.progress = 'Opening digitizer'

        self.num_samples = int(self.run_dictionary \
                                   .ix['Number of Digitizer Samples'].Value)
        self.sampling_rate = int(self.run_dictionary \
                                     .ix['Digitizer Sampling Rate [S/s]'].Value)
        self.ch_range = int(self.run_dictionary \
                                .ix['Digitizer Channel Range [V]'].Value)
        self.digi = digitizer.Digitizer(self.run_dictionary \
                                            .ix['Digitizer Address'].Value, \
                                        ch1_range = self.ch_range, \
                                        ch2_range = self.ch_range, \
                                        sampling_rate = self.sampling_rate, \
                                        num_samples = self.num_samples)
        self.digi_channel = int(self.run_dictionary.ix['Digitizer Channel ' + \
                                                       'for Detector'].Value)

        self.progress = 'Opening generator'

        self.gen = generator.Generator(calib = True)
        self.scan_wg = self.run_dictionary.ix['Waveguide to Scan'].Value
        self.gen.power_low('A')
        self.gen.power_on('A')
        self.gen.power_low('B')
        self.gen.power_on('B')

        self.max_rep = int(self.run_dictionary.ix['Number of Repeats'].Value)
        self.max_avg = int(self.run_dictionary.ix['Number of Averages'].Value)

        p_min = float(self.run_dictionary \
                          .ix['Waveguide Power (Start) [dBm]'].Value)
        p_max = float(self.run_dictionary \
                          .ix['Waveguide Power (Stop) [dBm]'].Value)
        self.n_powers = int(self.run_dictionary \
                                .ix['Number of Power Scan Steps'].Value)

        self.gen_p_list = np.linspace(p_min, p_max, self.n_powers)
        self.gen_p_randomized = np.random.permutation(self.gen_p_list)

        f_min = float(self.run_dictionary \
                          .ix['Waveguide Frequency (Start) [MHz]'].Value)
        f_max = float(self.run_dictionary \
                          .ix['Waveguide Frequency (Stop) [MHz]'].Value)
        self.n_freqs = int(self.run_dictionary \
                                .ix['Number of Frequency Scan Steps'].Value)

        self.gen_f_list = np.linspace(f_min, f_max, self.n_freqs)
        self.gen_f_randomized = np.random.permutation(self.gen_f_list)

        self.progress = 'Setting up data table'

        cols = ['Generator Channel',
                'Repeat',
                'Waveguide Frequency Setting [MHz]',
                'Waveguide Power Setting [dBm]',
                'Average',
                "Waveguide A Power Reading  (Generator On) [V]",
                "Waveguide B Power Reading (Generator On) [V]",
                "Waveguide A Power Reading  (Generator Off) [V]",
                "Waveguide B Power Reading (Generator Off) [V]",
                "Digitizer DC (Quenches On) [V]",
                "Digitizer STD (Quenches On) [V]",
                "Digitizer DC (Quenches Off) [V]",
                "Digitizer STD (Quenches Off) [V]",
                "Digitizer DC On/Off Ratio",
                "Time"]

        for q in self.open_quenches:
            cols.append(qol.formatted_quench_name(q) + \
                        ' Power Detector Reading (Generator On) [V]')
            cols.append(qol.formatted_quench_name(q) + \
                        ' Attenuator Voltage Reading (Generator On) [V]')
            cols.append(qol.formatted_quench_name(q) + \
                        ' Power Detector Reading (Generator Off) [V]')
            cols.append(qol.formatted_quench_name(q) + \
                        ' Attenuator Voltage Reading (Generator Off) [V]')

        # Write column headers
        self.data = pd.DataFrame(columns = cols)
        data_file = open(self.folder + 'data.txt', 'a')
        self.data.to_csv(data_file, index=False)
        data_file.close()
        print('\t'.join(self.data.columns))

        self.rep = 0
        self.avg = 0
        self.gen_p_iterator = 0
        self.gen_f_iterator = 0
        self.wg_iterator = 0

        self.frequency = 0.0

        if self.scan_wg == 'A' or self.scan_wg == 'B':
            self.n_wgs = 1
            self.waveguide_list = [self.scan_wg]
        elif self.scan_wg == 'BOTH':
            self.n_wgs = 2
            self.waveguide_list = ['A', 'B']
        else:
            raise qol.Travisty("Waveguide to Scan must have value \'A\', " + \
                               "\'B\', or BOTH.")

        self.waveguide_list_randomized = np.random  \
                                           .permutation(self.waveguide_list)

        self.total_traces = self.max_rep * self.max_avg * self.n_powers * \
                            self.n_freqs * self.n_wgs

        self.progress = 'Initialization complete'
        self.start_time = dt.now()
        print('Beginning acquisition...')

        return

    def acquire(self):

        gen_p = self.gen_p_randomized[self.gen_p_iterator]
        gen_f = self.gen_f_randomized[self.gen_f_iterator]
        wg = self.waveguide_list_randomized[self.wg_iterator]

        if self.frequency != gen_f:
            self.gen.set_rf_frequency(gen_f, "N")
            self.frequency = gen_f

        while self.avg < self.max_avg:
            self.num_complete = self.wg_iterator * self.max_rep * \
                                self.n_freqs * self.n_powers * self.max_avg + \
                                self.rep * self.n_freqs * self.n_powers * \
                                self.max_avg + self.gen_f_iterator * \
                                self.n_powers * self.max_avg + \
                                self.gen_p_iterator * self.max_avg + \
                                self.avg + 1
            self.progress = 'Waveguide ' + wg + '\n' + \
                            'Repeat ' + str(self.rep + 1) + '\n' + \
                            'Generator Power: ' + str(round(gen_p,2)) + \
                            ' dBm\n' + \
                            'Generator Frequency: ' + str(round(gen_f,2)) + \
                            ' MHz\n' + \
                            'Average ' + str(self.avg + 1) + '\n' + \
                            'Complete: ' + \
                            str(int(100. * self.num_complete/ \
                                           self.total_traces)) + '%'


            self.gen.set_rf_power(wg, round(gen_p,1))
            print(self.gen.get_rf_generator_power(wg))
            self.qm.cavities_on(self.on_quenches)

            V = self.digi.ini_read(channel = self.digi_channel, \
                                   read_type = 'FLOAT', \
                                   ret_bin = False)
            V = V[0]

            dc_on_avg = np.mean(V)
            dc_on_std = np.std(V)

            atten_vs_read_on = self.qm.get_dac_voltages(self.open_quenches)
            powers_on = self.qm.get_cavity_powers(self.open_quenches)

            wg_A_power_on = self.gen.get_wg_power('A')
            wg_B_power_on = self.gen.get_wg_power('B')
            # pd_voltage_on = self.qm.get_power_detector_dc_in()

            self.gen.power_low('A')
            self.gen.power_low('B')
            self.qm.cavities_off(self.on_quenches)

            V = self.digi.ini_read(channel = self.digi_channel, \
                                   read_type = 'FLOAT', \
                                   ret_bin = False)
            V = V[0]

            dc_off_avg = np.mean(V)
            dc_off_std = np.std(V)

            atten_vs_read_off = self.qm.get_dac_voltages(self.open_quenches)
            powers_off = self.qm.get_cavity_powers(self.open_quenches)

            wg_A_power_off = self.gen.get_wg_power('A')
            wg_B_power_off = self.gen.get_wg_power('B')
            # pd_voltage_off = self.qm.get_power_detector_dc_in()

            on_off_ratio = dc_on_avg / dc_off_avg

            data_to_append = np.array([wg,
                                       int(self.rep)+1,
                                       gen_f,
                                       gen_p,
                                       int(self.avg)+1,
                                       wg_A_power_on,
                                       wg_B_power_on,
                                       wg_A_power_off,
                                       wg_B_power_off,
                                       dc_on_avg,
                                       dc_on_std,
                                       dc_off_avg,
                                       dc_off_std,
                                       on_off_ratio,
                                       time.time()])
            for quench_index in self.open_quenches:
                this_quench = [powers_on[quench_index],
                               atten_vs_read_on[quench_index],
                               powers_off[quench_index],
                               atten_vs_read_off[quench_index]]
                data_to_append = np.append(data_to_append, this_quench)

            print(len(self.data.columns))
            print('\t'.join(list(map(str,data_to_append))))
            self.data = self.data.append(pd.Series(data_to_append,
                                                   name = len(self.data),
                                                   index = self.data.columns
                                                   )
                                        )
            self.avg += 1

        data_file = open(self.folder + 'data.txt', 'a')
        data_out = self.data.iloc[-self.max_avg:] \
                            .set_index(['Generator Channel',
                                        'Repeat',
                                        'Waveguide Frequency Setting [MHz]',
                                        'Waveguide Power Setting [dBm]',
                                        'Average'])
        data_out.to_csv(data_file, header = False)
        data_file.close()

        self.avg = 0
        self.gen_p_iterator += 1

        if self.gen_p_iterator == self.n_powers:
            self.gen_p_iterator = 0
            self.gen_f_iterator += 1
            self.gen_p_randomized = np.random.permutation(self.gen_p_list)

        if self.gen_f_iterator == self.n_freqs:
            self.gen_f_iterator = 0
            self.rep += 1
            self.gen_f_randomized = np.random.permutation(self.gen_f_list)

        if self.rep == self.max_rep:
            self.rep = 0
            self.wg_iterator += 1

        if self.wg_iterator == self.n_wgs:
            self.progress = 'Finished'
            self.acquisition_complete = True

        return

    def pause(self):
        # Perform any shutdown/disconnect actions you want here before
        # communicating with the manager.

        self.progress = 'Paused... \n' + \
                        'Complete: ' + \
                        str(int(100. * self.num_complete/self.total_traces)) + \
                        '\%'
        self.close_instruments()
        super(WaveguideCalibration, self).pause()

        return

    def resume(self):
        # Perform any re-initialization actions you want here before
        # communicating with the manager.

        self.progress = 'Resuming'
        self.qm = quench.QuenchManager()
        self.qm.open_quenches(self.open_quenches, \
                              atten_v = self.initial_atten_vs, \
                              is_on = self.quench_is_on)
        self.qm.cavities_off(self.off_quenches)

        self.digi = digitizer.Digitizer(self.run_dictionary \
                                            .ix['Digitizer Address'].Value, \
                                        ch1_range = self.ch_range, \
                                        ch2_range = self.ch_range, \
                                        num_samples = self.num_samples)

        self.gen = generator.Generator(calib = True)
        self.gen.power_low('A')
        self.gen.power_low('B')

        super(WaveguideCalibration, self).resume()

        return

    def shut_down(self):
        # Perform any shutdown/disconnect actions you want here before
        # communicating with the manager.

        self.progress = 'Shutting down'
        self.close_instruments()
        super(WaveguideCalibration, self).shut_down()

        return

    def close_instruments(self):
        ''' Closes all instruments associated with the acquisition.'''

        try:
            self.progress = 'Closing quenches'
            self.qm.off_and_close()
        except Exception as e:
            sys.stderr.write(tb.format_exc())

        try:
            self.progress = 'Closing digitizer'
            self.digi.close()
        except Exception as e:
            sys.stderr.write(tb.format_exc())

        try:
            self.progress = 'Closing generator'
            self.gen.close()
        except Exception as e:
            sys.stderr.write(tb.format_exc())

# This function must always be included. This function is what the Manager
# will call. It must always take these three arguments in this order.
def begin(queue_in, queue_out, queue_err):
    acq = WaveguideCalibration(queue_in, queue_out, queue_err)

    return

def main():
    queue_in = mp.queues.Queue()
    queue_out = mp.queues.Queue()
    queue_err = mp.queues.Queue()

    queue_in.put(independent_rd_location)

    acq = PhaseMonitor(queue_in, queue_out, queue_err)

if __name__ == '__main__':
    main()