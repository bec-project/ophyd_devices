from enum import IntEnum

from ophyd import Component as Cpt
from ophyd import EpicsSignal, EpicsSignalRO, Kind
from ophyd.status import SubscriptionStatus

from ophyd_devices.interfaces.base_classes.psi_device_base import PSIDeviceBase


class ShutterOpenState(IntEnum):
    OPEN = 1
    CLOSED = 0


class ShutterEnabled(IntEnum):
    ENABLED = 1
    DISABLED = 0


def _is_state(state: int | str):
    def _cb(*, old_value, value, **kwargs):
        return value == state

    return _cb


class Shutter(PSIDeviceBase):
    """A generic optics shutter device, for IOCs with the format '[BEAMLINE]-EH1-PSYS:SH-[A/B]-'

    Example config:
        shutter:
          description: Optics Shutter A
          deviceClass: ophyd_devices.optics_shutter.Shutter
          deviceConfig: {prefix: 'X10SA-EH1-PSYS:SH-A-'}
          enabled: true
          onFailure: retry
          readOnly: false
          readoutPriority: baseline
          softwareTrigger: false
          userParameter: {}

    Example usage:
        shutter = Shutter(name="shutter", prefix="X10SA-EH1-PSYS:SH-A-")
        if shutter.enabled == ShutterEnabled.ENABLED:
            st = shutter.open()
            st.wait()

    """

    is_open = Cpt(EpicsSignalRO, "OPEN", kind=Kind.hinted)
    is_closed = Cpt(EpicsSignalRO, "CLOSE", kind=Kind.omitted)
    is_enabled = Cpt(EpicsSignalRO, "ENABLE")
    is_ok = Cpt(EpicsSignalRO, "OK")
    alarm = Cpt(EpicsSignalRO, "ALARM")
    set_open = Cpt(EpicsSignal, "OPEN-SET", kind=Kind.omitted)
    set_closed = Cpt(EpicsSignal, "CLOSE-SET", kind=Kind.omitted)

    def _check_enabled(self):
        if self.enabled() != ShutterEnabled.ENABLED:
            raise RuntimeError("The shutter is disabled!")

    def open(self):
        """Open the shutter.

        Returns: ophyd.status.SubscriptionStatus which resolved when the shutter is opened.
        """
        self._check_enabled()
        self.set_open.put(1)
        return SubscriptionStatus(self.is_open, _is_state(ShutterOpenState.OPEN))

    def close(self):
        """Close the shutter.

        Returns: ophyd.status.SubscriptionStatus which resolved when the shutter is closed.
        """
        self._check_enabled()
        self.set_closed.put(1)
        return SubscriptionStatus(self.is_open, _is_state(ShutterOpenState.CLOSED))

    def status(self) -> ShutterOpenState:
        return ShutterOpenState(self.is_open.get())

    def enabled(self) -> ShutterEnabled:
        return ShutterEnabled(self.is_enabled.get())


if __name__ == "__main__":
    prefix = "X10SA-EH1-PSYS:SH-A-"
    print(f"Testing shutter device with prefix {prefix}")
    shutter = Shutter(name="shutter", prefix=prefix)
    shutter.wait_for_connection()
    print(shutter.read())
