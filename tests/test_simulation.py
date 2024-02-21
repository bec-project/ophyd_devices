from ophyd_devices.utils.bec_device_base import BECDeviceBase, BECDevice


def test_BECDeviceBase():
    # Test the BECDeviceBase class
    test = BECDeviceBase(name="test")
    assert isinstance(test, BECDevice)
    assert test.connected is True
