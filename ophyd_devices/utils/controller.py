import functools
import threading

from bec_lib.core import bec_logger
from ophyd.ophydobj import OphydObject

logger = bec_logger.logger


def threadlocked(fcn):
    """Ensure that the thread acquires and releases the lock."""

    @functools.wraps(fcn)
    def wrapper(self, *args, **kwargs):
        lock = self._lock if hasattr(self, "_lock") else self.controller._lock
        with lock:
            return fcn(self, *args, **kwargs)

    return wrapper


class Controller(OphydObject):
    _controller_instances = {}

    SUB_CONNECTION_CHANGE = "connection_change"

    def __init__(
        self,
        *,
        name=None,
        socket_cls=None,
        socket_host=None,
        socket_port=None,
        attr_name="",
        parent=None,
        labels=None,
        kind=None,
    ):
        self.sock = None
        self._socket_cls = socket_cls
        self._socket_host = socket_host
        self._socket_port = socket_port
        if not hasattr(self, "_initialized"):
            super().__init__(
                name=name, attr_name=attr_name, parent=parent, labels=labels, kind=kind
            )
            self._lock = threading.RLock()
            self._initialize()
            self._initialized = True

    def _initialize(self):
        self._connected = False
        self._set_default_values()

    def _set_default_values(self):
        # no. of axes controlled by each controller
        self._axis_per_controller = 8
        self._motors = [None for axis_num in range(self._axis_per_controller)]

    @property
    def connected(self):
        return self._connected

    @connected.setter
    def connected(self, value):
        self._connected = value
        self._run_subs(sub_type=self.SUB_CONNECTION_CHANGE)

    def set_motor(self, motor, axis):
        """Set the motor instance for a specified controller axis."""
        self._motors[axis] = motor

    def get_motor(self, axis):
        """Get motor instance for a specified controller axis."""
        return self._motors[axis]

    def on(self) -> None:
        """Open a new socket connection to the controller"""
        if not self.connected or self.sock is None:
            self.sock = self._socket_cls(host=self._socket_host, port=self._socket_port)
            self.sock.open()
            self.connected = True
        else:
            logger.info("The connection has already been established.")

    def off(self) -> None:
        """Close the socket connection to the controller"""
        if self.connected or self.sock is not None:
            self.sock.close()
            self.connected = False
            self.sock = None
        else:
            logger.info("The connection is already closed.")

    def __new__(cls, *args, **kwargs):
        socket_cls = kwargs.get("socket_cls")
        socket_host = kwargs.get("socket_host")
        socket_port = kwargs.get("socket_port")
        if not socket_cls:
            raise RuntimeError("Socket class must be specified.")
        if not socket_host:
            raise RuntimeError("Socket host must be specified.")
        if not socket_port:
            raise RuntimeError("Socket port must be specified.")
        host_port = f"{socket_host}:{socket_port}"
        if host_port not in Controller._controller_instances:
            Controller._controller_instances[host_port] = object.__new__(cls)
        return Controller._controller_instances[host_port]
