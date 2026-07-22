"""Custom ROI processing Device for AreaDetector ROI/Stats plugin processing."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from enum import IntEnum
from functools import partial
from time import time
from typing import Any, Literal

import numpy as np
from bec_lib.devicemanager import ScanInfo
from bec_lib.logger import bec_logger
from bec_lib.utils.rpc_utils import rgetattr
from bec_server.scan_server.scans.scan_base import ScanInfo as ScanServerScanInfo
from ophyd import Component as Cpt
from ophyd import EpicsSignal, EpicsSignalRO, Kind, Signal
from pydantic import ValidationError

from ophyd_devices import TransitionStatus
from ophyd_devices.devices.areadetector.plugins import ROIPlugin_V35 as ROIPlugin
from ophyd_devices.devices.areadetector.plugins import StatsPlugin_V35
from ophyd_devices.utils.bec_roi_signals.roi_processing import (
    LITERAL_ROI_PROCESSING_CONFIG,
    ROIProcessing,
)

"""Utility functions for the devices."""


def fetch_scan_info(scan_info: ScanInfo) -> ScanServerScanInfo:
    """Fetch the scan parameters from the scan_info object and return them as a ScanServerScanInfo object."""
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
    """Enum for TSAcquireMode values."""

    FIXED_LENGTH = 0
    CIRCULAR_BUFFER = 1


class TSReadMode(IntEnum):
    """Enum for TSReadMode values. Recommend to use PASSIVE mode for most applications."""

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
    """StatsPlugin with additional timestamp control signals."""

    ts_acquire_status = Cpt(EpicsSignalRO, "TS:TSAcquiring", kind=Kind.omitted, auto_monitor=True)
    ts_acquire = Cpt(EpicsSignal, "TS:TSAcquire", kind=Kind.omitted)
    ts_acquire_mode = Cpt(EpicsSignal, "TS:TSAcquireMode", kind=Kind.omitted)
    ts_read_mode = Cpt(EpicsSignal, "TS:TSRead.SCAN", kind=Kind.omitted)
    ts_read = Cpt(EpicsSignal, "TS:TSRead.PROC", kind=Kind.omitted)
    ts_current_index = Cpt(EpicsSignalRO, "TS:TSCurrentPoint", kind=Kind.omitted)
    ts_num_points = Cpt(EpicsSignalRO, "TS:TSNumPoints", kind=Kind.omitted, auto_monitor=True)


@dataclass
class StatsSubscription:
    """Bookkeeping for callbacks subscribed to StatsPlugin output signals."""

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
    """Signal to compute the average number of frames per trigger."""

    def put(self, value, **kwargs):
        if not isinstance(value, (bool, int, float)):
            raise ValueError("average_frames_per_trigger must be a boolean or numeric value.")
        value = bool(value)
        super().put(value, **kwargs)


class ADROIProcessing(ROIProcessing):
    """ROI processing signal for AD detector setups at PSI."""

    roi1 = Cpt(ROIPlugin, "ROI1:", kind="normal")
    stats1 = Cpt(StatsPluginWithTSControl, "Stats1:", kind="normal")
    average_frames_per_trigger = Cpt(
        AverageFramesForEachTrigger, name="average_frames_per_trigger", kind=Kind.config, value=True
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._stats_subscriptions: dict[str, StatsSubscription] = {}
        self._missing_stats_paths: set[str] = set()
        self._config_update_in_progress = False
        self.scan_server_scan_info: ScanServerScanInfo | None = None

    def get_scalar_outputs(self) -> list[str]:
        scalar_outputs = []
        for config in NDPLUGIN_STATS_CONFIG.values():
            scalar_outputs.extend(config.get("scalar_outputs", []))
        return scalar_outputs

    def get_waveform_outputs(self) -> list[str]:
        waveform_outputs = []
        for config in NDPLUGIN_STATS_CONFIG.values():
            waveform_outputs.extend(config.get("waveform_outputs", []))
        return waveform_outputs

    def get_available_analysis_operations(self) -> list[str]:
        return list(NDPLUGIN_STATS_CONFIG.keys())

    def wait_for_connection(self, *args, **kwargs):
        super().wait_for_connection(*args, **kwargs)
        # Subscribe stats plugin to ROI plugin,  the self.root.cam assumes cam to be available on root object, so we trust roi1 to be properly configured.
        self.roi1.nd_array_port.put(self.root.cam.port_name.get())
        self.stats1.nd_array_port.put(self.roi1.port_name.get())
        # ROIPlugin related callbacks
        self.selected_operations.subscribe(
            self._on_processing_selection_update,
            event_type=self.selected_operations.SUB_VALUE,
            run=False,
        )
        self._apply_roi_configuration()
        self._sync_stats_subscriptions()

    def _on_config_update(self, value, **kwargs):
        self._config_update_in_progress = True
        try:
            super()._on_config_update(value, **kwargs)
        finally:
            self._config_update_in_progress = False

        self._apply_roi_configuration()
        self._sync_stats_subscriptions()

    def _on_processing_selection_update(self, *args, **kwargs) -> None:
        if self._config_update_in_progress:
            return
        self._sync_stats_subscriptions()

    def _apply_roi_configuration(self) -> None:
        """Apply the BEC ROI geometry to the AreaDetector ROI plugin."""
        self.roi1.min_xyz.min_x.put(int(self.x.get()))
        self.roi1.min_xyz.min_y.put(int(self.y.get()))
        self.roi1.size.x.put(int(self.width.get()))
        self.roi1.size.y.put(int(self.height.get()))

    def _desired_stats_outputs(
        self,
    ) -> dict[str, tuple[str, str, Literal["scalar", "waveform"], str]]:
        """Determine the desired StatsPlugin outputs based on the selected operations."""
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
        """Resolve a dotted name to an actual signal on the stats1 plugin."""
        signal = rgetattr(self.stats1, dotted_name, None)
        if signal is None:
            logger.warning(f"Could not resolve StatsPlugin signal: {dotted_name}")
            self._missing_stats_paths.add(dotted_name)
        return signal

    def _sync_stats_subscriptions(self) -> None:
        """Subscribe to selected StatsPlugin outputs and unsubscribe stale ones."""
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

        self._apply_stats_enable_signals()

    def _unsubscribe_all_stats(self) -> None:
        for subscription in self._stats_subscriptions.values():
            subscription.signal.unsubscribe(subscription.callback_id)
        self._stats_subscriptions.clear()

    def _apply_stats_enable_signals(self) -> None:
        selected_operations = set(self.selected_operations.get()) if self.active.get() else set()
        for operation, config in NDPLUGIN_STATS_CONFIG.items():
            enable_signal = config.get("enable_signal")
            if enable_signal is None:
                continue
            signal = rgetattr(self.stats1, enable_signal, None)  # Check if the attribute exists
            if signal is None:
                continue
            signal.put("Yes" if operation in selected_operations else "No")

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
        """Publish a StatsPlugin update into the matching BEC result signal."""
        if not self._is_operation_active(operation):
            return
        if self.average_frames_per_trigger.get() is True:
            if isinstance(value, (list, np.ndarray)):
                value = value / len(value)  # Average over the number of frames per trigger
            value = float(value)  # Ensure the value is a float for list and np.ndarray types

        signal = self.result_scalar if output_kind == "scalar" else self.result_waveform
        signal.put({result_name: {"value": value, "timestamp": timestamp or time.time()}})

    def _is_operation_active(self, operation: str) -> bool:
        return bool(self.active.get()) and operation in self.selected_operations.get()

    ################
    ## Scan Hooks ##
    ################

    def on_connected(self):
        """Hook called when the device is connected."""
        # TODO Consider using 'set' in future after wrapping EpicsSignal with proper set wrapper
        self.stats1.ts_acquire_mode.put(TSAcquireMode.FIXED_LENGTH.value)
        self.stats1.ts_read_mode.put(TSReadMode.PASSIVE.value)
        if self.stats1.ts_acquire_status.get() == 0:
            self.stats1.ts_acquire.put(0)  # Start timestamp acquisition

    def on_stage(self):
        """Hook called when the device is staged."""
        self.root: PSIDeviceBase
        self.scan_server_scan_info = fetch_scan_info(self.root.scan_info)
        self.stats1.ts_num_points.put(self.scan_server_scan_info.frames_per_trigger)

    def on_trigger(self) -> TransitionStatus:
        """Hook called when the device is triggered."""
        # TODO add hook, needs to be triggered before the detector acquire starts if it is triggered manually.
        status = TransitionStatus(self.stats1.ts_acquire_status, transitions=[1, 0])
        self.stats1.ts_acquire.put(1)  # Start timestamp acquisition
        return status

    def on_stop(self):
        """Hook called when the device is stopped."""
        self.stats1.ts_acquire.put(0)  # Stop timestamp acquisition

    def on_destroy(self):
        """Hook called when the device is destroyed."""
        self._unsubscribe_all_stats()


#####################
### Test Detector ###
#####################


import threading
import traceback
from typing import TYPE_CHECKING

from ophyd import ADBase

from ophyd_devices import PreviewSignal, PSIDeviceBase
from ophyd_devices.devices.areadetector.cam import SimDetectorCam
from ophyd_devices.devices.areadetector.plugins import ImagePlugin_V35 as ImagePlugin

if TYPE_CHECKING:
    from bec_lib.devicemanager import ScanInfo
    from bec_server.device_server.devices.devicemanager import DeviceManagerDS


class MyDetector(PSIDeviceBase, ADBase):
    cam = Cpt(SimDetectorCam, "cam1:")
    image = Cpt(ImagePlugin, "image1:")
    roi_processing = Cpt(
        ADROIProcessing,
        "",
        kind="normal",
        active=1,
        roi_name="roi1",
        x=400,
        y=400,
        width=100,
        height=100,
        selected_operations=["basic_statistics", "centroid"],
    )

    preview = Cpt(
        PreviewSignal,
        name="preview",
        ndim=2,
        num_rotation_90=0,
        doc="Preview signal for the camera.",
    )

    def __init__(
        self,
        *,
        name: str,
        prefix: str = "",
        scan_info: ScanInfo | None = None,
        device_manager: DeviceManagerDS | None = None,
        **kwargs,
    ):
        super().__init__(
            name=name, prefix=prefix, scan_info=scan_info, device_manager=device_manager, **kwargs
        )
        self._poll_thread_kill_event = threading.Event()
        self._poll_rate = 1.0  # Hz
        self._unique_array_id = None
        self._poll_thread = threading.Thread(
            target=self._poll_array_data, daemon=True, name=f"{self.name}_poll_thread"
        )

    def wait_for_connection(self, *args, **kwargs):
        super().wait_for_connection(*args, **kwargs)
        self._poll_thread.start()

    def _poll_array_data(self):
        """Poll the array data for preview updates."""
        while not self._poll_thread_kill_event.wait(1 / self._poll_rate):
            try:
                # First check if there is a new image
                if self.image.unique_id.get() != self._unique_array_id:
                    self._unique_array_id = self.image.unique_id.get()
                else:
                    logger.info(f"No new image for preview of {self.name}, skipping update.")
                    continue  # No new image, skip update
                # Get new image data
                value = self.image.array_data.get()
                if value is None:
                    logger.info(f"No image data available for preview of {self.name}")
                    continue

                width = self.image.array_size.width.get()
                height = self.image.array_size.height.get()
                # Geometry correction for the image
                data = np.reshape(value, (height, width))
                logger.info(f"Setting preview data for {self.name} with shape {data.shape}")
                self.preview.put(data)
            except Exception:  # pylint: disable=broad-except
                content = traceback.format_exc()
                logger.error(
                    f"Error while polling array data for preview of {self.name}: {content}"
                )

    def on_stage(self):
        """Stage the detector and prepare for acquisition."""
        self.roi_processing.on_stage()  # Stage the ROI processing

    def on_trigger(self):
        """Trigger the detector and wait for completion."""
        self.roi_processing.on_trigger()  # Start timestamp acquisition

    def on_stop(self):
        """Stop the detector and timestamp acquisition."""
        self.roi_processing.on_stop()  # Stop timestamp acquisition

    def on_destroy(self):
        """Clean up resources."""
        self.roi_processing.on_destroy()  # Stop timestamp acquisition
        self._poll_thread_kill_event.set()
        if self._poll_thread.is_alive():
            self._poll_thread.join(timeout=0.5)
