import socket
from unittest import mock

import pytest
from bec_server.device_server.tests.utils import DMMock

from ophyd_devices.tests.utils import SocketMock
from ophyd_devices.utils.controller import Controller, ControllerCommunicationError
from ophyd_devices.utils.socket import SocketIO, SocketSignal


class DummySocketSignal(SocketSignal):
    """Dummy SocketSignal class for testing the SocketSignal interface."""

    def __init__(self, name, controller: Controller, **kwargs):
        super().__init__(name=name, **kwargs)
        self.controller = controller

    def _socket_get(self) -> str:
        return self.controller.socket_put_and_receive("get")

    def _socket_set(self, value: str):
        self.controller.socket_put_and_receive(value)


@pytest.fixture
def controller():
    """Controller fixture for testing the SocketSignal interface."""
    try:
        dm = DMMock()
        Controller._reset_controller()
        controller = Controller(
            name="controller",
            socket_cls=SocketMock,
            socket_host="localhost",
            socket_port=8080,
            device_manager=dm,
        )
        controller.on()
        yield controller
    finally:
        Controller._reset_controller()


@pytest.fixture
def signal(controller):
    """Dummy SocketSignal fixture for testing."""
    return DummySocketSignal(name="signal", auto_monitor=True, controller=controller)


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
    Test that the callback mechanism of SocketSignal correctly handles recursive reads without
    causing multiple socket reads, and that the value is correctly cached and passed to the callback.
    """
    controller = signal.controller
    assert signal._auto_monitor == True

    controller.sock: SocketMock
    controller.sock.buffer_recv = [b"value2", b"value1"]

    callback_read_buffer = []
    callback_value_buffer = []

    readback = signal.read()
    assert readback[signal.name]["value"] == "value2"

    def _test_cb(value, old_value, **kwargs):
        """Simulate a callback that triggers another read."""
        signal = kwargs["obj"]
        callback_value_buffer.append((value, old_value))
        readback = signal.read()
        callback_read_buffer.append(readback)

    signal.subscribe(_test_cb, event_type=signal.SUB_VALUE, run=False)

    readback = signal.read()
    assert len(callback_read_buffer) == 1, "Callback should have been called once"
    assert len(callback_value_buffer) == 1, "Callback should have been called once"

    assert readback == callback_read_buffer[0]
    assert callback_value_buffer == [("value1", "value2")]


def test_socket_signal_put(signal):
    """
    Test that the put method of the SocketSignal class correctly sends values to the socket,
    and that it implements the necessary subscription notifications for value changes.
    """
    controller = signal.controller
    controller.sock: SocketMock

    controller.sock.buffer_recv = [b"value2", b"new_value", b"new_value"]

    callback_read_buffer = []
    callback_value_buffer = []

    readback = signal.read()
    assert readback[signal.name]["value"] == "value2"

    def _test_readback_cb(value, old_value, **kwargs):
        """Simulate a callback that triggers another read."""
        signal = kwargs["obj"]
        callback_value_buffer.append((value, old_value))
        readback = signal.read()
        callback_read_buffer.append(readback)

    callback_setpoint_buffer = []

    def _test_setpoint_cb(value, old_value, **kwargs):
        """Simulate a callback that runs a read, this should trigger another read on the socket."""
        signal = kwargs["obj"]
        callback_setpoint_buffer.append((value, old_value))
        signal.read()

    signal.subscribe(_test_setpoint_cb, event_type=signal.SUB_SETPOINT, run=False)
    signal.subscribe(_test_readback_cb, event_type=signal.SUB_VALUE, run=False)

    # Now we run 'put'. This runs super().put(...), which triggers the SUB_VALUE callback first,
    # and then the SUB_SETPOINT callback. With our extra callback on SUB_VALUE, we will trigger
    # one _test_readback_cb callback through the super().put(...) call with sub_type SUB_VALUE,
    # and another _test_readback_cb callback through the _test_setpoint_cb callback with sub_type SUB_SETPOINT.
    # Respectively the signal.read() call in test_setpoint_cb.
    signal.put("new_value")
    assert controller.sock.buffer_put == [b"get\n", b"new_value\n", b"get\n"]
    assert len(callback_setpoint_buffer) == 1, "Setpoint callback should have been called once"
    assert len(callback_read_buffer) == 2, "Readback callback should have been called twice"
    assert len(callback_value_buffer) == 2, "Value callback should have been called twice"
    assert callback_setpoint_buffer == [("new_value", "value2")]
    assert callback_read_buffer[0][signal.name]["value"] == "new_value"
    assert callback_read_buffer[1][signal.name]["value"] == "new_value"
    assert callback_value_buffer == [("new_value", "value2"), ("new_value", "new_value")]


def test_socket_put_and_receive_raises_controller_communication_error(controller):
    """Test that socket_put_and_receive raises ControllerCommunicationError on socket errors."""
    controller.sock.buffer_recv = [b"\xbfhello", b"ok"]

    # First receive will raise a UnicodeDecodeError, which should be caught and re-raised as ControllerCommunicationError
    # second one will be successful
    val = controller.socket_put_and_receive("test")
    assert val == "ok"

    # Second test: simulate a socket error that cannot be decoded
    controller.sock.buffer_recv = [b"\xbfhello", b"\xbfworld"]
    with pytest.raises(ControllerCommunicationError):
        controller.socket_put_and_receive("test")


@pytest.fixture
def make_controller():
    """Factory fixture to build a fresh controller singleton with custom term/trail settings."""

    def _make(controller_cls=Controller, **kwargs):
        Controller._reset_controller()
        controller = controller_cls(
            name="controller",
            socket_cls=SocketMock,
            socket_host="localhost",
            socket_port=8080,
            device_manager=DMMock(),
            **kwargs,
        )
        controller.on()
        return controller

    yield _make
    Controller._reset_controller()


def test_socket_put_appends_custom_term(make_controller):
    controller = make_controller(term="\r")
    controller.socket_put("get")
    assert controller.sock.buffer_put == [b"get\r"]


@pytest.mark.parametrize(
    ["trail", "reply", "expected"],
    [
        (None, "value\r\n", "value"),
        (None, "\r\n", ""),
        (None, "line1\r\nline2\r\n", "line1\r\nline2"),
        ("\n", "value\n", "value"),
        ("\n", "\n", ""),
        ("\n", "line1\nline2\n", "line1\nline2"),
        ("", "value\r\n", "value\r\n"),
    ],
)
def test_remove_trailing_characters_strips_suffix_only(make_controller, trail, reply, expected):
    """The trail is stripped from the end of a reply only; mid-reply occurrences are preserved,
    a bare terminator reduces to an empty payload, and an empty trail strips nothing."""
    kwargs = {} if trail is None else {"trail": trail}
    controller = make_controller(**kwargs)
    assert controller._remove_trailing_characters(reply) == expected


@pytest.mark.parametrize(
    "kwargs", [{"term": b"\n"}, {"trail": b"\r\n"}, {"term": 13}, {"trail": 0}]
)
def test_term_and_trail_must_be_strings(make_controller, kwargs):
    with pytest.raises(TypeError):
        make_controller(**kwargs)


def test_second_construction_with_conflicting_term_trail_warns(make_controller):
    """A second construction for the same host:port keeps the first term/trail and warns."""
    controller = make_controller(term="\r", trail="\n")
    with mock.patch("ophyd_devices.utils.controller.logger") as mock_logger:
        second = Controller(
            name="controller",
            socket_cls=SocketMock,
            socket_host="localhost",
            socket_port=8080,
            device_manager=DMMock(),
            term="\n",
        )
        assert second is controller
        mock_logger.warning.assert_called_once()
    assert controller._term == "\r"
    assert controller._trail == "\n"


def test_second_construction_without_conflict_does_not_warn(make_controller):
    controller = make_controller(term="\r")
    with mock.patch("ophyd_devices.utils.controller.logger") as mock_logger:
        for kwargs in ({"term": "\r"}, {}):
            second = Controller(
                name="controller",
                socket_cls=SocketMock,
                socket_host="localhost",
                socket_port=8080,
                device_manager=DMMock(),
                **kwargs,
            )
            assert second is controller
        mock_logger.warning.assert_not_called()


def test_subclass_overrides_term_trail_as_class_attributes(make_controller):
    """Subclasses can set the wire protocol with class attributes, without any constructor plumbing."""

    class CRTermController(Controller):
        _term = "\r"
        _trail = "\n"

    controller = make_controller(controller_cls=CRTermController)
    controller.sock.buffer_recv = [b"value\n"]
    assert controller.socket_put_and_receive("get") == "value"
    assert controller.sock.buffer_put == [b"get\r"]
