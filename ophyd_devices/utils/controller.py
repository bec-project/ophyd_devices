import functools
import threading
from typing import TYPE_CHECKING, Type

from bec_lib import bec_logger
from ophyd import Device
from ophyd.ophydobj import OphydObject

if TYPE_CHECKING:
    from bec_server.device_server.device_server import DeviceManagerDS

    from ophyd_devices.utils.socket import SocketIO


logger = bec_logger.logger


class ControllerError(Exception):
    """Base class for controller exceptions."""


class ControllerCommunicationError(ControllerError):
    """Exception raised when a communication error occurs with the controller."""


def threadlocked(fcn):
    """Ensure that the thread acquires and releases the lock."""

    @functools.wraps(fcn)
    def wrapper(self, *args, **kwargs):
        lock = self._lock if hasattr(self, "_lock") else self.controller._lock
        with lock:
            return fcn(self, *args, **kwargs)

    return wrapper


def retry_once(fcn):
    """Decorator to rerun a function in case a CommunicationError was raised. This may happen if the buffer was not empty."""

    @functools.wraps(fcn)
    def wrapper(self, *args, **kwargs):
        try:
            val = fcn(self, *args, **kwargs)
        except ControllerCommunicationError:
            val = fcn(self, *args, **kwargs)
        return val

    return wrapper


def axis_checked(fcn):
    """Decorator to catch attempted access to channels that are not available."""

    @functools.wraps(fcn)
    def wrapper(self, *args, **kwargs):
        if "axis_nr" in kwargs:
            self._check_axis_number(kwargs["axis_nr"])
        elif "axis_Id_numeric" in kwargs:
            self._check_axis_number(kwargs["axis_Id_numeric"])
        elif args:
            self._check_axis_number(args[0])
        return fcn(self, *args, **kwargs)

    return wrapper


class Controller(OphydObject):
    """
    Base class for all socket-based controllers.

    Args:
        name (str, optional): Name of the controller
        socket_cls (Type[SocketIO]): Socket class to use for communication
        socket_host (str): Hostname or IP address of the controller
        socket_port (int): Port number of the controller
        device_manager (DeviceManagerDS): Device manager instance
    """

    _controller_instances = {}
    _initialized = False
    _axes_per_controller = 1

    SUB_CONNECTION_CHANGE = "connection_change"

    def __init__(
        self,
        *,
        socket_cls: Type["SocketIO"],
        socket_host: str,
        socket_port: int,
        device_manager: "DeviceManagerDS",
        name: str = "",
        attr_name="",
        parent=None,
        labels=None,
        kind=None,
    ):
        if not self._initialized:
            super().__init__(
                name=name, attr_name=attr_name, parent=parent, labels=labels, kind=kind
            )
            self._lock = threading.RLock()
            self._axis: list[Device] = []
            self._initialize()
            self._initialized = True
            self.sock = None
            self.device_manager = device_manager
            self._socket_cls = socket_cls
            self._socket_host = socket_host
            self._socket_port = socket_port

    @threadlocked
    def socket_put(self, val: str):
        """
        Send a command to the controller through the socket.

        Args:
            val (str): Command to send
        """
        self.sock.put(f"{val}\n".encode())

    @threadlocked
    def socket_get(self):
        """
        Receive a response from the controller through the socket.
        """
        return self.sock.receive().decode()

    @retry_once
    @threadlocked
    def socket_put_and_receive(self, val: str, remove_trailing_chars=True) -> str:
        """
        Send a command to the controller and receive the response.
        Override this method in the derived class if necessary, especially if the response
        needs to be parsed differently.
        """
        self.socket_put(val)
        if remove_trailing_chars:
            return self._remove_trailing_characters(self.sock.receive().decode())
        return self.socket_get()

    def _remove_trailing_characters(self, var) -> str:
        if len(var) > 1:
            return var.split("\r\n")[0]
        return var

    def get_axis_by_name(self, name: str) -> Device:
        """
        Get an axis by name.

        Args:
            name (str): Name of the axis

        Returns:
            Device: Device instance
        """
        for axis in self._axis:
            if axis:
                if axis.name == name:
                    return axis
        raise RuntimeError(f"Could not find an axis with name {name}")

    def set_device_read_write(self, device_name: str, enabled: bool) -> None:
        """
        Change the read-only status of a device.
        If the device is not configured, a warning is logged.

        Args:
            device_name (str): Name of the device
            enabled (bool): Set device to read-only or writable
        """
        if device_name not in self.device_manager.devices:
            logger.warning(
                f"Device {device_name} is not available on the device manager, cannot be set to read-only: {not enabled}."
            )
            return
        self.device_manager.devices[device_name].read_only = not enabled

    def set_device_enabled(self, device_name: str, enabled: bool) -> None:
        """
        Enable/disable a device. If the device is not configured, a warning is logged.

        Args:
            device_name (str): Name of the device
            enabled (bool): Enable or disable the device
        """
        if device_name not in self.device_manager.devices:
            logger.warning(
                f"Device {device_name} is not available on the device manager, cannot be set to enabled: {enabled}."
            )
            return
        self.device_manager.devices[device_name].enabled = enabled
        if enabled:
            self.on()
        else:
            all_disabled = all(
                not self.device_manager.devices[axis.name].enabled
                for axis in self._axis
                if axis is not None
            )
            if all_disabled:
                self.off(update_config=False)

    def set_all_devices_enabled(self, enabled: bool) -> None:
        """
        Enable or disable all devices registered for the controller.

        Args:
            enabled (bool): Enable or disable all devices
        """
        for axis in self._axis:
            if axis is None:
                logger.info("Axis is not assigned, skipping enabling/disabling.")
                continue
            self.set_device_enabled(axis.name, enabled)

    def _initialize(self):
        self._connected = False
        self._set_default_values()

    def _set_default_values(self):
        # no. of axes controlled by each controller
        self._axis = [None for axis_num in range(self._axes_per_controller)]

    @classmethod
    def _reset_controller(cls):
        cls._controller_instances = {}
        cls._initialized = False

    @property
    def connected(self):
        return self._connected

    @connected.setter
    def connected(self, value):
        self._connected = value
        self._run_subs(sub_type=self.SUB_CONNECTION_CHANGE)

    @axis_checked
    def set_axis(self, *, axis: Device, axis_nr: int) -> None:
        """Assign an axis to a device instance.

        Args:
            axis (Device): Device instance (e.g. GalilMotor)
            axis_nr (int): Controller axis number

        """
        self._axis[axis_nr] = axis

    @axis_checked
    def remove_axis(self, *, axis_nr: int) -> None:
        """Remove the device instance assigned to a controller axis.

        Args:
            axis_nr (int): Controller axis number

        """
        self._axis[axis_nr] = None
        if not any(self._axis):
            self.off(update_config=False)

    @axis_checked
    def get_axis(self, axis_nr: int) -> Device:
        """Get device instance for a specified controller axis.

        Args:
            axis_nr (int): Controller axis number

        Returns:
            Device: Device instance (e.g. GalilMotor)

        """
        return self._axis[axis_nr]

    def _check_axis_number(self, axis_Id_numeric: int) -> None:
        if axis_Id_numeric >= self._axes_per_controller:
            raise ValueError(
                f"Axis {axis_Id_numeric} exceeds the available number of axes ({self._axes_per_controller})"
            )

    def on(self, timeout: int = 10) -> None:
        """
        Open a new socket connection to the controller

        Args:
            timeout (int): Time in seconds to wait for connection
        """
        if not self.connected or self.sock is None:
            self.sock = self._socket_cls(host=self._socket_host, port=self._socket_port)
            self.sock.open(timeout=timeout)
            self.connected = True
        else:
            logger.info("The connection has already been established.")

    def off(self, update_config: bool = True) -> None:
        """Close the socket connection to the controller"""
        if self.connected and self.sock is not None:
            self.sock.close()
            self.connected = False
            self.sock = None
            if update_config:
                # Disable all axes associated with this controller
                self.set_all_devices_enabled(False)
        else:
            logger.info("The connection is already closed.")

    def __new__(cls, *args, **kwargs):
        socket_cls = kwargs.get("socket_cls")
        socket_host = kwargs.get("socket_host")
        socket_port = kwargs.get("socket_port")
        device_manager = kwargs.get("device_manager")
        if not socket_cls:
            raise RuntimeError("Socket class must be specified.")
        if not socket_host:
            raise RuntimeError("Socket host must be specified.")
        if not socket_port:
            raise RuntimeError("Socket port must be specified.")
        if not device_manager:
            raise RuntimeError("Device manager must be specified.")
        host_port = f"{socket_host}:{socket_port}"
        if host_port not in cls._controller_instances:
            cls._controller_instances[host_port] = object.__new__(cls)
        return cls._controller_instances[host_port]
