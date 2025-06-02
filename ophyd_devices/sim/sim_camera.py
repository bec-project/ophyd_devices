"""Simulated 2D camera device"""

import numpy as np
from bec_lib.logger import bec_logger
from ophyd import Component as Cpt
from ophyd import Device, Kind, StatusBase

from ophyd_devices.interfaces.base_classes.psi_device_base import PSIDeviceBase
from ophyd_devices.sim.sim_data import SimulatedDataCamera
from ophyd_devices.sim.sim_signals import ReadOnlySignal, SetableSignal
from ophyd_devices.sim.sim_utils import H5Writer
from ophyd_devices.utils.bec_signals import PreviewSignal

logger = bec_logger.logger


class SimCameraControl(Device):
    """SimCamera Control layer"""

    USER_ACCESS = ["sim", "registered_proxies"]

    sim_cls = SimulatedDataCamera
    SHAPE = (100, 100)
    BIT_DEPTH = np.uint16

    SUB_MONITOR = "device_monitor_2d"
    _default_sub = SUB_MONITOR

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
    name (string)           : Name of the device. This is the only required argmuent, passed on to all signals of the device.
    precision (integer)     : Precision of the readback in digits, written to .describe(). Default is 3 digits.
    sim_init (dict)         : Dictionary to initiate parameters of the simulation, check simulation type defaults for more details.
    parent                  : Parent device, optional, is used internally if this signal/device is part of a larger device.
    kind                    : A member the Kind IntEnum (or equivalent integer), optional. Default is Kind.normal. See Kind for options.

    """

    def __init__(self, name: str, scan_info=None, device_manager=None, **kwargs):
        super().__init__(name=name, scan_info=scan_info, device_manager=device_manager, **kwargs)
        self.file_path = None

    def on_trigger(self) -> StatusBase:
        """Trigger the camera to acquire images.

        This method can be called from BEC during a scan. It will acquire images and send them to BEC.
        Whether the trigger is send from BEC is determined by the softwareTrigger argument in the device config.

        Here, we also run a callback on SUB_MONITOR to send the image data the device_monitor endpoint in BEC.
        """

        def trigger_cam() -> None:
            """Trigger the camera to acquire images."""
            for _ in range(self.burst.get()):
                data = self.image.get()
                # pylint: disable=protected-access
                self.preview.put(data)
                self._run_subs(sub_type=self.SUB_MONITOR, value=data)
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
            # pylint: disable=protected-access
            self._run_subs(
                sub_type=self.SUB_FILE_EVENT,
                file_path=self.file_path,
                done=False,
                successful=False,
                hinted_location={"data": "/entry/data/data"},
            )

    def on_complete(self) -> StatusBase:
        """Complete the motion of the simulated device."""

        if not self.write_to_disk.get():
            return None

        def complete_cam():
            """Complete the camera acquisition."""
            self.h5_writer.on_complete()
            self._run_subs(
                sub_type=self.SUB_FILE_EVENT,
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
