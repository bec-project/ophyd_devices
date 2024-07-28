import traceback
from threading import Thread

import numpy as np
from bec_lib.logger import bec_logger
from ophyd import Component as Cpt
from ophyd import DeviceStatus, Kind

from ophyd_devices.interfaces.base_classes.psi_detector_base import (
    CustomDetectorMixin,
    PSIDetectorBase,
)
from ophyd_devices.sim.sim_data import SimulatedDataCamera
from ophyd_devices.sim.sim_signals import ReadOnlySignal, SetableSignal
from ophyd_devices.sim.sim_utils import H5Writer
from ophyd_devices.utils.errors import DeviceStopError

logger = bec_logger.logger


class SimCameraSetup(CustomDetectorMixin):
    """Mixin class for the SimCamera device."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._thread_trigger = None
        self._thread_complete = None

    def on_trigger(self) -> None:
        """Trigger the camera to acquire images.

        This method can be called from BEC during a scan. It will acquire images and send them to BEC.
        Whether the trigger is send from BEC is determined by the softwareTrigger argument in the device config.

        Here, we also run a callback on SUB_MONITOR to send the image data the device_monitor endpoint in BEC.
        """
        status = DeviceStatus(self.parent)

        def on_trigger_call(status: DeviceStatus) -> None:
            try:
                for _ in range(self.parent.burst.get()):
                    data = self.parent.image.get()
                    # pylint: disable=protected-access
                    self.parent._run_subs(sub_type=self.parent.SUB_MONITOR, value=data)
                    if self.parent.stopped:
                        raise DeviceStopError(f"{self.parent.name} was stopped")
                    if self.parent.write_to_disk.get():
                        self.parent.h5_writer.receive_data(data)
                status.set_finished()
            # pylint: disable=broad-except
            except Exception as exc:
                content = traceback.format_exc()
                logger.warning(
                    f"Error in on_trigger_call in device {self.parent.name}. Error traceback: {content}"
                )
                status.set_exception(exc)

        self._thread_trigger = Thread(target=on_trigger_call, args=(status,))
        self._thread_trigger.start()
        return status

    def on_stage(self) -> None:
        """Stage the camera for upcoming scan

        This method is called from BEC in preparation of a scan.
        It receives metadata about the scan from BEC,
        compiles it and prepares the camera for the scan.

        FYI: No data is written to disk in the simulation, but upon each trigger it
        is published to the device_monitor endpoint in REDIS.
        """
        self.parent.filepath.set(
            self.parent.filewriter.compile_full_filename(f"{self.parent.name}")
        ).wait()

        self.parent.frames.set(
            self.parent.scaninfo.num_points * self.parent.scaninfo.frames_per_trigger
        )
        self.parent.exp_time.set(self.parent.scaninfo.exp_time)
        self.parent.burst.set(self.parent.scaninfo.frames_per_trigger)
        if self.parent.write_to_disk.get():
            self.parent.h5_writer.prepare(
                file_path=self.parent.filepath.get(), h5_entry="/entry/data/data"
            )
            self.publish_file_location(done=False, successful=False)
        self.parent.stopped = False

    def on_complete(self) -> None:
        """Complete the motion of the simulated device."""
        status = DeviceStatus(self.parent)

        def on_complete_call(status: DeviceStatus) -> None:
            try:
                if self.parent.write_to_disk.get():
                    self.parent.h5_writer.write_data()
                self.publish_file_location(done=True, successful=True)
                if self.parent.stopped:
                    raise DeviceStopError(f"{self.parent.name} was stopped")
                status.set_finished()
            # pylint: disable=broad-except
            except Exception as exc:
                content = traceback.format_exc()
                logger.warning(
                    f"Error in on_complete call in device {self.parent.name}. Error traceback: {content}"
                )
                status.set_exception(exc)

        self._thread_complete = Thread(target=on_complete_call, args=(status,), daemon=True)
        self._thread_complete.start()
        return status

    def on_stop(self) -> None:
        """Stop the camera acquisition."""
        if self._thread_trigger:
            self._thread_trigger.join()
        if self._thread_complete:
            self._thread_complete.join()
        self._thread_trigger = None
        self._thread_complete = None


class SimCamera(PSIDetectorBase):
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
    device_manager          : DeviceManager from BEC, optional . Within startup of simulation, device_manager is passed on automatically.

    """

    USER_ACCESS = ["sim", "registered_proxies"]

    custom_prepare_cls = SimCameraSetup
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
    write_to_disk = Cpt(SetableSignal, name="write_to_disk", value=False, kind=Kind.config)

    def __init__(
        self, name, *, kind=None, parent=None, sim_init: dict = None, device_manager=None, **kwargs
    ):
        self.sim_init = sim_init
        self._registered_proxies = {}
        self.sim = self.sim_cls(parent=self, **kwargs)
        self.h5_writer = H5Writer()
        super().__init__(
            name=name, parent=parent, kind=kind, device_manager=device_manager, **kwargs
        )
        if self.sim_init:
            self.sim.set_init(self.sim_init)

    @property
    def registered_proxies(self) -> None:
        """Dictionary of registered signal_names and proxies."""
        return self._registered_proxies
