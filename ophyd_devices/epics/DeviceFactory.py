# -*- coding: utf-8 -*-
"""
Created on Wed Oct 13 17:06:51 2021

@author: mohacsi_i
"""

import os
import yaml
from ophyd.ophydobj import OphydObject
from ophyd import EpicsSignal, EpicsSignalRO, EpicsMotor
from ophyd.sim import SynAxis, SynSignal, SynPeriodicSignal
from ophyd.quadem import QuadEM
import pathlib


path = os.path.dirname(os.path.abspath(__file__))


from proxies import *


# Load SLS common database
fp = open(f"{path}/db/test_database.yml", "r")
lut_db = yaml.load(fp, Loader=yaml.Loader)

# Load SLS common database (already in DB)
# fp = open(f"{path}/db/machine_database.yml", "r")
# lut_db = yaml.load(fp, Loader=yaml.Loader)

# Load beamline specific database
bl = os.getenv("BEAMLINE_XNAME", "X12SA")
fp = open(f"{path}/db/{bl.lower()}_database.yml", "r")
lut_db.update(yaml.load(fp, Loader=yaml.Loader))


def createProxy(name: str, connect=True) -> OphydObject:
    """Factory routine to create an ophyd device with a pre-defined schema.
    Does nothing if the device is already an OphydObject!
    """
    if issubclass(type(name), OphydObject):
        return name

    entry = lut_db[name]
    cls_candidate = globals()[entry["type"]]
    print(f"Device candidate: {cls_candidate}")

    if issubclass(cls_candidate, OphydObject):
        ret = cls_candidate(**entry["config"])
        if connect:
            ret.wait_for_connection(timeout=5)
        return ret
    else:
        raise RuntimeError(f"Unsupported return class: {entry['type']}")


if __name__ == "__main__":
    for key in lut_db:
        print("")
        dut = createProxy(str(key))
        print(f"{key}\t:\t{dut.read()}")
 
