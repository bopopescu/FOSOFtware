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
import sys

# Run Dictionary Keys
# Experiment Name = string
# Experiment Name Addon = string
# Number of Repeats = int > 0
# Number of Averages = int > 0
# RF Attenuator Voltage (Start) [V] = float 0.0 <= x <= 8.0
# RF Attenuator Voltage (Stop) [V] = float 0.0 <= x <= 8.0
# Number of Scan Steps = int > 0
# Digitizer Address = A or B
# Digitizer Channel Range [V] = int (see Digitizer Manual)
# Digitizer Sampling Rate [S/s] = int (see Digitizer Manual)
# Number of Digitizer Samples = int (see Digitizer Manual)
# Digitizer Channel for Detector = 1 or 2
# Quenches = filename
# Quench Cavity to Scan = cavity name (see Manager docs)
# Binary Traces = bool

independent_rd_location = qol.path_file['Run Queue'] + \
                          'quench_calibration_DEFAULT.rd'

class QuenchCalibration(Acquisition):

    # This init header should not be changed. The function should always take
    # self and three queues.
    def __init__(self, queue_in, queue_out, queue_err):
        super(QuenchCalibration, self).__init__(queue_in, queue_out, \
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
        self.scan_quench = self.run_dictionary.ix['Quench Cavity to Scan'].Value

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
        #self.gen.power_low('A')
        #self.gen.power_low('B')

        self.max_rep = int(self.run_dictionary.ix['Number of Repeats'].Value)
        self.max_avg = int(self.run_dictionary.ix['Number of Averages'].Value)

        v_min = float(self.run_dictionary \
                          .ix['RF Attenuator Voltage (Start) [V]'].Value)
        v_max = float(self.run_dictionary \
                          .ix['RF Attenuator Voltage (Stop) [V]'].Value)
        self.n_atten_vs = int(self.run_dictionary \
                                  .ix['Number of Scan Steps'].Value)

        self.atten_v_list = self.linear_sqpower_list(v_min, v_max, self.n_atten_vs)
        self.atten_v_randomized = np.random.permutation(self.atten_v_list)

        self.progress = 'Setting up data table'

        cols = ["Repeat",
                "Average",
                "Attenuator Voltage Setting [V]",
                "Digitizer DC (Quenches On) [V]",
                "Digitizer STD (Quenches On) [V]",
                "Digitizer DC (Quenches Off) [V]",
                "Digitizer STD (Quenches Off) [V]",
                "Digitizer DC On/Off Ratio",
                "Time"]

        for q in self.open_quenches:
            cols.append(qol.formatted_quench_name(q) + \
                        ' Power Detector Reading (Quenches On) [V]')
            cols.append(qol.formatted_quench_name(q) + \
                        ' Attenuator Voltage Reading (Quenches On) [V]')
            cols.append(qol.formatted_quench_name(q) + \
                        ' Power Detector Reading (Quenches Off) [V]')
            cols.append(qol.formatted_quench_name(q) + \
                        ' Attenuator Voltage Reading (Quenches Off) [V]')

        # Write column headers
        self.data = pd.DataFrame(columns = cols)
        data_file = open(self.folder + 'data.txt', 'a')
        self.data.to_csv(data_file, index=False)
        data_file.close()
        print('\t'.join(self.data.columns))

        self.rep = 0
        self.avg = 0
        self.atten_v_iterator = 0

        self.total_traces = self.max_rep * self.max_avg * self.n_atten_vs

        self.progress = 'Initialization complete'
        self.start_time = dt.now()
        print('Beginning acquisition...')

        return

    def acquire(self):

        atten_v = self.atten_v_randomized[self.atten_v_iterator]
        self.qm.set_dac_voltage(self.scan_quench, atten_v)

        while self.avg < self.max_avg:
            self.num_complete = self.rep * self.n_atten_vs * self.max_avg + \
                           self.atten_v_iterator * self.max_avg + self.avg + 1
            self.progress = 'Repeat ' + str(self.rep + 1) + '\n' + \
                            'Attenuation Voltage: ' + str(round(atten_v,2)) + \
                            ' V\n' + \
                            'Average ' + str(self.avg + 1) + '\n' + \
                            'Complete: ' + \
                            str(int(100. * self.num_complete/self.total_traces)) + \
                            '\%'

            self.qm.cavities_on(self.on_quenches)

            V = self.digi.ini_read(channel = self.digi_channel, \
                                   read_type = 'FLOAT', \
                                   ret_bin = False)
            V = V[0]

            dc_on_avg = np.mean(V)
            dc_on_std = np.std(V)

            atten_vs_read_on = self.qm.get_dac_voltages(self.open_quenches)
            powers_on = self.qm.get_cavity_powers(self.open_quenches)
            # pd_voltage_on = self.qm.get_power_detector_dc_in()

            self.qm.cavities_off(self.on_quenches)

            V = self.digi.ini_read(channel = self.digi_channel, \
                                   read_type = 'FLOAT', \
                                   ret_bin = False)
            V = V[0]

            dc_off_avg = np.mean(V)
            dc_off_std = np.std(V)

            atten_vs_read_off = self.qm.get_dac_voltages(self.open_quenches)
            powers_off = self.qm.get_cavity_powers(self.open_quenches)
            # pd_voltage_off = self.qm.get_power_detector_dc_in()

            on_off_ratio = dc_on_avg / dc_off_avg

            data_to_append = np.array([int(self.rep)+1, \
                                       int(self.avg)+1, \
                                       atten_v, \
                                       dc_on_avg, \
                                       dc_on_std, \
                                       dc_off_avg, \
                                       dc_off_std, \
                                       on_off_ratio, \
                                       time.time()])
            for quench_index in self.open_quenches:
                this_quench = [powers_on[quench_index], \
                               atten_vs_read_on[quench_index], \
                               powers_off[quench_index], \
                               atten_vs_read_off[quench_index]]
                data_to_append = np.append(data_to_append, this_quench)

            print('\t'.join(list(map(str,data_to_append))))
            self.data = self.data.append(pd.Series(data_to_append, \
                                                   name = len(self.data), \
                                                   index = self.data.columns
                                                   )
                                        )
            self.avg += 1

        data_file = open(self.folder + 'data.txt', 'a')
        data_out = self.data.iloc[-self.max_avg:] \
                            .set_index(['Repeat', \
                                        'Average', \
                                        'Attenuator Voltage Setting [V]'])
        data_out.to_csv(data_file, header = False)
        data_file.close()

        self.avg = 0
        self.atten_v_iterator += 1

        if self.atten_v_iterator == self.n_atten_vs:
            self.atten_v_iterator = 0
            self.rep += 1
            self.atten_v_randomized = np.random.permutation(self.atten_v_list)

        if self.rep == self.max_rep:
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
        super(QuenchCalibration, self).pause()

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

        super(QuenchCalibration, self).resume()

        return

    def shut_down(self):
        # Perform any shutdown/disconnect actions you want here before
        # communicating with the manager.

        self.progress = 'Shutting down'
        self.close_instruments()
        super(QuenchCalibration, self).shut_down()

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

    def linear_sqpower_list(self, v_min, v_max, n_points):
        ''' Takes the maximum and minimum voltage inputs for the voltage
        attenuator and converts them to root powers in Sqrt[W] by fitting to a
        calibration file.
        '''

        calibration = pd.read_csv("C:/DEVICEDATA/" + \
                                  "SqrtRfPowerVsRfAttenuationVoltage.txt", \
                                  sep = '\t')
        calibration = calibration.set_index('RF attenuator voltage [V]')

        # Fit 15th order polynomials to the data. The fit order is overkill but
        # it looks fine.
        v_to_sqp = np.polyfit(calibration.index, \
                              np.transpose(calibration.values).flatten(), 15)
        sqp_to_v = np.polyfit(np.transpose(calibration.values).flatten(), \
                              calibration.index, 15)
        sqp_to_v_vec = np.vectorize(np.poly1d(sqp_to_v)) # Allow the function to
                                                         # accept an array as
                                                         # input

        # Convert the extremities
        min_sqp = np.poly1d(v_to_sqp)(v_min)
        max_sqp = np.poly1d(v_to_sqp)(v_max)

        # Make a list of points linear in sqrt(P)
        sqp_list = np.linspace(min_sqp, max_sqp, num = n_points)

        # Convert the list to volts and return
        v_list = sqp_to_v_vec(sqp_list)

        return v_list

# This function must always be included. This function is what the Manager
# will call. It must always take these three arguments in this order.
def begin(queue_in, queue_out, queue_err):
    acq = QuenchCalibration(queue_in, queue_out, queue_err)

    return

def main():
    queue_in = mp.queues.Queue()
    queue_out = mp.queues.Queue()
    queue_err = mp.queues.Queue()

    queue_in.put(independent_rd_location)

    acq = PhaseMonitor(queue_in, queue_out, queue_err)

if __name__ == '__main__':
    main()