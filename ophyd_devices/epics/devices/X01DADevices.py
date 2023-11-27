"""
Ophyd device classes for beamline X01DA "Debye"
"""

print(f"Loading {__file__}...")

import time
from datetime import datetime

from collections import OrderedDict

from ophyd import Kind, Device, DeviceStatus, EpicsSignal, EpicsSignalRO
from ophyd.flyers import FlyerInterface
from ophyd import Component as Cpt
from ophyd.status import SubscriptionStatus
import bluesky.plan_stubs as bps
import bluesky.preprocessors as bpp

from bluesky import RunEngine
from bluesky.callbacks.best_effort import BestEffortCallback


class NIDAQ_flyer(FlyerInterface, Device):
    """
    Ophyd flyer implementation for the Debye NIDAQ
    """
    acquire = Cpt(EpicsSignal, "Trigger", auto_monitor=True)
    nidaq_state = Cpt(EpicsSignalRO, "FSMState", auto_monitor=True)
    rate_act = Cpt(EpicsSignalRO, "SamplingRateActualized", auto_monitor=True)
    rate_req = Cpt(EpicsSignalRO, "SamplingRateRequested", auto_monitor=True)

    def __init__(self, *args, **kwargs):

        super().__init__(*args, **kwargs)

        self._start_time = 0
        self._verified = False


    def configure(self):
        """
        Scan configuration logic
        """
        self.acquire.put(0, use_complete=True)

        self._verified = True


    def kickoff(self):
        """
        Start the flyer
        """
        def callback(*, old_value, value, **kwargs):
            return (old_value == 1 and value == 0)

        self._status = SubscriptionStatus(self.acquire, callback)

        print(f"{time.asctime()}: scan started ...")

        self._start_time = time.time()
        self.acquire.put(1)
        self._status.wait()

        return self._status


    def complete(self):
        """
        Wait for the flyer to complete
        """
        def callback(value, old_value, **kwargs):
            return (old_value == 3 and value == 2)

        self._status = SubscriptionStatus(self.nidaq_state, callback)
        self._status.wait()

        return self._status


    def collect(self):
        """
        Retrieve data from the flyer
        """
#        data = {"time": self._start_time, "data": {}, "timestamps": {}}
#        for attr in ("rate_act", "rate_req"):
#            obj = getattr(self, attr)
#            data["data"][obj.name] = obj.get()
#            data["timestamps"][obj.name] = obj.timestamp
#
#        print(data)
#        return data

        return 0


    def describe_collect(self):
        """
        Schema and meta-data for collect()
        """
#        desc = OrderedDict()
#        for attr in ("rate_act", "rate_req"):
#            desc.update(getattr(self, attr).describe())

        ret = {'dtype': 'number',
               'shape': [],
               'source': 'SCANSERVER'}

        return {self.name: ret}


def daq_flyer_RE(flyer, *, md=None):
    _md = {}
    _md.update(md or {})
    @bpp.run_decorator(md=_md)
    def single_scan(flyer):
        bps.configure(flyer)
        yield from bps.kickoff(flyer, wait=True)
        yield from bps.complete(flyer, wait=True)
        bps.collect(flyer)

    return (yield from single_scan(flyer))


def daq_flyer_simple(flyer, *, md=None):
    _md = {}
    _md.update(md or {})
    def single_scan(flyer):
        flyer.configure()
        flyer.kickoff()
        flyer.complete()
        flyer.describe_collect()
        flyer.collect()

    return single_scan(flyer)


flyer = NIDAQ_flyer("X01DA-PC-SCANSERVER:NIDAQ-", name="test")

RE = RunEngine()
bec = BestEffortCallback()
