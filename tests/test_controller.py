from unittest import mock

from ophyd_devices.utils.controller import Controller


def test_controller_off(dm_with_devices):
    controller = Controller(
        socket_cls=mock.MagicMock(),
        socket_host="dummy",
        socket_port=123,
        device_manager=dm_with_devices,
    )
    controller.on()
    with mock.patch.object(controller.device_manager, "config_helper") as mock_config_helper:
        with mock.patch.object(controller.sock, "close") as mock_close:
            controller.off()
            assert controller.sock is None
            assert controller.connected is False
            mock_close.assert_called_once()

            # make sure it is indempotent
            controller.off()
    controller._reset_controller()


def test_controller_on(dm_with_devices):
    socket_cls = mock.MagicMock()
    Controller._controller_instances = {}
    controller = Controller(
        socket_cls=socket_cls, socket_host="dummy", socket_port=123, device_manager=dm_with_devices
    )
    controller.on()
    assert controller.sock is not None
    assert controller.connected is True
    socket_cls().open.assert_called_once()

    # make sure it is indempotent
    controller.on()
    socket_cls().open.assert_called_once()
    controller._reset_controller()


def test_controller_with_multiple_axes(dm_with_devices):
    """Test that turning the controller on and off enables/disables all axes attached to it."""
    socket_cls = mock.MagicMock()
    Controller._controller_instances = {}
    Controller._axes_per_controller = 2
    controller = Controller(
        socket_cls=socket_cls, socket_host="dummy", socket_port=123, device_manager=dm_with_devices
    )
    with mock.patch.object(controller.device_manager, "config_helper") as mock_config_helper:
        # Disable samx, samy first
        dm_with_devices.devices.get("samx").enabled = False
        dm_with_devices.devices.get("samy").enabled = False
        # Set axes on the controller
        controller.set_axis(axis=dm_with_devices.devices["samx"], axis_nr=0)
        controller.set_axis(axis=dm_with_devices.devices["samy"], axis_nr=1)
        # Turn the controller on, should turn the controller on, but not enable the axes
        controller.on()
        assert dm_with_devices.devices.get("samx").enabled is False
        assert dm_with_devices.devices.get("samy").enabled is False
        assert controller.connected is True
        controller.set_all_devices_enabled(True)
        assert dm_with_devices.devices.get("samx").enabled is True
        assert dm_with_devices.devices.get("samy").enabled is True
        # Disable one axis after another, the last one should turn the controller off
        controller.set_device_enabled("samx", False)
        assert controller.connected is True
        assert dm_with_devices.devices.get("samx").enabled is False
        assert dm_with_devices.devices.get("samy").enabled is True
        controller.set_device_enabled("samy", False)
        assert dm_with_devices.devices.get("samy").enabled is False
        # Enabling one axis should turn the controller back on
        assert controller.connected is False
        controller.set_device_enabled("samx", True)
        assert controller.connected is True
