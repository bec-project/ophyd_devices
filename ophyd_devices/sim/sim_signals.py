import time as ttime

from bec_lib import bec_logger
from ophyd import Signal
from ophyd.utils import ReadOnlyError

logger = bec_logger.logger


class ReadbackSignal(Signal):
    """Readback signal for simulated devices.

    It will return the value of the readback signal based on the position
    created in the sim_state dictionary of the parent device.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._metadata.update(
            connected=True,
            write_access=False,
        )

    def get(self, **kwargs):
        """Get the current position of the simulated device."""
        self._readback = self.parent.sim_state["readback"]
        self.parent.sim_state["readback_ts"] = ttime.time()
        return self._readback

    def describe(self):
        """Describe the readback signal."""
        res = super().describe()
        res[self.name]["precision"] = self.parent.precision
        return res

    @property
    def timestamp(self):
        """Timestamp of the readback value"""
        return self.parent.sim_state["readback_ts"]

    def put(self, value, *, timestamp=None, force=False, **kwargs):
        """Put method, should raise ReadOnlyError since the signal is readonly."""
        raise ReadOnlyError(f"The signal {self.name} is readonly.")

    def set(self, value, *, timestamp=None, force=False, **kwargs):
        """Set method, should raise ReadOnlyError since the signal is readonly."""
        raise ReadOnlyError(f"The signal {self.name} is readonly.")


class SetpointSignal(Signal):
    """Setpoint signal for simulated devices.

    When read, it will return the "setpoint" key from the dictionary sim_state,
    and whe put it will call the set method of the parent device with the value.
    """

    def put(self, value, *, timestamp=None, force=False, **kwargs):
        """Put the value to the simulated device."""
        self._readback = float(value)
        self.parent.set(float(value))

    def get(self, **kwargs):
        """Get the current setpoint of the simulated device."""
        self._readback = self.parent.sim_state["setpoint"]
        return self.parent.sim_state["setpoint"]

    @property
    def timestamp(self):
        """Timestamp of the readback value"""
        return self.parent.sim_state["setpoint_ts"]


class IsMovingSignal(Signal):
    """IsMoving signal for simulated devices.

    When read, it will return the "is_moving" key from the dictionary sim_state,
    and whe put it will call the set method of the parent device with the value.
    """

    def get(self, **kwargs):
        self._readback = self.parent.sim_state["is_moving"]
        self.parent.sim_state["is_moving_ts"] = ttime.time()
        return self.parent.sim_state["is_moving"]

    @property
    def timestamp(self):
        """Timestamp of the readback value"""
        return self.parent.sim_state["is_moving_ts"]

    def put(self, value, *, timestamp=None, force=False, **kwargs):
        """Put method, should raise ReadOnlyError since the signal is readonly."""
        raise ReadOnlyError(f"The signal {self.name} is readonly.")

    def set(self, value, *, timestamp=None, force=False, **kwargs):
        """Set method, should raise ReadOnlyError since the signal is readonly."""
        raise ReadOnlyError(f"The signal {self.name} is readonly.")
