''' This python module was made to clean up all of our acquisition codes. It
contains methods for routines that we perform all the time. This should save us
some space so we can more easily write and debug our acquisition codes.
'''
import pandas as pd
import time
import os
import sys
from datetime import date
from datetime import datetime as dt
from termcolor import cprint
import subprocess as sp
import threading
import numpy as np
from numpy import sin, cos, tan, pi
import thread
import socket


try:
    from Queue import Queue, Empty
except ImportError:
    from queue import Queue, Empty

_DEFAULT_FILE_LOCATION_ = 'C:/DEVICEDATA/'
path_file = pd.read_csv(_DEFAULT_FILE_LOCATION_ + "paths.csv")
path_file = pd.Series(path_file.ix[0]) # Turning this into a dict (basically)

_GD_DATA_PATH_ = path_file["Data"]
_BINARY_PATH_ = path_file["Binary Traces"]


class Travisty(Exception):
    def __init__(self, msg):
        self.message = msg

class NewLogger(object):
    ''' A new logger class to work with the new FOSOFtware.'''

    def __init__(self, out_queue, out_file, kind, app = False):
        self.kind = kind
        self.output = out_queue
        if app:
            self.outfile = open(out_file,'a')
        else:
            self.outfile = open(out_file,'w')

    def write(self, message):
        self.output.put(message)
        date_and_time = dt.strftime(dt.today(),'%Y-%m/%d %H:%M:%S')
        self.outfile.write(date_and_time + '\t' + message)
        self.outfile.write("\n")
        self.outfile.flush()

    def flush(self):
        self.outfile.flush()

    def close(self):
        self.outfile.close()
        self.restore()

    def restore(self):
        if self.kind == 'out':
            sys.stdout == sys.__stdout__
        elif self.kind == 'err':
            sys.stderr == sys.__stderr__

def make_gd_folder(main_name, addon, make_bin = False):
    ''' Creates a folder for the acquisition in the Google Drive data folder
    and returns the absolute path to the new folder. Has an option to let you
    make a binary folder as well.
    '''

    start_time_string = time.strftime("%H%M%S")
    filename_prefix = date.today().strftime("%y%m%d")+ "-" + start_time_string
    directory_name = filename_prefix + " - " + main_name + " - " + addon
    absolute = _GD_DATA_PATH_ + directory_name + '/'

    os.mkdir(absolute)

    if make_bin:
        absolute_bin = make_binary_folder(main_name, filename_prefix, addon)
        return absolute, absolute_bin

    return absolute

def make_binary_folder(main_name, prefix, addon):
    ''' Creates a folder for the acquisition in the binary data traces folder
    and returns the absolute path to the new folder.
    '''

    absolute = _BINARY_PATH_ + prefix + " - " + main_name + " - " + addon +  "/"
    os.mkdir(absolute)
    os.mkdir(absolute + "run parameters/")

    return absolute

def fit(y,dt,f):
    # Fit data to: y(t) = a cos(omega t) + b sin(omega t) + c
    #                   = A cos(phi) cos(omega t) + A sin(phi) sin(omega t) + c
    #                   = A cos(omega t - phi) + c
    # Fitting routine is simple fourier amplitude extraction
    # Input parameters are:
    # y - digitizer trace data
    # dt - time elapsed between each data point in SECONDS (we usually use 1us)
    # f - frequency of interest in HERTZ

    data_length = len(y)
    omega = 2.0*pi*f
    t = np.linspace(0,(data_length-1)*dt,data_length)

    a = 2.0*np.average(y*cos(omega*t))
    b = 2.0*np.average(y*sin(omega*t))
    c = np.average(y)

    A = np.sqrt(a**2 + b**2)
    phi = (np.arctan2(b,a) + 2.0*pi) % (2.0*pi)
        # arctan2(y,x) = tan^-1(y/x), returns values in the range (-pi,pi)
        # with the above definition, phi gets mapped to the interval (0,2*pi)

    # Returns: amplitude of the waveform A, phase phi, and DC offset c
    return np.float(A), np.float(phi), np.float(c)

def quench_arrays(quench_file):

    openq = [ind for ind in quench_file.index if quench_file.ix[ind]['Open']]
    on = [quench_file.ix[q]['Status'] for q in openq]
    on_qs = [q for q in openq if quench_file.ix[q]['Status'] == 'on']
    off = [q for q in openq if quench_file.ix[q]['Status'] == 'off']
    atten_vs = [quench_file.ix[q]['Attenuation Voltage'] for q in openq]

    return (openq, on, off, atten_vs, on_qs)

def formatted_quench_name(name):
    return name.replace('p','P').replace('q','Q').replace('_',' ')

def dbm_to_sqrtw(p_dbm):
    ''' Conversion function sqrt(W) to dBm.'''

    p_dbm = float(p_dbm)
    return np.sqrt( np.power( 10, (p_dbm - 30)/10 ) )

def sqrtw_to_dbm(p_sqrtw):
    ''' Conversion function dBm to sqrt(W).'''

    p_sqrtw = float(p_sqrtw)
    return 10.0 * np.log10( 1000.0 * np.power( p_sqrtw, 2 ) )

def make_comment_string(run_dict, rd_order):
    ''' Makes a comment string given a dictionary. Each line of the comment
    section will appear as:
    # index = value
    '''

    comment_string = '\n'.join(["# " + str(run_dict.index[rd_order[i]]) + \
                                " = " + \
                                str(run_dict.iloc[rd_order[i]]['Value']) \
                                for i in range(len(rd_order))])

    return comment_string + "\n"

def load_run_dictionary(filename, quenchfilename):
    ''' Creates a run dictionary by loading the files specified. Will return the
    run dictionary itself as well as a list with which to order the columns in
    the output txt file for the data set. Note that the column 'Experiment Name'
    must be present in all run dictionary csv files.
    '''

    #os.chdir(_DEFAULT_FILE_LOCATION_)

    # Makes sure everything is read in as a string
    rd = pd.read_csv(filename, dtype = str)
    props = rd.Property.values
    order = rd.Order.values
    order_list = [0 for i in range(len(order))]
    for i in range(len(order_list)):
        order_list[i] = props[int(order[i])]
    rd = rd.set_index('Property')['Value'].transpose().to_dict()

    qd = pd.read_csv(quenchfilename).set_index('Quench Name')

    for ind in qd.index:
        rd[ind] = dict(pd.Series(qd.loc[ind]))

    return rd, order_list
