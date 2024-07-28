"""Module for ophyd_devices specific errors. """


class DeviceStopError(Exception):
    """Error to raise if the device is stopped."""


class DeviceTimeoutError(Exception):
    """Error to raise if the device times out."""
