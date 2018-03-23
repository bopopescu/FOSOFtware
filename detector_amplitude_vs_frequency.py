'''This program was used to determine the time constant for Amar's mini
detector. This is done by amplitude modulating one waveguide at various
frequencies and analyzing the resulting traces to determine the bandwidth of
the detector.
'''

import generator
import fosof_qol as qol
import digitizer
import time
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime as dt
import os

def main():
    # Data collection parameters
    n_repeats = 1
    n_averages = 5
    ch_range = 0.25
    sleep_time = 0.5

    # Folder in which we will save
    timestring = dt.strftime(dt.now(),'%Y%m%d-%H%M%S')
    folder = 'C:/Google Drive/data/'+timestring+' - Detector Bandwidth Test'
    os.mkdir(folder)

    # Dataframe setup
    dataframe_columns = ['Repeat',
                         'Average',
                         'AM Modulation Frequency [Hz]',
                         'Amplitude at AM Modulation Frequency [V]',
                         '0 Hz Frequency Component (AM On) [V]',
                         'Noise at AM Modulation Frequency [V]',
                         '0 Hz Frequency Component (AM Off) [V]']
    dataframe = pd.DataFrame(columns = dataframe_columns)

    # Connect to generator and digitizer
    gen = generator.Generator(calib=True, b_on = False)
    digi = digitizer.Digitizer('B',sampling_rate = int(1e5),
                               num_samples = int(1e5), ch1_range = ch_range)

    # Determine am_frequencies to use
    am_freqs = np.array([int(i*10) for i in range(101) if (i*10) % 60 > 0])
    am_freqs = np.random.permutation(am_freqs)

    # Initialize generator parameters
    gen.set_rf_frequency(910.0, 'N')
    gen.set_rf_power('A',-10.0)
    gen.am_on('A',80.0,100)
    time.sleep(0.5)


    for rep in range(n_repeats):
        for am_mod_freq in am_freqs:
            for avg in range(n_averages):
                gen.am_on('A', 80.0, am_mod_freq)
                time.sleep(sleep_time)

                V, err = digi.ini_read(channel = 1, ret_bin = False)
                V = V*ch_range/32767
                amplitude_on, phase, dc_on = qol.fit(V, 1e-5, am_mod_freq)

                print(am_mod_freq, amplitude_on)

                gen.am_off()
                time.sleep(sleep_time)

                V, err = digi.ini_read(channel = 1, ret_bin = False)
                V = V*ch_range/32767
                amplitude_off, phase, dc_off = qol.fit(V, 1e-5, am_mod_freq)

                print(am_mod_freq, amplitude_off)

                data_to_append = [rep+1,
                                  avg+1,
                                  am_mod_freq,
                                  amplitude_on,
                                  dc_on,
                                  amplitude_off,
                                  dc_off]
                dataframe = dataframe.append(pd.Series(data_to_append,
                                                       index = dataframe_columns),
                                             ignore_index=True)

    gen.power_low('A')
    gen.close()

    digi.close()

    dataframe = dataframe.set_index(dataframe_columns[:3])
    dataframe.to_csv(folder + '/data.csv')

if __name__ == '__main__':
    main()