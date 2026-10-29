"""
AreaDetector ROI/Stats configuration, buffered capture and result publication.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import dataclass
from enum import IntEnum
from functools import partial, reduce
from threading import Event, Lock, RLock
from time import time
from typing import Any, Literal, cast

import numpy as np
from bec_lib.devicemanager import ScanInfo
from bec_lib.logger import bec_logger
from bec_lib.messages import RectROIConfig, ROIConfigurationMessage
from bec_lib.utils.rpc_utils import rgetattr
from bec_server.scan_server.scans.scan_base import ScanInfo as ScanServerScanInfo
from ophyd import ADBase, Component, EpicsSignal, EpicsSignalRO, FormattedComponent, Kind, Signal
from ophyd.utils.errors import InvalidState, StatusTimeoutError, WaitTimeoutError
from pydantic import ValidationError

from ophyd_devices.devices.areadetector.configuration import configure_ad_signals
from ophyd_devices.devices.areadetector.plugins import ROIPlugin_V35 as ROIPlugin
from ophyd_devices.devices.areadetector.plugins import StatsPlugin_V35
from ophyd_devices.interfaces.base_classes.psi_device_base import DeviceStoppedError
from ophyd_devices.utils.bec_roi_signals.roi_processing import (
    LITERAL_ROI_PROCESSING_CONFIG,
    ROIProcessing,
)
from ophyd_devices.utils.bec_signals import PreviewSignal
from ophyd_devices.utils.psi_device_base_utils import (
    AndStatus,
    CompareStatus,
    DeviceStatus,
    StatusBase,
    SubscriptionStatus,
    TransitionStatus,
)


def fetch_scan_info(scan_info: ScanInfo) -> ScanServerScanInfo:
    """
    Resolve shared scan metadata into the scan-server acquisition schema.

    Convert list-based positions to a NumPy array and include the monitored readout
    count. If current-schema validation fails, normalize the legacy scan_type value
    before retrying validation. Initial normalization updates scan_info.msg.info.

    Args:
        scan_info (ScanInfo): Mutable device-manager wrapper holding the current
            ScanStatusMessage, its info dictionary and num_monitored_readouts.

    Returns:
        ScanServerScanInfo: Validated scan parameters used by standalone ROI capture.

    Raises:
        KeyError: Required scan metadata is missing.
        pydantic.ValidationError: Neither current nor legacy-normalized metadata
            satisfies the scan-server schema.
    """
    info = scan_info.msg.info
    if isinstance(info["positions"], list):
        info["positions"] = np.array(info["positions"])
    info["num_monitored_readouts"] = scan_info.msg.num_monitored_readouts
    try:
        msg = ScanServerScanInfo.model_validate(info)
    except ValidationError:  # This means we have an old scan_info object.
        info = deepcopy(info)
        # We need to convert a few parameters manually.
        info["scan_type"] = (
            "hardware_triggered" if info["scan_type"] == "fly" else "software_triggered"
        )
        msg = ScanServerScanInfo.model_validate(info)

    return msg


logger = bec_logger.logger


class TSAcquireMode(IntEnum):
    """
    Enum for TSAcquireMode values.
    """

    FIXED_LENGTH = 0
    CIRCULAR_BUFFER = 1


class TSReadMode(IntEnum):
    """
    Enum for TSReadMode values. Recommend to use PASSIVE mode for most applications.
    """

    PASSIVE = 0
    EVENT = 1
    IO_INTR = 2
    TEN_SECOND = 3
    FIVE_SECOND = 4
    TWO_SECOND = 5
    ONE_SECOND = 6
    HALF_SECOND = 7
    TWO_TENTHS_SECOND = 8
    ONE_TENTH_SECOND = 9


class StatsPluginWithTSControl(StatsPlugin_V35):
    """
    Expose Stats outputs and the explicitly paired NDTimeSeries plugin controls.

    The TS: records belong to NDTimeSeries, while scalar/time-series waveforms belong
    to Stats. Monitored acquisition/index/averaging readbacks support status-based
    capture acknowledgement. Duplicate legacy sigma components are omitted to avoid
    colliding signal names in BEC metadata.
    """

    # ADCore's structured sigma.x/y signals supersede these inherited flat
    # components. Keeping both creates duplicate Ophyd names in BEC metadata.
    sigma_x = None
    sigma_y = None

    basic_sigma = Component(EpicsSignalRO, "Sigma_RBV", kind=Kind.omitted)

    ts_acquire_status = Component(
        EpicsSignalRO, "TS:TSAcquiring", kind=Kind.omitted, auto_monitor=True
    )
    ts_acquire = Component(EpicsSignal, "TS:TSAcquire", kind=Kind.omitted)
    ts_acquire_mode = Component(EpicsSignal, "TS:TSAcquireMode", kind=Kind.omitted)
    ts_read_mode = Component(EpicsSignal, "TS:TSRead.SCAN", kind=Kind.omitted)
    ts_read = Component(EpicsSignal, "TS:TSRead.PROC", kind=Kind.omitted)
    ts_array_counter = Component(
        EpicsSignalRO, "TS:ArrayCounter_RBV", kind=Kind.omitted, auto_monitor=True
    )
    ts_current_index = Component(EpicsSignalRO, "TS:TSCurrentPoint", kind=Kind.omitted)
    ts_num_points = Component(EpicsSignal, "TS:TSNumPoints", kind=Kind.omitted, auto_monitor=True)
    ts_averaging_time = Component(
        EpicsSignal, "TS:TSAveragingTime", kind=Kind.omitted, auto_monitor=True
    )
    ts_num_average = Component(
        EpicsSignalRO, "TS:TSNumAverage", kind=Kind.omitted, auto_monitor=True
    )


@dataclass
class StatsSubscription:
    """
    Describe one standalone Stats output subscription owned by an ROI component.

    Attributes:
        signal (Any): Resolved backend signal providing the result updates.
        callback_id (int): Subscription token used to unsubscribe during reconfiguration.
        operation (str): Analysis operation owning the result.
        result_name (str): Short name published in the dynamic result stream.
        output_kind (Literal["scalar", "waveform"]): Result signal receiving updates.
    """

    signal: Any
    callback_id: int
    operation: str
    result_name: str
    output_kind: Literal["scalar", "waveform"]


NDPLUGIN_STATS_CONFIG: LITERAL_ROI_PROCESSING_CONFIG = {
    "basic_statistics": {
        "enable_signal": "compute_statistics",
        "scalar_outputs": [
            "min_value",
            "min_x",
            "min_y",
            "max_value",
            "max_x",
            "max_y",
            "mean_value",
            "sigma",
            "total",
            "net",
        ],
        "waveform_outputs": [],
        "source_signals": {
            "min_value": "ts_min_value",
            "min_x": "ts_min.x",
            "min_y": "ts_min.y",
            "max_value": "ts_max_value",
            "max_x": "ts_max.x",
            "max_y": "ts_max.y",
            "mean_value": "ts_mean_value",
            "sigma": "ts_sigma",
            "total": "ts_total",
            "net": "ts_net",
            "timestamp": "ts_timestamp",
        },
    },
    "centroid": {
        "enable_signal": "compute_centroid",
        "scalar_outputs": [
            "centroid_x",
            "centroid_y",
            "sigma_x",
            "sigma_y",
            "sigma_xy",
            "skew_x",
            "skew_y",
            "kurtosis_x",
            "kurtosis_y",
            "eccentricity",
            "orientation",
        ],
        "waveform_outputs": [],
        "source_signals": {
            "centroid_x": "ts_centroid.x",
            "centroid_y": "ts_centroid.y",
            "sigma_x": "ts_sigma_x.ts_sigma_x",
            "sigma_y": "ts_sigma_x.ts_sigma_y",
            "sigma_xy": "ts_sigma_xy",
            "skew_x": "ts_skew.x",
            "skew_y": "ts_skew.y",
            "kurtosis_x": "ts_kurtosis.x",
            "kurtosis_y": "ts_kurtosis.y",
            "eccentricity": "ts_eccentricity",
            "orientation": "ts_orientation",
            "timestamp": "ts_timestamp",
        },
    },
}


class AverageFramesForEachTrigger(Signal):
    """
    Store whether ROI results should be averaged across frames from one trigger.

    Numeric inputs are converted to a boolean. Standalone Stats callbacks and camera
    publication paths consult this flag when their acquisition mode permits averaging.
    This signal does not configure the IOC's own time-series averaging. Changes
    are rejected while scan or capture configuration is locked.
    """

    def put(self, value: bool | float, **kwargs: Any) -> None:
        """
        Store a boolean averaging preference from a boolean or numeric input.

        Args:
            value (bool | int | float): False/zero disables averaging; nonzero enables it.
            **kwargs (Any): Additional write options forwarded to ophyd.Signal.put().

        Raises:
            TypeError: value is neither boolean nor numeric.
            RuntimeError: A scan or capture currently locks ROI configuration.
        """
        if not isinstance(value, (bool, int, float)):
            raise TypeError("average_frames_per_trigger must be a boolean or numeric value.")
        requests = self.parent.update_received
        with requests._update_lock:
            if requests.updates_blocked:
                raise RuntimeError(
                    f"ROI configuration is locked: {self.name} cannot change during a scan."
                )
            super().put(bool(value), **kwargs)

    def set(
        self,
        value: bool | float,
        *,
        timeout: float | None = None,
        settle_time: float | None = None,
        **kwargs: Any,
    ) -> StatusBase:
        """
        Set the averaging preference and preserve validation or scan-lock failures.

        Args:
            value (bool | int | float): Averaging preference passed to put().
            timeout (float | None): Timeout for the returned status.
            settle_time (float | None): Delay before successful status completion.
            **kwargs (Any): Additional signal-write options forwarded to put().

        Returns:
            StatusBase: Result of the synchronous local setting update.
        """
        status = StatusBase(self, timeout=timeout, settle_time=settle_time or 0)
        try:
            self.put(value, **kwargs)
        except Exception as error:  # noqa: BLE001 - preserve the original setting failure.
            status.set_exception(error)
        else:
            status.set_finished()
        return status


@configure_ad_signals
class ADROIProcessing(ROIProcessing, ADBase):
    """
    ROI processing with configurable AD plugin suffixes.

    Accept only RectROIConfig, the axis-aligned rectangle supported by the IOC's
    ROI plugin. Reject other shapes before queuing requests or changing signals.

    ``roi_suffix`` and ``stats_suffix`` are relative to this component's prefix
    and default to ``ROI1:`` and ``Stats1:``. Declare a separate component for
    each pair, for example ``Component(ADROIProcessing, "", roi_suffix="ROI2:",
    stats_suffix="Stats2:")``. Each pair must have its own IOC plugins.

    Set ``manage_capture=False`` when the camera owns arming, buffered reads and
    result publication. saved controls only file persistence through signal_info.saved;
    None inherits the camera save_roi_data preference (True for standalone ROIs).
    ROI values still publish when saved is False. Plugin routing, ROI geometry and
    enablement remain owned by this component, but it installs no result callbacks
    or acquisition hooks.
    """

    preview = Component(PreviewSignal, ndim=1)

    roi1 = FormattedComponent(ROIPlugin, "{self.prefix}{self.roi_suffix}", kind=Kind.omitted)
    stats1 = FormattedComponent(
        StatsPluginWithTSControl, "{self.prefix}{self.stats_suffix}", kind=Kind.omitted
    )
    average_frames_per_trigger = Component(
        AverageFramesForEachTrigger, name="average_frames_per_trigger", kind=Kind.config, value=True
    )

    def __init__(
        self,
        *args,
        roi_suffix: str = "ROI1:",
        stats_suffix: str = "Stats1:",
        manage_capture: bool = True,
        saved: bool | None = None,
        **kwargs,
    ):
        """
        Create an AD ROI/Stats pair and its local capture/configuration state.

        Construction sets up metadata and an IOC-configuration executor without reading
        or writing PVs. Connection setup is performed explicitly by on_connected(). AD
        supports axis-aligned rectangles only; allowed_roi_config_types cannot broaden
        that backend capability.

        Args:
            *args (Any): Positional device arguments forwarded to ROIProcessing, normally
                the component prefix shared by the ROI and Stats plugins.
            roi_suffix (str): ROI plugin suffix relative to that prefix. Defaults to "ROI1:".
            stats_suffix (str): Stats plugin suffix relative to that prefix. Defaults to
                "Stats1:". Each pair must address distinct IOC plugin instances.
            manage_capture (bool): True to use this component's standalone legacy capture
                hooks/subscriptions. False lets the owning camera arm buffers, read results
                and publish scan data explicitly. Defaults to True.
            saved (bool | None): Initial result persistence flag. None inherits the root
                camera's save_roi_data value, defaulting to True without that preference.
                This does not disable capture or streaming.
            **kwargs (Any): ROIProcessing/ROI/device arguments, including roi_config,
                active, roi_name, selected_operations, name and parent. The optional
                allowed_roi_config_types argument accepts only [RectROIConfig]; None or
                omission uses that restriction automatically.

        Raises:
            ValueError: allowed_roi_config_types attempts to permit an unsupported AD
                shape, or an inherited constructor option is invalid.
            TypeError: The initial configuration is not a permitted rectangular shape.
            pydantic.ValidationError: The initial configuration fails its shape schema.
        """
        self._capture_outputs: dict[str, str] = {}
        self._capture_offset = 0
        self._capture_start_count = 0
        self._capture_armed = False
        self.manage_capture = manage_capture
        self.roi_suffix = roi_suffix
        self.stats_suffix = stats_suffix
        allowed = kwargs.get("allowed_roi_config_types")
        if allowed is not None and any(cls is not RectROIConfig for cls in allowed):
            raise ValueError("AD ROI processing only supports RectROIConfig")
        kwargs["allowed_roi_config_types"] = (RectROIConfig,) if allowed is None else allowed
        super().__init__(*args, **kwargs)
        # Set metadata before device-server inspection, without changing publication.
        save_data = getattr(self.root, "save_roi_data", True) if saved is None else saved
        self.result_scalar.signal_info.saved = bool(save_data)
        self.result_waveform.signal_info.saved = bool(save_data)
        self._stats_subscriptions: dict[str, StatsSubscription] = {}
        self._missing_stats_paths: set[str] = set()
        self._ad_connection_initialized = False
        self._ioc_config_lock = RLock()
        self._ioc_pending_lock = Lock()
        self._ioc_sync_pending = False
        self._ioc_sync_dirty = False
        self._ioc_config_closed = False
        self._ioc_config_subscriptions = []
        self._ioc_config_executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="ADROI-config"
        )
        self.scan_server_scan_info: ScanServerScanInfo | None = None

    def arm_capture(self, *, camera: Any, capacity: int | None) -> DeviceStatus:
        """
        Arm this ROI/Stats pair and return its readiness status.

        Arm capture in this order:

        1. Stop Stats and apply ROI/Stats plugin enablement.
        2. Validate CA waveform capacities and disable IOC time-series averaging.
        3. Configure time-series mode, read mode and buffer capacity.
        4. Record the camera counter origin before camera input starts.
        5. Install acquiring/reset subscriptions, then start Stats capture.
        6. Request an empty TSRead and acknowledge every selected waveform is empty.
        7. Complete readiness before the owning camera can produce any new frames.

        Starting Stats clears internal storage but leaves previous waveform PV values
        intact. The empty waveform baseline is required for fixed-index readout to
        distinguish the new capture from an equal-length previous burst. No waveform
        monitor settings are changed.

        Statuses represent acknowledgement waits. Reads and command submission use
        the camera's bounded I/O timeout. Camera stop cancels pending arming.

        Args:
            camera (Any): Owning camera providing controller counters, I/O timeout and status
                cancellation. It must keep input stopped until all ROI pairs are armed.
            capacity (int | None): Positive number of samples to retain without wrapping.
                None uses the smallest NELM of the selected statistic and timestamp
                waveforms. Async capture is bounded by this capacity for the entire
                scan; software bursts reset their buffers for each trigger.

        Returns:
            DeviceStatus: Readiness acknowledgement. An inactive ROI or an ROI without
            selected outputs finishes without starting time-series capture. Invalid
            ownership, capacity, connection and readiness failures are forwarded
            through this status.
        """
        capture_armed = DeviceStatus(None, description="ROI capture armed")
        readiness_statuses = []
        io, stats = camera.io_timeout, self.stats1
        camera.cancel_on_stop(capture_armed)

        def fail(error):
            if isinstance(error, (WaitTimeoutError, StatusTimeoutError)):
                error = TimeoutError(str(error))
            if not capture_armed.done:
                capture_armed.set_exception(error)

        def cleanup(status):
            if status.success:
                return
            for child in readiness_statuses:
                if not child.done:
                    try:
                        child.set_exception(RuntimeError("ROI arming aborted"))
                    except InvalidState:
                        pass  # The child already has a scheduled completion.

        capture_armed.add_callback(cleanup)

        def configure_capture(plugins_ready):
            nonlocal capacity
            if capture_armed.done:
                return
            try:
                plugins_ready.wait(timeout=0)
                camera.check_cancelled()
                if not self._capture_outputs:
                    capture_armed.set_finished()
                    return
                # Native CA element capacity is NELM, not the current waveform
                # length (NORD). TSNumPoints can exceed it without IOC rejection.
                maxima = []
                for path in {*self._capture_outputs.values(), "ts_timestamp"}:
                    waveform = rgetattr(stats, path)
                    waveform.wait_for_connection(timeout=io)
                    maximum = int(waveform._read_pv.nelm)
                    maxima.append(maximum)
                    if capacity is not None and maximum < capacity:
                        raise ValueError(
                            f"Requested ROI capture exceeds IOC buffer capacity: {path} "
                            f"supports {maximum} elements, requested {capacity}"
                        )
                if capacity is None:
                    capacity = min(maxima)
                if capacity < 1:
                    raise ValueError("ROI waveforms have no usable IOC buffer capacity")
                # Keep capture fixed-length. Circular TSRead output shifts its
                # oldest sample to index zero, but separate statistic/timestamp
                # waveforms carry no snapshot-associated absolute position. Once
                # wrapped, equal lengths or overlapping values cannot reliably
                # align them (statistics may be constant). Revisit circular capture
                # only with a reliable way to identify each waveform's sample range.
                settings = (
                    (stats.ts_averaging_time, 0),
                    (stats.ts_acquire_mode, 0),
                    (stats.ts_read_mode, 0),
                    (stats.ts_num_points, capacity),
                )
                applied = [
                    CompareStatus(
                        signal,
                        value,
                        run=True,
                        timeout=io,
                        description=f"ROI capture setting {signal.name}={value}",
                    )
                    for signal, value in settings
                ]
                applied.append(
                    CompareStatus(
                        stats.ts_num_average,
                        1,
                        run=True,
                        timeout=io,
                        description="ROI time series stores one sample per frame",
                    )
                )
                readiness_statuses.extend(applied)
                for signal, value in settings:
                    camera.check_cancelled()
                    signal.put(value, wait=False, timeout=io)
                reduce(AndStatus, applied).add_callback(start_capture)
            except Exception as error:  # noqa: BLE001 - forward configuration failures.
                fail(error)

        def start_capture(settings_applied):
            if capture_armed.done:
                return
            try:
                settings_applied.wait(timeout=0)
                camera.check_cancelled()
                if int(stats.ts_num_points.get(timeout=io, use_monitor=False)) != capacity:
                    raise ValueError("Requested ROI capture exceeds IOC buffer capacity")
                if int(stats.ts_num_average.get(timeout=io, use_monitor=False)) != 1:
                    raise ValueError("ROI time-series averaging must store one sample per frame")
                self._capture_offset = 0
                self._capture_start_count = int(
                    camera.cam.array_counter.get(timeout=io, use_monitor=False)
                )
                acquiring = CompareStatus(
                    stats.ts_acquire_status,
                    1,
                    run=False,
                    timeout=io,
                    description="Stats capture acquiring",
                )
                reset = CompareStatus(
                    stats.ts_current_index,
                    0,
                    run=True,
                    timeout=io,
                    description="Stats capture buffer reset",
                )
                readiness_statuses.extend((acquiring, reset))
                (acquiring & reset).add_callback(clear_waveforms)
                camera.check_cancelled()
                stats.ts_acquire.put(1, wait=False, timeout=io)
            except Exception as error:  # noqa: BLE001 - forward arming failures.
                fail(error)

        def clear_waveforms(capture_started):
            if capture_armed.done:
                return
            try:
                capture_started.wait(timeout=0)
                camera.check_cancelled()
                empty_waveforms = []
                paths = dict.fromkeys([*self._capture_outputs.values(), "ts_timestamp"])
                for path in paths:
                    waveform = rgetattr(stats, path)
                    empty = SubscriptionStatus(
                        waveform,
                        lambda *, value, **_: value is not None and np.asarray(value).size == 0,
                        run=False,
                        timeout=io,
                        description=f"ROI waveform reset: {path}",
                    )
                    readiness_statuses.append(empty)
                    camera.cancel_on_stop(empty)
                    empty_waveforms.append((waveform, empty))
                camera.check_cancelled()
                stats.ts_read.put(1, wait=True, timeout=io)
                for waveform, empty in empty_waveforms:
                    camera.check_cancelled()
                    # Unchanged empty records need not emit monitor events. A fresh
                    # read also acknowledges that they contain no previous samples.
                    value = waveform.get(timeout=io, use_monitor=False)
                    if value is not None and np.asarray(value).size == 0 and not empty.done:
                        try:
                            empty.set_finished()
                        except InvalidState:
                            pass  # Its zero-length monitor arrived concurrently.
                reduce(AndStatus, [status for _, status in empty_waveforms]).add_callback(
                    mark_armed
                )
            except Exception as error:  # noqa: BLE001 - report empty-baseline failures.
                fail(error)

        def mark_armed(waveforms_empty):
            if capture_armed.done:
                return
            try:
                waveforms_empty.wait(timeout=0)
                camera.check_cancelled()
                self._capture_armed = True
                capture_armed.set_finished()
            except Exception as error:  # noqa: BLE001 - forward readiness failures.
                fail(error)

        try:
            camera.check_cancelled()
            if self.manage_capture:
                raise RuntimeError("Camera-owned capture requires manage_capture=False")
            if capacity is not None and (type(capacity) is not int or capacity < 1):
                raise ValueError("ROI capacity must be a positive integer")
            self._capture_armed = False
            self._capture_outputs = {}
            active = bool(self.active.get())
            if active:
                for operation in cast(list[str], self.selected_operations.get()):
                    config = NDPLUGIN_STATS_CONFIG[operation]
                    for name in config.get("scalar_outputs", []):
                        self._capture_outputs[name] = config.get("source_signals", {})[name]
            enabled = "Enable" if active else "Disable"
            idle = CompareStatus(
                stats.ts_acquire_status,
                0,
                run=True,
                timeout=io,
                description="Stats idle before arming",
            )
            roi_enabled = CompareStatus(
                self.roi1.enable, enabled, timeout=io, description="ROI plugin enablement applied"
            )
            stats_enabled = CompareStatus(
                stats.enable, enabled, timeout=io, description="Stats plugin enablement applied"
            )
            readiness_statuses.extend((idle, roi_enabled, stats_enabled))
            stats.ts_acquire.put(0, wait=False, timeout=io)
            self.roi1.enable.put(enabled, wait=False, timeout=io)
            stats.enable.put(enabled, wait=False, timeout=io)
            (idle & roi_enabled & stats_enabled).add_callback(configure_capture)
        except Exception as error:  # noqa: BLE001 - propagate failures through the returned status.
            fail(error)
        return capture_armed

    def drain_capture(self, *, camera: Any) -> DeviceStatus:
        """
        Wait for accepted camera frames to reach Stats, then stop ROI capture.

        Drain capture in this order:

        1. Compute accepted camera frames relative to the counter recorded at arming.
        2. Wait for the fixed Stats buffer index to reach that frame count.
        3. Stop Stats capture and wait for idle acknowledgement.

        An empty capture needs no counter notification. Capture never wraps: more
        accepted frames than buffer slots is an error. The caller publishes results
        after this status finishes.

        Args:
            camera (Any): Owning camera providing the final frame count, I/O timeout and
                cancellation services. Camera input must already have finished or stopped.

        Returns:
            DeviceStatus: Drain/shutdown acknowledgement, already finished if this
            ROI was not armed. Buffer capacity, missing-frame, timeout and stop
            failures are forwarded through it.
        """
        drain_done = DeviceStatus(None, description="Drain ROI buffers")
        if not self._capture_armed:
            drain_done.set_finished()
            return drain_done
        io, stats = camera.io_timeout, self.stats1

        def stop_capture(frames_received):
            try:
                frames_received.wait(timeout=0)
                camera.check_cancelled()
                idle = SubscriptionStatus(
                    stats.ts_acquire_status,
                    lambda *, value, **_: value == 0,
                    run=True,
                    timeout=io,
                    description="Stats capture stopped",
                )
                camera.cancel_on_stop(idle)
                idle.add_callback(mark_drained)
                stats.ts_acquire.put(0, wait=False, timeout=io)
            except Exception as error:  # noqa: BLE001 - report errors through acquisition statuses.
                if not drain_done.done:
                    drain_done.set_exception(error)

        def mark_drained(capture_stopped):
            try:
                capture_stopped.wait(timeout=0)
                camera.check_cancelled()
                self._capture_armed = False
                if not drain_done.done:
                    drain_done.set_finished()
            except Exception as error:  # noqa: BLE001 - report errors through acquisition statuses.
                if not drain_done.done:
                    drain_done.set_exception(error)

        try:
            expected = (
                int(camera.cam.array_counter.get(timeout=io, use_monitor=False))
                - self._capture_start_count
            )
            if expected == 0:
                empty = DeviceStatus(None, description="No ROI frames to drain")
                empty.set_finished()
                stop_capture(empty)
                return drain_done
            if expected > int(stats.ts_num_points.get(timeout=io, use_monitor=False)):
                raise RuntimeError("ROI buffer capacity exceeded")
            frames_received = SubscriptionStatus(
                stats.ts_current_index,
                lambda *, value, **_: int(value) >= expected,
                run=True,
                timeout=io,
                description="Stats received all camera frames",
            )
            camera.cancel_on_stop(frames_received)
            frames_received.add_callback(stop_capture)
        except Exception as error:  # noqa: BLE001 - report errors through acquisition statuses.
            drain_done.set_exception(error)
        return drain_done

    def publish_capture(
        self,
        *,
        camera: Any,
        source_path: str,
        group: str,
        frame_origin: int,
        single_value: bool = False,
        average_frames: bool = False,
        check_overflow: bool = False,
    ) -> None:
        """
        Read unpublished Stats values and emit scalar ROI DynamicSignals.

        Capture uses fixed positions starting at zero and never wraps. Waveforms
        can arrive at different lengths: publish only the common available prefix,
        bounded by the observed Stats index. Remaining samples are read on the next
        update. Acquisition may continue during TSRead because earlier positions
        retain their values. Final readout after draining requires every expected
        sample to be available. Offsets advance after the entire batch is published.

        Args:
            camera (Any): Owning camera providing timeouts, result session and cancellation.
            source_path (str): Dotted ROI path recorded in result metadata.
            group (str): DynamicSignal correlation group, independent of acquisition source.
            frame_origin (int): Camera counter at the start of the scan result session.
            single_value (bool): Reduce all available frames to one value for baseline readout.
            average_frames (bool): Respect average_frames_per_trigger for a software burst.
            check_overflow (bool): Check fixed-buffer capacity against accepted camera frames.

        Raises:
            RuntimeError: Capture reset, exceeded buffer capacity or incomplete waveform data.
            DeviceStoppedError: The owning camera was stopped before publication finished.

        Full camera images are not sent through this method; it publishes ROI statistics.
        """
        io = camera.io_timeout
        if not self._capture_outputs:
            return

        stats = self.stats1
        if check_overflow and self._capture_armed:
            acquired = (
                int(camera.cam.array_counter.get(timeout=io, use_monitor=False))
                - self._capture_start_count
            )
            capacity = int(stats.ts_num_points.get(timeout=io, use_monitor=False))
            if acquired > capacity:
                raise RuntimeError(
                    f"ROI scan exceeds IOC buffer capacity ({capacity} samples). "
                    "Reduce the number of frames per scan or disable ROI outputs."
                )
        stop = int(stats.ts_current_index.get(timeout=io, use_monitor=False))
        if stop < self._capture_offset:
            raise RuntimeError("ROI buffer reset during acquisition")
        if stop == self._capture_offset:
            return
        stats.ts_read.put(1, wait=True, timeout=io)
        values = {
            name: np.asarray(rgetattr(stats, path).get(timeout=io, use_monitor=False)).copy()
            for name, path in self._capture_outputs.items()
        }
        stamps = np.asarray(stats.ts_timestamp.get(timeout=io, use_monitor=False)).copy()
        available = min(stop, len(stamps), *(len(value) for value in values.values()))
        if not self._capture_armed and available < stop:
            raise RuntimeError("Incomplete ROI time series")
        if available <= self._capture_offset:
            return
        stop = available
        section = slice(self._capture_offset, stop)
        values = {name: value[section] for name, value in values.items()}
        stamps = stamps[section] + 631152000.0
        frame_ids = np.arange(self._capture_offset, stop) + self._capture_start_count - frame_origin
        reduce_frames = single_value or (
            average_frames and bool(self.average_frames_per_trigger.get())
        )
        if reduce_frames:
            values = {name: np.asarray([np.mean(value, axis=0)]) for name, value in values.items()}
            stamps = np.asarray([np.mean(stamps)])
        signal: Any = self.result_scalar
        signal.signal_info.correlation_group = group
        for index, stamp in enumerate(stamps):
            camera.check_cancelled()
            data = {
                name: {
                    "value": (float(value[index]) if np.ndim(value[index]) == 0 else value[index]),
                    "timestamp": float(stamp),
                }
                for name, value in values.items()
            }
            if len(signal.signal_info.signals) == 1 and len(data) == 1:
                data = {signal.name: next(iter(data.values()))}
            signal.put(
                data,
                async_update={"type": "add", "max_shape": [None] * (signal.signal_info.ndim + 1)},
                metadata={
                    "correlation_group": group,
                    "session_id": camera.session_id,
                    "source": f"{source_path}.result_scalar",
                    "frame_ids": frame_ids.tolist() if reduce_frames else [int(frame_ids[index])],
                },
            )
        self._capture_offset = stop

    def read_preview_values(
        self, *, io_timeout: float, stop_event: Event | None = None
    ) -> tuple[np.ndarray, list[str]]:
        """
        Read instantaneous scalar Stats values for the live ROI preview.

        Resolve selected operation outputs to their scalar PVs and read them in declared
        order. These are current plugin values, not samples drained from a scan time-series
        buffer. A supplied stop event is checked before each bounded PV read.

        Args:
            io_timeout (float): Timeout in seconds for each individual backend read.
            stop_event (threading.Event | None): Optional cancellation event. None disables
                cancellation checks within this read sequence.

        Returns:
            tuple[numpy.ndarray, list[str]]: Numeric values and their corresponding short
                result names, in matching order. Both are empty when no outputs are selected.

        Raises:
            DeviceStoppedError: stop_event is set before a statistic is read.
            Exception: A backend statistic read fails or times out.
        """
        live_paths = {
            "sigma": "basic_sigma",
            "sigma_x": "sigma.x",
            "sigma_y": "sigma.y",
            "min_x": "min_xy.x",
            "min_y": "min_xy.y",
            "max_x": "max_xy.x",
            "max_y": "max_xy.y",
            "centroid_x": "centroid.x",
            "centroid_y": "centroid.y",
            "skew_x": "skew.x",
            "skew_y": "skew.y",
            "kurtosis_x": "kurtosis.x",
            "kurtosis_y": "kurtosis.y",
        }
        names = [
            name
            for op in cast(list[str], self.selected_operations.get())
            for name in NDPLUGIN_STATS_CONFIG[op].get("scalar_outputs", [])
        ]
        values = []
        for name in names:
            if stop_event is not None and stop_event.is_set():
                raise DeviceStoppedError("Redis preview stopped")
            value = rgetattr(self.stats1, live_paths.get(name, name)).get(
                timeout=io_timeout, use_monitor=False
            )
            values.append(float(value))
        values = np.asarray(values)
        return values, names

    def stop_capture(self, *, io_timeout: float) -> None:
        """
        Stop this ROI's time-series capture and release deferred configuration updates.

        Install an idle acknowledgement before sending the stop command and wait with a
        bounded timeout. Clear the local armed state and release only the capture
        lock, even if shutdown fails. Scan/manual locks continue to defer requests;
        releasing capture must never apply edits during an open scan.

        Args:
            io_timeout (float): Timeout in seconds for the stop command and idle acknowledgement.

        Raises:
            Exception: Stopping capture, acknowledging idle or applying a deferred
                configuration fails.
        """
        stopped = SubscriptionStatus(
            self.stats1.ts_acquire_status,
            lambda *, value, **_: value in (0, "Done"),
            run=True,
            timeout=io_timeout,
            description="Stats capture stopped",
        )
        try:
            self.stats1.ts_acquire.put(0, wait=False, timeout=io_timeout)
            stopped.wait(timeout=io_timeout)
        finally:
            if not stopped.done:
                stopped.set_exception(RuntimeError("ROI stop aborted"))
            self._capture_armed = False
            self.update_received.unblock_updates(owner="capture")

    def get_scalar_outputs(self) -> list[str]:
        """
        Declare scalar result names for every supported Stats analysis operation.

        Returns:
            list[str]: Scalar output names from NDPLUGIN_STATS_CONFIG, including outputs
                belonging to currently unselected operations. No PVs are read.
        """
        scalar_outputs = []
        for config in NDPLUGIN_STATS_CONFIG.values():
            scalar_outputs.extend(config.get("scalar_outputs", []))
        return scalar_outputs

    def get_waveform_outputs(self) -> list[str]:
        """
        Declare waveform result names for every supported Stats analysis operation.

        Returns:
            list[str]: Waveform output names from NDPLUGIN_STATS_CONFIG. The list may be
                empty, and no PVs are read.
        """
        waveform_outputs = []
        for config in NDPLUGIN_STATS_CONFIG.values():
            waveform_outputs.extend(config.get("waveform_outputs", []))
        return waveform_outputs

    def get_available_analysis_operations(self) -> list[str]:
        """
        Declare the selectable operations provided by this Stats implementation.

        Returns:
            list[str]: Operation names from NDPLUGIN_STATS_CONFIG, independent of the
                current selection and without reading hardware.
        """
        return list(NDPLUGIN_STATS_CONFIG.keys())

    def on_connected(self) -> None:
        """
        Initialize the explicitly paired ROI/Stats pipeline after EPICS connection.

        The owning device invokes this method. Initialization proceeds in this order:

        1. Initialize shared ROI configuration, processing metadata and request handling.
        2. Connect Stats input to the paired ROI port, preserving the ROI's IOC input chain.
        3. Apply the stored rectangle, plugin enablement and processing selection.
        4. Configure standalone capture modes when manage_capture is True.
        5. Monitor IOC geometry and processing controls for confirmed configuration updates.

        Successful repeated calls do nothing. Transform settings and upstream routing
        remain owned by the IOC configuration.

        Raises:
            Exception: Shared initialization, plugin configuration or monitor setup fails.
        """
        # Commit initialization only after all IOC observers are installed. Partial
        # failures release observers and can be retried without duplicate callbacks.
        if self._ad_connection_initialized:
            return
        super().on_connected()
        # The IOC owns the ROI input chain, including upstream NDTransform settings.
        # Only wire the Stats plugin to its explicitly paired ROI plugin.
        self.stats1.nd_array_port.put(
            self.roi1.port_name.get(), timeout=getattr(self.root, "io_timeout", 3.0), wait=True
        )
        self._apply_roi_configuration()
        self._sync_stats_subscriptions()
        if self.manage_capture:
            self.stats1.ts_acquire_mode.put(TSAcquireMode.FIXED_LENGTH.value, wait=True, timeout=2)
            self.stats1.ts_read_mode.put(TSReadMode.PASSIVE.value, wait=True, timeout=2)
        try:
            for signal in self._ioc_configuration_signals().values():
                if any(signal is observed for observed, _ in self._ioc_config_subscriptions):
                    continue  # A previous rollback could not remove this observer.
                token = signal.subscribe(self._on_ioc_configuration_changed, run=False)
                self._ioc_config_subscriptions.append((signal, token))
        except Exception as error:
            for signal, token in tuple(self._ioc_config_subscriptions):
                try:
                    signal.unsubscribe(token)
                except Exception as cleanup_error:  # noqa: BLE001 - preserve installation failure.
                    error.add_note(f"Removing partial IOC observer also failed: {cleanup_error!r}")
                else:
                    self._ioc_config_subscriptions.remove((signal, token))
            raise
        self._ad_connection_initialized = True

    def destroy(self) -> None:
        """
        Release IOC configuration observation, Stats subscriptions and request resources.

        Mark observation closed, remove its PV subscriptions and shut down the owned
        configuration executor before destroying shared ROI resources. Repeated calls do
        nothing after destruction succeeds. Cleanup attempts every resource even if
        an unsubscribe fails. Acquisition shutdown is owned by the detector's
        stop path rather than this resource-cleanup method.
        """
        if self._destroyed:
            return
        with self._ioc_pending_lock:
            self._ioc_config_closed = True
        errors = []
        for signal, token in tuple(self._ioc_config_subscriptions):
            try:
                signal.unsubscribe(token)
            except Exception as error:  # noqa: BLE001 - release every owned resource.
                errors.append(error)
            else:
                self._ioc_config_subscriptions.remove((signal, token))
        for cleanup in (
            lambda: self._ioc_config_executor.shutdown(wait=True, cancel_futures=True),
            self._unsubscribe_all_stats,
            super().destroy,
        ):
            try:
                cleanup()
            except Exception as error:  # noqa: BLE001 - finish cleanup before reporting.
                errors.append(error)
        if errors:
            for error in errors[1:]:
                errors[0].add_note(f"Additional ROI cleanup failure: {error!r}")
            raise errors[0]

    def _on_config_update(self, value: ROIConfigurationMessage, **kwargs) -> None:
        """
        Apply a complete rectangle and processing selection to the paired IOC plugins.

        Validate before any changes, then serialize against IOC readback refreshes.
        Apply geometry and plugin processing controls before recording the requested
        state. The request path publishes configuration only after this
        method returns successfully. IOC writes are not transactional: if a later
        write fails, earlier writes remain applied and IOC observers reconcile the
        resulting backend state. The failed request is never published as successful.

        Args:
            value (ROIConfigurationMessage): Complete configuration whose roi_config must
                be a RectROIConfig and whose operations must be supported by AD Stats.
            **kwargs (Any): Application context forwarded to ROIProcessing.

        Raises:
            TypeError: The requested shape is not rectangular.
            ValueError: The target or processing selection is invalid.
            Exception: Applying IOC geometry or processing controls fails.
        """
        self.update_received.check_value(value)
        with self._ioc_config_lock:
            self._apply_roi_configuration(cast(RectROIConfig, value.roi_config))
            self._apply_stats_enable_signals(value)
            # Record confirmed state only after every backend write succeeds.
            super()._on_config_update(value, **kwargs)
            self._sync_stats_subscriptions(apply_enable=False)

    def _ioc_configuration_signals(self) -> dict[str, Any]:
        """
        Identify IOC readbacks needed to reconstruct the current ROI configuration.

        Returns:
            dict[str, Any]: Geometry, ROI/Stats enablement and per-operation control names
                mapped to their backend signals. Reading these values is left to the caller.
        """
        return {
            "x": self.roi1.min_xyz.min_x,
            "y": self.roi1.min_xyz.min_y,
            "width": self.roi1.size.x,
            "height": self.roi1.size.y,
            "roi_enabled": self.roi1.enable,
            "stats_enabled": self.stats1.enable,
            **{
                operation: getattr(self.stats1, cast(str, config["enable_signal"]))
                for operation, config in NDPLUGIN_STATS_CONFIG.items()
            },
        }

    def _on_ioc_configuration_changed(self, **kwargs) -> None:
        """
        Schedule a coalesced configuration refresh after an IOC monitor event.

        Mark the readback state dirty and submit at most one executor job. Perform no
        backend reads or Redis publication in the monitor callback itself. Events received
        while closing are ignored.

        Args:
            **kwargs (Any): IOC subscription metadata; only the arrival of the event matters.
        """
        with self._ioc_pending_lock:
            if self._ioc_config_closed:
                return
            self._ioc_sync_dirty = True
            if self._ioc_sync_pending:
                return
            self._ioc_sync_pending = True
            self._ioc_config_executor.submit(self._drain_ioc_configuration)

    def _drain_ioc_configuration(self) -> None:
        """
        Refresh confirmed configuration until all coalesced monitor events are consumed.

        Run on the owned configuration executor and serialize with complete request
        application. Stop when the component closes or no refresh is pending. Read or
        publication failures are logged so later monitor events can still be processed.
        """
        while True:
            with self._ioc_pending_lock:
                if self._ioc_config_closed or not self._ioc_sync_dirty:
                    self._ioc_sync_pending = False
                    return
                self._ioc_sync_dirty = False
            try:
                with self._ioc_config_lock:
                    self._read_ioc_configuration()
            except Exception as error:  # noqa: BLE001 - observer boundary; survive IOC disconnects.
                logger.warning(f"Could not refresh {self.name} IOC configuration: {error}")

    def _read_ioc_configuration(self) -> None:
        """
        Reconstruct and publish confirmed IOC configuration without echoing PV writes.

        Read the geometry and enablement signals, build one RectROIConfig and update
        locally recorded state under the caller's configuration lock. When enabled, also
        refresh the operation selection. Publish only when state changed; standalone
        subscriptions are adjusted without reapplying enable controls.

        Raises:
            Exception: Reading IOC configuration or publishing changed state fails.
        """
        values = {}
        for key, signal in self._ioc_configuration_signals().items():
            if self._ioc_config_closed:
                return
            values[key] = signal.get(timeout=3, use_monitor=True)
        if self._ioc_config_closed:
            return

        def enabled(value: Any) -> bool:
            return value in (1, "1", "Enable", "Yes")

        active = enabled(values.pop("roi_enabled")) and enabled(values.pop("stats_enabled"))
        geometry = RectROIConfig(**{key: int(values[key]) for key in ("x", "y", "width", "height")})
        settings: dict[str, Any] = {"active": active}
        if active:
            settings["selected_operations"] = [
                operation for operation in NDPLUGIN_STATS_CONFIG if enabled(values[operation])
            ]
        changed = geometry != self._roi_config
        if changed:
            self._record_geometry(geometry)
        for key, value in settings.items():
            signal = getattr(self, key)
            if signal.get() != value:
                Signal.put(signal, value, force=True)
                changed = True
        if changed:
            if self.manage_capture:
                self._sync_stats_subscriptions(apply_enable=False)
            self._publish_configuration()

    def _apply_roi_configuration(self, config: RectROIConfig | None = None) -> None:
        """
        Write rectangular geometry to this component's IOC ROI plugin.

        Use explicit config when applying a request before its state is recorded. Without
        an argument, apply the locally stored rectangle, as during connection setup.
        The owning request/connection path handles publication separately.

        Args:
            config (RectROIConfig | None): Rectangle containing native-pixel x/y offsets
                and width/height. None uses the component's stored configuration.

        Raises:
            Exception: Reading or writing an IOC geometry signal fails or times out.
        """
        config = config if config is not None else cast(RectROIConfig, self._roi_config)
        timeout = getattr(self.root, "io_timeout", 3.0)
        for signal, value in (
            (self.roi1.min_xyz.min_x, config.x),
            (self.roi1.min_xyz.min_y, config.y),
            (self.roi1.size.x, config.width),
            (self.roi1.size.y, config.height),
        ):
            signal.put(int(value), timeout=timeout, wait=True)

    def _desired_stats_outputs(
        self,
    ) -> dict[str, tuple[str, str, Literal["scalar", "waveform"], str]]:
        """
        Resolve result subscriptions required by the currently selected operations.

        Returns:
            dict[str, tuple[str, str, Literal["scalar", "waveform"], str]]: Entries keyed by
                operation.result_name. Each tuple contains operation, short result name,
                output kind and dotted backend signal path. Outputs without a source path
                are omitted.
        """
        desired = {}
        for operation in self.selected_operations.get():
            config = NDPLUGIN_STATS_CONFIG.get(operation)
            if not config:
                continue
            source_signals = config.get("source_signals", {})
            for result_name in config.get("scalar_outputs", []):
                dotted_name = source_signals.get(result_name)
                if dotted_name:
                    key = f"{operation}.{result_name}"
                    desired[key] = (operation, result_name, "scalar", dotted_name)
            for result_name in config.get("waveform_outputs", []):
                dotted_name = source_signals.get(result_name)
                if dotted_name:
                    key = f"{operation}.{result_name}"
                    desired[key] = (operation, result_name, "waveform", dotted_name)
        return desired

    def _resolve_stats_signal(self, dotted_name: str) -> Any:
        """
        Look up a configured result path on the paired Stats plugin.

        Args:
            dotted_name (str): Signal path relative to stats1, including nested components.

        Returns:
            Any | None: Resolved signal, or None when the path is absent. Missing paths
                are logged and recorded in _missing_stats_paths for diagnostics.
        """
        signal = rgetattr(self.stats1, dotted_name, None)
        if signal is None:
            logger.warning(f"Could not resolve StatsPlugin signal: {dotted_name}")
            self._missing_stats_paths.add(dotted_name)
        return signal

    def _sync_stats_subscriptions(self, *, apply_enable: bool = True) -> None:
        """
        Reconcile standalone result callbacks with selected processing operations.

        Subscribe newly selected outputs and remove obsolete callbacks. Camera-managed
        ROIs remove all standalone result subscriptions so camera capture remains their
        sole scan publisher. Optionally update IOC ROI/Stats and operation enable controls.

        Args:
            apply_enable (bool): True to write enable controls after reconciliation. False
                updates subscriptions only, as when accepting observed IOC configuration.
        """
        if not self.manage_capture:
            self._unsubscribe_all_stats()
            if apply_enable:
                self._apply_stats_enable_signals()
            return
        desired = self._desired_stats_outputs()

        for key in set(self._stats_subscriptions) - set(desired):
            subscription = self._stats_subscriptions.pop(key)
            subscription.signal.unsubscribe(subscription.callback_id)
            logger.info(
                f"Unsubscribed from StatsPlugin output {subscription.operation}.{subscription.result_name} ({subscription.output_kind})"
            )

        for key, (operation, result_name, output_kind, dotted_name) in desired.items():
            if key in self._stats_subscriptions:
                continue
            signal = self._resolve_stats_signal(dotted_name)
            if signal is None:
                continue
            callback = partial(
                self._on_stats_signal_update,
                operation=operation,
                result_name=result_name,
                output_kind=output_kind,
            )
            callback_id = signal.subscribe(callback, event_type=signal.SUB_VALUE, run=False)
            self._stats_subscriptions[key] = StatsSubscription(
                signal=signal,
                callback_id=callback_id,
                operation=operation,
                result_name=result_name,
                output_kind=output_kind,
            )
            logger.info(
                f"Subscribed to StatsPlugin output {operation}.{result_name} ({output_kind})"
            )

        if apply_enable:
            self._apply_stats_enable_signals()

    def _unsubscribe_all_stats(self) -> None:
        """
        Remove every standalone result callback and clear its subscription bookkeeping.

        This does not stop IOC capture or alter plugin enablement. Callers handle those
        operations separately when stopping acquisition or changing ownership.
        """
        errors = []
        for key, subscription in tuple(self._stats_subscriptions.items()):
            try:
                subscription.signal.unsubscribe(subscription.callback_id)
            except Exception as error:  # noqa: BLE001 - remove every result subscription.
                errors.append(error)
            else:
                self._stats_subscriptions.pop(key)
        if errors:
            for error in errors[1:]:
                errors[0].add_note(f"Additional Stats unsubscribe failure: {error!r}")
            raise errors[0]

    def _apply_stats_enable_signals(
        self, configuration: ROIConfigurationMessage | None = None
    ) -> None:
        """
        Apply ROI/Stats enablement and the selected operation controls to the IOC.

        The active signal enables or disables both paired plugins. Operation controls are
        enabled only when the ROI is active and the corresponding operation is selected.
        Unavailable optional operation controls are skipped. Configuration I/O uses the
        root's io_timeout, or three seconds when that setting is absent.

        Args:
            configuration (ROIConfigurationMessage | None): Proposed state to apply
                before recording it locally. None uses the current applied state.

        Raises:
            Exception: Reading or writing an available IOC control fails.
        """
        configuration = (
            configuration if configuration is not None else self._configuration_message()
        )
        timeout = getattr(self.root, "io_timeout", 3.0)
        enabled = configuration.active
        self.roi1.enable.put("Enable" if enabled else "Disable", timeout=timeout, wait=True)
        self.stats1.enable.put("Enable" if enabled else "Disable", timeout=timeout, wait=True)
        selected_operations = set(configuration.selected_operations) if enabled else set()
        for operation, config in NDPLUGIN_STATS_CONFIG.items():
            enable_signal = config.get("enable_signal")
            if enable_signal is None:
                continue
            signal = rgetattr(self.stats1, enable_signal, None)  # Check if the attribute exists
            if signal is None:
                continue
            signal.put(
                "Yes" if operation in selected_operations else "No", timeout=timeout, wait=True
            )

    def _on_stats_signal_update(
        self,
        *,
        operation: str,
        result_name: str,
        output_kind: Literal["scalar", "waveform"],
        value,
        timestamp=None,
        **kwargs,
    ) -> None:
        """
        Publish one standalone Stats update to its scalar or waveform result signal.

        Ignore inactive/unselected operations and updates arriving before scan information
        is available. When per-trigger averaging is enabled, reduce incoming frame arrays
        before publishing and size the dynamic stream for one result per scan position.
        Camera-managed ROI capture does not install these callbacks.

        Args:
            operation (str): Analysis operation owning the update.
            result_name (str): Short result key in the outgoing DynamicSignal message.
            output_kind (Literal["scalar", "waveform"]): Destination result stream.
            value (Any): Backend scalar or array, possibly containing several frame samples.
            timestamp (float | None): Result time in seconds. None uses the current time;
                a supplied zero timestamp is preserved.
            **kwargs (Any): Additional backend subscription metadata; unused here.
        """
        if not self._is_operation_active(operation):
            return
        if not self.scan_server_scan_info:
            return

        n_points = int(
            len(self.scan_server_scan_info.positions)
            * self.scan_server_scan_info.frames_per_trigger
        )
        if self.average_frames_per_trigger.get() is True:
            n_points = len(self.scan_server_scan_info.positions)
            samples = np.asarray(value)
            if samples.size == 0:
                return
            if samples.ndim > 0:
                value = np.mean(samples, axis=0)
            if output_kind == "scalar":
                value = float(value)

        if output_kind == "scalar":
            async_update = {"type": "add", "max_shape": [n_points]}
            self.result_scalar.put(
                {
                    result_name: {
                        "value": value,
                        "timestamp": timestamp if timestamp is not None else time(),
                    }
                },
                async_update=async_update,
            )
        else:
            async_update = {"type": "add", "max_shape": [n_points, None]}
            self.result_waveform.put(
                {
                    result_name: {
                        "value": value,
                        "timestamp": timestamp if timestamp is not None else time(),
                    }
                },
                async_update=async_update,
            )

    def _is_operation_active(self, operation: str) -> bool:
        """
        Check whether an operation is both selected and enabled for this ROI.

        Args:
            operation (str): Operation name to inspect.

        Returns:
            bool: True when the ROI is active and operation is selected.
        """
        return bool(self.active.get()) and operation in self.selected_operations.get()

    ################
    ## Scan Hooks ##
    ################

    def on_stage(self):
        """
        Prepare scan information and fixed-burst capacity for standalone ROI capture.

        When manage_capture is True, resolve scan information from the root and configure
        TSNumPoints from frames_per_trigger. Camera-managed components do nothing here;
        the camera's acquisition components explicitly arm their buffers.

        Raises:
            Exception: Resolving scan information or configuring buffer capacity fails.
        """
        if not self.manage_capture:
            return
        self.scan_server_scan_info = fetch_scan_info(self.root.scan_info)
        self.stats1.ts_num_points.put(
            self.scan_server_scan_info.frames_per_trigger, wait=True, timeout=2
        )

    def on_trigger(self) -> TransitionStatus | None:
        """
        Start one standalone time-series capture and return its completion status.

        The caller must arm ROI capture before starting detector input. Camera-managed
        components return None because their camera controls arming and publication.

        Returns:
            TransitionStatus | None: Standalone acquiring-to-idle acknowledgement, or None
                when manage_capture is False.
        """
        if not self.manage_capture:
            return None
        # TODO add hook, needs to be triggered before the detector acquire starts if it is triggered manually.
        status = TransitionStatus(self.stats1.ts_acquire_status, transitions=[1, 0])
        self.stats1.ts_acquire.put(1)  # Start timestamp acquisition
        return status

    def on_stop(self):
        """
        Request that standalone time-series capture stop.

        Send TSAcquire=0 only when manage_capture is True. Camera-managed acquisition
        uses the explicit stop_capture() operation from its owning camera's stop path.
        """
        if self.manage_capture:
            self.stats1.ts_acquire.put(0)  # Stop timestamp acquisition

    def on_destroy(self):
        """
        Remove standalone Stats result callbacks when the owning device requests cleanup.

        This hook releases result subscriptions only. destroy() additionally closes IOC
        configuration observation and shared request-signal resources.
        """
        self._unsubscribe_all_stats()
