from unittest import mock

from ophyd_devices.utils.controller import Controller


def test_controller_off():
    controller = Controller(socket_cls=mock.MagicMock(), socket_host="dummy", socket_port=123)
    controller.on()
    with mock.patch.object(controller.sock, "close") as mock_close:
        controller.off()
        assert controller.sock is None
        assert controller.connected is False
        mock_close.assert_called_once()

        # make sure it is indempotent
        controller.off()
    controller._reset_controller()


def test_controller_on():
    socket_cls = mock.MagicMock()
    Controller._controller_instances = {}
    controller = Controller(socket_cls=socket_cls, socket_host="dummy", socket_port=123)
    controller.on()
    assert controller.sock is not None
    assert controller.connected is True
    socket_cls().open.assert_called_once()

    # make sure it is indempotent
    controller.on()
    socket_cls().open.assert_called_once()
    controller._reset_controller()
