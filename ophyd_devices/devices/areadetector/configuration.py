"""
Camera-local AD signal definitions with monitored configuration and dimension readbacks.
"""

from copy import copy
from typing import Any, TypeVar

from ophyd import Device, DynamicDeviceComponent, Kind
from ophyd.signal import EpicsSignalBase

DeviceT = TypeVar("DeviceT", bound=Device)

# Configuration used by camera staging, live transitions, file writing and ROI capture.
# Commands (Acquire, Capture, TSRead, TSAcquire) deliberately remain outside this set.
MONITORED_SETTINGS = frozenset(
    {
        "width",
        "height",
        "depth",
        "acquire_time",
        "acquire_period",
        "num_images",
        "image_mode",
        "trigger_mode",
        "array_callbacks",
        "enable",
        "nd_array_port",
        "port_name",
        "file_path",
        "file_name",
        "file_template",
        "file_write_mode",
        "auto_increment",
        "auto_save",
        "lazy_open",
        "num_capture",
        "file_path_exists",
        "write_status",
        "write_message",
        "ts_acquire_mode",
        "ts_read_mode",
        "ts_num_points",
        "min_x",
        "min_y",
        "x",
        "y",
        "compute_statistics",
        "compute_centroid",
    }
)


def configure_ad_signals(cls: type[DeviceT], *, configuration_kinds: bool = False) -> type[DeviceT]:
    """
    Copy AD component definitions and monitor the configuration this integration uses.

    Work only with descriptors: no signals are instantiated and no connections are
    opened. Copy nested definitions so shared AD driver/plugin classes are unchanged.
    Enable monitoring for acquisition settings and image dimensions used in cached
    readiness checks. This includes HDF5 width/height/depth readbacks for priming.

    Args:
        cls (type[DeviceT]): Camera-local device or plugin class to copy recursively.
        configuration_kinds (bool): Move normal/hinted signals to config and omit
            configuration-name bookkeeping when True. Preserve component kinds
            when False. Existing omitted components remain omitted.

    Returns:
        type[DeviceT]: Derived class containing independent component descriptors
            with the requested kinds and monitor settings. The shared input class
            is unchanged, and no signals are instantiated by this function.
    """
    attributes: dict[str, Any] = {"__module__": cls.__module__, "__doc__": cls.__doc__}
    if configuration_kinds:
        attributes["_default_configuration_attrs"] = None
    for name, original in cls._sig_attrs.items():
        component = copy(original)
        if configuration_kinds:
            if name == "configuration_names":
                component.kind = Kind.omitted
            elif component.kind & Kind.normal:
                component.kind = Kind.config
        if issubclass(component.cls, Device):
            component.cls = configure_ad_signals(
                component.cls, configuration_kinds=configuration_kinds
            )
            if isinstance(component, DynamicDeviceComponent):
                component.components = dict(component.cls._sig_attrs)
                if configuration_kinds:
                    component.default_configuration_attrs = None
        elif name in MONITORED_SETTINGS and issubclass(component.cls, EpicsSignalBase):
            component.kwargs = {**component.kwargs, "auto_monitor": True}
        attributes[name] = component
    return type(cls.__name__, (cls,), attributes)
