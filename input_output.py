# This code is part of the new Run Scheduler/Manager program. This deals with
# all of the user interfaces for this setup.
# - T.V. October 30, 2017

from Tkinter import *
import tkMessageBox
import threading as th
import multiprocessing as mp
from datetime import datetime as dt
import time
import pandas as pd
import numpy as np
import fosof_qol as qol
import ttk
import os
import tkFileDialog as tkfd

try:
    from queue import Queue, Empty
except ImportError:
    from Queue import Queue, Empty

_RM_FOLDER_ = qol.path_file['Run Manager Files Folder']
_QUENCH_FOLDER_ = qol.path_file['Quench Files Folder']
_QUEUE_ = qol.path_file['Run Queue']
_ICODE_ = qol.path_file['Instrument Code']
_CODE_ = qol.path_file['Code']

class UserInput(Toplevel):
    ''' A command line-type user input window.'''

    def __init__(self, queue_out, queue_in, master=None):
        Toplevel.__init__(self, master)
        assert isinstance(queue_out, mp.queues.Queue)
        assert isinstance(queue_in, mp.queues.Queue)
        self.title("FOSOFtware: User Input")
        self.running = True
        self.queue_out = queue_out # Will be the queue to send data
        self.queue_in = queue_in # Will be the queue to receive data
        self.grid()
        self.createWidgets()

        # This thread constantly searches for messages coming from the
        # manager program.
        self.t = th.Thread(target=self.run_loop)
        self.t.start()

        self.outfile_name = qol.path_file['Run Queue']+'userinput.txt'
        self.outfile_descriptor = 'w'

        outtext = dt.strftime(dt.today(),'%Y-%m/%d %H:%M:%S')
        outtext = outtext + '\tStart\n'
        with open(self.outfile_name, self.outfile_descriptor) as ofile:
            ofile.write(outtext)
            ofile.flush()
            self.outfile_descriptor = 'a'

    def run_loop(self):
        ''' A loop for to continually check the incoming queue.'''

        while self.running:
            self.check_queue()

    def check_queue(self):
        ''' Checks the queue shared with the Manager class.'''

        newtext = None

        # Safe method to look at the queue repeatedly until something
        # appears. This method does not hang if the queue is empty.
        try:
            newtext = self.queue_in.get_nowait()
        except Empty:
            return
        else:
            if newtext != '':
                self.check_kwds(newtext)
            return

    def check_kwds(self, text):
        ''' A function to search user input for keywords relevant to this
        object.
        '''

        if text == 'quit' or text == 'quit now':
            self.queue_out.put(text)
            self.running = False
            self.t.join()
            self.quit()
        elif text == 'acq ended' or text == 'new acq':
            self.outfile_descriptor = 'w'
            outtext = dt.strftime(dt.today(),'%Y-%m/%d %H:%M:%S')
            outtext = outtext + '\tStart\n'
            with open(self.outfile_name, self.outfile_descriptor) as ofile:
                ofile.write(outtext)
                ofile.flush()
                self.outfile_descriptor = 'a'
        elif text == 'acq resumed':
            self.outfile_descriptor = 'a'

    def update_label(self, new_text):
        ''' A convenience method to update the label, making sure that no
        more than 80 characters are displayed per line in the past input
        box.
        '''

        new_text_list = []
        new_text = self.in_text.get() + " " + new_text
        if len(new_text) > 80:
            for chunk in range(1,int(len(new_text) / 80)+1):
                new_text_list.append(new_text[(chunk-1)*80:chunk*80])
        else:
            new_text_list.append(new_text)

        # display_text_list is the list of user-entered text that appears
        # in the past input box. This will be separated by newline chars.
        for i in range(len(new_text_list)):
            self.display_text_list.append(new_text_list[i])

        # If the text has surpassed the top of the screen, get rid of the
        # least recent data.
        while len(self.display_text_list) > 30:
            self.display_text_list.pop(0)

        # Increase the line number, and set the "In[#]" label beside the
        # user entry box.
        self.line_num.set(self.line_num.get() + 1)
        self.in_text.set(self.make_in_text(self.line_num.get()))

        # Reset the display text
        self.display_text.set('\n'.join(self.display_text_list))

    def newline_event(self, event):
        ''' Handles the event in which the user hits <Return>. This will add
        the text from text_entry to the text_display Label after checking
        the entered text for keywords. Also writes text to the output file.
        '''

        new_line = self.entry_line.get()
        if new_line != '':
            self.entry_line.set('')
            self.check_kwds(new_line)
            try:
                outtext = dt.strftime(dt.today(),'%Y-%m/%d %H:%M:%S')
                outtext = outtext + '\t' + new_line + '\n'
                with open(self.outfile_name, self.outfile_descriptor) as ofile:
                    ofile.write(outtext)
                    ofile.flush()
                    self.outfile_descriptor = 'a'
            except ValueError as e:
                print(tb.format_exc())
                pass
            self.queue_out.put(new_line)
            self.update_label(new_line)

        return

    def make_in_text(self, n):
        ''' Convenience function to get rid of clutter in the code.'''
        return 'In['+str(n)+']:'

    def createWidgets(self):
        ''' The mainloop method.'''
        self.line_num = IntVar()
        self.line_num.set(0)

        # The user input In[#] label.
        self.in_text = StringVar()
        self.in_text.set(self.make_in_text(self.line_num.get()))
        self.in_label = Label(self, width=10, height=1, \
                              background='white', foreground='black', \
                              textvariable = self.in_text, \
                              justify = RIGHT, anchor = E)
        self.in_label.grid(column=0,row=1)

        # The user input box.
        self.entry_line = StringVar()
        self.entry_line.set("Enter commands here. Hit <Return> to send.")
        self.text_entry = Entry(self, width=80, \
                                textvariable=self.entry_line)
        self.text_entry.bind("<Key-Return>",self.newline_event)
        self.text_entry.grid(column=1,row=1)

        # The past input display box.
        self.display_text_list = ['Your text will appear here ' + \
                                  'once entered.']
        self.display_text = StringVar()
        self.display_text.set('\n'.join(self.display_text_list))
        self.text_display = Label(self, width=80, height=30, \
                                  background='white', foreground='blue', \
                                  textvariable = self.display_text, \
                                  justify = LEFT, anchor = SW, \
                                  relief = 'groove')
        self.text_display.grid(column=0, row=0, columnspan=2)

class OutputMonitor(Toplevel):
    ''' Will display all output from every process.'''

    def __init__(self, queue_out, queue_in, master=None):
        Toplevel.__init__(self, master)
        assert isinstance(queue_out, mp.queues.Queue)
        assert isinstance(queue_in, mp.queues.Queue)
        self.running = True
        self.queue_out = queue_out # Queue to send data
        self.queue_in = queue_in # Queue to receive data
        self.grid()
        self.createWidgets()

        # This thread constantly searches for messages coming from the
        # manager program.
        self.t = th.Thread(target=self.run_loop)
        self.t.start()

    def run_loop(self):
        ''' A loop for to continually check the incoming queue.'''

        while self.running:
            self.check_queue()

    def check_kwds(self, text):
        ''' Check text against a predetermined list of keywords.'''

        if text == 'quit':
            self.running = False
            self.quit()

        return


    def check_queue(self):
        ''' Checks the queue shared with the Manager class.'''

        newtext = None

        # Safe method to look at the queue repeatedly until something
        # appears. This method does not hang if the queue is empty.
        try:
            newtext = self.queue_in.get_nowait()
        except Empty:
            return
        else:
            if newtext != '':
                self.check_kwds(newtext)
                self.update_label(newtext)
            return

    def update_label(self, new_text):
        ''' A convenience method to update the label, making sure that no
        more than 80 lines are displayed.
        '''

        # Break lines longer than 80 lines into multiple lines
        new_text_list = []
        if len(new_text) > 80:
            for chunk in range(1,int(len(new_text) / 80)+1):
                new_text_list.append(new_text[(chunk-1)*80:chunk*80])
        else:
            new_text_list.append(new_text)

        # Add the new text to the list of text to display and  get rid of
        # the least recent data.
        for i in range(len(new_text_list)):
            self.display_text_list.append(new_text_list[i])

        while len(self.display_text_list) > 30:
            self.display_text_list.pop(0)

        # Update the label with the new data.
        self.display_text.set('\n'.join(self.display_text_list))

    def createWidgets(self):
        ''' Mainloop function.'''

        # Creating the text display.
        self.display_text_list = []
        self.display_text = StringVar()
        self.display_text.set('\n'.join(self.display_text_list))
        self.text_display = Label(self, width=80, height=30, \
                                  background='white', foreground='black', \
                                  textvariable = self.display_text, \
                                  justify = LEFT, anchor = SW)
        self.text_display.grid(column=0, row=0)

class RunScheduler(Frame):
    ''' The main and most complex user interface for the run scheduling
    and manager program. Deals with all the scheduling and creation of run
    files.
    '''

    def __init__(self, queue_out, queue_in, master = None):
        Frame.__init__(self, master)
        self.master = master
        assert isinstance(queue_out, mp.queues.Queue) # Send
        assert isinstance(queue_in, mp.queues.Queue) # Receive
        self.queue_out = queue_out
        self.queue_in = queue_in
        self.schedule_list = pd.DataFrame() # Scheduled acquisitions
        self.grid()
        self.createwidgets()

        # This thread constantly checks for input from the manager object.
        self.t = th.Thread(target=self.check_queue)
        self.t.start()

    def check_kwds(self, text):
        ''' Check text against a predetermined list of keywords.'''

        if text == 'quit':
            self.quit()
        if text == 'rd':
            self.send_run_dictionary()

        return

    def send_run_dictionary(self):
        ''' Sends the run dictionary at the top of the schedule list to the
        manager.
        '''

        if len(self.schedule_list) > 0:
            # Sends a pandas Series object to the manager and gets rid of
            # this object from the list.
            next_rd = self.schedule_list.iloc[0]
            self.queue_out.put(next_rd)
            self.schedule_list = self.schedule_list \
                                     .drop(self.schedule_list.index[0])
            self.runqueue_treeview.delete(self.runqueue_treeview \
                                              .get_children()[0])
        return

    def check_queue(self):
        ''' Safe method to check the queue for input from the manager.
        '''

        while True:
            newtext = None

            try:
                newtext = self.queue_in.get_nowait()
            except Empty:
                pass
            else:
                if newtext != '':
                    self.check_kwds(newtext)
        return

    def new_rd_from_template(self):
        ''' Creates a new run dictionary from scratch.'''

        # Ask the user what script file they'd like to use. The folder
        # here should be set to the computer's main code folder, though it
        # doesn't really matter.
        scriptfile = tkfd.askopenfilename(defaultextension='.py', \
                                          filetypes=(('Python Script',\
                                          '*.py'),), \
                                          title='Select a Python Script' + \
                                                ' to Run', \
                                          initialdir=_CODE_)

        file_location = scriptfile[:scriptfile.rfind('/')+1]
        scriptfile = scriptfile[scriptfile.rfind('/')+1:]

        if len(scriptfile) > 0:
            open_file = open(file_location + scriptfile,'r')
            file_contents = open_file.read().split('\n')
            open_file.close()
        else:
            return

        if '# Run Dictionary Keys' in file_contents:
            rundict_keys = []
            rundict_values = []
            keys_start = file_contents.index('# Run Dictionary Keys')
            i = 1
            while True:
                if file_contents[keys_start + i].find('#') > -1:
                    if file_contents[keys_start + i].find(' = ') > -1:
                        keyvalue = file_contents[keys_start + i].split(' = ')
                        rundict_keys.append(keyvalue[0][2:])
                        rundict_values.append(keyvalue[1])
                    else:
                        rundict_keys.append(file_contents[keys_start + i][2:])
                else:
                    break
                i += 1
        else:
            tkMessageBox.showerror('File Format Error', \
                                   'Unable to find \'# Run Dictionary' + \
                                   ' Keys\' in the .py file selected.' + \
                                   ' Try a different file or start a run' + \
                                   ' dictionary from scratch.')
            return

        # Ask the user for a filename to save the run manager file and make
        # sure it's a .rm file.
        ext = ''
        while not ext == '.rm':
            rmfile = tkfd.asksaveasfilename(defaultextension='.rm', \
                                            filetypes=(('Run Manager ' \
                                                        'File','*.rm'),), \
                                            title='Select a Name for the' + \
                                                  ' Run Manager File', \
                                            initialdir=_RM_FOLDER_)
            if not rmfile:
                break
            ext = rmfile[rmfile.find('.'):]
            if not ext == '.rm':
                tkMessageBox.showerror('Wrong File Extension', \
                                       'Please use the \'.rm\' file ' + \
                                       'extension.\nIt\'ll make things ' + \
                                       'more organized!')

        if scriptfile and rmfile:
            # Create a mock file that has two columns and one row of data.
            self.rmfile = rmfile
            dct = {}

            if len(rundict_values) == len(rundict_keys):
                dct = {'Property':rundict_keys, 'Value':rundict_values}
            else:
                dct = {'Property':rundict_keys, \
                       'Value':['' for i in range(len(rundict_keys))]}

            df = pd.DataFrame(dct, columns = ['Property', 'Value'])
            df = df.set_index('Property')

            # Open the rm file and write the script file name
            f = open(rmfile,'w')
            f.write(scriptfile + ',' + file_location + '\n')
            f.close()

            # Append the data to the file.
            f = open(rmfile,'a')
            df.to_csv(f)
            f.close()

            # Proceed with regular run dictionary opening routine.
            self.open_rundict(fname = rmfile)

    def new_rundict(self):
        ''' Creates a new run dictionary from scratch.'''

        # Ask the user what script file they'd like to use. The folder
        # here should be set to the computer's main code folder, though it
        # doesn't really matter.
        scriptfile = tkfd.askopenfilename(defaultextension='.py', \
                                          filetypes=(('Python Script',\
                                          '*.py'),), \
                                          title='Select a Python Script' + \
                                                ' to Run', \
                                          initialdir=_CODE_)

        file_location = scriptfile[:scriptfile.rfind('/')+1]
        scriptfile = scriptfile[scriptfile.rfind('/')+1:]

        # Ask the user for a filename to save the run manager file and make
        # sure it's a .rm file.
        ext = ''
        while not ext == '.rm':
            rmfile = tkfd.asksaveasfilename(defaultextension='.rm', \
                                            filetypes=(('Run Manager ' \
                                                        'File','*.rm'),), \
                                            title='Select a Name for the' + \
                                                  ' Run Manager File', \
                                            initialdir=_RM_FOLDER_)
            if not rmfile:
                break
            ext = rmfile[rmfile.find('.'):]
            if not ext == '.rm':
                tkMessageBox.showerror('Wrong File Extension', \
                                       'Please use the \'.rm\' file ' + \
                                       'extension.\nIt\'ll make things ' + \
                                       'more organized!')

        if scriptfile and rmfile:
            # Create a mock file that has two columns and one row of data.
            self.rmfile = rmfile
            df = pd.DataFrame({'Property':['Property'],
                               'Value':['Value (Example)']
                               }).set_index('Property')

            # Open the rm file and write the script file name
            f = open(rmfile,'w')
            f.write(scriptfile + ',' + file_location + '\n')
            f.close()

            # Append the mock data to the file.
            f = open(rmfile,'a')
            df.to_csv(f)
            f.close()

            # Proceed with regular run dictionary opening routine.
            self.open_rundict(fname = rmfile)

    def able_quenches(self, enable):
        ''' Convenience method to enable/disable all components of the window
        that are related to quench cavities.
        '''

        if enable:
            self.status_entry.config(state = NORMAL)
            self.status_button.config(state = NORMAL)
            self.open_entry.config(state = NORMAL)
            self.open_button.config(state = NORMAL)
            self.av_entry.config(state = NORMAL)
            self.av_button.config(state = NORMAL)
        else:
            for child in self.quenches_treeview.get_children():
                self.quenches_treeview.delete(child)
            self.status_entry.config(state = DISABLED)
            self.status_button.config(state = DISABLED)
            self.open_entry.config(state = DISABLED)
            self.open_button.config(state = DISABLED)
            self.av_entry.config(state = DISABLED)
            self.av_button.config(state = DISABLED)

    def open_rundict(self, fname = None):

        # If a filename was not passed, ask the user for one.
        if not fname:
            filename = tkfd.askopenfilename(defaultextension='.rm', \
                                            filetypes=(('Run Manager File',
                                                        '*.rm'),), \
                                            title='Select a Starting Run ' + \
                                                  'Manager File', \
                                            initialdir=_RM_FOLDER_)
        else:
            filename = fname

        if not filename:
            return

        self.rmfile = filename
        self.rd = pd.read_csv(filename, skiprows=1).set_index('Property')

        # Reads the first line of the run manager file. According to the
        # file standards I came up with, this should be the name of the
        # acquisition script file, i.e. acquisition.py
        openfile = open(filename)
        self.rd_acqfilename = openfile.readline().replace('\n','') \
                                                 .split(',')
        self.rd_acqfileloc = self.rd_acqfilename[1]
        self.rd_acqfilename = self.rd_acqfilename[0]
        openfile.close()

        # Clear the items currently in the run dictionary editing table
        for child in self.rundict_treeview.get_children():
            self.rundict_treeview.delete(child)

        # Make sure the run dictionary has an 'Experiment Name' value
        if 'Experiment Name' in self.rd.index:
            self.rd_acqname = self.rd.ix['Experiment Name'].Value
        else:
            self.rd_acqname = 'Unknown Acquisition'

        # Populate the table with properties and values from the run manager
        # file.
        for intind in range(len(self.rd.index)):
            self.rundict_treeview.insert('',intind,iid=self.rd.index[intind])
            self.rundict_treeview.set(self.rd.index[intind],'Property', \
                                      self.rd.index[intind])
            self.rundict_treeview.set(self.rd.index[intind], 'Value', \
                                      self.rd.iloc[intind]['Value'])

        # If the user has selected a run manager file that makes reference to
        # quench cavities, the .quench file must be opened as well.
        if 'Quenches' in self.rd.index:
            filename = self.rd.ix['Quenches']['Value']
            newname = self.fix_quench_file_name(filename)

            # Change the value in the table as well as in the pandas DataFrame
            if not filename == newname:
                self.rd.at['Quenches','Value'] = newname
                self.rundict_treeview.set('Quenches', 'Value', newname)

            self.open_quenches(self.rd.ix['Quenches']['Value'])
        else:
            self.able_quenches(False)

        # Highlight a value in the run dictionary table and fill in the
        # 'change value' entry box.
        self.rundict_treeview.selection_set('\"'+self.rd.index[0]+'\"')
        self.change_entry.delete(0,END)
        self.change_entry.insert(0,self.rundict_treeview \
                                       .item(self.rd.index[0],'values')[1])

        # Enable all user input components
        self.change_entry.config(state = NORMAL)
        self.change_button.config(state = NORMAL)
        self.add_button.config(state = NORMAL)
        self.new_entry.config(state = NORMAL)
        self.delete_entry.config(state = NORMAL)
        self.prop_up.config(state = NORMAL)
        self.prop_down.config(state = NORMAL)
        self.schedule_button.config(state = NORMAL)

    def fix_quench_file_name(self, filename):
        ''' If the acquisition requires operation of the USB synthesizers and
        the quench cavities, parameters must be input for the cavities
        (to determine which cavities are open/on and at what power they will
        run). The user must specify the filename in the run dictionary/run
        manager file. If the file name does not follow the standards required
        by the Manager, this function will fix the filename.
        '''
        newname = filename

        # Check to see if the file name is an absolute path or relative path
        if newname.find('C:/') == -1:
            if newname.find('/') == -1:
                # If it's not an absolute path from (C:/), assume it is in
                # the main quench folder.
                newname = _QUENCH_FOLDER_ + newname
            else:
                newname = _QUENCH_FOLDER_ + newname[newname.rfind('/'):]

        # If the file does not have the mandatory .quench extension, fix
        # that.
        if newname.find('.quench') == -1:
            # If there is an extension that is not '.quench', change it.
            if newname.find('.') > -1:
                newname = newname[:newname.rfind('.')] + '.quench'
            # If the file has no extension, assume the user meant to put
            # '.quench' at the end.
            else:
                newname = newname + '.quench'
            # If the original file exists, move the file to match with the
            # new file name. If the user specified a new file, just create
            # a new file.
            if os.path.exists(filename):
                shutil.move(filename,newname)

        # The output file will be an absolute path to a .quench file that
        # may or may not already exist, depending on what name the user
        # specified.
        return newname

    def open_quenches(self, filename):
        ''' Open the .quench file specified by filename. This function assumes
        that the filename is an absolute path to a quench file. If it is not
        an absolute path, no exceptions will be raised but the file may be
        re-created elsewhere.
        '''

        # If the file does not exist, create a new quench dictionary and save it
        if not os.path.exists(filename):
            qd = self.create_quench_template()
            qd.to_csv(filename)

        # Open it as a global variable
        self.qd = pd.read_csv(filename, dtype=str).set_index('Quench Name')

        chld = self.quenches_treeview.get_children()

        if len(chld) > 0:
            for child in chld:
                self.quenches_treeview.delete(child)

        # Populate the quench parameter table in the main window.
        for intind in range(len(self.qd.index)):
            self.quenches_treeview.insert('',intind,iid=self.qd.index[intind])

            self.quenches_treeview.set(self.qd.index[intind],'Quench Name', \
                                       self.qd.index[intind])
            self.quenches_treeview.set(self.qd.index[intind], 'Cavity', \
                                       self.qd.iloc[intind]['Cavity'])
            self.quenches_treeview.set(self.qd.index[intind], 'Status', \
                                       self.qd.iloc[intind]['Status'])
            self.quenches_treeview.set(self.qd.index[intind], 'Open', \
                                       self.qd.iloc[intind]['Open'])
            self.quenches_treeview.set(self.qd.index[intind], \
                                       'Attenuation Voltage', \
                                       self.qd.iloc[intind]
                                                   ['Attenuation Voltage'])

        # Highlight a value in the table, clear the user input and enable the
        # user interfaces.
        self.quenches_treeview.selection_set('\"'+self.qd.index[0]+'\"')

        sel = self.quenches_treeview.selection()
        self.status_entry.delete(0,END)
        self.status_entry.insert(0,self.quenches_treeview.item(sel[0], \
                                                               'values')[2])

        self.open_entry.delete(0,END)
        self.open_entry.insert(0,self.quenches_treeview.item(sel[0], \
                                                             'values')[3])

        self.av_entry.delete(0,END)
        self.av_entry.insert(0,self.quenches_treeview.item(sel[0], \
                                                           'values')[4])

        self.able_quenches(True)

    def create_quench_template(self):
        ''' Creates a dataframe with the default quench values.
        '''

        d = {}
        d['Quench Name'] = ['pre-quench_910', 'pre-quench_1088', \
                            'pre-quench_1147', 'post-quench_910', \
                            'post-quench_1088', 'post-quench_1147']
        d['Cavity'] = ['pre-910','pre-1088','pre-1147', \
                       'post-910','post-1088','post-1147']
        d['Status'] = ['off' for i in range(6)]
        d['Open'] = ['FALSE' for i in range(6)]
        d['Attenuation Voltage'] = ['None' for i in range(6)]

        df = pd.DataFrame(d)
        df = df.set_index('Quench Name')
        return df

    def change_selection(self, evnt):
        ''' Triggered when changing the selection in the run dictionary
        table.
        '''

        # Populate the entry box with the corresponding value.
        sel = self.rundict_treeview.selection()

        self.change_entry.delete(0,END)
        self.change_entry.insert(0,self.rundict_treeview
                                       .item(sel[0],'values')[1])

    def change_quench_selection(self, evnt):
        ''' Triggered when changing the selection in the quench dictionary
        table.
        '''

        # Populate the entry boxes with the corresponding values.
        sel = self.quenches_treeview.selection()

        self.status_entry.delete(0,END)
        self.status_entry.insert(0,self.quenches_treeview
                                       .item(sel[0],'values')[2])

        self.open_entry.delete(0,END)
        self.open_entry.insert(0,self.quenches_treeview
                                     .item(sel[0],'values')[3])

        self.av_entry.delete(0,END)
        self.av_entry.insert(0,self.quenches_treeview
                                   .item(sel[0],'values')[4])

    def modify_value(self):
        ''' Triggered when a user hits the 'Change Value' button for the run
        dictionary.
        '''

        # Obtain the text in the entry box and the item name in the table.
        text = self.change_entry.get()
        sel = self.rundict_treeview.selection()

        # Ensure the quench file name is properly formatted and open the file.
        if sel[0] == 'Quenches':
            text = self.fix_quench_file_name(text)
            self.open_quenches(text)

        self.rundict_treeview.set(sel[0],'Value',text)
        self.rd.at[sel[0],'Value'] = text

    def modify_status(self):
        ''' Triggered when a user hits the 'Change Value' button for the status
        parameter of the quenches. Protects against invalid values.
        '''

        status = self.status_entry.get()
        sel = self.quenches_treeview.selection()

        if status in ['on','off']:
            self.quenches_treeview.set(sel[0],'Status',status)
            self.qd.at[sel[0],'Status'] = status
        else:
            tkMessageBox.showwarning('Invalid Status','The \'Status\' ' + \
                                     'property can only be \'on\' or \'off\'.')

    def modify_open(self):
        ''' Triggered when a user hits the 'Change Value' button for the open
        parameter of the quenches. Protects against invalid values.
        '''

        o = self.open_entry.get()
        print(o)
        sel = self.quenches_treeview.selection()

        if o in ['True','False']:
            self.quenches_treeview.set(sel[0],'Open',o)
            self.qd.at[sel[0],'Open'] = eval(o)
        else:
            tkMessageBox.showwarning('Invalid Open','The \'Open\' property ' + \
                                     'can only be \'True\' or \'False\'.')

    def modify_av(self):
        ''' Triggered when a user hits the 'Change Value' button for the
        attenuation voltage parameter of the quenches. Protects against
        invalid values.
        '''

        voltage = self.av_entry.get()
        sel = self.quenches_treeview.selection()

        # If the value entered is a float outside the allowed range, notify
        # the user.
        try:
            if 0.0 <= float(voltage) <= 8.0:
                self.quenches_treeview.set(sel[0],'Attenuation Voltage',voltage)
                self.qd.at[sel[0],'Attenuation Voltage'] = voltage
            else:
                tkMessageBox.showwarning('Invalid Attenuation Voltage','The' + \
                                         ' \'Attenuation Voltage\' property' + \
                                         ' must be\na \'float\' between 0.0' + \
                                         ' and 8.0 or \'None\'.')
        # If the value could not be converted to a float, also notify the user.
        except ValueError:
            print("GOT IT")
            if voltage == 'None':
                self.quenches_treeview.set(sel[0],'Attenuation Voltage',voltage)
                self.qd.at[sel[0],'Attenuation Voltage'] = voltage
            else:
                tkMessageBox.showwarning('Invalid Attenuation Voltage','The' + \
                                         ' \'Attenuation Voltage\' property' + \
                                         ' must be\na \'float\' between 0.0' + \
                                         ' and 8.0 or \'None\'.')

    def new_value(self):
        ''' Error checks the input from the user and creates a new row in the
        run dictionary table if no errors are found.
        '''

        a_new_value = self.newval.get()

        # Check for proper format.
        if a_new_value.find(';') > -1:
            a_new_value = a_new_value.split(';')
            new_property = a_new_value[0]
            new_val = a_new_value[1]

            # Check to make sure the item is not in the index already.
            if not new_property in self.rd.index:
                if new_property == 'Quenches':
                    new_val = self.fix_quench_file_name(new_val)

                    self.open_quenches(new_val)

                self.rd = self.rd.append(pd.Series({'Value':new_val}, \
                                         name=new_property))
                self.rundict_treeview.insert('',len(self.rd)-1, \
                                             iid=new_property)
                self.rundict_treeview.set(new_property, 'Property', \
                                          new_property)
                self.rundict_treeview.set(new_property, 'Value', \
                                          new_val)
                self.rundict_treeview.selection_set('\"'+new_property+'\"')
                self.change_entry.delete(0,END)
                self.change_entry.insert(0,new_val)
            else:
                tkMessageBox.showerror('Property Already Present', \
                                       'Cannot add the new property since ' + \
                                       'it already exists. \nModify the ' + \
                                       'value instead.')
        else:
            tkMessageBox.showerror('Property Already Present', \
                                   'Make sure your entry is in the form ' + \
                                   '\'property;value\'.')

    def remove_value(self):
        ''' Triggered when the user hits \'Delete Property\' for the run
        dictionary.
        '''

        # Always show a warning.
        if tkMessageBox.askokcancel('Warning!','Are you sure you want to ' + \
                                               'delete this property?\nIt ' + \
                                               'may affect how the ' + \
                                               'acquisition runs!'):

            sel = self.rundict_treeview.selection()
            self.rundict_treeview.delete(sel[0])
            self.rd = self.rd.drop(sel[0])
            self.rundict_treeview.selection_set('\"'+self.rd.index[0]+'\"')
            self.change_entry.delete(0,END)
            self.change_entry.insert(0,self.rd.iloc[0].Value)

            if sel[0] == 'Quenches':
                self.able_quenches(False)

    def schedule(self):
        ''' Triggered when the user hits the 'Schedule' button.'''

        # Overwrite the run manager .rm file with the info currently in the
        # dictionary.
        ext = ''
        f = open(self.rmfile,'w')
        f.write(self.rd_acqfilename+','+self.rd_acqfileloc+'\n')
        f.close()

        f = open(self.rmfile,'a')
        self.rd['Value'].to_csv(f, header=['Value'], index_label='Property')
        f.close()

        # Ask the user what run dictionary filename they'd like to use and where
        # they'd like to place it. Make sure the extension is .rd.
        while not ext == '.rd':
            filename = tkfd.asksaveasfilename(defaultextension='.rd', \
                                              title='Select a Starting Run ' + \
                                              'Dictionary', \
                                              filetypes=(("Run Dictionary",
                                                          "*.rd"),), \
                                              initialdir=_QUEUE_)
            if not filename:
                return
            ext = filename[filename.find('.'):]
            if not ext == '.rd':
                tkMessageBox.showerror('Wrong Extension',
                                       'Please use the .rd file extension.' + \
                                       '\nIt will help keep things organized!')

        # Add to the run dictionary file the order of the properties. This will
        # determine the order in which they are written to the text file output
        # by the acquisition (if any).
        self.rd['Order'] = [i for i in range(len(self.rd))]
        self.rd.to_csv(filename)

        # The columns of the DataFrame element sent to the Manager.
        self.runqueue_columns = ["Run Dictionary", "Experiment Name", \
                                 "Script File", ".rd File Location", \
                                 "Quenches", "Script File Location"]

        # The quenches filename is passed separately to the Manager if it
        # exists. This allows the manager to easily move the quench dictionary
        # to the Google Drive folder.
        if "Quenches" in self.rd.index:
            quenches = self.rd.loc["Quenches"].Value
            print("QUENCH FILE NAME: " + quenches)
        else:
            quenches = None
        self.schedule_list = self.schedule_list \
                                 .append(pd.Series([self.rd.copy(deep=True),
                                                    self.rd_acqname, \
                                                    self.rd_acqfilename, \
                                                    filename, quenches, \
                                                    self.rd_acqfileloc], \
                                        index = self.runqueue_columns), \
                                        ignore_index=True)

        # Delete and re-populate the run queue table
        for child in self.runqueue_treeview.get_children():
            self.runqueue_treeview.delete(child)

        for intind in range(len(self.schedule_list.index)):
            this_iid = self.schedule_list.iloc[intind]['Script File'] + str(intind)
            self.runqueue_treeview.insert('',intind,iid=this_iid)
            self.runqueue_treeview.set(this_iid, 'Filename', \
                                       self.schedule_list \
                                           .iloc[intind]['.rd File Location'])
            self.runqueue_treeview.set(this_iid, 'Script File', \
                                       self.schedule_list \
                                           .iloc[intind]['Script File'])

        # Make sure to save the quench file if there is one.
        if 'Quenches' in self.rd.index:
            self.qd.to_csv(self.rd.loc['Quenches'].Value)

        # Activate the user interfaces for the run queue
        self.moveup_button.configure(state = NORMAL)
        self.movedown_button.configure(state = NORMAL)
        self.delete_button.configure(state = NORMAL)

    def moveup(self):
        ''' Move a scheduled acquisition up in the queue.'''

        sel = self.runqueue_treeview.selection()
        ind = self.runqueue_treeview.index(sel)

        if ind > 0:
            self.runqueue_treeview.move(sel,'',ind-1)
            self.schedule_list.ix[ind-1], \
            self.schedule_list.ix[ind] = self.schedule_list.ix[ind].copy(), \
                                         self.schedule_list.ix[ind-1].copy()

    def movedown(self):
        ''' Move a scheduled acquisition down in the queue.'''
        sel = self.runqueue_treeview.selection()
        ind = self.runqueue_treeview.index(sel)

        if ind < len(self.runqueue_treeview.get_children())-1:
            self.runqueue_treeview.move(sel,'',ind+1)
            self.schedule_list.ix[ind+1], \
            self.schedule_list.ix[ind] = self.schedule_list.ix[ind].copy(), \
                                         self.schedule_list.ix[ind+1].copy()

    def movepropdown(self):
        ''' Move a property down in the run dictionary order.'''

        sel = self.rundict_treeview.selection()
        ind = self.rundict_treeview.index(sel[0])

        if ind < len(self.rundict_treeview.get_children())-1:
            self.rundict_treeview.move(sel[0],'',ind+1)
            self.rd.iloc[ind], \
            self.rd.iloc[ind+1] = self.rd.iloc[ind+1].copy(), \
                                  self.rd.iloc[ind].copy()
            temp = self.rd.index[ind]

            # Re-order the rows of the DataFrame object. This is a bit trickier
            # than re-ordering the run queue dataframe since we have a
            # non-integer index and we also want to switch the indices.
            self.rd.index = np.append(np.append(self.rd.index.values[:ind], \
                                                [self.rd.index[ind+1], \
                                                 self.rd.index[ind]]), \
                                                self.rd.index.values[ind+2:])
            self.rd.index.names = ['Property']

    def movepropup(self):
        ''' Move a property up in the run dictionary order.'''

        sel = self.rundict_treeview.selection()
        ind = self.rundict_treeview.index(sel[0])

        if ind > 0:
            self.rundict_treeview.move(sel[0],'',ind-1)
            self.rd.iloc[ind], \
            self.rd.iloc[ind-1] = self.rd.iloc[ind-1].copy(), \
                                  self.rd.iloc[ind].copy()

            self.rd.index = np.append(np.append(self.rd.index[:ind-1], \
                                                [self.rd.index[ind], \
                                                 self.rd.index[ind-1]]), \
                                                self.rd.index[ind+1:])
            self.rd.index.names = ['Property']

    def deletefile(self):
        ''' Remove an acquisition from the queue.'''

        sel = self.runqueue_treeview.selection()
        ind = self.runqueue_treeview.index(sel)

        self.runqueue_treeview.delete(sel)
        self.schedule_list = self.schedule_list.drop(ind)

    def createwidgets(self):
        ''' Set up the main window.'''

        self.menubar = Menu(self.master)

        # File menu creation
        self.filemenu = Menu(self,tearoff=0)
        self.filemenu.add_command(label='New Run Dictionary', \
                                  command=self.new_rundict)
        self.filemenu.add_command(label = 'New Run Dictionary from Template', \
                                  command = self.new_rd_from_template)
        self.filemenu.add_command(label='Open Run Dictionary', \
                                  command=self.open_rundict)

        # Adding things to the menu bar at the top of the window.
        self.menubar.add_cascade(label='File',menu=self.filemenu)
        self.master.config(menu=self.menubar)

        # Setting up the run dictionary table. See documentation on ttk.Treeview
        # for more info.
        self.rundict_columns = ['Property','Value']
        self.rundict_treeview = ttk.Treeview(self, \
                                             columns = (self.rundict_columns), \
                                             show='headings')
        for i in range(len(self.rundict_columns)):
            self.rundict_treeview.heading(i,text=self.rundict_columns[i])
        self.rundict_treeview.bind('<<TreeviewSelect>>',self.change_selection)
        self.rundict_treeview.grid(column = 0, row = 0,columnspan=3, sticky=W)

        # Run dictionary table scrollbar
        self.rundict_scroll = Scrollbar(self, orient = VERTICAL, \
                                        command = self.rundict_treeview.yview, \
                                        width = 15)
        self.rundict_scroll.grid(column = 3,row = 0, sticky = NS)
        self.rundict_treeview.configure(yscrollcommand = self.rundict_scroll \
                                                             .set)

        # Button and entry box used to change a value in the run dictionary
        # table
        self.change_button = Button(self, text='Change Value', \
                                    command=self.modify_value, state = DISABLED)
        self.change_button.grid(column=2,row=1)
        self.replaceval = StringVar()
        self.change_entry = Entry(self, textvariable=self.replaceval, \
                                  width=50, state = DISABLED)
        self.change_entry.grid(column = 0, row = 1, columnspan = 2)

        # Button and entry box used to create a value in the run dictionary
        # table
        self.add_button = Button(self, text = 'Add New Property', \
                                 command = self.new_value, state = DISABLED)
        self.add_button.grid(column = 2, row = 2)
        self.newval = StringVar()
        self.new_entry = Entry(self, textvariable=self.newval, \
                               width=50, state = DISABLED)
        self.new_entry.grid(column=0,row=2,columnspan=2)

        # Delete a row from the rd table
        self.delete_entry = Button(self, text='Delete Selected Property', \
                                   command=self.remove_value, state = DISABLED)
        self.delete_entry.grid(column=0,row=3)

        # Move a row from the rd table upward
        self.prop_up = Button(self, text='Move Property Up', \
                              command=self.movepropup, state=DISABLED)
        self.prop_up.grid(column=1, row=3)

        # Move a row from the rd table downward
        self.prop_down = Button(self, text='Move Property Down', \
                                command=self.movepropdown, state=DISABLED)
        self.prop_down.grid(column=2, row=3)

        # Schedule an acquisition
        self.schedule_button = Button(self, text='Schedule', \
                                      command=self.schedule, state = DISABLED)
        self.schedule_button.grid(column=0,row=4,columnspan=3)

        # Quench table
        self.quenches_columns = ['Quench Name', 'Cavity', 'Status', 'Open', \
                                 'Attenuation Voltage']
        self.quenches_treeview = ttk.Treeview(self, \
                                              columns = (self \
                                                         .quenches_columns),
                                              show = 'headings')
        for i in range(len(self.quenches_columns)):
            self.quenches_treeview.heading(i,text=self.quenches_columns[i])
        self.quenches_treeview.bind('<<TreeviewSelect>>', \
                                    self.change_quench_selection)
        self.quenches_treeview.grid(column = 0, row = 5,columnspan=7)

        # Change buttons and entry boxes for quench properties
        # Status
        self.status_button = Button(self, text='Change \'Status\' Value', \
                                    command=self.modify_status, state = DISABLED)
        self.status_button.grid(column=2,row=6)
        self.statusval = StringVar()
        self.status_entry = Entry(self, textvariable=self.statusval, \
                                  width=50, state = DISABLED)
        self.status_entry.grid(column=0,row=6,columnspan=2)

        # Open
        self.open_button = Button(self, text='Change \'Open\' Value', \
                                  command=self.modify_open, state = DISABLED)
        self.open_button.grid(column=2,row=7)
        self.openval = StringVar()
        self.open_entry = Entry(self, textvariable=self.openval, \
                                width=50, state = DISABLED)
        self.open_entry.grid(column=0,row=7,columnspan=2)

        # Attenuation voltage
        self.av_button = Button(self, \
                                text='Change \'Attenuation Voltage\' Value', \
                                command=self.modify_av, state = DISABLED)
        self.av_button.grid(column=2,row=8)
        self.avval = DoubleVar()
        self.av_entry = Entry(self, textvariable=self.avval,width=50, \
                              state = DISABLED)
        self.av_entry.grid(column=0,row=8,columnspan=2)

        # Run queue table
        self.runqueue_columns = ['Filename','Script File']
        self.runqueue_treeview = ttk.Treeview(self, \
                                              columns = (self   \
                                                         .runqueue_columns), \
                                              show = 'headings')
        for i in range(len(self.runqueue_columns)):
            self.runqueue_treeview.heading(i,text=self.runqueue_columns[i])
        self.runqueue_treeview.bind('<<TreeviewSelect>>')
        self.runqueue_treeview.grid(column = 4, row = 0,columnspan=3, sticky=W)

        # Run queue table scrollbar
        self.runqueue_scroll = Scrollbar(self, orient = VERTICAL, \
                                         command = self.runqueue_treeview \
                                                       .yview, \
                                         width = 15)
        self.runqueue_scroll.grid(column=7,row=0, sticky = NS)
        self.runqueue_treeview.configure(yscrollcommand = self.runqueue_scroll \
                                                              .set)

        # Move and delete an acquisition from the run queue.
        self.moveup_button = Button(self, text = 'Move File Up', \
                                    command = self.moveup, state = DISABLED)
        self.moveup_button.grid(column=4, row=1)

        self.movedown_button = Button(self, text = 'Move File Down', \
                                      command = self.movedown, state = DISABLED)
        self.movedown_button.grid(column=5, row=1)

        self.delete_button = Button(self, text = 'Delete From Queue', \
                                    command = self.deletefile, state = DISABLED)
        self.delete_button.grid(column=6, row=1)

root = None

def on_closing():
    ''' Overriding the standard on_closing method of the Tk window.'''

    global root

    if tkMessageBox.askokcancel("Quit", "Do you want to quit? The current" + \
                                        " acquisition will END!"):
        root.destroy()

def run_iotk(termin_queueout, termin_queuein, termout_queueout, \
             termout_queuein, termerr_queueout, termerr_queuein, \
             rs_queueout, rs_queuein):
    ''' The method called by the Manager class; the main method that starts all
    windows.
    '''

    global root

    root = Tk()
    style = ttk.Style()
    root.geometry('1200x750')

    run_scheduler = RunScheduler(rs_queueout, rs_queuein, master=root)
    inp = UserInput(termin_queueout, termin_queuein, master=root)
    otp = OutputMonitor(termout_queueout, termout_queuein, master=root)
    err = OutputMonitor(termerr_queueout, termerr_queuein, master=root)

    root.title("FOSOFtware: Run Dictionary Manager")
    inp.title("FOSOFtware: User Input")
    otp.title("FOSOFtware: Output")
    err.title("FOSOFtware: Error Log")

    root.protocol("WM_DELETE_WINDOW", on_closing)
    inp.protocol("WM_DELETE_WINDOW", on_closing)
    otp.protocol("WM_DELETE_WINDOW", on_closing)
    err.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()
