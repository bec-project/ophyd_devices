"""
Explicit AD configuration metadata and independent acquisition monitoring.
"""

from collections.abc import Collection
from copy import copy
from typing import Any, TypeVar

from ophyd import Device, DynamicDeviceComponent, Kind
from ophyd.signal import EpicsSignalBase

DeviceT = TypeVar("DeviceT", bound=Device)

# Paths are relative to the camera controller, not arbitrary leaf names shared by
# camera settings, image dimensions and measured Stats results.
CAMERA_CONFIGURATION_SIGNALS = frozenset(
    {
        "acquire_time",
        "acquire_period",
        "array_callbacks",
        "bin_x",
        "bin_y",
        "color_mode",
        "data_type",
        "frame_type",
        "gain",
        "image_mode",
        "min_x",
        "min_y",
        "num_exposures",
        "num_images",
        "reverse.reverse_x",
        "reverse.reverse_y",
        "shutter_close_delay",
        "shutter_mode",
        "shutter_open_delay",
        "size.size_x",
        "size.size_y",
        "temperature",
        "trigger_mode",
        "nd_attributes_file",
    }
)
SIM_CONFIGURATION_SIGNALS = CAMERA_CONFIGURATION_SIGNALS | {
    "gain_rgb.gain_red",
    "gain_rgb.gain_green",
    "gain_rgb.gain_blue",
    "gain_xy.gain_x",
    "gain_xy.gain_y",
    "noise",
    "peak_num.peak_num_x",
    "peak_num.peak_num_y",
    "peak_start.peak_start_x",
    "peak_start.peak_start_y",
    "peak_step.peak_step_x",
    "peak_step.peak_step_y",
    "peak_variation",
    "peak_width.peak_width_x",
    "peak_width.peak_width_y",
    "sim_mode",
}
VIMBA_CONFIGURATION_SIGNALS = CAMERA_CONFIGURATION_SIGNALS | {
    "frame_rate",
    "frame_rate_enable",
    "trigger_source",
    "trigger_overlap",
    "exposure_mode",
    "exposure_auto",
    "gain_auto",
    "pixel_format",
    "time_stamp_mode",
    "unique_id_mode",
    "convert_pixel_format",
}

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

# Status inputs remain monitored even though none is configuration metadata.
MONITORED_STATUS_SIGNALS = frozenset(
    {
        "acquire",
        "array_counter",
        "capture",
        "num_captured",
        "write_file",
        "ts_acquire_status",
        "ts_array_counter",
        "ts_current_index",
    }
)


def configure_ad_signals(
    cls: type[DeviceT], *, configuration_signals: Collection[str] = ()
) -> type[DeviceT]:
    """
    Copy AD definitions with an explicit selection of EPICS configuration fields.

    Work only with descriptors: no signals are instantiated and no connections are
    opened. Copy nested definitions so shared AD driver/plugin classes are unchanged.
    Selected dotted paths are configuration; other EPICS fields and AD bookkeeping
    are omitted. Existing local soft configuration and BEC result streams retain
    their kinds. Parent devices expose selected descendants only when that branch
    was not explicitly omitted. Inherited AD configuration lists are reset so they
    cannot reintroduce runtime signals or hide selected nested settings.

    Monitoring is independent of metadata kind. Omitted acquisition counters, state
    and image dimensions still monitor IOC updates used by readiness/completion.

    Args:
        cls (type[DeviceT]): Camera-local device or plugin class to copy recursively.
        configuration_signals (Collection[str]): Genuine EPICS setting paths relative
            to cls, such as "cam.acquire_time". Defaults to no EPICS configuration.
            ROI components keep their local configuration while omitting backend PVs.

    Returns:
        type[DeviceT]: Derived class containing independent component descriptors
            with the requested kinds and monitor settings. The shared input class
            is unchanged, and no signals are instantiated by this function.
    """
    attributes: dict[str, Any] = {"__module__": cls.__module__, "__doc__": cls.__doc__}
    attributes["_default_configuration_attrs"] = None
    attributes["_default_read_attrs"] = None
    selected = frozenset(configuration_signals)
    for name, original in cls._sig_attrs.items():
        component = copy(original)
        if issubclass(component.cls, Device):
            prefix = f"{name}."
            component.cls = configure_ad_signals(
                component.cls,
                configuration_signals={p[len(prefix) :] for p in selected if p.startswith(prefix)},
            )
            if component.kind & Kind.normal:
                component.kind = (
                    Kind.config
                    if any(c.kind & Kind.config for c in component.cls._sig_attrs.values())
                    else Kind.omitted
                )
            if isinstance(component, DynamicDeviceComponent):
                component.components = dict(component.cls._sig_attrs)
                component.default_configuration_attrs = None
        elif issubclass(component.cls, EpicsSignalBase):
            component.kind = Kind.config if name in selected else Kind.omitted
            if name in MONITORED_SETTINGS or name in MONITORED_STATUS_SIGNALS:
                component.kwargs = {**component.kwargs, "auto_monitor": True}
        elif name in ("configuration_names", "asyn_pipeline_config"):
            component.kind = Kind.omitted
        attributes[name] = component
    return type(cls.__name__, (cls,), attributes)
