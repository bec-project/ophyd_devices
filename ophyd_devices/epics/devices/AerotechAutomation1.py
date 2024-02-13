from ophyd import Device, Component, EpicsMotor, EpicsSignal, EpicsSignalRO, Kind, DerivedSignal
from ophyd.status import Status, SubscriptionStatus, StatusBase
from time import sleep
import warnings
import numpy as np
import time

from .AerotechAutomation1Enums import (DataCollectionMode, DataCollectionFrequency, 
    AxisDataSignal, PsoWindowInput, DriveDataCaptureInput, DriveDataCaptureTrigger,
    TaskDataSignal, SystemDataSignal, TomcatSequencerState)

from .AerotechAutomation1Enums import *
from typing import Union
from collections import OrderedDict


def epicsCharArray2String(raw: bytes) -> str:
    """ Ophyd might convert strings to uint16 vector..."""
    if isinstance(raw, np.ndarray):
        raw = raw[:-1] if raw[-1]==0 else raw 
        sReply = ''.join(str(s, encoding='ASCII') for s in raw.astype(np.uint8))
        print(f"Raw reply: {raw}\nConverted reply: {sReply}")
        return sReply
    else:
        return raw    
    
    
    

class EpicsSignalPassive(Device):
    value = Component(EpicsSignalRO, "", kind=Kind.hinted)
    proc = Component(EpicsSignal, ".PROC", kind=Kind.omitted, put_complete=True)
    def get(self):
         self.proc.set(1).wait()
         return self.value.get()


class EpicsStringPassiveRO(EpicsSignalRO):
    """Special helper class to work around a bug in ophyd (caproto backend)
        that reads CHAR array strigs as uint16 arrays.
    """
    
    def __init__(self, read_pv, *, string=False, name=None, **kwargs):       
        super().__init__(read_pv, string=string, name=name, **kwargs)
        self._proc = EpicsSignal(read_pv+".PROC", kind=Kind.omitted, put_complete=True)
        
    def wait_for_connection(self, *args, **kwargs):        
        super().wait_for_connection(*args, **kwargs)
        self._proc.wait_for_connection(*args, **kwargs)
        
    def get(self, *args, **kwargs):
        self._proc.set(1).wait()
        raw = super().get(*args, **kwargs)
        return epicsCharArray2String(raw)
        
    @property 
    def value(self):
        raw = super().value
        return epicsCharArray2String(raw)
    
    
class EpicsStringPassive(EpicsSignal):
    """Special helper class to work around a bug in ophyd (caproto backend)
        that reads CHAR array strigs as uint16 arrays.
    """        
    def __init__(self, read_pv, write_pv=None, *, put_complete=False,
                 string=False, limits=False, name=None, **kwargs):
        super().__init__(read_pv, write_pv, put_complete, string, limits, name, **kwargs)
        self._proc = EpicsSignal(read_pv+".PROC", kind=Kind.omitted, put_complete=True)
        
    def wait_for_connection(self, *args, **kwargs):        
        super().wait_for_connection(*args, **kwargs)
        self._proc.wait_for_connection(*args, **kwargs)
        
    def get(self, *args, **kwargs):
        self._proc.set(1).wait()
        raw = super().get(*args, **kwargs)
        return epicsCharArray2String(raw)
        
    @property 
    def value(self):
        raw = super().value
        return epicsCharArray2String(raw)


class EpicsString(EpicsSignal):
    """Special helper class to work around a bug in ophyd (caproto backend)
        that reads CHAR array strigs as uint16 arrays.
    """
    def get(self, *args, **kwargs):
        raw = super().get(*args, **kwargs)
        return epicsCharArray2String(raw)
        
    @property 
    def value(self):
        raw = super().value
        return epicsCharArray2String(raw)

        
class EpicsStringRO(EpicsSignalRO):
    """Special helper class to work around a bug in ophyd (caproto backend)
        that reads CHAR array strigs as uint16 arrays.
    """
    def get(self, *args, **kwargs):
        raw = super().get(*args, **kwargs)
        return epicsCharArray2String(raw)
        
    @property 
    def value(self):
        raw = super().value
        return epicsCharArray2String(raw)


class aa1Controller(Device):
    """Ophyd proxy class for the Aerotech Automation 1's core controller functionality"""
    controllername = Component(EpicsSignalRO, "NAME", kind=Kind.config)
    serialnumber = Component(EpicsSignalRO, "SN", kind=Kind.config)
    apiversion = Component(EpicsSignalRO, "API_VERSION", kind=Kind.config)
    axiscount = Component(EpicsSignalRO, "AXISCOUNT", kind=Kind.config)
    taskcount = Component(EpicsSignalRO, "TASKCOUNT", kind=Kind.config)
    fastpoll = Component(EpicsSignalRO, "RUNNING", auto_monitor=True, kind=Kind.hinted)
    slowpoll = Component(EpicsSignalRO, "RUNNING", auto_monitor=True, kind=Kind.hinted)
    def __init__(self, prefix="", *, name, kind=None, read_attrs=None, configuration_attrs=None, parent=None, **kwargs):
        super().__init__(prefix=prefix, name=name, kind=kind, read_attrs=read_attrs, configuration_attrs=configuration_attrs, parent=parent, **kwargs)

class aa1Tasks(Device):
    """ Task management API
    
        The place to manage tasks and AeroScript user files on the controller. 
        You can read/write/compile/execute AeroScript files and also retrieve 
        saved data files from the controller.
        
        Execute does not require to store the script in a file, it will compile
        it and run it directly on a certain thread. But there's no way to 
        retrieve the source code.
    """
    _failure = Component(EpicsSignalRO, "FAILURE", kind=Kind.hinted)
    errStatus = Component(EpicsSignalRO, "ERRW", auto_monitor=True, kind=Kind.hinted)
    warnStatus = Component(EpicsSignalRO, "WARNW", auto_monitor=True, kind=Kind.hinted)    
    taskIndex = Component(EpicsSignal, "TASKIDX", kind=Kind.config, put_complete=True)
    switch = Component(EpicsSignal, "SWITCH", kind=Kind.config, put_complete=True)
    _execute = Component(EpicsSignal, "EXECUTE", kind=Kind.config,  put_complete=True)
    _executeMode = Component(EpicsSignal, "EXECUTE-MODE", kind=Kind.config,  put_complete=True)
    _executeReply = Component(EpicsSignalRO, "EXECUTE_RBV", auto_monitor=True)

    fileName = Component(EpicsSignal, "FILENAME", kind=Kind.config,  put_complete=True)
    _fileList = Component(EpicsSignalPassive, "FILELIST", kind=Kind.config)
    _fileRead = Component(EpicsSignalPassive, "FILEREAD", kind=Kind.config)
    _fileWrite = Component(EpicsSignal, "FILEWRITE", kind=Kind.config,  put_complete=True)
    
    def __init__(self, prefix="", *, name, kind=None, read_attrs=None, configuration_attrs=None, parent=None, **kwargs):
        """ __init__ MUST have a full argument list"""
        super().__init__(prefix=prefix, name=name, kind=kind, read_attrs=read_attrs, configuration_attrs=configuration_attrs, parent=parent, **kwargs)
        self._currentTaskMonitor = None
        self._textToExecute = None 
    
    def listFiles(self) -> list:
        """ List all available files on the controller """
        # Have to use CHAR array due to EPICS LSI bug...
        namesbytes = self._fileList.get().astype(np.uint8).tobytes()
        nameslist = namesbytes.decode('ascii').split('\t')
        return nameslist
    
    def readFile(self, filename: str) -> str:
        """ Read a file from the controller """
        # Have to use CHAR array due to EPICS LSI bug...
        self.fileName.set(filename).wait()
        filebytes = self._fileRead.get().astype(np.uint8).tobytes()
        # C-strings terminate with trailing zero
        if filebytes[-1]==0:
            filebytes = filebytes[:-1]
        filetext = filebytes.decode('ascii')
        return filetext
    
    def writeFile(self, filename: str, filetext: str) -> None:
        """ Write a file to the controller """
        self.fileName.set(filename).wait()
        self._fileWrite.set(filetext).wait()

    def runScript(self, filename: str, taskIndex: int==2, filetext=None, settle_time=0.5) -> None:
        """ Run a script file that either exists, or is newly created and compiled"""
        
        self.configure(text=filetext, filename=filename, taskIndex=taskIndex)
        self.trigger(settle_time=settle_time).wait()
                
    def execute(self, text: str, taskIndex: int=3, mode: str=0, settle_time=0.5):
        """ Run a short text command on the Automation1 controller"""
        
        print(f"Executing program on task: {taskIndex}")        
        self.configure(text=text, taskIndex=taskIndex, mode=mode)
        self.trigger(settle_time=settle_time).wait()
    
        if mode in [0, "None", None]:
            return None
        else:
            raw = self._executeReply.get()
            return epicsCharArray2String(raw)

    def configure(self, text: str=None, filename: str=None, taskIndex: int=4, settle_time=None, **kwargs):
        """ Interface for configuration """
        # Validation
        if taskIndex < 0 or taskIndex > 31:
            raise RuntimeError(f"Invalid task index: {taskIndex}")
        if (text is None) and (filename is None):
            raise RuntimeError("Task execution requires either AeroScript text or filename")
        if 'mode' in kwargs:
            if kwargs['mode'] not in [0, 1, 2, 3, 4, "None", "Axis", "Int", "Double", "String", None]:
                raise RuntimeError(f"Unknown execution mode: {kwargs['mode']}")    
            if kwargs['mode'] is None:
                kwargs['mode'] = "None"
        else:
            kwargs['mode'] = "None"
            
        # common operations
        self.taskIndex.set(taskIndex).wait() 
        self._textToExecute = None
        #self._currentTaskMonitor = aa1TaskState()
            
        # Choose the right execution mode
        if (filename is None) and (text not in [None, ""]):
            # Direct command execution
            print("Preparing for direct command execution")
            self._executeMode.set(kwargs['mode']).wait()
            self._textToExecute = text
        elif (filename is not None) and (text in [None, ""]):
            # Execute existing file
            self.fileName.set(filename).wait()
            self.switch.set("Load").wait()
        elif (filename is not None) and (text not in [None, ""]):
            print("Preparing to execute via intermediary file")
            # Execute text via intermediate file
            self.taskIndex.set(taskIndex).wait()       
            self.fileName.set(filename).wait()
            self._fileWrite.set(text).wait()
            self.switch.set("Load").wait()
            self._textToExecute = None
        else:
            raise RuntimeError("Unsupported filename-text combo")
            
    ##########################################################################
    # Bluesky stepper interface        
    def stage(self) -> None:
        """ Default staging """
        super().stage()
    def unstage(self) -> None:
        """ Default unstaging """
        super().unstage()

    def trigger(self, settle_time=0.2) -> StatusBase:
        """ Execute the script on the configured task"""
        if self._textToExecute is not None:
            status = self._execute.set(self._textToExecute, settle_time=settle_time)
        else:
            status = self.switch.set("Run", settle_time=settle_time)
        return status
    
    def stop(self):
        """ Stop the currently selected task """
        self.switch.set("Stop").wait()                  

    ##########################################################################
    # Flyer interface
    def kickoff(self) -> StatusBase:
        """ Execute the script on the configured task"""
        if self._textToExecute is not None:
            status = self._execute.set(self._textToExecute, settle_time=0.5)
        else:
            status = self.switch.set("Run", settle_time=0.1)
        return status

    def complete(self) -> StatusBase:
        """ Execute the script on the configured task"""
        #return self._currentTaskMonitor.complete()
        status = StatusBase()
        status.set_finished()
        return status
    
    def describe_collect(self) -> OrderedDict:
        dd = OrderedDict()
        dd['success'] = {'source': "internal", 'dtype': 'integer', 'shape': [], 'units': '', 'lower_ctrl_limit': 0, 'upper_ctrl_limit': 0}
        return {self.name: dd}
        
    def collect(self) -> OrderedDict:
        ret = OrderedDict()
        ret["timestamps"] = {"success": time.time()}
        ret["data"] = {"success": 1}
        yield ret

        
class aa1TaskState(Device):
    """ Task state monitoring API
    
        This is the task state monitoring interface for Automation1 tasks. It 
        does not launch execution, but can wait for the execution to complete.
    """
    index = Component(EpicsSignalRO, "INDEX", kind=Kind.config)
    status = Component(EpicsSignalRO, "STATUS", auto_monitor=True, kind=Kind.hinted)
    errorCode = Component(EpicsSignalRO, "ERROR", auto_monitor=True, kind=Kind.hinted)
    warnCode = Component(EpicsSignalRO, "WARNING", auto_monitor=True, kind=Kind.hinted)

    def complete(self) -> StatusBase:
        """ Bluesky flyer interface"""
        # Define wait until the busy flag goes down (excluding initial update)
        timestamp_ = 0
        def notRunning(*args, old_value, value, timestamp, **kwargs):
            nonlocal timestamp_       
            result = False if (timestamp_== 0) else (value not in ["Running", 4])   
            print(f"Old {old_value}\tNew: {value}\tResult: {result}")
            timestamp_ = timestamp
            return result
        
        # Subscribe and wait for update
        status = SubscriptionStatus(self.status, notRunning, settle_time=0.5)        
        return status
                
    def kickoff(self) -> StatusBase:
        status = StatusBase()
        status.set_finished()
        return status
    
    def describe_collect(self) -> OrderedDict:
        dd = OrderedDict()
        dd['success'] = {'source': "internal", 'dtype': 'integer', 'shape': [], 'units': '', 'lower_ctrl_limit': 0, 'upper_ctrl_limit': 0}
        return dd
        
    def collect(self) -> OrderedDict:
        ret = OrderedDict()
        ret["timestamps"] = {"success": time.time()}
        ret["data"] = {"success": 1}
        yield ret
    
        
class aa1DataAcquisition(Device):
    """ Controller Data Acquisition
    
        This class implements the controller data collection feature of the 
        Automation1 controller. This feature logs various inputs at a 
        **fixed frequency** from 1 kHz up to 200 kHz.
        Usage:
            1. Start a new configuration with "startConfig"
            2. Add your signals with "addXxxSignal" 
            3. Start your data collection
            4. Read back the recorded data with "readback"
    """
    # Status monitoring
    status = Component(EpicsSignalRO, "RUNNING", auto_monitor=True, kind=Kind.hinted)
    points_max = Component(EpicsSignal, "MAXPOINTS",  kind=Kind.config, put_complete=True)
    signal_num = Component(EpicsSignalRO, "NITEMS",  kind=Kind.config)

    points_total = Component(EpicsSignalRO, "NTOTAL", auto_monitor=True, kind=Kind.hinted)
    points_collected = Component(EpicsSignalRO, "NCOLLECTED", auto_monitor=True, kind=Kind.hinted)
    points_retrieved= Component(EpicsSignalRO, "NRETRIEVED", auto_monitor=True, kind=Kind.hinted)
    overflow = Component(EpicsSignalRO, "OVERFLOW", auto_monitor=True, kind=Kind.hinted)
    runmode = Component(EpicsSignalRO, "MODE_RBV", auto_monitor=True, kind=Kind.hinted)
    # DAQ setup
    numpoints = Component(EpicsSignal, "NPOINTS", kind=Kind.config, put_complete=True)
    frequency = Component(EpicsSignal, "FREQUENCY", kind=Kind.config, put_complete=True)
    _configure = Component(EpicsSignal, "CONFIGURE", kind=Kind.omitted, put_complete=True)
    
    def startConfig(self, npoints: int, frequency: DataCollectionFrequency):
        self.numpoints.set(npoints).wait()
        self.frequency.set(frequency).wait()
        self._configure.set("START").wait()

    def clearConfig(self):
        self._configure.set("CLEAR").wait()

    srcTask = Component(EpicsSignal, "SRC_TASK", kind=Kind.config, put_complete=True)
    srcAxis = Component(EpicsSignal, "SRC_AXIS", kind=Kind.config, put_complete=True)
    srcCode = Component(EpicsSignal, "SRC_CODE", kind=Kind.config, put_complete=True)
    _srcAdd = Component(EpicsSignal, "SRC_ADD", kind=Kind.omitted, put_complete=True)
    
    def addAxisSignal(self, axis: int, code: int) -> None:
        """ Add a new axis-specific data signal to the DAQ configuration. The
            most common signals are PositionFeedback and PositionError.
        """
        self.srcAxis.set(axis).wait()
        self.srcCode.set(code).wait()
        self._srcAdd.set("AXIS").wait()

    def addTaskSignal(self, task: int, code: int) -> None:
        """ Add a new task-specific data signal to the DAQ configuration"""
        self.srcTask.set(task).wait()
        self.srcCode.set(code).wait()
        self._srcAdd.set("TASK").wait()

    def addSystemSignal(self, code: int) -> None:
        """ Add a new system data signal to the DAQ configuration. The most 
            common signal is SampleCollectionTime. """
        self.srcCode.set(code).wait()
        self._srcAdd.set("SYSTEM").wait()

    # Starting / stopping the DAQ
    _mode = Component(EpicsSignal, "MODE", kind=Kind.config, put_complete=True)
    _switch = Component(EpicsSignal, "SET", kind=Kind.omitted, put_complete=True)
    
    def start(self, mode=DataCollectionMode.Snapshot) -> None:
        """ Start a new data collection """
        self._mode.set(mode).wait()
        self._switch.set("START").wait()
        
    def stop(self) -> None:
        """ Stop a running data collection """
        self._switch.set("STOP").wait()       

    def run(self, mode=DataCollectionMode.Snapshot) -> None:
        """ Start a new data collection """
        self._mode.set(mode).wait()
        self._switch.set("START").wait()        
        # Wait for finishing acquisition
        # Note: this is very bad blocking sleep
        while self.status.value!=0:
            sleep(0.1)
        sleep(0.1)
            
        # Data readback
        data = self.data_rb.get()
        rows = self.data_rows.get()
        cols = self.data_cols.get()
        if len(data)==0 or rows==0 or cols==0:
            sleep(0.5)
            data = self.data_rb.get()
            rows = self.data_rows.get()
            cols = self.data_cols.get()
        print(f"Data shape: {rows} x {cols}")
        data = data.reshape([int(rows), -1])
        return data

    # DAQ data readback
    data_rb = Component(EpicsSignalPassive, "DATA", kind=Kind.hinted)
    data_rows = Component(EpicsSignalRO, "DATA_ROWS", auto_monitor=True, kind=Kind.hinted)
    data_cols = Component(EpicsSignalRO, "DATA_COLS", auto_monitor=True, kind=Kind.hinted)
    data_stat = Component(EpicsSignalRO, "DATA_AVG", auto_monitor=True, kind=Kind.hinted)
    
    def dataReadBack(self) -> np.ndarray:
        """Retrieves collected data from the controller"""
        data = self.data_rb.get()
        rows = self.data_rows.get()
        cols = self.data_cols.get()
        if len(data)==0 or rows==0 or cols==0:
            sleep(0.2)
            data = self.data_rb.get()
            rows = self.data_rows.get()
            cols = self.data_cols.get()
        print(f"Data shape: {rows} x {cols}")
        data = data.reshape([int(rows), -1])
        return data


        
class aa1GlobalVariables(Device):
    """ Global variables
    
    This class provides an interface to directly read/write global variables 
    on the Automation1 controller. These variables are accesible from script
    files and are thus a convenient way to interface with the outside word.
    
    Read operations take as input the memory address and the size
    Write operations work with the memory address and value
    """
    # Status monitoring
    num_real = Component(EpicsSignalRO, "NUM-REAL_RBV", kind=Kind.config)
    num_int = Component(EpicsSignalRO, "NUM-INT_RBV",  kind=Kind.config)
    num_string = Component(EpicsSignalRO, "NUM-STRING_RBV",  kind=Kind.config)
    
    integer_addr = Component(EpicsSignal, "INT-ADDR", kind=Kind.omitted, put_complete=True)
    integer_size = Component(EpicsSignal, "INT-SIZE", kind=Kind.omitted, put_complete=True)
    integer = Component(EpicsSignal, "INT", kind=Kind.omitted, put_complete=True)
    integer_rb = Component(EpicsSignalPassive, "INT-RBV", kind=Kind.omitted)
    integerarr = Component(EpicsSignal, "INTARR", kind=Kind.omitted, put_complete=True)
    integerarr_rb = Component(EpicsSignalPassive, "INTARR-RBV", kind=Kind.omitted)    
    
    real_addr = Component(EpicsSignal, "REAL-ADDR", kind=Kind.omitted, put_complete=True)
    real_size = Component(EpicsSignal, "REAL-SIZE", kind=Kind.omitted, put_complete=True)
    real = Component(EpicsSignal, "REAL", kind=Kind.omitted, put_complete=True)
    real_rb = Component(EpicsSignalPassive, "REAL-RBV", kind=Kind.omitted)
    realarr = Component(EpicsSignal, "REALARR", kind=Kind.omitted, put_complete=True)
    realarr_rb = Component(EpicsSignalPassive, "REALARR-RBV", kind=Kind.omitted)    
    
    string_addr = Component(EpicsSignal, "STRING-ADDR", kind=Kind.omitted, put_complete=True)
    string = Component(EpicsSignal, "STRING", kind=Kind.omitted, put_complete=True)
    string_rb = Component(EpicsStringPassiveRO, "STRING-RBV", kind=Kind.omitted)
    
    def readInt(self, address: int, size: int=None) -> int:
        """ Read a 64-bit integer global variable """
        if address > self.num_int.get():
            raise RuntimeError("Integer address {address} is out of range")
            
        if size is None:
            self.integer_addr.set(address).wait()
            return self.integer_rb.get()
        else:
            self.integer_addr.set(address).wait()
            self.integer_size.set(size).wait()
            return self.integerarr_rb.get()
            
    def writeInt(self, address: int, value) -> None:
        """ Write a 64-bit integer global variable """
        if address > self.num_int.get():
            raise RuntimeError("Integer address {address} is out of range")
            
        if isinstance(value, (int, float)):
            self.integer_addr.set(address).wait()
            self.integer.set(value).wait()
        elif isinstance(value, np.ndarray):
            self.integer_addr.set(address).wait()
            self.integerarr.set(value).wait()
        elif isinstance(value, (list, tuple)):
            value = np.array(value, dtype=np.int32)
            self.integer_addr.set(address).wait()
            self.integerarr.set(value).wait()
        else:
            raise RuntimeError("Unsupported integer value type: {type(value)}")


    def readFloat(self, address: int, size: int=None) -> float:
        """ Read a 64-bit double global variable """
        if address > self.num_real.get():
            raise RuntimeError("Floating point address {address} is out of range")
            
        if size is None:
            self.real_addr.set(address).wait()
            return self.real_rb.get()
        else:
            self.real_addr.set(address).wait()
            self.real_size.set(size).wait()
            return self.realarr_rb.get()

    def writeFloat(self, address: int, value) -> None:
        """ Write a 64-bit float global variable """
        if address > self.num_real.get():
            raise RuntimeError("Float address {address} is out of range")
            
        if isinstance(value, (int, float)):
            self.real_addr.set(address).wait()
            self.real.set(value).wait()
        elif isinstance(value, np.ndarray):
            self.real_addr.set(address).wait()
            self.realarr.set(value).wait()
        elif isinstance(value, (list, tuple)):
            value = np.array(value)
            self.real_addr.set(address).wait()
            self.realarr.set(value).wait()
        else:
            raise RuntimeError("Unsupported float value type: {type(value)}")

    def readString(self, address: int) -> str:
        """ Read a 40 letter string global variable 
        ToDo: Automation 1 strings are 256 bytes
        """
        if address > self.num_string.get():
            raise RuntimeError("String address {address} is out of range")
            
        self.string_addr.set(address).wait()
        return self.string_rb.get()

    def writeString(self, address: int, value) -> None:
        """ Write a 40 bytes string  global variable """
        if address > self.num_string.get():
            raise RuntimeError("Integer address {address} is out of range")
            
        if isinstance(value, str):
            self.string_addr.set(address).wait()
            self.string.set(value).wait()
        else:
            raise RuntimeError("Unsupported string value type: {type(value)}")


        
class aa1GlobalVariableBindings(Device):
    """ Global variables
    
    This class provides an interface to directly read/write global variables 
    on the Automation1 controller. These variables are accesible from script
    files and are thus a convenient way to interface with the outside word.
    
    Read operations take as input the memory address and the size
    Write operations work with the memory address and value
    """
    int0 = Component(EpicsSignalRO, "INT0_RBV", auto_monitor=True, name="int0", kind=Kind.hinted)
    int1 = Component(EpicsSignalRO, "INT1_RBV", auto_monitor=True, name="int1", kind=Kind.hinted)
    int2 = Component(EpicsSignalRO, "INT2_RBV", auto_monitor=True, name="int2", kind=Kind.hinted)
    int3 = Component(EpicsSignalRO, "INT3_RBV", auto_monitor=True, name="int3", kind=Kind.hinted)
    int8 = Component(EpicsSignal, "INT8_RBV", put_complete=True, write_pv="INT8", auto_monitor=True, name="int8", kind=Kind.hinted)
    int9 = Component(EpicsSignal, "INT9_RBV", put_complete=True, write_pv="INT9", auto_monitor=True, name="int9", kind=Kind.hinted)
    int10 = Component(EpicsSignal, "INT10_RBV", put_complete=True, write_pv="INT10", auto_monitor=True, name="int10", kind=Kind.hinted)
    int11 = Component(EpicsSignal, "INT11_RBV", put_complete=True, write_pv="INT11", auto_monitor=True, name="int11", kind=Kind.hinted)

    float0 = Component(EpicsSignalRO, "REAL0_RBV", auto_monitor=True, name="float0", kind=Kind.hinted)
    float1 = Component(EpicsSignalRO, "REAL1_RBV", auto_monitor=True, name="float1", kind=Kind.hinted)
    float2 = Component(EpicsSignalRO, "REAL2_RBV", auto_monitor=True, name="float2", kind=Kind.hinted)
    float3 = Component(EpicsSignalRO, "REAL3_RBV", auto_monitor=True, name="float3", kind=Kind.hinted)
    float16 = Component(EpicsSignal, "REAL16_RBV", write_pv="REAL16", put_complete=True, auto_monitor=True, name="float16", kind=Kind.hinted)
    float17 = Component(EpicsSignal, "REAL17_RBV", write_pv="REAL17", put_complete=True, auto_monitor=True, name="float17", kind=Kind.hinted)
    float18 = Component(EpicsSignal, "REAL18_RBV", write_pv="REAL18", put_complete=True, auto_monitor=True, name="float18", kind=Kind.hinted)
    float19 = Component(EpicsSignal, "REAL19_RBV", write_pv="REAL19", put_complete=True, auto_monitor=True, name="float19", kind=Kind.hinted)

    _str0 = Component(EpicsStringRO, "STR0_RBV", auto_monitor=True, name="str0_raw", kind=Kind.omitted)
    str0 = Component(DerivedSignal, "_str0", inverse=epicsCharArray2String, auto_monitor=True, name="str0", kind=Kind.hinted)
    
    str1 = Component(EpicsStringRO, "STR1_RBV", auto_monitor=True, name="str1", kind=Kind.hinted)
    str4 = Component(EpicsString, "STR4_RBV", put_complete=True, auto_monitor=True, write_pv="STR4", name="str4", kind=Kind.hinted)
    str5 = Component(EpicsString, "STR5_RBV", put_complete=True, auto_monitor=True, write_pv="STR5", name="str4", kind=Kind.hinted)    



class aa1AxisIo(Device):
    """ Analog / digital Input-Output
    
    This class provides convenience wrappers around the Aerotech API's axis 
    specific IO functionality. Note that this is a low-speed API, actual work
    should be done in AeroScript. Only one IO pin is polled simultaneously!
    """
    polllvl = Component(EpicsSignal, "POLLLVL", put_complete=True, kind=Kind.config)
    
    ai_addr = Component(EpicsSignal, "AI-ADDR", put_complete=True, kind=Kind.config)
    ai = Component(EpicsSignalRO, "AI-RBV", auto_monitor=True, kind=Kind.hinted)

    ao_addr = Component(EpicsSignal, "AO-ADDR", put_complete=True, kind=Kind.config)
    ao = Component(EpicsSignal, "AO-RBV", write_pv="AO", auto_monitor=True, kind=Kind.hinted)

    di_addr = Component(EpicsSignal, "DI-ADDR", put_complete=True, kind=Kind.config)
    di = Component(EpicsSignalRO, "DI-RBV", auto_monitor=True, kind=Kind.hinted)

    do_addr = Component(EpicsSignal, "DO-ADDR", put_complete=True, kind=Kind.config)
    do = Component(EpicsSignal, "DO-RBV", write_pv="DO", auto_monitor=True, kind=Kind.hinted)

    def setAnalog(self, pin: int, value: float, settle_time=0.05):
        # Set the address
        self.ao_addr.set(pin).wait()
        # Set the voltage
        self.ao.set(value, settle_time=settle_time).wait()
        
    def setDigital(self, pin: int, value: int, settle_time=0.05):
        # Set the address
        self.do_addr.set(pin).wait()
        # Set the voltage
        self.do.set(value, settle_time=settle_time).wait()
        


class aa1AxisPsoBase(Device):
    """ Position Sensitive Output - Base class
    
    This class provides convenience wrappers around the Aerotech IOC's PSO 
    functionality. As a base class, it's just a collection of PVs without 
    significant logic (that should be implemented in the child classes). 
    It uses event-waveform concept to produce signals on the configured 
    output pin: a specified position based event will trigger the generation
    of a waveform on the oputput that can be either used as exposure enable, 
    as individual trigger or as a series of triggers per each event. 
    As a first approach, the module follows a simple pipeline structure:
        Genrator --> Event --> Waveform --> Output
           
    Specific operation modes should be implemented in child classes.
    """   
    # ########################################################################
    # General module status
    status = Component(EpicsSignalRO, "STATUS", auto_monitor=True, kind=Kind.hinted)
    output = Component(EpicsSignalRO, "OUTPUT-RBV", auto_monitor=True, kind=Kind.hinted)
    _eventSingle = Component(EpicsSignal, "EVENT:SINGLE",  put_complete=True, kind=Kind.omitted)
    _reset = Component(EpicsSignal, "RESET", put_complete=True, kind=Kind.omitted)    
    posInput = Component(EpicsSignal, "DIST:INPUT",  put_complete=True, kind=Kind.omitted)   

    # ########################################################################
    # PSO Distance event module
    dstEventsEna = Component(EpicsSignal, "DIST:EVENTS",  put_complete=True, kind=Kind.omitted)
    dstCounterEna = Component(EpicsSignal, "DIST:COUNTER", put_complete=True, kind=Kind.omitted)
    dstCounterVal = Component(EpicsSignalRO, "DIST:CTR0_RBV", auto_monitor=True, kind=Kind.hinted)
    dstArrayDepleted = Component(EpicsSignalRO, "DIST:ARRAY-DEPLETED-RBV", auto_monitor=True, kind=Kind.hinted)
    
    dstDirection = Component(EpicsSignal, "DIST:EVENTDIR",  put_complete=True, kind=Kind.omitted)    
    dstDistance = Component(EpicsSignal, "DIST:DISTANCE", put_complete=True, kind=Kind.hinted)
    dstDistanceArr = Component(EpicsSignal, "DIST:DISTANCES", put_complete=True, kind=Kind.omitted)
    dstArrayRearm = Component(EpicsSignal, "DIST:REARM-ARRAY", put_complete=True, kind=Kind.omitted)

    # ########################################################################
    # PSO Window event module    
    winEvents = Component(EpicsSignal, "WINDOW:EVENTS", put_complete=True, kind=Kind.omitted)
    winOutput = Component(EpicsSignal, "WINDOW0:OUTPUT", put_complete=True, kind=Kind.omitted)
    winInput = Component(EpicsSignal, "WINDOW0:INPUT", put_complete=True, kind=Kind.omitted)
    winCounter = Component(EpicsSignal, "WINDOW0:COUNTER", put_complete=True, kind=Kind.omitted)
    _winLower = Component(EpicsSignal, "WINDOW0:LOWER", put_complete=True, kind=Kind.omitted)
    _winUpper = Component(EpicsSignal, "WINDOW0:UPPER", put_complete=True, kind=Kind.omitted)
    
    # ########################################################################
    # PSO waveform module
    waveEnable = Component(EpicsSignal, "WAVE:ENABLE", put_complete=True, kind=Kind.omitted)
    waveMode = Component(EpicsSignal, "WAVE:MODE", put_complete=True, kind=Kind.omitted)
    #waveDelay = Component(EpicsSignal, "WAVE:DELAY", put_complete=True, kind=Kind.omitted)
    
    # PSO waveform pulse output
    #pulseTrunc = Component(EpicsSignal, "WAVE:PULSE:TRUNC", put_complete=True, kind=Kind.omitted)
    pulseOnTime = Component(EpicsSignal, "WAVE:PULSE:ONTIME", put_complete=True, kind=Kind.omitted)
    pulseWindow = Component(EpicsSignal, "WAVE:PULSE:PERIOD", put_complete=True, kind=Kind.omitted)
    pulseCount = Component(EpicsSignal, "WAVE:PULSE:COUNT", put_complete=True, kind=Kind.omitted)
    pulseApply = Component(EpicsSignal, "WAVE:PULSE:APPLY", put_complete=True, kind=Kind.omitted)

    # ########################################################################
    # PSO output module
    outPin = Component(EpicsSignal, "PIN", put_complete=True, kind=Kind.omitted)
    outSource = Component(EpicsSignal, "SOURCE", put_complete=True, kind=Kind.omitted)    

    def fire(self, settle_time=None):
        """ Fire a single PSO event (i.e. manual software trigger)"""
        self._eventSingle.set(1, settle_time=settle_time).wait()

    def toggle(self):
        orig_waveMode = self.waveMode.get()
        self.waveMode.set("Toggle").wait()
        self.fire(0.1)
        self.waveMode.set(orig_waveMode).wait()





class aa1AxisPsoDistance(aa1AxisPsoBase):
    """ Position Sensitive Output - Distance mode
    
    This class provides convenience wrappers around the Aerotech API's PSO 
    functionality in distance mode. It uses event-waveform concept to produce 
    signals on the configured output pin: a specified position based event 
    will trigger the generation af a waveform on the oputput that can be either
    used as exposure enable, as individual trigger or as a series of triggers 
    per each event. 
    As a first approach, the module follows a simple pipeline structure:
        Genrator --> Event --> Waveform --> Output
           
    The module provides configuration interface to common functionality, such 
    as fixed distance or array based triggering and can serve as a base for
    future advanced functionality. The relative distances ease the limitations 
    coming from 32 bit PSO positions.
    For a more detailed description of additional signals and masking plase 
    refer to Automation1's online manual.
    """   
    
    def __init__(self, *args, **kwargs):
        """ Member declarations in init"""
        self._Vdistance = 3.141592
        super().__init__(*args, **kwargs)
        
    # ########################################################################
    # PSO high level interface
    def configure(self, distance: Union[float, np.ndarray, list, tuple], wmode: str,
                       t_pulse: float=2000, w_pulse: float=5000, n_pulse: int=1,
                       posInput: int=None, pinOutput: int=None, **argv) -> None:
        """ Simplified configuration interface to access the most common 
            functionality for distance mode PSO.
            
            :param distance: The trigger distance or the array of distances between subsequent points.
            :param wmode: Waveform mode configuration, usually pulsed/toggled. 
        """
        # Validate input parameters
        if wmode not in ["pulse", "pulsed", "toggle", "toggled"]:
            raise RuntimeError(f"Unsupported distace triggering mode: {wmode}")

        
        # Set the position data source and output pin
        if posInput is not None:
            self.posInput.set(posInput).wait()
        if pinOutput is not None:
            self.pinOutput.set(pinOutput).wait()
        
        # Configure distance generator (also resets counter to 0)
        self._distanceValue = distance
        if isinstance(distance, (float, int)):
            self.dstDistance.set(distance).wait()
        elif isinstance(distance, (np.ndarray, list, tuple)):
            self.dstDistanceArr.set(distance).wait()
        
        self.winEvents.set("Off").wait()
        self.dstCounterEna.set("Off").wait()                 
        self.dstEventsEna.set("Off").wait()
        
        # Configure the pulsed/toggled waveform        
        if wmode in ["toggle", "toggled"]:
            # Switching to simple toggle mode
            self.waveEnable.set("On").wait()
            self.waveMode.set("Toggle").wait()
      
        elif wmode in ["pulse", "pulsed"]:           
            # Switching to pulsed mode        
            self.waveEnable.set("On").wait()            
            self.waveMode.set("Pulse").wait()             
            # Setting pulse shape        
            self.pulseWindow.set(w_pulse).wait()
            self.pulseOnTime.set(t_pulse).wait()
            self.pulseCount.set(n_pulse).wait()
            # Commiting configuration
            self.pulseApply.set(1).wait()
            # Enabling PSO waveform outputs
            self.waveEnable.set("On").wait()
        else:
            raise RuntimeError(f"Unsupported waveform mode: {wmode}")           
        
        # Ensure output is set to low
        if self.output.value:
            self.toggle()        
        
        # Set PSO output data source
        self.outSource.set("Waveform").wait()      
        
    # ########################################################################
    # Bluesky step scan interface
    def stage(self, settle_time=None):
        self.dstEventsEna.set("On").wait()
        if isinstance(self._distanceValue, (np.ndarray, list, tuple)):       
            self.dstArrayRearm.set(1).wait()
        self.dstCounterEna.set("On").wait()         
        if settle_time is not None:
            sleep(settle_time)
        return super().stage()

    def trigger(self): 
        return super().trigger()        
                
    def unstage(self):
        # Turn off counter monitoring
        self.dstEventsEna.set("Off").wait()
        self.dstCounterEna.set("Off").wait()          
        return super().unstage()
    # ########################################################################
    # Bluesky flyer interface
    def kickoff(self) -> StatusBase:
        # Rearm the configured array
        if hasattr(self, "_distanceValue") and isinstance(self._distanceValue, (np.ndarray, list, tuple)):       
            self.dstArrayRearm.set(1).wait()
        # Start monitoring the counters
        self.dstEventsEna.set("On").wait()
        self.dstCounterEna.set("On").wait()         
        status = StatusBase()
        status.set_finished()
        return status
    
    def complete(self) -> StatusBase:
        """ Bluesky flyer interface"""
        # Array mode waits until the buffer is empty
        if isinstance(self._distanceValue, (np.ndarray, list, tuple)):      
            # Define wait until the busy flag goes down (excluding initial update)
            timestamp_ = 0
            def notRunning(*args, old_value, value, timestamp, **kwargs):
                nonlocal timestamp_       
                result = False if (timestamp_== 0) else bool(int(value) & 0x1000)   
                print(f"Old {old_value}\tNew: {value}\tResult: {result}")
                timestamp_ = timestamp
                return result
            
            # Subscribe and wait for update
            status = SubscriptionStatus(self.status, notRunning, settle_time=0.5)                
        else:
            # In distance trigger mode there's no specific goal
            status = StatusBase()
            status.set_finished()
        return status
    
    def describe_collect(self) -> OrderedDict:
        ret = OrderedDict()
        ret['index'] = {'source': "internal", 'dtype': 'integer', 'shape': [], 'units': '', 'lower_ctrl_limit': 0, 'upper_ctrl_limit': 0}
        return {self.name: ret}
        
    def collect(self) -> OrderedDict:
        ret = OrderedDict()
        ret["timestamps"] = {"index": time.time()}
        ret["data"] = {"index": self.dstCounterVal.value }
        yield ret
    



class aa1AxisPsoWindow(aa1AxisPsoBase):
    """ Position Sensitive Output - Window mode
    
    This class provides convenience wrappers around the Aerotech API's PSO 
    functionality in window mode. It can either use the event-waveform concept 
    or provide a direct window output signal (in/out) to the output pin. The 
    latter is particularly well-suited for the generation of trigger enable 
    signals, while in event mode it allows the finetuning of trigger lenth.
    As a first approach, the module follows a simple pipeline structure:
        Genrator --> Event --> Waveform --> Output pin
        Genrator --> Window output --> Output pin

    The module provides configuration interface to common functionality, such 
    as repeated trigger enable signal or fixed area scaning. Unfortunately the 
    entered positions are absolute, meaning this mode has an inherent limitation 
    with encoder counters being kept in 32 bit integers.
    For a more detailed description of additional signals and masking plase 
    refer to Automation1's online manual.
    """   
    def __init__(self, *args, **kwargs):
        """ Member declarations in init"""
        self._mode = "output"
        self._eventMode = "Enter"
        super().__init__(*args, **kwargs)

    # ########################################################################
    # PSO high level interface        
    def configure(self, bounds: Union[np.ndarray, list, tuple], wmode: str, emode: str="Enter",
                       t_pulse: float=2000, w_pulse: float=5000, n_pulse: int=1,
                       posInput: int=None, pinOutput: int=None, **argv) -> None:
        """ Simplified configuration interface to access the most common 
            functionality for distance mode PSO.
            
            :param distance: The trigger distance or the array of distances between subsequent points.
            :param wmode: Waveform mode configuration, usually output/pulsed/toggled. 
        """
        # Validate input parameters
        if wmode not in ["pulse", "pulsed", "toggle", "toggled", "output", "flag"]:
            raise RuntimeError(f"Unsupported window triggering mode: {wmode}")
        self._mode = wmode
        self._eventMode = emode
        
        # Set the position data source and output pin
        if posInput is not None:
            self.posInput.set(posInput).wait()
        if pinOutput is not None:
            self.outPin.set(pinOutput).wait()

        # Configure the window module
        # Set the window ranges (MUST be in start position)
        if len(bounds) == 2:
            self.winCounter.set(0).wait()
            self._winLower.set(bounds[0]).wait()
            self._winUpper.set(bounds[1]).wait()     
                
        elif isinstance(bounds, np.ndarray):
            # ToDo...
            pass

        # Don't start triggering just yet
        self.winOutput.set("Off").wait()
        self.winEvents.set("Off").wait()

        # Configure the pulsed/toggled waveform        
        if wmode in ["toggle", "toggled"]:
            # Switching to simple toggle mode
            self.waveEnable.set("On").wait()
            self.waveMode.set("Toggle").wait()           
        elif wmode in ["pulse", "pulsed"]:           
            # Switching to pulsed mode        
            self.waveEnable.set("On").wait()            
            self.waveMode.set("Pulse").wait()     
            # Setting pulse shape        
            self.pulseWindow.set(w_pulse).wait()
            self.pulseOnTime.set(t_pulse).wait()
            self.pulseCount.set(n_pulse).wait()
            # Commiting configuration
            self.pulseApply.set(1).wait()
            # Enabling PSO waveform outputs
            self.waveEnable.set("On").wait()
        elif wmode in ["output", "flag"]:
            self.waveEnable.set("Off").wait()
        else:
            raise RuntimeError(f"Unsupported window mode: {wmode}")         

        # Set PSO output data source
        if wmode in ["toggle", "toggled", "pulse", "pulsed"]:
            self.outSource.set("Waveform").wait()    
        elif wmode in ["output", "flag"]:
            self.outSource.set("Window").wait()    
      
    def stage(self, settle_time=None):
        if self.outSource.get() in ["Window", 2]:
            self.winOutput.set("On").wait()
        else:    
            self.winEvents.set(self._eventMode).wait()
        if settle_time is not None:
            sleep(settle_time)
        return super().stage()

    def kickoff(self, settle_time=None): 
        if self.outSource.get() in ["Window", 2]:
            self.winOutput.set("On").wait()
        else:    
            self.winEvents.set(self._eventMode).wait()
        if settle_time is not None:
            sleep(settle_time)         
        
    def unstage(self, settle_time=None):
        self.winOutput.set("Off").wait()
        self.winEvents.set("Off").wait()
        if settle_time is not None:
            sleep(settle_time)       
        return super().unstage()







class aa1AxisDriveDataCollection(Device):
    """ Axis data collection
    
    This class provides convenience wrappers around the Aerotech API's axis 
    specific data collection functionality. This module allows to record
    hardware synchronized signals with up to 200 kHz.
    
    The default configuration is using a fixed memory mapping allowing up to 
    1 million recorded data points on an XC4e (this depends on controller).
    """
    
    # ########################################################################
    # General module status
    nsamples_rbv = Component(EpicsSignalRO, "SAMPLES_RBV", auto_monitor=True, kind=Kind.hinted)
    _switch = Component(EpicsSignal, "ACQUIRE", put_complete=True, kind=Kind.omitted)
    _input0 = Component(EpicsSignal, "INPUT0", put_complete=True, kind=Kind.config)
    _input1 = Component(EpicsSignal, "INPUT1", put_complete=True, kind=Kind.config)
    _trigger = Component(EpicsSignal, "TRIGGER", put_complete=True, kind=Kind.config)

    npoints = Component(EpicsSignal, "NPOINTS", put_complete=True, kind=Kind.config)
    _readback0 = Component(EpicsSignal, "AREAD0", kind=Kind.omitted)
    _readstatus0 = Component(EpicsSignalRO, "AREAD0_RBV", auto_monitor=True, kind=Kind.omitted)
    _readback1 = Component(EpicsSignal, "AREAD1", kind=Kind.omitted)
    _readstatus1 = Component(EpicsSignalRO, "AREAD1_RBV", auto_monitor=True, kind=Kind.omitted)
    
    _buffer0 = Component(EpicsSignalRO, "BUFFER0", auto_monitor=True, kind=Kind.hinted)
    _buffer1 = Component(EpicsSignalRO, "BUFFER1", auto_monitor=True, kind=Kind.hinted)

    def configure(self, npoints, 
                  trigger: int=DriveDataCaptureTrigger.PsoOutput,
                  source0: int=DriveDataCaptureInput.PrimaryFeedback,
                  source1: int=DriveDataCaptureInput.PositionCommand):
        self._input0.set(source0).wait()
        self._input1.set(source1).wait()
        self._trigger.set(trigger).wait()
        # This allocates the memory...
        self.npoints.set(npoints).wait()
        
        
    # Bluesky step scanning interface 
    def stage(self, settle_time=0.1):
        super().stage()
        self._switch.set("Start", settle_time=0.5).wait()                
        status = Status(timeout=0.1, settle_time=settle_time).set_finished()
        return status

    def unstage(self, settle_time=0.1):
        self._switch.set("Stop", settle_time=settle_time).wait()
        super().unstage()
   
    # Bluesky flyer interface 
    def kickoff(self, settle_time=0.1) -> Status:
        status = self._switch.set("Start", settle_time=settle_time)                
        return status

    def complete(self, settle_time=0.1) -> Status:
        """ DDC just reads back whatever is available in the buffers"""
        status  = Status(settle_time=settle_time)
        status.set_finished()
        return status
           
    def _collect(self, index=0):
        """ Force a readback of the data buffer
        
            Note that there's a weird behaviour in ophyd that it issues an 
            initial update event with the initial value but 0 timestamp. Theese
            old_values are invalid and must be filtered out. 
        """
        
        # Define wait until the busy flag goes down (excluding initial update)
        timestamp_ = 0
        def negEdge(*args, old_value, value, timestamp, **kwargs):
            nonlocal timestamp_            
            result = False if (timestamp_== 0) else (old_value == 1 and value == 0)         
           # print(f"\nBuffer1 status:\t{old_value} ({timestamp_}) to  {value} ({timestamp}) Result: {result}")
            timestamp_ = timestamp
            return result
        
        if index==0:
            status = SubscriptionStatus(self._readstatus0, negEdge, settle_time=0.5)
            self._readback0.set(1).wait()
        elif index==1:
            status = SubscriptionStatus(self._readstatus1, negEdge, settle_time=0.5)
            self._readback1.set(1).wait()
    
        # Start asynchronous readback
        status.wait()
        return status
        

    def describe_collect(self) -> OrderedDict:
        ret = OrderedDict()
        ret['buffer0'] = {'source': "internal", 'dtype': 'array', 'shape': [], 'units': '', 'lower_ctrl_limit': 0, 'upper_ctrl_limit': 0}
        ret['buffer1'] = {'source': "internal", 'dtype': 'array', 'shape': [], 'units': '', 'lower_ctrl_limit': 0, 'upper_ctrl_limit': 0}
        return {self.name: ret}
        
    def collect(self) -> OrderedDict:

        self._collect(0).wait()
        self._collect(1).wait()

        b0 = self._buffer0.value
        b1 = self._buffer1.value
        ret = OrderedDict()
        ret["timestamps"] = {"buffer0": time.time(), "buffer1": time.time() }
        ret["data"] = {"buffer0": b0, "buffer1": b1 }
        yield ret
    



# Automatically start simulation if directly invoked
if __name__ == "__main__":
    
    # Drive data collection
    tcDdc = aa1AxisDriveDataCollection("X02DA-ES1-SMP1:ROTY:DDC:", name="tcddc")
    tcDdc.wait_for_connection()


