""" """

from __future__ import annotations

import inspect
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Callable

from ophyd import Component as Cpt
from ophyd import Kind, PositionerBase

from ophyd_devices.interfaces.base_classes.psi_device_base import PSIDeviceBase
from ophyd_devices.utils.bec_processed_signal import BECProcessedSignal, ProcessedSignalModel
from ophyd_devices.utils.psi_device_base_utils import AndStatus, StatusBase

if TYPE_CHECKING:  # pragma: no cover
    from bec_server.device_server.devices.devicemanager import DeviceManagerDS


class PSIPseudoMotorBase(ABC, PSIDeviceBase, PositionerBase):
    """
    Base class for PSI pseudo motors.

    Args:
        name (str): The name of the pseudo motor.
        device_manager (DeviceManagerDS): The device manager to use for connecting to the positioners.
        positioners (dict[str, str]): A dictionary mapping positioner names to device names in the device manager.
                                      Keys of this dictionary must match the arguments of the forward_calculation,
                                      inverse_calculation and motors_are_moving methods. The values must be the names
                                      of the devices in the device manager that correspond to the positioners.
    """

    readback = Cpt(BECProcessedSignal, name="readback", model={}, kind=Kind.hinted)
    setpoint = Cpt(BECProcessedSignal, name="setpoint", model={}, kind=Kind.normal)
    motor_is_moving = Cpt(BECProcessedSignal, name="motor_is_moving", model={}, kind=Kind.omitted)

    def __init__(
        self,
        name: str,
        device_manager: DeviceManagerDS,
        positioners: dict[str, PositionerBase] | None = None,
        egu: str = "",
        **kwargs,
    ):
        self.positioner_objects = positioners or {}
        self._positioner_move_kwargs: dict[str, dict[str, Any]] = {}
        self._egu = egu
        super().__init__(name=name, device_manager=device_manager, **kwargs)

    @property
    def egu(self) -> str:
        """Engineering units for the pseudo motor. This can be set during initialization or by setting the egu attribute."""
        return self._egu

    def set_positioner_objects(self, positioners: dict[str, PositionerBase]) -> None:
        """
        Method to set the positioner objects after initialization. This can be used if the positioner objects are not available at the time of initialization.

        Args:
            positioners (dict[str, PositionerBase]): A dictionary mapping positioner names to positioner objects.
        """
        self.positioner_objects = positioners

    def wait_for_connection(self, *args, **kwargs) -> None:
        """Connect to relevant positioners, setup processed signals."""
        if not self.positioner_objects:
            raise ConnectionError(
                f"No positioners specified for pseudo motor {self.name}. Please use 'set_positioner_objects' or pass positioner objects during initialization."
            )
        # Check if all methods have the required signature that matches the positioner_objects keys
        self._check_method_signatures()
        self._setup_pseudo_signal(
            "readback", ["readback", "user_readback"], self.forward_calculation, return_type=float
        )
        self._setup_pseudo_signal(
            "setpoint", ["setpoint", "user_setpoint"], self.forward_calculation, return_type=float
        )
        self._setup_pseudo_signal(
            "motor_is_moving", ["motor_is_moving"], self.motors_are_moving, return_type=int
        )
        return super().wait_for_connection(*args, **kwargs)

    def _check_method_signatures(self) -> None:
        """
        Method to check that the forward_calculation, inverse_calculation and motors_are_moving methods
        have the required signature that matches the positioner_objects keys.
        """
        input_names = set(self.positioner_objects.keys())
        for method in [self.forward_calculation, self.inverse_calculation, self.motors_are_moving]:
            signature = inspect.signature(method)
            method_param_names = set(signature.parameters.keys())
            for param in input_names:
                if param not in method_param_names:
                    raise TypeError(
                        f"Method '{method.__name__}' has parameter '{param}' that does not match any of the positioner names specified in positioner_objects: {method_param_names}."
                    )

    def _setup_pseudo_signal(
        self,
        pseudo_attr: str,
        allowed_attributes: list[str],
        compute_method: Callable[..., float],
        return_type: type,
    ):
        """
        Setup a pseudo signal with the given compute method and return type. The compute method will be called with
        the values of the positioners as arguments. The allowed_attributes are used to determine which signal of the
        positioner to use as input for the compute method. The first attribute that is found in the positioner will be used.

        Args:
            pseudo_attr (str): The attribute of the pseudo motor to set the model for.
            allowed_attributes (list[str]): The attributes of the positioner to look for as input for the compute method.
            compute_method (Callable[..., float]): The method to compute the value of the pseudo signal.
            return_type (type): The return type of the compute method.
        """
        device_objects = {}
        dotted_names = {}
        pseudo_attr_obj: BECProcessedSignal = getattr(self, pseudo_attr)
        for name, positioner in self.positioner_objects.items():
            obj = None
            device_name = positioner.name
            for attr in allowed_attributes:
                if hasattr(positioner, attr):
                    obj = getattr(positioner, attr)
                    break
            if obj is None:
                raise AttributeError(
                    f"Positioner '{name}' does not have any of the allowed attributes: {allowed_attributes}."
                )
            dotted_names[name] = f"{device_name}.{obj.name}"
            device_objects[name] = obj

        model = ProcessedSignalModel(
            devices=dotted_names, compute_method=compute_method, return_type=return_type
        )
        pseudo_attr_obj.set_device_object(device_objects)
        pseudo_attr_obj.set_model(model)
        pseudo_attr_obj.wait_for_connection()

    def get_positioner_objects(
        self, name: str, positioners: dict[str, str], device_manager: DeviceManagerDS
    ) -> dict[str, PositionerBase]:
        """
        Helper method to get the positioner objects from the device manager based on a positioner dictionary.

        Args:
            name (str): The name of the pseudo motor device to look for in the device manager config.
            positioners (dict[str, str]): A dictionary mapping positioner names to device names in the device manager.
            device_manager (DeviceManagerDS): The device manager to use for connecting to the positioners.

        Returns:
            dict[str, PositionerBase]: A dictionary mapping positioner names to positioner objects.
        """
        positioner_objs = {}
        # First we check that the device config of this device specifies
        # the relevant positioners as needs

        config = self._find_device_config_in_session(name, device_manager)
        needs = config.get("needs", [])
        for name, device_name in positioners.items():
            if device_name not in needs:
                raise ConnectionError(
                    f"Device '{name}' requires positioner device '{device_name}' to be specified in list of 'needs' in the device config."
                )
            try:
                device = device_manager.devices[device_name]
            except KeyError:
                raise ConnectionError(f"Device '{device_name}' not found in device manager.")
            if not hasattr(device, "move"):
                raise AttributeError(f"Device '{device_name}' does not have a 'move' method.")
            required_attrs = [
                ("readback", "user_readback"),
                ("setpoint", "user_setpoint"),
                ("motor_is_moving",),
            ]
            if not all(
                any([hasattr(device, attr) for attr in attr_tuple]) for attr_tuple in required_attrs
            ):
                raise AttributeError(
                    f"Device '{device_name}' must have at least one argument for each tuple in the following list of tuples: {required_attrs}."
                )
            positioner_objs[name] = device
            move_signature = inspect.signature(device.move)
            if "wait" in move_signature.parameters:
                self._positioner_move_kwargs[name] = {"wait": False}
        return positioner_objs

    def _find_device_config_in_session(
        self, device_name: str, device_manager: DeviceManagerDS
    ) -> dict[str, Any]:
        """
        Helper method to find the device config for a given device name in the current session config of the device manager.
        """
        configs = device_manager.current_session["devices"]
        config = None
        for conf in configs:
            if conf["name"] == device_name:
                config = conf
                break
        if config is None:
            raise ConnectionError(f"Device '{device_name}' not found in current session config.")
        return config

    @abstractmethod
    def forward_calculation(self, *args) -> float:
        """Calculate the pseudo motor value based on the positioner values."""

    @abstractmethod
    def inverse_calculation(self, position: float, **positioner_objects) -> dict[str, float]:
        """Calculate the positioner values based on the pseudo motor value."""

    @abstractmethod
    def motors_are_moving(self, *args) -> int:
        """Calculate whether the motors are moving based on the positioner values. Should be 0 or 1."""

    # pylint: disable=arguments-differ
    def move(self, position: float, **kwargs) -> StatusBase:
        """
        Move method for the pseudo motor. This currently only supports moving all positioners
        at once. If children want to implement more complex move logic, they can override this method
        based on this implementation and the inverse_calculation method.

        Args:
            position (float): The position to move the pseudo motor to.
            kwargs: The kwargs to pass to the move method of the positioners.
        """
        self.check_value(position)
        status = None
        motor_positions = self.inverse_calculation(position, **self.positioner_objects)
        for name, pos in motor_positions.items():
            positioner = self.positioner_objects[name]
            move_kwargs = self._positioner_move_kwargs.get(name, {})
            move_kwargs.update(kwargs)
            st = positioner.move(pos, **move_kwargs)
            if status is None:
                status = st
            else:
                status = AndStatus(status, st)  # Combine Status objects

        return status
