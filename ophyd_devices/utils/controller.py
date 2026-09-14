from __future__ import annotations

import functools
import threading
import time
import traceback
from collections import deque
from collections.abc import Callable
from typing import TYPE_CHECKING, Annotated, overload

from bec_lib import bec_logger
from ophyd import Device
from ophyd.ophydobj import OphydObject
from pydantic import BaseModel, ConfigDict, Field

from ophyd_devices.utils.socket import (
    DEFAULT_CONNECT_TIMEOUT,
    DEFAULT_SOCKET_TIMEOUT,
    USE_DEFAULT_TIMEOUT,
    Timeout,
    _validate_timeout,
)

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


class SocketFraming(BaseModel):
    """Framing for UTF-8 commands and replies."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    put_prefix: str = Field(
        default="",
        description="Text prepended by socket_put() before UTF-8 encoding. "
        r"""With put_prefix=":" and the default suffix, socket_put("AB") sends b":AB\n".""",
    )
    put_suffix: str = Field(
        default="\n",
        description="Text appended by socket_put() before UTF-8 encoding. "
        r"""With put_suffix="\r" and the default prefix, socket_put("AB") sends b"AB\r".""",
    )
    get_terminators: tuple[Annotated[str, Field(min_length=1)], ...] = Field(
        default=("\r\n",),
        min_length=1,
        description="Non-empty sequences that tell socket_get() when to finish reading a text "
        "reply. "
        r"""With get_terminators=("\r\n",), reads of b"AB\r" and b"\n" complete one reply """
        r"""and socket_get() returns "AB\r\n".""",
    )
    get_trim_sequence: str = Field(
        default="\r\n",
        description="When trimming is enabled, socket_put_and_receive() returns the text before "
        "the first occurrence of this exact sequence in the completed reply. "
        r"""With get_trim_sequence="\r\n:", a reply of "123\r\n:" becomes "123", """
        """while a bare ":" stays visible. An empty string disables trimming.""",
    )


class Controller(OphydObject):
    r"""
    Base class for all socket-based controllers.
    For each unique combination of socket host and port, only one instance of a controller is created.

    Text communication separates command formatting, response completion, and
    response cleanup. Receiving a chunk from the socket does not necessarily mean
    the full response has arrived: a reply may span several reads.

    Args:
        name (str, optional): Name of the controller
        socket_cls (Callable[..., SocketIO]): Socket factory accepting host and port keywords.
        socket_host (str): Hostname or IP address of the controller
        socket_port (int): Port number of the controller
        device_manager (DeviceManagerDS): Device manager instance
        socket_timeout (float | None): Default time in seconds for a send or a
            complete reply. Omit to use the transport's default. None disables
            the timeout and zero selects nonblocking I/O. An explicit value
            requires a factory that accepts the socket_timeout keyword and must
            match the value on any controller already initialized for this endpoint.
        socket_connect_timeout (float | None): Default timeout in seconds for
            opening or reopening the socket. Defaults to 10 seconds. None
            allows connection attempts without a deadline.
        framing (SocketFraming | None): Complete text framing override. Defaults
            to the controller class's framing. An explicit override must match the
            framing of a controller already initialized for this endpoint.

    Notes:
        ``socket_get`` does not trim responses; ``wait_for_trail=False`` makes it
        read only once. Supplying ``response_length`` instead receives an exact
        byte count and bypasses text completion, decoding, and trimming. Commands
        supplied as bytes bypass the outgoing prefix and suffix.

    Example:
        A Galil controller uses different sequences to finish receiving and to
        trim value replies::

            framing = SocketFraming(
                put_prefix="",
                put_suffix="\r",
                get_terminators=(":", "?"),
                get_trim_sequence="\r\n:",
            )

        Both a bare acknowledgement ":" and an error marker "?" finish receiving
        and remain visible to the caller. For a value reply "123\r\n:",
        ``socket_get`` returns the entire reply, while ``socket_put_and_receive``
        returns "123" with its default trimming enabled. Thus the trim sequence
        can be longer than the sequence that completes receiving.
    """

    _controller_instances = {}
    _initialized = False
    _axes_per_controller = 1
    framing = SocketFraming()
    max_reply_length: int | None = None
    """Optional byte limit for text replies, including the terminator."""

    SUB_CONNECTION_CHANGE = "connection_change"

    def __init__(
        self,
        *,
        socket_cls: Callable[..., SocketIO],
        socket_host: str,
        socket_port: int,
        device_manager: DeviceManagerDS,
        name: str = "",
        attr_name="",
        parent=None,
        labels=None,
        kind=None,
        framing: SocketFraming | None = None,
        socket_timeout: Timeout = USE_DEFAULT_TIMEOUT,
        socket_connect_timeout: Timeout = USE_DEFAULT_TIMEOUT,
    ):
        _validate_timeout(socket_timeout, "socket_timeout")
        _validate_timeout(socket_connect_timeout, "socket_connect_timeout")
        if framing is not None and not isinstance(framing, SocketFraming):
            raise TypeError("framing must be a SocketFraming instance")
        if self._initialized and framing is not None and framing != self.framing:
            raise ValueError(f"Controller at {socket_host}:{socket_port} has different framing")
        if (
            self._initialized
            and socket_timeout is not USE_DEFAULT_TIMEOUT
            and socket_timeout != self._socket_timeout
        ):
            raise ValueError(
                f"Controller at {socket_host}:{socket_port} has a different socket timeout"
            )
        if (
            self._initialized
            and socket_connect_timeout is not USE_DEFAULT_TIMEOUT
            and socket_connect_timeout != self._socket_connect_timeout
        ):
            raise ValueError(
                f"Controller at {socket_host}:{socket_port} has a different socket connect timeout"
            )

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
            self._socket_timeout = socket_timeout
            self._socket_connect_timeout = (
                DEFAULT_CONNECT_TIMEOUT
                if socket_connect_timeout is USE_DEFAULT_TIMEOUT
                else socket_connect_timeout
            )
            self.framing = framing if framing is not None else self.framing
            self.command_history: deque[str] = deque(maxlen=self._command_history_length)
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
        sock = self.sock
        if not self.connected or sock is None:
            raise ConnectionError("Socket is not connected. Call 'on()' to establish a connection.")

        self.command_history.append(f"[PUT]: {val}")
        try:
            if isinstance(val, bytes):
                data = val
            else:
                data = f"{self.framing.put_prefix}{val}{self.framing.put_suffix}".encode()
            sock.put(data)
        except Exception as exc:
            self.command_history.append(f"[PUT-ERROR]: {exc!r}")
            raise

    @overload
    def socket_get(
        self,
        wait_for_trail: bool = True,
        timeout: Timeout = USE_DEFAULT_TIMEOUT,
        *,
        response_length: None = None,
    ) -> str: ...

    @overload
    def socket_get(
        self,
        wait_for_trail: bool = True,
        timeout: Timeout = USE_DEFAULT_TIMEOUT,
        *,
        response_length: int,
    ) -> bytes: ...

    @threadlocked
    def socket_get(
        self,
        wait_for_trail: bool = True,
        timeout: Timeout = USE_DEFAULT_TIMEOUT,
        *,
        response_length: int | None = None,
    ) -> str | bytes:
        """
        Receive a response from the controller through the socket.

        Args:
            wait_for_trail (bool): Keep receiving until any ``framing.get_terminators``
                entry is found. If False, receive only once. The response includes
                the trailing sequence and any remaining data from the final receive.
            timeout (float | None): Maximum time in seconds to receive the
                response across all reads. Omit to use the configured socket
                timeout or the transport's default. None waits indefinitely and
                zero reads only data that is immediately available.
            response_length (int | None): Receive exactly this positive number of
                bytes and return them unchanged. Overrides ``wait_for_trail``;
                no delimiter search or text decoding is performed.

        Returns:
            str | bytes: UTF-8 text when ``response_length`` is None, otherwise
            exactly ``response_length`` raw bytes. Text includes the delimiter
            and any following data from the last read; binary data is not stripped.

        Raises:
            ValueError: The timeout or response length is invalid, a text reply
                exceeds the configured byte limit, or the transport returns
                more bytes than requested in binary mode.
            TimeoutError: The response deadline or socket read timeout expires.
            ConnectionError: The socket closes before the requested length or
                text delimiter is received. A single text read may return "".
            UnicodeDecodeError: A text response contains invalid UTF-8.
            OSError: Another socket read error occurs.

        Notes:
            Holds the controller lock for the entire receive operation. Successful
            responses and receive errors are recorded in command history.
        """
        sock = self.sock
        if not self.connected or sock is None:
            raise ConnectionError("Socket is not connected. Call 'on()' to establish a connection.")
        try:
            self._validate_response_length(response_length)
            if timeout is USE_DEFAULT_TIMEOUT:
                timeout = self._socket_timeout
            if timeout is USE_DEFAULT_TIMEOUT:
                timeout = getattr(sock, "socket_timeout", DEFAULT_SOCKET_TIMEOUT)
            _validate_timeout(timeout)
            data = self._receive_reply(sock, response_length, wait_for_trail, timeout)
            response = data.decode() if response_length is None else bytes(data)
        except Exception as exc:
            self.command_history.append(f"[GET-ERROR]: {exc!r}")
            raise
        self.command_history.append(f"[GET]: {response}")
        return response

    def _receive_reply(
        self, sock: SocketIO, length: int | None, wait_for_trail: bool, timeout: float | None
    ) -> bytearray:
        """Collect the raw bytes for one reply under the controller lock.

        Args:
            sock: Transport captured at the start of the read.
            length: Validated positive byte count for a fixed-length reply.
                Each read requests only the remaining bytes. None selects text framing.
            wait_for_trail: In text mode, read until any configured terminator
                occurs, including across chunk boundaries. If False, read one chunk.
            timeout: Total receive budget in seconds, shared across all reads.
                None disables the deadline. Zero makes each read nonblocking.

        Returns:
            The collected bytes. Text replies include the matched terminator and
            any following bytes from the final chunk. A single-chunk read can be empty.

        Raises:
            TimeoutError: The receive budget or a transport read times out.
                The error includes any bytes collected before the timeout.
            ConnectionError: The peer closes before a framed reply is complete.
            ValueError: A text reply exceeds the configured byte limit or the
                transport returns more bytes than requested in binary mode.
            OSError: The transport reports another read failure.
        """
        deadline = time.monotonic() + timeout if timeout else None
        response = bytearray()
        terminators = self.framing.get_terminators if length is None and wait_for_trail else ()
        encoded_terminators = tuple(sequence.encode() for sequence in terminators)
        max_reply_length = self.max_reply_length
        if length is not None:
            expected = f"{length} bytes"
        elif terminators:
            expected = f"one of the trailing sequences {terminators!r}"
        else:
            expected = "a socket response"

        while True:
            remaining = timeout
            if deadline is not None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError(
                        f"Timed out after {timeout} seconds waiting for {expected}. "
                        f"Received data: {bytes(response)!r}"
                    )
            try:
                if length is None:
                    chunk = sock.receive(timeout=remaining)
                else:
                    chunk = sock.receive(buffer_length=length - len(response), timeout=remaining)
            except TimeoutError as exc:
                raise TimeoutError(
                    f"Socket read timed out while waiting for {expected}. "
                    f"Received data: {bytes(response)!r}"
                ) from exc
            if not chunk and (length is not None or terminators):
                raise ConnectionError(
                    f"Socket closed before {expected} was received. "
                    f"Received data: {bytes(response)!r}"
                )

            response.extend(chunk)
            if length is not None:
                if len(response) > length:
                    raise ValueError("Socket receive returned more bytes than requested")
                if len(response) == length:
                    return response
            else:
                if max_reply_length is not None and len(response) > max_reply_length:
                    raise ValueError(f"Reply exceeded max_reply_length ({max_reply_length} bytes)")
                if not terminators or any(sequence in response for sequence in encoded_terminators):
                    return response

    @overload
    def socket_put_and_receive(
        self,
        val: str,
        remove_trailing_chars=True,
        timeout: Timeout = USE_DEFAULT_TIMEOUT,
        *,
        response_length: None = None,
    ) -> str: ...

    @overload
    def socket_put_and_receive(
        self,
        val: str | bytes,
        remove_trailing_chars=True,
        timeout: Timeout = USE_DEFAULT_TIMEOUT,
        *,
        response_length: int,
    ) -> bytes: ...

    @threadlocked
    def socket_put_and_receive(
        self,
        val: str | bytes,
        remove_trailing_chars=True,
        timeout: Timeout = USE_DEFAULT_TIMEOUT,
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
                ``framing.get_trim_sequence``. Defaults to True. An empty trim
                sequence leaves text unchanged. Ignored for fixed-length binary
                responses, which are always returned unchanged.
            timeout (float | None): Maximum time in seconds to receive the
                response. Omit to use the same default as socket_get. None
                waits indefinitely and zero uses nonblocking reads.
            response_length (int | None): Positive response size in bytes. When
                supplied, return bytes even if the request is text.

        Returns:
            str | bytes: Text when ``response_length`` is None, otherwise exactly
            the requested number of raw bytes.

        Raises:
            ValueError: The timeout or response length is invalid, or a binary
                request is supplied without a response length. No command is sent.
            ControllerCommunicationError: Sending, receiving, decoding or stripping
                the response fails. The original exception is preserved as the cause.
        """
        _validate_timeout(timeout)
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
                f"Failed to communicate with the controller ({exc!r}). "
                f"The last {self._command_history_length} commands were: "
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
        """Trim a decoded text reply at the first occurrence of the configured sequence.

        Args:
            var: The full reply after UTF-8 decoding.

        Returns:
            The text preceding the first exact match. If the sequence is empty or
            absent from the reply, return the full reply.
        """
        trim_sequence = self.framing.get_trim_sequence
        return var.split(trim_sequence, 1)[0] if trim_sequence else var

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

    def on(self, timeout: Timeout = USE_DEFAULT_TIMEOUT) -> None:
        """
        Open a new socket connection to the controller

        Args:
            timeout: Connection timeout in seconds. Omit to use socket_connect_timeout.
                None allows connection attempts without a deadline.

        Raises:
            ValueError: The timeout is negative or nonfinite.
        """
        _validate_timeout(timeout)
        if not self.connected or self.sock is None:
            socket_options = (
                {}
                if self._socket_timeout is USE_DEFAULT_TIMEOUT
                else {"socket_timeout": self._socket_timeout}
            )
            self.sock = self._socket_cls(
                host=self._socket_host, port=self._socket_port, **socket_options
            )
            if timeout is USE_DEFAULT_TIMEOUT:
                timeout = self._socket_connect_timeout
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

    @threadlocked
    def reconnect(self, timeout: Timeout = USE_DEFAULT_TIMEOUT) -> None:
        """Replace the socket connection while holding the controller lock.

        The configured devices stay enabled. Callers decide whether to issue
        another command after the new connection opens.

        Args:
            timeout: Connection timeout in seconds. Omit to use socket_connect_timeout.
                None allows connection attempts without a deadline.

        Raises:
            ValueError: The timeout is negative or nonfinite.
            OSError: Closing the old connection or opening the new one fails.
        """
        _validate_timeout(timeout)
        logger.info("Reconnecting the controller socket...")
        self.off(update_config=False)
        self.on(timeout=self._socket_connect_timeout if timeout is USE_DEFAULT_TIMEOUT else timeout)

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
