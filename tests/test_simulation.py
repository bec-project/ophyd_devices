from ophyd_devices.utils.bec_device_base import BECDeviceBase, BECDevice

from ophyd import Device, Signal


def test_BECDeviceBase():
    # Test the BECDeviceBase class
    bec_device_base = BECDeviceBase(name="test")
    assert isinstance(bec_device_base, BECDevice)
    assert bec_device_base.connected is True
    signal = Signal(name="signal")
    assert isinstance(signal, BECDevice)
    device = Device(name="device")
    assert isinstance(device, BECDevice)
