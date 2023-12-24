import enum
import os
import threading
import time as ttime

# import numpy as np
from ophyd.ophydobj import Kind

os.environ["EPICS_CA_AUTO_ADDR_LIST"] = "No"
os.environ["EPICS_CA_ADDR_LIST"] = "129.129.208.143"

# from typing import Any
from ophyd import EpicsSignal, EpicsSignalRO, EpicsSignalWithRBV
from ophyd import Device
from ophyd import Component as Cpt, ADComponent as ADCpt

from bec_lib.logger import bec_logger

from ophyd_devices.epics.devices.psi_detector_base import PSIDetectorBase, CustomDetectorMixin

logger = bec_logger.logger


class GrashopperError(Exception):
    """Base class for Grashopper detector errors."""


class GrashopperTimeoutError(GrashopperError):
    """Base class for Grashopper detector errors."""


class AutoMode(enum.IntEnum):
    """Acquire time auto for Grashopper detector.

    class for acquire_auto and gain_auto

    Off:        Gain tap balancing is user controlled using Gain.
    Once:       Gain tap balancing is automatically adjusted once by the device.
                Once it has converged, it automatically returns to the Off state.
    Continuous: Gain tap balancing is constantly adjusted by the device.
    """

    OFF = 0
    ONCE = 1
    CONTINUOUS = 2


class ImageMode(enum.IntEnum):
    """Image mode for Grashopper detector.

    Single: Acquire a single image, ignores NumImages PV
    Multiple: Acquire NumImages images
    Continuous: Acquire images continuously
    """

    SINGLE = 0
    MULTIPLE = 1
    CONTINUOUS = 2


class DetectorState(enum.IntEnum):
    """Detector states for Grashopper detector"""

    IDLE = 0
    ACQUIRE = 1
    READOUT = 2
    CORRECT = 3
    SAVING = 4
    ABORTING = 5
    ERROR = 6
    WAITING = 7
    INITIALIZING = 8
    DISCONNECTED = 9
    ABORTED = 10


class ImageBinning(enum.IntEnum):
    """Image binning for Grashopper detector"""

    X1 = 1
    X2 = 2
    X4 = 4


class VideoMode(enum.IntEnum):
    """Video mode for Grashopper detector.

    For details, consult EPICs IOC manual.
    """

    MODE0 = 0
    MODE1 = 1
    MODE2 = 2
    MODE3 = 3


class PixelFormat(enum.IntEnum):
    """Pixel format for Grashopper detector."""

    MONO8 = 0
    MONO12PACKED = 1
    MONO12P = 2
    MONO16 = 3


class COLORMODE(enum.IntEnum):
    """Color mode for Grashopper detector.

    Only for readback values from color_mode RO PV.
    """

    MONO = 0
    BAYER = 1
    RGB1 = 2
    RGB2 = 3
    RGB3 = 4
    YUV444 = 5
    YUV422 = 6
    YUV421 = 7


class TriggerSource(enum.IntEnum):
    """Trigger signals for Grashopper detector"""

    SOFTWARE = 0
    LINE0 = 1
    LINE2 = 2
    LINE3 = 3


class MemoryPolling(enum.IntEnum):
    """Memory polling for Grashopper detector.

    Defines update rate of memory polling for IOC (1s suggested).
    """

    PASSIVE = 0
    EVENT = 1
    IOINTR = 2
    SECONDS10 = 3
    SECONDS5 = 4
    SECONDS2 = 5
    SECONDS1 = 6
    SECONDS05 = 7
    SECONDS02 = 8
    SECONDS01 = 9


class GrashopperTOMCATSetup(CustomDetectorMixin):
    """Mixin class to setup TOMCAT specific implementations of the detector.

    This class will be called by the custom_prepare_cls attribute of the detector class.
    """

    def __init__(self, *_args, parent: Device = None, **_kwargs) -> None:
        super().__init__(*_args, parent=parent, **_kwargs)

        self.image_shape = (
            self.parent.cam.image_size_y.get(),
            self.parent.cam.image_size_x.get(),
        )
        self.monitor_thread = None
        self.stop_monitor = False
        self.update_frequency = 1
        self.low_frame_rate = 80

    def initialize_detector(self) -> None:
        """Initialize detector."""
        self.parent.cam.acquire.put(0)
        self.parent.cam.acquire_time_auto.put(AutoMode.CONTINUOUS)
        self.parent.cam.gain_auto.put(AutoMode.CONTINUOUS)
        self.parent.cam.image_mode.put(ImageMode.MULTIPLE)
        self.parent.cam.image_binning.put(ImageBinning.X1)
        self.parent.cam.video_mode.put(VideoMode.MODE0)
        self.parent.cam.pixel_format.put(PixelFormat.MONO16)
        self.parent.cam.trigger_source.put(TriggerSource.SOFTWARE)
        self.parent.cam.memory_polling.put(MemoryPolling.SECONDS1)
        self.parent.cam.set_image_counter.put(0)

    def initialize_detector_backend(self) -> None:
        self.parent.image.queue_size.put(5)
        self.parent.image.array_port.put(self.parent.cam.port_name.get())
        self.parent.image.enable_cb.put(1)
        self.parent.image.set_array_counter.put(0)

    def set_exposure_time(self, exposure_time: float) -> None:
        """Set the detector framerate.

        Args:
            framerate (float): Desired framerate in Hz smallest is 87Hz
        """
        framerate = 1 / exposure_time
        if framerate > self.low_frame_rate:
            raise GrashopperError(
                f"Trying to set exposure time to {exposure_time}s, this is below the lowest"
                f" possible exposure of {1/self.low_frame_rate}s"
            )
        self.parent.cam.frame_rate.put(framerate)

    def prepare_detector(self) -> None:
        """Prepare detector for acquisition."""
        self.parent.cam.image_mode.put(ImageMode.MULTIPLE)
        self.parent.cam.acquire_time_auto.put(AutoMode.CONTINUOUS)
        self.set_exposure_time(self.parent.scaninfo.exp_time)
        self.parent.set_trigger(TriggerSource.SOFTWARE)
        self.parent.cam.set_image_counter.put(0)
        self.set_acquisition_params()

    def set_acquisition_params(self) -> None:
        """Set acquisition parameters for the detector"""

        # Set number of images and frames (frames is for internal burst of detector)
        self.parent.cam.num_images.put(
            int(self.parent.scaninfo.num_points * self.parent.scaninfo.frames_per_trigger)
        )

    def prepare_detector_backend(self) -> None:
        """Prepare detector backend for acquisition."""
        self.parent.image.set_array_counter.put(0)
        self.monitor_thread = None
        self.stop_monitor = False
        self.run_monitor()

    def arm_acquisition(self) -> None:
        """Arm grashopper detector for acquisition"""
        self.parent.cam.acquire.put(1)
        signal_conditions = [
            (
                self.parent.cam.detector_state.get,
                DetectorState.WAITING,
            )
        ]
        if not self.wait_for_signals(
            signal_conditions=signal_conditions,
            timeout=self.parent.timeout,
            check_stopped=True,
            all_signals=False,
        ):
            raise GrashopperTimeoutError(
                f"Failed to arm the acquisition. Detector state {signal_conditions[0][0]}"
            )

    def on_trigger(self) -> None:
        """Trigger the detector"""
        if self.parent.cam.trigger_source.get() == TriggerSource.SOFTWARE:
            self.parent.cam.software_trigger.put(1)

    def run_monitor(self) -> None:
        """
        Run the monitor loop in a separate thread.
        """
        self.monitor_thread = threading.Thread(target=self.monitor_loop, daemon=True)
        self.monitor_thread.start()

    def monitor_loop(self) -> None:
        """
        Monitor the detector status and send data.
        """
        while True:
            self.send_data()
            ttime.sleep(1 / self.update_frequency)
            if self.parent.stopped:
                break

    def send_data(self) -> None:
        """Send data to monitor endpoint in redis."""
        try:
            img = self.parent.image.array_data.get().reshape(self.image_shape)
            # pylint: disable=protected-access
            self.parent._run_subs(sub_type=self.parent.SUB_VALUE, value=img)
        except Exception as e:
            logger.debug(f"{e} for image with shape {self.parent.image.array_data.get().shape}")

    def stop_detector(self) -> None:
        """Stop detector."""
        self.parent.cam.acquire.put(0)
        signal_conditions = [
            (
                self.parent.cam.detector_state.get,
                DetectorState.IDLE,
            ),
        ]
        if not self.wait_for_signals(
            signal_conditions=signal_conditions,
            timeout=self.parent.timeout - self.parent.timeout // 2,
            check_stopped=True,
            all_signals=False,
        ):
            # Retry stop detector and wait for remaining time
            self.parent.cam.acquire.put(0)
            if not self.wait_for_signals(
                signal_conditions=signal_conditions,
                timeout=self.parent.timeout - self.parent.timeout // 2,
                check_stopped=True,
                all_signals=False,
            ):
                raise GrashopperTimeoutError(
                    f"Failed to stop detector, detector state {signal_conditions[0][0]}"
                )

    def stop_detector_backend(self) -> None:
        """Stop the data backend sending data."""
        self.stop_monitor = True


class SLSDetectorCam(Device):
    """
    SLS Detector Camera - Grashoppter

    Base class to map EPICS PVs to ophyd signals.
    """

    ## Deprecated PVs, to be checked!
    # acquire_time = ADCpt(EpicsSignal, "AcquireTime", kind=Kind.omitted)
    # num_exposures = ADCpt(EpicsSignal, "NumExposures", kind=Kind.omitted)
    # acquire_period = ADCpt(EpicsSignalWithRBV, "AcquirePeriod", kind=Kind.config)

    # Control PVs
    acquire_time_auto = ADCpt(EpicsSignal, "AcquireTimeAuto", kind=Kind.config)

    frame_rate = ADCpt(EpicsSignalWithRBV, "FrameRate", kind=Kind.normal)
    num_images = ADCpt(EpicsSignalWithRBV, "NumImages", kind=Kind.normal)
    num_images_counter = ADCpt(EpicsSignalRO, "NumImagesCounter_RBV", kind=Kind.normal)
    image_mode = ADCpt(EpicsSignalWithRBV, "ImageMode", kind=Kind.config)
    acquire = ADCpt(EpicsSignalWithRBV, "Acquire", kind=Kind.config)
    detector_state = ADCpt(EpicsSignalRO, "DetectorState_RBV", kind=Kind.normal)
    status_message = ADCpt(EpicsSignalRO, "StatusMessage_RBV", string=True, kind=Kind.config)

    set_image_counter = ADCpt(EpicsSignal, "ArrayCounter", kind=Kind.config)
    image_counter = ADCpt(EpicsSignal, "ArrayCounter_RBV", kind=Kind.normal)
    image_rate = ADCpt(EpicsSignalRO, "ArrayRate_RBV", kind=Kind.omitted)

    # Asyn Port name
    port_name = ADCpt(EpicsSignalRO, "PortName_RBV", string=True, kind=Kind.omitted)

    # Readout related PVs
    max_image_size_x = ADCpt(EpicsSignalRO, "MaxSizeX_RBV", kind=Kind.config)
    max_image_size_y = ADCpt(EpicsSignalRO, "MaxSizeY_RBV", kind=Kind.config)
    image_size_x = ADCpt(EpicsSignalRO, "ArraySizeX_RBV", kind=Kind.config)
    image_size_y = ADCpt(EpicsSignalRO, "ArraySizeY_RBV", kind=Kind.config)
    # Only BinY PV is working, sets both
    image_binning = ADCpt(EpicsSignalWithRBV, "BinY", kind=Kind.config)

    gain = ADCpt(EpicsSignalWithRBV, "Gain", kind=Kind.config)
    gain_auto = ADCpt(EpicsSignalWithRBV, "GainAuto", kind=Kind.config)
    video_mode = ADCpt(EpicsSignalWithRBV, "VideoMode", kind=Kind.config)
    pixel_format = ADCpt(EpicsSignalWithRBV, "PixelFormat", kind=Kind.config)
    # Desired to set this in future?
    color_mode = ADCpt(EpicsSignalRO, "ColorMode_RBV", kind=Kind.config)

    # HW Status PVs
    temperature_actual = ADCpt(EpicsSignal, "TemperatureActual", kind=Kind.omitted)

    # Trigger
    trigger_mode_active = ADCpt(EpicsSignalWithRBV, "TriggerMode", kind=Kind.config)
    trigger_source = ADCpt(EpicsSignalWithRBV, "TriggerSource", kind=Kind.config)
    trigger_delay = ADCpt(EpicsSignalWithRBV, "TriggerDelay", kind=Kind.omitted)
    exposure_mode = ADCpt(EpicsSignalWithRBV, "ExposureMode", kind=Kind.omitted)
    software_trigger = ADCpt(EpicsSignal, "SoftwareTrigger", kind=Kind.config)

    # buffer
    memory_polling = ADCpt(EpicsSignal, "PoolUsedMem.SCAN", kind=Kind.omitted)


class SLSImagePlugin(Device):
    """SLS Image Plugin

    Image plugin for SLS detector imitating the behaviour of ImagePlugin from
    ophyd's areadetector plugins.
    """

    # Control
    array_port = Cpt(EpicsSignal, "NDArrayPort", kind=Kind.omitted, string=True)
    enable_cb = Cpt(EpicsSignal, "EnableCallbacks", kind=Kind.config)
    queue_size = Cpt(EpicsSignal, "QueueSize", kind=Kind.config)
    set_array_counter = Cpt(EpicsSignal, "ArrayCounter", kind=Kind.config)
    array_counter = Cpt(EpicsSignal, "ArrayCounter_RBV", kind=Kind.normal)
    set_dropped_arrays = Cpt(EpicsSignal, "DroppedArrays", kind=Kind.config)
    dropped_arrays = Cpt(EpicsSignal, "DroppedArrays_RBV", kind=Kind.normal)
    image_id = Cpt(EpicsSignal, "UniqueId_RBV", kind=Kind.normal)

    # Data
    array_data = Cpt(EpicsSignal, "ArrayData", kind=Kind.omitted)

    # Size related PVs from Plugin
    array_size_0 = Cpt(EpicsSignalRO, "ArraySize0_RBV", kind=Kind.omitted)
    array_size_1 = Cpt(EpicsSignalRO, "ArraySize1_RBV", kind=Kind.omitted)
    array_size_2 = Cpt(EpicsSignalRO, "ArraySize2_RBV", kind=Kind.omitted)
    array_dimension_size = Cpt(EpicsSignalRO, "NDimensions_RBV", kind=Kind.omitted)


class GrashopperTOMCAT(PSIDetectorBase):
    """
    Grashopper detector for TOMCAT

    Parent class: PSIDetectorBase

    class attributes:
        custom_prepare_cls (GrashopperTOMCATSetup)        : Custom detector setup class for TOMCAT,
                                                            inherits from CustomDetectorMixin
        cam (SLSDetectorCam)                              : Detector camera
        image (SLSImagePlugin)                            : Image plugin for detector
    """

    # Specify which functions are revealed to the user in BEC client
    USER_ACCESS = [
        "describe",
    ]

    SUB_MONITOR = "monitor"
    SUB_VALUE = "value"
    _default_sub = SUB_VALUE

    # specify Setup class
    custom_prepare_cls = GrashopperTOMCATSetup
    # specify minimum readout time for detector
    MIN_READOUT = 0
    # specify class attributes
    cam = ADCpt(SLSDetectorCam, "cam1:")
    image = ADCpt(SLSImagePlugin, "image1:")

    def stage(self) -> list[object]:
        rtr = super().stage()
        self.custom_prepare.arm_acquisition()
        return rtr

    def unstage(self) -> list[object]:
        rtr = super().unstage()
        self.custom_prepare.stop_monitor = True
        return rtr

    def set_trigger(self, trigger_source: TriggerSource) -> None:
        """Set trigger source for the detector.
        Check the TriggerSource enum for possible values

        Args:
            trigger_source (TriggerSource): Trigger source for the detector

        """
        value = trigger_source
        self.cam.trigger_source.put(value)


if __name__ == "__main__":
    hopper = GrashopperTOMCAT(name="hopper", prefix="X02DA-PG-USB:", sim_mode=True)
    hopper.wait_for_connection(all_signals=True)
