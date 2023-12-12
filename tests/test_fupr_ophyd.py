from unittest import mock

import pytest
from utils import SocketMock

from ophyd_devices.galil.fupr_ophyd import FuprGalilController, FuprGalilMotor


@pytest.fixture
def fsamroy():
    FuprGalilController._reset_controller()
    fsamroy_motor = FuprGalilMotor(
        "A", name="fsamroy", host="mpc2680.psi.ch", port=8081, socket_cls=SocketMock
    )
    fsamroy_motor.controller.on()
    assert isinstance(fsamroy_motor.controller, FuprGalilController)
    yield fsamroy_motor
    fsamroy_motor.controller.off()
    fsamroy_motor.controller._reset_controller()


@pytest.mark.parametrize(
    "pos,msg_received,msg_put,sign",
    [
        (-0.5, b" -12800\n\r", [b"TPA\r", b"MG_BGA\r", b"TPA\r"], 1),
        (-0.5, b" 12800\n\r", [b"TPA\r", b"MG_BGA\r", b"TPA\r"], -1),
    ],
)
def test_axis_get(fsamroy, pos, msg_received, msg_put, sign):
    fsamroy.sign = sign
    fsamroy.device_manager = mock.MagicMock()
    fsamroy.controller.sock.flush_buffer()
    fsamroy.controller.sock.buffer_recv = msg_received
    val = fsamroy.read()
    assert val["fsamroy"]["value"] == pos
    assert fsamroy.readback.get() == pos
    assert fsamroy.controller.sock.buffer_put == msg_put


@pytest.mark.parametrize(
    "target_pos,socket_put_messages,socket_get_messages",
    [
        (
            0,
            [b"MG axisref\r", b"PAA=0\r", b"PAA=0\r", b"BGA\r"],
            [b"1.00", b"-1", b":", b":", b":", b":", b"-1"],
        )
    ],
)
def test_axis_put(fsamroy, target_pos, socket_put_messages, socket_get_messages):
    fsamroy.controller.sock.flush_buffer()
    fsamroy.controller.sock.buffer_recv = socket_get_messages
    fsamroy.user_setpoint.put(target_pos)
    assert fsamroy.controller.sock.buffer_put == socket_put_messages


def test_drive_axis_to_limit(fsamroy):
    fsamroy.controller.sock.flush_buffer()
    with pytest.raises(NotImplementedError):
        fsamroy.controller.drive_axis_to_limit(0, "forward")
