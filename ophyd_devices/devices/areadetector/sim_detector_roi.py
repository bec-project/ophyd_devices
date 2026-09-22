"""
Simulated AreaDetector (ADSimDetector IOC) with a BEC ROI processing component.

This is the test vehicle for :class:`~ophyd_devices.utils.bec_roi_signals.ad_roi_signal.ADROIProcessing`
against a running ADSimDetector IOC. It forwards the scan hooks to the ROI component and publishes
the image plugin data as preview. Camera acquisition itself is not started by ``on_trigger``;
run the simulated detector in continuous mode on the IOC.
"""

from __future__ import annotations

import threading
import traceback
from typing import TYPE_CHECKING

import numpy as np
from bec_lib.logger import bec_logger
from ophyd import ADBase
from ophyd import Component as Cpt

from ophyd_devices.devices.areadetector.cam import SimDetectorCam
from ophyd_devices.devices.areadetector.plugins import ImagePlugin_V35 as ImagePlugin
from ophyd_devices.interfaces.base_classes.psi_device_base import PSIDeviceBase
from ophyd_devices.utils.bec_roi_signals.ad_roi_signal import ADROIProcessing
from ophyd_devices.utils.bec_signals import PreviewSignal

if TYPE_CHECKING:
    from bec_lib.devicemanager import ScanInfo
    from bec_server.device_server.devices.devicemanager import DeviceManagerDS

logger = bec_logger.logger


class SimDetectorROI(PSIDeviceBase, ADBase):
    """ADSimDetector with one ROI/Stats processing chain exposed to BEC."""

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

    def on_connected(self):
        """Start polling the image plugin for previews."""
        if not self._poll_thread.is_alive():
            self._poll_thread.start()

    def _poll_array_data(self):
        """Poll the array data for preview updates."""
        while not self._poll_thread_kill_event.wait(1 / self._poll_rate):
            try:
                unique_id = self.image.unique_id.get()
                if unique_id == self._unique_array_id:
                    continue  # No new image, skip update
                self._unique_array_id = unique_id
                value = self.image.array_data.get()
                if value is None:
                    logger.debug(f"No image data available for preview of {self.name}")
                    continue
                width = self.image.array_size.width.get()
                height = self.image.array_size.height.get()
                self.preview.put(np.reshape(value, (height, width)))
            except Exception:  # pylint: disable=broad-except
                content = traceback.format_exc()
                logger.error(
                    f"Error while polling array data for preview of {self.name}: {content}"
                )

    def on_stage(self):
        """Stage the ROI processing (time series length)."""
        return self.roi_processing.on_stage()

    def on_trigger(self):
        """Start the time series acquisition of the Stats plugin and return its status."""
        return self.roi_processing.on_trigger()

    def on_stop(self):
        """Stop the time series acquisition."""
        self.roi_processing.on_stop()

    def on_destroy(self):
        """Clean up resources."""
        self.roi_processing.on_destroy()
        self._poll_thread_kill_event.set()
        if self._poll_thread.is_alive():
            self._poll_thread.join(timeout=0.5)
