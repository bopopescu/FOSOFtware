# -*- coding: utf-8 -*-
"""
Created on Mon May 15 12:01:36 2017

@author: travis
"""

from __future__ import division
import pandas as pd
import matplotlib.mlab as mlab
import numpy as np
import scipy.optimize as opt
import matplotlib.pyplot as plt
import os, sys
import scipy.optimize as scopt

#%matplotlib inline
#%config InlineBackend.figure_format = 'svg'

data_directory = "C:\\Google Drive\\data\\"
dataset_directory = data_directory + "180108-100304 - Waveguide calibration - BOTH waveguides 4MHz Scan 0config-PD_OFF\\"
data = pd.read_csv(dataset_directory + "data.txt", skiprows = 18)

print(data.columns)

#%%

# The chi-squared probability density function
def chi_squared_pdf(chisq, dof):
    if chisq > 0:
        return chisq**(dof/2-1)*np.exp(-chisq/2)/(2**(dof/2)*sp.special.gamma(dof/2))
    else:
        return 0

# Calculates the chi squared value of the function f compared to the data
# (anXArray, aYArray +/- errorsInYArray). The value functionDOF is the number
# of coefficients that were determined by the fit and hence the degrees of freedom
# for the fit that were removed by determining the best fit function.
def find_chi_squared_value(x_array, y_array, y_error, f, function_dof):
    return (1.0/float(len(x_array)-function_dof))*np.sum(((y_array - f(x_array))/y_error)**2)

# Function to calculate both chi squared and the probability of obtaining that chi squared
# This just minimizes function calls later in the code
def find_chi_squared_and_probability(x_array, y_array, y_error, f, function_dof):
    chisq = find_chi_squared_value(x_array, y_array,  y_error, f, function_dof)
    return chisq, chi_squared_probability(chisq, len(x_array) - function_dof)[0]

# Calculates the probability of obtaining the given chi squared with the number of
# degrees of freedom by numerically integrating the probability density function from
# chiSq to infinity
def chi_squared_probability(chisq, dof):
    return sp.integrate.quad(lambda chi_squared: chi_squared_pdf(chi_squared, dof), dof*chisq, np.inf)

#%%

def get_power_dbm(p, v):
    f = lambda x: abs(p(x)-v)
    soln = scopt.minimize_scalar(f,bounds=(-50.0,20.0),method='bounded')

    return soln['x']

vget_power_dbm = np.vectorize(get_power_dbm)
power_calib_dbm_column = 'RF power [dBm]'
power_calib_det_volt = 'Power detector signal [V]'
power_calib_det_volt_std = 'STD the mean of power detector signal [V]'

power_detector_calibration_data = pd.read_csv("C:\\Google Drive\code\\instrument control\\" + \
                                              "170822-130101 - RF power detector calibration/" + \
                                              "KRYTAR 109B power calibration.CSV")

poly, cov = np.polyfit(power_detector_calibration_data[power_calib_dbm_column],
                       power_detector_calibration_data[power_calib_det_volt], 7, \
                       w=1./power_detector_calibration_data[power_calib_det_volt_std]**2,
                       cov=True)
p = np.poly1d(poly)
errs = np.sqrt(np.abs(np.diag(cov)))

# plt.errorbar(power_detector_calibration_data[power_calib_dbm_column], \
#              power_detector_calibration_data[power_calib_det_volt],
#              xerr=power_detector_calibration_data[power_calib_det_volt_std],fmt='r.', \
#              label="m = "+str(round(p[1],4)) + "0+/-" + str(round(errs[0],4)))
# plt.plot(power_detector_calibration_data[power_calib_dbm_column],
#          p(power_detector_calibration_data[power_calib_dbm_column]))
# plt.xlabel("RF Power [dBm]")
# plt.ylabel("Power Detector Voltage [V]")
# plt.title("RF Power Detector Calibration")
# plt.show()

print(get_power_dbm(p,-0.5))

#%%

def dBm_to_watts(pdBm):
    return 10**(pdBm/10.0)/1000.0

def watts_to_dBm(pW):
    return 10.0 * np.log10(1000.0*pW)

def stdm(x):
    return np.std(x) / np.sqrt(len(x) - 1)

# print(max(data['Waveguide Power Setting [dBm]'])+44)
# print(get_power_dbm(p, min(data['Waveguide A Power Reading  (Generator On) [V]']))+40)

power_dbm_column = 'Waveguide Power Setting [dBm]'
frequency_column = 'Waveguide Frequency Setting [MHz]'
waveguide_to_analyze = 'B'
power_reading_column = 'Waveguide ' + waveguide_to_analyze + ' Power Reading (Generator On) [V]'
data = data.groupby("Generator Channel").get_group(waveguide_to_analyze)
on_off_column = 'Digitizer DC On/Off Ratio'

power_sqrtw_column = 'Waveguide Power Setting [sqrtW]'
detected_power_dbm_column = 'Detected Power (RF Generator ON) [dBm]'
detected_power_sqrtw_column = 'Detected Power (RF Generator ON) [sqrtW]'

# Convert power detector voltages into dBm
data[on_off_column] = data[on_off_column].values / max(data[on_off_column].values)
data[power_sqrtw_column] = np.sqrt(dBm_to_watts(data[power_dbm_column]))
data[detected_power_dbm_column] = np.array([get_power_dbm(p,data[power_reading_column].values[i])+30
                                            for i in range(len(data.index))])
data[detected_power_sqrtw_column] = np.sqrt(dBm_to_watts(data[detected_power_dbm_column]))

on_resonance = data.groupby(frequency_column).get_group(909.1)
on_resonance = on_resonance.groupby(power_dbm_column).agg([np.mean,stdm])

# plt.title("Measured Power vs Set Power")
# plt.xlabel("Set Power [dBm]")
# plt.ylabel("Measured Power [W]")
# plt.errorbar(on_resonance.index, \
#             on_resonance[detected_power_dbm_column]['mean'].values-30, \
#             fmt='b.', \
#             yerr = on_resonance[detected_power_dbm_column]['stdm'].values)
# plt.show()

#%%

# Plot fractional population vs measured power (in dBm) for a given carrier frequency
frequencies = data[frequency_column].unique()
print(np.sort(frequencies))
frequency_separated_data = data.groupby(frequency_column)
for frequency in np.sort(frequencies):
    a_frequency = frequency_separated_data.get_group(frequency)

    a_frequency_by_power = a_frequency.reset_index().groupby(power_dbm_column).agg([np.mean,stdm])
    set_power = a_frequency[power_dbm_column].unique()

    #fit = np.polyfit(a_frequency_by_power['Detected Power (RF Generator ON) [sqrtW]']['mean'].values, \
    #                 a_frequency_by_power['ON/OFF ratio']['mean'].values, 1, \
    #                 w = 1.0/a_frequency_by_power['ON/OFF ratio']['stdm'].values**2)
    #
    #poly = np.poly1d(fit)

    # plt.figure(figsize=[15,15])
    # plt.title(str(frequency) + "MHz Waveguide Quench")
    # plt.ylabel("Fractional Population Remaining")
    # plt.xlabel("Detected RF Power [sqrtW]")
    #plt.plot(a_frequency_by_power['Detected Power (RF Generator ON) [sqrtW]']['mean'].values, \
    #         poly(a_frequency_by_power['Detected Power (RF Generator ON) [sqrtW]']['mean'].values))
    # plt.errorbar(a_frequency_by_power[power_sqrtw_column]['mean'].values, \
    #              a_frequency_by_power[on_off_column]['mean'].values,fmt='b.', \
    #              yerr=a_frequency_by_power[on_off_column]['stdm'].values, \
    #              xerr=a_frequency_by_power[power_sqrtw_column]['stdm'].values)
    #plt.show()

    print(p[1],p[0])

print(dBm_to_watts(p(2.11)+40))
print(dBm_to_watts(p(.7)+40))
print(p(0.7)-p(2.11))
print(min(a_frequency_by_power[on_off_column]['mean'].values))

#%%

# Fit the simulated quench file to a polynomial of order n
#sim_file = pd.read_csv("C:\\Users\\Travis\\Google Drive\\Travis Code\\Simulations\\Waveguide Calibration\\OUTPUT910.0MHZ.DAT", delim_whitespace = True)
sim_file = pd.read_csv("C:\\Google Drive\\code\\instrument control\\Waveguide Calibration\\OUTPUT910.0MHZ.DAT", delim_whitespace = True)

n = 8
sim_poly = np.polyfit(sim_file['EFIELD'],sim_file['PRBF=0']/max(sim_file['PRBF=0']), n)
sim_p = np.poly1d(sim_poly)

# plt.title("Fractional Population\nvs.\nElectric Field Magnitude\n(Simulated)")
# plt.xlabel("Electric Field Magnitude [V/cm]")
# plt.ylabel("Fractional Population")
# plt.plot(sim_file['EFIELD'],sim_file['PRBF=0']/max(sim_file['PRBF=0']),'r.')
# plt.plot(sim_file['EFIELD'],sim_p(sim_file['EFIELD']),'g-')
#plt.show()

#%%

def efield_to_sqrtw(p, x):
    a = p[0]
    b = p[1]
    c = p[2]
    return a/(x+b)**2 + c

def efield_to_sqrtw_err(p, x, y):
    return efield_to_sqrtw(p, x) - y

function_table = pd.DataFrame()
calib_p = [None for j in range(len(frequencies))]
conv_function = [None for j in range(len(frequencies))]
k = 0

for frequency in np.sort(frequencies):
    # Fit the simulated quench file to a polynomial of order n
    #print("C:\\Users\\Travis\\Google Drive\\Travis Code\\Simulations\\OUTPUT" + str(round(frequency,1)) +"MHZ.DAT")
    #print("C:\\Users\\Travis\\Google Drive\\Travis Code\\Simulations\\OUTPUT" + str(round(frequency,1)) +"MHZ.DAT")
    #sim_file = pd.read_csv("C:\Google Drive\code\instrument control\Waveguide Calibration\\OUTPUT" + str(round(frequency,1)) +"MHZ.DAT", \
    #                       delim_whitespace = True)
                           
    sim_file = pd.read_csv("C:\\Google Drive\code\\instrument control\\Waveguide Calibration\\OUTPUT" + str(round(frequency,1)) +"MHZ.DAT", \
                           delim_whitespace = True)

    # Obtain the proper simulation file and fit the simulation data to an 8th order polynomial
    n = 12
    sim_poly = np.polyfit(sim_file['EFIELD'],sim_file['PRBF=0']/max(sim_file['PRBF=0']), n)
    sim_p = np.poly1d(sim_poly)

    # plt.figure(figsize=[15,15])
    # # Plot the simulation and the fit
    # plt.title("Simulated Fractional Population vs. Electric Field\nfor "+str(frequency)+" MHz")
    # plt.ylabel("DC ON/OFF Ratio (Fractional Population)")
    # plt.xlabel("Electric Field Amplitude $\\left[ V/cm \\right]$")
    # efields = np.linspace(-1,100,1000)
    # plt.plot(sim_file['EFIELD'],sim_file['PRBF=0']/max(sim_file['PRBF=0']),'r.')
    # plt.plot(efields, sim_p(efields))
    # plt.show()

    # Get the data for the current carrier frequency from the data file
    a_frequency = frequency_separated_data.get_group(frequency)
    a_frequency = a_frequency.groupby(power_sqrtw_column).agg([np.mean, stdm])[[detected_power_sqrtw_column,on_off_column]]

    nprime = 6
    # Fit the experimental data for on/off ratio (fractional population) vs. sqrt(power) [sqrt(W)]
    measured_poly = np.polyfit(a_frequency[detected_power_sqrtw_column]['mean'], a_frequency[on_off_column]['mean'], nprime)#, \
                               #w = 1.0/a_frequency['ON/OFF ratio']['stdm']**2)
    measured_p = np.poly1d(measured_poly)
    pows = np.linspace(min(a_frequency[detected_power_sqrtw_column]['mean']), \
                       max(a_frequency[detected_power_sqrtw_column]['mean']),100)

    # plt.figure(figsize=[15,15])
    # # Plot the fit against the data
    # plt.title("Measured Fractional Population vs Sqrt(Set RF Power)\nfor "+str(frequency)+" MHz")
    # plt.ylabel("DC ON/OFF Ratio (Fractional Population)")
    # plt.xlabel("$\sqrt{\\mathrm{Power}}\\ \\left[ \\sqrt{W} \\right]$")
    # plt.plot(pows, measured_p(pows))
    # plt.errorbar(a_frequency[detected_power_sqrtw_column]['mean'], a_frequency[on_off_column]['mean'].values, \
    #              yerr = a_frequency[on_off_column]['stdm'].values, fmt = 'r.')
    # plt.show()

    # data_shifted = a_frequency['ON/OFF ratio']['mean'].values - min(a_frequency['ON/OFF ratio']['mean'].values)
    # data_shifted = data_shifted/max(data_shifted)*max(a_frequency['ON/OFF ratio']['mean'].values)
    #
    # # Fit the shifted data for on/off ratio (fractional population) vs. sqrt(power) [sqrt(W)]
    # poly_shifted = np.polyfit(a_frequency['Detected Power (RF Generator ON) [sqrtW]']['mean'], data_shifted, nprime, \
    #                           w = 1.0/a_frequency['ON/OFF ratio']['stdm']**2)
    # p_shifted = np.poly1d(poly_shifted)
    #
    # plt.figure(figsize=[15,15])
    # # Plot the fit against the data
    # plt.title("Measured and Shifted/Normalized\nFractional Population vs Sqrt(Set RF Power)\nfor "+str(frequency)+" MHz")
    # plt.ylabel("DC ON/OFF Ratio (Fractional Population)")
    # plt.xlabel("$\sqrt{\\mathrm{Power}}\\ \\left[ \\sqrt{W} \\right]$")
    # plt.plot(a_frequency['Detected Power (RF Generator ON) [sqrtW]']['mean'], data_shifted, 'r.', label = "Shifted Data")
    # plt.plot(a_frequency['Detected Power (RF Generator ON) [sqrtW]']['mean'], a_frequency['ON/OFF ratio']['mean'].values, 'b.', label = "Acquired Data")
    # plt.legend()
    # plt.show()

    # Convert the sqrt(W) to volts per cm in the following way:
    # 1) Find a point on the measured data on/off ratio
    # 2) Match its value to a fractional population value from the simulation
    # 3) Find the electric field that yields the given fractional population
    volts_per_cm = opt.fsolve(lambda x: sim_p(x) - measured_p(a_frequency[detected_power_sqrtw_column]['mean']), \
                              [10.0 for j in range(len(a_frequency.index))])

    a_frequency['Electric Field [V/cm]'] = volts_per_cm

    # shifted_v_cm = opt.fsolve(lambda x: sim_p(x) - p_shifted(a_frequency['Detected Power (RF Generator ON) [sqrtW]']['mean']), \
    #                           [10.0 for j in range(len(a_frequency.index))])
    #
    # a_frequency['Electric Field (Shifted) [V/cm]'] = shifted_v_cm

    # Points to disregard: any data after the amplifier appears to be saturated
    # will cause problems with the fit. If this fit doesn't work the first time,
    # look for saturation, remove some of the saturated points and try again.
    points_to_disregard = 1

    # plt.figure(figsize=[15,15])
    # plt.title("Measured Data @ Calibrated Electric Field vs.\nSimulation Data")
    # plt.xlabel("Electric Field [V/cm]")
    # plt.ylabel("Fractional Population")
    # plt.plot(sim_file['EFIELD'],sim_file['PRBF=0']/max(sim_file['PRBF=0']),'r.')
    # plt.plot(a_frequency['Electric Field [V/cm]'].values[:-max(1,points_to_disregard)], a_frequency[on_off_column]['mean'].values[:-max(1,points_to_disregard)], 'b.')
    # plt.show()

    # plt.figure(figsize=[15,15])
    # plt.title("Shifted Data @ Calibrated Electric Field vs.\nSimulation Data")
    # plt.xlabel("Electric Field [V/cm]")
    # plt.ylabel("Fractional Population")
    # plt.plot(sim_file['EFIELD'],sim_file['PRBF=0']/max(sim_file['PRBF=0']),'r.')
    # plt.plot(a_frequency['Electric Field (Shifted) [V/cm]'].values[:-max(1,points_to_disregard)], data_shifted[:-max(1,points_to_disregard)], 'b.')
    # plt.show()

    calib_poly, cov = np.polyfit(a_frequency['Electric Field [V/cm]'].values[:-max(1,points_to_disregard)], a_frequency.index[:-max(1,points_to_disregard)], 5, cov = True)
    calib_p = np.poly1d(calib_poly)
    errs = np.sqrt(np.diag(cov))
    power_range = np.linspace(min(a_frequency['Electric Field [V/cm]'].values[:-max(1,points_to_disregard)]), \
                              max(a_frequency['Electric Field [V/cm]'].values[:-max(1,points_to_disregard)]), 1000)

    plt.figure(figsize=[15,15])
    plt.title("Electric Field vs Sqrt(Set Power)\nfor " + str(frequency) + "MHz")
    plt.xlabel("Electric Field [V/cm]")
    plt.ylabel("$\sqrt{\\mathrm{Power}}\\ \\left[ \\sqrt{W} \\right]$")
    plt.plot(power_range, calib_p(power_range), label = "Fit")
    plt.plot(a_frequency['Electric Field [V/cm]'].values[:-max(1,points_to_disregard)], a_frequency.index[:-max(1,points_to_disregard)], 'r.')
    plt.legend()
    plt.show()

    conv_function = lambda x: watts_to_dBm((calib_p(x)**2.0))

    new_series = pd.Series([frequency, False, conv_function(5.0), conv_function(6.0), conv_function(7.0), conv_function(8.0), conv_function(9.0), \
                            conv_function(10.0), conv_function(11.0), conv_function(12.0), conv_function(13.0), conv_function(14.0), \
                            conv_function(15.0), conv_function(16.0), conv_function(17.0), conv_function(18.0), conv_function(19.0), \
                            conv_function(20.0), conv_function(21.0), conv_function(22.0), conv_function(23.0), conv_function(24.0), \
                            conv_function(25.0), conv_function(26.0), conv_function(27.0), conv_function(28.0), conv_function(29.0), \
                            conv_function(30.0)])
    function_table = function_table.append(new_series, ignore_index = True)

    # calib_poly, cov = np.polyfit(a_frequency['Electric Field (Shifted) [V/cm]'].values[:-max(1,points_to_disregard)], a_frequency.index[:-max(1,points_to_disregard)], 5, cov = True)
    # calib_p = np.poly1d(calib_poly)
    # errs = np.sqrt(np.diag(cov))
    # power_range = np.linspace(min(a_frequency['Electric Field (Shifted) [V/cm]'].values[:-max(1,points_to_disregard)]), \
    #                           max(a_frequency['Electric Field (Shifted) [V/cm]'].values[:-max(1,points_to_disregard)]), 1000)
    #
    # plt.figure(figsize=[15,15])
    # plt.title("Electric Field (Shifted and Unshifted) vs Sqrt(Set Power)\nfor " + str(frequency) + "MHz")
    # plt.xlabel("Electric Field [V/cm]")
    # plt.ylabel("$\sqrt{\\mathrm{Power}}\\ \\left[ \\sqrt{W} \\right]$")
    # plt.plot(power_range, calib_p(power_range), label = "Fit")
    # plt.plot(a_frequency['Electric Field (Shifted) [V/cm]'].values[:-max(1,points_to_disregard)], a_frequency.index[:-max(1,points_to_disregard)], 'r.', label = "Shifted Data")
    # plt.plot(a_frequency['Electric Field [V/cm]'].values[:-max(1,points_to_disregard)], a_frequency.index[:-max(1,points_to_disregard)], 'r.', label = "Measured Data")
    # plt.legend()
    # plt.show()
    #
    # conv_function = lambda x: watts_to_dBm((calib_p(x)**2.0))
    #
    # new_series = pd.Series([frequency, True, conv_function(5.0), conv_function(6.0), conv_function(7.0), conv_function(8.0), conv_function(9.0), \
    #                         conv_function(10.0), conv_function(11.0), conv_function(12.0), conv_function(13.0), conv_function(14.0), \
    #                         conv_function(15.0), conv_function(16.0), conv_function(17.0), conv_function(18.0), conv_function(19.0), \
    #                         conv_function(20.0), conv_function(21.0), conv_function(22.0), conv_function(23.0), conv_function(24.0), \
    #                         conv_function(25.0), conv_function(26.0), conv_function(27.0), conv_function(28.0), conv_function(29.0), \
    #                         conv_function(30.0)])
    # function_table = function_table.append(new_series, ignore_index = True)

function_table.columns = ["Carrier Frequency [MHz]", "Shifted?", "5.0 V/cm", "6.0 V/cm", "7.0 V/cm", "8.0 V/cm", "9.0 V/cm", \
                          "10.0 V/cm", "11.0 V/cm", "12.0 V/cm", "13.0 V/cm", "14.0 V/cm", "15.0 V/cm", "16.0 V/cm", "17.0 V/cm", \
                          "18.0 V/cm", "19.0 V/cm", "20.0 V/cm", "21.0 V/cm", "22.0 V/cm", "23.0 V/cm", "24.0 V/cm", "25.0 V/cm", \
                          "26.0 V/cm", "27.0 V/cm", "28.0 V/cm", "29.0 V/cm", "30.0 V/cm"]

function_table = function_table.set_index('Shifted?')

#%%

print(function_table.columns)
function_table = function_table.loc[False].reset_index().set_index('Carrier Frequency [MHz]')#.drop('index',axis=1)
print(function_table.index)
print(function_table.values)

#%%

output_directory = "C:\\Google Drive\\code\\instrument control\\medium\\"
for col in function_table.columns:
    this_efield = function_table[col].copy()
    filename = "Waveguide_" + waveguide_to_analyze + " E="+col[:col.find(".")]

    this_efield.to_csv(output_directory+filename+".txt",sep="\t", header=["RF generator power [dBm]"], \
                                        index_label="Frequency [MHz]")
