# -*- coding: utf-8 -*-
"""
Created on Wed Oct 13 17:06:51 2021

@author: mohacsi_i
"""

import os
import yaml
from ophyd.ophydobj import OphydObject

from devices import *

# ####################################################
# Test connection to beamline devices
# ####################################################
# Current file path
path = os.path.dirname(os.path.abspath(__file__))

# Load simulated device database
fp = open(f"{path}/db/test_database.yml", "r")
lut_db = yaml.load(fp, Loader=yaml.Loader)

# Load beamline specific database
bl = os.getenv("BEAMLINE_XNAME", "TESTENV")
if bl != "TESTENV":
    fp = open(f"{path}/db/{bl.lower()}_database.yml", "r")
    lut_db.update(yaml.load(fp, Loader=yaml.Loader))


def createProxy(name: str, connect=True) -> OphydObject:
    """Create an ophyd device from its alias

    Factory routine that uses the beamline database to instantiate
    ophyd devices from their alias and pre-defined configuration.
    Does nothing if the device is already an OphydObject!
    """
    if issubclass(type(name), OphydObject):
        return name

    entry = lut_db[name]
    # Yeah, using global namespace
    cls_candidate = globals()[entry["type"]]
    # print(f"Class candidate: {cls_candidate}")

    if issubclass(cls_candidate, OphydObject):
        ret = cls_candidate(**entry["config"])
        if connect:
            ret.wait_for_connection(timeout=5)
        return ret
    else:
        raise RuntimeError(f"Unsupported return class: {entry['type']}")


if __name__ == "__main__":
    num_errors = 0
    for key in lut_db:
        try:
            dut = createProxy(str(key))
            print(f"{key}\t: {type(dut)}\t{dut.read()}")
            # print(f"{key}\t: {type(dut)}")
        except Exception as ex:
            num_errors += 1
            print(key)
            print(ex)
    print(f"\nTotal number of errors: {num_errors}")
