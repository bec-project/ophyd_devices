"""BEC-facing providers; native HAL details stay in this package."""

from .provider import OphydProvider


def convert_value(device, value):
    """Compatibility entry point for the former DeviceServer conversion helper."""
    return OphydProvider().wrap(device).convert_value(value)
