import socket
import time
from unittest import mock

import pytest
from bec_server.device_server.tests.utils import DMMock

from ophyd_devices.tests.utils import SocketMock
from ophyd_devices.utils.controller import Controller
from ophyd_devices.utils.socket import SocketIO, SocketSignal


class DummySocketSignal(SocketSignal):
    """Dummy SocketSignal class for testing the SocketSignal interface."""

    def __init__(
        self, name, controller: Controller, notify_bec=True, readback_timeout=None, **kwargs
    ):
        super().__init__(
            name=name, notify_bec=notify_bec, readback_timeout=readback_timeout, **kwargs
        )
        self.controller = controller

    def _socket_get(self) -> str:
        self._metadata["timestamp"] = time.monotonic()
        return self.controller.socket_put_and_receive("get")

    def _socket_set(self, value: str):
        self.controller.socket_put_and_receive(value)


@pytest.fixture
def controller():
    dm = DMMock()
    controller = Controller(
        name="controller",
        socket_cls=SocketMock,
        socket_host="localhost",
        socket_port=8080,
        device_manager=dm,
    )
    controller.on()
    return controller


@pytest.fixture
def signal(controller):
    return DummySocketSignal(name="signal", controller=controller, readback_timeout=0.1)


class DummySocket:
    AF_INET = 2
    SOCK_STREAM = 1

    def __init__(self) -> None:
        self.address_family = None
        self.socket_kind = None
        self.timeout = None

    def socket(self, address_family, socket_kind):
        self.address_family = address_family
        self.socket_kind = socket_kind
        return self

    def settimeout(self, timeout):
        self.timeout = timeout

    def send(self, msg, *args, **kwargs):
        self.send_buffer = msg

    def connect(self, address):
        self.host = address[0]
        self.port = address[1]
        self.connected = True

    def close(self):
        self.connected = False


def test_socket_init():
    socketio = SocketIO("localhost", 8080)

    assert socketio.host == "localhost"
    assert socketio.port == 8080

    assert socketio.is_open == False

    assert socketio.sock.family == socket.AF_INET
    assert socketio.sock.type == socket.SOCK_STREAM


def test_socket_put():
    dsocket = DummySocket()
    socketio = SocketIO("localhost", 8080)
    socketio.sock = dsocket
    socketio.put(b"message")
    assert dsocket.send_buffer == b"message"


def test_open():
    dsocket = DummySocket()
    socketio = SocketIO("localhost", 8080)
    socketio.sock = dsocket
    socketio.open()
    assert socketio.is_open == True
    assert socketio.sock.host == socketio.host
    assert socketio.sock.port == socketio.port


def test_socket_open_with_timeout():
    dsocket = DummySocket()
    socketio = SocketIO("localhost", 8080)
    socketio.sock = dsocket
    with mock.patch.object(dsocket, "connect") as mock_connect:
        socketio.open(timeout=0.1)
        mock_connect.assert_called_once()
        mock_connect.reset_mock()
        # There is a 1s sleep in the retry loop, mock_connect should be called only once
        mock_connect.side_effect = Exception("Connection failed")
        with pytest.raises(ConnectionError):
            socketio.open(timeout=0.4)
        mock_connect.assert_called_once()


def test_close():
    socketio = SocketIO("localhost", 8080)
    socketio.close()
    assert socketio.sock == None
    assert socketio.is_open == False


def test_socket_signal_get(signal):
    """
    Test that the get method of the SocketSignal class correctly retrives values from the socket,
    and that it implements the caching and timeout mechanism to avoid excessive socket reads and/or recursions.
    """
    # First get should call the socket and cache the value
    controller = signal.controller

    controller.sock: SocketMock
    controller.sock.buffer_recv = [b"value2", b"value1"]
    signal._readback_timeout = 0
    readback = signal.read()
    assert readback[signal.name]["value"] == "value2"
    readback2 = signal.read()
    assert readback2[signal.name]["value"] == "value1"
    assert readback[signal.name]["timestamp"] != readback2[signal.name]["timestamp"]
    controller.sock.buffer_recv = [b"value2"]

    cb_bucket = []
    read_value = None
    signal._readback_timeout = 10

    def _test_cb(value, old_value, **kwargs):
        cb_bucket.append((value, old_value))
        read_value = signal.read()

    signal.subscribe(_test_cb, event_type=signal.SUB_VALUE, run=False)
    signal._readback_timeout = 10
    signal._last_readback = 0  # reset the last readback time to force a socket read
    readback1 = signal.read()
    assert readback1[signal.name]["value"] == "value2"
    # The value should be cached, so it should not change
    assert cb_bucket == [("value2", "value1")]
    readback2 = signal.read()
    for entry in ("value", "timestamp"):
        assert readback1[signal.name][entry] == readback2[signal.name][entry]


def test_socket_signal_put(signal):
    """
    Test that the put method of the SocketSignal class correctly sends values to the socket,
    and that it implements the necessary subscription notifications for value changes.
    """
    controller = signal.controller
    controller.sock: SocketMock
    cb_bucket = []
    initial_value = signal._readback

    def _test_cb(value, old_value, **kwargs):
        cb_bucket.append((value, old_value))

    signal.subscribe(_test_cb, event_type=signal.SUB_SETPOINT, run=False)
    signal.put("new_value")
    assert controller.sock.buffer_put == [b"new_value\n"]
    assert cb_bucket == [("new_value", initial_value)]
    signal.put("another_value")
    assert controller.sock.buffer_put == [b"new_value\n", b"another_value\n"]
    assert cb_bucket == [("new_value", initial_value), ("another_value", "new_value")]
