"""Camera settings and live previews using the ordinary PSI device lifecycle."""

from __future__ import annotations

from enum import StrEnum
from math import isfinite
from threading import Event, Lock, Thread, current_thread
from time import monotonic
from typing import TYPE_CHECKING, Any, ClassVar

from bec_lib import messages
from bec_lib.endpoints import MessageEndpoints
from bec_lib.logger import bec_logger
from bec_lib.messages import ScanStatusMessage
from bec_lib.utils.rpc_utils import rgetattr
from ophyd import Component, Kind, Signal, Staged

from ophyd_devices.interfaces.base_classes.psi_device_base import DeviceStoppedError, PSIDeviceBase
from ophyd_devices.utils.bec_roi_signals.roi_processing import ROIProcessing
from ophyd_devices.utils.bec_signals import FileEventSignal, PreviewSignal
from ophyd_devices.utils.psi_device_base_utils import StatusBase

if TYPE_CHECKING:
    from bec_lib.devicemanager import DeviceManagerBase, ScanInfo


class AcquisitionSource(StrEnum):
    """
    Source of independent acquisition for an async camera.
    """

    EXTERNAL = "external"
    INTERNAL = "internal"


class AcquisitionMode(StrEnum):
    """
    Length of an async camera acquisition, independently of its trigger source.
    """

    FIXED = "fixed"
    CONTINUOUS = "continuous"


class CameraBase(PSIDeviceBase):
    """
    Camera settings, public live control and an optional Redis preview timer.

    Stage, trigger, complete, unstage, stop and destroy are inherited unchanged
    from PSIDeviceBase. Concrete cameras implement the ordinary on_* hooks.

    Readout priority selects the acquisition lifecycle: baseline acquires once at
    pre_scan, monitored acquires on BEC triggers, async runs from stage until complete,
    and on_request retains live behavior. acquisition_source selects the internal
    clock or external pulses for async acquisition. acquisition_mode selects fixed
    or continuous acquisition independently of the source. Fixed async acquisitions
    use num_points * frames_per_trigger from scan settings, or controller NumImages
    when use_scan_timing is False. Continuous input runs until complete.
    Independent acquisition starts at stage; completion waits for fixed input or
    stops continuous input. Software bursts use frames_per_trigger. Camera and
    plugin counters track the frames received.
    With selected ROI outputs, async_frame_limit bounds total samples per scan.
    None uses the available IOC waveform capacity; capture never wraps.
    These settings change local configuration; hardware is configured in the hooks.
    """

    USER_ACCESS: ClassVar[list[str]] = [
        *getattr(PSIDeviceBase, "USER_ACCESS", []),
        "start_live",
        "stop_live",
    ]

    live_enabled = Component(Signal, value=True, kind=Kind.config)
    live_follows_scan_timing = Component(Signal, value=True, kind=Kind.config)
    use_scan_timing = Component(Signal, value=True, kind=Kind.config)
    # Baseline/monitored hooks always use finite internal bursts.
    acquisition_source = Component(Signal, value=AcquisitionSource.INTERNAL.value, kind=Kind.config)
    acquisition_mode = Component(Signal, value=AcquisitionMode.CONTINUOUS.value, kind=Kind.config)
    save_frame_data = Component(Signal, value=True, kind=Kind.config)
    preview = Component(PreviewSignal, ndim=2)
    file_event = Component(FileEventSignal)

    def __init__(
        self,
        prefix: str = "",
        *,
        name: str,
        device_manager: DeviceManagerBase | None = None,
        scan_info: ScanInfo | None = None,
        live_enabled: bool = True,
        live_follows_scan_timing: bool = True,
        acquisition_source: AcquisitionSource | str = AcquisitionSource.INTERNAL,
        acquisition_mode: AcquisitionMode | str = AcquisitionMode.CONTINUOUS,
        save_frame_data: bool = True,
        save_roi_data: bool = True,
        redis_update_frequency: float = 0,
        preview_transports: dict[str, list[Any]] | None = None,
        detector_readout_time: float = 0,
        async_frame_limit: int | None = None,
        io_timeout: float = 2,
        acquisition_timeout: float = 30,
        **kwargs: Any,
    ) -> None:
        # Child ROI constructors read this before BEC publishes signal metadata.
        self._save_roi_data = bool(save_roi_data)
        acquisition_source = AcquisitionSource(acquisition_source)
        acquisition_mode = AcquisitionMode(acquisition_mode)
        if not isfinite(redis_update_frequency) or redis_update_frequency < 0:
            raise ValueError("redis_update_frequency must be finite and nonnegative")
        if any(not isfinite(t) or t <= 0 for t in (io_timeout, acquisition_timeout)):
            raise ValueError("Camera timeouts must be finite and positive")
        self.io_timeout, self.acquisition_timeout = io_timeout, acquisition_timeout
        self._redis_update_frequency = float(redis_update_frequency)
        self._preview_transports = preview_transports or {}
        self._preview_paths: list[str] = []
        self._next_redis_preview = 0.0
        self.exposure, self.period, self.frames_per_trigger = 0.0, 0.0, 1
        self.detector_readout_time = detector_readout_time
        self.async_frame_limit = async_frame_limit
        self.session_id = ""
        self._live_active = self._live_ready = False
        self._live_shutdown_lock = Lock()
        self._live_shutdown: StatusBase | None = None
        self._updating_live = False
        self._poll_stop = Event()
        self._poll_thread: Thread | None = None

        super().__init__(
            prefix, name=name, device_manager=device_manager, scan_info=scan_info, **kwargs
        )
        self._configure_preview_transports(["preview", *self._preview_transports])
        self.live_follows_scan_timing.put(live_follows_scan_timing)
        self.acquisition_source.put(acquisition_source.value)
        self.acquisition_mode.put(acquisition_mode.value)
        self.save_frame_data.put(save_frame_data)
        self.live_enabled.put(live_enabled)
        self._live_subscription = self.live_enabled.subscribe(self._live_changed, run=False)

    ########################################
    #           Scan information           #
    ########################################

    @property
    def save_roi_data(self) -> bool:
        """
        Whether ROI result signals are saved by BEC's file writer.

        Configure through deviceConfig at creation or between scans. The setter
        changes signal_info.saved, leaving capture and publication enabled. BEC
        must refresh published device metadata after applying the config update.
        """
        return self._save_roi_data

    @save_roi_data.setter
    def save_roi_data(self, value: bool) -> None:
        if not isinstance(value, bool):
            raise TypeError("save_roi_data must be a boolean")
        message = self.scan_info.msg
        if self.staged != Staged.no or getattr(message, "status", None) in ("open", "paused"):
            raise RuntimeError("ROI saving can only be changed between scans")
        for _, child in self.walk_subdevices():
            if isinstance(child, ROIProcessing):
                child.result_scalar.signal_info.saved = value
                child.result_waveform.signal_info.saved = value
        self._save_roi_data = value

    @property
    def readout_priority(self) -> str:
        """
        The camera's priority in the current scan, or on_request outside scans.
        """
        if self.staged == Staged.no:
            return "on_request"
        priorities = self._scan_message.readout_priority
        if priorities is None:
            raise ValueError("Readout priorities are unavailable")
        matches = [p for p, devices in priorities.items() if self.root.name in devices]
        if len(matches) > 1:
            raise ValueError("Camera appears in multiple readout priorities")
        priority = matches[0] if matches else "on_request"
        if priority not in ("baseline", "monitored", "async", "on_request"):
            raise ValueError(f"Unsupported camera priority: {priority}")
        return priority

    @property
    def scan_type(self) -> str:
        return self._scan_message.info.get("scan_type", "software_triggered")

    @property
    def _scan_message(self) -> ScanStatusMessage:
        message = self.scan_info.msg
        if message is None:
            raise RuntimeError("Scan information is unavailable")
        return message

    def check_cancelled(self) -> None:
        """
        Stop bounded acquisition work after the normal device stop hook runs.
        """
        if self.stopped:
            raise DeviceStoppedError(f"Device {self.name} has been stopped")

    ########################################
    #          Public live control         #
    ########################################

    def start_live(self, *, update_preference: bool = True) -> StatusBase:
        """
        Start live input and previews; hooks use update_preference=False to resume.

        A scan may pause live acquisition without changing the user's preference.
        Acquisition setup belongs to on_live_mode_starts in the concrete camera.
        A stop arriving while startup waits for prior shutdown cancels the restart.
        """
        if self.staged != Staged.no and self.readout_priority != "on_request":
            raise RuntimeError("Cannot change live acquisition during a scan")
        # Clear an earlier stop only when accepting this new startup request.
        # Never clear it after waiting: a later stop must cancel this continuation.
        if update_preference or self.live_enabled.get():
            self.stopped = False
        if update_preference:
            self._set_live_preference(True)
        if not self.live_enabled.get():
            finished = StatusBase()
            finished.set_finished()
            return finished
        if self._live_active:
            self.stop_live(update_preference=False).wait(timeout=self.io_timeout)
        self.check_cancelled()
        if self.staged != Staged.no and self.readout_priority != "on_request":
            raise RuntimeError("Cannot change live acquisition during a scan")
        if not self.live_enabled.get():
            raise DeviceStoppedError("Live acquisition was disabled during startup")
        self._live_active = True
        try:
            status = self.on_live_mode_starts()
            if status is not None:
                status.wait(timeout=self.io_timeout)
            self.check_cancelled()
            self.start_polling()
            if status is None:
                status = StatusBase()
                status.set_finished()
            return status
        except Exception:
            self.stop()
            raise

    def stop_live(self, *, update_preference: bool = True) -> StatusBase:
        """
        Stop live input and previews; scan hooks preserve the live preference.

        Keep shutdown pending until the hook succeeds, including a returned status.
        Overlapping calls share one pending shutdown and invoke the hook once.
        Failed shutdowns remain retryable and never acknowledge a stopped backend.
        """
        if update_preference:
            if self.staged != Staged.no and self.readout_priority != "on_request":
                raise RuntimeError("Cannot change live acquisition during a scan")
            self._set_live_preference(False)
        self.stop_polling()
        with self._live_shutdown_lock:
            if self._live_shutdown is not None and not self._live_shutdown.done:
                return self._live_shutdown
            if not self._live_active:
                finished = StatusBase()
                finished.set_finished()
                return finished
            shutdown = StatusBase(self, description="Live acquisition stopped")
            self._live_shutdown = shutdown

        def stopped(completed: StatusBase) -> None:
            try:
                completed.wait(timeout=0)
            except Exception as error:  # noqa: BLE001 - preserve shutdown failure for retry.
                shutdown.set_exception(error)
            else:
                with self._live_shutdown_lock:
                    self._live_active = False
                    self._live_shutdown = None
                shutdown.set_finished()

        # Reserve the shared status before invoking a hook, without holding the
        # bookkeeping lock during backend I/O or callback execution.
        try:
            status = self.on_live_mode_stops()
            if status is None:
                with self._live_shutdown_lock:
                    self._live_active = False
                    self._live_shutdown = None
                shutdown.set_finished()
            else:
                status.add_callback(stopped)
        except Exception as error:
            shutdown.set_exception(error)
            raise
        return shutdown

    def _set_live_preference(self, enabled: bool) -> None:
        self._updating_live = True
        try:
            self.live_enabled.put(enabled)
        finally:
            self._updating_live = False

    def _live_changed(self, *, value: Any, **kwargs: Any) -> None:
        if self._updating_live or not self._live_ready or self.staged != Staged.no:
            return
        if value:
            self.start_live(update_preference=False)
        else:
            self.stop_live(update_preference=False).wait(timeout=self.io_timeout)

    ########################################
    #        Redis preview timer          #
    ########################################

    @property
    def redis_update_frequency(self) -> float:
        """
        Redis preview updates per second; zero disables updates without stopping live.
        """
        return self._redis_update_frequency

    @redis_update_frequency.setter
    def redis_update_frequency(self, frequency: float) -> None:
        """
        Reconfigure the preview timer while preserving camera acquisition.

        Args:
            frequency (float): Finite nonnegative updates per second. Zero disables
                Redis updates. A positive value starts updates when live is active.

        Raises:
            ValueError: frequency is not finite and nonnegative.
            TimeoutError: An existing preview read does not finish within the normal
                timer shutdown bound. Acquisition itself is not stopped by this setter.
        """
        try:
            valid = isfinite(frequency) and frequency >= 0
        except TypeError:
            valid = False
        if not valid:
            raise ValueError("redis_update_frequency must be finite and nonnegative")
        if frequency == self._redis_update_frequency:
            return
        on_timer = self._poll_thread is current_thread()
        if not on_timer:
            self.stop_polling()
        self._redis_update_frequency = float(frequency)
        self._next_redis_preview = 0.0
        self._configure_preview_transports(self._preview_paths)
        if self._live_active and not self.stopped and not on_timer:
            self.start_polling()

    def start_polling(self) -> None:
        """
        Start the optional Redis preview timer; ZMQ needs no Python timer.
        """
        if self.redis_update_frequency <= 0:
            return
        if self._poll_thread is not None and self._poll_thread.is_alive():
            return
        self._poll_stop.clear()
        self._poll_thread = Thread(target=self._poll_loop, name=f"{self.name}-preview", daemon=True)
        self._poll_thread.start()

    def stop_polling(self) -> None:
        """
        Finish any Redis preview read before changing acquisition settings.
        """
        self._poll_stop.set()
        if self._poll_thread is not None and current_thread() is not self._poll_thread:
            self._poll_thread.join(timeout=self.io_timeout * 4)
            if self._poll_thread.is_alive():
                raise TimeoutError("Redis preview timer did not stop")

    def _poll_loop(self) -> None:
        try:
            while not self._poll_stop.is_set():
                frequency = self.redis_update_frequency
                if frequency <= 0 or self._poll_stop.wait(1 / frequency):
                    return
                self.on_poll()
        except DeviceStoppedError:
            if not self._poll_stop.is_set():
                self.stop()
        except Exception as error:  # noqa: BLE001 - report errors through acquisition statuses.
            bec_logger.logger.error(f"Camera {self.name} preview failed: {error!r}")
            self.stop()

    ########################################
    #  Beamline Specific Implementations   #
    ########################################

    def on_live_mode_starts(self) -> StatusBase | None:
        """
        Called to start or resume live input outside scan acquisition.

        Configure continuous acquisition and return its acknowledgement status.
        IOC ZMQ publication requires no Python publisher.
        """

    def on_live_mode_stops(self) -> StatusBase | None:
        """
        Called to stop live input before staging, disabling live or stopping.

        Acknowledge camera shutdown and release live-specific resources. Scan
        completion and abort cleanup belong in on_complete and on_stop.
        """

    def on_poll(self) -> None:
        """
        Called by the Redis preview timer while live acquisition is active.

        Keep each call bounded. Lifecycle hooks stop the timer before changing
        acquisition settings. IOC ZMQ publication is independent of polling.
        """

    ########################################
    # Preview transport and Redis updates  #
    ########################################

    def _configure_preview_transports(self, paths: list[str]) -> None:
        """
        Describe existing IOC streams; never create/configure their publishers.
        """
        self._preview_paths = list(dict.fromkeys([*self._preview_paths, *paths]))
        for path in self._preview_paths:
            signal = rgetattr(self, path)
            transports = list(self._preview_transports.get(path, []))
            if self.redis_update_frequency > 0:
                transports.append(
                    messages.RedisSignalTransport.from_endpoint_info(
                        MessageEndpoints.device_preview(self.name, path)
                    )
                )
            signal.signal_info.transports = transports

    def _read_preview_signal(self, signal: Any) -> Any:
        """
        Read one preview PV, checking cancellation between bounded reads.
        """
        if self._poll_stop.is_set():
            raise DeviceStoppedError("Redis preview stopped")
        return signal.get(timeout=self.io_timeout, use_monitor=False)

    def _redis_preview_due(self) -> bool:
        """
        Throttle CA reads as well as Redis puts; zero disables both.
        """
        frequency = self.redis_update_frequency
        if frequency <= 0:
            return False
        now = monotonic()
        if now < self._next_redis_preview:
            return False
        self._next_redis_preview = now + 1 / frequency
        return True
