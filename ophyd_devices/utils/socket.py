import abc
import functools
import logging
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
    SUB_SETPOINT = "setpoint"

    @abc.abstractmethod
    def _socket_get(self):
        ...

    @abc.abstractmethod
    def _socket_set(self, val):
        ...

    def get(self):
        self._readback = self._socket_get()
        return self._readback

    def put(
        self,
        value,
        force=False,
        connection_timeout=1,
        callback=None,
        use_complete=None,
        timeout=1,
        **kwargs,
    ):
        """Using channel access, set the write PV to `value`.

        Keyword arguments are passed on to callbacks

        Parameters
        ----------
        value : any
            The value to set
        force : bool, optional
            Skip checking the value in Python first
        connection_timeout : float, optional
            If not already connected, allow up to `connection_timeout` seconds
            for the connection to complete.
        use_complete : bool, optional
            Override put completion settings
        callback : callable
            Callback for when the put has completed
        timeout : float, optional
            Timeout before assuming that put has failed. (Only relevant if
            put completion is used.)
        """
        if not force:
            pass
            # self.check_value(value)

        self.wait_for_connection(timeout=connection_timeout)
        if use_complete is None:
            use_complete = False

        self._socket_set(value)
        old_value = self._parent.position

        timestamp = time.time()
        super().put(value, timestamp=timestamp, force=True)
        self._run_subs(
            sub_type=self.SUB_SETPOINT,
            old_value=old_value,
            value=value,
            timestamp=timestamp,
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
        return {
            self.name: {
                "source": f"{self.parent.controller.name}:{self.name}",
                "dtype": data_type(val),
                "shape": data_shape(val),
            }
        }


class SocketIO:
    """SocketIO helper class for TCP IP connections"""

    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.is_open = False
        self._initialize_socket()

    def connect(self):
        print(f"connecting to {self.host} port {self.port}")
        # self.sock.create_connection((host, port))
        if self.sock is None:
            self._initialize_socket()
        self.sock.connect((self.host, self.port))

    def _put(self, msg_bytes):
        logger.debug(f"put message: {msg_bytes}")
        return self.sock.send(msg_bytes)

    def _recv(self, buffer_length=1024):
        msg = self.sock.recv(buffer_length)
        logger.debug(f"recv message: {msg}")
        return msg

    def _initialize_socket(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(5)

    def put(self, msg):
        return self._put(msg)

    def receive(self, buffer_length=1024):
        return self._recv(buffer_length=buffer_length)

    def open(self):
        self.connect()
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

    def connect(self):
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

    def open(self):
        self._initialize_socket()
        self.is_open = True

    def close(self):
        self.sock = None
        self.is_open = False
