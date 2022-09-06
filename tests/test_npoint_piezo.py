import pytest

from ophyd_devices.npoint import NPointController, NPointAxis


class SocketMock:
    def __init__(self, sock=None):
        self.buffer_put = ""
        self.buffer_recv = ""
        self.is_open = False
        if sock is None:
            self.open()
        else:
            self.sock = sock

    def connect(self, host, port):
        print(f"connecting to {host} port {port}")
        # self.sock.create_connection((host, port))
        # self.sock.connect((host, port))

    def _put(self, msg_bytes):
        self.buffer_put = msg_bytes
        print(self.buffer_put)

    def _recv(self, buffer_length=1024):
        print(self.buffer_recv)
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


@pytest.mark.parametrize(
    "pos,msg",
    [
        (5, b"\xa2\x18\x12\x83\x11\xcd\xcc\x00\x00U"),
        (0, b"\xa2\x18\x12\x83\x11\x00\x00\x00\x00U"),
        (-5, b"\xa2\x18\x12\x83\x1133\xff\xffU"),
    ],
)
def test_axis_put(pos, msg):
    controller = NPointController(SocketMock())
    npointx = NPointAxis(controller, 0, "nx")
    controller.on()
    npointx.set(pos)
    assert npointx.controller.socket.buffer_put == msg


@pytest.mark.parametrize(
    "pos, msg_in, msg_out",
    [
        (5.0, b"\xa04\x13\x83\x11U", b"\xa0\x34\x13\x83\x11\xcd\xcc\x00\x00U"),
        (0, b"\xa04\x13\x83\x11U", b"\xa0\x34\x13\x83\x11\x00\x00\x00\x00U"),
        (-5, b"\xa04\x13\x83\x11U", b"\xa0\x34\x13\x83\x1133\xff\xffU"),
    ],
)
def test_axis_get_out(pos, msg_in, msg_out):
    controller = NPointController(SocketMock())
    npointx = NPointAxis(controller, 0, "nx")
    controller.on()
    npointx.controller.socket.buffer_recv = msg_out
    assert pytest.approx(npointx.get(), rel=0.01) == pos
    # assert controller.socket.buffer_put == msg_in


@pytest.mark.parametrize(
    "axis, msg_in, msg_out",
    [
        (0, b"\xa04\x13\x83\x11U", b"\xa0\x34\x13\x83\x11\xcd\xcc\x00\x00U"),
        (1, b"\xa04#\x83\x11U", b"\xa0\x34\x13\x83\x11\x00\x00\x00\x00U"),
        (2, b"\xa043\x83\x11U", b"\xa0\x34\x13\x83\x1133\xff\xffU"),
    ],
)
def test_axis_get_in(axis, msg_in, msg_out):
    controller = NPointController(SocketMock())
    npointx = NPointAxis(controller, 0, "nx")
    controller.on()
    controller.socket.buffer_recv = msg_out
    controller._get_current_pos(axis)
    assert controller.socket.buffer_put == msg_in


def test_axis_out_of_range():
    controller = NPointController(SocketMock())
    with pytest.raises(ValueError):
        npointx = NPointAxis(controller, 3, "nx")


def test_get_axis_out_of_range():
    controller = NPointController(SocketMock())
    with pytest.raises(ValueError):
        controller._get_current_pos(3)


def test_set_axis_out_of_range():
    controller = NPointController(SocketMock())
    with pytest.raises(ValueError):
        controller._set_target_pos(3, 5)


@pytest.mark.parametrize(
    "in_buffer, byteorder, signed, val",
    [
        (["0x0", "0x0", "0xcc", "0xcd"], "big", True, 52429),
        (["0xcd", "0xcc", "0x0", "0x0"], "little", True, 52429),
        (["cd", "cc", "00", "00"], "little", True, 52429),
    ],
)
def test_hex_list_to_int(in_buffer, byteorder, signed, val):
    assert NPointController._hex_list_to_int(in_buffer, byteorder=byteorder, signed=signed) == val


@pytest.mark.parametrize(
    "axis, msg_in, msg_out",
    [
        (0, b"\xa0x\x10\x83\x11U", b"\xa0\x78\x13\x83\x11\x64\x00\x00\x00U"),
        (1, b"\xa0x \x83\x11U", b"\xa0\x78\x13\x83\x11\x64\x00\x00\x00U"),
        (2, b"\xa0x0\x83\x11U", b"\xa0\x78\x13\x83\x11\x64\x00\x00\x00U"),
    ],
)
def test_get_range(axis, msg_in, msg_out):
    controller = NPointController(SocketMock())
    npointx = NPointAxis(controller, 0, "nx")
    controller.on()
    controller.socket.buffer_recv = msg_out
    val = controller._get_range(axis)
    assert controller.socket.buffer_put == msg_in and val == 100
