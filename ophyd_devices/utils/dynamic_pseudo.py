"""
This module provides a class for creating a pseudo signal that is computed from other signals.
"""

from functools import reduce
from typing import Callable

from ophyd import SignalRO
from ophyd.ophydobj import Kind


def rgetattr(obj, attr, *args):
    """See https://stackoverflow.com/questions/31174295/getattr-and-setattr-on-nested-objects"""

    def _getattr(obj, attr):
        return getattr(obj, attr, *args)

    return reduce(_getattr, [obj] + attr.split("."))


class ComputedSignal(SignalRO):
    """
    A read-only signal that is computed from other signals. The compute method should be a string
    representation of a function that takes the input signals as arguments and returns the computed
    value. The input signals should be provided as a list of strings that represent the path to the
    signal in the device manager.
    """

    def __init__(
        self,
        *,
        name,
        value=0,
        timestamp=None,
        device_manager=None,
        parent=None,
        labels=None,
        kind=Kind.hinted,
        tolerance=None,
        rtolerance=None,
        metadata=None,
        cl=None,
        attr_name=""
    ):
        super().__init__(
            name=name,
            value=value,
            timestamp=timestamp,
            parent=parent,
            labels=labels,
            kind=kind,
            tolerance=tolerance,
            rtolerance=rtolerance,
            metadata=metadata,
            cl=cl,
            attr_name=attr_name,
        )
        self._device_manager = device_manager
        self._input_signals = []
        self._signal_subs = []
        self._compute_method = None

    def _signal_callback(self, *args, **kwargs):
        self._run_subs(sub_type=self.SUB_VALUE, old_value=None, value=self.get())

    @property
    def compute_method(self) -> Callable | None:
        """
        Set the compute method for the pseudo signal

        Args:
            compute_method (str): The compute method to be used. This should be a string
                representation of a function that takes the input signals as arguments
                and returns the computed value.

        Example:
            >>> signal.compute_method = "def test(a, b): return a.get() + b.get()"

        """
        return self._compute_method

    @compute_method.setter
    def compute_method(self, method: str):
        if not method.startswith("def"):
            raise ValueError("The compute method should be a string representation of a function")

        # get the function name
        function_name = method.split("(")[0].split(" ")[1]
        # pylint: disable=exec-used
        exec(method)
        self._compute_method = locals()[function_name]

    @property
    def input_signals(self):
        """
        Set the input signals for the pseudo signal

        Args:
            *input_vars: The input signals to be used for the computation

        Example:
            >>> signal.input_signals = ["samx_readback", "samx_readback"]

        """
        return self._input_signals

    @input_signals.setter
    def input_signals(self, input_vars):
        if self._signal_subs:
            for signal, sub_id in self._signal_subs:
                signal.unsubscribe(sub_id)
        signals = []
        for signal in input_vars:
            if isinstance(signal, str):
                target = signal.replace("_", ".")
                parts = target.split(".")
                target = ".".join([parts[0], "obj"] + parts[1:])
                obj = rgetattr(self._device_manager.devices, target)
                sub_id = obj.subscribe(self._signal_callback)
                self._signal_subs.append((obj, sub_id))
                signals.append(obj)
            else:
                signals.append(signal)
        self._input_signals = signals

    def get(self):
        if self.compute_method:
            # pylint: disable=not-callable
            return self.compute_method(*self.input_signals)
        return None
