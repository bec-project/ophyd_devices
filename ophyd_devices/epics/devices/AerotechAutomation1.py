# -*- coding: utf-8 -*-
"""
Created on Thu Nov  3 15:54:08 2022

@author: mohacsi_i
"""
import os
os.environ["EPICS_CA_ADDR_LIST"]="129.129.144.255"

from collections import OrderedDict
import warnings

import numpy as np
from time import sleep, time
import unittest
from ophyd import EpicsMotor, EpicsSignal, EpicsSignalRO

try:
    from AerotechAutomation1 import (aa1Controller, aa1Tasks, aa1TaskState, aa1DataAcquisition, 
            aa1GlobalVariables, aa1AxisIo, aa1AxisDriveDataCollection,
            aa1GlobalVariableBindings, aa1AxisPsoDistance, aa1AxisPsoWindow)
    from AerotechAutomation1Enums import AxisDataSignal, SystemDataSignal, DriveDataCaptureInput, DriveDataCaptureTrigger
except Exception:
    from .AerotechAutomation1 import (aa1Controller, aa1Tasks, aa1TaskState, aa1DataAcquisition, 
        aa1GlobalVariables, aa1AxisIo, aa1AxisDriveDataCollection,
        aa1GlobalVariableBindings, aa1AxisPsoDistance, aa1AxisPsoWindow)
    from .AerotechAutomation1Enums import AxisDataSignal, SystemDataSignal, DriveDataCaptureInput, DriveDataCaptureTrigger



AA1_IOC_NAME = "X02DA-ES1-SMP1"
AA1_AXIS_NAME = "ROTY"


class AerotechAutomation1Test(unittest.TestCase):
    _isConnected = False

    @classmethod
    def setUpClass(cls):
        try:
            # HIL testing only if there's hardware
            dev = aa1Controller(AA1_IOC_NAME+":CTRL:", name="aa1")
            dev.wait_for_connection()
            cls._isConnected = True
            print("\n")
        except Exception as ex:
            print(ex)
    
    def test_00_Instantiation(self):
        """ Test instantiation and interfaces
        
        This method tests the more abstract bluesky compatibility of the
        aerotech ophyd devices. In particular it checks the existence of the
        required schema functions (that are not called in other tests).
        """
        # Throws if IOC is not available or PVs are incorrect        
        def classTestSequence(DeviceClass, prefix, config=None, setable=False, set_value=None, flyable=False):
            dut = DeviceClass(prefix, name="dut")
            dut.wait_for_connection()       
            
            # Readable device (required)
            dut.describe()                              # Describes read()            
            dut.read()                                  # Read the device active values
            dut.trigger()
            dut.describe_configuration()                # Describes read_configuration()
            dut.read_configuration()                    # Reads device configuration
            if config is not None:
                try:
                    ret = dut.configure(config)
                    self.assertTrue(type(ret)==tuple, f"On device class {DeviceClass}: configure is expected to return a tuple")
                    self.assertTrue(isinstance(ret[0], OrderedDict), f"On device class {DeviceClass}: old configuration is expected to be an OrderedDict")
                    self.assertTrue(isinstance(ret[1], (dict, OrderedDict)), f"On device class {DeviceClass}: new configuration is expected to be dict or OrderedDict")
                except Exception:
                    pass
            # Readable device (optional)
            dut.stage()
            dut.unstage()
            # Setable device
            if setable and set_value is not None:
                try:
                    st = dut.set(set_value)
                    #dut.stop()
                    dut.check_value(set_value)
                    dut.position
                except Exception as ex:
                    warnings.warn(f"Exception occured while testing setable interface: {ex}")
            if flyable:
                try:
                    dut.configure(config)
                    st = dut.kickoff()
                    st = dut.complete()
                    ret = dut.describe_collect()
                    ret = dut.collect()
                except Exception:
                    pass            
        
        classDBase = [
            (aa1Controller, f"{AA1_IOC_NAME}:CTRL:"),
            (aa1Tasks, f"{AA1_IOC_NAME}:TASK:"),
            (aa1DataAcquisition, f"{AA1_IOC_NAME}:DAQ:"),
            (aa1GlobalVariables, f"{AA1_IOC_NAME}:VAR:"),
            (aa1GlobalVariableBindings, f"{AA1_IOC_NAME}:VAR:"),

            (EpicsMotor, f"{AA1_IOC_NAME}:{AA1_AXIS_NAME}"),
            (aa1AxisIo, f"{AA1_IOC_NAME}:{AA1_AXIS_NAME}:IO:"),
            (aa1AxisDriveDataCollection, f"{AA1_IOC_NAME}:{AA1_AXIS_NAME}:DDC:"),
            (aa1AxisPsoDistance, f"{AA1_IOC_NAME}:{AA1_AXIS_NAME}:PSO:"),
            (aa1AxisPsoWindow, f"{AA1_IOC_NAME}:{AA1_AXIS_NAME}:PSO:"),
            ]
            
        print("BSKY: Testing basic Ophyd device class interfaces")
        for DeviceClass, prefix in classDBase:
            classTestSequence(DeviceClass, prefix)
        print("BSKY: Done testing CTRL module!")

    
    
    def test_01_ControllerProxy(self):
        # Throws if IOC is not available or PVs are incorrect
        dev = aa1Controller(AA1_IOC_NAME+":CTRL:", name="aa1")
        dev.wait_for_connection()
        
        print("CTRL: Testing basic controller readback")
        # Check if controller info was loaded correctly
        self.assertTrue(len(dev.controllername.get())>0, "Controller name seems invalid")
        self.assertTrue(len(dev.serialnumber.get())>0, "Controller serial number seems invalid")
        self.assertTrue(dev.axiscount.get()>0, "Maximum controller axis count seems invalid")
        self.assertTrue(dev.taskcount.get()>0, "Maximum controller task count seems invalid")
        print("CTRL: Done testing CTRL module!")


    def test_02_TaskProxy(self):
        # Throws if IOC is not available or PVs are incorrect        
        dev = aa1Tasks(AA1_IOC_NAME+":TASK:", name="tsk")
        dev.wait_for_connection()
        
        print("\nTASK: Testing the 'execute' command (direct string execution)")
        # Attempt to run a short test script using the Execute interface (real)
        text = "$rreturn[0]=3.141592"
        rbv = dev.execute(text, mode="Double", taskIndex=3)
        
        self.assertTrue(dev._executeMode.get() in ["Double", 3], f"Expecting double return type for execution, but got: {dev._executeMode.get()}")
        self.assertTrue(dev.taskIndex.get()==3, "Execution must happen on task 3")
        self.assertTrue(rbv=="Result (double): 3.141592", f"Unexpected reply from execution: {rbv}")
        # Attempt to run a short test script using the Execute interface (integer)
        text = "$ireturn[0]=42"
        rbv = dev.execute(text, mode="Int", taskIndex=4)
        self.assertTrue(dev.taskIndex.get()==4, "Execution must happen on task 1")
        self.assertTrue(rbv=="Result (int): 42", f"Unexpected reply from execution: {rbv}")

        print("TASK: Testing the 'file' interface")       
        # Write and read back a file
        filename = "unittesting.ascript"
        text =  "program\nvar $positions[2] as real\nend"
        if len(text)>40:
            print(f"\tWARN: Program text is too long for EPICS string: {len(text)}")
        
        dev.writeFile(filename, text)
        contents = dev.readFile(filename)
        self.assertTrue(contents==text, "File contents changed on readback")

        print("TASK: Testing the 'run' command (run an existing file)")
        # Send another empty program
        filename = "unittesting2.ascript"
        text =  "program\nvar $positions[2] as real\nend"
        dev.runScript(filename, taskIndex=3, filetext=text)
        
        print("TASK: Testing bluesky interface with free text)")
        dev.configure({'text': "$rreturn[0]=137.036", 'taskIndex': 4, 'mode': "Double"})
        dev.kickoff().wait()
        dev.complete().wait()
        rbv = dev._executeReply.get()
        self.assertTrue(dev._executeMode.get() in ["Double", 3], f"Expecting double return type for execution, but got: {dev._executeMode.get()}")
        self.assertTrue(dev.taskIndex.get()==4, "Execution must happen on task 4")
        self.assertTrue(rbv=="Result (double): 137.036000", f"Unexpected reply from execution: {rbv}")                
        print("TASK: Done testing TASK module!")

        
    def test_03_DataCollectionProxy(self):
        """ This tests the controller data collection
        
            Test for testing the controller data collection that occurs at a
            fixed frequency. This interface is not so important if there's 
            hardware synchronization.
        """
        return
        # Throws if IOC is not available or PVs are incorrect
        dev = aa1DataAcquisition(AA1_IOC_NAME+":DAQ:", name="daq")
        dev.wait_for_connection()
        
        print("\nDAQ: Testing the controller configuration")
        self.assertTrue(dev.status.get()==0, "DAQ must be idle to start the tests")
        self.assertTrue(dev.points_max.get()>30000, "The test requires at least 30000 point buffer")

        ######################################################################
        # Test configuration 1
        print("DAQ: Running a short test run")
        dev.startConfig(3000, "1kHz")
        dev.addSystemSignal(SystemDataSignal.DataCollectionSampleTime)
        dev.addAxisSignal(0, AxisDataSignal.PositionFeedback)
        self.assertTrue(dev.signal_num.get()==2, "Expected 2 data sources")
        # Run the data acquisition (run blocks and returns array)
        _ = dev.run()
        # Check post-run parameter values
        self.assertTrue(dev.points_total.get()==3000, "Expected to have 3k points")
        self.assertTrue(dev.points_collected.get()==3000, "Expected to record 3k points, did {dev.points_collected.value}")

        print("DAQ: Checking the returned array")
        arr = dev.dataReadBack()
        self.assertTrue(arr.size==6000, f"Unexpected data array size {arr.size}")
        self.assertTrue(arr.shape==(3000,2), f"Unexpected data array shape {arr.size}")
        
        ######################################################################
        # Test manual configuration 2
        print("DAQ: Running a short test run")
        dev.startConfig(2800, "1kHz")
        dev.addSystemSignal(SystemDataSignal.DataCollectionSampleTime)
        dev.addAxisSignal(0, AxisDataSignal.PositionFeedback)
        dev.addAxisSignal(0, AxisDataSignal.VelocityFeedback)
        self.assertTrue(dev.signal_num.get()==3, "Expected 3 data sources")
        # Run the data acquisition (run blocks and returns array)
        _ = dev.run()
        # Check post-run parameter values
        self.assertTrue(dev.points_total.get()==2800, f"Expected to have 2.8k points, got {dev.points_total.get()}")
        self.assertTrue(dev.points_collected.get()==2800, f"Expected to record 2.8k points, got {dev.points_collected.get()}")

        print("DAQ: Checking the returned array")
        arr = dev.dataReadBack()
        self.assertTrue(arr.size==8400, f"Unexpected data array size {arr.size}")
        self.assertTrue(arr.shape==(2800,3), f"Unexpected data array shape {arr.size}")
        print("DAQ: Done testing DAQ module!")


    def test_04_GlobalVariables1(self):
        """Test the basic read/write global variable interface
        """
        # Throws if IOC is not available or PVs are incorrect
        dev = aa1GlobalVariables(AA1_IOC_NAME+":VAR:", name="gvar")
        polled = aa1GlobalVariableBindings(AA1_IOC_NAME+":VAR:", name="pvar")  
        dev.wait_for_connection()
        polled.wait_for_connection()
        
        print("\nVAR: Checking available memory")
        self.assertTrue(dev.num_int.get()>=32, "At least 32 integer variables are needed for this test")
        self.assertTrue(dev.num_real.get()>=32, "At least 32 real variables are needed for this test")
        self.assertTrue(dev.num_string.get()>=32, "At least 32 string[256] variables are needed for this test")

        print("VAR: Setting and checking a few variables")
        # Use random variables for subsequent runs
        val_f = 100*np.random.random()
        dev.writeFloat(11, val_f)
        rb_f = dev.readFloat(11)
        self.assertEqual(val_f, rb_f, f"Floating point readback value changed, read {rb_f} instead of {val_f}")
        rb_f = dev.readFloat(10, 4)
        self.assertEqual(val_f, rb_f[1], f"Floating point array readback value changed, read {rb_f[1]} instead of {val_f}")

        val_i = 1+int(100*np.random.random())
        dev.writeInt(13, val_i)
        rb_i = dev.readInt(13)
        self.assertEqual(val_i, rb_i, f"Integer readback value changed, read {rb_i} instead of {val_i}")
        rb_i = dev.readInt(10, 4)       
        self.assertEqual(val_i, rb_i[3], f"Integer array readback value changed, read {rb_i[3]} instead of {val_i}")

        val_i =1+int(100*np.random.random())
        dev.writeInt(13, val_i)
        rb_i = dev.readInt(13)
        self.assertEqual(val_i, rb_i, f"Integer readback value changed, read {rb_i} instead of {val_i}")
        rb_i = dev.readInt(10, 4)       
        self.assertEqual(val_i, rb_i[3], f"Integer array readback value changed, read {rb_i[3]} instead of {val_i}")

        val_s = np.random.choice(['f', 'o', 'o', 'b', 'a', 'r'], 6)
        val_s = ''.join(val_s)
        dev.writeString(7, val_s)
        rb_s = dev.readString(7)
        self.assertEqual(val_s, rb_s, f"String readback value changed, read {rb_s} instead of {val_s}")
        print("VAR: Done testing VAR module basic functionality!")


    def test_05_GlobalVariables2(self):
        """Test the direct global variable bindings together with the task and 
        standard global variable interfaces.        
        """
        
        # Throws if IOC is not available or PVs are incorrect
        var = aa1GlobalVariables(AA1_IOC_NAME+":VAR:", name="gvar")
        var.wait_for_connection()
        dev = aa1GlobalVariableBindings(AA1_IOC_NAME+":VAR:", name="var")
        dev.wait_for_connection()
        tsk = aa1Tasks(AA1_IOC_NAME+":TASK:", name="tsk")
        tsk.wait_for_connection()
        
        print("\nVAR: Checking the direct global variable bindings")
        # Use random variables for subsequent runs
        val_f = 100*np.random.random()
        dev.float16.set(val_f, settle_time=0.91).wait() # settle time seems to be ignored by ophyd

        rb_f = dev.float16.value
        self.assertEqual(val_f, dev.float16.value, f"Floating point readback value changed, read {rb_f}, expected {val_f}")
        #rb_f = dev.readFloat(10, 4)
        #self.assertEqual(val_f, rb_f[1], f"Floating point array readback value changed, read {rb_f[1]} instead of {val_f}")

        val_i = 1+int(100*np.random.random())
        dev.int8.set(val_i, settle_time=0.91).wait() 
        rb_i = dev.int8.value
        self.assertEqual(val_i, dev.int8.value, f"Integer readback value changed, read {rb_i}, expected {val_i}")
        #rb_i = dev.readInt(10, 4)       
        #self.assertEqual(val_i, rb_i[3], f"Integer array readback value changed, read {rb_i[3]} instead of {val_i}")

        val_s = np.random.choice(['f', 'o', 'o', 'b', 'a', 'r'], 6)
        val_s = ''.join(val_s)
        dev.str4.set(val_s, settle_time=0.91).wait() 
        rb_s = dev.str4.value
        self.assertEqual(val_s, rb_s, f"String readback value changed, read {rb_s} instead of {val_s}")
        print("VAR: Done testing VAR module direct bindings!")

                
    def test_06_MotorRecord(self):
        """ Tests the basic move functionality of the MotorRecord
        """
        
        mot = EpicsMotor(AA1_IOC_NAME+ ":" + AA1_AXIS_NAME, name="x")
        mot.wait_for_connection()
        print("\nMR: Checking the standard EPICS motor record")
        
        # Four test with absolute moves
        dist = 30 + 50.0 * np.random.random()
        target = mot.position + dist
        print(f"Absolute move to {target}, distance: {dist}")
        mot.move(target, wait=True)
        self.assertTrue(np.abs(target-mot.position)<0.1, f"Final position {mot.position} is too far from target {target} (1)")

        dist = 30 + 50.0 * np.random.random()
        target = mot.position - dist
        print(f"Absolute move to {target}, distance: {dist}")
        mot.move(target, wait=True)
        self.assertTrue(np.abs(target-mot.position)<0.1, f"Final position {mot.position} is too far from target {target} (2)")

        dist = 30 + 50.0 * np.random.random()
        target = mot.position+dist
        print(f"Absolute move to {target}, distance: {dist}")
        mot.move(target, wait=True)
        self.assertTrue(np.abs(target-mot.position)<0.1, f"Final position {mot.position} is too far from target {target} (3)")

        dist = 30 + 50.0 * np.random.random()
        target = mot.position - dist
        print(f"Absolute move to {target}, distance: {dist}")
        mot.move(target, wait=True)
        self.assertTrue(np.abs(target-mot.position)<0.1, f"Final position {mot.position} is too far from target {target} (4)")
        print("MR: Done testing MotorRecord!")


    def test_07_AxisIo(self):   
        # Throws if IOC is not available or PVs are incorrect
        dev = aa1AxisIo(AA1_IOC_NAME+ ":" + AA1_AXIS_NAME + ":IO:", name="io")
        dev.wait_for_connection()
        dev.polllvl.set(1, settle_time=0.5).wait() 
        print("\nAX:IO: Checking axis IO")
    
        # Writing random values to analog/digital outputs        
        for ii in range(5):
            val_f = np.random.random()
            dev.setAnalog(0, val_f)
            self.assertAlmostEqual(dev.ao.get(), val_f, 2, "Unexpected readback on analog output")
        print("Digital")
        for ii in range(5):
            val_b = round(np.random.random())
            dev.setDigital(0, val_b)
            self.assertEqual(dev.do.get(), val_b, "Unexpected readback on digital output")
        print("IO: Done testing IO module!")


    def test_08_AxisDdc(self):
        """ Drive data collection 
        
            This is the preliminary test case dor drive data collection using 
            internal PSO based triggers. It tests basic functionality, like
            configuration, state monitoring and readback.
        """
        # Throws if IOC is not available or PVs are incorrect
        dev = aa1AxisDriveDataCollection(AA1_IOC_NAME+ ":" + AA1_AXIS_NAME + ":DDC:", name="ddc")
        event = EpicsSignal(AA1_IOC_NAME+ ":" + AA1_AXIS_NAME + ":PSO:EVENT:SINGLE", put_complete=True)
        dev.wait_for_connection()
        event.wait_for_connection()       
        print("\nAX:DDC: Checking axis DDC")
        
        # Stop any running acquisition
        dev.unstage(settle_time=0.1)

        print("AX:DDC: Running a partial acquisition (1/3)")
        # Configure the DDC for 42 points and start waiting for triggers
        dev.configure({'npoints': 42, 'trigger': DriveDataCaptureTrigger.PsoEvent})
        dev.kickoff().wait()
        # Fire 12 triggers and stop the acquisition early
        for ii in range(12):
            event.set(1,  settle_time=0.02).wait()
        # Stop the data acquisition early
        dev.unstage()            
            
        # Wait for polling to catch up
        sleep(1)

        # Do the readback and check final state
        rbv = yield from dev.collect()
        self.assertEqual(dev.nsamples_rbv.value, 12, f"Expected to collect 12 points by now, got {dev.nsamples_rbv.value}")
        self.assertEqual(len(rbv["buffer0"]), 12, f"Expected to read back 12 points by now, got {len(rbv['buffer0'])}")
        self.assertEqual(len(rbv["buffer1"]), 12, f"Expected to read back 12 points by now, got {len(rbv['buffer1'])}")
        
        
        print("AX:DDC: Running an overruning acquisition (2/3)")
        # Configure the DDC for 42 points and start waiting for triggers
        dev.configure(16, trigger=DriveDataCaptureTrigger.PsoEvent)
        dev.stage()
        num = dev.nsamples_rbv.get()
        self.assertEqual(num, 0, f"Stage should reset the number of DDC points but got: {num}")        

        # Fire 20 triggers and stop the acquisition early
        for ii in range(20):
            event.set(1,  settle_time=0.02).wait()
        dev.unstage()            
            
        # Wait for polling to catch up
        sleep(1)

        # Do the readback and check final state
        rbv = dev.collect()
        self.assertEqual(dev.nsamples_rbv.value, 16, f"Expected to collect 16 points by now, got {dev.nsamples_rbv.value}")
        self.assertEqual(len(rbv["buffer0"]), 16, f"Expected to read back 16 points by now, got {len(rbv['buffer0'])}")
        self.assertEqual(len(rbv["buffer1"]), 16, f"Expected to read back 16 points by now, got {len(rbv['buffer1'])}")

        
        print("AX:DDC: Trying to record some noise on the analog input (3/3)")
        dev.configure(36, trigger=DriveDataCaptureTrigger.PsoEvent, source1=DriveDataCaptureInput.AnalogInput0)
        dev.stage()
        num = dev.nsamples_rbv.get()
        self.assertEqual(num, 0, f"Stage should reset the number of DDC points but got: {num}")   
        # Fire 36 triggers
        for ii in range(36):
            event.set(1,  settle_time=0.02).wait()
        dev.unstage()            
            
        # Wait for polling to catch up
        sleep(1)

        # Do the readback and check final state
        rbv = dev.collect()
        self.assertEqual(dev.nsamples_rbv.value, 36, f"Expected to collect 12 points by now, got {dev.nsamples_rbv.value}")
        self.assertEqual(len(rbv["buffer0"]), 36, f"Expected to read back 36 points by now, got {len(rbv['buffer0'])}")
        self.assertEqual(len(rbv["buffer1"]), 36, f"Expected to read back 36 points by now, got {len(rbv['buffer1'])}")
        self.assertTrue(np.std(rbv["buffer1"])>0.000001, f"Expected some noise on analog input, but std is: {np.std(rbv['buffer1'])}")
        print("AX:DDC: Done testing DDC module!")


    def test_09_AxisPsoDistance1(self):
        """ Test basic PSO distance mode functionality
        
            This module tests basic PSO distance functionality, like events and
            waveform generation. The goal is to ensure the basic operation of 
            the PSO module and the polled feedback.
        """        
        # Throws if IOC is not available or PVs are incorrect
        dev = aa1AxisPsoDistance(AA1_IOC_NAME+ ":" + AA1_AXIS_NAME + ":PSO:", name="pso1")
        ddc = aa1AxisDriveDataCollection(AA1_IOC_NAME+ ":" + AA1_AXIS_NAME + ":DDC:", name="ddc")
        mot = EpicsMotor(AA1_IOC_NAME+ ":" + AA1_AXIS_NAME, name="x")
        mot.wait_for_connection()
        dev.wait_for_connection()
        ddc.wait_for_connection()
        print("\nAX:PSO: Checking axis PSO in distance mode (basic)")
        if dev.output.value:
            dev.toggle()  
            sleep(1)
        
        print("AX:PSO: Directly checking basic 'toggled' event generation (1/3)")
        # Configure steps and move to middle of range
        dev.configure({'distance': 5, 'wmode': "toggle"})
        mot.move(mot.position + 2.5)
        dev.stage()
        # Start moving in steps, while checking output
        for ii in range(10):
            last_pso = dev.output.value
            mot.move(mot.position + 5)
            sleep(1)
            self.assertTrue(dev.output.value != last_pso, f"Expected to toggle the PSO output at step {ii}, got {dev.output.value}")
        dev.unstage()        
        ddc.unstage()
        
        print("AX:PSO: Checking basic 'toggled' event generation with DDC (2/3)")
        # Configure steps and move to middle of range
        dev.configure({'distance': 2.0, 'wmode': "toggle"})
        dev.stage()        

        # Configure DDC
        npoints = 720 / 2.0
        ddc.configure({'npoints': npoints+100, 'trigger': DriveDataCaptureTrigger.PsoOutput})
        ddc.stage()
        npoints_rbv = ddc.nsamples_rbv.value
        self.assertEqual(npoints_rbv, 0, f"DDC.stage should reset the number of DDC points but got: {npoints_rbv}")      
        self.assertTrue(dev.output.value==0, "Expected to start from LOW state")

        # Start moving and wait for polling
        mot.move(mot.position + 720)
        sleep(0.5)

        # Evaluate results 
        npoints_rbv = ddc.nsamples_rbv.value
        self.assertTrue(np.abs(npoints_rbv-720/4)<=1, f"Expected to record {720/4} points but got {npoints_rbv}")
        dev.unstage()        
        ddc.unstage()


        print("AX:PSO: Checking basic 'pulsed' event generation with DDC (3/5)")
        # Configure steps and move to middle of range
        dev.configure({'distance': 1.8, 'wmode': "pulsed", 'n_pulse': 3})
        dev.kickoff().wait()
  
        # Configure DDC
        npoints = 3 * 720 / 1.8
        ddc.configure({'npoints': npoints+100, 'trigger': DriveDataCaptureTrigger.PsoOutput})
        ddc.stage()
        npoints_rbv = ddc.nsamples_rbv.value
        self.assertEqual(npoints_rbv, 0, f"DDC.stage should reset the number of DDC points but got: {npoints_rbv}")      
        self.assertTrue(dev.output.value==0, "Expected to start from LOW state")

        # Start moving and wait for polling
        mot.move(mot.position + 720.9)
        sleep(0.5)

        # Evaluate results 
        npoints_rbv = ddc.nsamples_rbv.value
        self.assertTrue(np.abs(npoints_rbv-3*720/1.8)<=1, f"Expected to record {3*720/1.8} points but got {npoints_rbv}")
        print("AX:PSO: Done testing basic PSO distance functionality!")
        dev.unstage()        
        ddc.unstage()


    def test_10_PsoIntegration01(self):
        """ The first integration test aims to verify PSO functionality under 
            real life scenarios. It uses the DDC for collecting encoder signals
            and compares them to the expected values.
        """
        # Throws if IOC is not available or PVs are incorrect
        dev = aa1AxisPsoDistance(AA1_IOC_NAME+ ":" + AA1_AXIS_NAME + ":PSO:", name="pso1")
        ddc = aa1AxisDriveDataCollection(AA1_IOC_NAME+ ":" + AA1_AXIS_NAME + ":DDC:", name="ddc")
        mot = EpicsMotor(AA1_IOC_NAME+ ":" + AA1_AXIS_NAME, name="x")
        mot.wait_for_connection()
        dev.wait_for_connection()
        ddc.wait_for_connection()
        print("\nAX:PSO: Integration test for vector style PSO triggering (advanced)")

        print("AX:PSO: Testing standard 'enable' style PSO triggering with DDC (1/3)")
        # This is one line of the Tomcat sequence scan! 
        acc_dist = 0.5 * mot.velocity.value * mot.acceleration.value
        vec_dist = [acc_dist, 18, 0.01, 18, 0.01, 18, 0.01, 18, 0.01, 18, 0.01, 18]
        dev.configure({'distance': vec_dist, 'wmode': "toggle"})
        if dev.output.value:
            dev.toggle()
        dev.stage()        
  
        # Configure DDC
        npoints_exp = len(vec_dist)/2
        ddc.configure({'npoints': npoints_exp+100, 'trigger': DriveDataCaptureTrigger.PsoOutput})
        ddc.stage()
        npoints_rbv = ddc.nsamples_rbv.value
        self.assertEqual(npoints_rbv, 0, f"DDC.stage should reset the number of DDC points but got: {npoints_rbv}")      
        self.assertTrue(dev.output.value==0, "Expected to start from LOW state")

        # Start moving and wait for polling
        mot.move(mot.position + np.sum(vec_dist) + 10)
        sleep(0.9)

        # Evaluate results 
        npoints_rbv = ddc.nsamples_rbv.value
        self.assertTrue(np.abs(npoints_rbv-npoints_exp)<1, f"Expected to record {npoints_exp} points but got {npoints_rbv}")
        self.assertTrue(dev.output.value==0, "Expected to finish in LOW state")
        self.assertTrue(dev.dstArrayDepleted.value, "Expected to cover all pints in the distance array")
        dev.unstage()        
        ddc.unstage()        
        
        print("AX:PSO: Checking 'individual' style trigger signal with DDC (2/5)")
        # This is practically golden ratio tomography! 
        acc_dist = 0.5 * mot.velocity.value * mot.acceleration.value
        vec_dist = [acc_dist]
        vec_dist.extend([1.618]* 100)
        dev.configure({'distance': vec_dist, 'wmode': "pulsed"})
        dev.stage()        
  
        # Configure DDC
        npoints_exp = len(vec_dist)
        ddc.configure({'npoints': npoints_exp+100, 'trigger': DriveDataCaptureTrigger.PsoOutput})
        ddc.stage()
        npoints_rbv = ddc.nsamples_rbv.value
        self.assertEqual(npoints_rbv, 0, f"DDC.stage should reset the number of DDC points but got: {npoints_rbv}")      
        self.assertTrue(dev.output.value==0, "Expected to start from LOW state")

        # Start moving and wait for polling (move negative direction)
        mot.move(mot.position - np.sum(vec_dist) - acc_dist)
        sleep(0.9)

        # Evaluate results 
        npoints_rbv = ddc.nsamples_rbv.value
        self.assertTrue(np.abs(npoints_rbv-npoints_exp)<1, f"Expected to record {npoints_exp} points but got {npoints_rbv}")
        self.assertTrue(dev.output.value==0, "Expected to finish in LOW state")
        self.assertTrue(dev.dstArrayDepleted.value, "Expected to cover all pints in the distance array") 
        print("AX:PSO: Done testing PSO module in distance mode!")
        dev.unstage()        
        ddc.unstage()


    def test_11_AxisPsoWindow1(self):
        """ Test basic PSO window mode functionality
        
            This module tests basic PSO distance functionality, like events and
            waveform generation. The goal is to ensure the basic operation of 
            the PSO module and the polled feedback.
        """
        return
        # Throws if IOC is not available or PVs are incorrect
        dev = aa1AxisPsoWindow(AA1_IOC_NAME+ ":" + AA1_AXIS_NAME + ":PSO:", name="pso1")
        ddc = aa1AxisDriveDataCollection(AA1_IOC_NAME+ ":" + AA1_AXIS_NAME + ":DDC:", name="ddc")
        mot = EpicsMotor(AA1_IOC_NAME+ ":" + AA1_AXIS_NAME, name="x")
        mot.wait_for_connection()
        dev.wait_for_connection()
        ddc.wait_for_connection()
        print("\nAX:PSO: Checking axis PSO in window mode (basic)")
        if dev.output.value:
            dev.toggle()     

        print("AX:PSO: Directly checking basic window output (1/3)")
        # Configure steps and move to middle of range
        dev.configure((5, 13), "output")
        dev.stage()
        sleep(1)
        # Move half a step
        mot.move(mot.position + 0.1)
        dist = 0.1

        # Start moving in steps, while checking output
        for ii in range(42):
            mot.move(mot.position + 0.2)
            dist += 0.2
            sleep(1)
            if 5 < dist < 13:
                self.assertTrue(dev.output.value==1, f"Expected HIGH PSO output inside the window at distance {dist}")
            else:
                self.assertTrue(dev.output.value==0, f"Expected LOW PSO output outside the window at distance {dist}")

        print("AX:PSO: The following tests whould fail as multiple triggers/events are being emmitted when entering/exiting the window!")
        dev.unstage()        
        return

        print("AX:PSO: Checking basic window event generation with DDC (2/3)")
        print("  WARN: The encoder output is very noisy, one transition generates several events")
        # Move to acceleration position
        acc_dist = 0.5 * mot.velocity.value * mot.acceleration.value
        print(f"Acceleration distance: {acc_dist}")
        start_position = mot.position
        mot.move(start_position - acc_dist)
        # Configure PSO in window mode       
        dev.configure((acc_dist, 30 + acc_dist), "pulsed", "Both",  n_pulse=1)
        # Configure the data capture (must be performed in start position)
        ddc.configure(5*10, trigger=DriveDataCaptureTrigger.PsoOutput)
        ddc.stage()
        npoints_rbv = ddc.nsamples_rbv.value
        self.assertEqual(npoints_rbv, 0, f"DDC.stage should reset the number of DDC points but got: {npoints_rbv}")
        # Repeated line scan
        for ii in range(10):
            dev.stage()
            mot.move(start_position + 30 + acc_dist)
            dev.unstage()
            mot.move(start_position - acc_dist)
        sleep(0.5)
        npoints_rbv = ddc.nsamples_rbv.value
        self.assertTrue(np.abs(npoints_rbv-50)<1, f"Expected to record 10 points but got {npoints_rbv}")
        

        print("AX:PSO: Checking basic 'toggled' event generation with DDC (3/3)")
        print("Test removed as there's some heavy jitter on the PSO output flag")
        # Move to acceleration position
        acc_dist = 0.5 * mot.velocity.value * mot.acceleration.value
        print(f"Acceleration distance: {acc_dist}")
        mot.move(mot.position - acc_dist)
        # Configure PSO in window mode
        dev.configure((acc_dist, 30 + acc_dist + 1), "output")
        dev.stage()        
        # Configure the data capture
        ddc.configure(10, trigger=DriveDataCaptureTrigger.PsoOutput)
        ddc.stage()
        npoints_rbv = ddc.nsamples_rbv.value
        self.assertEqual(npoints_rbv, 0, f"DDC.stage should reset the number of DDC points but got: {npoints_rbv}")
        # Snake scan
        for ii in range(10):
            if ii % 2 == 0:
                mot.move(mot.position + 30+ 2*acc_dist + 0.1)
            else:
                mot.move(mot.position - 30 - 2*acc_dist - 0.1)
        sleep(0.5)
        npoints_rbv = ddc.nsamples_rbv.value
        self.assertTrue(np.abs(npoints_rbv-10)<1, f"Expected to record 10 points but got {npoints_rbv}")
               
                
        
    def test_12_TomcatSequenceScan(self):
        """ Test the zig-zag sequence scan from Tomcat (via BEC)
        
            This module tests basic PSO distance functionality, like events and
            waveform generation. The goal is to ensure the basic operation of 
            the PSO module and the polled feedback.
        """
        # Throws if IOC is not available or PVs are incorrect
        pso = aa1AxisPsoDistance(AA1_IOC_NAME+ ":" + AA1_AXIS_NAME + ":PSO:", name="pso1")
        ddc = aa1AxisDriveDataCollection(AA1_IOC_NAME+ ":" + AA1_AXIS_NAME + ":DDC:", name="ddc")
        mot = EpicsMotor(AA1_IOC_NAME+ ":" + AA1_AXIS_NAME, name="x")
        mot.wait_for_connection()
        pso.wait_for_connection()
        ddc.wait_for_connection()
        t_start = time()
        print("\nTOMCAT Sequeence scan (via Ophyd)")        
        
        ScanStart = 42.0
        ScanRange = 180
        NumRepeat = 10
        ScanType = "PosNeg"
        
        # Dynamic properties
        VelScan = 90
        AccScan = 500
        SafeDist = 10.0
        
        ######################################################################
        print("\tConfigure")        
        # Scan range
        AccDist = 0.5 * VelScan * VelScan / AccScan + SafeDist
        if ScanType in ["PosNeg", "Pos"]:
            PosStart = ScanStart - AccDist
            PosEnd = ScanStart + ScanRange + AccDist
        elif ScanType in ["NegPos", "Neg"]:
            PosStart = ScanStart + AccDist
            PosEnd = ScanStart - ScanRange - AccDist
        else:
            raise RuntimeError(f"Unexpected ScanType: {ScanType}")

        # Motor setup
        mot.velocity.set(VelScan).wait()
        mot.acceleration.set(VelScan/AccScan).wait()
        mot.move(PosStart)
        self.assertTrue(np.abs(mot.position-PosStart)<0.1, f"Expected to move to scan start position {PosStart}, found motor at {mot.position}")        

        # PSO setup
        print(f"Configuring PSO to:  {[AccDist, ScanRange]}")
        pso.configure({'distance': [AccDist, ScanRange], "wmode": "toggle"})

        # DDC  setup (Tomcat runs in ENABLE mode, so only one posedge)
        ddc.configure({'npoints': NumRepeat})

        print("\tStage") 
        mot.stage()
        pso.stage()
        ddc.stage()
             
        for ii in range(NumRepeat):
            # No option to reset the index counter...
            pso.dstArrayRearm.set(1).wait()

            if ScanType in ["Pos", "Neg"]:
                    mot.move(PosEnd)
                    self.assertTrue(np.abs(mot.position-PosEnd)<1.0,   f"Expected to reach {PosEnd}, motor is at {mot.position} on iteration {ii}")
                    mot.move(PosStart)
                    self.assertTrue(np.abs(mot.position-PosStart)<1.0, f"Expected to rewind to {PosStart}, motor is at {mot.position} on iteration {ii}")

            if ScanType in ["PosNeg", "NegPos"]:
                if ii % 2 == 0:
                    mot.move(PosEnd)
                    self.assertTrue(np.abs(mot.position-PosEnd)<1.0, f"Expected to reach {PosEnd}, motor is at {mot.position} on iteration {ii}")
                else:   
                    mot.move(PosStart)
                    self.assertAlmostEqual(mot.position, PosStart, 1, f"Expected to reach {PosStart}, motor is at {mot.position} on iteration {ii}")

            sleep(0.5)
            npoints_rbv = ddc.nsamples_rbv.value
            self.assertEqual(npoints_rbv, ii+1, f"Expected to record {ii+1} DDC points, but got: {npoints_rbv} on iteration {ii}")        

        print("\tUnstage")        
        mot.unstage()
        ddc.unstage()
        pso.unstage()
        
        t_end = time()
        t_elapsed = t_end - t_start
        print(f"Elapsed scan time: {t_elapsed}")
        
        print("Evaluate final state")
        sleep(3)
        npoints_rbv = ddc.nsamples_rbv.value
        self.assertEqual(npoints_rbv, NumRepeat, f"Expected to record {NumRepeat} DDC points, but got: {npoints_rbv}")        


    def test_13_TomcatSequenceScan(self):
        """ Test the zig-zag sequence scan from Tomcat (via AeroScript)
        
            This module tests basic PSO distance functionality, like events and
            waveform generation. The goal is to ensure the basic operation of 
            the PSO module and the polled feedback.
        """
        # Throws if IOC is not available or PVs are incorrect        
        dev = aa1Tasks(AA1_IOC_NAME+":TASK:", name="tsk")
        tsk4 = aa1TaskState(AA1_IOC_NAME+ ":TASK:T4:", name="tsk4")

        dev.wait_for_connection()
        tsk4.wait_for_connection()
        
        t_start = time()        
        print("\nTOMCAT Sequeence scan (via AeroScript)")        
        

        filename = "test/testScan02.ascript"
        with open(filename) as f:
            text = f.read()
        # Copy file to controller and run it
        dev.runScript("tcatZigZagSequence2.ascript", taskIndex=4, filetext=text)
        sleep(0.5)
        tsk4.complete().wait()

        t_end = time()
        t_elapsed = t_end - t_start
        print(f"Elapsed scan time: {t_elapsed}")
        
        # Do the readback and check final state
        ddc = aa1AxisDriveDataCollection(AA1_IOC_NAME+ ":" + AA1_AXIS_NAME + ":DDC:", name="ddc")
        ddc.wait_for_connection()              
        rbv = yield from ddc.collect()
        npoints_rbv = ddc.nsamples_rbv.value
        self.assertEqual(npoints_rbv, 10, f"Expected to collect 10 points by now, got {npoints_rbv}")
        self.assertEqual(len(rbv["buffer0"]), 10, f"Expected to read back 10 points by now, got {len(rbv['buffer0'])}")
        self.assertEqual(len(rbv["buffer1"]), 10, f"Expected to read back 10 points by now, got {len(rbv['buffer1'])}")
        self.assertTrue(np.std(rbv["buffer0"])>5, f"Expected some noise on analog input, but std is: {np.std(rbv['buffer1'])}")
        self.assertTrue(np.std(rbv["buffer1"])>5, f"Expected some noise on analog input, but std is: {np.std(rbv['buffer1'])}")
        print("AX:DDC: Done testing DDC module!")
                
    def test_14_JinjaTomcatSequenceScan(self):
        return
        # Load the test file
        filename = "test/testSequenceScanTemplate.ascript"
        with open(filename) as f:
            templatetext = f.read()           
        
        import jinja2
        scanconfig = {'startpos': 42, 'scanrange': 180, 'nrepeat': 10, 'scandir': 'NegPos', 'scanvel': 90, 'scanacc': 500}
        tm = jinja2.Template(templatetext)
        text = tm.render(scan=scanconfig)
        with open("test/tcatSequenceScan.ascript", "w") as text_file:
            text_file.write(text)
        
        # Throws if IOC is not available or PVs are incorrect        
        dev = aa1Tasks(AA1_IOC_NAME+":TASK:", name="tsk")
        tsk4 = aa1TaskState(AA1_IOC_NAME+ ":TASK:T4:", name="tsk4")
        dev.wait_for_connection()
        tsk4.wait_for_connection()
        print("\nTOMCAT Sequeence scan (via Jinjad AeroScript)")  
        
        # Copy file to controller and run it
        t_start = time()                
        dev.runScript("tcatSequenceScan.ascript", taskIndex=4, filetext=text)
        sleep(0.5)
        tsk4.complete().wait()
        t_end = time()
        t_elapsed = t_end - t_start
        print(f"Elapsed scan time: {t_elapsed}")




if __name__ == "__main__":
    unittest.main()
























