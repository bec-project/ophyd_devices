"""Simulated 2D camera device"""

import numpy as np
from bec_lib.logger import bec_logger
from ophyd import Component as Cpt
from ophyd import Device, Kind, StatusBase

from ophyd_devices.interfaces.base_classes.psi_device_base import PSIDeviceBase
from ophyd_devices.sim.sim_data import SimulatedDataCamera
from ophyd_devices.sim.sim_signals import ReadOnlySignal, SetableSignal
from ophyd_devices.sim.sim_utils import H5Writer
from ophyd_devices.utils.bec_roi_signals import LITERAL_ROI_PROCESSING_CONFIG, ROIProcessing
from ophyd_devices.utils.bec_signals import FileEventSignal, PreviewSignal

logger = bec_logger.logger

SIM_CONFIG: LITERAL_ROI_PROCESSING_CONFIG = {
    "basic_statistics": {
        "scalar_outputs": ["sum", "mean", "min", "max"],
        "waveform_outputs": [],
        "enable_signal": None,
        "source_signals": {},
    }
}


class SimCameraROIProcessing(ROIProcessing):
    """ROI processing signal for simulated camera setups."""

    def get_scalar_outputs(self) -> list[str]:
        scalar_outpus = []
        for v in SIM_CONFIG.values():
            scalar_outpus.extend(v["scalar_outputs"])
        return scalar_outpus

    def get_waveform_outputs(self) -> list[str]:
        waveform_outputs = []
        for v in SIM_CONFIG.values():
            waveform_outputs.extend(v["waveform_outputs"])
        return waveform_outputs

    def get_available_analysis_operations(self) -> list[str]:
        return list(SIM_CONFIG.keys())

    def wait_for_connection(self, *args, **kwargs):
        super().wait_for_connection(*args, **kwargs)
        self.parent.image.subscribe(
            self._on_image_update, event_type=self.parent.image.SUB_VALUE, run=False
        )

    def _on_image_update(self, value, **kwargs):
        """Callback for image updates."""
        if not self.active.get():
            return  # Do nothing if not enabled

        if not isinstance(value, np.ndarray):
            logger.warning(f"Received non-numpy array value: {value}")
            return  # Do nothing if not numpy array
        if "basic_statistics" not in self.selected_operations.get():
            return
        roi_image = self._extract_roi(value)
        if roi_image.size == 0:
            logger.warning(f"ROI {self.roi_name.get()} is outside image bounds or has zero size.")
            return
        self.result_scalar.put(self._compute_basic_statistics(roi_image))

    def _extract_roi(self, image: np.ndarray) -> np.ndarray:
        """Return the configured rectangular ROI clipped to the image bounds."""
        x = int(self.x.get())
        y = int(self.y.get())
        width = int(self.width.get())
        height = int(self.height.get())
        if width <= 0 or height <= 0:
            return image[0:0, 0:0]

        x0 = max(0, x)
        y0 = max(0, y)
        x1 = min(image.shape[1], x + width)
        y1 = min(image.shape[0], y + height)
        if x1 <= x0 or y1 <= y0:
            return image[0:0, 0:0]
        return image[y0:y1, x0:x1]

    def _compute_basic_statistics(self, image: np.ndarray) -> dict[str, dict[str, float]]:
        """Compute basic statistics for the given image."""
        timestamp = self.parent.image.timestamp
        values = {
            "sum": {"value": float(np.sum(image)), "timestamp": timestamp},
            "mean": {"value": float(np.mean(image)), "timestamp": timestamp},
            "min": {"value": float(np.min(image)), "timestamp": timestamp},
            "max": {"value": float(np.max(image)), "timestamp": timestamp},
        }
        return {name: values[name] for name in self.get_scalar_outputs() if name in values}


class SimCameraControl(Device):
    """SimCamera Control layer"""

    USER_ACCESS = ["sim", "registered_proxies"]

    sim_cls = SimulatedDataCamera
    SHAPE = (100, 100)
    BIT_DEPTH = np.uint16

    exp_time = Cpt(SetableSignal, name="exp_time", value=1, kind=Kind.config)
    file_pattern = Cpt(SetableSignal, name="file_pattern", value="", kind=Kind.config)
    frames = Cpt(SetableSignal, name="frames", value=1, kind=Kind.config)
    burst = Cpt(SetableSignal, name="burst", value=1, kind=Kind.config)

    image_shape = Cpt(SetableSignal, name="image_shape", value=SHAPE, kind=Kind.config)
    image = Cpt(
        ReadOnlySignal,
        name="image",
        value=np.empty(SHAPE, dtype=BIT_DEPTH),
        compute_readback=True,
        kind=Kind.omitted,
    )
    preview = Cpt(PreviewSignal, name="preview", ndim=2, num_rotation_90=0)
    file_event = Cpt(FileEventSignal)
    write_to_disk = Cpt(SetableSignal, name="write_to_disk", value=False, kind=Kind.config)

    def __init__(self, name, *, parent=None, sim_init: dict = None, device_manager=None, **kwargs):
        self.sim_init = sim_init
        self.device_manager = device_manager
        self._registered_proxies = {}
        self.sim = self.sim_cls(parent=self, **kwargs)
        self.h5_writer = H5Writer()
        super().__init__(name=name, parent=parent, **kwargs)
        if self.sim_init:
            self.sim.set_init(self.sim_init)

    @property
    def registered_proxies(self) -> None:
        """Dictionary of registered signal_names and proxies."""
        return self._registered_proxies


class SimCamera(PSIDeviceBase, SimCameraControl):
    """A simulated device mimic any 2D camera.

    It's image is a computed signal, which is configurable by the user and from the command line.
    The corresponding simulation class is sim_cls=SimulatedDataCamera, more details on defaults within the simulation class.

    >>> camera = SimCamera(name="camera")

    Parameters
    ----------
    name (string)           : Name of the device. This is the only required argument, passed on to all signals of the device.
    precision (integer)     : Precision of the readback in digits, written to .describe(). Default is 3 digits.
    sim_init (dict)         : Dictionary to initiate parameters of the simulation, check simulation type defaults for more details.
    parent                  : Parent device, optional, is used internally if this signal/device is part of a larger device.
    kind                    : A member the Kind IntEnum (or equivalent integer), optional. Default is Kind.normal. See Kind for options.

    """

    roi_processing = Cpt(
        SimCameraROIProcessing,
        name="roi_processing",
        active=True,
        x=25,
        y=25,
        width=50,
        height=50,
        selected_operations=["basic_statistics"],
        kind=Kind.normal,
    )

    def __init__(self, name: str, scan_info=None, device_manager=None, **kwargs):
        super().__init__(name=name, scan_info=scan_info, device_manager=device_manager, **kwargs)
        self.file_path = None

    def on_trigger(self) -> StatusBase:
        """Trigger the camera to acquire images.

        This method can be called from BEC during a scan. It will acquire images and send them to BEC using the
        preview signal. Whether the device receives a trigger from BEC or not is determined by the softwareTrigger
        parameter in the device configuration. If softwareTrigger is set to True, the device will receive a trigger
        from BEC and acquire images.
        """

        def trigger_cam() -> None:
            """Trigger the camera to acquire images."""
            for _ in range(self.burst.get()):
                data = self.image.get()
                # pylint: disable=protected-access
                self.preview.put(data)
                if self.write_to_disk.get():
                    self.h5_writer.receive_data(data)

        status = self.task_handler.submit_task(trigger_cam)
        return status

    def on_stage(self) -> None:
        """Stage the camera for upcoming scan

        This method is called from BEC in preparation of a scan.
        It receives metadata about the scan from BEC,
        compiles it and prepares the camera for the scan.

        FYI: No data is written to disk in the simulation, but upon each trigger it
        is published to the device_monitor endpoint in REDIS.
        """
        self.file_path = self.file_utils.get_full_path(
            scan_status_msg=self.scan_info.msg, name=self.name
        )
        self.frames.set(
            self.scan_info.msg.num_points * self.scan_info.msg.scan_parameters["frames_per_trigger"]
        ).wait()
        self.exp_time.set(self.scan_info.msg.scan_parameters["exp_time"]).wait()
        self.burst.set(self.scan_info.msg.scan_parameters["frames_per_trigger"]).wait()
        if self.write_to_disk.get():
            self.h5_writer.on_stage(file_path=self.file_path, h5_entry="/entry/data/data")
            self.file_event.put(
                file_path=self.file_path,
                done=False,
                successful=False,
                hinted_h5_entries={"data": "/entry/data/data"},
            )

    def on_complete(self) -> StatusBase:
        """Complete the motion of the simulated device."""

        if not self.write_to_disk.get():
            return None

        def complete_cam():
            """Complete the camera acquisition."""
            self.h5_writer.on_complete()
            self.file_event.put(
                file_path=self.file_path,
                done=True,
                successful=True,
                hinted_location={"data": "/entry/data/data"},
            )

        status = self.task_handler.submit_task(complete_cam)
        return status

    def on_unstage(self) -> None:
        """Unstage the camera device."""
        if self.write_to_disk.get():
            self.h5_writer.on_unstage()

    def on_stop(self) -> None:
        """Stop the camera acquisition."""
        self.task_handler.shutdown()
        self.on_unstage()
