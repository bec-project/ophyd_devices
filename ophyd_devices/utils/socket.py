import abc
import functools
import socket
import time
import typing

import numpy as np
from bec_lib import bec_logger
from ophyd import Signal
from ophyd.utils.errors import DisconnectedError

logger = bec_logger.logger
# logger = bec_logger.logger("socket")


def raise_if_disconnected(fcn):
    """Decorator to catch attempted access to disconnected Galil channels."""

    @functools.wraps(fcn)
    def wrapper(self, *args, **kwargs):
        if self.connected:
            return fcn(self, *args, **kwargs)
        raise DisconnectedError(f"{self.name} is not connected")

    return wrapper


DEFAULT_EPICSSIGNAL_VALUE = object()

_type_map = {
    "number": (float, np.floating),
    "array": (np.ndarray, list, tuple),
    "string": (str,),
    "integer": (int, np.integer),
}


def data_shape(val):
    """Determine data-shape (dimensions)

    Returns
    -------
    list
        Empty list if val is number or string, otherwise
        ``list(np.ndarray.shape)``
    """
    if data_type(val) != "array":
        return []

    try:
        return list(val.shape)
    except AttributeError:
        return [len(val)]


def data_type(val):
    """Determine the JSON-friendly type name given a value

    Returns
    -------
    str
        One of {'number', 'integer', 'array', 'string'}

    Raises
    ------
    ValueError if the type is not recognized
    """
    bad_iterables = (str, bytes, dict)
    if isinstance(val, typing.Iterable) and not isinstance(val, bad_iterables):
        return "array"

    for json_type, py_types in _type_map.items():
        if isinstance(val, py_types):
            return json_type

    raise ValueError(
        f"Cannot determine the appropriate bluesky-friendly data type for "
        f"value {val} of Python type {type(val)}. "
        f"Supported types include: int, float, str, and iterables such as "
        f"list, tuple, np.ndarray, and so on."
    )


class SocketSignal(abc.ABC, Signal):
    """
    A base class for signals that interact with a socket. This class provides the necessary structure
    for reading from and writing to a socket, as well as handling callbacks and subscriptions in a way
    that prevents recursive calls. Children should implement the `_socket_get` and `_socket_set` methods
    to define the specific logic for interacting with the socket. `get` and `put` methods should not be
    overriden by children to ensure proper callback handling.

    Args:
        name (str): The name of the signal.
        auto_monitor (bool, optional): If True, it indicates that the signal should be auto_monitored.
    """

    SUB_SETPOINT = "setpoint"

    def __init__(self, *, name, auto_monitor=False, **kwargs):

        super().__init__(name=name, **kwargs)
        self._auto_monitor = auto_monitor
        self._active_socket_callbacks: set[str] = set()

    @abc.abstractmethod
    def _socket_get(self) -> typing.Any: ...

    @abc.abstractmethod
    def _socket_set(self, val): ...

    def get(self, **kwargs):
        """
        Get the current value of the signal. Children should never
        override this method, but should implement the socket read logic in
        'socket_get' to ensure proper callback handling and caching of values.
        """
        if self.SUB_VALUE in self._active_socket_callbacks:
            return self._readback
        old_value = self._readback
        self._readback = self._socket_get()
        timestamp = time.time()
        self._metadata["timestamp"] = timestamp
        self._run_subs(
            sub_type=self.SUB_VALUE, old_value=old_value, value=self._readback, timestamp=timestamp
        )
        return self._readback

    def _run_subs(self, *args, sub_type, **kwargs):
        """
        This method runs the callbacks for a given subscription type. It is overridden to ensure that
        callbacks for the same subscription type can not trigger additional subscriptions of the same type.
        We thereby avoid that callbacks can triggered recursively. In practice, a callback may call 'get'
        or 'read' itself, but it won't trigger any recursive calls of the callbacks for the same subscription type.

        Args:
            sub_type (str): The subscription type for which to run the callbacks.
        """
        if sub_type in self._active_socket_callbacks:
            return
        try:
            self._active_socket_callbacks.add(sub_type)
            super()._run_subs(*args, sub_type=sub_type, **kwargs)
        finally:
            if sub_type in self._active_socket_callbacks:
                self._active_socket_callbacks.remove(sub_type)

    def put(self, value, connection_timeout=1, **kwargs):
        """
        Put method to send values to the socket. Children should never override this method,
        but should implement instead the socket write logic in 'socket_set' to ensure proper
        callback handling.

        Args:
            value (any): The value to set
            connection_timeout (float, optional): If not already connected, allow up to `connection_timeout` seconds
                for the connection to complete.
        """

        self.wait_for_connection(timeout=connection_timeout)
        old_value = self._readback
        self._socket_set(value)
        timestamp = time.time()
        # Super().put(..) triggers the SUB_VALUE callbacks with the new value.
        super().put(value, timestamp=timestamp, force=True)
        self._run_subs(
            sub_type=self.SUB_SETPOINT, old_value=old_value, value=value, timestamp=timestamp
        )

    def describe(self):
        """Provide schema and meta-data for :meth:`~BlueskyInterface.read`

        This keys in the `OrderedDict` this method returns must match the
        keys in the `OrderedDict` return by :meth:`~BlueskyInterface.read`.

        This provides schema related information, (ex shape, dtype), the
        source (ex PV name), and if available, units, limits, precision etc.

        Returns
        -------
        data_keys : OrderedDict
            The keys must be strings and the values must be dict-like
            with the ``event_model.event_descriptor.data_key`` schema.
        """
        if self._readback is DEFAULT_EPICSSIGNAL_VALUE:
            val = self.get()
        else:
            val = self._readback
        controller = self.root.controller if hasattr(self.root, "controller") else None
        return {
            self.name: {
                "source": f"{controller.name}:{self.name}" if controller else self.name,
                "dtype": data_type(val),
                "shape": data_shape(val),
            }
        }


class SocketIO:
    """SocketIO helper class for TCP IP connections"""

    def __init__(self, host: str, port: int, socket_timeout: int = 2):
        self.host = host
        self.port = port
        self.is_open = False
        self.socket_timeout = socket_timeout
        self._initialize_socket()

    def connect(self, timeout: int = 10):
        """
        Establish socket connection to host:port within timeout period

        Args:
            timeout (int): Time in seconds to wait for connection
        """
        logger.info(f"Connecting to {self.host}:{self.port}.")
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                if self.sock is None:
                    self._initialize_socket()
                self.sock.connect((self.host, self.port))
                break
            except Exception as exc:
                self.sock = None
                logger.warning(
                    f"Connection to {self.host}:{self.port} failed after {time.time()-start_time:.2f} seconds"
                    f" with exception: {exc}. Retrying after 1 second..."
                )
                time.sleep(1)
        else:
            raise ConnectionError(
                f"Could not connect to {self.host}:{self.port} within {time.time()-start_time:.2f} seconds"
            )

    def _put(self, msg_bytes):
        logger.debug(f"put message: {msg_bytes}")
        return self.sock.send(msg_bytes)

    def _recv(self, buffer_length=1024):
        msg = self.sock.recv(buffer_length)
        logger.debug(f"recv message: {msg}")
        return msg

    def _initialize_socket(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(self.socket_timeout)

    def put(self, msg):
        return self._put(msg)

    def receive(self, buffer_length=1024):
        return self._recv(buffer_length=buffer_length)

    def open(self, timeout: int = 10):
        """
        Open the socket connection to the host:port

        Args:
            timeout (int): Time in seconds to wait for connection
        """
        self.connect(timeout=timeout)
        self.is_open = True

    def close(self):
        self.sock.close()
        self.sock = None
        self.is_open = False


class SocketMock:
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.buffer_put = b""
        self.buffer_recv = [b" -12800"]
        self.is_open = False
        # self.open()

    def connect(self, timeout: int = 10):
        print(f"connecting to {self.host} port {self.port}")

    def _put(self, msg_bytes):
        self.buffer_put = msg_bytes
        print(self.buffer_put)

    def _recv(self, buffer_length=1024):
        print(self.buffer_recv)
        if isinstance(self.buffer_recv, list):
            if len(self.buffer_recv) > 0:
                ret_val = self.buffer_recv.pop(0)
            else:
                ret_val = b""
            return ret_val
        return self.buffer_recv

    def _initialize_socket(self):
        pass

    def put(self, msg):
        return self._put(msg)

    def receive(self, buffer_length=1024):
        return self._recv(buffer_length=buffer_length)

    def open(self, timeout: int = 10):
        self._initialize_socket()
        self.is_open = True

    def close(self):
        self.sock = None
        self.is_open = False
