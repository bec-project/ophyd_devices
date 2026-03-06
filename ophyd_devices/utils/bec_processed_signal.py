from __future__ import annotations

import inspect
from typing import TYPE_CHECKING, Any, Callable, Self, TypeAlias

import numpy as np
from ophyd import Device, Signal, SignalRO
from pydantic import BaseModel, model_validator

if TYPE_CHECKING:  # pragma: no cover
    from bec_server.device_server.devices.devicemanager import DeviceManagerDS

ALLOWED_RETURN_TYPES = (float, int, str, np.ndarray)
ALLOWED_TYPE_ALIAS: TypeAlias = type[float] | type[int] | type[str] | type[np.ndarray]

ComputeMethod: TypeAlias = Callable[..., ALLOWED_TYPE_ALIAS]


class ProcessedSignalModel(BaseModel):
    """
    Model for the BECProcessedSignal, which defines the devices/signals to subscribe to, and a
    compute method that will be called with the device/signal objects as arguments. The method
    `get_device_objects_from_device_manager` can be used to get the device/signal objects from the device manager
    based on the devices dictionary.

    Args:
        signals (dict[str, DeviceSignalMapping]): A dictionary mapping signal names to their corresponding device
                    and attribute names. The keys of this dictionary must match the parameters of the compute_method.
        compute_method (Callable): A callable that will be called with the device/signal objects as arguments.
                    The signature of this method must match the keys of the signals dictionary. The return value of
                    this method will be used as the value of the BECProcessedSignal. The compute method can also be a
                    coroutine function, in which case it will be awaited.
        return_type (type): The expected return type of the compute method. This is used for validation and to ensure
                    that the value of the BECProcessedSignal is of the correct type. Must be one of the types specified
                    in ALLOWED_RETURN_TYPES.
    """

    model_config = {"arbitrary_types_allowed": True}

    devices: dict[str, str]
    compute_method: ComputeMethod
    return_type: ALLOWED_TYPE_ALIAS

    @model_validator(mode="after")
    def validate_signals_in_compute_method(self) -> Self:
        """Validator to check that the compute method signature contains all keys of the devices field."""
        # Check that the compute method's signature contains all the keys in the devices dictionary.
        input_names = set(self.devices.keys())

        signature = inspect.signature(self.compute_method)

        parameters = signature.parameters

        method_param_names = set(parameters.keys())

        if method_param_names != input_names:
            raise ValueError(
                "The compute_method signature does not match with the devices keys provided. "
                f"Expected parameters: {sorted(input_names)}, "
                f"got: {sorted(method_param_names)}"
            )
        return self

    def get_device_objects_from_device_manager(
        self, device_manager: DeviceManagerDS, signal_name: str
    ) -> dict[str, Device | Signal]:
        """
        Helper method to get the device/signal objects from the device manager based on the devices dictionary.

        Args:
            device_manager (DeviceManagerDS): The device manager to get the devices/signals from.
            signal_name (str): The name of the ProcessedSignal
        Returns:
            dict[str, Device | Signal]: A dictionary mapping the device/signal names to their corresponding
                                        ophyd Device or Signal objects.
        """
        device_objs = {}
        signal_config = self._find_device_config_in_session(signal_name, device_manager)
        needs = signal_config.get("needs", [])
        for name, dotted_name in self.devices.items():
            dev_name = dotted_name.split(".")[0]  # First part of the dotted name is device
            if dev_name not in needs:
                raise ConnectionError(
                    f"Device {dev_name} needs to be specified in the 'needs' field of the config for the current session"
                    f"for signal '{signal_name}' in order to fetch the device object with name  {dotted_name}from the device manager."
                )
            # Attribute access resolves dotted name to fetch the correct signal/device object from the device manager
            device = device_manager.devices[dotted_name]
            # TODO: How to safeguard against using variables and not signals?
            # if not isinstance(device, (Device, Signal)):
            #     raise ConnectionError(
            #         f"Device '{dotted_name}' does not point to a valid signal or device but to type {type(device)}."
            #     )
            device_objs[name] = device

        return device_objs

    def _find_device_config_in_session(
        self, name: str, device_manager: DeviceManagerDS
    ) -> dict[str, Any]:
        """
        Helper method to find the device config for a given device name in the current session config of the device manager.
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


class BECProcessedSignal(SignalRO):

    def __init__(
        self,
        name: str,
        model: ProcessedSignalModel | dict[str, Any] | None = None,
        device_manager: DeviceManagerDS | None = None,
        **kwargs,
    ):
        super().__init__(name=name, **kwargs)
        self._model = model or {}
        self._device_manager: DeviceManagerDS = self._get_device_manager(device_manager)
        self.device_objects: dict[str, Device | Signal] = {}
        self._metadata["connected"] = False
        self._callback_is_running = False
        self._active_callbacks: set[str] = set()

    def set_model(self, model: ProcessedSignalModel | dict[str, Any]) -> None:
        """
        Method to set the model for the BECProcessedSignal. This method will be used to set the devices/signals to subscribe to,
        and the compute method to use for processing the values from those devices/signals.

        Args:
            model (ProcessedSignalModel | dict): The model for the BECProcessedSignal. Can be either a ProcessedSignalModel instance or a dictionary that can be used to create a ProcessedSignalModel instance.
        """
        if isinstance(model, dict):
            model = ProcessedSignalModel(**model)
        self._model = model

    def set_device_object(self, device_objects: dict[str, Device | Signal]) -> None:
        """
        Method to set the device/signal objects for the BECProcessedSignal. This method will be used to provide the actual ophyd Device or Signal objects that correspond to the devices/signals specified in the model.

        Args:
            device_objects (dict[str, Device | Signal]): A dictionary mapping the device/signal names to their corresponding ophyd Device or Signal objects.
        """
        self.device_objects = device_objects

    def wait_for_connection(self, *args, **kwargs) -> None:
        """
        Wait for connection will try to connect to the device/signal objects specified in the
        model. It will check the model for validity, and attempt to fetch the device_objects if
        they are not already set. Once everything is set up, it subscribe to the default subscriptions
        and compute an initial value while asserting that its return value is of the correct type.
        """

        # I. Check that model is set, if not raise an error.
        if self._model is None:
            raise ValueError(
                f"No model provided for signal {self.name}. Please either provided model in init or use `set_model` before `wait_for_connection` is called."
            )

        # II. Check that device objects are set, if not raise an error.
        if not self.device_objects:
            # The method will also check that the device object names are specified in this signals config needs field.
            device_objects = self._model.get_device_objects_from_device_manager(
                self._device_manager, self.name
            )
            self.set_device_object(device_objects)

        # III. Check that device_objects dict contains all keys specified in the model's devices field.
        model_keys = set(self._model.devices.keys())
        device_object_keys = set(self.device_objects.keys())
        if model_keys != device_object_keys:
            raise ValueError(
                f"The device_objects provided do not match with the devices specified in the model for signal {self.name}. "
                f"Expected keys: {sorted(model_keys)}, got: {sorted(device_object_keys)}"
            )

        # Now we connect to the default subscriptions of the provided signal/device objects.
        for device_obj in self.device_objects.values():
            device_obj.wait_for_connection(*args, **kwargs)  # Ensure connected

            device_obj.subscribe(
                self._subscription_callback, event_type=device_obj._default_sub, run=False
            )

        # Run computation of the processed signal, this stores the value in _readback
        self._subscription_callback(**self.device_objects)
        if not isinstance(self._readback, self._model.return_type):
            raise TypeError(
                f"Computed value has type {type(self._readback)}, but expected {self._model.return_type}"
            )
        # Signal is connected
        self._metadata["connected"] = True

    def _subscription_callback(self, *args, **kwargs):
        """Callback method that is executed whenever any of the subscribed signal/device objects have an update."""
        if self._callback_is_running:
            return  # Callback is already running, skip to avoid multiple executions at the same time
        try:
            self._callback_is_running = True
            old_value = self._readback
            self._readback = self._model.compute_method(**self.device_objects)
            self._run_subs(sub_type=self._default_sub, old_value=old_value, value=self._readback)
        finally:
            self._callback_is_running = False

    def _run_subs(self, *args, sub_type, **kwargs):
        """
        Run subs should not allow for recursive calls of the same subscription type to avoid recursion loops.

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

    def _get_device_manager(self, device_manager: DeviceManagerDS | None = None) -> DeviceManagerDS:
        """
        Helper method to get the device manager instance.

        Args:
            device_manager (DeviceManagerDS | None): Optional device manager instance. If not provided, it will attempt to fetch from the root device.

        Returns:
            DeviceManagerDS: The device manager instance.
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
        ret = super().describe()
        ret[self.name]["device_objects"] = ", ".join(self._model.devices.values())
        return ret


if __name__ == "__main__":  # pragma: no cover

    from bec_server.device_server.tests.utils import DMMock

    from ophyd_devices.sim.sim_positioner import SimPositioner

    dm = DMMock()

    samx = SimPositioner(name="samx")
    samx.velocity.set(0.5)
    samy = SimPositioner(name="samy")
    samy.velocity.set(0.5)

    dm.devices._add_device("samx", samx)
    dm.devices._add_device("samy", samy)

    def compute_method(signal_1: Signal, signal_2: Signal) -> float:
        """Example compute method that adds two signals."""
        return float(signal_1.get() + signal_2.get())

    def _callback_print(value, **kwargs):
        obj = kwargs.get("obj")
        print(f"Processed signal updated for {obj.name}: {value}")

    samx.readback.subscribe(_callback_print, run=False, event_type=samx.readback.SUB_VALUE)
    samy.readback.subscribe(_callback_print, run=False, event_type=samy.readback.SUB_VALUE)

    _model = ProcessedSignalModel(
        devices={"signal_1": "samx.readback", "signal_2": "samy.readback"},
        compute_method=compute_method,
        return_type=float,
    )

    processed_signal = BECProcessedSignal(name="processed_signal", model=_model, device_manager=dm)
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
