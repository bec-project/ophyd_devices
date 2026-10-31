"""Pure native value normalization shared by handlers and compatibility helpers."""

from typing import Any


def convert_value(device: Any, value: Any) -> Any:
    """Preserve integral-float enum conversion without constructing a provider."""
    choices = getattr(device, "enum_strs", None)
    if choices and isinstance(value, float):
        if not value.is_integer():
            raise ValueError(
                f"Cannot convert float {value} to enum index for {device.name}. Value must be an integer to select one of the enum strings: {choices}."
            )
        return int(value)
    return value
