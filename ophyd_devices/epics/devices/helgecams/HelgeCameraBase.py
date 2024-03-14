# -*- coding: utf-8 -*-
"""
Created on Wed Dec  6 11:33:54 2023

@author: mohacsi_i
"""

from ophyd import Device, Component, EpicsMotor, EpicsSignal, EpicsSignalRO, Kind
from ophyd.status import Status, SubscriptionStatus, StatusBase
from time import sleep
import warnings
import numpy as np




class HelgeCameraBase(Device):
    """ Ophyd baseclass for Helge camera IOCs
    
    This class provides wrappers for Helge's camera IOCs around SwissFEL and 
    for high performance SLS 2.0 cameras. 

    The IOC's operatio

    

    """   
    # ########################################################################
    # General hardware info
    camType = Component(EpicsSignalRO, "QUERY",  kind=Kind.omitted)
    camBoard = Component(EpicsSignalRO, "BOARD", kind=Kind.config)
    #camSerial = Component(EpicsSignalRO, "SERIALNR", kind=Kind.config)

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
    # Acquisition commands


    # ########################################################################
    # Polled CamStatus
    busy = Component(EpicsSignalRO, "BUSY", auto_monitor=True, kind=Kind.config)
    camState = Component(EpicsSignalRO, "SS_CAMERA", auto_monitor=True, kind=Kind.config)

    camError = Component(EpicsSignalRO, "ERRCODE", auto_monitor=True, kind=Kind.config)
    camWarning = Component(EpicsSignalRO, "WARNCODE", auto_monitor=True, kind=Kind.config)
    camProgress = Component(EpicsSignalRO, "CAMPROGRESS", auto_monitor=True, kind=Kind.config)
    camRate = Component(EpicsSignalRO, "CAMRATE", auto_monitor=True, kind=Kind.config)

    # Weird state maschine with separate transition states
    camStatusCmd = Component(EpicsSignal, "CAMERASTATUS", put_complete=True, kind=Kind.config)
    camSetParam = Component(EpicsSignalRO, "SET_PARAM", auto_monitor=True, kind=Kind.config)
    camSetParamBusy = Component(EpicsSignalRO, "BUSY_SET_PARAM", auto_monitor=True, kind=Kind.config)
    camCamera = Component(EpicsSignalRO, "CAMERA", auto_monitor=True, kind=Kind.config)
    #camCameraBusy = Component(EpicsSignalRO, "CAMERA_BUSY", auto_monitor=True, kind=Kind.config)
    camInit= Component(EpicsSignalRO, "INIT", auto_monitor=True, kind=Kind.config)
    #camInitBusy = Component(EpicsSignalRO, "INIT_BUSY", auto_monitor=True, kind=Kind.config)

    # ########################################################################
    # Acquisition configuration    
    acqMode = Component(EpicsSignalRO, "ACQMODE", auto_monitor=True, kind=Kind.config)
    acqExpTime = Component(EpicsSignalRO, "EXPOSURE", auto_monitor=True, kind=Kind.config)
    acqDelay = Component(EpicsSignalRO, "DELAY", auto_monitor=True, kind=Kind.config)
    acqTriggerEna = Component(EpicsSignalRO, "TRIGGER", auto_monitor=True, kind=Kind.config)
    #acqTriggerSource = Component(EpicsSignalRO, "TRIGGERSOURCE", auto_monitor=True, kind=Kind.config)
    #acqTriggerEdge = Component(EpicsSignalRO, "TRIGGEREDGE", auto_monitor=True, kind=Kind.config)
    
    
    bufferRecMode = Component(EpicsSignalRO, "RECMODE", auto_monitor=True, kind=Kind.config)
    bufferStoreMode = Component(EpicsSignalRO, "STOREMODE", auto_monitor=True, kind=Kind.config)
    fileRecMode = Component(EpicsSignalRO, "RECMODE", auto_monitor=True, kind=Kind.config)
    
    
    image = Component(EpicsSignalRO, "FPICTURE", kind=Kind.omitted)


    def configure(self, exposure_time=None):
        if exposure_time is not None:
            self.acqExpTime.set(exposure_time).wait()



    def stage(self):
        """ State transitions are only allowed when the IOC is not busy """
        if self.camCameraBusy.value or self.camInitBusy.value or self.camSetParamBusy.value:
            raise RuntimeErrror("Failed to stage, the camera appears busy.")
        self.camStatusCmd.set("Running").wait()

    def unstage(self):
        """ State transitions are only allowed when the IOC is not busy """
        self.camStatusCmd.set("Idle").wait()


# Automatically connect to test camera if directly invoked
if __name__ == "__main__":
    
    # Drive data collection
    cam = HelgeCameraBase("SINBC02-DSRM310:", name="mcpcam")
    cam.wait_for_connection()









