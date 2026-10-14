from __future__ import annotations

import functools
import threading
import time
import traceback
from collections import deque
from typing import TYPE_CHECKING, Type, overload

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
        except Exception:
            content = traceback.format_exc()
            logger.warning(
                f"Communication error occurred. Retrying the command. Traceback: {content}"
            )
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
    r"""
    Base class for all socket-based controllers.
    For each unique combination of socket host and port, only one instance of a controller is created.

    Text communication separates command formatting, response completion, and
    response cleanup. Receiving a chunk from the socket does not necessarily mean
    the full response has arrived: a reply may span several reads.

    Args:
        name (str, optional): Name of the controller
        socket_cls (Type[SocketIO]): Socket class to use for communication
        socket_host (str): Hostname or IP address of the controller
        socket_port (int): Port number of the controller
        device_manager (DeviceManagerDS): Device manager instance
        get_trail_sequences (tuple[str, ...] | None): Alternative sequences that
            mark a complete text response. With ``wait_for_trail=True``,
            ``socket_get`` keeps reading until any sequence occurs in the collected
            bytes, even across reads. It returns the decoded text including the
            matched sequence and any following data from the final read. Matching
            only completes receiving; it does not classify a reply as success or
            error. The base default is ("\r\n",).
        get_trim_sequence (str | None): One exact sequence used to clean up a
            completed text response in ``socket_put_and_receive`` when
            ``remove_trailing_chars=True``. The first occurrence and everything
            after it are removed. An empty string or an absent match leaves the
            text unchanged. This is a complete sequence, not a set of characters
            to strip, and it does not control when receiving finishes. The base
            default is "\r\n".
        put_lead_char (str | None): Prefix prepended to outgoing text commands.
            The base default is an empty string.
        put_trail_char (str | None): Suffix appended to outgoing text commands
            before UTF-8 encoding. The base default is "\n".

    Notes:
        These settings can be defined as subclass attributes or passed to the
        constructor. Passing None keeps the corresponding class default.
        ``socket_get`` does not trim responses; ``wait_for_trail=False`` makes it
        read only once. Supplying ``response_length`` instead receives an exact
        byte count and bypasses text completion, decoding, and trimming. Commands
        supplied as bytes bypass the outgoing prefix and suffix.

    Example:
        A Galil controller uses different sequences to finish receiving and to
        trim value replies::

            put_trail_char = "\r"
            get_trail_sequences = (":", "?")
            get_trim_sequence = "\r\n:"

        Both a bare acknowledgement ":" and an error marker "?" finish receiving
        and remain visible to the caller. For a value reply "123\r\n:",
        ``socket_get`` returns the entire reply, while ``socket_put_and_receive``
        returns "123" with its default trimming enabled. Thus the trim sequence
        can be longer than the sequence that completes receiving.
    """

    _controller_instances = {}
    _initialized = False
    _axes_per_controller = 1
    put_lead_char = ""
    put_trail_char = "\n"
    get_trail_sequences = ("\r\n",)
    get_trim_sequence = "\r\n"

    SUB_CONNECTION_CHANGE = "connection_change"

    def __init__(
        self,
        *,
        socket_cls: Type[SocketIO],
        socket_host: str,
        socket_port: int,
        device_manager: DeviceManagerDS,
        name: str = "",
        attr_name="",
        parent=None,
        labels=None,
        kind=None,
        get_trail_sequences: tuple[str, ...] | None = None,
        get_trim_sequence: str | None = None,
        put_lead_char: str | None = None,
        put_trail_char: str | None = None,
    ):
        if not self._initialized:
            super().__init__(
                name=name, attr_name=attr_name, parent=parent, labels=labels, kind=kind
            )
            self._command_history_length = 50  # Store the last 50 commands sent to the controller
            self._lock = threading.RLock()
            self._axis: list[Device] = []
            self._initialize()
            self.sock = None
            self.device_manager = device_manager
            self._socket_cls = socket_cls
            self._socket_host = socket_host
            self._socket_port = socket_port
            self.get_trail_sequences = (
                get_trail_sequences if get_trail_sequences is not None else self.get_trail_sequences
            )
            self.get_trim_sequence = (
                get_trim_sequence if get_trim_sequence is not None else self.get_trim_sequence
            )
            self.put_lead_char = put_lead_char if put_lead_char is not None else self.put_lead_char
            self.put_trail_char = (
                put_trail_char if put_trail_char is not None else self.put_trail_char
            )
            self.command_history: deque[str] = deque(maxlen=self._command_history_length)

            if not isinstance(self.get_trail_sequences, tuple) or not all(
                isinstance(seq, str) for seq in self.get_trail_sequences
            ):
                raise ValueError("get_trail_sequences must be a tuple of strings")
            if not isinstance(self.get_trim_sequence, str):
                raise ValueError("get_trim_sequence must be a string")

            # convert get_trail_sequences to a tuple of bytes for internal use
            self._get_trail_sequences_bytes = tuple(
                seq.encode() for seq in self.get_trail_sequences
            )

            self._initialized = True

    @threadlocked
    def socket_put(self, val: str | bytes) -> None:
        """
        Send a command to the controller through the socket.

        Args:
            val (str | bytes): Command to send. Text uses the configured prefix and
                suffix and UTF-8 encoding; bytes are sent unchanged.

        Raises:
            ConnectionError: The controller is disconnected or has no socket.
            OSError: The transport fails to send the command, including a socket
                timeout. Transport errors are recorded in command history and
                propagated unchanged.
        """
        if not self.connected or self.sock is None:
            raise ConnectionError("Socket is not connected. Call 'on()' to establish a connection.")

        self.command_history.append(f"[PUT]: {val}")
        try:
            if isinstance(val, bytes):
                data = val
            else:
                data = f"{self.put_lead_char}{val}{self.put_trail_char}".encode()
            self.sock.put(data)
        except Exception as exc:
            self.command_history.append(f"[PUT-ERROR]: {exc!r}")
            raise

    @overload
    def socket_get(
        self, wait_for_trail: bool = True, timeout: float = 2, *, response_length: None = None
    ) -> str: ...

    @overload
    def socket_get(
        self, wait_for_trail: bool = True, timeout: float = 2, *, response_length: int
    ) -> bytes: ...

    @threadlocked
    def socket_get(
        self, wait_for_trail: bool = True, timeout: float = 2, *, response_length: int | None = None
    ) -> str | bytes:
        """
        Receive a response from the controller through the socket.

        Args:
            wait_for_trail (bool): Keep receiving until any ``get_trail_sequences``
                entry is found. If False, receive only once. The response includes
                the trailing sequence and any remaining data from the final receive.
            timeout (float): Maximum time in seconds to receive the response,
                across all reads. Defaults to 2 seconds.
            response_length (int | None): Receive exactly this positive number of
                bytes and return them unchanged. Overrides ``wait_for_trail``;
                no delimiter search or text decoding is performed.

        Returns:
            str | bytes: UTF-8 text when ``response_length`` is None, otherwise
            exactly ``response_length`` raw bytes. Text includes the delimiter
            and any following data from the last read; binary data is not stripped.

        Raises:
            ValueError: The response length is not a positive integer, or the
                transport returns more bytes than requested in binary mode.
            TimeoutError: The response deadline or socket read timeout expires.
            ConnectionError: The socket closes before the requested length or
                text delimiter is received. A single text read may return "".
            UnicodeDecodeError: A text response contains invalid UTF-8.
            OSError: Another socket read error occurs.

        Notes:
            Holds the controller lock for the entire receive operation. Successful
            responses and receive errors are recorded in command history.
        """
        if not self.connected or self.sock is None:
            raise ConnectionError("Socket is not connected. Call 'on()' to establish a connection.")
        try:
            self._validate_response_length(response_length)
            if response_length is not None:
                response = self._receive_exactly(response_length, timeout)
            else:
                response = self._receive_text(wait_for_trail, timeout)
        except Exception as exc:
            self.command_history.append(f"[GET-ERROR]: {exc!r}")
            raise
        self.command_history.append(f"[GET]: {response}")
        return response

    def _receive_exactly(self, length: int, timeout: float) -> bytes:
        """Receive a binary frame without reading into the next response.

        Args:
            length (int): Exact number of bytes to collect. The caller must
                validate that this is a positive integer before calling.
            timeout (float): Response deadline in seconds, shared across all
                reads. The transport's own read timeout may expire sooner.

        Returns:
            bytes: The complete frame, without decoding or delimiter removal.

        Raises:
            TimeoutError: The response deadline or socket read timeout expires.
            ConnectionError: The socket closes before the frame is complete.
            ValueError: The transport returns more bytes than requested.
            OSError: Another socket read error occurs.

        Notes:
            Called by ``socket_get`` while the controller lock is held. Each read
            requests only the number of bytes still missing from the frame.
        """
        # only for type checking; already validated by socket_get
        assert self.sock is not None

        deadline = time.monotonic() + timeout
        response = bytearray()
        while len(response) < length:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(
                    f"Timed out after {timeout} seconds waiting for {length} bytes. "
                    f"Received data: {bytes(response)!r}"
                )
            chunk = self.sock.receive(buffer_length=length - len(response), timeout=remaining)
            if not chunk:
                raise ConnectionError(
                    f"Socket closed before {length} bytes were received. "
                    f"Received data: {bytes(response)!r}"
                )
            response.extend(chunk)
            if len(response) > length:
                raise ValueError("Socket receive returned more bytes than requested")
        return bytes(response)

    def _receive_text(self, wait_for_trail: bool, timeout: float) -> str:
        """Receive text, decoding only after all chunks have been collected.

        Args:
            wait_for_trail (bool): If True, collect bytes until any UTF-8 encoded
                sequence in ``get_trail_sequences`` occurs in the response.
                Otherwise, read once.
            timeout (float): Response deadline in seconds, shared across all
                reads. The transport's own read timeout may expire sooner.

        Returns:
            str: UTF-8 decoded response, including the delimiter and any data
            following it in the final read. A single read can return "".

        Raises:
            TimeoutError: The response deadline or socket read timeout expires.
            ConnectionError: The socket closes while waiting for the delimiter.
            UnicodeDecodeError: The collected response is not valid UTF-8.
            OSError: Another socket read error occurs.

        Notes:
            Called by ``socket_get`` while the controller lock is held. Delimiters
            and UTF-8 characters may span multiple reads.
        """
        # only for type checking; already validated by socket_get
        assert self.sock is not None

        deadline = time.monotonic() + timeout
        response = bytearray()
        expected = (
            f"one of the trailing sequences {self.get_trail_sequences!r}"
            if wait_for_trail
            else "a socket response"
        )
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(
                    f"Timed out after {timeout} seconds waiting for {expected}. "
                    f"Received data: {bytes(response)!r}"
                )
            chunk = self.sock.receive(timeout=remaining)
            if wait_for_trail and not chunk:
                raise ConnectionError(
                    f"Socket closed before {expected} was received. "
                    f"Received data: {bytes(response)!r}"
                )
            response.extend(chunk)
            if not wait_for_trail or any(
                sequence in response for sequence in self._get_trail_sequences_bytes
            ):
                # UTF-8 characters, like the delimiter, may span multiple receives.
                return response.decode()

    @overload
    def socket_put_and_receive(
        self,
        val: str,
        remove_trailing_chars=True,
        timeout: float = 2,
        *,
        response_length: None = None,
    ) -> str: ...

    @overload
    def socket_put_and_receive(
        self,
        val: str | bytes,
        remove_trailing_chars=True,
        timeout: float = 2,
        *,
        response_length: int,
    ) -> bytes: ...

    @threadlocked
    def socket_put_and_receive(
        self,
        val: str | bytes,
        remove_trailing_chars=True,
        timeout: float = 2,
        *,
        response_length: int | None = None,
    ) -> str | bytes:
        """
        Send a command once and receive the response.
        Holds the controller lock across the send/receive operation. Communication
        failures are propagated without resending the command. Protocol-specific
        response validation belongs to the caller.

        Args:
            val (str | bytes): Text command or raw binary request. Binary requests
                require ``response_length``.
            remove_trailing_chars (bool): Return only the text before the first
                ``get_trim_sequence``. Defaults to True. An empty trim sequence
                leaves text unchanged. Ignored for fixed-length binary responses,
                which are always returned unchanged.
            timeout (float): Maximum time in seconds to receive the response.
            response_length (int | None): Positive response size in bytes. When
                supplied, return bytes even if the request is text.

        Returns:
            str | bytes: Text when ``response_length`` is None, otherwise exactly
            the requested number of raw bytes.

        Raises:
            ValueError: The response length is invalid, or a binary request is
                supplied without a response length. No command is sent.
            ControllerCommunicationError: Sending, receiving, decoding or stripping
                the response fails. The original exception is preserved as the cause.
        """
        # Validate before sending: an invalid receive mode must not issue a command.
        self._validate_response_length(response_length)
        if isinstance(val, bytes) and response_length is None:
            raise ValueError("Binary requests require response_length")
        try:
            self.socket_put(val)
            if response_length is not None:
                return self.socket_get(timeout=timeout, response_length=response_length)
            if remove_trailing_chars:
                return self._remove_trailing_characters(self.socket_get(timeout=timeout))
            return self.socket_get(timeout=timeout)
        except Exception as exc:
            logger.error(
                f"Error in socket_put_and_receive: {exc}. Command history: {list(self.command_history)}"
            )
            raise ControllerCommunicationError(
                f"Failed to communicate with the controller. The last {self._command_history_length} commands were: "
                f"{list(self.command_history)}"
            ) from exc

    @staticmethod
    def _validate_response_length(response_length: int | None) -> None:
        """Validate the optional fixed-length receive size.

        Args:
            response_length (int | None): None selects text receiving; a positive
                integer selects a fixed-length binary response.

        Raises:
            ValueError: The value is neither None nor a positive integer.
                Booleans are rejected even though they are integer subclasses.
        """
        if response_length is not None and (
            isinstance(response_length, bool)
            or not isinstance(response_length, int)
            or response_length <= 0
        ):
            raise ValueError("response_length must be a positive integer")

    def _remove_trailing_characters(self, var: str) -> str:
        """Return text before the trim sequence, or unchanged if trimming is disabled."""
        return var.split(self.get_trim_sequence, 1)[0] if self.get_trim_sequence else var

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
        if host_port not in cls._controller_instances or not isinstance(
            cls._controller_instances[host_port], cls
        ):
            cls._controller_instances[host_port] = object.__new__(cls)
        return cls._controller_instances[host_port]
