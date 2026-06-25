from __future__ import annotations

from dataclasses import dataclass
from functools import partial
from typing import Any, Literal

import numpy as np
from bec_lib.logger import bec_logger
from bec_lib.utils.rpc_utils import rgetattr
from ophyd import Component as Cpt
from ophyd import Device

from ophyd_devices.devices.areadetector.plugins import ROIPlugin_V35, StatsPlugin_V35
from ophyd_devices.utils.bec_roi_signals.roi_processing import (
    LITERAL_ROI_PROCESSING_CONFIG,
    ROIProcessing,
)


class StatsPlugin(StatsPlugin_V35):
    # plugin_type = None
    # codec = None
    # compressed_size = None


class ROIPlugin(ROIPlugin_V35):
    # plugin_type = None
    # codec = None
    # compressed_size = None


logger = bec_logger.logger


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
            "min",
            "min_x",
            "min_y",
            "max",
            "max_x",
            "max_y",
            "mean",
            "total",
            "net",
            "sigma",
        ],
        "waveform_outputs": [],
        "source_signals": {
            "min": "min_value",
            "min_x": "min_xy.x",
            "min_y": "min_xy.y",
            "max": "max_value",
            "max_x": "max_xy.x",
            "max_y": "max_xy.y",
            "mean": "mean_value",
            "total": "total",
            "net": "net",
            "sigma": "sigma_readout",
        },
    },
    "centroid": {
        "enable_signal": "compute_centroid",
        "scalar_outputs": [
            "centroid_total",
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
            "centroid_total": "centroid_total",
            "centroid_x": "centroid.x",
            "centroid_y": "centroid.y",
            "sigma_x": "sigma_x",
            "sigma_y": "sigma_y",
            "sigma_xy": "sigma_xy",
            "skew_x": "skew.x",
            "skew_y": "skew.y",
            "kurtosis_x": "kurtosis.x",
            "kurtosis_y": "kurtosis.y",
            "eccentricity": "eccentricity",
            "orientation": "orientation",
        },
    },
    "profiles": {
        "enable_signal": "compute_profiles",
        "scalar_outputs": ["profile_size_x", "profile_size_y", "cursor_x", "cursor_y"],
        "waveform_outputs": [
            "profile_average_x",
            "profile_average_y",
            "profile_threshold_x",
            "profile_threshold_y",
            "profile_centroid_x",
            "profile_centroid_y",
            "profile_cursor_x",
            "profile_cursor_y",
        ],
        "source_signals": {
            "profile_size_x": "profile_size.x",
            "profile_size_y": "profile_size.y",
            "cursor_x": "cursor.x",
            "cursor_y": "cursor.y",
            "profile_average_x": "profile_average.x",
            "profile_average_y": "profile_average.y",
            "profile_threshold_x": "profile_threshold.x",
            "profile_threshold_y": "profile_threshold.y",
            "profile_centroid_x": "profile_centroid.x",
            "profile_centroid_y": "profile_centroid.y",
            "profile_cursor_x": "profile_cursor.x",
            "profile_cursor_y": "profile_cursor.y",
        },
    },
    "histogram": {
        "enable_signal": "compute_histogram",
        "scalar_outputs": ["hist_below", "hist_above", "hist_entropy"],
        "waveform_outputs": ["histogram", "histogram_x"],
        "source_signals": {
            "hist_below": "hist_below",
            "hist_above": "hist_above",
            "hist_entropy": "hist_entropy",
            "histogram": "histogram",
            "histogram_x": "histogram_x",
        },
    },
}


class ADROIProcessing(ROIProcessing):
    """ROI processing signal for AD detector setups at PSI."""

    roi1 = Cpt(ROIPlugin, "ROI1:", kind="normal")
    stats1 = Cpt(StatsPlugin, "STATS1:", kind="normal")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._stats_subscriptions: dict[str, StatsSubscription] = {}
        self._missing_stats_paths: set[str] = set()
        self._config_update_in_progress = False

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
        # ROIPlugin related callbacks
        self.selected_operations.subscribe(
            self._on_processing_selection_update,
            event_type=self.selected_operations.SUB_VALUE,
            run=False,
        )
        self._apply_roi_configuration()
        self._sync_stats_subscriptions()

    def destroy(self):
        self._unsubscribe_all_stats()
        super().destroy()

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

    def _sync_stats_subscriptions(self) -> None:
        """Subscribe to selected StatsPlugin outputs and unsubscribe stale ones."""
        desired = self._desired_stats_outputs()

        for key in set(self._stats_subscriptions) - set(desired):
            subscription = self._stats_subscriptions.pop(key)
            subscription.signal.unsubscribe(subscription.callback_id)

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

        self._apply_stats_enable_signals()

    def _desired_stats_outputs(
        self,
    ) -> dict[str, tuple[str, str, Literal["scalar", "waveform"], str]]:
        if not self.active.get():
            return {}

        selected_operations = set(self.selected_operations.get())
        desired = {}
        for operation, config in NDPLUGIN_STATS_CONFIG.items():
            if operation not in selected_operations:
                continue
            source_signals = config.get("source_signals", {})
            for result_name in config.get("scalar_outputs", []):
                signal_path = source_signals[result_name]
                desired[f"scalar:{operation}:{result_name}"] = (
                    operation,
                    result_name,
                    "scalar",
                    signal_path,
                )
            for result_name in config.get("waveform_outputs", []):
                signal_path = source_signals[result_name]
                desired[f"waveform:{operation}:{result_name}"] = (
                    operation,
                    result_name,
                    "waveform",
                    signal_path,
                )
        return desired

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
            signal = self._resolve_stats_signal(enable_signal)
            if signal is None:
                continue
            signal.put("Yes" if operation in selected_operations else "No")

    def _resolve_stats_signal(self, signal_path: str):
        """Resolve a dotted StatsPlugin attribute path to an ophyd signal."""
        try:
            signal = rgetattr(self.stats1, signal_path)  # Check if the attribute exists
        except AttributeError:
            if signal_path not in self._missing_stats_paths:
                logger.warning(
                    "StatsPlugin signal path %s is not available on %s.",
                    signal_path,
                    self.stats1.__class__.__name__,
                )
                self._missing_stats_paths.add(signal_path)
            return None
        return signal

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

        signal = self.result_scalar if output_kind == "scalar" else self.result_waveform
        signal.put({result_name: {"value": value, "timestamp": timestamp or self._get_timestamp()}})

    def _is_operation_active(self, operation: str) -> bool:
        return bool(self.active.get()) and operation in self.selected_operations.get()


import threading
import traceback

from ophyd import ADBase

from ophyd_devices import PreviewSignal, PSIDeviceBase
from ophyd_devices.devices.areadetector.cam import SimDetectorCam
from ophyd_devices.devices.areadetector.plugins import ImagePlugin_V35 as ImagePlugin


class MyDetector(PSIDeviceBase, ADBase):
    cam = Cpt(SimDetectorCam, "cam1:")
    image = Cpt(ImagePlugin, "image1:")
    roi_processing = Cpt(ADROIProcessing, "", kind="normal")

    preview = Cpt(
        PreviewSignal,
        name="preview",
        ndim=2,
        num_rotation_90=0,
        doc="Preview signal for the camera.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
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
