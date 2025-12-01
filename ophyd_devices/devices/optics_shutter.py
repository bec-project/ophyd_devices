"""
Module for the optics shutter device at PSI beamlines.

Example config:
shutter:
    description: Optics Shutter A
    deviceClass: ophyd_devices.optics_shutter.OpticsShutter
    deviceConfig: {prefix: 'X10SA-EH1-PSYS:SH-A-'}
    enabled: true
    onFailure: retry
    readOnly: false
    readoutPriority: baseline
    softwareTrigger: false
    userParameter: {}
"""

from enum import IntEnum

from ophyd import Component as Cpt
from ophyd import Device, EpicsSignal, EpicsSignalRO, Kind, Signal

from ophyd_devices import CompareStatus


class ShutterOpenState(IntEnum):
    """Enum for shutter open state."""

    OPEN = 1
    CLOSED = 0


class ShutterEnabled(IntEnum):
    """Enum for shutter enabled state."""

    ENABLED = 1
    DISABLED = 0


class ShutterControl(Device):
    """Control interface for the PVs related to the shutter."""

    is_open = Cpt(EpicsSignalRO, "OPEN", kind=Kind.config, auto_monitor=True)
    is_closed = Cpt(EpicsSignalRO, "CLOSE", kind=Kind.omitted)
    is_enabled = Cpt(EpicsSignalRO, "ENABLE", kind=Kind.config, auto_monitor=True)
    is_ok = Cpt(EpicsSignalRO, "OK", kind=Kind.omitted, auto_monitor=True)
    alarm = Cpt(EpicsSignalRO, "ALARM", kind=Kind.omitted, auto_monitor=True)
    set_open = Cpt(EpicsSignal, "OPEN-SET", kind=Kind.omitted)
    set_closed = Cpt(EpicsSignal, "CLOSE-SET", kind=Kind.omitted)


class ShutterOpenSignal(Signal):
    """
    ShutterOpenSignal. When called with 1, it will try to open the shutter.
    If called with 0, it will try to close the shutter.
    """

    def enabled(self) -> ShutterEnabled:
        """Check if the shutter is enabled."""
        return ShutterEnabled(self.parent.epics_control.is_enabled.get())

    def _check_enabled(self):
        if self.enabled() != ShutterEnabled.ENABLED:
            dev_name = self.parent.name if self.parent else "unknown"
            raise RuntimeError(f"The shutter {dev_name} is disabled!")

    def get(self) -> int:
        return self.parent.epics_control.is_open.get()

    def put(self, value: int, **kwargs) -> None:
        self._check_enabled()
        if value == ShutterOpenState.OPEN:
            self.parent.epics_control.set_open.put(1, **kwargs)
        elif value == ShutterOpenState.CLOSED:
            self.parent.epics_control.set_closed.put(1, **kwargs)
        else:
            raise ValueError("Invalid value for ShutterOpenSignal. Use 0 (CLOSED) or 1 (OPEN).")

    def set(self, value: int, **kwargs) -> CompareStatus:
        self.put(value, **kwargs)
        return CompareStatus(self.parent.epics_control.is_open, value)


class OpticsShutter(Device):
    """A shutter device with shutter open signal, and sub-device with full control PVs of the Epics implementation."""

    set_open = Cpt(
        ShutterOpenSignal,
        name="open",
        kind=Kind.omitted,
        doc="Signal to open/close the shutter. Use 0 (CLOSED) or 1 (OPEN).",
    )
    is_open = Cpt(
        EpicsSignalRO,
        "OPEN",
        kind=Kind.normal,
        auto_monitor=True,
        doc="Readback of the shutter open state. 0 (CLOSED) or 1 (OPEN).",
    )
    epics_control = Cpt(ShutterControl, suffix="", name="epics_control", kind=Kind.omitted)


if __name__ == "__main__":
    prefix = "X10SA-EH1-PSYS:SH-A-"
    print(f"Testing shutter device with prefix {prefix}")
    shutter = OpticsShutter(name="shutter", prefix=prefix)
    shutter.wait_for_connection()
    print(shutter.read())
