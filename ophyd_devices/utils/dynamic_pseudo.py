"""
This module provides a class for creating a pseudo signal that is computed from other signals.
"""

import ast
import re
from functools import reduce
from typing import Callable

import numpy as np
import scipy as sp
from bec_lib import bec_logger
from ophyd import Signal, SignalRO
from ophyd.ophydobj import Kind

logger = bec_logger.logger

_FIRST_DEF = re.compile(r"(^|\\n)\s*def", re.MULTILINE)


def _smart_strip(method: str) -> str:
    if (first_def := _FIRST_DEF.search(method)) is not None:
        return method[first_def.span()[1] - 3 :]
    else:
        raise ValueError(f"No 'def' keyword found in function definition: {method}")


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
        attr_name="",
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
        self._input_signals: list[Signal] = []
        self._signal_subs = []
        self._compute_method = None
        self._compute_method_str = None
        self._active_callbacks: set[str] = set()

    def _signal_callback(self, *args, **kwargs):
        old_value = self._readback
        val = self.get()
        if val is not None:
            self._run_subs(sub_type=self.SUB_VALUE, old_value=old_value, value=val)

    @property
    def compute_method(self) -> Callable | None:
        """
        Property that returns the compute method for the pseudo signal.
        Example:
            >>> signal.compute_method = "def test(a, b): return a.get() + b.get()"

        """
        return self._compute_method_str

    @compute_method.setter
    def compute_method(self, method: str):
        """
        Set the compute method for the pseudo signal. We  import numpy (as np) and scipy as packages
        that are also available for user to use in their compute method.

        Args:
            compute_method (str): The compute method to be used. This should be a string
                representation of a function that takes the input signals as arguments
                and returns the computed value.

        Example:
            >>> signal.compute_method = "def test(a, b): return a.get() + b.get()"

        """
        logger.info(f"Updating compute method for {self.name}.")
        method = _smart_strip(method)
        # Parse and validate the function using AST
        try:
            tree = ast.parse(method)
            if not tree.body or not isinstance(tree.body[0], ast.FunctionDef):
                raise ValueError("The compute method should be a valid function definition")

            # Rename the function in the AST
            func_def = tree.body[0]
            func_def.name = "user_compute_method"

            # Convert AST back to code and compile
            code = compile(tree, "<string>", "exec")
        except SyntaxError as exc:
            raise ValueError(f"Invalid function syntax: {exc}") from exc

        self._compute_method_str = method
        # pylint: disable=exec-used
        namespace = {"np": np, "sp": sp}
        exec(code, namespace)
        self._compute_method = namespace["user_compute_method"]

    @property
    def input_signals(self):
        """
        Set the input signals for the pseudo signal

        Args:
            *input_vars: The input signals to be used for the computation

        Example:
            >>> signal.input_signals = ["samx.readback", "samx.readback"]

        """
        return self._input_signals

    @input_signals.setter
    def input_signals(self, input_vars):
        if self._signal_subs:
            for signal, sub_id in self._signal_subs:
                signal.unsubscribe(sub_id)
            self._signal_subs.clear()
        signals = []
        for signal in input_vars:
            if isinstance(signal, str):
                obj = rgetattr(self._device_manager.devices, signal)
                sub_id = obj.subscribe(self._signal_callback, run=False)
                self._signal_subs.append((obj, sub_id))
                signals.append(obj)
            else:
                signals.append(signal)
        self._input_signals = signals

    def get(self, **kwargs):
        return_value = None
        if self._compute_method:
            # pylint: disable=not-callable
            if self.input_signals:
                return_value = self._compute_method(*self.input_signals)
            else:
                return_value = self._compute_method()
        self._readback = return_value if return_value is not None else self._readback
        return return_value

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
