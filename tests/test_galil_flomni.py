from unittest import mock

import pytest
from utils import SocketMock

from ophyd_devices.galil.fgalil_ophyd import FlomniGalilController, FlomniGalilMotor


@pytest.fixture(scope="function")
def leyey():
    FlomniGalilController._reset_controller()
    leyey_motor = FlomniGalilMotor(
        "H", name="leyey", host="mpc2680.psi.ch", port=8081, socket_cls=SocketMock
    )
    leyey_motor.controller.on()
    yield leyey_motor
    leyey_motor.controller.off()
    leyey_motor.controller._reset_controller()


@pytest.fixture(scope="function")
def leyex():
    FlomniGalilController._reset_controller()
    leyex_motor = FlomniGalilMotor(
        "H", name="leyey", host="mpc2680.psi.ch", port=8081, socket_cls=SocketMock
    )
    leyex_motor.controller.on()
    yield leyex_motor
    leyex_motor.controller.off()
    leyex_motor.controller._reset_controller()


@pytest.mark.parametrize("pos,msg,sign", [(1, b" -12800\n\r", 1), (-1, b" -12800\n\r", -1)])
def test_axis_get(leyey, pos, msg, sign):
    leyey.sign = sign
    leyey.controller.sock.flush_buffer()
    leyey.controller.sock.buffer_recv = msg
    val = leyey.read()
    assert val["leyey"]["value"] == pos
    assert leyey.readback.get() == pos


@pytest.mark.parametrize(
    "target_pos,socket_put_messages,socket_get_messages",
    [
        (
            0,
            [
                b"MG allaxref\r",
                b"MG_XQ0\r",
                b"naxis=7\r",
                b"ntarget=0.000\r",
                b"movereq=1\r",
                b"XQ#NEWPAR\r",
                b"MG_XQ0\r",
            ],
            [b"1.00", b"-1", b":", b":", b":", b":", b"-1"],
        )
    ],
)
def test_axis_put(leyey, target_pos, socket_put_messages, socket_get_messages):
    leyey.controller.sock.flush_buffer()
    leyey.controller.sock.buffer_recv = socket_get_messages
    leyey.user_setpoint.put(target_pos)
    assert leyey.controller.sock.buffer_put == socket_put_messages


@pytest.mark.parametrize(
    "axis_nr,direction,socket_put_messages,socket_get_messages",
    [
        (
            0,
            "forward",
            [
                b"naxis=0\r",
                b"ndir=1\r",
                b"XQ#NEWPAR\r",
                b"XQ#FES\r",
                b"MG_XQ0\r",
                b"MG _MOA\r",
                b"MG_XQ0\r",
                b"MG _MOA\r",
                b"MG _LRA, _LFA\r",
            ],
            [b":", b":", b":", b":", b"0", b"0", b"-1", b"-1", b"1.000 0.000"],
        ),
        (
            1,
            "reverse",
            [
                b"naxis=1\r",
                b"ndir=-1\r",
                b"XQ#NEWPAR\r",
                b"XQ#FES\r",
                b"MG_XQ0\r",
                b"MG _MOB\r",
                b"MG_XQ0\r",
                b"MG _MOB\r",
                b"MG _LRB, _LFB\r",
            ],
            [b":", b":", b":", b":", b"0", b"0", b"-1", b"-1", b"0.000 1.000"],
        ),
    ],
)
def test_drive_axis_to_limit(leyex, axis_nr, direction, socket_put_messages, socket_get_messages):
    leyex.controller.sock.flush_buffer()
    leyex.controller.sock.buffer_recv = socket_get_messages
    leyex.controller.drive_axis_to_limit(axis_nr, direction)
    assert leyex.controller.sock.buffer_put == socket_put_messages


@pytest.mark.parametrize(
    "axis_nr,socket_put_messages,socket_get_messages",
    [
        (
            0,
            [
                b"naxis=0\r",
                b"XQ#NEWPAR\r",
                b"XQ#FRM\r",
                b"MG_XQ0\r",
                b"MG _MOA\r",
                b"MG_XQ0\r",
                b"MG _MOA\r",
                b"MG axisref[0]\r",
            ],
            [b":", b":", b":", b"0", b"0", b"-1", b"-1", b"1.00"],
        ),
        (
            1,
            [
                b"naxis=1\r",
                b"XQ#NEWPAR\r",
                b"XQ#FRM\r",
                b"MG_XQ0\r",
                b"MG _MOB\r",
                b"MG_XQ0\r",
                b"MG _MOB\r",
                b"MG axisref[1]\r",
            ],
            [b":", b":", b":", b"0", b"0", b"-1", b"-1", b"1.00"],
        ),
    ],
)
def test_find_reference(leyex, axis_nr, socket_put_messages, socket_get_messages):
    leyex.controller.sock.flush_buffer()
    leyex.controller.sock.buffer_recv = socket_get_messages
    leyex.controller.find_reference(axis_nr)
    assert leyex.controller.sock.buffer_put == socket_put_messages


@pytest.mark.parametrize(
    "axis_Id,socket_put_messages,socket_get_messages,triggered",
    [
        ("A", [b"MG @IN[14]\r"], [b" 1.0000\n"], True),
        ("B", [b"MG @IN[14]\r"], [b" 0.0000\n"], False),
    ],
)
def test_fosaz_light_curtain_is_triggered(
    axis_Id, socket_put_messages, socket_get_messages, triggered
):
    """test that the light curtain is triggered"""
    fosaz = FlomniGalilMotor(
        axis_Id, name="fosaz", host="mpc2680.psi.ch", port=8081, socket_cls=SocketMock
    )
    fosaz.controller.on()
    fosaz.controller.sock.flush_buffer()
    fosaz.controller.sock.buffer_recv = socket_get_messages
    assert fosaz.controller.fosaz_light_curtain_is_triggered() == triggered
    assert fosaz.controller.sock.buffer_put == socket_put_messages
    fosaz.controller.off()
    fosaz.controller._reset_controller()
