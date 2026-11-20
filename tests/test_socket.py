import socket
from unittest import mock

import pytest
from bec_server.device_server.tests.utils import DMMock
from pydantic import ValidationError

from ophyd_devices.tests.utils import SocketMock
from ophyd_devices.utils.controller import Controller, ControllerCommunicationError, SocketFraming
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
def controller_kwargs():
    return {
        "name": "controller",
        "socket_cls": SocketMock,
        "socket_host": "localhost",
        "socket_port": 8080,
        "device_manager": DMMock(),
    }


@pytest.fixture
def controller(request, controller_kwargs):
    """Controller fixture for testing the SocketSignal interface."""
    Controller._reset_controller()
    try:
        controller = Controller(**controller_kwargs, framing=getattr(request, "param", None))
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

    def sendall(self, msg, *args, **kwargs):
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
    assert socketio.put(b"message") is None
    assert dsocket.send_buffer == b"message"


@pytest.mark.parametrize(
    ("configured_timeout", "read_timeout"), [(None, 0.5), (0.1, 0.5), (2, 0.5), (2, None)]
)
@pytest.mark.parametrize("fails", [False, True])
def test_socket_receive_overrides_and_restores_timeout(configured_timeout, read_timeout, fails):
    with mock.patch("ophyd_devices.utils.socket.socket.socket") as socket_factory:
        socketio = SocketIO("localhost", 8080)
    raw_socket = socket_factory.return_value
    raw_socket.gettimeout.return_value = configured_timeout
    raw_socket.settimeout.reset_mock()
    error = TimeoutError("Receive timed out")
    raw_socket.recv.side_effect = [error if fails else b"response"]

    if fails:
        with pytest.raises(TimeoutError) as exc_info:
            socketio.receive(timeout=read_timeout)
        assert exc_info.value is error
    else:
        assert socketio.receive(timeout=read_timeout) == b"response"

    assert raw_socket.settimeout.call_args_list == [
        mock.call(read_timeout),
        mock.call(configured_timeout),
    ]
    raw_socket.recv.assert_called_once_with(1024)


def test_socket_receive_keeps_timeout_when_omitted():
    with mock.patch("ophyd_devices.utils.socket.socket.socket") as socket_factory:
        socketio = SocketIO("localhost", 8080)
    raw_socket = socket_factory.return_value
    raw_socket.settimeout.reset_mock()
    raw_socket.recv.return_value = b"response"

    assert socketio.receive() == b"response"

    raw_socket.settimeout.assert_not_called()


def test_socket_rejects_negative_default_timeout_before_creating_socket():
    with (
        mock.patch("ophyd_devices.utils.socket.socket.socket") as socket_factory,
        pytest.raises(ValueError, match="socket_timeout must be finite"),
    ):
        SocketIO("localhost", 8080, socket_timeout=-1)

    socket_factory.assert_not_called()


@pytest.mark.parametrize("method", ["connect", "open", "receive"])
def test_socket_rejects_negative_timeout_before_io(method):
    with mock.patch("ophyd_devices.utils.socket.socket.socket") as socket_factory:
        socketio = SocketIO("localhost", 8080)
    raw_socket = socket_factory.return_value
    raw_socket.reset_mock()

    with pytest.raises(ValueError, match="timeout must be finite"):
        getattr(socketio, method)(timeout=-1)

    assert raw_socket.mock_calls == []
    assert not socketio.is_open


@pytest.mark.parametrize("replace_socket", [False, True])
def test_socket_receive_preserves_error_if_socket_closes_during_read(replace_socket):
    with mock.patch("ophyd_devices.utils.socket.socket.socket"):
        socketio = SocketIO("localhost", 8080)
    raw_socket = socketio.sock
    raw_socket.gettimeout.return_value = 2
    raw_socket.settimeout.reset_mock()
    replacement = mock.Mock()
    error = OSError("Socket closed during read")

    def close_during_read(_buffer_length):
        socketio.close()
        if replace_socket:
            socketio.sock = replacement
        raise error

    raw_socket.recv.side_effect = close_during_read
    with pytest.raises(OSError) as exc_info:
        socketio.receive(timeout=0.5)

    assert exc_info.value is error
    raw_socket.settimeout.assert_called_once_with(0.5)
    replacement.settimeout.assert_not_called()


def test_socket_receive_preserves_error_if_timeout_restoration_fails():
    with mock.patch("ophyd_devices.utils.socket.socket.socket"):
        socketio = SocketIO("localhost", 8080)
    raw_socket = socketio.sock
    raw_socket.gettimeout.return_value = 2
    error = TimeoutError("Receive timed out")
    raw_socket.recv.side_effect = error
    raw_socket.settimeout.reset_mock()
    raw_socket.settimeout.side_effect = [None, OSError("Socket closed during restoration")]

    with pytest.raises(TimeoutError) as exc_info:
        socketio.receive(timeout=0.5)

    assert exc_info.value is error
    assert raw_socket.settimeout.call_args_list == [mock.call(0.5), mock.call(2)]


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
        # The sleep consumes the remaining budget when it is shorter than the retry interval.
        mock_connect.side_effect = Exception("Connection failed")
        with pytest.raises(ConnectionError):
            socketio.open(timeout=0.4)
        mock_connect.assert_called_once()


@pytest.mark.parametrize("connect_timeout", [3, None])
def test_socket_uses_connection_budget_then_restores_operation_timeout(connect_timeout):
    with mock.patch("ophyd_devices.utils.socket.socket.socket") as socket_factory:
        socketio = SocketIO("localhost", 8080, socket_timeout=0.1)
    raw_socket = socket_factory.return_value
    operations = mock.Mock()
    operations.attach_mock(raw_socket.settimeout, "settimeout")
    operations.attach_mock(raw_socket.connect, "connect")
    with mock.patch("ophyd_devices.utils.socket.time.monotonic", side_effect=[10, 10]):
        socketio.open(timeout=connect_timeout)

    assert operations.mock_calls == [
        mock.call.settimeout(connect_timeout),
        mock.call.connect(("localhost", 8080)),
        mock.call.settimeout(0.1),
    ]


def test_close():
    socketio = SocketIO("localhost", 8080)
    socketio.close()
    assert socketio.sock == None
    assert socketio.is_open == False


@pytest.mark.parametrize(("socket_timeout", "connect_timeout"), [(0.1, 5), (None, None)])
def test_controller_forwards_socket_timeout_when_opening_and_reconnecting(
    controller_kwargs, socket_timeout, connect_timeout
):
    Controller._reset_controller()
    initial_socket, replacement_socket = mock.Mock(), mock.Mock()
    socket_factory = mock.Mock(side_effect=[initial_socket, replacement_socket])
    controller_kwargs["socket_cls"] = socket_factory
    try:
        controller = Controller(
            **controller_kwargs,
            socket_timeout=socket_timeout,
            socket_connect_timeout=connect_timeout,
        )
        controller.on()
        controller.reconnect()
        assert socket_factory.call_args_list == [
            mock.call(host="localhost", port=8080, socket_timeout=socket_timeout),
            mock.call(host="localhost", port=8080, socket_timeout=socket_timeout),
        ]
        initial_socket.open.assert_called_once_with(timeout=connect_timeout)
        replacement_socket.open.assert_called_once_with(timeout=connect_timeout)
        assert Controller(**controller_kwargs) is controller
        with pytest.raises(ValueError, match="different socket timeout"):
            Controller(**controller_kwargs, socket_timeout=2)
    finally:
        Controller._reset_controller()


@pytest.mark.parametrize("name", ["socket_timeout", "socket_connect_timeout"])
def test_controller_rejects_negative_configured_timeout(controller_kwargs, name):
    Controller._reset_controller()
    try:
        with pytest.raises(ValueError, match=f"{name} must be finite"):
            Controller(**controller_kwargs, **{name: -1})
    finally:
        Controller._reset_controller()


@pytest.mark.parametrize("connect_timeout", [3, None])
def test_controller_reconnect_replaces_socket_without_sending(controller, connect_timeout):
    old_socket = controller.sock
    new_socket = mock.Mock()
    with (
        mock.patch.object(controller, "_socket_cls", return_value=new_socket),
        mock.patch.object(controller, "set_all_devices_enabled") as set_enabled,
    ):
        controller.reconnect(timeout=connect_timeout)

    assert not old_socket.is_open
    assert controller.sock is new_socket
    assert controller.connected
    new_socket.open.assert_called_once_with(timeout=connect_timeout)
    new_socket.put.assert_not_called()
    assert old_socket.buffer_put == []
    set_enabled.assert_not_called()


@pytest.mark.parametrize("timeout", [-1, float("nan"), float("inf")])
def test_invalid_reconnect_timeout_preserves_live_socket(controller, timeout):
    old_socket = controller.sock
    with (
        mock.patch.object(controller, "_socket_cls") as socket_factory,
        pytest.raises(ValueError, match="timeout must be finite"),
    ):
        controller.reconnect(timeout=timeout)

    assert controller.sock is old_socket
    assert old_socket.is_open
    assert controller.connected
    socket_factory.assert_not_called()


def test_invalid_connect_timeout_does_not_create_socket(controller):
    controller.off(update_config=False)
    with (
        mock.patch.object(controller, "_socket_cls") as socket_factory,
        pytest.raises(ValueError, match="timeout must be finite"),
    ):
        controller.on(timeout=-1)

    assert not controller.connected
    socket_factory.assert_not_called()


def test_socket_signal_get(signal):
    """
    Test that the callback mechanism of SocketSignal correctly handles recursive reads without
    causing multiple socket reads, and that the value is correctly cached and passed to the callback.
    """
    controller = signal.controller
    assert signal._auto_monitor == True

    controller.sock: SocketMock
    controller.sock.buffer_recv = [b"value2\r\n", b"value1\r\n"]

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

    controller.sock.buffer_recv = [b"value2\r\n", b"new_value\r\n", b"new_value\r\n"]

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


@pytest.mark.parametrize(
    "chunks, controller, expected",
    [
        ([b"hello\r\n"], None, "hello\r\n"),
        ([b"hel", b"lo", b"\r\n"], None, "hello\r\n"),
        ([b"hello\r", b"\n"], None, "hello\r\n"),
        ([b"caf\xc3", b"\xa9\r\n"], None, "café\r\n"),
        ([b"hello<", b"END", b">"], SocketFraming(get_terminators=("<END>",)), "hello<END>"),
        ([b"hello\r\nextra"], None, "hello\r\nextra"),
    ],
    indirect=["controller"],
)
def test_socket_get_waits_for_trail(controller, chunks, expected):
    with mock.patch.object(controller.sock, "receive", side_effect=chunks) as receive:
        assert controller.socket_get() == expected

    assert receive.call_count == len(chunks)
    assert list(controller.command_history) == [f"[GET]: {expected}"]


@pytest.mark.parametrize("first_chunk", [b"partial", b""])
def test_socket_get_without_waiting_for_trail(controller, first_chunk):
    controller.sock.buffer_recv = [first_chunk, b"remaining\r\n"]

    assert controller.socket_get(wait_for_trail=False) == first_chunk.decode()

    assert controller.sock.buffer_recv == [b"remaining\r\n"]
    assert list(controller.command_history) == [f"[GET]: {first_chunk.decode()}"]


@pytest.mark.parametrize("use_exchange", [False, True])
@pytest.mark.parametrize("socket_timeout", [0.125, 0, None])
def test_socket_receive_uses_transport_timeout_by_default(controller, use_exchange, socket_timeout):
    controller.sock.socket_timeout = socket_timeout
    with (
        mock.patch("ophyd_devices.utils.controller.time.monotonic", side_effect=[10, 10]),
        mock.patch.object(controller.sock, "receive", return_value=b"reply\r\n") as receive,
    ):
        if use_exchange:
            assert controller.socket_put_and_receive("get") == "reply"
        else:
            assert controller.socket_get() == "reply\r\n"

    receive.assert_called_once_with(timeout=socket_timeout)


def test_socket_exchange_none_overrides_a_finite_transport_timeout(controller):
    with mock.patch("ophyd_devices.utils.socket.socket.socket") as socket_factory:
        controller.sock = SocketIO("localhost", 8080, socket_timeout=0.1)
    raw_socket = socket_factory.return_value
    raw_socket.gettimeout.return_value = 0.1
    raw_socket.settimeout.reset_mock()
    raw_socket.recv.side_effect = [b"re", b"ply\r\n"]

    assert controller.socket_put_and_receive("get", timeout=None) == "reply"

    assert raw_socket.settimeout.call_args_list == [mock.call(None), mock.call(0.1)] * 2


def test_invalid_socket_get_timeout_does_not_read(controller):
    with (
        mock.patch.object(controller.sock, "receive") as receive,
        pytest.raises(ValueError, match="timeout must be finite"),
    ):
        controller.socket_get(timeout=-1)

    receive.assert_not_called()


def test_invalid_exchange_timeout_does_not_send(controller):
    with pytest.raises(ValueError, match="timeout must be finite"):
        controller.socket_put_and_receive("get", timeout=-1)

    assert controller.sock.buffer_put == []
    assert not controller.command_history


def test_socket_get_timeout_covers_all_reads(controller):
    with (
        mock.patch(
            "ophyd_devices.utils.controller.time.monotonic", side_effect=[10, 10, 10.75, 11]
        ),
        mock.patch.object(controller.sock, "receive", side_effect=[b"par", b"tial"]) as receive,
    ):
        with pytest.raises(TimeoutError, match="Timed out after 1 seconds") as exc_info:
            controller.socket_get(timeout=1)

    assert [call.kwargs["timeout"] for call in receive.call_args_list] == [1, 0.25]
    assert list(controller.command_history) == [f"[GET-ERROR]: {exc_info.value!r}"]


@pytest.mark.parametrize("chunks", [[b""], [b"partial", b""]])
def test_socket_get_logs_closed_connection_before_trail(controller, chunks):
    with mock.patch.object(controller.sock, "receive", side_effect=chunks) as receive:
        with pytest.raises(
            ConnectionError, match="Socket closed before one of the trailing sequences"
        ) as exc_info:
            controller.socket_get()

    assert receive.call_count == len(chunks)
    assert list(controller.command_history) == [f"[GET-ERROR]: {exc_info.value!r}"]


@pytest.mark.parametrize("partial_response", [[], [b"partial"]])
def test_socket_get_logs_receive_error(controller, partial_response):
    error = TimeoutError("Receive timed out")
    with mock.patch.object(controller.sock, "receive", side_effect=[*partial_response, error]):
        with pytest.raises(TimeoutError) as exc_info:
            controller.socket_get()

    assert exc_info.value.__cause__ is error
    assert f"Received data: {b''.join(partial_response)!r}" in str(exc_info.value)
    assert list(controller.command_history) == [f"[GET-ERROR]: {exc_info.value!r}"]


def test_socket_get_logs_decode_error(controller):
    controller.sock.buffer_recv = [b"\xbfhello\r\n"]

    with pytest.raises(UnicodeDecodeError) as exc_info:
        controller.socket_get()

    assert list(controller.command_history) == [f"[GET-ERROR]: {exc_info.value!r}"]


def test_socket_put_logs_send_error(controller):
    error = BrokenPipeError("Connection closed")
    with mock.patch.object(controller.sock, "put", side_effect=error):
        with pytest.raises(BrokenPipeError) as exc_info:
            controller.socket_put("test")

    assert exc_info.value is error
    assert list(controller.command_history) == [
        "[PUT]: test",
        "[PUT-ERROR]: BrokenPipeError('Connection closed')",
    ]


@pytest.mark.parametrize(
    "controller, chunks, raw_response, stripped_response",
    [
        (
            SocketFraming(get_terminators=("<END>",), get_trim_sequence="<END>"),
            [b"hel", b"lo<EN", b"D>extra"],
            "hello<END>extra",
            "hello",
        ),
        (SocketFraming(get_terminators=("\n",), get_trim_sequence="\n"), [b"\n"], "\n", ""),
        (
            SocketFraming(get_terminators=(":", "?"), get_trim_sequence="\r\n:"),
            [b"123\r", b"\n", b":"],
            "123\r\n:",
            "123",
        ),
        (SocketFraming(get_terminators=(":", "?"), get_trim_sequence="\r\n:"), [b":"], ":", ":"),
        (SocketFraming(get_terminators=(":", "?"), get_trim_sequence="\r\n:"), [b"?"], "?", "?"),
        (
            SocketFraming(get_terminators=("<END>",), get_trim_sequence=""),
            [b"hello<END>"],
            "hello<END>",
            "hello<END>",
        ),
    ],
    indirect=["controller"],
)
@pytest.mark.parametrize("remove_trailing_chars", [True, False])
def test_socket_put_and_receive_waits_for_trail(
    controller, remove_trailing_chars, chunks, raw_response, stripped_response
):
    controller.sock.buffer_recv = chunks.copy()

    response = controller.socket_put_and_receive(
        "test", remove_trailing_chars=remove_trailing_chars
    )

    assert response == (stripped_response if remove_trailing_chars else raw_response)
    assert controller.sock.buffer_put == [b"test\n"]
    assert controller.sock.buffer_recv == []
    assert list(controller.command_history) == ["[PUT]: test", f"[GET]: {raw_response}"]


@pytest.mark.parametrize("remove_trailing_chars", [True, False])
def test_socket_put_and_receive_forwards_timeout(controller, remove_trailing_chars):
    with mock.patch.object(controller, "socket_get", return_value="ok\r\n") as socket_get:
        response = controller.socket_put_and_receive(
            "test", remove_trailing_chars=remove_trailing_chars, timeout=0.5
        )

    socket_get.assert_called_once_with(timeout=0.5)
    assert response == ("ok" if remove_trailing_chars else "ok\r\n")


def test_socket_put_and_receive_raises_controller_communication_error(controller):
    """Test that socket_put_and_receive raises ControllerCommunicationError on socket errors."""
    controller.sock.buffer_recv = [b"\xbfhello\r\n", b"ok\r\n"]

    with pytest.raises(ControllerCommunicationError) as exc_info:
        controller.socket_put_and_receive("test")
    assert isinstance(exc_info.value.__cause__, UnicodeDecodeError)
    assert controller.sock.buffer_put == [b"test\n"]
    assert controller.sock.buffer_recv == [b"ok\r\n"]
    assert [entry.split(": ", 1)[0] for entry in controller.command_history] == [
        "[PUT]",
        "[GET-ERROR]",
    ]
    assert str(list(controller.command_history)) in str(exc_info.value)


@pytest.mark.parametrize(
    "controller", [SocketFraming(put_prefix=":", put_suffix="\r")], indirect=True
)
@pytest.mark.parametrize("command, expected", [("test", b":test\r"), (b"\xa2\x00U", b"\xa2\x00U")])
def test_socket_put_preserves_binary_commands(controller, command, expected):
    controller.socket_put(command)
    assert controller.sock.buffer_put == [expected]


@pytest.mark.parametrize("terminators", [(), ("",), ("\r\n", "")])
def test_socket_framing_rejects_empty_terminators(terminators):
    with pytest.raises(ValidationError, match="get_terminators"):
        SocketFraming(get_terminators=terminators)


def test_controller_uses_subclass_framing(controller, controller_kwargs):
    class CustomController(Controller):
        framing = SocketFraming(
            put_prefix=":", put_suffix="\r", get_terminators=(">",), get_trim_sequence="\n>"
        )

    custom = CustomController(**{**controller_kwargs, "socket_port": 8081})
    custom.on()
    custom.sock.buffer_recv = [b"value\n", b">"]

    assert custom.socket_put_and_receive("test") == "value"
    assert custom.sock.buffer_put == [b":test\r"]
    assert controller.framing == SocketFraming()


@pytest.mark.parametrize("controller", [SocketFraming(put_suffix="\r")], indirect=True)
def test_cached_controller_rejects_conflicting_framing(controller, controller_kwargs):
    assert Controller(**controller_kwargs) is controller
    assert Controller(**controller_kwargs, framing=SocketFraming(put_suffix="\r")) is controller
    with pytest.raises(ValueError, match="different framing"):
        Controller(**controller_kwargs, framing=SocketFraming())
    assert controller.framing.put_suffix == "\r"


@pytest.mark.parametrize("remove_trailing_chars", [True, False])
@pytest.mark.parametrize(
    "controller", [SocketFraming(get_terminators=("U",), get_trim_sequence="U")], indirect=True
)
def test_binary_exchange_receives_complete_frame(controller, remove_trailing_chars):
    request = b"\xa0\x18\x12\x83\x11U"
    response = b"\xa0\x18\x12\x83\x11U\r\n\x00U"
    with mock.patch.object(
        controller.sock, "receive", side_effect=[response[:6], response[6:8], response[8:]]
    ) as receive:
        result = controller.socket_put_and_receive(
            request, response_length=10, remove_trailing_chars=remove_trailing_chars
        )
    assert result == response
    assert controller.sock.buffer_put == [request]
    assert [call.kwargs["buffer_length"] for call in receive.call_args_list] == [10, 4, 2]
    assert list(controller.command_history) == [f"[PUT]: {request}", f"[GET]: {response}"]


def test_fixed_length_receive_leaves_next_frame_on_socket(controller):
    # Model recv's size limit using the real SocketIO adapter.
    pending = bytearray(b"\xffU\x00U\x80next")

    def recv(size):
        chunk = bytes(pending[:size])
        del pending[:size]
        return chunk

    with mock.patch("ophyd_devices.utils.socket.socket.socket") as socket_factory:
        controller.sock = SocketIO("localhost", 8080)
    raw_socket = socket_factory.return_value
    raw_socket.gettimeout.return_value = 2
    raw_socket.recv.side_effect = recv

    assert controller.socket_get(response_length=4) == b"\xffU\x00U"
    assert controller.socket_get(response_length=5) == b"\x80next"
    assert raw_socket.recv.call_args_list == [mock.call(4), mock.call(5)]


@pytest.mark.parametrize("chunks", [[b""], [b"\xffU", b""]])
def test_binary_receive_reports_early_close(controller, chunks):
    controller.sock.buffer_recv = chunks
    with pytest.raises(ConnectionError, match="10 bytes") as exc_info:
        controller.socket_get(response_length=10)
    assert list(controller.command_history) == [f"[GET-ERROR]: {exc_info.value!r}"]


def test_binary_receive_has_one_deadline(controller):
    with (
        mock.patch(
            "ophyd_devices.utils.controller.time.monotonic", side_effect=[10, 10, 10.75, 11]
        ),
        mock.patch.object(controller.sock, "receive", side_effect=[b"\xff", b"U"]) as receive,
    ):
        with pytest.raises(TimeoutError, match="10 bytes"):
            controller.socket_get(response_length=10, timeout=1)
    assert [call.kwargs["timeout"] for call in receive.call_args_list] == [1, 0.25]
    assert [call.kwargs["buffer_length"] for call in receive.call_args_list] == [10, 9]


@pytest.mark.parametrize("length", [0, -1, 1.5, True, "10"])
def test_invalid_response_length_does_not_send(controller, length):
    with pytest.raises(ValueError, match="positive integer"):
        controller.socket_put_and_receive(b"request", response_length=length)
    assert controller.sock.buffer_put == []


def test_binary_request_requires_response_length(controller):
    with pytest.raises(ValueError, match="require response_length"):
        controller.socket_put_and_receive(b"request")
    assert controller.sock.buffer_put == []


def test_text_request_can_receive_binary_response(controller):
    controller.sock.buffer_recv = [b"\xff\x00"]
    assert controller.socket_put_and_receive("read", response_length=2) == b"\xff\x00"
    assert controller.sock.buffer_put == [b"read\n"]


@pytest.mark.parametrize(
    "command,response_length,expected_command",
    [("request", None, b"request\n"), (b"request", 10, b"request")],
)
@pytest.mark.parametrize("partial_response", [[], [b"partial"]])
def test_socket_exchange_does_not_retry_receive_errors(
    controller, command, response_length, expected_command, partial_response
):
    error = TimeoutError("Receive timed out")
    with mock.patch.object(
        controller.sock, "receive", side_effect=[*partial_response, error, b"00000000\r\n"]
    ) as receive:
        with pytest.raises(ControllerCommunicationError) as exc_info:
            controller.socket_put_and_receive(command, response_length=response_length)
    receive_error = exc_info.value.__cause__
    assert isinstance(receive_error, TimeoutError)
    assert receive_error.__cause__ is error
    assert f"Received data: {b''.join(partial_response)!r}" in str(receive_error)
    assert controller.command_history[-1] == f"[GET-ERROR]: {receive_error!r}"
    assert controller.sock.buffer_put == [expected_command]
    assert receive.call_count == len(partial_response) + 1
