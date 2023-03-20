"""
ophyd device classes for X07MA beamline
"""
from collections import OrderedDict
import time
from typing import Any

from ophyd import Component as Cpt
from ophyd import FormattedComponent as FCpt

from ophyd import Device, EpicsSignal, EpicsSignalRO, Kind, PVPositioner, EpicsMotor
from ophyd.flyers import FlyerInterface
from ophyd.status import DeviceStatus, SubscriptionStatus
from ophyd.pv_positioner import PVPositionerComparator

__all__ = [
    "X07MAUndulator",
    "PGMMonochromator",
    "PGMOtFScan",
    "VacuumValve",
    "X07MAExitSlit",
    "X07MAMagnet",
    "X07MAAnalogSignals",
    "X07MASampleManipulator",
    "X07MATemperatureController",
    "X07MAAutoTemperatureControl",
]


class X07MAUndulator(PVPositioner):
    """
    X07MA undulator
    """

    setpoint = Cpt(EpicsSignal, "ENERGY", auto_monitor=True)
    readback = Cpt(EpicsSignalRO, "ENERGY-READ", kind=Kind.hinted, auto_monitor=True)
    done = Cpt(EpicsSignalRO, "DONE", kind=Kind.omitted, auto_monitor=True)
    stop_signal = Cpt(EpicsSignal, "STOP", kind=Kind.omitted)

    energy_offset = Cpt(EpicsSignal, "ENERGY-OFFS", kind=Kind.config)
    pol_mode = Cpt(EpicsSignal, "MODE")
    pol_angle = Cpt(EpicsSignal, "ALPHA")
    harmonic = Cpt(EpicsSignal, "HARMONIC")


class PGMMonochromator(PVPositioner):
    """
    PGM monochromator
    """

    setpoint = Cpt(EpicsSignal, "PHS-E:GO.A", auto_monitor=True)
    readback = Cpt(EpicsSignalRO, "PGM:CERBK", kind=Kind.hinted, auto_monitor=True)
    done = Cpt(EpicsSignalRO, "PHS:alldone", kind=Kind.omitted, auto_monitor=True)
    stop_signal = Cpt(EpicsSignal, "PGM:stop", kind=Kind.omitted)

    cff = Cpt(EpicsSignal, "PGM:rbkcff", write_pv="PGM:cff.A", kind=Kind.config)
    with_undulator = Cpt(EpicsSignal, "PHS-E:OPT", kind=Kind.config)


class PGMOtFScan(FlyerInterface, Device):
    """
    PGM on-the-fly scan
    """

    SUB_VALUE = "value"
    SUB_FLYER = "flyer"
    _default_sub = SUB_VALUE

    e1 = Cpt(EpicsSignal, "E1", kind=Kind.config)
    e2 = Cpt(EpicsSignal, "E2", kind=Kind.config)
    time = Cpt(EpicsSignal, "TIME", kind=Kind.config)
    folder = Cpt(EpicsSignal, "FOLDER", kind=Kind.config)
    file = Cpt(EpicsSignal, "FILE", kind=Kind.config)
    acquire = Cpt(EpicsSignal, "START", auto_monitor=True)
    edata = Cpt(EpicsSignalRO, "EDATA", kind=Kind.hinted, auto_monitor=True)
    data = Cpt(EpicsSignalRO, "DATA", kind=Kind.hinted, auto_monitor=True)
    idata = Cpt(EpicsSignalRO, "IDATA", kind=Kind.hinted, auto_monitor=True)
    fdata = Cpt(EpicsSignalRO, "FDATA", kind=Kind.hinted, auto_monitor=True)
    count = Cpt(EpicsSignalRO, "COUNT", kind=Kind.omitted, auto_monitor=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._start_time = 0
        self.acquire.subscribe(self._update_status, run=False)
        self.count.subscribe(self._update_data, run=False)

    def kickoff(self):
        self._start_time = time.time()
        self.acquire.put(1, use_complete=True)
        status = DeviceStatus(self)
        status.set_finished()
        return status

    def complete(self):
        def check_value(*, old_value, value, **kwargs):
            return old_value == 1 and value == 0

        status = SubscriptionStatus(self.acquire, check_value, event_type=self.acquire.SUB_VALUE)
        return status

    def collect(self):
        data = {"time": self._start_time, "data": {}, "timestamps": {}}
        for attr in ("edata", "data", "idata", "fdata"):
            obj = getattr(self, attr)
            data["data"][obj.name] = obj.get()
            data["timestamps"][obj.name] = obj.timestamp

        return data

    def describe_collect(self):
        desc = OrderedDict()
        for attr in ("edata", "data", "idata", "fdata"):
            desc.update(getattr(self, attr).describe())
        return desc

    def _update_status(self, *, old_value, value, **kwargs):
        if old_value == 1 and value == 0:
            self._update_data(100)  # make sure that the last entries are also emitted
            self._done_acquiring()

    def _update_data(self, value, **kwargs):
        if value == 0:
            return
        data = self.collect()

        # FIXME: to avoid emitting outdated / stale data, wait until all signals report > 10 entries
        if any(len(val) < 10 for val in data["data"].values()) or value < 10:
            return
        self._run_subs(sub_type=self.SUB_FLYER, value=data)


class VacuumValve(PVPositionerComparator):
    """
    EPS vacuum valve.

    The setpoint is of 2 choices
       0 - Close
       1 - Try open

    The readback is of 8 choices
       0 - TO CONNECT
           1 - MAN OPEN
           2 - CLOSED
           3 - ERROR
           4 - MOVING
           5 - OPEN
           6 - ERROR
           7 - ERROR
    """

    setpoint = Cpt(EpicsSignal, "WT_SET")
    readback = Cpt(EpicsSignalRO, "POSITION")

    def __init__(self, prefix: str, *, name: str, **kwargs):
        kwargs.update({"limits": (0, 1)})
        super().__init__(prefix, name=name, **kwargs)

    def done_comparator(self, readback: Any, setpoint: Any) -> bool:
        return readback != 4


class X07MAExitSlit(PVPositioner):
    """
    Exit slit
    """

    setpoint = Cpt(EpicsSignal, "TR_AP")
    readback = Cpt(EpicsSignalRO, "TR_ISAP", kind=Kind.hinted, auto_monitor=True)
    done = Cpt(EpicsSignalRO, "TR.DMOV", kind=Kind.omitted, auto_monitor=True)


class X07MAMagnet(Device):
    """
    Magnet fields.
    """

    class MagnetAxis(PVPositioner):
        """
        A single magnet field axis.
        """

        done_value = 2
        actuate_value = 1
        setpoint = FCpt(EpicsSignal, "{prefix}{_axis_id}:DMD")
        readback = FCpt(
            EpicsSignalRO, "{prefix}{_axis_id}:RBV", kind=Kind.hinted, auto_monitor=True
        )
        actuate = Cpt(EpicsSignal, "STARTRAMP.PROC", kind=Kind.omitted)
        done = FCpt(
            EpicsSignalRO, "{_ps_prefix}STS:RAMP:MADE", kind=Kind.omitted, auto_monitor=True
        )
        ramprate = FCpt(
            EpicsSignal, "{_ps_prefix}STS:RAMPRATE:TPM", write_pv="{_ps_prefix}SET:DMD:RAMPRATE:TPM"
        )

        def __init__(self, prefix="", axis_id="", ps_prefix="", *, name=None, **kwargs):
            self._axis_id = axis_id
            self._ps_prefix = ps_prefix
            super().__init__(prefix, name=name, **kwargs)

    x = Cpt(MagnetAxis, "", axis_id="X", ps_prefix="X07MA-PC-PS2:", name="x")
    z = Cpt(MagnetAxis, "", axis_id="Z", ps_prefix="X07MA-PC-PS1:", name="z")


class X07MAAnalogSignals(Device):
    """
    ADC inputs
    """

    s1 = Cpt(EpicsSignalRO, "SIGNAL0", kind=Kind.hinted, auto_monitor=True)
    s2 = Cpt(EpicsSignalRO, "SIGNAL1", kind=Kind.hinted, auto_monitor=True)
    s3 = Cpt(EpicsSignalRO, "SIGNAL2", kind=Kind.hinted, auto_monitor=True)
    s4 = Cpt(EpicsSignalRO, "SIGNAL3", kind=Kind.hinted, auto_monitor=True)
    s5 = Cpt(EpicsSignalRO, "SIGNAL4", kind=Kind.hinted, auto_monitor=True)
    s6 = Cpt(EpicsSignalRO, "SIGNAL5", kind=Kind.hinted, auto_monitor=True)
    s7 = Cpt(EpicsSignalRO, "SIGNAL6", kind=Kind.hinted, auto_monitor=True)

    # Aliases
    tey = s1
    i0 = s2
    trans = s3
    field_z = s4
    field_x = s5


class X07MASampleManipulator(Device):
    """
    Sample manipulator
    """

    hor = Cpt(EpicsMotor, "TRZS")
    vert = Cpt(EpicsMotor, "TRY1")
    rot = Cpt(EpicsMotor, "ROY1")


class X07MATemperatureController(Device):
    """
    Temperature controller
    """

    needle_valve = Cpt(EpicsSignal, "STS:LOOP2:MANUAL", write_pv="DMD:LOOP2:MANUAL")
    setpoint = Cpt(EpicsSignal, "STS:LOOP1:SETPOINT", write_pv="DMD:LOOP1:SETPOINT")
    readback = Cpt(EpicsSignalRO, "STS:T1", kind=Kind.hinted, auto_monitor=True)


class X07MAAutoTemperatureControl(Device):
    """
    Automatic temperature control.
    """

    control = Cpt(EpicsSignal, "CONTROL")
    status = Cpt(EpicsSignalRO, "STATUS", string=True, auto_monitor=True)
