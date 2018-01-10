from acquisition import Acquisition
import fosof_qol as qol
import sys
import time

# Run Dictionary Keys
# Experiment Name = string
# Experiment Name Addon = string
# Repeats = int > 0
# Averages = int > 0

class FakeAcquisition(Acquisition):

    def __init__(self, queue_in, queue_out, queue_err):
        super(FakeAcquisition, self).__init__(queue_in, queue_out, \
                                              queue_err)

    def initialize_acquisition(self):
        self.repeats = int(self.run_dictionary.loc['Repeats'].Value)
        self.averages = int(self.run_dictionary.loc['Averages'].Value)

        self.rep = 0
        self.av = 0

        self.progress = 'Initialization complete...'

        return

    def acquire(self):

        sys.stdout.write("Acquiring some data.")
        time.sleep(1)

        self.progress = "Repeat: " + str(self.rep) + "\nAverage: " + \
                        str(self.av)

        self.av = self.av + 1

        if self.av == self.averages:
            self.av = 0
            self.rep = self.rep + 1

        if self.rep == self.repeats:
            self.acquisition_complete = True

        return

    def pause(self):
        sys.stdout.write("Closing stuff before pausing...")
        time.sleep(2)

        super(FakeAcquisition, self).pause()

        return

    def resume(self):
        sys.stdout.write("Re-initialize stuff before resuming...")
        time.sleep(2)

        super(FakeAcquisition, self).resume()

        return

    def shut_down(self):
        sys.stdout.write("Shutting stuff down safely.")
        super(FakeAcquisition, self).shut_down()

        return

def begin(queue_in, queue_out, queue_err):
    # print("HELLO")
    acq = FakeAcquisition(queue_in, queue_out, queue_err)

    return
