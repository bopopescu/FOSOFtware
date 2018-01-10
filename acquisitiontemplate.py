# imports here
from acquisition import Acquisition

class Name(Acquisition):

    # This init header should not be changed. The function should always take
    # self and three queues.
    def __init__(self, queue_in, queue_out, queue_err):
        super(Name, self).__init__(queue_in, queue_out, \
                                   queue_err)

        # This is where the Acquisition class will handshake with the Manager.
        # Information is swapped before the acquisition starts. You can write
        # some more initialization here but I recommend doing that later
        # in the initialize_acquisition function.

    # Define required functions

    def initialize_acquisition(self):
        # Initialize all global variables here, including the 'progress'
        # variable.

        return

    def acquire(self):

        # Any acquisition should be done here. Also, update the progress
        # variable.
        # This function can include as many or few traces as you like. See
        # fakeacquisition.py as an example.

        # This function should always end with
        # if somecondition:
        #     self.acquisition_complete = True

        return

    def pause(self):
        # Perform any shutdown/disconnect actions you want here before
        # communicating with the manager.

        super(AcquisitionName, self).pause()

        return

    def resume(self):
        # Perform any re-initialization actions you want here before
        # communicating with the manager.

        super(AcquisitionName, self).resume()

        return

    def shut_down(self):
        # Perform any shutdown/disconnect actions you want here before
        # communicating with the manager.

        super(AcquisitionName, self).shut_down()

        return

    # Define any other acquisition-specific functions below.

# This function must always be included. This function is what the Manager
# will call. It must always take these three arguments in this order.
def begin(queue_in, queue_out, queue_err):
    acq = FakeAcquisition(queue_in, queue_out, queue_err)

    return
