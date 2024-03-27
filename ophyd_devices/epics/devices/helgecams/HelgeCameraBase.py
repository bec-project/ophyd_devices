# -*- coding: utf-8 -*-
"""
Created on Wed Dec  6 11:33:54 2023

@author: mohacsi_i
"""

from ophyd import Device, Component, EpicsMotor, EpicsSignal, EpicsSignalRO, Kind
from ophyd.status import Status, SubscriptionStatus, StatusBase, DeviceStatus
from time import sleep
import warnings
import numpy as np


class HelgeCameraCore(Device):
    """Ophyd baseclass for Helge camera IOCs
    
    This class provides wrappers for Helge's camera IOCs around SwissFEL and 
    for high performance SLS 2.0 cameras. 

    The IOC's operation is a bit arcane.

    

    """   
    USER_ACCESS = ["kickoff"]
    # ########################################################################
    # General hardware info
    camType = Component(EpicsSignalRO, "QUERY",  kind=Kind.omitted)
    camBoard = Component(EpicsSignalRO, "BOARD", kind=Kind.config)
    #camSerial = Component(EpicsSignalRO, "SERIALNR", kind=Kind.config)
    camError = Component(EpicsSignalRO, "ERRCODE", auto_monitor=True, kind=Kind.config)
    camWarning = Component(EpicsSignalRO, "WARNCODE", auto_monitor=True, kind=Kind.config)    
    
    # ########################################################################
    # Acquisition commands
    camStatusCmd = Component(EpicsSignal, "CAMERASTATUS", put_complete=True, kind=Kind.config)

    # ########################################################################
    # Polled state maschine with separate transition states
    camStatusCode = Component(EpicsSignalRO, "STATUSCODE", auto_monitor=True, kind=Kind.config)
    camSetParam = Component(EpicsSignal, "SET_PARAM", auto_monitor=True, kind=Kind.config)
    camSetParamBusy = Component(EpicsSignalRO, "BUSY_SET_PARAM", auto_monitor=True, kind=Kind.config)
    camCamera = Component(EpicsSignalRO, "CAMERA", auto_monitor=True, kind=Kind.config)
    camCameraBusy = Component(EpicsSignalRO, "BUSY_CAMERA", auto_monitor=True, kind=Kind.config)
    camInit= Component(EpicsSignalRO, "INIT", auto_monitor=True, kind=Kind.config)
    camInitBusy = Component(EpicsSignalRO, "BUSY_INIT", auto_monitor=True, kind=Kind.config)
    #camRemoval = Component(EpicsSignalRO, "REMOVAL", auto_monitor=True, kind=Kind.config)

    camStateString = Component(EpicsSignalRO, "SS_CAMERA", string=True, auto_monitor=True, kind=Kind.config)


    @property
    def state(self) -> str:
        """ Single word camera state"""
        if self.camSetParamBusy.value:
            return "BUSY"        
        if self.camStatusCode.value==2 and self.camInit.value==1:
            return "IDLE"  
        if self.camStatusCode.value==6 and self.camInit.value==1:
            return "RUNNING"
        if self.camRemoval.value==0 and self.camInit.value==0:        
            return "OFFLINE"
        #if self.camRemoval.value:
        #    return "REMOVED"
        return "UNKNOWN"

    @state.setter
    def state(self):
        raise ReadOnlyError("State is a ReadOnly property")

    def configure(self, d: dict = {}) -> tuple:
        if self.state in ["OFFLINE", "REMOVED", "RUNNING"]:
            raise RuntimeError(f"Can't change configuration from state {self.state}")
  
    def stage(self) -> None:
        """ Start acquisition"""
        
        # Acquisition is only allowed when the IOC is not busy
        if self.state in ("OFFLINE", "BUSY", "REMOVED", "RUNNING"):
            raise RuntimeError(f"Camera in in state: {self.state}")

        # Start the acquisition (this sets parameers and starts acquisition)
        self.camStatusCmd.set("Running").wait()

        # Subscribe and wait for update
        def isRunning(*args, old_value, value, timestamp, **kwargs):
            return bool(self.state=="RUNNING")
        status = SubscriptionStatus(self.camStatusCode, isRunning, settle_time=0.2)
        status.wait()
        # Call parent        
        super().stage()

    def kickoff(self, settle_time=0.2) -> DeviceStatus:
        """ Start acquisition"""
    
        # Acquisition is only allowed when the IOC is not busy
        if self.state in ("OFFLINE", "BUSY", "REMOVED", "RUNNING"):
            raise RuntimeError(f"Camera in in state: {self.state}")
            
        # Start the acquisition
        self.camStatusCmd.set("Running").wait()
   
        # Subscribe and wait for update
        def isRunning(*args, old_value, value, timestamp, **kwargs):
            # result = bool(value==6 and self.camInit.value==1)
            result = bool(self.state=="RUNNING")
            return result
        status = SubscriptionStatus(self.camStatusCode, isRunning, settle_time=0.2)
        return status

    def stop(self):
        """ Stop the running acquisition """
        self.camStatusCmd.set("Idle").wait()
        super().unstage()

    def unstage(self):
        """ Stop the running acquisition and unstage the device"""
        self.camStatusCmd.set("Idle").wait()
        super().unstage()







class HelgeCameraBase(HelgeCameraCore):
    """Ophyd baseclass for Helge camera IOCs
    
    This class provides wrappers for Helge's camera IOCs around SwissFEL and 
    for high performance SLS 2.0 cameras. Theese are mostly PCO cameras running 
    on a special Windows IOC host with lots of RAM and CPU power.

    The IOC's operation is a bit arcane, and is documented on the "read the code"
    level. However the most important part is the state machine of 7+1 PV signals:
    INIT
    BUSY_INIT
    SET_PARAM
    BUSY_SET_PARAM
    CAMERA
    BUSY_CAMERA
    CAMERASTATUSCODE
    CAMERASTATUS

    

    """   
    
    USER_ACCESS = ["describe", "shape", "bin", "roi"]
    # ########################################################################
    # Additional status info
    busy = Component(EpicsSignalRO, "BUSY", auto_monitor=True, kind=Kind.config)
    camState = Component(EpicsSignalRO, "SS_CAMERA", auto_monitor=True, kind=Kind.config)
    camProgress = Component(EpicsSignalRO, "CAMPROGRESS", auto_monitor=True, kind=Kind.config)
    camRate = Component(EpicsSignalRO, "CAMRATE", auto_monitor=True, kind=Kind.config)

    # ########################################################################
    # Acquisition configuration    
    acqMode = Component(EpicsSignalRO, "ACQMODE", auto_monitor=True, kind=Kind.config)
    acqExpTime = Component(EpicsSignalRO, "EXPOSURE", auto_monitor=True, kind=Kind.config)
    acqDelay = Component(EpicsSignalRO, "DELAY", auto_monitor=True, kind=Kind.config)
    acqTriggerEna = Component(EpicsSignalRO, "TRIGGER", auto_monitor=True, kind=Kind.config)
    #acqTriggerSource = Component(EpicsSignalRO, "TRIGGERSOURCE", auto_monitor=True, kind=Kind.config)
    #acqTriggerEdge = Component(EpicsSignalRO, "TRIGGEREDGE", auto_monitor=True, kind=Kind.config)
    
    # ########################################################################
    # Image size settings
    # Priority is: binning -> roi -> final size
    pxBinX = Component(EpicsSignalRO, "BINX", auto_monitor=True, kind=Kind.config)
    pxBinY = Component(EpicsSignalRO, "BINY", auto_monitor=True, kind=Kind.config)
    pxRoiX_lo = Component(EpicsSignalRO, "REGIONX_START", auto_monitor=True, kind=Kind.config)
    pxRoiX_hi = Component(EpicsSignalRO, "REGIONX_END", auto_monitor=True, kind=Kind.config)
    pxRoiY_lo = Component(EpicsSignalRO, "REGIONY_START", auto_monitor=True, kind=Kind.config)
    pxRoiY_hi = Component(EpicsSignalRO, "REGIONY_END", auto_monitor=True, kind=Kind.config)
    pxNumX = Component(EpicsSignalRO, "WIDTH", auto_monitor=True, kind=Kind.config)
    pxNumY = Component(EpicsSignalRO, "HEIGHT", auto_monitor=True, kind=Kind.config)


    # ########################################################################
    # Buffer configuration  
    bufferRecMode = Component(EpicsSignalRO, "RECMODE", auto_monitor=True, kind=Kind.config)
    bufferStoreMode = Component(EpicsSignalRO, "STOREMODE", auto_monitor=True, kind=Kind.config)
    fileRecMode = Component(EpicsSignalRO, "RECMODE", auto_monitor=True, kind=Kind.config)
    
    image = Component(EpicsSignalRO, "FPICTURE", kind=Kind.omitted)
    
    # ########################################################################
    # File interface
    camFileFormat = Component(EpicsSignal, "FILEFORMAT", put_complete=True, kind=Kind.config)
    camFilePath = Component(EpicsSignal, "FILEPATH", put_complete=True, kind=Kind.config)
    camFileName = Component(EpicsSignal, "FILENAME", put_complete=True, kind=Kind.config)
    camFileNr = Component(EpicsSignal, "FILENR", put_complete=True, kind=Kind.config)
    camFilePath = Component(EpicsSignal, "FILEPATH", put_complete=True, kind=Kind.config)
    camFileTransferStart = Component(EpicsSignal, "FTRANSFER", put_complete=True, kind=Kind.config)
    camFileTransferStop = Component(EpicsSignal, "SAVESTOP", put_complete=True, kind=Kind.config)



    def configure(self, d: dict = {}) -> tuple:
        """
        Camera configuration instructions:
        After setting the corresponding PVs, one needs to process SET_PARAM and wait until 
        BUSY_SET_PARAM goes high and low, followed by SET_PARAM goes high and low. This will 
        both send the settings to the camera and allocate the necessary buffers in the correct 
        size and shape (that takes time). Starting the exposure with CAMERASTATUS will also 
        call SET_PARAM, but it might take long.
        """
        old = self.read_configuration()
        super().configure(d)
    
        if "exptime" in d:
            exposure_time = d['exptime']
            if exposure_time is not None:
                self.acqExpTime.set(exposure_time).wait()

        if "roi" in d:
            roi = d["roi"]
            if not isinstance(roi, (list, tuple)):
                raise ValueError(f"Unknown ROI data type {type(roi)}")
            if not len(roi[0])==2 and len(roi[1])==2:
                raise ValueError(f"Unknown ROI shape: {roi}")           
            self.pxRoiX_lo.set(roi[0][0]).wait()
            self.pxRoiX_hi.set(roi[0][1]).wait()
            self.pxRoiY_lo.set(roi[1][0]).wait()
            self.pxRoiY_hi.set(roi[1][1]).wait()

        if "bin" in d:
            binning = d["bin"]
            if not isinstance(binning, (list, tuple)):
                raise ValueError(f"Unknown BINNING data type {type(binning)}")
            if not len(binning)==2:
                raise ValueError(f"Unknown ROI shape: {binning}")           
            self.pxBinX.set(binning[0]).wait()
            self.pxBinY.set(binning[1]).wait()
        
        # State machine
        # Initial: BUSY and SET both low
        # 1. BUSY set to high 
        # 2. BUSY goes low, SET goes high
        # 3. SET goes low
        self.camSetParam.set(1).wait()
        def risingEdge(*args, old_value, value, timestamp, **kwargs):
            return bool(not old_value and value)
        def fallingEdge(*args, old_value, value, timestamp, **kwargs):
            return bool(old_value and not value)
        # Subscribe and wait for update
        status = SubscriptionStatus(self.camSetParam, fallingEdge, settle_time=0.5)
        status.wait()
        new = self.read_configuration()
        return (old, new)
                


    @property
    def shape(self):
        return (int(self.pxNumX.value), int(self.pxNumY.value))
    
    @shape.setter
    def shape(self):
        raise ReadOnlyError("Shape is a ReadOnly property")

    @property
    def bin(self):
        return (int(self.pxBinX.value), int(self.pxBinY.value))
    
    @bin.setter
    def bin(self):
        raise ReadOnlyError("Bin is a ReadOnly property")

    @property
    def roi(self):
        return ((int(self.pxRoiX_lo.value), int(self.pxRoiX_hi.value)), (int(self.pxRoiY_lo.value), int(self.pxRoiY_hi.value)))

    @roi.setter
    def roi(self):
        raise ReadOnlyError("Bin is a ReadOnly property")











# Automatically connect to test camera if directly invoked
if __name__ == "__main__":
    
    # Drive data collection
    cam = HelgeCameraBase("SINBC02-DSRM310:", name="mcpcam")
    cam.wait_for_connection()









