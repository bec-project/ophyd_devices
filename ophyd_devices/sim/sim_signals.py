import time
import numpy as np

from bec_lib import bec_logger
from ophyd import Signal, Kind
from ophyd.utils import ReadOnlyError

logger = bec_logger.logger

# Readout precision for Setable/ReadOnlySignal signals
PRECISION = 3


class SetableSignal(Signal):
    """Setable signal for simulated devices.

    The signal will store the value in sim_state of the SimulatedData class of the parent device.
    It will also return the value from sim_state when get is called. Compared to the ReadOnlySignal,
    this signal can be written to.

    >>> signal = SetableSignal(name="signal", parent=parent, value=0)

    Parameters
    ----------

    name  (string)           : Name of the signal
    parent (object)          : Parent object of the signal, default none.
    value (any)              : Initial value of the signal, default 0.
    kind (int)               : Kind of the signal, default Kind.normal.
    precision (float)        : Precision of the signal, default PRECISION.
    """

    def __init__(
        self,
        name: str,
        *args,
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
        self._value = value
        self.precision = precision
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

    # pylint: disable=arguments-differ
    def get(self):
        """Get the current position of the simulated device.

        Core function for signal.
        """
        self._value = self._get_value()
        return self._value

    # pylint: disable=arguments-differ
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
    """Computed readback signal for simulated devices.

    The readback will be computed from a function hosted in the SimulatedData class from the parent device
    if compute_readback is True. Else, it will return the value stored int sim.sim_state directly.

    >>> signal = ComputedReadOnlySignal(name="signal", parent=parent, value=0, compute_readback=True)

    Parameters
    ----------

    name  (string)           : Name of the signal
    parent (object)          : Parent object of the signal, default none.
    value (any)              : Initial value of the signal, default 0.
    kind (int)               : Kind of the signal, default Kind.normal.
    precision (float)        : Precision of the signal, default PRECISION.
    compute_readback (bool)  : Flag whether to compute readback based on function hosted in SimulatedData
                               class. If False, sim_state value will be returned, if True, new value will be computed
    """

    def __init__(
        self,
        name: str,
        *args,
        parent=None,
        value: any = 0,
        kind: int = Kind.normal,
        precision: float = PRECISION,
        compute_readback: bool = False,
        **kwargs,
    ):
        super().__init__(*args, name=name, parent=parent, value=value, kind=kind, **kwargs)
        self._metadata.update(
            connected=True,
            write_access=False,
        )
        self._value = value
        self.precision = precision
        self.compute_readback = compute_readback
        self.sim = getattr(self.parent, "sim", None)
        if self.sim:
            self._init_sim_state()

    def _init_sim_state(self) -> None:
        """Create the initial sim_state in the SimulatedData class of the parent device."""
        self.sim.update_sim_state(self.name, self._value)

    def _update_sim_state(self) -> None:
        """Update the readback value."""
        self.sim.compute_sim_state(signal_name=self.name, compute_readback=self.compute_readback)

    def _get_value(self) -> any:
        """Update the timestamp of the readback value."""
        return self.sim.sim_state[self.name]["value"]

    def _get_timestamp(self) -> any:
        """Update the timestamp of the readback value."""
        return self.sim.sim_state[self.name]["timestamp"]

    # pylint: disable=arguments-differ
    def get(self):
        """Get the current position of the simulated device."""
        if self.sim:
            self._update_sim_state()
            self._value = self._get_value()
            return self._value
        return np.random.rand()

    # pylint: disable=arguments-differ
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
        if self.sim:
            return self._get_timestamp()
        return time.time()
