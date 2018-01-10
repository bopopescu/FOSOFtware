# A base class to accommodate all acquisitions. This should make everything
# work with the Manager class from manager.py.
# - T.V. October 27, 2017

import multiprocessing as mp
import multiprocessing.queues
import thread
import threading
import time
import fosof_qol as qol
import sys
import os
import pandas as pd
import time
import logging
import traceback as tb

try:
    from queue import Queue, Empty
except ImportError:
    from Queue import Queue, Empty

class Acquisition(object):
    ''' This will (hopefully) be the base class for all FOSOF acquisitions
    for the hydrogen experiment. This class contains all the methods
    required for an acquisition to be compatible with the Manager class.
    Many of these functions can be added to by calling the super() method in
    the child class. This should give enough flexibility for the user to
    complete whatever it is they want.

    The user can add onto whatever methods they like by overriding them in
    the child class and calling the parent methods of the same name if they
    choose, using the super command. The only method that should not be
    overridden is the main_acq method.
    '''

    def __init__(self, queue_in, queue_out, queue_err, phase_monitor = False):

        # Make sure all the queues passed are actually queues. If they are not,
        # an AssertionError will be raised
        assert isinstance(queue_in, multiprocessing.queues.Queue)
        assert isinstance(queue_out, multiprocessing.queues.Queue)
        assert isinstance(queue_err, multiprocessing.queues.Queue)

        # Make the queues object-wide variables
        self.queue_in = queue_in
        self.queue_out = queue_out
        self.queue_err = queue_err

        # Create another queue to communicate with the child process that will
        # monitor the input queue. This sounds confusing, but see 'check_queue'
        # for more info.
        self.child_queue_in = Queue()

        self.queue_location = qol.path_file['Run Queue']

        if phase_monitor:
            self.outfile = self.queue_location + 'phaseout.txt'
            self.errfile = self.queue_location + 'phaseerr.txt'
        else:
            self.outfile = self.queue_location + 'runlog.txt'
            self.errfile = self.queue_location + 'err.txt'

        # Change the standard input and output to a new type of logger file. See
        # fosof_qol.py for more details.
        sys.stdout = qol.NewLogger(self.queue_out, \
                                   self.outfile, 'out')
        sys.stderr = qol.NewLogger(self.queue_err, \
                                   self.errfile, 'err')

        sys.stdout.write("HELLO")

        try:
            # This variable will be read by the loop in self.main_acq
            self.state = 'active'

            sys.stdout.write("HELLO")

            # Obtain a run dictionary location from the run manager
            sys.stdout.write("Checking for run dictionary.")
            rd_location = self.get_something_from_queue(self.queue_in)
            sys.stdout.write("Received: " + rd_location)

            # Make sure the file exists
            if not os.path.exists(rd_location):
                sys.stderr.write("Could not find run dictionary.")
                sys.stdout.write("Could not find run dictionary.")
                return
            sys.stdout.write("Path found.")

            self.run_dictionary = pd.read_csv(rd_location)
            sys.stdout.write('File opened.')

            if not 'Property' and 'Value' in self.run_dictionary.columns:
                sys.stderr.write('Run dictionary does not have proper format.')
                sys.stdout.write('Run dictionary does not have proper format.')
                return

            self.run_dictionary = self.run_dictionary.set_index('Property')
            sys.stdout.write("manager:received rd") # Communicate to the manager

            sys.stdout.write("Checking for acquisition name and addon...")

            # Checking for necessary keys in run dictionary. This will eventually be
            # replaced by a method that will check for all necessary keys at once.
            if not 'Experiment Name' in self.run_dictionary.index:
                sys.stderr.write("Could not obtain experiment name from run " + \
                                 "dictionary.")
                sys.stdout.write("Could not obtain experiment name from run " + \
                                 "dictionary.")
            if not 'Experiment Name Addon' in self.run_dictionary.index:
                sys.stderr.write("Could not obtain experiment name addon from " + \
                                 "run dictionary.")
                sys.stdout.write("Could not obtain experiment name from run " + \
                                 "dictionary.")
            acq_name = self.run_dictionary.ix['Experiment Name']['Value']
            acq_addon = self.run_dictionary.ix['Experiment Name Addon']['Value']
            sys.stdout.write(acq_name + " - " + acq_addon)

            # Create the folder in the Google Drive where the run dictionary and
            # (possibly) quench file will be moved.
            if self.run_dictionary.ix["Binary Traces"]["Value"] == "True":
                self.folder, self.bin = qol.make_gd_folder(acq_name, \
                                                           acq_addon, \
                                                           make_bin = True)
            else:
                self.folder = qol.make_gd_folder(acq_name, acq_addon, \
                                                 make_bin = False)
                self.bin = None
            sys.stdout.write("Made the folder in the Google Drive.")
            sys.stdout.write("manager:"+self.folder)

            # Control variable for the daemon thread
            self.acquisition_complete = False
        except Exception as e:
            sys.stderr.write(tb.format_exc())
            sys.stderr.write('Shutting down.')
            return

        self.main_acq()

    def get_something_from_queue(self, queue):
        ''' A method that waits indefinitely for anything from the queue. This
        is okay to do because if the run manager does not hear back from this
        acquisition process after a certain timeout period (if there is a
        miscommunication) then this process will be terminated.
        '''

        data = None

        while data == None:
            try:
                data = queue.get_nowait()
            except Empty:
                pass

        return data

    def check_queue(self, in_queue, out_queue):
        ''' This function will be run as a separate thread from the main_acq
        function. That way, the main_acq function does not have to constantly
        check the queue.
        '''
        keep_going = True

        # Until told otherwise...
        while keep_going and not self.acquisition_complete:

            # Do nothing until the
            data = self.get_something_from_queue(in_queue)

            # Check variables against a few key words. No other communication
            # should be needed

            # 'quit acq now' will safely end the acquisition immediately or
            # once the main thread finishes sleeping.
            if data == 'quit acq now':
                keep_going = False
                thread.interrupt_main()
            # 'quit acq' will safely end the acquisition once the parent thread
            # checks the parent/child communication queue. This can be at any
            # convenient time the user chooses
            elif data == 'quit acq':
                keep_going = False
                out_queue.put(data)
            else:
                out_queue.put(data)

        return

    def main_acq(self):
        ''' The main acquisition function. This will be the managing function
        for the acquisition. It will:
            1) Start the child thread that continuously checks the queues
            2) Check the parent/child queue
            3) Handle any keywords found
            4) Run the acquisition routine given by the user
            5) Handle any exceptions
            6) Safely shut down the acquisition
        '''

        try:
            # Start a separate thread to check the queues until the acquisition
            # is complete or cancelled.
            sys.stdout.write("Starting daemon thread")
            self.t = threading.Thread(target = self.check_queue, \
                                      args = (self.queue_in,
                                              self.child_queue_in)
                                     )
            self.t.daemon = True # A daemon thread dies with the parent process.
            self.t.start()
            sys.stdout.write("Thread started.")

            # Response to the user when progress is queried. This can be
            # modified in the acquire method.
            self.progress = 'Progress not specified.'

            # This will be a user modified/designed method to initialize
            # variables
            self.initialize_acquisition()

            # The self.acquisition_complete variable should be changed in the
            # acquire function. The user must override the acquire method and
            # make this change at the end.
            while not self.acquisition_complete:
                # Safely check the queue from the daemon thread for user input.
                try:
                    sys.stdout.write("Checking for user-entered data.")
                    data = self.child_queue_in.get_nowait()
                    sys.stdout.write("Got " + str(data))

                    # Check for a few keywords and act accordingly.
                    if data == 'quit acq':
                        sys.stdout.write("Quitting.")
                        break
                    elif data == 'pause':
                        if self.state == 'active':
                            sys.stdout.write("Pausing.")
                            self.pause()
                        elif self.state == 'paused':
                            self.queue_out.put('manager:paused')
                    elif data == 'resume':
                        if self.state == 'paused':
                            sys.stdout.write("Resuming.")
                            self.resume()
                        elif self.state == 'active':
                            self.queue_out.put('manager:resumed')
                    elif data == 'progress':
                        sys.stdout.write(self.progress)
                    else:
                        sys.stdout.write('Useless input.')
                except Empty:
                    sys.stdout.write("Did not find any user input.")
                    pass

                # If the acquisition is not paused, continue. Otherwise,
                # wait for resume.
                if self.state == 'active':
                    self.acquire()
                else:
                    sys.stdout.write("Waiting for resume command.")
                    time.sleep(1)

        # KeyboardInterrupt will be thrown by the daemon thread if 'quit acq
        # now' is received.
        except KeyboardInterrupt:
            sys.stderr.write(tb.format_exc())
            sys.stdout.write("manager:err")
            sys.stderr.write("Shutdown requested by user.")
            sys.stderr.write("Final progress: " + self.progress)
            self.shut_down() # Safe shut down
        # Any other exceptions will be caught by this.
        except Exception as e:
            sys.stderr.write(tb.format_exc())
            sys.stderr.write("Uh oh! Something went wrong.")
            sys.stderr.write("Final progress: " + self.progress)
            sys.stderr.write("Shutting down.")
            sys.stdout.write("manager:err")
            self.shut_down() # Safe shut down
        # Let the manager process know the acquisition is finished.
        else:
            sys.stdout.write("Acquisition complete!")
            sys.stdout.write(self.progress)
            sys.stdout.write('manager:done')
            self.shut_down()

        return

    def initialize_acquisition(self):
        ''' This method will be run before the acquisition begins. This can
        be overridden by the user in the child class.
        '''

        self.progress = 'Initializing'

        return

    def acquire(self):
        ''' This is where the magic happens. The user should override this
        function completely with their own \'acquire\' function. Object
        properties are changed here. There should also be a check for
        acquisition completeness and a change of the progress and
        acquisition_complete variables.
        '''

        self.progress = 'Acquiring'
        self.acquisition_complete = True

        return

    def pause(self):
        ''' This method should be preceded by the user-defined pause method.'''

        # Notify the manager that the command was received and halt the
        # acquisition.
        sys.stdout.write("manager:paused")
        self.state = 'paused'

        return

    def resume(self):
        ''' This method should be preceded by the user-defined resume method.'''

        # Notify the manager that the command was received and continue the
        # acquisition.
        sys.stdout.write("manager:resumed")
        self.state = 'active'

        return

    def shut_down(self):
        ''' This method should be preceded by the user-defined shut_down method.
        '''

        # Collect the daemon thread. Only wait 10 seconds for the thread to exit
        # before killing it by ending the parent process.
        self.t.join(10)

        # Notify the manager that the thread has shut down and restore the
        # standard output/error to system default.
        sys.stdout.write("manager:shut down")
        sys.stdout.restore()
        sys.stderr.restore()

        return
