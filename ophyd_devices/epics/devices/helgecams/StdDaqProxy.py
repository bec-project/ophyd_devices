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

import requests

STDAQ_REST_ADDR = "http://127.0.0.1:5001"




data = {"sources":"eiger", "n_images":10, "output_file":"/tmp/test.h5"}
headers = {'Content-type': 'application/json'}
r = requests.post(url = "http://127.0.0.1:5000/write_sync", json=data, headers=headers)





class StdDaqBase(Device):
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


    def configure(self, d: dict = {}):
        self._n_images = d['n_images'] if 'n_images' in d else None
        self._sources = d['sources'] if 'sources' in d else None
        self._output_file = d['output_file'] if 'output_file' in d else None

    
    
    def kickoff(self):
        data = {"sources": self._sources, "n_images": self._n_images, "output_file": self._output_file}
        headers = {'Content-type': 'application/json'}
        r = requests.post(url = "http://127.0.0.1:5000/write_async", json=data, headers=headers)
        self.req_id = req_id = str(r.json()["request_id"])