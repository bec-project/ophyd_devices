import enum
import threading
import time
import numpy as np
import os

from typing import Any

from ophyd import EpicsSignal, EpicsSignalRO, EpicsSignalWithRBV
from ophyd import Device
from ophyd import ADComponent as ADCpt

from std_daq_client import StdDaqClient

from bec_lib import threadlocked
from bec_lib.logger import bec_logger
from bec_lib import messages
from bec_lib.endpoints import MessageEndpoints

from ophyd_devices.epics.devices.psi_detector_base import PSIDetectorBase, CustomDetectorMixin

logger = bec_logger.logger




class StdDaqBase(Device):
    """ 
        Standalone standard_daq base class from the Eiger 9M.
    """
    std_numpoints = None
    std_filename = None

    def __init__(self, prefix="", *, name, stddaq_filepath, kind=None, stddaq_rest_url="http://xbl-daq-29:5000", stddaq_timeout=5, read_attrs=None, configuration_attrs=None, parent=None, **kwargs):
    
        self.std_rest_url = stddaq_rest_url
        self.std_timeout = stddaq_timeout
        self.std_filepath = stddaq_filepath
    
        # Std client
        self.std_client = StdDaqClient(url_base=self.std_rest_url)

        # Stop writer
        self.std_client.stop_writer()
        
        # Change e-account
        #eacc = self.parent.scaninfo.username
        #self.update_std_cfg("writer_user_id", int(eacc.strip(" e")))

        signal_conditions = [(lambda: self.std_client.get_status()["state"], "READY")]
        if not self.wait_for_signals(
            signal_conditions=signal_conditions,
            timeout=self.std_timeout,
            all_signals=True,
        ):
            raise TimeoutError(f"Std client not in READY state, returns: {self.std_client.get_status()}")
        
    def update_std_cfg(self, cfg_key: str, value: Any) -> None:
        """
        Update std_daq config

        Checks that the new value matches the type of the former entry.

        Args:
            cfg_key (str)   : config key of value to be updated
            value (Any)     : value to be updated for the specified key
        """

        # Load config from client and check old value
        cfg = self.std_client.get_config()
        old_value = cfg.get(cfg_key)
        if old_value is None:
            raise KeyError( f"Tried to change entry for key {cfg_key} in std_config that does not exist")
        if not isinstance(value, type(old_value)):
            raise TypeError(f"Type of new value {type(value)}:{value} does not match old value {type(old_value)}:{old_value}")

        # Update config with new value and send back to client
        cfg.update({cfg_key: value})
        self.std_client.set_config(cfg)
        
    def configure(self, d: dict):
        """Configure the standard_daq"""

        filename = str(d['filename']).split(".")[0]

        self.std_numpoints = int(d['numpoints'])
        self.std_filename = f"{self.std_filepath}/{filename}.h5"
     
       
    def stage(self) -> None:
        """Start acquiring"""
        
        self.stop()
        try:
            self.std_client.start_writer_async(
                {"output_file": self.std_filename, "n_images": int(self.std_numpoints)}
            )
        except Exception as ex:
            time.sleep(5)
            if self.std_client.get_status()["state"] == "READY":
                raise TimeoutError(f"Timeout of start_writer_async with {ex}") from ex

        # Check status of std_daq
        signal_conditions = [(lambda: self.std_client.get_status()["acquisition"]["state"], "WAITING_IMAGES")]
        if not self.wait_for_signals(
            signal_conditions=signal_conditions,
            timeout=self.std_timeout,
            check_stopped=False,
            all_signals=True,
        ):
            raise TimeoutError(f"Timeout of 5s reached for std_daq start_writer_async with std_daq client status {self.std_client.get_status()}")
          

    def unstage(self) -> None:
        """Close file writer"""
        self.std_client.stop_writer()
        
    def stop(self) -> None:
        """Close file writer"""
        self.std_client.stop_writer()        
        
        
        
        

if __name__ == "__main__":
    daq = StdDaqBase(name="daq", stddaq_filepath="~/Data10")
