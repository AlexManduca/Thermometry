#!/usr/bin/env python
# coding: utf-8

# # Cold Thermometry Readout

# Import statements

# In[2]:


import os
import sys
import csv
import numpy as np
import pandas as pd
from labjack import ljm
from datetime import date, datetime
import plotly.express as px


#  

# Open up labjack

# In[ ]:


# open first found LabJack and call it handle
handle = ljm.openS("ANY", "ANY", "ANY")  # Any device, Any connection, Any identifier

# grab and print out important info 
info = ljm.getHandleInfo(handle)
print("Opened a LabJack with Device type: %i, Connection type: %i,\n"
      "Serial number: %i, IP address: %s, Port: %i,\nMax bytes per MB: %i" %
      (info[0], info[1], info[2], ljm.numberToIP(info[3]), info[4], info[5]))


#  

# Configure the following parameters:
# * bias
# * voltage divider resistance
# * gain
# * analog input channels
# * sample rate with user input

# In[3]:


# bias config
try:
    bias = float(input("Enter the peak-to-peak amplitude of your bias (in V):  \n"))
except Exception:
    print(sys.exc_info()[1])
    raise

# constant resistor config, should be 10Mohms
r_constant = 1e8

# gain, set by preamp board
gain = 160*0.4

# current, in Amps
I = bias / r_constant

# resistance to temperature config
scriptDir = os.path.dirname(os.path.realpath("__file__"))
file = scriptDir + os.path.sep + "temp_and_res_lists.csv"
temp_list, res_list = np.loadtxt(file, delimiter = ",", skiprows = 0, usecols = (0, 1), unpack = True)

# set range, resolution, and settling time for channels
# note:
#   Negative channel: single ended = 199, differential = 1
#   Range: The instrumentation amplifier in the T7 provides 4 different gains:
#         x1 (RANGE is ±10 volts), enter 10.0
#         x10 (RANGE is ±1 volts), enter 1.0
#         x100 (RANGE is ±0.1 volts), enter 0.1
#         x1000 (RANGE is ±0.01 volts), enter 0.01
#   Resolution index = Default (0)
#   Settling, in microseconds = Auto (0) resource on settling times: https://old3.labjack.com/support/app-notes/SettlingTime
setup_names = ["AIN_ALL_NEGATIVE_CH", "AIN_ALL_RANGE","STREAM_RESOLUTION_INDEX","STREAM_SETTLING_US"]
setup_values = [199,10.0,0,0]

# AIN channel setup
channels_to_read = input("Which channels would you like to read?\nIf you want to read all channels, type 'all'\notherwise, list the channels you'd like read out in the following format: 48,56,49,57\n")

try:
    if channels_to_read == 'all':

        # analog input channels to be read out
        positive_channels = np.append(np.append(np.arange(48,56), np.arange(80,88)), np.arange(96,104))
        negative_channels = np.append(np.append(np.arange(56,64), np.arange(88,96)), np.arange(104,112))
        channel_numbers = [item for sublist in zip(positive_channels, negative_channels) for item in sublist]

        channel_names = []
        for c in channel_numbers: channel_names = channel_names+["AIN%d"%c]
        print(channel_names)
    else:
        channel_names = []
        for i in channels_to_read.split(","):
            i = "AIN"+i
            channel_names.append(i)
        print(channel_names)
except Exception:
    print(sys.exc_info()[1])
    raise
    
# assign the values of range, resolution, and settling to each channel
ljm.eWriteNames(handle, len(setup_names), setup_names, setup_values)

# list of channels to scan
scan_list = ljm.namesToAddresses(len(channel_names), channel_names)[0]

# set scan rate, in Hz
print("\nThe T7 max sample rate is 100 ksamples/second. This is achievable for any single-address stream, but for a multi-address stream this is only true when resolution index = 0 or 1 and when range = +/-10V for all analog inputs.")
max_sample_rate = 100000 / len(channel_names)

print("\nGiven your inputs, the maximum sample rate, per channel, is " + str(max_sample_rate) + " samples / second")

sample_rate = float(input("\nEnter your desired sample rate, per channel, in Hz\ne.g. I want to sample each channel x number of times per second\n(Note: for the sake of avoiding stream overlaps, it is best to sample slower than your maximum sample rate)\n"))

# scan_amount determines how many readout loops the labjack will perform 
try:
    scan_amount = input("Enter the number of times you would like the labjack to stream data at a rate of %f Hz from each channel, i.e. enter desired number of scans\n(type either an integer or the word 'infinite'):\n" %sample_rate)
    if scan_amount != "infinite": scan_amount = int(scan_amount)
except Exception:
    print(sys.exc_info()[1])
    raise

# print to see if channels were set up properly
print("\nSet configuration:")
print("    Bias amplitude: %sV" %bias)
print("    Sample rate: %sHz" %sample_rate)
print("    Number of scans to be performed on each channel: %s" %scan_amount)
for i in range(len(setup_names)):
    print("    %s : %f" % (setup_names[i], setup_values[i]))


#  

# Collect and save data

# In[54]:


print("Note: Stream data is transferred as 16-bit values")

# assign the values of range, resolution, and settling to each channel
ljm.eWriteNames(handle, len(setup_names), setup_names, setup_values)

dictionary = {}
for n in channel_names:
    dictionary[n] = {"V [V]":[],"R [komhs]":[],"Temp [mK]":[],"Time":[]}

try:
    # Configure and start stream
    sample_rate = ljm.eStreamStart(handle, int(sample_rate), len(channel_names), scan_list, sample_rate)
    print("\nStream started with a sample rate of %0.0f Hz." % sample_rate)

    # just a little message
    loop_message = " Press Ctrl+C to stop."
    print("\nStarting %s read loops.%s\n" % (str(scan_amount), loop_message))
    
    # start timer
    start = datetime.now()
    total_scans = 0
    total_skipped_samples = 0 # Total skipped samples

    i = 1
    while i <= scan_amount:
        v_measured = ljm.eStreamRead(handle)[0]
        time = datetime.now().strftime("%Y/%m/%d, %H:%M:%S")
        
        for i in range(len(channel_names)):
            dictionary[channel_names[i]]["V [V]"].append(v_measured[i])
            dictionary[channel_names[i]]["Time"].append(time[i])

        scans = len(v_measured)/len(channel_names)
        total_scans += scans
        
        # Count the skipped samples which are indicated by -9999 values. Missed
        # samples occur after a device's stream buffer overflows and are
        # reported after auto-recover mode ends.
        total_skipped_samples += data.count(-9999.0)
        
        print("\neStreamRead %i" % i)
        ain_string = ""
        for j in range(0, numAddresses):
            ain_string += "%s = %0.5f " % (channel_names[j], v_measured[j])
        print("  1st scan out of %i: %s" % (scans, ain_string))
        i += 1
    
    end = datetime.now()

    print("\nTotal scans = %i" % (total_scans))
    time_taken = (end-start).seconds + float((end-start).microseconds)/1000000
    print("Time taken = %f seconds" % (time_taken))
    print("Timed scan rate = %f scans/second" % (total_scans/time_taken))
    print("Timed sample rate = %f samples/second" % ((total_scans*len(channel_names))/time_taken))
    print("Skipped samples = %0.0f" % (total_skipped_samples/len(channel_names)))
except ljm.LJMError:
    ljme = sys.exc_info()[1]
    print(ljme)
except Exception:
    e = sys.exc_info()[1]
    print(e)

print("\nStop Stream")
ljm.eStreamStop(handle)

# Close handle
ljm.close(handle)


#  

# Save raw and averaged data to files

# In[ ]:


for n in channel_names:
    j = 0
    r_var = []
    for i in range(int(scan_rate)):
        r_var.append(((dictionary[n]['V [V]'][i] / 0.3535) / gain) / I)
        dictionary[n]["R [komhs]"][i].append(r_var[i])
        temp = 1000*np.interp(dictionary[n]["R [komhs]"][i],res_list,temp_list)
        dictionary[n]["Temp [mK]"][i].append(temp)
        j+=1
        if j == int(scan_rate): j = 0

# csv data files
if os.path.exists('data/%s_data' %(datetime.now().strftime("%Y-%m-%d"))) == False:
    os.mkdir('data/%s_data' %(datetime.now().strftime("%Y-%m-%d")))

files = []
for i in range(len(channel_names)):
    files.append('data/%s_data' %(datetime.now().strftime("%Y-%m-%d")) + "/thermometer_%s" %channel_names[i])

for n in files:
    df = pd.DataFrame(dictionary[n[33:]])
    df.to_csv(n, index = False)
    
# averaged data
averaged_dictionary = {}
for n in channel_names:
    averaged_dictionary[n] = {"V [V]":[],"R [komhs]":[],"Temp [mK]":[],"Time":[]}

for n in channel_names:
    i = 0
    while i < len(dictionary[n]['V [V]']):
        averaged_dictionary[n]['V [V]'].append(sum(dictionary[n]['V [V]'][i:sample_rate])/sample_rate)
        averaged_dictionary[n]['R [komhs]'].append(sum(dictionary[n]['R [komhs]'][i:sample_rate])/sample_rate)
        averaged_dictionary[n]['Temp [mK]'].append(sum(dictionary[n]['Temp [mK]'][i:sample_rate])/sample_rate)
        averaged_dictionary[n]['Time'].append(dictionary[n]['Time'][0])
        i += sample_rate
        
# averaged csv data files
if os.path.exists('averaged_data/averaged_%s_data' %(datetime.now().strftime("%Y-%m-%d"))) == False:
    os.mkdir('averaged_data/averaged_%s_data' %(datetime.now().strftime("%Y-%m-%d")))

files = []
for i in range(len(channel_names)):
    files.append('averaged_data/averaged_%s_data' %(datetime.now().strftime("%Y-%m-%d")) + "/thermometer_%s" %channel_names[i])

for n in files:
    df = pd.DataFrame(averaged_dictionary[n[33:]])
    df.to_csv(n, index = False)


#  

# Read data from file and plot

# In[ ]:


df = pd.read_csv(files[0])
df.head()


# In[ ]:


figK = px.line(df, x = 'Time', y = 'Temp [K]', title='Temperature [K] over time')
figK.show()

