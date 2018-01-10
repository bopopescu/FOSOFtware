from Tkinter import *
import sys
sys.path.insert(0,'Y:/analyzed_data/valdez/instrument control modules/')
import threading as th
import multiprocessing as mp
import ttk
import tkFileDialog as tkfd
import subprocess as sp
import time
import input_output as ioput
import fosof_qol as qol
import os
import shutil
import pandas as pd
import phasemonitor

try:
    from Queue import Queue, Empty
except ImportError:
    from queue import Queue, Empty

class Manager(object):

    def __init__(self):
        # Queues for communication with input, output windows. The queuein
        # queues are for the terminal windows to send and the main thread to
        # receive. The queueout queues are for the main thread to send and the
        # windows to receive.
        self.terminal_out_queuein = Queue()
        self.terminal_err_queuein = Queue()
        self.terminal_in_queuein = Queue()
        self.terminal_out_queueout = Queue()
        self.terminal_err_queueout = Queue()
        self.terminal_in_queueout = Queue()

        # For communication with the runscheduler window. The run scheduler will
        # be asked for the next file/files in line, and will send them.
        self.rs_queuein = Queue()
        self.rs_queueout = Queue()

        # Queues for communication with the current acquisition. The mp Queue is
        # very similar to the regular queue, but it can be used with a
        # multiprocessing Process object.
        self.acq_in = mp.Queue()
        self.acq_out = mp.Queue()
        self.acq_err = mp.Queue()

        self.phase_in = mp.Queue()
        self.phase_out = mp.Queue()
        self.phase_err = mp.Queue()

        # Variables that determine what to do next
        self.state = 'STANDBY'
        self.last_state = 'STARTUP'

        # Acquisition variables
        self.phase_proc = None
        self.p = None
        self.datafolder = None
        self.phasefolder = None
        self.ask_run_dict = True

        # Run queue location
        self.file_location = qol.path_file['Run Queue']
        self.user_input_file = self.file_location + 'userinput.txt'
        self.user_input_alternate = self.file_location + 'temp.txt'
        self.default_phase_file = 'phase_monitor_DEFAULT.rd'

        self.run_main_loop()

    def run_main_loop(self):
        ''' The main decision-making loop for this manager program. This method
        sets in motion all of the acquisitions and manages the run dictionaries
        before and after the acquisitions take place.
        '''

        # Start the user input/output windows.
        self.t = th.Thread(target=ioput.run_iotk, \
                           args=(self.terminal_in_queuein, \
                                 self.terminal_in_queueout, \
                                 self.terminal_out_queuein, \
                                 self.terminal_out_queueout, \
                                 self.terminal_err_queuein, \
                                 self.terminal_err_queueout, \
                                 self.rs_queuein,
                                 self.rs_queueout))
        self.t.daemon = True # Thread will be terminated if main process quits
        self.t.start()

        self.run_result = None # Logs the success/failure of the last run

        while self.state != 'DONE':

            # Current and last state determine the course of action
            s = self.state
            ls = self.last_state

            # The starting state of the manager
            if s == 'PHASE' and ls == 'STARTUP':
                # Create a makeshift run dictionary item. Similar to those
                # passed by input_output.py
                self.rd = {}
                self.rd['Script File'] = 'phasemonitor.py'
                self.rd['Script File Location'] = qol.path_file['Code']
                self.rd['.rd File Location'] = self.file_location + \
                                                  self.default_phase_file
                self.rd['Run Dictionary'] = pd.read_csv(self.rd['.rd File' + \
                                                                ' Location']
                                                       )
                self.run_result = self.run_acq(run_dictionary = self.rd, \
                                               startup = True)
            elif s == 'STANDBY' and ls == 'STARTUP':
                self.phase_rd = None
                self.phasefolder = None
                self.rd = None

                self.run_acq()
            # If an acquisition has just finished/ended without an error during
            # startup
            elif s == 'PHASE' and ls == 'ACQUISITION' and self.run_result:
                self.terminal_in_queueout.put('acq ended')
                self.copyfiles(self.rd, self.file_location, self.datafolder, \
                               'data')
                shutil.move(self.user_input_alternate, self.user_input_file)
                self.terminal_in_queueout.put('acq resumed')

                # Reset acquisition variables
                self.datafolder = None
                self.rd = self.phase_rd # Make sure current run dict is phase
                self.acq_in = self.clear_queue(self.acq_in)
                self.acq_out = self.clear_queue(self.acq_out)
                self.acq_err = self.clear_queue(self.acq_err)

                self.run_acq()

            # If an acquisition has just finished/ended before completing
            # startup
            elif s == 'PHASE' and ls == 'ACQUISITION' and not self.run_result:
                self.terminal_err_queueout.put('Problem with the file ' + \
                                               self.rd['.rd File Location'] + \
                                               ' and the script ' + \
                                               self.rd['Script File'])

                self.terminal_err_queueout.put('Reverting back to phase ' + \
                                               ' monitor.')

                self.terminal_in_queueout.put('acq ended')
                self.copyfiles(self.rd, self.file_location, self.datafolder, \
                               'data')
                shutil.move(self.user_input_alternate, self.user_input_file)
                self.terminal_in_queueout.put('acq resumed')

                # Reset acquisition variables
                self.datafolder = None
                self.rd = self.phase_rd # Make sure current run dict is phase
                self.acq_in = self.clear_queue(self.acq_in)
                self.acq_out = self.clear_queue(self.acq_out)
                self.acq_err = self.clear_queue(self.acq_err)

                self.run_acq()

            # After ending the phase monitor and re-starting it. This combo of
            # state and last state may never actually happen...
            elif s == 'PHASE' and ls == 'STANDBY':
                self.rd = self.next_run_dictionary
                self.terminal_in_queueout.put('new acq')
                self.run_result = self.run_acq(run_dictionary = self.rd, \
                                               startup = True)

            # Beginning an acquisition from the phase monitor state. Note that
            # the ACQUISITION state may just be a new phase monitor (with a
            # change of parameters, etc.).
            elif s == 'ACQUISITION' and ls == 'PHASE':

                # If the new process is another phase monitor, end the old
                # phase monitor process and clear its queues/variables
                if self.next_run_dictionary['Script File'] == 'phasemonitor.py':
                    self.end_acq(self.phase_out, self.phase_in, \
                                 self.phase_err, self.phase_proc, now = True)
                    self.state = 'PHASE'

                    # Copy the run dictionary and out/error files to the new
                    # folder
                    self.terminal_in_queueout.put('acq ended')
                    self.copyfiles(self.rd, self.file_location, \
                                   self.phasefolder, 'phase')
                    self.terminal_in_queueout.put('new acq')

                    # Reset variables
                    self.phasefolder = None
                    self.phase_in = self.clear_queue(self.phase_in)
                    self.phase_out = self.clear_queue(self.phase_out)
                    self.phase_err = self.clear_queue(self.phase_err)

                # If the new acquisition is not a phase monitor, pause the
                # current phase monitor and store the phase run dictionary in
                # a separate variable.
                else:
                    self.phase_out.put("pause")
                    check = self.wait_for_signal('manager:paused',
                                                 self.phase_in,
                                                 self.terminal_out_queueout,
                                                 120.0,
                                                 check_keywds = True)
                    self.phase_rd = self.rd
                    self.terminal_in_queueout.put('acq ended')
                    shutil.move(self.user_input_file,self.user_input_alternate)
                    self.terminal_in_queueout.put('new acq')

                # Set the run dictionary to the new rd and start the script.
                self.rd = self.next_run_dictionary
                self.run_result = self.run_acq(run_dictionary = self.rd, \
                                               startup = True)

            # Here, a new acquisition is started from a "do nothing" state.
            elif s == 'ACQUISITION' and ls == 'STANDBY':

                # Change the state if the new acquisition is a phase monitor
                if self.next_run_dictionary['Script File'] == 'phasemonitor.py':
                    self.state = 'PHASE'

                # Begin the acquisition
                self.rd = self.next_run_dictionary
                self.terminal_in_queueout.put('new acq')
                self.run_result = self.run_acq(run_dictionary = self.rd, \
                                               startup = True)

            # If a phasemonitor process has just ended.
            elif s == 'STANDBY' and ls == 'PHASE':

                # Copy script file and output/error files to the new folder.
                self.terminal_in_queueout.put('acq ended')
                self.copyfiles(self.rd, self.file_location, self.phasefolder, \
                               'phase')

                # Reset variables
                self.phase_rd = None
                self.phasefolder = None
                self.phase_in = self.clear_queue(self.phase_in)
                self.phase_out = self.clear_queue(self.phase_out)
                self.phase_err = self.clear_queue(self.phase_err)
                self.rd = None

                self.run_acq()

            # If an acquisition has ended after startup is complete
            elif s == 'STANDBY' and ls == 'ACQUISITION' and self.run_result:

                self.terminal_in_queueout.put('acq ended')
                self.copyfiles(self.rd, self.file_location, self.datafolder, \
                               'data')

                # Reset variables
                self.rd = None
                self.datafolder = None
                self.acq_in = self.clear_queue(self.acq_in)
                self.acq_out = self.clear_queue(self.acq_out)
                self.acq_err = self.clear_queue(self.acq_err)

                self.run_acq()

            # If an acquisition has ended before startup is complete
            elif s == 'STANDBY' and ls == 'ACQUISITION' and not self.run_result:

                self.terminal_in_queueout.put('acq ended')
                self.copyfiles(self.rd, self.file_location, self.datafolder, \
                               'data')

                self.rd = None
                self.datafolder = None
                self.acq_in = self.clear_queue(self.acq_in)
                self.acq_out = self.clear_queue(self.acq_out)
                self.acq_err = self.clear_queue(self.acq_err)

                self.run_acq()

            # If the user has asked everything to end during an acquisition
            elif s == 'END' and ls == 'ACQUISITION':
                self.terminal_in_queueout.put('acq ended')
                if self.phasefolder:
                    shutil.move(self.user_input_file, \
                                qol.path_file['Run Queue'] + 'ui.txt')
                    shutil.move(self.user_input_alternate, self.user_input_file)
                    self.copyfiles(self.phase_rd, self.file_location, \
                                   self.phasefolder, 'phase')
                    self.phase_in = self.clear_queue(self.phase_in)
                    self.phase_out = self.clear_queue(self.phase_out)
                    self.phase_err = self.clear_queue(self.phase_err)

                shutil.move(qol.path_file['Run Queue'] + 'ui.txt', \
                            self.user_input_file)
                self.copyfiles(self.rd, self.file_location, self.datafolder, \
                               'data')
                self.acq_in = self.clear_queue(self.acq_in)
                self.acq_out = self.clear_queue(self.acq_out)
                self.acq_err = self.clear_queue(self.acq_err)

                self.state = 'DONE'

            # If the user has asked everything to end during a phasemonitor
            # state
            elif s == 'END' and ls == 'PHASE':
                self.terminal_in_queueout.put('acq ended')
                self.copyfiles(self.rd, self.file_location, self.phasefolder, \
                               'phase')
                self.phase_in = self.clear_queue(self.phase_in)
                self.phase_out = self.clear_queue(self.phase_out)
                self.phase_err = self.clear_queue(self.phase_err)

                self.state = 'DONE'

            # If the user has asked everything to end while nothing is happening
            elif s == 'END' and ls == 'STANDBY':
                self.state = 'DONE'

        # Safely join the thread.
        self.t.join()

    def clear_queue(self, q):
        ''' Convenience. Clears a queue in a thread-safe manner.'''

        q.close()
        return mp.Queue()

    def copyfiles(self, rd, fromfolder, tofolder, kind):
        ''' Safely attempts to copy the output/error files to the new folder (in
        the Google Drive) at the end of an acquisition. 'kind' can be either
        'phase' or 'data'; the filenames are different. By 'safely' attempting,
        I mean there is a handler for if the files don't exist (if for some
        reason the files don't exist).
        '''

        if kind == 'phase':
            outfile = 'phaseout.txt'
            errfile = 'phaseerr.txt'
        elif kind == 'data':
            outfile = 'runlog.txt'
            errfile = 'err.txt'
        else:
            self.terminal_out_queueout.put.write("Wrong \'kind\' in " + \
                                                 "copyfiles: " + str(kind))
            return

        uifile = qol.path_file['Run Queue'] + 'userinput.txt'
        scriptfile = self.rd['Script File Location'] + self.rd['Script File']

        # Try to move each folder in turn. Notify the user of errors.
        if isinstance(tofolder, str):
            if os.path.exists(tofolder):
                try:
                    shutil.copy2(scriptfile, tofolder)
                except IOError:
                    self.terminal_out_queueout.put("Could not find the script " + \
                                                "file in the code folder.")

                try:
                    shutil.copy2(rd['.rd File Location'], tofolder)
                except IOError:
                    self.terminal_out_queueout.put("Could not move the " + \
                                    "acquisition file " + fromfolder + outfile + \
                                    " to the directory " + tofolder)

                try:
                    shutil.copy2(fromfolder + outfile, tofolder)
                except IOError:
                    self.terminal_out_queueout.put("Could not move the output " + \
                                    "file " + fromfolder + outfile + " to the " + \
                                    "directory " + tofolder)

                try:
                    shutil.copy2(fromfolder + errfile, tofolder)
                except IOError:
                    self.terminal_out_queueout.put("Could not move the error " + \
                                                "file " + fromfolder + \
                                                errfile + " to the " + \
                                                "directory " + tofolder)

                try:
                    shutil.copy2(uifile, tofolder)
                except IOError:
                    self.terminal_out_queueout.put("Could not move the user " + \
                                                   "input file " + uifile + \
                                                   " to the directory " + tofolder)

                if 'Quenches' in rd['Run Dictionary'].index:
                    try:
                        print(rd['Run Dictionary'].ix['Quenches'])
                        shutil.copy2(self.rd['Run Dictionary'].ix['Quenches'] \
                                                            .Value, \
                                     tofolder)
                    except IOError:
                        self.terminal_out_queueout \
                            .put("Could not move the output file " + fromfolder + \
                                outfile + " to the directory " + tofolder)
            else:
                self.terminal_out_queueout.put("Could not find the destination" + \
                                            " directory: " + tofolder)
        return

    def check_keywds(self, text, acq_in, acq_out, acq_err, proc):
        ''' Checks text entered by the user or sent by the child process for
        keywords and acts accordingly. Returns 'end' if the manager should quit
        after return. Otherwise, returns none. Will also change the state of the
        manager to end the while loop in run_acq.
        '''

        # Text from the acquisition process begins with 'manager'
        if text.find('manager:') > -1:
            text = text[len('manager:'):]
            # If the child process has finished, change the state and  make sure
            # the process is ended.
            if text == 'done':
                self.state = self.last_state
                self.wait_for_signal('manager:shut down', acq_in, \
                                     self.terminal_out_queueout, 30.0)
                proc.join(30.0)
                if proc.is_alive():
                    self.terminal_out_queueout.put("Did not receive a " + \
                                                   "shutdown notification" + \
                                                   " from the child process" + \
                                                   ". It will now be " + \
                                                   "terminated.")
                    proc.terminate()
                return True
            # If the child process exited with an error, notify the user via the
            # error output terminal
            elif text == 'err':
                self.state = self.last_state
                self.terminal_err_queueout.put('Acquisition exited with an ' + \
                                               'error!')
                self.wait_for_signal('manager:shut down', acq_in, \
                                     self.terminal_out_queueout, 30.0)
                proc.join(30.0)
                if proc.is_alive():
                    self.terminal_out_queueout.put("Did not receive a " + \
                                                   "shutdown notification" + \
                                                   " from the child process" + \
                                                   ". It will now be " + \
                                                   "terminated.")
                    proc.terminate()
                return True

        # Text from the user or unimportant output from the process does not
        # begin with 'manager'
        else:
            # Command to pause the run queue. Maybe to rotate the waveguides
            # or something.
            if text == 'pause queue':
                self.ask_run_dict = False

            # Command to resume the run queue. Maybe to rotate the waveguides
            # or something.
            elif text == 'resume queue':
                self.ask_run_dict = True

            # Tell the process to end when convenient.
            elif text == 'quit':
                if not self.state == 'STANDBY':
                    self.end_acq(acq_out, acq_in, acq_err, proc)
                    if (not proc.is_alive()) and \
                       (not self.phase_proc.is_alive()):
                        self.state = 'END'
                if self.state == 'ACQUISITION' and self.last_state == 'PHASE':
                    self.end_acq(self.phase_out, self.phase_in, \
                                 self.phase_err, self.phase_proc)
                return True

            # Tell the process to end immediately. This should cause a keyboard
            # interrupt in the process and it will shut down safely.
            elif text == 'quit now':
                if not self.state == 'STANDBY':
                    self.end_acq(acq_out, acq_in, acq_err, proc, now = True)
                if self.state == 'ACQUISITION' and self.last_state == 'PHASE':
                    self.end_acq(self.phase_out, self.phase_in, \
                                 self.phase_err, self.phase_proc, now = True)
                self.state = 'END'
                return True

            # Tell the process to end when convenient. Wait (at most) 2 minutes
            # for the process to terminate. If it is still active, notify the
            # user. If the process is successfully terminated, change the state.
            elif text == 'quit acq':
                if not self.state == 'STANDBY':
                    self.end_acq(acq_out, acq_in, acq_err, proc)
                    if not proc.is_alive():
                        if self.state == 'PHASE':
                            self.state = 'STANDBY'
                        else:
                            self.state = self.last_state
                return True

            # Tell the process to terminate immediately by way of a
            # KeyboardInterrupt. If it is still active after 40 s, terminate it.
            elif text == 'quit acq now':
                if not self.state == 'STANDBY':
                    self.end_acq(acq_out, acq_in, acq_err, proc, now = True)
                    if self.state == 'PHASE':
                        self.state = 'STANDBY'
                    else:
                        self.state = self.last_state
                return True

            # Ask the process to pause. If it is not paused, notify the user.
            elif text == 'pause':
                if not self.state == 'STANDBY':
                    acq_out.put(text)
                    check = self.wait_for_signal('manager:paused', \
                                                 acq_in, \
                                                 self.terminal_out_queueout, \
                                                 120.0,
                                                 check_keywds = True)
                    if check == None:
                        self.terminal_out_queueout \
                            .put("Could not confirm that the process was" + \
                                 " paused. You may want to consider " + \
                                 "terminating the process with the command " + \
                                 "\'quit acq now\'.")
                return True

            # Ask the process to resume. If it is not resumed, notify the user.
            elif text == 'resume':
                if not self.state == 'STANDBY':
                    acq_out.put(text)
                    check = self.wait_for_signal('manager:resumed', \
                                                 acq_in, \
                                                 self.terminal_out_queueout, \
                                                 120.0,
                                                 check_keywds = True)
                    if check == None:
                        self.terminal_out_queueout \
                            .put("Could not confirm that the process was" + \
                                 " resumed. You may want to consider " + \
                                 "terminating the process with the command " + \
                                 "\'quit acq now\'.")
                return True
            elif text == 'progress':
                if not self.state == 'STANDBY':
                    acq_out.put(text)
        return False

    def wait_for_signal(self, signal, queue_in, queue_out, timeout, \
                        check_keywds = False, acq_in = None, acq_out = None, \
                        acq_errin = None, proc = None):
        ''' This method is used to wait for a critical response from the
        acquisition or phasemonitor process. If the message is not received
        in a certain amount of time, the process will be terminated. Currently,
        this is used for shut down notification, pause/resume notifications,
        run queue receipt and Google Drive folder receipt.
        '''

        data = None
        start_time = time.time()

        while time.time() - start_time < timeout:
            data = self.get_from_queue(queue_in)

            if isinstance(data, str):
                # If the data is found, exit the loop
                if data.find(signal) > -1 or data == signal:
                    return data

                # Otherwise, check the data received for keywords and continue
                # waiting
                else:
                    if check_keywds:
                        self.check_keywds(data, acq_in, acq_out, acq_errin, \
                                          proc)
                    queue_out.put(data)
                    data = None
        else:
            return None

    def start_acq(self, run_dictionary):
        ''' A method that starts a new acquisition file.'''

        # Start the correct process and use the correct queues
        if self.state == 'PHASE':
            self.phase_proc = mp.Process(target = phasemonitor.begin, \
                                         args = (self.phase_out, \
                                                 self.phase_in, \
                                                 self.phase_err)
                                        )
            self.phase_proc.start()
            proc = self.phase_proc

            acq_in = self.phase_in
            acq_out = self.phase_out
            acq_errin = self.phase_err

        elif self.state == 'ACQUISITION':
            module_name = run_dictionary['Script File']
            module_name = module_name[:module_name.find('.py')]

            # Check to make sure the module has been defined and that it is a
            # module. Also check that it has a function called 'begin'.
            try:
                self.module = __import__(module_name,fromlist=[''])
                assert isinstance(self.module,type(phasemonitor))
                assert isinstance(self.module.begin, \
                                  type(phasemonitor.begin))
                reload(self.module)
            except NameError:
                self.terminal_out_queueout \
                    .put("Module name " + str(module_name) + " is not defined.")
                return False
            except AssertionError:
                self.terminal_out_queueout \
                    .put("Object "+str(module_name)+" is not a module or" + \
                         " does not have a \'begin\' function.")
                return False
            except ImportError:
                self.terminal_out_queueout \
                    .put("Object "+str(module_name)+" could not be found" + \
                         " in the PYTHONPATH.")
                return False

            self.p = mp.Process(target = self.module.begin, \
                                args = (self.acq_out, self.acq_in, \
                                        self.acq_err)
                               )
            self.p.start()
            proc = self.p

            acq_in = self.acq_in
            acq_out = self.acq_out
            acq_errin = self.acq_err

        # The csv file for the run dictionary to be passed to the acquisition
        run_dict_file_location = run_dictionary['.rd File Location']
        if not os.path.exists(run_dict_file_location):
            return False

        # Send the file location to the child process and make sure it was
        # received
        acq_out.put(run_dict_file_location)
        recvd = self.wait_for_signal('manager:received rd', \
                                     acq_in, \
                                     self.terminal_out_queueout, 30.0, \
                                     check_keywds = True,
                                     acq_in = acq_in, acq_out = acq_out, \
                                     acq_errin = acq_errin, proc = proc)

        # If the file was not confirmed as received, terminate the acquisition
        if not recvd:
            self.end_acq(acq_out, acq_in, acq_errin, proc, now = True)
            return False

        # Receive the name of the data folder that the child process is using
        folder = self.wait_for_signal('manager:C:/', acq_in,
                                      self.terminal_out_queueout, 30.0, \
                                      check_keywds = True,
                                      acq_in = acq_in, acq_out = acq_out, \
                                      acq_errin = acq_errin, proc = proc)

        # If the folder was not received, terminate the process
        if folder:
            folder = folder[len('manager:'):]
            if self.state == 'ACQUISITION':
                self.datafolder = folder
            elif self.state == 'PHASE':
                self.phasefolder = folder
        else:
            self.terminal_out_queueout \
                .put("Did not receive a folder name from the child process." + \
                     " Shutting it down.")
            self.end_acq(acq_out, acq_in, acq_errin, proc, now = True)
            return False

        return True

    def end_acq(self, acq_out, acq_in, acq_errin, proc, now = False):
        ''' Function to end the process in a few different ways. If now = False,
        just end the process whenever the acquisition deems it convenient. If
        now is True, kill the process immediately (but safely).
        '''
        if now:
            timeout = 30.0
            text = 'quit acq now'
        else:
            timeout = 600.0
            text = 'quit acq'
        acq_out.put(text)
        self.wait_for_signal('manager:shut down', acq_in, \
                             self.terminal_out_queueout, timeout)
        proc.join(10.0) # Wait another 10 seconds for shutdown.
        if proc.is_alive() and not now:
            self.terminal_out_queueout\
                .put("Did not receive a shutdown notification from" + \
                     " the child process. You may want to consider" + \
                     " terminating the process and these windows" + \
                     " with the command \'quit acq now\'.")
        elif proc.is_alive() and now:
            self.terminal_out_queueout.put("Terminating process...")
            proc.terminate()

        proc.join()

    def run_acq(self, run_dictionary = None, startup = False):
        ''' A method to run any acquisition (phase difference program included)
        or just wait in standby mode.
        '''

        # If the process needs to be started (not resumed), do so.
        if startup:
            if not self.start_acq(run_dictionary):
                last_state = self.last_state
                self.last_state = self.state
                self.state = last_state
                return False

        # Keep track of changes of the current state
        current_state = self.state

        # Set the appropriate queues and processes
        if self.state == 'PHASE':
            acq_out = self.phase_out
            acq_in = self.phase_in
            acq_errin = self.phase_err
            proc = self.phase_proc
        elif self.state == 'ACQUISITION':
            acq_out = self.acq_out
            acq_in = self.acq_in
            acq_errin = self.acq_err
            proc = self.p
        else:
            acq_out = None
            acq_in = None
            acq_errin = None
            proc = None

        # Tell the process to resume. Even if the process has just been started
        # this command will simply do nothing.
        if current_state != 'STANDBY':
            acq_out.put('resume')

        # If we're collecting phase data or nothing, the manager will look for
        # new run dictionaries in the queue. This is a timer to tell the manager
        # when to query the run scheduler for a new dictionary.
        if current_state != 'ACQUISITION':
            run_dict_wait = time.time()

        # This is a timer for checking if the current process is still active
        if self.state != 'STANDBY':
            active_wait = time.time()

        # While the state hasn't changed...
        while self.state == current_state:
            next_run_dictionary = None
            user_input = None
            acq_output = None
            acq_error = None

            # Check and query for a new run dictionary if necessary
            if current_state != 'ACQUISITION' and self.ask_run_dict:
                self.next_run_dictionary = self.get_from_queue(self.rs_queuein)
                if isinstance(self.next_run_dictionary, pd.Series):
                    self.state = 'ACQUISITION'
                    break

                if time.time() - run_dict_wait > 5.0:
                    run_dict_wait = time.time()
                    self.rs_queueout.put('rd')

            # Check if the process is still active
            if current_state != 'STANDBY':
                if time.time() - active_wait > 10.0:
                    active_wait = time.time()
                    if not proc.is_alive():
                        proc.join()
                        if current_state == 'PHASE':
                            self.state = 'STANDBY'
                        elif current_state == 'ACQUISITION':
                            self.state = 'PHASE'

            # Read most recent user input and output from the acquisition
            user_input = self.get_from_queue(self.terminal_in_queuein)
            acq_output = self.get_from_queue(acq_in)
            acq_error = self.get_from_queue(acq_errin)

            # Check user input for keywords. The check_keywds program will
            # handle all necessary actions and change the state if required.
            if user_input:
                self.check_keywds(user_input, acq_in, acq_out, acq_errin, proc)

            # Check acquisition output for keywords and send to output terminal
            if acq_output:
                if not self.check_keywds(acq_output, acq_in, acq_out, \
                                         acq_errin, proc):
                    self.terminal_out_queueout.put(acq_output)

            # Send acquisition error to the error terminal
            if acq_error:
                self.terminal_err_queueout.put(acq_error)

            # If the user input/output processes have closed/terminated, end the
            # acquisition as well.
            if not self.t.is_alive():
                if self.p:
                    if self.p.is_alive():
                        self.end_acq(self.acq_out, self.acq_in, self.acq_err, \
                                     self.p, now = True)
                if self.phase_proc:
                    if self.phase_proc.is_alive():
                        self.end_acq(self.phase_out, self.phase_in, \
                                     self.phase_err, self.phase_proc, \
                                     now = True)
                self.state = 'END'

        self.last_state = current_state

        return True

    def get_from_queue(self, queue):
        if queue:
            try:
                data = queue.get_nowait()
            except Empty:
                return None
            else:
                return data
        else:
            return None

if __name__ == '__main__':
    man = Manager()
