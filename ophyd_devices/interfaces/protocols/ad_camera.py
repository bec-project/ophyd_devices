"""Structural camera interface consumed by shared AD operations."""

from collections.abc import Iterable
from enum import Enum
from threading import Event
from typing import Any, Protocol

from bec_lib.messages import ScanStatusMessage
from ophyd import Device, Signal
from ophyd.status import StatusBase

from ophyd_devices.devices.areadetector.cam import CamBase
from ophyd_devices.devices.areadetector.plugins import HDF5Plugin_V35, ImagePlugin_V35
from ophyd_devices.utils.bec_signals import FileEventSignal
from ophyd_devices.utils.psi_device_base_utils import FileHandler


class ADCamera(Protocol):
    """Required signals and ordinary device services, independent of concrete camera classes.

    Camera implementations satisfy this interface structurally; they do not need
    to inherit it or be registered in a list of supported camera types.
    """

    @property
    def live_enabled(self) -> Signal: ...

    @property
    def live_follows_scan_timing(self) -> Signal: ...

    @property
    def use_scan_timing(self) -> Signal: ...

    @property
    def acquisition_source(self) -> Signal: ...

    @property
    def acquisition_mode(self) -> Signal: ...

    @property
    def save_frame_data(self) -> Signal: ...

    hdf5: HDF5Plugin_V35 | None
    file_event: FileEventSignal
    hdf5_path_mapping: dict[str, str] | None
    file_utils: FileHandler

    device_manager: Any
    name: str
    _poll_stop: Event
    exposure: float
    period: float
    frames_per_trigger: int
    readout_priority: str
    detector_readout_time: float
    async_frame_limit: int | None
    internal_trigger_mode: Enum
    external_trigger_mode: Enum | None
    stage_sigs: dict[Any, Any]
    session_id: str
    _frame_origin: int
    io_timeout: float
    acquisition_timeout: float
    destroyed: bool
    stopped: bool

    @property
    def cam(self) -> CamBase:
        """Driver-specific AD camera PVs."""
        ...

    @property
    def image(self) -> ImagePlugin_V35 | None:
        """Optional image plugin used for Redis preview reads."""
        ...

    @property
    def _scan_message(self) -> ScanStatusMessage:
        """Validated current scan information."""
        ...

    def walk_subdevices(self, *, include_lazy: bool = False) -> Iterable[tuple[str, Device]]:
        """Discover child devices, including nested ROI processing instances."""
        ...

    def cancel_on_stop(self, status: StatusBase) -> None:
        """Register unfinished acquisition work for interruption."""
        ...

    def stop(self, *, success: bool = False) -> None:
        """Stop input and cancel registered statuses through the normal device hook."""
        ...

    def check_cancelled(self) -> None:
        """Raise when the device has been interrupted."""
        ...

    def _stop_stoppable_status_objects(self) -> None:
        """Cancel registered acquisition work before stopping hardware."""
        ...

    def _redis_preview_due(self) -> bool:
        """Return whether the optional Redis preview interval has elapsed."""
        ...

    def _read_preview_signal(self, signal: Any) -> Any:
        """Read one preview signal with a bounded timeout and cancellation check."""
        ...

    def _configure_preview_transports(self, paths: list[str]) -> None:
        """Describe IOC streams and optional Redis transport without socket setup."""
        ...
