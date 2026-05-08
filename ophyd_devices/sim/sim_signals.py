"""Module for signals of the ophyd_devices simulation."""

import time
from typing import Any

import numpy as np
from bec_lib import bec_logger
from ophyd import DeviceStatus, Kind, Signal
from ophyd.utils import ReadOnlyError

logger = bec_logger.logger

# Readout precision for Setable/ReadOnlySignal signals
PRECISION = 3


class SetableSignal(Signal):
    """Setable signal for simulated devices.

    The signal will store the value in sim_state of the SimulatedData class of the parent device.
    It will also return the value from sim_state when get is called. Compared to the ReadOnlySignal,
    this signal can be written to.
    The settable signal inherits from the Signal class of ophyd, thus the class attribute needs to be
    initiated as a Component (class from ophyd).

    >>> signal = SetableSignal(name="signal", parent=parent, value=0)

    Parameters
    ----------

    name  (string)           : Name of the signal
    parent (object)          : Parent object of the signal, default none.
    value (any)              : Initial value of the signal, default 0.
    kind (int)               : Kind of the signal, default Kind.normal.
    precision (float)        : Precision of the signal, default PRECISION.
    """

    SUB_VALUE = "value"

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
        self._metadata.update(connected=True, write_access=False)
        self._value = value
        self.precision = precision
        self.sim = getattr(self.parent, "sim", None)
        self._update_sim_state(value)
        self._metadata.update(write_access=True)
        self._active_callbacks: set[str] = set()

    def _update_sim_state(self, value: Any) -> None:
        """Update the readback value."""
        if self.sim:
            self.sim.update_sim_state(self.name, value)

    def _get_value(self) -> Any:
        """Update the timestamp of the readback value."""
        if self.sim:
            return self.sim.sim_state[self.name]["value"]
        return self._value

    def _get_timestamp(self) -> float:
        """Update the timestamp of the readback value."""
        if self.sim:
            return self.sim.sim_state[self.name]["timestamp"]
        return time.time()

    # pylint: disable=arguments-differ
    def get(self, **kwargs) -> Any:
        """Get the current position of the simulated device.

        Core function for signal.
        """
        old_value = self._readback
        self._readback = self._value = self._get_value()
        if old_value != self._readback:  # only run subs if the value has changed
            self._run_subs(sub_type=self.SUB_VALUE, old_value=old_value, value=self._readback)
        return self._readback

    # pylint: disable=arguments-differ
    def put(self, value) -> None:
        """Put the value to the simulated device.

        Core function for signal.
        """
        old_value = self._value
        self.check_value(value)
        self._update_sim_state(value)
        self._value = value
        self._run_subs(sub_type=self.SUB_VALUE, old_value=old_value, value=self._value)
        super().put(value)

    def set(self, value):
        """Set method"""
        self.put(value)
        status = DeviceStatus(self)
        status.set_finished()
        return status

    def describe(self):
        """Describe the readback signal.

        Core function for signal.
        """
        res = super().describe()
        if self.precision is not None:
            res[self.name]["precision"] = self.precision
        return res

    @property
    def timestamp(self) -> float:
        """Timestamp of the readback value"""
        return self._get_timestamp()

    def _run_subs(self, *args, sub_type, **kwargs):
        """
        This method runs the callbacks for a given subscription type. It is overridden to ensure that
        callbacks for the same subscription type can not trigger additional subscriptions of the same type.
        We thereby avoid that callbacks can triggered recursively. In practice, a callback may call 'get'
        or 'read' itself, but it won't trigger any recursive calls of the callbacks for the same subscription type.

        Args:
            sub_type (str): The subscription type for which to run the callbacks.
        """
        if sub_type in self._active_callbacks:
            return
        try:
            self._active_callbacks.add(sub_type)
            super()._run_subs(*args, sub_type=sub_type, **kwargs)
        finally:
            if sub_type in self._active_callbacks:
                self._active_callbacks.remove(sub_type)


class ReadOnlySignal(Signal):
    """Computed readback signal for simulated devices.

    The readback will be computed from a function hosted in the SimulatedData class from the parent device
    if compute_readback is True. Else, it will return the value stored int sim.sim_state directly.
    The readonly signal inherits from the Signal class of ophyd, thus the class attribute needs to be
    initiated as a Component (class from ophyd).

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
        sim=None,
        **kwargs,
    ):
        super().__init__(*args, name=name, parent=parent, value=value, kind=kind, **kwargs)
        self._metadata.update(connected=True, write_access=False)
        self._value = value  # In a signal, this is self._readback
        self.precision = precision
        self.compute_readback = compute_readback
        self.sim = sim if sim is not None else getattr(self.parent, "sim", None)
        if self.sim:
            self._init_sim_state()
        self._metadata.update(write_access=False)
        self._active_callbacks: set[str] = set()

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
        old_value = self._readback
        if self.sim:
            self._update_sim_state()
            self._readback = self._value = self._get_value()
        else:
            self._readback = np.random.rand()
        try:
            if (
                isinstance(old_value, (int, float, list)) and old_value != self._readback
            ):  # only run subs if the value has changed
                self._run_subs(sub_type=self.SUB_VALUE, old_value=old_value, value=self._readback)
            else:  # must be numpy
                if not np.array_equal(old_value, self._readback):
                    self._run_subs(
                        sub_type=self.SUB_VALUE, old_value=old_value, value=self._readback
                    )
        except Exception as e:
            logger.info(
                f"Error in comparing old_value {old_value} with new_value {self._readback}: {e}"
            )
        return self._readback

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

    def _run_subs(self, *args, sub_type, **kwargs):
        """
        This method runs the callbacks for a given subscription type. It is overridden to ensure that
        callbacks for the same subscription type can not trigger additional subscriptions of the same type.
        We thereby avoid that callbacks can triggered recursively. In practice, a callback may call 'get'
        or 'read' itself, but it won't trigger any recursive calls of the callbacks for the same subscription type.

        Args:
            sub_type (str): The subscription type for which to run the callbacks.
        """
        if sub_type in self._active_callbacks:
            return
        try:
            self._active_callbacks.add(sub_type)
            super()._run_subs(*args, sub_type=sub_type, **kwargs)
        finally:
            if sub_type in self._active_callbacks:
                self._active_callbacks.remove(sub_type)
