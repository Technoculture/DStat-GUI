#!/usr/bin/env python
# -*- coding: utf-8 -*-
#     DStat Interface - An interface for the open hardware DStat potentiostat
#     Copyright (C) 2014  Michael D. M. Dryden - 
#     Wheeler Microfluidics Laboratory <http://microfluidics.utoronto.ca>
#         
#     
#     This program is free software: you can redistribute it and/or modify
#     it under the terms of the GNU General Public License as published by
#     the Free Software Foundation, either version 3 of the License, or
#     (at your option) any later version.
#     
#     This program is distributed in the hope that it will be useful,
#     but WITHOUT ANY WARRANTY; without even the implied warranty of
#     MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#     GNU General Public License for more details.
#     
#     You should have received a copy of the GNU General Public License
#     along with this program.  If not, see <http://www.gnu.org/licenses/>.

""" GUI Interface for Wheeler Lab DStat """

import sys,os
from errors import InputError, VarError, ErrorLogger
_logger = ErrorLogger(sender="dstat-interface-main")

try:
    import pygtk
    pygtk.require('2.0')
except ImportError:
    _logger.error('PyGTK 2.0 not available', 'ERR')
    sys.exit(1)
try:
    import gtk
except ImportError:
    _logger.error('GTK not available', 'ERR')
    sys.exit(1)
try:
    import gobject
except ImportError:
    _logger.error('gobject not available', 'ERR')
    sys.exit(1)

os.chdir(os.path.dirname(os.path.abspath(sys.argv[0])))

import interface.save as save
import dstat_comm as comm
import interface.exp_window as exp_window
import interface.adc_pot as adc_pot
import plot
import microdrop

from serial import SerialException
import multiprocessing
import time

class Main(object):
    """Main program """
    def __init__(self):
        self.builder = gtk.Builder()
        self.builder.add_from_file('interface/dstatinterface.glade')
        self.builder.connect_signals(self)
        self.cell = gtk.CellRendererText()

        #create instance of interface components
        self.statusbar = self.builder.get_object('statusbar')
        self.ocp_disp = self.builder.get_object('ocp_disp')
        self.window = self.builder.get_object('window1')
        self.aboutdialog = self.builder.get_object('aboutdialog1')
        self.rawbuffer = self.builder.get_object('databuffer1')
        self.databuffer = self.builder.get_object('databuffer2')
        self.stopbutton = self.builder.get_object('pot_stop')
        self.startbutton = self.builder.get_object('pot_start')
        self.adc_pot = adc_pot.adc_pot()
        
        self.error_context_id = self.statusbar.get_context_id("error")
        self.message_context_id = self.statusbar.get_context_id("message")
        
        self.plotwindow = self.builder.get_object('plotbox')
        
        self.exp_window = exp_window.Experiments(self.builder)
        
        #setup autosave
        self.autosave_checkbox = self.builder.get_object('autosave_checkbutton')
        self.autosavedir_button = self.builder.get_object('autosavedir_button')
        self.autosavename = self.builder.get_object('autosavename')
        
        self.plot = plot.plotbox(self.plotwindow)
        
        #fill adc_pot_box
        self.adc_pot_box = self.builder.get_object('gain_adc_box')
        self.adc_pot_container = self.adc_pot.builder.get_object('vbox1')
        self.adc_pot_container.reparent(self.adc_pot_box)
        
        #fill serial
        self.serial_connect = self.builder.get_object('serial_connect')
        self.serial_disconnect = self.builder.get_object('serial_disconnect')
        self.serial_disconnect.set_sensitive(False)
        self.serial_combobox = self.builder.get_object('serial_combobox')
        self.serial_combobox.pack_start(self.cell, True)
        self.serial_combobox.add_attribute(self.cell, 'text', 0)
        
        self.serial_liststore = self.builder.get_object('serial_liststore')
        self.serial_devices = comm.SerialDevices()
        
        for i in self.serial_devices.ports:
            self.serial_liststore.append([i])
        
        self.serial_combobox.set_active(0)
        
        #initialize experiment selection combobox
        self.expcombobox = self.builder.get_object('expcombobox')
        self.expcombobox.pack_start(self.cell, True)
        self.expcombobox.add_attribute(self.cell, 'text', 2)
        self.expcombobox.set_active(0)
        
        self.spinner = self.builder.get_object('spinner')

        self.mainwindow = self.builder.get_object('window1')
        self.mainwindow.set_title("DStat Interface 1.0.1")
        self.mainwindow.show_all()
        
        self.on_expcombobox_changed()

        self.expnumber = 0
        
        self.connected = False
        
        self.menu_dropbot_connect = self.builder.get_object(
                                                         'menu_dropbot_connect')
        self.menu_dropbot_disconnect = self.builder.get_object(
                                                      'menu_dropbot_disconnect')
        self.dropbot_enabled = False
        self.dropbot_triggered = False

    def on_window1_destroy(self, object, data=None):
        """ Quit when main window closed."""
        self.on_serial_disconnect_clicked()
        gtk.main_quit()

    def on_gtk_quit_activate(self, menuitem, data=None):
        """Quit when Quit selected from menu."""
        self.on_serial_disconnect_clicked()
        gtk.main_quit()

    def on_gtk_about_activate(self, menuitem, data=None):
        """Display the about window."""
        self.response = self.aboutdialog.run()  # waits for user to click close
        self.aboutdialog.hide()

    def on_expcombobox_changed(self, data=None):
        """Change the experiment window when experiment box changed."""
        model = self.expcombobox.get_model()
        _, id, _ = model[self.expcombobox.get_active()]  # id is in 2nd col
        self.statusbar.remove_all(self.error_context_id)
        if not self.exp_window.set_exp(id):
            self.statusbar.push(
                self.error_context_id, "Experiment not yet implemented")

    def on_serial_refresh_clicked(self, data=None):
        """Refresh list of serial devices."""
        self.serial_devices.refresh()
        self.serial_liststore.clear()
        
        for i in self.serial_devices.ports:
            self.serial_liststore.append([i])
            
    def on_serial_connect_clicked(self, data=None):
        """Connect and retrieve DStat version."""
        
        try:
            self.serial_connect.set_sensitive(False)
            self.version = comm.version_check(self.serial_liststore.get_value(
                                    self.serial_combobox.get_active_iter(), 0))
            
            self.statusbar.remove_all(self.error_context_id)
            
            if not len(self.version) == 2:
                self.statusbar.push(self.error_context_id, "Communication Error")
                return
            
            else:
                self.adc_pot.set_version(self.version)
                self.statusbar.push(self.error_context_id,
                                    "".join(["DStat version: ", str(self.version[0]),
                                    ".", str(self.version[1])])
                                )
                                
                comm.read_settings()

                self.start_ocp()
                self.connected = True
                self.serial_connect.set_sensitive(False)
                self.serial_disconnect.set_sensitive(True)
        
        except AttributeError as err:
            _logger.error(err, 'WAR')
            self.serial_connect.set_sensitive(True)
        except TypeError as err:
            _logger.error(err, 'WAR')
            self.serial_connect.set_sensitive(True)
            
    def on_serial_disconnect_clicked(self, data=None):
        """Disconnect from DStat."""
        if self.connected == False:
            return
        
        try:
            if self.ocp_is_running:
                self.stop_ocp()
            else:
                self.on_pot_stop_clicked()
            comm.serial_instance.ctrl_pipe_p.send("DISCONNECT")
            comm.serial_instance.proc.terminate()
            
        except AttributeError as err:
            _logger.error(err, 'WAR')
            pass
        
        self.connected = False
        self.serial_connect.set_sensitive(True)
        self.serial_disconnect.set_sensitive(False)

    def start_ocp(self):
        """Start OCP measurements."""
        if self.version[0] >= 1 and self.version[1] >= 2:
            _logger.error("Start OCP", "INFO")
            comm.serial_instance.proc_pipe_p.send(comm.OCPExp())
            self.ocp_proc = (gobject.io_add_watch(comm.serial_instance.data_pipe_p,
                                                 gobject.IO_IN,
                                                 self.ocp_running_data),
                             gobject.io_add_watch(comm.serial_instance.proc_pipe_p,
                                                  gobject.IO_IN,
                                                  self.ocp_running_proc)
                            )
            self.ocp_is_running = True
            
        else:
            _logger.error("OCP measurements not supported on v1.1 boards.",'INFO')
        return
        
    def stop_ocp(self):
        """Stop OCP measurements."""
        if self.version[0] >= 1 and self.version[1] >= 2:
            _logger.error("Stop OCP",'INFO')
            comm.serial_instance.ctrl_pipe_p.send('a')

            for i in self.ocp_proc:
                gobject.source_remove(i)
            while self.ocp_running_proc(None, None):
                pass
            self.ocp_is_running = False
            self.ocp_disp.set_text("")
        else:
            logger.error("OCP measurements not supported on v1.1 boards.",'INFO')
        return
        
    def ocp_running_data(self, source, condition):
        """Receive OCP value from experiment process and update ocp_disp field
        
        Returns:
        True -- when experiment is continuing to keep function in GTK's queue.
        False -- when experiment process signals EOFError or IOError to remove
            function from GTK's queue.
        """
        
        try:                    
            incoming = comm.serial_instance.data_pipe_p.recv()

            if isinstance(incoming, basestring): # test if incoming is str
                self.on_serial_disconnect_clicked()
                return False
                
            data = "".join(["OCP: ",
                            "{0:.3f}".format(incoming),
                            " V"])
            self.ocp_disp.set_text(data)

            return True
            
        except EOFError:
            return False
        except IOError:
            return False

    def ocp_running_proc(self, source, condition):
        """Handles signals on proc_pipe_p for OCP.
        
        Returns:
        True -- when experiment is continuing to keep function in GTK's queue.
        False -- when experiment process signals EOFError or IOError to remove
            function from GTK's queue.
        """
        _logger.error("ocp_running_proc()",'DBG')
        
        try:
            proc_buffer = comm.serial_instance.proc_pipe_p.recv()
            _logger.error("".join(("ocp_running_proc: ", proc_buffer)), 'DBG')
            if proc_buffer in ["DONE", "SERIAL_ERROR", "ABORT"]:                
                if proc_buffer == "SERIAL_ERROR":
                    self.on_serial_disconnect_clicked()
                
                while comm.serial_instance.data_pipe_p.poll():
                    comm.serial_instance.data_pipe_p.recv()
                
                gobject.source_remove(self.ocp_proc[0])
                return False
                    
            return True
            
        except EOFError:
            return False
        except IOError:
            return False
            
    def on_pot_start_clicked(self, data=None):
        """Run currently visible experiment."""
        def exceptions():
            """ Cleans up after errors """
            if self.dropbot_enabled == True:
                if self.dropbot_triggered == True:
                    self.dropbot_triggered = False
                    self.microdrop.reply(microdrop.EXPFINISHED)
                    self.microdrop_proc = gobject.timeout_add(500,
                                                          self.microdrop_listen)
            self.spinner.stop()
            self.startbutton.set_sensitive(True)
            self.stopbutton.set_sensitive(False)
            self.start_ocp()
        
        def run_experiment():
            """ Starts experiment """
            self.plot.clearall()
            self.plot.changetype(self.current_exp)

            comm.serial_instance.proc_pipe_p.send(self.current_exp)

            self.plot_proc = gobject.timeout_add(200,
                                                self.experiment_running_plot)
            self.experiment_proc = (
                    gobject.io_add_watch(comm.serial_instance.data_pipe_p,
                                            gobject.IO_IN,
                                            self.experiment_running_data),
                    gobject.io_add_watch(comm.serial_instance.proc_pipe_p,
                                            gobject.IO_IN,
                                            self.experiment_running_proc)
                                    )
        
        
        self.stop_ocp()
        
        while comm.serial_instance.data_pipe_p.poll(): # Clear data pipe
            comm.serial_instance.data_pipe_p.recv()
        
        selection = self.expcombobox.get_active()
        parameters = {}
        parameters['version'] = self.version
        
        if self.adc_pot.buffer_toggle.get_active(): # True if box checked
            parameters['adc_buffer'] = "2"
        else:
            parameters['adc_buffer'] = "0"
            
        if self.adc_pot.short_toggle.get_active():
            parameters['re_short'] = "1"
        else:
            parameters['re_short'] = "0"
        
        srate_model = self.adc_pot.srate_combobox.get_model()
        pga_model = self.adc_pot.pga_combobox.get_model()
        gain_model = self.adc_pot.gain_combobox.get_model()
        
        parameters['adc_rate'] = srate_model.get_value(
               self.adc_pot.srate_combobox.get_active_iter(), 2)  # third column
        parameters['adc_pga'] = pga_model.get_value(
                                 self.adc_pot.pga_combobox.get_active_iter(), 2)
        parameters['gain'] = gain_model.get_value(
                                self.adc_pot.gain_combobox.get_active_iter(), 2)
        
        self.line = 0
        self.lastline = 0
        self.lastdataline = 0
        
        self.spinner.start()
        self.startbutton.set_sensitive(False)
        self.stopbutton.set_sensitive(True)
        self.statusbar.remove_all(self.error_context_id)
        
        try:
            if selection == 0:  # CA
                # Add experiment parameters to existing
                parameters.update(self.exp_window.get_params('cae'))
                if not parameters['potential']:
                    raise InputError(parameters['potential'],
                                     "Step table is empty")
                
                
                self.current_exp = comm.Chronoamp(parameters)
                
                self.rawbuffer.set_text("")
                self.rawbuffer.place_cursor(self.rawbuffer.get_start_iter())
                
                for i in self.current_exp.commands:
                    self.rawbuffer.insert_at_cursor(i)
                   
                run_experiment()
                
                return
        
            elif selection == 1: # LSV
                parameters.update(self.exp_window.get_params('lsv'))
                
                #check parameters are within hardware limits
                if (parameters['clean_mV'] > 1499 or 
                        parameters['clean_mV'] < -1500):
                    raise InputError(parameters['clean_mV'],
                                     "Clean potential exceeds hardware limits.")
                if (parameters['dep_mV'] > 1499 or
                        parameters['dep_mV'] < -1500):
                    raise InputError(parameters['dep_mV'],
                                "Deposition potential exceeds hardware limits.")
                if (parameters['clean_s'] < 0):
                    raise InputError(parameters['clean_s'],
                                     "Clean time cannot be negative.")
                if (parameters['dep_s'] < 0):
                    raise InputError(parameters['dep_s'],
                                     "Deposition time cannot be negative.")
                if (parameters['start'] > 1499 or parameters['start'] < -1500):
                    raise InputError(parameters['start'],
                                     "Start parameter exceeds hardware limits.")
                if (parameters['stop'] > 1499 or parameters['stop'] < -1500):
                    raise InputError(parameters['stop'],
                                     "Stop parameter exceeds hardware limits.")
                if (parameters['slope'] > 2000 or parameters['slope'] < 1):
                    raise InputError(parameters['slope'],
                                     "Slope parameter exceeds hardware limits.")
                if parameters['start'] == parameters['stop']:
                    raise InputError(parameters['start'],
                                     "Start cannot equal Stop.")

                
                self.current_exp = comm.LSVExp(parameters)
                run_experiment()
                
                return
            
            elif selection == 2: # CV
                parameters.update(self.exp_window.get_params('cve'))
                
                # check parameters are within hardware limits
                if (parameters['clean_mV'] > 1499 or
                        parameters['clean_mV'] < -1500):
                    raise InputError(parameters['clean_mV'],
                                     "Clean potential exceeds hardware limits.")
                if (parameters['dep_mV'] > 1499 or
                        parameters['dep_mV'] < -1500):
                    raise InputError(parameters['dep_mV'],
                                "Deposition potential exceeds hardware limits.")
                if (parameters['clean_s'] < 0):
                    raise InputError(parameters['clean_s'],
                                     "Clean time cannot be negative.")
                if (parameters['dep_s'] < 0):
                    raise InputError(parameters['dep_s'],
                                     "Deposition time cannot be negative.")
                if (parameters['start'] > 1499 or parameters['start'] < -1500):
                    raise InputError(parameters['start'],
                                     "Start parameter exceeds hardware limits.")
                if (parameters['slope'] > 2000 or parameters['slope'] < 1):
                    raise InputError(parameters['slope'],
                                     "Slope parameter exceeds hardware limits.")
                if (parameters['v1'] > 1499 or parameters['v1'] < -1500):
                    raise InputError(parameters['v1'],
                                  "Vertex 1 parameter exceeds hardware limits.")
                if (parameters['v2'] > 1499 or parameters['v2'] < -1500):
                    raise InputError(parameters['v2'],
                                  "Vertex 2 parameter exceeds hardware limits.")
                if (parameters['scans'] < 1 or parameters['scans'] > 255):
                    raise InputError(parameters['scans'], 
                                     "Scans parameter outside limits.")
                if parameters['v1'] == parameters['v2']:
                    raise InputError(parameters['v1'],
                                     "Vertex 1 cannot equal Vertex 2.")
                
                
                self.current_exp = comm.CVExp(parameters)
                run_experiment()
                
                return
                
            elif selection == 3:  # SWV
                parameters.update(self.exp_window.get_params('swv'))
                
                if parameters['cyclic_checkbutton'] :
                    if parameters['scans'] < 1:
                        raise InputError(parameters['scans'],
                                        "Must have at least one scan.")
                else:
                    parameters['scans'] = 0
                
                # check parameters are within hardware limits (doesn't
                # check if pulse will go out of bounds, but instrument
                # checks this (I think))
                if (parameters['clean_mV'] > 1499 or
                        parameters['clean_mV'] < -1500):
                    raise InputError(parameters['clean_mV'],
                                     "Clean potential exceeds hardware limits.")
                if (parameters['dep_mV'] > 1499 or
                        parameters['dep_mV'] < -1500):
                    raise InputError(parameters['dep_mV'],
                                "Deposition potential exceeds hardware limits.")
                if (parameters['clean_s'] < 0):
                    raise InputError(parameters['clean_s'],
                                     "Clean time cannot be negative.")
                if (parameters['dep_s'] < 0):
                    raise InputError(parameters['dep_s'],
                                     "Deposition time cannot be negative.")
                if (parameters['start'] > 1499 or parameters['start'] < -1500):
                    raise InputError(parameters['start'],
                                     "Start parameter exceeds hardware limits.")
                if (parameters['step'] > 200 or parameters['step'] < 1):
                    raise InputError(parameters['step'],
                               "Step height parameter exceeds hardware limits.")
                if (parameters['stop'] > 1499 or parameters['stop'] < -1500):
                    raise InputError(parameters['stop'],
                                      "Stop parameter exceeds hardware limits.")
                if (parameters['pulse'] > 150 or parameters['pulse'] < 1):
                    raise InputError(parameters['pulse'],
                              "Pulse height parameter exceeds hardware limits.")
                if (parameters['freq'] < 1 or parameters['freq'] > 1000):
                    raise InputError(parameters['freq'],
                                     "Frequency parameter outside limits.")
                if parameters['start'] == parameters['stop']:
                    raise InputError(parameters['start'],
                                     "Start cannot equal Stop.")
                    
                
                self.current_exp = comm.SWVExp(parameters)
                run_experiment()
                
                return
        
            elif selection == 4:  # DPV
                parameters.update(self.exp_window.get_params('dpv'))
                
                if (parameters['clean_mV'] > 1499 or
                        parameters['clean_mV'] < -1500):
                    raise InputError(parameters['clean_mV'],
                                     "Clean potential exceeds hardware limits.")
                if (parameters['dep_mV'] > 1499 or
                        parameters['dep_mV'] < -1500):
                    raise InputError(parameters['dep_mV'],
                                "Deposition potential exceeds hardware limits.")
                if (parameters['clean_s'] < 0):
                    raise InputError(parameters['clean_s'],
                                     "Clean time cannot be negative.")
                if (parameters['dep_s'] < 0):
                    raise InputError(parameters['dep_s'],
                                     "Deposition time cannot be negative.")
                if (parameters['start'] > 1499 or parameters['start'] < -1500):
                    raise InputError(parameters['start'],
                                     "Start parameter exceeds hardware limits.")
                if (parameters['step'] > 200 or parameters['step'] < 1):
                    raise InputError(parameters['step'],
                               "Step height parameter exceeds hardware limits.")
                if (parameters['stop'] > 1499 or parameters['stop'] < -1500):
                    raise InputError(parameters['stop'],
                                     "Stop parameter exceeds hardware limits.")
                if (parameters['pulse'] > 150 or parameters['pulse'] < 1):
                    raise InputError(parameters['pulse'],
                        "Pulse height parameter exceeds hardware limits.")
                if (parameters['period'] < 1 or parameters['period'] > 1000):
                    raise InputError(parameters['period'], 
                                    "Period parameter outside limits.")
                if (parameters['width'] < 1 or parameters['width'] > 1000):
                    raise InputError(parameters['width'],
                                     "Width parameter outside limits.")
                if parameters['period'] <= parameters['width']:
                    raise InputError(parameters['width'],
                                     "Width must be less than period.")
                if parameters['start'] == parameters['stop']:
                    raise InputError(parameters['start'],
                                     "Start cannot equal Stop.")
                
                
                self.current_exp = comm.DPVExp(parameters)
                run_experiment()
                
                return
                
            elif selection == 6:  # PD                    
                parameters.update(self.exp_window.get_params('pde'))
                
                if (parameters['time'] <= 0):
                    raise InputError(parameters['clean_s'],
                                     "Time must be greater than zero.")
                if (parameters['time'] > 65535):
                    raise InputError(parameters['clean_s'],
                                     "Time must fit in 16-bit counter.")
                
                
                self.current_exp = comm.PDExp(parameters)
                run_experiment()
                
                return
                            
            elif selection == 7:  # POT
                if not (self.version[0] >= 1 and self.version[1] >= 2):
                    self.statusbar.push(self.error_context_id, 
                                "v1.1 board does not support potentiometry.")
                    exceptions()
                    return
                    
                parameters.update(self.exp_window.get_params('pot'))
                
                if (parameters['time'] <= 0):
                    raise InputError(parameters['clean_s'],
                                     "Time must be greater than zero.")
                if (parameters['time'] > 65535):
                    raise InputError(parameters['clean_s'],
                                     "Time must fit in 16-bit counter.")
                
                
                self.current_exp = comm.PotExp(parameters)
                run_experiment()
                
                return
                
            else:
                self.statusbar.push(self.error_context_id, 
                                    "Experiment not yet implemented.")
                exceptions()
                
        except ValueError as i:
            print i
            self.statusbar.push(self.error_context_id, 
                                "Experiment parameters must be integers.")
            exceptions()
        
        except KeyError as i:
            print i
            self.statusbar.push(self.error_context_id, 
                                "Experiment parameters must be integers.")
            exceptions()
        
        except InputError as err:
            print err
            self.statusbar.push(self.error_context_id, err.msg)
            exceptions()
        
        except SerialException as err:
            print err
            self.statusbar.push(self.error_context_id, 
                                "Could not establish serial connection.")
            exceptions()

        except AssertionError as err:
            print err
            self.statusbar.push(self.error_context_id, str(err))
            exceptions()

    def experiment_running_data(self, source, condition):
        """Receive data from experiment process and add to current_exp.data.
        Run in GTK main loop.
        
        Returns:
        True -- when experiment is continuing to keep function in GTK's queue.
        False -- when experiment process signals EOFError or IOError to remove
            function from GTK's queue.
        """
        try:
            incoming = comm.serial_instance.data_pipe_p.recv()
            if isinstance(incoming, basestring): # Test if incoming is str
                self.experiment_done()
                self.on_serial_disconnect_clicked()
                return False
            
            self.line, data = incoming
            if self.line > self.lastdataline:
                self.current_exp.data += [[], []]
                if len(data) > 2:
                    self.current_exp.data_extra += [[], []]
                self.lastdataline = self.line
            for i in range(2):
                self.current_exp.data[2*self.line+i].append(data[i])
                if len(data) > 2:
                    self.current_exp.data_extra[2*self.line+i].append(
                                                                    data[i+2])
            return True

        except EOFError as err:
            print err
            self.experiment_done()
            return False
        except IOError as err:
            print err
            self.experiment_done()
            return False
            
    def experiment_running_proc(self, source, condition):
        """Receive proc signals from experiment process.
        Run in GTK main loop.
        
        Returns:
        True -- when experiment is continuing to keep function in GTK's queue.
        False -- when experiment process signals EOFError or IOError to remove
            function from GTK's queue.
        """
        try:
            proc_buffer = comm.serial_instance.proc_pipe_p.recv()

            if proc_buffer in ["DONE", "SERIAL_ERROR", "ABORT"]:
                self.experiment_done()
                if proc_buffer == "SERIAL_ERROR":
                    self.on_serial_disconnect_clicked()
                
            else:
                e = "Unrecognized experiment return code "
                e += proc_buffer
                _logger.error(e, 'WAR')
            
            return False

        except EOFError as err:
            _logger.error(err, 'WAR')
            self.experiment_done()
            return False
        except IOError as err:
            _logger.error(err, 'WAR')
            self.experiment_done()
            return False
            
    def experiment_running_plot(self):
        """Plot all data in current_exp.data.
        Run in GTK main loop. Always returns True so must be manually
        removed from GTK's queue.
        """
        if self.line > self.lastline:
            self.plot.addline()
            # make sure all of last line is added
            self.plot.updateline(self.current_exp, self.lastline) 
            self.lastline = self.line
        self.plot.updateline(self.current_exp, self.line)
        self.plot.redraw()
        return True

    def experiment_done(self):
        """Clean up after data acquisition is complete. Update plot and
        copy data to raw data tab. Saves data if autosave enabled.
        """
        gobject.source_remove(self.experiment_proc[0])
        gobject.source_remove(self.plot_proc)  # stop automatic plot update
        self.experiment_running_plot()  # make sure all data updated on plot

        self.databuffer.set_text("")
        self.databuffer.place_cursor(self.databuffer.get_start_iter())
        self.rawbuffer.insert_at_cursor("\n")
        self.rawbuffer.set_text("")
        self.rawbuffer.place_cursor(self.rawbuffer.get_start_iter())

        for i in self.current_exp.commands:
            self.rawbuffer.insert_at_cursor(i)

        self.rawbuffer.insert_at_cursor("\n")

        for col in zip(*self.current_exp.data):
            for row in col:
                self.rawbuffer.insert_at_cursor(str(row)+ "    ")
            self.rawbuffer.insert_at_cursor("\n")
        
        if self.current_exp.data_extra:
            for col in zip(*self.current_exp.data_extra):
                for row in col:
                    self.databuffer.insert_at_cursor(str(row)+ "    ")
                self.databuffer.insert_at_cursor("\n")
    
        if self.autosave_checkbox.get_active():
            save.autoSave(self.current_exp, self.autosavedir_button,
                          self.autosavename.get_text(), self.expnumber)
            save.autoPlot(self.plot, self.autosavedir_button,
                          self.autosavename.get_text(), self.expnumber)
            self.expnumber += 1
        
        if self.dropbot_enabled == True:
            if self.dropbot_triggered == True:
                self.dropbot_triggered = False
                self.microdrop.reply(microdrop.EXPFINISHED)
            self.microdrop_proc = gobject.timeout_add(500,
                                                      self.microdrop_listen)
        
        self.spinner.stop()
        self.startbutton.set_sensitive(True)
        self.stopbutton.set_sensitive(False)
        self.start_ocp()

    def on_pot_stop_clicked(self, data=None):
        """Stop current experiment. Signals experiment process to stop."""
        try:
            comm.serial_instance.ctrl_pipe_p.send('a')

        except AttributeError:
            pass
        except:
            _logger.error(sys.exc_info(),'WAR')
    
    def on_file_save_exp_activate(self, menuitem, data=None):
        """Activate dialogue to save current experiment data. """
        if self.current_exp:
            save.manSave(self.current_exp)
    
    def on_file_save_plot_activate(self, menuitem, data=None):
        """Activate dialogue to save current plot."""
        save.plotSave(self.plot)
    
    def on_menu_dropbot_connect_activate(self, menuitem, data=None):
        """Listen for remote control connection from µDrop."""
        self.microdrop = microdrop.microdropConnection()
        self.dropbot_enabled = True
        self.menu_dropbot_connect.set_sensitive(False)
        self.menu_dropbot_disconnect.set_sensitive(True)
        self.statusbar.push(self.message_context_id,
                            "Waiting for µDrop to connect…")
        self.microdrop_proc = gobject.timeout_add(500, self.microdrop_listen)
    
    def on_menu_dropbot_disconnect_activate(self, menuitem=None, data=None):
        """Disconnect µDrop connection and stop listening."""
        gobject.source_remove(self.microdrop_proc)
        self.microdrop.reset()
        del self.microdrop
        self.dropbot_enabled = False
        self.menu_dropbot_connect.set_sensitive(True)
        self.menu_dropbot_disconnect.set_sensitive(False)
        self.statusbar.push(self.message_context_id, "µDrop disconnected.")

    def microdrop_listen(self):
        """Manage signals from µDrop. Must be added to GTK's main loop to
        run periodically.
        """
        drdy, data = self.microdrop.listen()
        if drdy == False:
            return True

        if data == microdrop.EXP_FINISH_REQ:
            if self.dropbot_triggered:
                if self.connected:
                    self.on_pot_start_clicked()
                else:
                    _logger.error("µDrop requested experiment but DStat disconnected",
                                 'WAR')
                    self.statusbar.push(self.message_context_id,
                                        "Listen stopped—DStat disconnected.")
                    self.microdrop.reply(microdrop.EXPFINISHED)
                    self.on_menu_dropbot_disconnect_activate()
                    return False  # Removes function from GTK's main loop 
            else:
                _logger.error("µDrop requested experiment finish confirmation without starting experiment.",
                             'WAR')
                self.microdrop.reply(microdrop.EXPFINISHED)
            
        elif data == microdrop.STARTEXP:
            self.microdrop.connected = True
            self.statusbar.push(self.message_context_id, "µDrop connected.")
            self.dropbot_triggered = True
            self.microdrop.reply(microdrop.START_REP)
        else:
            _logger.error("Received invalid command from µDrop",'WAR')
            self.microdrop.reply(microdrop.INVAL_CMD)
        return True


if __name__ == "__main__":
    multiprocessing.freeze_support()
    gobject.threads_init()
    MAIN = Main()
    gtk.main()