"""Base class for pseudo motors built from real positioner objects.

The class wires three :class:`BECProcessedSignal` instances (`readback`,
`setpoint`, `motor_is_moving`) to user-defined calculation methods and combines
child-motor move statuses into one pseudo-motor status.
"""

from __future__ import annotations

import inspect
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Callable

from ophyd import Component as Cpt
from ophyd import Kind, PositionerBase

from ophyd_devices.interfaces.base_classes.psi_device_base import PSIDeviceBase
from ophyd_devices.utils.bec_processed_signal import BECProcessedSignal
from ophyd_devices.utils.psi_device_base_utils import AndStatus, StatusBase

if TYPE_CHECKING:  # pragma: no cover
    from bec_server.device_server.devices.devicemanager import DeviceManagerDS


class PSIPseudoMotorBase(ABC, PSIDeviceBase, PositionerBase):
    """Abstract base class for pseudo-positioners.

    Subclasses implement coordinate transforms via:

    - ``forward_calculation`` for readback/setpoint projection
    - ``inverse_calculation`` for pseudo-to-real target mapping
    - ``motors_are_moving`` for movement aggregation

    Please note that forward_calculation, inverse_calculation and motors_are_moving methods must be implemented with
    the same signature as the keys for the associated positioner objects stored in the positioner_objects attribute
    which is either passed to __init__ or set using the set_positioner_objects method. The positioner objects are expected
    to be ophyd PositionerBase object like devices or at least implement a 'move' method and have attributes
    'readback' or 'user_readback', 'setpoint' or 'user_setpoint', and 'motor_is_moving'.

    Args:
        name (str): The name of the pseudo motor device.
        device_manager (DeviceManagerDS): The device manager instance to fetch the positioner objects from based on the configuration.
        positioners (dict[str, PositionerBase] | None): A dictionary of positioner objects that this pseudo motor depends on. The keys should match the input parameters of the forward_calculation, inverse_calculation and motors_are_moving methods. If not provided during initialization, it can be set later using the set_positioner_objects method.
        egu (str): Engineering units for the pseudo motor.
        **kwargs: Additional keyword arguments to pass to the parent classes.
    """

    readback = Cpt(BECProcessedSignal, name="readback", model_config=None, kind=Kind.hinted)
    setpoint = Cpt(BECProcessedSignal, name="setpoint", model_config=None, kind=Kind.normal)
    motor_is_moving = Cpt(
        BECProcessedSignal, name="motor_is_moving", model_config=None, kind=Kind.omitted
    )

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
        self.readback.name = self.name

    @property
    def egu(self) -> str:
        """Engineering units for the pseudo motor."""
        return self._egu

    def set_positioner_objects(self, positioners: dict[str, PositionerBase]) -> None:
        """Set the positioner objects for the pseudo motor.

        Args:
            positioners (dict[str, PositionerBase]): A dictionary of positioner objects that this pseudo motor depends on.
        """
        self.positioner_objects = positioners

    def wait_for_connection(self, *args, **kwargs) -> None:
        """Validate signatures, wire processed signals, and connect dependencies."""
        if not self.positioner_objects:
            raise ConnectionError(
                f"No positioners specified for pseudo motor {self.name}. Please use 'set_positioner_objects' or pass positioner objects during initialization."
            )
        # Check if all methods have the required signature that matches the positioner_objects keys
        self._check_method_signatures()
        self._setup_pseudo_signal(
            "readback", ["readback", "user_readback"], self.forward_calculation
        )
        self._setup_pseudo_signal(
            "setpoint", ["setpoint", "user_setpoint"], self.forward_calculation
        )
        self._setup_pseudo_signal("motor_is_moving", ["motor_is_moving"], self.motors_are_moving)
        # Prepare move kwargs for each positioner based on their move method signature
        for name, positioner in self.positioner_objects.items():
            move_signature = inspect.signature(positioner.move)
            if "wait" in move_signature.parameters:
                self._positioner_move_kwargs[name] = {"wait": False}

        # Subscribe callback to updates of the readback signals
        self.readback.subscribe(self._run_readback_signal_subs, event_type=self.readback.SUB_VALUE)
        # Subscribe to "readback" event on each positioner
        for positioner in self.positioner_objects.values():
            positioner.subscribe(self._run_readback_event_subs, event_type=positioner.SUB_READBACK)
        return super().wait_for_connection(*args, **kwargs)

    def _run_readback_signal_subs(self, value: float, old_value: float, **kwargs):
        """Run subscriptions on the readback signal when it updates."""
        self._run_subs(sub_type=self.SUB_READBACK, old_value=old_value, value=value)

    def _run_readback_event_subs(self, *args, **kwargs):
        """Run subscriptions on the readback event when it updates."""
        new_val = self.readback.get()
        self._run_subs(sub_type=self.SUB_READBACK, value=new_val)

    def _check_method_signatures(self) -> None:
        """Ensure calculation method parameters match configured positioner keys."""
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
        self, pseudo_attr: str, allowed_attributes: list[str], compute_method: Callable[..., float]
    ):
        """Configure one pseudo signal from selected positioner attributes.

        Args:
            pseudo_attr (str): The name of the pseudo attribute to set up.
            allowed_attributes (list[str]): A list of allowed attributes for the positioner objects.
            compute_method (Callable[..., float]): Function used to compute the
                pseudo signal value.
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

        pseudo_attr_obj.set_compute_method(
            compute_method, **{name: obj for name, obj in device_objects.items()}
        )
        pseudo_attr_obj.wait_for_connection()

    def get_positioner_objects(
        self, name: str, positioners: dict[str, str], device_manager: DeviceManagerDS
    ) -> dict[str, PositionerBase]:
        """Resolve and validate positioner objects from device-manager names.

        Args:
            name (str): The name of the pseudo motor device.
            positioners (dict[str, str]): A dictionary mapping positioner names to device names.
            device_manager (DeviceManagerDS): The device manager instance to fetch the positioner objects from.

        Returns:
            dict[str, PositionerBase]: A dictionary of positioner objects.
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
        return positioner_objs

    def _find_device_config_in_session(
        self, device_name: str, device_manager: DeviceManagerDS
    ) -> dict[str, Any]:
        """Find the session configuration entry for ``device_name``.

        Args:
            device_name (str): The name of the device to find the configuration for.
            device_manager (DeviceManagerDS): The device manager instance to fetch the configuration from.

        Returns:
            dict[str, Any]: The configuration dictionary for the device.

        Raises:
            ConnectionError: If the device configuration is not found in the current session.
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
        """Compute pseudo value from positioner signals.

        Method parameters must include all keys defined in
        ``self.positioner_objects``.
        """

    @abstractmethod
    def inverse_calculation(self, position: float, **positioner_objects) -> dict[str, float]:
        """Map a pseudo target position to child-motor setpoints.

        The first argument is always the desired pseudo position.
        """

    @abstractmethod
    def motors_are_moving(self, *args) -> int:
        """Return a movement flag derived from child-motor motion signals."""

    # pylint: disable=arguments-differ
    def move(self, position: float, **kwargs) -> StatusBase:
        """Move child motors to realize a pseudo target position.

        The method calls :meth:`inverse_calculation` with the current method
        inputs of the ``readback`` processed signal, then moves each configured
        child positioner and combines all returned statuses with
        :class:`AndStatus`.

        Args:
            position (float): The desired position to move the pseudo motor to.
            **kwargs: Additional keyword arguments to pass to the move method of the positioner objects.
        Returns:
            StatusBase: A combined status object that represents the status of all the move operations on the
            positioner objects.
        """
        self.check_value(position)
        status = None
        motor_positions = self.inverse_calculation(
            position, **self.readback.compute_model.method_inputs
        )
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
