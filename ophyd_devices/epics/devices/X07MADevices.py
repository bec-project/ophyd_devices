"""
ophyd device classes for X07MA beamline
"""

import time
import traceback
from collections import OrderedDict
from typing import Any

from bec_lib import bec_logger
from ophyd import Component as Cpt
from ophyd import Device, EpicsMotor, EpicsSignal, EpicsSignalRO
from ophyd import FormattedComponent as FCpt
from ophyd import Kind, PVPositioner, Signal
from ophyd.flyers import FlyerInterface
from ophyd.pv_positioner import PVPositionerComparator
from ophyd.status import DeviceStatus, SubscriptionStatus

logger = bec_logger.logger


__all__ = [
    "X07MAUndulator",
    "PGMMonochromator",
    "PGMOtFScan",
    "VacuumValve",
    "X07MAExitSlit",
    "X07MAMagnetAxis",
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

    def __init__(
        self,
        prefix="",
        *,
        limits=None,
        name=None,
        read_attrs=None,
        configuration_attrs=None,
        parent=None,
        egu="",
        **kwargs
    ):
        super().__init__(
            prefix,
            limits=limits,
            name=name,
            read_attrs=read_attrs,
            configuration_attrs=configuration_attrs,
            parent=parent,
            egu=egu,
            **kwargs
        )
        self.readback.name = self.name


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

    def __init__(
        self,
        prefix="",
        *,
        limits=None,
        name=None,
        read_attrs=None,
        configuration_attrs=None,
        parent=None,
        egu="",
        **kwargs
    ):
        super().__init__(
            prefix,
            limits=limits,
            name=name,
            read_attrs=read_attrs,
            configuration_attrs=configuration_attrs,
            parent=parent,
            egu=egu,
            **kwargs
        )
        self.readback.name = self.name


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
        try:
            if value == 0:
                return
            data = self.collect()

            # FIXME: to avoid emitting outdated / stale data, wait until all signals report > 10 entries
            if any(len(val) < 10 for val in data["data"].values()) or value < 10:
                return
            self._run_subs(sub_type=self.SUB_FLYER, value=data)
        except Exception as exc:
            content = traceback.format_exc()
            logger.error(content)


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
        self.readback.name = self.name

    def done_comparator(self, readback: Any, setpoint: Any) -> bool:
        return readback != 4


class X07MAExitSlit(PVPositioner):
    """
    Exit slit
    """

    setpoint = Cpt(EpicsSignal, "TR_AP")
    readback = Cpt(EpicsSignalRO, "TR_ISAP", kind=Kind.hinted, auto_monitor=True)
    done = Cpt(EpicsSignalRO, "TR.DMOV", kind=Kind.omitted, auto_monitor=True)

    def __init__(
        self,
        prefix="",
        *,
        limits=None,
        name=None,
        read_attrs=None,
        configuration_attrs=None,
        parent=None,
        egu="",
        **kwargs
    ):
        super().__init__(
            prefix,
            limits=limits,
            name=name,
            read_attrs=read_attrs,
            configuration_attrs=configuration_attrs,
            parent=parent,
            egu=egu,
            **kwargs
        )
        self.readback.name = self.name


# class X07MAMagnet(Device):
#     """
#     Magnet fields.
#     """


class X07MAMagnetAxis(PVPositioner):
    """
    A single magnet field axis.
    """

    done_value = 1
    actuate_value = 1
    setpoint = FCpt(EpicsSignal, "{prefix}{_axis_id}:DMD")
    readback = FCpt(EpicsSignalRO, "{prefix}{_axis_id}:RBV", kind=Kind.hinted, auto_monitor=True)
    actuate = Cpt(EpicsSignal, "STARTRAMP.PROC", kind=Kind.omitted)
    done = FCpt(EpicsSignalRO, "{prefix}{_axis_id}:RAMP:DONE", auto_monitor=True)
    ramprate = FCpt(
        EpicsSignal, "{_ps_prefix}STS:RAMPRATE:TPM", write_pv="{_ps_prefix}SET:DMD:RAMPRATE:TPM"
    )

    def __init__(self, prefix="", axis_id="", ps_prefix="", *, name=None, **kwargs):
        self._axis_id = axis_id
        self._ps_prefix = ps_prefix
        super().__init__(prefix, name=name, **kwargs)
        self.readback.name = self.name

    def _setup_move(self, position):
        # If the setpoint is close to the current readback, the controller will not do anything,
        # and the done value will not change. So we simply say is done.
        if abs(position - self.readback.get()) < max(0.004, position * 0.0025):
            self._done_moving(success=True, time=time.ctime(), value=position)
        else:
            super()._setup_move(position)

    # x = Cpt(MagnetAxis, "", axis_id="X", ps_prefix="X07MA-PC-PS2:", name="x")
    # z = Cpt(MagnetAxis, "", axis_id="Z", ps_prefix="X07MA-PC-PS1:", name="z")


class NormSignal(Signal):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._metadata.update(
            write_access=False,
        )

    def wait_for_connection(self, timeout=0):
        super().wait_for_connection(timeout)
        self._metadata.update(connected=True)

    def get(self, **kwargs):
        val1 = self.parent.signal1.get()
        val2 = self.parent.signal2.get()
        return val1 / val2 if val2 != 0 else 0

    def describe(self):
        desc = {
            "shape": [],
            "dtype": "number",
            "source": "PV: {} / {}".format(self.parent.signal1.pvname, self.parent.signal2.pvname),
            "units": "",
            "precision": self.parent.signal1.precision,
        }
        return desc


class NormTEYSignals(Device):
    signal1 = Cpt(EpicsSignalRO, name="signal1", read_pv="X07MA-ES1-AI:SIGNAL1", kind="omitted")
    signal2 = Cpt(EpicsSignalRO, name="signal2", read_pv="X07MA-ES1-AI:SIGNAL2", kind="omitted")
    norm = Cpt(NormSignal, name="norm", kind="hinted")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.norm.name = self.name


class NormDIODESignals(Device):
    signal1 = Cpt(EpicsSignalRO, name="signal1", read_pv="X07MA-ES1-AI:SIGNAL3", kind="omitted")
    signal2 = Cpt(EpicsSignalRO, name="signal2", read_pv="X07MA-ES1-AI:SIGNAL2", kind="omitted")
    norm = Cpt(NormSignal, name="norm", kind="hinted")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.norm.name = self.name


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
    norm_tey = Cpt(NormTEYSignals, name="norm_tey", kind=Kind.hinted)
    norm_diode = Cpt(NormDIODESignals, name="norm_tey", kind=Kind.hinted)

    # Aliases
    # tey = s1
    # i0 = s2
    # trans = s3
    # field_z = s4
    # field_x = s5


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

    def __init__(
        self,
        prefix="",
        *,
        name,
        kind=None,
        read_attrs=None,
        configuration_attrs=None,
        parent=None,
        **kwargs
    ):
        super().__init__(
            prefix,
            name=name,
            kind=kind,
            read_attrs=read_attrs,
            configuration_attrs=configuration_attrs,
            parent=parent,
            **kwargs
        )
        self.readback.name = self.name


class X07MAAutoTemperatureControl(Device):
    """
    Automatic temperature control.
    """

    control = Cpt(EpicsSignal, "CONTROL")
    status = Cpt(EpicsSignalRO, "STATUS", string=True, auto_monitor=True)
