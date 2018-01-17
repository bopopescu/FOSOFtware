from acquisition import Acquisition
from fosof_qol import Travisty
import multiprocessing as mp
import thread
import threading
import time
import fosof_qol as qol
import sys
import pandas as pd
import generator
import digitizer
import quench
import time
from datetime import datetime as dt
import numpy as np
from numpy import sin, cos, tan, pi
import traceback as tb
import faradaycupclass
import matplotlib.pyplot as plt

try:
    from queue import Queue, Empty
except ImportError:
    from Queue import Queue, Empty

# Run Dictionary Keys
# Experiment Name = string
# Experiment Name Addon = string
# Number of Traces per Loop = int > 0
# Digitizer Channel Range [V] = int (see Digitizer Manual)
# Digitizer Sampling Rate [S/s] = int (see Digitizer Manual)
# Number of Digitizer Samples = int (see Digitizer Manual)
# Digitizer Address for Power Combiners = A or B
# Digitizer Channel for Power Combiner I = 1 or 2
# Digitizer Channel for Power Combiner R = 1 or 2
# Quenches = filename
# RF Generator Frequency Offset [Hz] = int < 2000
# RF Electric Field Peak Amplitude [V/cm] = int 5 - 25
# RF Frequency Range = string (small, medium, large, extralarge)
# Binary Traces = bool
# Notes = string

independent_rd_location = qol.path_file['Run Queue'] + \
                          'phase_monitor_DEFAULT.rd'

class PhaseMonitor(Acquisition):

    def __init__(self, queue_in, queue_out, queue_err):

        super(PhaseMonitor, self).__init__(queue_in, queue_out, queue_err, \
                                           phase_monitor = True)

    def initialize_acquisition(self):
        # Initialize all global variables here, including the 'progress'
        # variable.

        self.progress = 'Printing data.txt comment header'
        print(digitizer)

        self.comments = qol.make_comment_string(self.run_dictionary, \
                                                self.run_dictionary['Order'] \
                                                    .values)

        data_file = open(self.folder + 'data.txt', 'w')
        data_file.write(self.comments)

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
                                            .ix['Digitizer Address for ' + \
                                                'Power Combiners'].Value,
                                        ch1_range = self.ch_range,
                                        ch2_range = self.ch_range,
                                        sampling_rate = self.sampling_rate,
                                        num_samples = self.num_samples)
        self.digi_channel_i = int(self.run_dictionary \
                                      .ix['Digitizer Channel for Power ' + \
                                          'Combiner I'].Value)
        self.digi_channel_i -= 1

        self.digi_channel_r = int(self.run_dictionary \
                                      .ix['Digitizer Channel for Power ' + \
                                          'Combiner R'].Value)
        self.digi_channel_r -= 1

        self.progress = 'Opening generator'

        self.offset_freq = float(self.run_dictionary.ix['RF Generator ' + \
                                                        'Frequency Offset ' + \
                                                        '[Hz]'].Value)
        self.rf_e_field = int(self.run_dictionary.ix['RF Electric Field ' + \
                                                     'Peak Amplitude ' + \
                                                     '[V/cm]'].Value)
        self.rf_scan_range = self.run_dictionary.ix['RF Frequency Range'].Value
        self.gen = generator.Generator(offset_freq = self.offset_freq, \
                                       e_field = self.rf_e_field, \
                                       scan_range = self.rf_scan_range,
                                       calib = True)
        self.gen.set_rf_frequency(910.0, offset_channel = 'A',
                                  change_power = True)

        self.max_avg = int(self.run_dictionary \
                               .ix['Number of Traces per Loop'].Value)

        self.fc = faradaycupclass.FaradayCup()

        self.progress = 'Setting up data table'

        cols = ["Repeat", \
                "Average", \
                "Power Combiner I Amplitude [V]", \
                "Power Combiner I DC Offset [V]", \
                "Power Combiner R Amplitude [V]",
                "Power Combiner R DC Offset [V]", \
                "Power Combiner Phase Difference (R - I) [rad]", \
                "Waveguide A Power Detector Reading [V]", \
                "Waveguide B Power Detector Reading [V]", \
                "Time",
                "fc1a",
                "fc1b",
                "fc1c",
                "fc1d",
                "fc2i",
                "fc2ii",
                "fc2iii",
                "fc2iv",
                "fc3",
                "fccentre" ]

        for q in self.open_quenches:
            cols.append(qol.formatted_quench_name(q) + \
                       ' Power Detector Reading [V]')
            cols.append(qol.formatted_quench_name(q) + \
                       ' Attenuator Voltage Reading [V]')

        self.data = pd.DataFrame(columns = cols)
        self.data.set_index(['Repeat','Average']).to_csv(data_file)
        data_file.close()
        print('\t'.join(self.data.columns))

        self.rep = 0
        self.avg = 0

        self.progress = 'Initialization complete'
        self.start_time = dt.now()
        print('Beginning acquisition...')

        return

    def acquire(self):

        while self.avg < self.max_avg:
            self.progress = 'Loop ' + str(self.rep) + '\nTrace ' + str(self.avg)
            V = self.digi.ini_read(channel = None, read_type = 'FLOAT', ret_bin = False)
            print(self.digi_channel_i,self.digi_channel_r)

            a_i, phi_i, dc_i = qol.fit(V[self.digi_channel_i],
                                       1./self.sampling_rate, self.offset_freq)
            a_r, phi_r, dc_r = qol.fit(V[self.digi_channel_r],
                                       1./self.sampling_rate, self.offset_freq)

            phase_diff = (phi_r - phi_i + 2.*np.pi) % (2.*np.pi)

            fcup_currents = np.array(self.fc.get_current("all"))

            atten_vs_read = self.qm.get_dac_voltages(self.open_quenches)
            powers = self.qm.get_cavity_powers(self.open_quenches)
            wg_power_a = self.gen.get_wg_power('A')
            wg_power_b = self.gen.get_wg_power('B')

            data_to_append = np.array([self.rep+1,
                                       self.avg+1,
                                       a_i,
                                       dc_i,
                                       a_r,
                                       dc_r,
                                       phase_diff,
                                       wg_power_a,
                                       wg_power_b,
                                       time.time()])

            data_to_append = np.append(data_to_append, fcup_currents)

            for quench_index in self.open_quenches:
                this_quench = [powers[quench_index],
                               atten_vs_read[quench_index]]
                data_to_append = np.append(data_to_append, this_quench)

            sys.stdout.write('\t'.join(list(map(str,data_to_append))))
            self.data = self.data.append(pd.Series(data_to_append,
                                                   name = len(self.data),
                                                   index = self.data.columns
                                                  )
                                        )

            self.avg += 1

        data_file = open(self.folder + 'data.txt', 'a')
        self.data_out = self.data.iloc[-self.max_avg:].set_index(['Repeat', 'Average'])
        self.data_out.to_csv(data_file, header = False)
        data_file.close()
        self.rep += 1
        self.avg = 0

        return

    def pause(self):
        sys.stdout.write("Pausing.")

        self.close_instruments()
        super(PhaseMonitor,self).pause()

        return

    def resume(self):
        sys.stdout.write("Resuming.")
        self.progress = 'Opening quenches'

        self.qm = quench.QuenchManager()
        self.qm.open_quenches(self.open_quenches, \
                              atten_v = self.initial_atten_vs, \
                              is_on = self.quench_is_on)
        self.qm.cavities_off(self.off_quenches)

        self.progress = 'Opening digitizer'

        self.digi = digitizer.Digitizer(self.run_dictionary \
                                            .ix['Digitizer Address for ' + \
                                                'Power Combiners'].Value,
                                        ch1_range = self.ch_range,
                                        ch2_range = self.ch_range,
                                        sampling_rate = self.sampling_rate,
                                        num_samples = self.num_samples)

        self.progress = 'Opening generator'

        self.gen = generator.Generator(offset_freq = self.offset_freq, \
                                       e_field = self.rf_e_field, \
                                       scan_range = self.rf_scan_range,
                                       calib = True)
        self.gen.set_rf_frequency(910.0, offset_channel = 'A',
                                  change_power = True)

        self.fc = faradaycupclass.FaradayCup()

        self.progress = 'Resume complete'
        super(PhaseMonitor, self).resume()

        return

    def shut_down(self):
        sys.stdout.write("Shutting down.")

        self.close_instruments()
        super(PhaseMonitor,self).shut_down()

        return

    def close_instruments(self):

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

        try:
            self.progress = 'Closing Faraday cup'
            self.fc.close()
        except Exception as e:
            sys.stderr.write(tb.format_exc())

def begin(queue_in, queue_out, queue_err):
    acq = PhaseMonitor(queue_in, queue_out, queue_err)
    return

def main():
    queue_in = mp.queues.Queue()
    queue_out = mp.queues.Queue()
    queue_err = mp.queues.Queue()

    queue_in.put(independent_rd_location)

    acq = PhaseMonitor(queue_in, queue_out, queue_err)

if __name__ == '__main__':
    main()