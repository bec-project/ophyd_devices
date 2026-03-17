"""Utilities for building computed read-only signals.

This module provides:

- :class:`ProcessedSignalModel`, which validates that ``method_inputs`` can be
    passed to ``compute_method`` as keyword arguments.
- :class:`BECProcessedSignal`, a ``SignalRO`` subclass that subscribes to input
    ophyd objects and recomputes its readback whenever an input updates.

Re-entrant callback execution is guarded to avoid recursive subscription loops.
"""

from __future__ import annotations

import inspect
import time
from typing import TYPE_CHECKING, Any, Callable, Literal, Self

from ophyd import Component, Device, Signal, SignalRO
from pydantic import BaseModel, model_validator

if TYPE_CHECKING:  # pragma: no cover
    from bec_server.device_server.devices.devicemanager import DeviceManagerDS, DSDevice


def find_device_config_in_session(name: str, device_manager: DeviceManagerDS) -> dict[str, Any]:
    """Return the configuration entry of ``name`` from ``device_manager.current_session``.

    The helper is used by lookups that resolve objects through the device
    manager and need to validate the ``needs`` dependency list.

    Args:
        name: The name of the signal/device for which the config is being fetched.
        device_manager: The device manager instance to fetch the current session config from.
    """
    configs = device_manager.current_session["devices"]
    config = None
    for conf in configs:
        if conf["name"] == name:
            config = conf
            break
    if config is None:
        raise ConnectionError(f"Device '{name}' not found in current session config.")
    return config


class ProcessedSignalModel(BaseModel):
    """Configuration model for :class:`BECProcessedSignal`.

    The model stores arbitrary keyword inputs and a callable. Validation enforces
    that ``compute_method(**method_inputs)`` is a compatible call.

    Args:
        method_inputs (dict[str, Any]): A dictionary mapping input names of the compute method to the
            corresponding objects. They can be ophyd Signals, Devices, Components or any other additional argument that should be passed
            to the compute method when called. The keys of this dictionary must match the signature of the compute method.
        compute_method (Callable[..., Any]): A user-defined function that computes the value of the processed signal based on the input devices/signals.

    Note:
        Validation only checks call compatibility (missing/extra kwargs and
        unsupported signature kinds). It does not enforce the runtime return
        type of ``compute_method``.
    """

    model_config = {"arbitrary_types_allowed": True}

    method_inputs: dict[str, Any]
    compute_method: Callable[..., Any]

    @model_validator(mode="after")
    def validate_signals_in_compute_method(self) -> Self:
        """Validate compatibility of ``compute_method`` with ``method_inputs``."""
        signature = inspect.signature(self.compute_method)
        parameters = signature.parameters
        input_names = set(self.method_inputs)

        accepted_names = set()
        required_names = set()
        has_var_keyword = False

        for name, param in parameters.items():
            if param.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.VAR_POSITIONAL):
                raise ValueError(
                    "Compute method mus be compatible with compute_method(**method_inputs): "
                    f"unsupported parameter {name!r} ({param.kind.description})."
                    f"for compute method {self.compute_method.__name__!r} with signature {signature}."
                )

            if param.kind is inspect.Parameter.VAR_KEYWORD:
                has_var_keyword = True
                continue

            accepted_names.add(name)

            if param.default is inspect.Parameter.empty:
                required_names.add(name)

        missing = required_names - input_names
        extra = set() if has_var_keyword else input_names - accepted_names

        if missing or extra:
            problems = []
            if missing:
                problems.append(f"missing required inputs: {sorted(missing)}")
            if extra:
                problems.append(f"unexpected inputs: {sorted(extra)}")
            raise ValueError("; ".join(problems))

        return self


class BECProcessedSignal(SignalRO):
    """Read-only signal whose value is computed from other inputs.

    A compute model can be provided at construction time via ``model_config`` or
    later through :meth:`set_compute_method`. During
    :meth:`wait_for_connection`, input ophyd objects are subscribed and the
    current value is computed immediately.

    Args:
        name (str): The name of the signal.
        model_config (dict[Literal["devices", "compute_method"], Any] | None):
            Optional initialization payload for :meth:`set_compute_method`.
            ``devices`` is passed as keyword arguments to the compute method.
        device_manager (DeviceManagerDS | None): Device manager used by helpers
            that resolve objects from BEC names.
        **kwargs: Additional keyword arguments passed to the SignalRO initializer.
    """

    def __init__(
        self,
        name: str,
        model_config: dict[Literal["method_inputs", "compute_method"], Any] | None = None,
        device_manager: DeviceManagerDS | None = None,
        **kwargs,
    ):
        super().__init__(name=name, **kwargs)
        self.compute_model: ProcessedSignalModel | None = None
        self._device_manager: DeviceManagerDS = self._get_device_manager(device_manager)
        self._metadata["connected"] = False
        self._callback_is_running = False
        self._active_callbacks: set[str] = set()
        if model_config:
            self.set_compute_method(
                compute_method=model_config["compute_method"], **model_config["devices"]
            )

    @staticmethod
    def get_device_object_from_bec(
        object_name: str, signal_name: str, device_manager: DeviceManagerDS
    ) -> Device | Signal:
        """Resolve one device/signal object from a BEC object name.

        The method verifies that the resolved device is listed in the ``needs``
        section of ``signal_name`` in the active session configuration.
        """
        signal_config = find_device_config_in_session(signal_name, device_manager)
        needs = signal_config.get("needs", [])
        dev_name = object_name.split(".")[0]  # First part of the dotted name is device
        if dev_name not in needs:
            raise ConnectionError(
                f"Device {dev_name} needs to be specified in the 'needs' field of the config for the current session"
                f"for signal '{signal_name}' in order to fetch the device object with name  {object_name} from the device manager."
            )
        # Attribute access resolves dotted name to fetch the correct signal/device object from the device manager
        # If this line crashes, there is likely an issue with the implementation of 'needs' in the device manager.
        device = device_manager.devices[object_name]
        return device

    def set_compute_method(self, compute_method: Callable[..., Any], **kwargs) -> None:
        """Set or replace the compute method and its keyword inputs.

        ``kwargs`` may contain ophyd objects and/or plain values. All entries are
        forwarded to the compute method as keyword arguments.

        Args:
            compute_method: Callable used to compute the readback value.
            **kwargs: Keyword arguments forwarded to ``compute_method``.
        """
        # Lazy import DSDevice to avoid circular import issues
        from bec_server.device_server.devices.devicemanager import DSDevice

        method_inputs = {}
        found_opd_objects = False
        for kw, value in kwargs.items():
            if isinstance(value, (Component, Device, Signal, DSDevice)):
                found_opd_objects = True
            method_inputs[kw] = value
        if not found_opd_objects:
            raise ValueError(
                "At least one ophyd object (Component, Device, Signal, or DSDevice) must be provided as a keyword argument to set_compute_method."
            )
        self.compute_model = ProcessedSignalModel.model_validate(
            {"method_inputs": method_inputs, "compute_method": compute_method}
        )

    def wait_for_connection(self, *args, **kwargs) -> None:
        """Connect to inputs and initialize computed readback.

        Subscriptions are attached to every method input that exposes both
        ``wait_for_connection`` and ``subscribe``. Inputs without these methods
        are treated as static keyword arguments.
        """
        # Already connected, no need to do anything
        if self._metadata.get("connected", False):
            return

        # Check that model is set, if not raise an error.
        if self.compute_model is None:
            raise ValueError(
                f"No compute model provided for signal {self.name}. Please either provide a model_config in init or use `set_compute_method` before `wait_for_connection` is called."
            )

        # Setup subscriptions to input devices/signals based on the model's configuration.
        for input in self.compute_model.method_inputs.values():
            # Lazy import DSDevice to avoid circular import issues
            from bec_server.device_server.devices.devicemanager import DSDevice

            if not isinstance(input, (Component, Device, Signal, DSDevice)):
                continue  # Skip non-ophyd objects, they are additional arguments for the compute method
            input.wait_for_connection(*args, **kwargs)  # Ensure connected

            input.subscribe(self._subscription_callback, event_type=input._default_sub, run=False)

        # Run computation of the processed signal, this stores the value in _readback
        self._subscription_callback()
        # Signal is connected
        self._metadata["connected"] = True

    def _subscription_callback(self, *args, **kwargs):
        """Recompute readback from ``compute_model`` and emit value subscriptions."""
        if self._callback_is_running:
            return  # Callback is already running, skip to avoid multiple executions at the same time
        try:
            self._callback_is_running = True
            old_value = self._readback
            timestamp = time.time()
            self._metadata["timestamp"] = timestamp
            self._readback = self.compute_model.compute_method(**self.compute_model.method_inputs)
            self._run_subs(sub_type=self._default_sub, old_value=old_value, value=self._readback)
        finally:
            self._callback_is_running = False

    def _run_subs(self, *args, sub_type, **kwargs):
        """Prevent concurrent callbacks for the same subscription type."""
        if sub_type in self._active_callbacks:
            return
        try:
            self._active_callbacks.add(sub_type)
            super()._run_subs(*args, sub_type=sub_type, **kwargs)
        finally:
            if sub_type in self._active_callbacks:
                self._active_callbacks.remove(sub_type)

    def _get_device_manager(self, device_manager: DeviceManagerDS | None = None) -> DeviceManagerDS:
        """Return the active device manager for this signal.

        If ``device_manager`` is not provided, the method tries to read it from
        ``self.root.device_manager``.

        Args:
            device_manager (DeviceManagerDS | None): An optional device manager instance. If not provided, it will attempt to fetch
                the device manager from the root device's `device_manager` attribute.
        Returns:
            DeviceManagerDS: The resolved device manager.
        """
        if device_manager is None:
            # PSIDeviceBase will have a reference to the device manager on device_manager attribute.
            device_manager = (
                self.root.device_manager if hasattr(self.root, "device_manager") else None
            )
        # If device_manager could not be fetched, raise an error.
        if device_manager is None:
            raise RuntimeError(
                f"No device manager instance available for signal {self.name}. "
                f"Parent device {self.root.name} of type {self.root.__class__} does not have a 'device_manager' attribute."
            )
        return device_manager

    def describe(self):
        """Return ``describe`` metadata including compute model information."""
        ret = super().describe()
        if self.compute_model is None:
            ret[self.name]["method_inputs"] = ""
            ret[self.name]["compute_method"] = ""
            ret[self.name]["extra_kwargs"] = {}
            return ret
        ret[self.name]["method_inputs"] = ", ".join(
            [
                f"{obj.root.name}.{obj.dotted_name}"
                for obj in self.compute_model.method_inputs.values()
                if hasattr(obj, "dotted_name") and hasattr(obj, "root")  # Ophyd obj
            ]
        )
        ret[self.name]["compute_method"] = self.compute_model.compute_method.__name__
        ret[self.name]["extra_kwargs"] = {
            kw: value
            for kw, value in self.compute_model.method_inputs.items()
            if not (hasattr(value, "dotted_name") and hasattr(value, "root"))  # Ophyd obj
        }
        return ret


if __name__ == "__main__":  # pragma: no cover

    # pylint: disable=import-outside-toplevel, unused-import, missing-docstring, protected-access

    from bec_server.device_server.tests.utils import DMMock

    from ophyd_devices.sim.sim_positioner import SimPositioner

    dm = DMMock()

    samx = SimPositioner(name="samx")
    samx.velocity.set(0.5)
    samy = SimPositioner(name="samy")
    samy.velocity.set(0.5)

    dm.devices._add_device("samx", samx)
    dm.devices._add_device("samy", samy)

    def compute_method(signal_1: Signal, signal_2: Signal, tmp: float = 2) -> float:
        return float(signal_1.get() + signal_2.get()) + tmp

    def _callback_print(value, **kwargs):
        obj = kwargs.get("obj")
        print(f"Processed signal updated for {obj.name}: {value}")

    samx.readback.subscribe(_callback_print, run=False, event_type=samx.readback.SUB_VALUE)
    samy.readback.subscribe(_callback_print, run=False, event_type=samy.readback.SUB_VALUE)

    processed_signal = BECProcessedSignal(
        name="processed_signal", model_config={}, device_manager=dm
    )
    processed_signal.set_compute_method(
        compute_method, signal_1=samx.readback, signal_2=samy.readback, tmp=0
    )
    processed_signal.subscribe(_callback_print, run=False, event_type=processed_signal.SUB_VALUE)
    dm.current_session = {}
    dm.current_session["devices"] = [{"name": processed_signal.name, "needs": ["samx", "samy"]}]

    processed_signal.wait_for_connection()

    processed_signal.describe()

    print(processed_signal.read())

    samx.move(1).wait()

    print(samx.read())

    print(processed_signal.read())

    samy.move(2).wait()

    print(processed_signal.read())

    print("All done!")
