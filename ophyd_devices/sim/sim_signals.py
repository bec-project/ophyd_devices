import time as ttime

from bec_lib import bec_logger
import numpy as np
from ophyd import Signal, Kind
from ophyd.utils import ReadOnlyError

logger = bec_logger.logger

# Readout precision for Setable/Readonly/ComputedReadonly signals
PRECISION = 3


class SetableSignal(Signal):
    """Setable signal for simulated devices.

    It will return the value of the readback signal based on the position
    created in the sim_state dictionary of the parent device.
    """

    def __init__(
        self,
        *args,
        name: str,
        value: any = None,
        kind: int = Kind.normal,
        precision: float = PRECISION,
        **kwargs,
    ):
        super().__init__(*args, name=name, value=value, kind=kind, **kwargs)
        self._metadata.update(
            connected=True,
            write_access=False,
        )
        self._value = value
        self.precision = precision
        # Init the sim_state, if self.parent.sim available, use it, else use self.parent
        self.sim = getattr(self.parent, "sim", self.parent)
        self._update_sim_state(value)

    def _update_sim_state(self, value: any) -> None:
        """Update the readback value."""
        self.sim.update_sim_state(self.name, value)

    def _get_value(self) -> any:
        """Update the timestamp of the readback value."""
        return self.sim.sim_state[self.name]["value"]

    def _get_timestamp(self) -> any:
        """Update the timestamp of the readback value."""
        return self.sim.sim_state[self.name]["timestamp"]

    def get(self):
        """Get the current position of the simulated device.

        Core function for signal.
        """
        self._value = self._get_value()
        return self._value

    def put(self, value):
        """Put the value to the simulated device.

        Core function for signal.
        """
        self._update_sim_state(value)
        self._value = value

    def describe(self):
        """Describe the readback signal.

        Core function for signal.
        """
        res = super().describe()
        if self.precision is not None:
            res[self.name]["precision"] = self.precision
        return res

    @property
    def timestamp(self):
        """Timestamp of the readback value"""
        return self._get_timestamp()


class ReadOnlySignal(Signal):
    """Readonly signal for simulated devices.

    If initiated without a value, it will set the initial value to 0.
    """

    def __init__(
        self,
        *args,
        name: str,
        value: any = 0,
        kind: int = Kind.normal,
        precision: float = PRECISION,
        **kwargs,
    ):
        super().__init__(*args, name=name, value=value, kind=kind, **kwargs)
        self._metadata.update(
            connected=True,
            write_access=False,
        )
        self.precision = precision
        self._value = value
        # Init the sim_state, if self.parent.sim available, use it, else use self.parent
        self.sim = getattr(self.parent, "sim", None)
        self._init_sim_state()

    def _init_sim_state(self) -> None:
        """Init the readback value and timestamp in sim_state"""
        if self.sim:
            self.sim.update_sim_state(self.name, self._value)

    def _get_value(self) -> any:
        """Get the value of the readback from sim_state."""
        if self.sim:
            return self.sim.sim_state[self.name]["value"]
        else:
            return np.random.rand()

    def _get_timestamp(self) -> any:
        """Get the timestamp of the readback from sim_state."""
        if self.sim:
            return self.sim.sim_state[self.name]["timestamp"]
        else:
            return ttime.time()

    def get(self) -> any:
        """Get the current position of the simulated device.

        Core function for signal.
        """
        self._value = self._get_value()
        return self._value

    def put(self, value) -> None:
        """Put method, should raise ReadOnlyError since the signal is readonly."""
        raise ReadOnlyError(f"The signal {self.name} is readonly.")

    def describe(self):
        """Describe the readback signal.

        Core function for signal.
        """
        res = super().describe()
        if self.precision is not None:
            res[self.name]["precision"] = self.precision
        return res

    @property
    def timestamp(self):
        """Timestamp of the readback value"""
        return self._get_timestamp()


class ComputedReadOnlySignal(Signal):
    """Computed readback signal for simulated devices.

    It will return the value computed from the sim_state of the signal.
    This can be configured in parent.sim.
    """

    def __init__(
        self,
        *args,
        name: str,
        value: any = None,
        kind: int = Kind.normal,
        precision: float = PRECISION,
        **kwargs,
    ):
        super().__init__(*args, name=name, value=value, kind=kind, **kwargs)
        self._metadata.update(
            connected=True,
            write_access=False,
        )
        self._value = value
        self.precision = precision
        # Init the sim_state, if self.parent.sim available, use it, else use self.parent
        self.sim = getattr(self.parent, "sim", self.parent)
        self._update_sim_state()

    def _update_sim_state(self) -> None:
        """Update the readback value.

        Call _compute_sim_state in parent device which updates the sim_state.
        """
        self.sim._compute_sim_state(self.name)

    def _get_value(self) -> any:
        """Update the timestamp of the readback value."""
        return self.sim.sim_state[self.name]["value"]

    def _get_timestamp(self) -> any:
        """Update the timestamp of the readback value."""
        return self.sim.sim_state[self.name]["timestamp"]

    def get(self):
        """Get the current position of the simulated device.

        Core function for signal.
        """
        self._update_sim_state()
        self._value = self._get_value()
        return self._value

    def put(self, value) -> None:
        """Put method, should raise ReadOnlyError since the signal is readonly."""
        raise ReadOnlyError(f"The signal {self.name} is readonly.")

    def describe(self):
        """Describe the readback signal.

        Core function for signal.
        """
        res = super().describe()
        if self.precision is not None:
            res[self.name]["precision"] = self.precision
        return res

    @property
    def timestamp(self):
        """Timestamp of the readback value"""
        return self._get_timestamp()


if __name__ == "__main__":
    from ophyd_devices.sim import SimPositioner

    positioner = SimPositioner(name="positioner", parent=None)
    print(positioner.velocity.get())
    positioner.velocity.put(10)
    print(positioner.velocity.get())
    positioner.velocity.put(1)
    print(positioner.velocity.get())
