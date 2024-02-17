import enum
import threading
import time
import numpy as np
import os

from typing import Any

from ophyd import EpicsSignal, EpicsSignalRO, EpicsSignalWithRBV
from ophyd import Device
from ophyd import ADComponent as ADCpt

from std_daq_client import StdDaqClient

from bec_lib import threadlocked
from bec_lib.logger import bec_logger
from bec_lib import messages
from bec_lib.endpoints import MessageEndpoints

from ophyd_devices.epics.devices.psi_detector_base import PSIDetectorBase, CustomDetectorMixin

logger = bec_logger.logger


class EigerError(Exception):
    """Base class for exceptions in this module."""


class EigerTimeoutError(EigerError):
    """Raised when the Eiger does not respond in time."""


class Eiger9MSetup(CustomDetectorMixin):
    """Eiger setup class

    Parent class: CustomDetectorMixin

    """

    def __init__(self, *args, parent: Device = None, **kwargs) -> None:
        super().__init__(*args, parent=parent, **kwargs)
        self.std_rest_server_url = (
            kwargs["file_writer_url"] if "file_writer_url" in kwargs else "http://xbl-daq-29:5000"
        )
        self.std_client = None
        self._lock = threading.RLock()

    def initialize_default_parameter(self) -> None:
        """Set default parameters for Eiger9M detector"""
        self.update_readout_time()

    def update_readout_time(self) -> None:
        """Set readout time for Eiger9M detector"""
        readout_time = (
            self.parent.scaninfo.readout_time
            if hasattr(self.parent.scaninfo, "readout_time")
            else self.parent.MIN_READOUT
        )
        self.parent.readout_time = max(readout_time, self.parent.MIN_READOUT)

    def initialize_detector(self) -> None:
        """Initialize detector"""
        # Stops the detector
        self.stop_detector()
        # Sets the trigger source to GATING
        self.parent.set_trigger(TriggerSource.GATING)

    def initialize_detector_backend(self) -> None:
        """Initialize detector backend"""

        # Std client
        self.std_client = StdDaqClient(url_base=self.std_rest_server_url)

        # Stop writer
        self.std_client.stop_writer()

        # Change e-account
        eacc = self.parent.scaninfo.username
        self.update_std_cfg("writer_user_id", int(eacc.strip(" e")))

        signal_conditions = [
            (
                lambda: self.std_client.get_status()["state"],
                "READY",
            ),
        ]
        if not self.wait_for_signals(
            signal_conditions=signal_conditions,
            timeout=self.parent.timeout,
            all_signals=True,
        ):
            raise EigerTimeoutError(
                f"Std client not in READY state, returns: {self.std_client.get_status()}"
            )

    def update_std_cfg(self, cfg_key: str, value: Any) -> None:
        """
        Update std_daq config

        Checks that the new value matches the type of the former entry.

        Args:
            cfg_key (str)   : config key of value to be updated
            value (Any)     : value to be updated for the specified key

        Raises:
            Raises EigerError if the key was not in the config before and if the new value does not match the type of the old value

        """

        # Load config from client and check old value
        cfg = self.std_client.get_config()
        old_value = cfg.get(cfg_key)
        if old_value is None:
            raise EigerError(
                f"Tried to change entry for key {cfg_key} in std_config that does not exist"
            )
        if not isinstance(value, type(old_value)):
            raise EigerError(
                f"Type of new value {type(value)}:{value} does not match old value"
                f" {type(old_value)}:{old_value}"
            )

        # Update config with new value and send back to client
        cfg.update({cfg_key: value})
        logger.debug(cfg)
        self.std_client.set_config(cfg)
        logger.debug(f"Updated std_daq config for key {cfg_key} from {old_value} to {value}")

    def stop_detector(self) -> None:
        """Stop the detector"""

        # Stop detector
        self.parent.cam.acquire.put(0)

        # Check if detector returned in idle state
        signal_conditions = [
            (
                lambda: self.parent.cam.detector_state.read()[self.parent.cam.detector_state.name][
                    "value"
                ],
                DetectorState.IDLE,
            )
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
                raise EigerTimeoutError(
                    f"Failed to stop detector, detector state {signal_conditions[0][0]}"
                )

    def stop_detector_backend(self) -> None:
        """Close file writer"""
        self.std_client.stop_writer()

    def prepare_detector(self) -> None:
        """Prepare detector for scan"""
        self.set_detector_threshold()
        self.set_acquisition_params()
        self.parent.set_trigger(TriggerSource.GATING)

    def set_detector_threshold(self) -> None:
        """
        Set the detector threshold

        The function sets the detector threshold automatically to 1/2 of the beam energy.
        """

        # get current beam energy from device manageer
        mokev = self.parent.device_manager.devices.mokev.obj.read()[
            self.parent.device_manager.devices.mokev.name
        ]["value"]
        factor = 1

        # Check if energies are eV or keV, assume keV as the default
        unit = getattr(self.parent.cam.threshold_energy, "units", None)
        if unit is not None and unit == "eV":
            factor = 1000

        # set energy on detector
        setpoint = int(mokev * factor)
        energy = self.parent.cam.beam_energy.read()[self.parent.cam.beam_energy.name]["value"]
        if setpoint != energy:
            self.parent.cam.beam_energy.set(setpoint)

        # set threshold on detector
        threshold = self.parent.cam.threshold_energy.read()[self.parent.cam.threshold_energy.name][
            "value"
        ]
        if not np.isclose(setpoint / 2, threshold, rtol=0.05):
            self.parent.cam.threshold_energy.set(setpoint / 2)

    def set_acquisition_params(self) -> None:
        """Set acquisition parameters for the detector"""

        # Set number of images and frames (frames is for internal burst of detector)
        self.parent.cam.num_images.put(
            int(self.parent.scaninfo.num_points * self.parent.scaninfo.frames_per_trigger)
        )
        self.parent.cam.num_frames.put(1)

        # Update the readout time of the detector
        self.update_readout_time()

    def prepare_data_backend(self) -> None:
        """Prepare the data backend for the scan"""
        self.parent.filepath = self.parent.filewriter.compile_full_filename(
            self.parent.scaninfo.scan_number, f"{self.parent.name}.h5", 1000, 5, True
        )
        self.filepath_exists(self.parent.filepath)
        self.stop_detector_backend()
        try:
            self.std_client.start_writer_async(
                {
                    "output_file": self.parent.filepath,
                    "n_images": int(
                        self.parent.scaninfo.num_points * self.parent.scaninfo.frames_per_trigger
                    ),
                }
            )
        except Exception as exc:
            time.sleep(5)
            if self.std_client.get_status()["state"] == "READY":
                raise EigerTimeoutError(f"Timeout of start_writer_async with {exc}") from exc

        # Check status of std_daq
        signal_conditions = [
            (lambda: self.std_client.get_status()["acquisition"]["state"], "WAITING_IMAGES")
        ]
        if not self.wait_for_signals(
            signal_conditions=signal_conditions,
            timeout=self.parent.timeout,
            check_stopped=False,
            all_signals=True,
        ):
            raise EigerTimeoutError(
                "Timeout of 5s reached for std_daq start_writer_async with std_daq client status"
                f" {self.std_client.get_status()}"
            )

    def filepath_exists(self, filepath: str) -> None:
        """Check if filepath exists"""
        signal_conditions = [(lambda: os.path.exists(os.path.dirname(filepath)), True)]
        if not self.wait_for_signals(
            signal_conditions=signal_conditions,
            timeout=self.parent.timeout,
            check_stopped=False,
            all_signals=True,
        ):
            raise EigerError(f"Timeout of 3s reached for filepath {filepath}")

    def arm_acquisition(self) -> None:
        """Arm Eiger detector for acquisition"""
        self.parent.cam.acquire.put(1)
        signal_conditions = [
            (
                lambda: self.parent.cam.detector_state.read()[self.parent.cam.detector_state.name][
                    "value"
                ],
                DetectorState.RUNNING,
            )
        ]
        if not self.wait_for_signals(
            signal_conditions=signal_conditions,
            timeout=self.parent.timeout,
            check_stopped=True,
            all_signals=False,
        ):
            raise EigerTimeoutError(
                f"Failed to arm the acquisition. Detector state {signal_conditions[0][0]}"
            )

    def check_scanID(self) -> None:
        """Checks if scanID has changed and stops the scan if it has"""
        old_scanID = self.parent.scaninfo.scanID
        self.parent.scaninfo.load_scan_metadata()
        if self.parent.scaninfo.scanID != old_scanID:
            self.parent.stopped = True

    def publish_file_location(self, done: bool = False, successful: bool = None) -> None:
        """
        Publish the filepath to REDIS.

        We publish two events here:
        - file_event: event for the filewriter
        - public_file: event for any secondary service (e.g. radial integ code)

        Args:
            done (bool): True if scan is finished
            successful (bool): True if scan was successful
        """
        pipe = self.parent.connector.pipeline()
        if successful is None:
            msg = messages.FileMessage(file_path=self.parent.filepath, done=done)
        else:
            msg = messages.FileMessage(
                file_path=self.parent.filepath, done=done, successful=successful
            )
        self.parent.connector.set_and_publish(
            MessageEndpoints.public_file(self.parent.scaninfo.scanID, self.parent.name),
            msg,
            pipe=pipe,
        )
        self.parent.connector.set_and_publish(
            MessageEndpoints.file_event(self.parent.name), msg, pipe=pipe
        )
        pipe.execute()

    @threadlocked
    def finished(self):
        """Check if acquisition is finished."""
        signal_conditions = [
            (
                lambda: self.parent.cam.acquire.read()[self.parent.cam.acquire.name]["value"],
                DetectorState.IDLE,
            ),
            (lambda: self.std_client.get_status()["acquisition"]["state"], "FINISHED"),
            (
                lambda: self.std_client.get_status()["acquisition"]["stats"]["n_write_completed"],
                int(self.parent.scaninfo.num_points * self.parent.scaninfo.frames_per_trigger),
            ),
        ]
        if not self.wait_for_signals(
            signal_conditions=signal_conditions,
            timeout=self.parent.timeout,
            check_stopped=True,
            all_signals=True,
        ):
            raise EigerTimeoutError(
                f"Reached timeout with detector state {signal_conditions[0][0]}, std_daq state"
                f" {signal_conditions[1][0]} and received frames of {signal_conditions[2][0]} for"
                " the file writer"
            )
        self.stop_detector()
        self.stop_detector_backend()


class SLSDetectorCam(Device):
    """
    SLS Detector Camera - Eiger9M

    Base class to map EPICS PVs to ophyd signals.
    """

    threshold_energy = ADCpt(EpicsSignalWithRBV, "ThresholdEnergy")
    beam_energy = ADCpt(EpicsSignalWithRBV, "BeamEnergy")
    bit_depth = ADCpt(EpicsSignalWithRBV, "BitDepth")
    num_images = ADCpt(EpicsSignalWithRBV, "NumCycles")
    num_frames = ADCpt(EpicsSignalWithRBV, "NumFrames")
    trigger_mode = ADCpt(EpicsSignalWithRBV, "TimingMode")
    trigger_software = ADCpt(EpicsSignal, "TriggerSoftware")
    acquire = ADCpt(EpicsSignal, "Acquire")
    detector_state = ADCpt(EpicsSignalRO, "DetectorState_RBV")


class TriggerSource(enum.IntEnum):
    """Trigger signals for Eiger9M detector"""

    AUTO = 0
    TRIGGER = 1
    GATING = 2
    BURST_TRIGGER = 3


class DetectorState(enum.IntEnum):
    """Detector states for Eiger9M detector"""

    IDLE = 0
    ERROR = 1
    WAITING = 2
    FINISHED = 3
    TRANSMITTING = 4
    RUNNING = 5
    STOPPED = 6
    STILL_WAITING = 7
    INITIALIZING = 8
    DISCONNECTED = 9
    ABORTED = 10


class Eiger9McSAXS(PSIDetectorBase):
    """
    Eiger9M detector for CSAXS

    Parent class: PSIDetectorBase

    class attributes:
        custom_prepare_cls (FalconSetup)        : Custom detector setup class for cSAXS,
                                                  inherits from CustomDetectorMixin
        PSIDetectorBase.set_min_readout (float) : Minimum readout time for the detector
        Various EpicsPVs for controlling the detector
    """

    # Specify which functions are revealed to the user in BEC client
    USER_ACCESS = [
        "describe",
    ]

    # specify Setup class
    custom_prepare_cls = Eiger9MSetup
    # specify minimum readout time for detector
    MIN_READOUT = 3e-3
    # specify class attributes
    cam = ADCpt(SLSDetectorCam, "cam1:")

    def set_trigger(self, trigger_source: TriggerSource) -> None:
        """Set trigger source for the detector.
        Check the TriggerSource enum for possible values

        Args:
            trigger_source (TriggerSource): Trigger source for the detector

        """
        value = trigger_source
        self.cam.trigger_mode.put(value)

    def stage(self) -> list[object]:
        """
        Add functionality to stage, and arm the detector

        Additional call to:
        - custom_prepare.arm_acquisition()
        """
        rtr = super().stage()
        self.custom_prepare.arm_acquisition()
        return rtr


if __name__ == "__main__":
    eiger = Eiger9McSAXS(name="eiger", prefix="X12SA-ES-EIGER9M:", sim_mode=True)
