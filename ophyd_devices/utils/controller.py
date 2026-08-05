import functools
import threading
import time
import traceback
from collections import deque
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
    """Decorator to rerun a function once if a communication error was raised.

    Reconnects first to discard any stale/desynced reply left on the wire from the
    failed attempt -- without this, a late-arriving reply to the *first* attempt could
    be misread as the reply to the retry.
    """

    @functools.wraps(fcn)
    def wrapper(self, *args, **kwargs):
        try:
            val = fcn(self, *args, **kwargs)
        except Exception:
            content = traceback.format_exc()
            logger.warning(
                f"Communication error occurred. Reconnecting and retrying the command. Traceback: {content}"
            )
            self._reconnect()
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
        term (str, optional): Termination string appended to each outgoing socket request.
            Defaults to the class attribute _term ("\\n").
        trail (str, optional): Termination string stripped from the end of each socket reply.
            Defaults to the class attribute _trail ("\\r\\n").
        max_reply_length (int, optional): Max accepted length of a socket reply in bytes
            Defaults to 1024 bytes
        socket_timeout (int | float, optional): Timeout for each socket operation in seconds
            Defaults to 2 seconds

    Subclasses that need a different wire protocol should override the _term and _trail class
    attributes. The constructor arguments only take effect on the first instantiation per
    host:port; the controller is a singleton and later values are ignored with a warning.
    """

    _controller_instances = {}
    _initialized = False
    _axes_per_controller = 1
    _term = "\n"  # termination string appended to each outgoing request
    _trail = "\r\n"  # termination string stripped from the end of each reply
    _max_reply_length = 1024  # max accepted length of a socket reply in bytes
    _socket_timeout = 2  # timeout for each socket operation in seconds

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
        term: str | None = None,
        trail: str | list[str] | tuple[str, ...] | None = None,
        max_reply_length: int | None = None,
        socket_timeout: int | float | None = None,
    ):
        if term is not None and not isinstance(term, str):
            raise TypeError(f"term must be a string, got {type(term).__name__}")
        if trail is not None:
            if isinstance(trail, str):
                pass
            elif isinstance(trail, (list, tuple)) and all(isinstance(t, str) for t in trail):
                if not trail:
                    raise ValueError("trail must not be an empty list/tuple.")
            else:
                raise TypeError(
                    f"trail must be a string or a list/tuple of strings, got {type(trail).__name__}"
                )
        if max_reply_length is not None and not isinstance(max_reply_length, int):
            raise TypeError(
                f"max_reply_length must be an int, got {type(max_reply_length).__name__}"
            )
        if socket_timeout is not None and not isinstance(socket_timeout, (int, float)):
            raise TypeError(f"socket_timeout must be a number, got {type(socket_timeout).__name__}")
        if not self._initialized:
            super().__init__(
                name=name, attr_name=attr_name, parent=parent, labels=labels, kind=kind
            )
            self._command_history_length = 50  # Store the last 50 commands sent to the controller
            self._lock = threading.RLock()
            self._axis: list[Device] = []
            self._initialize()
            self._initialized = True
            self.sock = None
            self.device_manager = device_manager
            self._socket_cls = socket_cls
            self._socket_host = socket_host
            self._socket_port = socket_port
            if term is not None:
                self._term = term
            if trail is not None:
                self._trail = trail
            self._trail_options: tuple[str, ...] = (
                (self._trail,) if isinstance(self._trail, str) else tuple(self._trail)
            )
            if max_reply_length is not None:
                self._max_reply_length = max_reply_length
            if socket_timeout is not None:
                self._socket_timeout = socket_timeout
            self.command_history: deque[str] = deque(maxlen=self._command_history_length)
        elif (
            (term is not None and term != self._term)
            or (trail is not None and trail != self._trail)
            or (max_reply_length is not None and max_reply_length != self._max_reply_length)
            or (socket_timeout is not None and socket_timeout != self._socket_timeout)
        ):
            logger.warning(
                f"Controller {self._socket_host}:{self._socket_port} is already initialized with "
                f"term={self._term!r}, trail={self._trail!r}, max_reply_length={self._max_reply_length!r}, "
                f"socket_timeout={self._socket_timeout!r}; ignoring conflicting values "
                f"term={term!r}, trail={trail!r}, max_reply_length={max_reply_length!r}, "
                f"socket_timeout={socket_timeout!r}."
            )

    @threadlocked
    def _reconnect(self):
        """
        Close and reopen the socket connection.

        Required after any communication error, in particular a recv() timeout:
        this protocol has no per-message IDs, so there is no way to know whether
        bytes that show up on the wire *after* a timeout belong to the request that
        timed out or to whatever is sent next. A stale reply arriving late would
        otherwise be read as the answer to a new command (or concatenated with it).
        Closing and reopening the TCP connection discards any such reply-in-flight,
        so the next command starts from a guaranteed-clean slate.
        """
        try:
            if self.sock is not None:
                self.sock.close()
        except Exception:
            logger.warning("Error closing socket during reconnect.", exc_info=True)
        finally:
            self.sock = None
            self.connected = False
        self.on()

    @threadlocked
    def socket_put(self, val: str):
        """
        Send a command to the controller through the socket.

        Args:
            val (str): Command to send
        """
        self.command_history.append(f"[PUT]: time:{time.time()}, cmd:{val + self._term}")
        self.sock.put(f"{val}{self._term}".encode())

    @threadlocked
    def socket_get(self):
        """
        Receive a single, complete reply from the controller.

        Loops on `recv()` until any one of `self._trail_options` is seen, since a
        reply can arrive split across multiple TCP reads, and different commands on
        the same controller (e.g. ACS SETVAR vs GETVAR) can use different terminators.
        `self._max_reply_length` guards against a malformed/runaway reply with no
        matching trail. Does not protect against stale replies from a prior
        timed-out request; that's handled by reconnecting the socket on
        communication errors (see `_reconnect`).

        Returns:
            str: The decoded reply, including its trailing terminator.

        Raises:
            ControllerCommunicationError: If the connection closes while waiting
                for a reply, or the reply exceeds `self._max_reply_length`.
        """
        buf = b""
        while True:
            for trail in self._trail_options:
                if trail.encode() in buf:
                    response = buf.decode()
                    self.command_history.append(f"[GET]: time:{time.time()}, rep:{response}")
                    return response

            chunk = self.sock.receive()
            if not chunk:
                raise ControllerCommunicationError(
                    "Socket connection closed by remote host while waiting for a reply."
                )
            buf += chunk
            if len(buf) > self._max_reply_length:
                raise ControllerCommunicationError(
                    f"Reply exceeded max_reply_length ({self._max_reply_length} bytes): {buf!r}"
                )

    @retry_once
    @threadlocked
    def socket_put_and_receive(self, val: str, remove_trailing_chars=True) -> str:
        """
        Send a command to the controller and receive the response.
        Override this method in the derived class if necessary, especially if the response
        needs to be parsed differently.
        """
        try:
            self.socket_put(val)
            if remove_trailing_chars:
                return self._remove_trailing_characters(self.socket_get())
            return self.socket_get()
        except Exception as exc:
            logger.error(
                f"Error in socket_put_and_receive: {exc}. Command history: {list(self.command_history)}"
            )
            raise ControllerCommunicationError(
                f"Failed to communicate with the controller. The last {self._command_history_length} commands were: "
                f"{list(self.command_history)}"
            ) from exc

    def _remove_trailing_characters(self, var) -> str:
        """Strip whichever configured trail terminator is present at the end of a
        reply; mid-reply occurrences are kept."""
        for trail in self._trail_options:
            if var.endswith(trail):
                return var.removesuffix(trail)
        return var

    @threadlocked
    def print_command_history(self):
        """
        Print the command history for debugging purposes.
        """
        print("\n".join(self.command_history))

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
            timeout (int): Time in seconds to wait for the connection itself to
                be established (passed to `SocketIO.open`). This is separate from
                `self._socket_timeout`, which governs how long each individual
                send/recv call is allowed to take once connected.
        """
        if not self.connected or self.sock is None:
            self.sock = self._socket_cls(
                host=self._socket_host, port=self._socket_port, socket_timeout=self._socket_timeout
            )
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
        if host_port not in cls._controller_instances or not isinstance(
            cls._controller_instances[host_port], cls
        ):
            cls._controller_instances[host_port] = object.__new__(cls)
        return cls._controller_instances[host_port]
