import socket

from ophyd_devices.utils.socket import SocketIO


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


def test_close():
    socketio = SocketIO("localhost", 8080)
    socketio.close()
    assert socketio.sock == None
    assert socketio.is_open == False
