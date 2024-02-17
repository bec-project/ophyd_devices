from unittest import mock

import pytest
from utils import SocketMock

from ophyd_devices.rt_lamni import RtFlomniController, RtFlomniMotor
from ophyd_devices.rt_lamni.rt_ophyd import RtError


@pytest.fixture()
def rt_flomni():
    rt_flomni = RtFlomniController(
        name="rt_flomni", socket_cls=SocketMock, socket_host="localhost", socket_port=8081
    )
    with mock.patch.object(rt_flomni, "get_device_manager"):
        with mock.patch.object(rt_flomni, "sock"):
            rtx = mock.MagicMock(spec=RtFlomniMotor)
            rtx.name = "rtx"
            rty = mock.MagicMock(spec=RtFlomniMotor)
            rty.name = "rty"
            rtz = mock.MagicMock(spec=RtFlomniMotor)
            rtz.name = "rtz"
            rt_flomni.set_axis(rtx, 0)
            rt_flomni.set_axis(rty, 1)
            rt_flomni.set_axis(rtz, 2)
            yield rt_flomni


def test_rt_flomni_move_to_zero(rt_flomni):
    rt_flomni.move_to_zero()
    assert rt_flomni.sock.mock_calls == [
        mock.call.put(b"pa0,0\n"),
        mock.call.put(b"pa1,0\n"),
        mock.call.put(b"pa2,0\n"),
    ]


@pytest.mark.parametrize("return_value,is_running", [(b"1.00\n", False), (b"0.00\n", True)])
def test_rt_flomni_feedback_is_running(rt_flomni, return_value, is_running):
    rt_flomni.sock.receive.return_value = return_value
    assert rt_flomni.feedback_is_running() == is_running
    assert mock.call.put(b"l2\n") in rt_flomni.sock.mock_calls


def test_feedback_enable_with_reset(rt_flomni):

    device_manager = rt_flomni.get_device_manager()
    device_manager.devices.fsamx.user_parameter.get.return_value = 0.05
    device_manager.devices.fsamx.obj.readback.get.return_value = 0.05

    with mock.patch.object(rt_flomni, "feedback_is_running", return_value=True):
        with mock.patch.object(rt_flomni, "laser_tracker_on") as laser_tracker_on:
            with mock.patch.object(rt_flomni, "pid_y", return_value=0.05):
                with mock.patch.object(
                    rt_flomni, "slew_rate_limiters_on_target", return_value=True
                ) as slew_rate_limiters_on_target:

                    rt_flomni.feedback_enable_with_reset()
                    laser_tracker_on.assert_called_once()


def test_move_samx_to_scan_region(rt_flomni):
    device_manager = rt_flomni.get_device_manager()
    device_manager.devices.rtx.user_parameter.get.return_value = 1
    rt_flomni.move_samx_to_scan_region(20, 2)
    assert mock.call(b"v0\n") not in rt_flomni.sock.put.mock_calls
    assert mock.call(b"v1\n") in rt_flomni.sock.put.mock_calls


def test_feedback_enable_without_reset(rt_flomni):
    with mock.patch.object(rt_flomni, "set_device_enabled") as set_device_enabled:
        with mock.patch.object(rt_flomni, "feedback_is_running", return_value=True):
            with mock.patch.object(rt_flomni, "laser_tracker_on") as laser_tracker_on:
                rt_flomni.feedback_enable_without_reset()
                laser_tracker_on.assert_called_once()
                assert mock.call(b"l3\n") in rt_flomni.sock.put.mock_calls
                assert mock.call("fsamx", False) in set_device_enabled.mock_calls
                assert mock.call("fsamy", False) in set_device_enabled.mock_calls
                assert mock.call("foptx", False) in set_device_enabled.mock_calls
                assert mock.call("fopty", False) in set_device_enabled.mock_calls


def test_feedback_enable_without_reset_raises(rt_flomni):
    with mock.patch.object(rt_flomni, "feedback_is_running", return_value=False):
        with mock.patch.object(rt_flomni, "laser_tracker_on") as laser_tracker_on:
            with pytest.raises(RtError):
                rt_flomni.feedback_enable_without_reset()
                laser_tracker_on.assert_called_once()
                assert mock.call(b"l3\n") in rt_flomni.sock.put.mock_calls
