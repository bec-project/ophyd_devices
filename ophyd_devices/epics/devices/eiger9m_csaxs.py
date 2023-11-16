import enum
import time
import threading
import numpy as np
import os

from typing import Any, List, Type

from ophyd import EpicsSignal, EpicsSignalRO, EpicsSignalWithRBV
from ophyd import Device
from ophyd import ADComponent as ADCpt
from ophyd.device import Staged

from std_daq_client import StdDaqClient

from bec_lib import messages, MessageEndpoints, threadlocked, bec_logger
from bec_lib.bec_service import SERVICE_CONFIG
from bec_lib.devicemanager import DeviceStatus
from bec_lib.file_utils import FileWriterMixin

from ophyd_devices.epics.devices.bec_scaninfo_mixin import BecScaninfoMixin
from ophyd_devices.utils import bec_utils

logger = bec_logger.logger

# Specify here the minimum readout time for the detector
MIN_READOUT = 3e-3


class EigerError(Exception):
    """Base class for exceptions in this module."""

    pass


class EigerTimeoutError(EigerError):
    """Raised when the Eiger does not respond in time during unstage."""

    pass


class EigerInitError(EigerError):
    """Raised when initiation of the device class fails,
    due to missing device manager or not started in sim_mode."""

    pass


class CustomDetectorMixin:
    def __init__(self, parent: Device = None, *args, **kwargs) -> None:
        self.parent = parent

    def initialize_default_parameter(self) -> None:
        """
        Init parameters for the detector

        Raises (optional):
            DetectorTimeoutError: if detector cannot be initialized
        """
        pass

    def initialize_detector(self) -> None:
        """
        Init parameters for the detector

        Raises (optional):
            DetectorTimeoutError: if detector cannot be initialized
        """
        pass

    def initialize_detector_backend(self) -> None:
        """
        Init parameters for teh detector backend (filewriter)

        Raises (optional):
            DetectorTimeoutError: if filewriter cannot be initialized
        """
        pass

    def prepare_detector(self) -> None:
        """
        Prepare detector for the scan
        """
        pass

    def prepare_data_backend(self) -> None:
        """
        Prepare the data backend for the scan
        """
        pass

    def stop_detector(self) -> None:
        """
        Stop the detector
        """
        pass

    def stop_detector_backend(self) -> None:
        """
        Stop the detector backend
        """
        pass

    def on_trigger(self) -> None:
        """
        Specify actions to be executed upon receiving trigger signal
        """
        pass

    def pre_scan(self) -> None:
        """
        Specify actions to be executed right before a scan

        BEC calls pre_scan just before execution of the scan core.
        It is convenient to execute time critical features of the detector,
        e.g. arming it, but it is recommended to keep this function as short/fast as possible.
        """
        pass

    def finished(self) -> None:
        """
        Specify actions to be executed during unstage

        This may include checks if acquisition was succesful

        Raises (optional):
            DetectorTimeoutError: if detector cannot be stopped
        """

    def wait_for_signals(
        self,
        signal_conditions: list,
        timeout: float,
        check_stopped: bool = False,
        interval: float = 0.05,
        all_signals: bool = False,
    ) -> bool:
        """Wait for signals to reach a certain condition

        Args:
            signal_conditions (tuple): tuple of (get_current_state, condition) functions
            timeout (float): timeout in seconds
            interval (float): interval in seconds
            all_signals (bool): True if all signals should be True, False if any signal should be True
        Returns:
            bool: True if all signals are in the desired state, False if timeout is reached
        """
        timer = 0
        while True:
            checks = [
                get_current_state() == condition
                for get_current_state, condition in signal_conditions
            ]
            if (all_signals and all(checks)) or (not all_signals and any(checks)):
                return True
            if check_stopped == True and self.parent._stopped == True:
                return False
            if timer > timeout:
                return False
            time.sleep(interval)
            timer += interval


class Eiger9MSetup(CustomDetectorMixin):
    """Eiger setup class

    Parent class: CustomDetectorMixin

    """

    def __init__(self, parent: Device = None, *args, **kwargs) -> None:
        super().__init__(parent=parent, *args, **kwargs)
        self.std_rest_server_url = (
            kwargs["file_writer_url"] if "file_writer_url" in kwargs else "http://xbl-daq-29:5000"
        )
        self.std_client = None
        self._lock = self.parent._lock

    def initialize_default_parameter(self) -> None:
        """Set default parameters for Eiger9M detector"""
        self.update_readout_time()

    def update_readout_time(self) -> None:
        """Set readout time for Eiger9M detector"""
        readout_time = (
            self.parent.scaninfo.readout_time
            if hasattr(self.parent.scaninfo, "readout_time")
            else self.parent.readout_time_min
        )
        self.parent.readout_time = max(readout_time, self.parent.readout_time_min)

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
        """Update std_daq config with new e-account for the current beamtime"""
        cfg = self.std_client.get_config()
        old_value = cfg.get(cfg_key)
        if old_value is None:
            raise EigerError(
                f"Tried to change entry for key {cfg_key} in std_config that does not exist"
            )
        if not isinstance(value, type(old_value)):
            raise EigerError(
                f"Type of new value {type(value)}:{value} does not match old value {type(old_value)}:{old_value}"
            )
        cfg.update({cfg_key: value})
        logger.debug(cfg)
        self.std_client.set_config(cfg)
        logger.debug(f"Updated std_daq config for key {cfg_key} from {old_value} to {value}")

    def stop_detector(self) -> None:
        """Stop the detector and wait for the proper status message"""
        # Stop detector
        self.parent.cam.acquire.put(0)
        signal_conditions = [
            (
                lambda: self.parent.cam.detector_state.read()[self.parent.cam.detector_state.name][
                    "value"
                ],
                DetectorState.IDLE,
            ),
            (lambda: self.parent._stopped, True),
        ]

        if not self.wait_for_signals(
            signal_conditions=signal_conditions,
            timeout=self.parent.timeout - self.parent.timeout // 2,
            all_signals=False,
        ):
            # Retry stop detector
            self.parent.cam.acquire.put(0)
            if not self.wait_for_signals(
                signal_conditions=signal_conditions,
                timeout=self.parent.timeout - self.parent.timeout // 2,
                all_signals=False,
            ):
                raise EigerTimeoutError("Failed to stop the acquisition. IOC did not update.")

    def stop_detector_backend(self) -> None:
        """Close file writer"""
        self.std_client.stop_writer()

    def prepare_detector(self) -> None:
        """Prepare detector for scan.
        Includes checking the detector threshold, setting the acquisition parameters and setting the trigger source
        """
        self.set_detector_threshold()
        self.set_acquisition_params()
        self.parent.set_trigger(TriggerSource.GATING)

    def set_detector_threshold(self) -> None:
        """
        Set correct detector threshold to 1/2 of current X-ray energy, allow 5% tolerance

        Threshold might be in ev or keV
        """
        mokev = self.parent.device_manager.devices.mokev.obj.read()[
            self.parent.device_manager.devices.mokev.name
        ]["value"]
        factor = 1

        # Check if energies are eV or keV, assume keV as the default
        unit = getattr(self.parent.cam.threshold_energy, "units", None)
        if unit != None and unit == "eV":
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
        self.parent.cam.num_images.put(
            int(self.parent.scaninfo.num_points * self.parent.scaninfo.frames_per_trigger)
        )
        self.parent.cam.num_frames.put(1)
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
                raise EigerTimeoutError(f"Timeout of start_writer_async with {exc}")

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
                f"Timeout of 5s reached for std_daq start_writer_async with std_daq client status {self.std_client.get_status()}"
            )

    def filepath_exists(self, filepath: str) -> None:
        """Check if filepath exists"""
        signal_conditions = [(lambda: os.path.exists(os.path.dirname(self.parent.filepath)), True)]
        if not self.wait_for_signals(
            signal_conditions=signal_conditions,
            timeout=self.parent.timeout,
            check_stopped=False,
            all_signals=True,
        ):
            raise EigerError(f"Timeout of 3s reached for filepath {self.parent.filepath}")

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
        pipe = self.parent._producer.pipeline()
        if successful is None:
            msg = BECMessage.FileMessage(file_path=self.parent.filepath, done=done)
        else:
            msg = BECMessage.FileMessage(
                file_path=self.parent.filepath, done=done, successful=successful
            )
        self.parent._producer.set_and_publish(
            MessageEndpoints.public_file(self.parent.scaninfo.scanID, self.parent.name),
            msg.dumps(),
            pipe=pipe,
        )
        self.parent._producer.set_and_publish(
            MessageEndpoints.file_event(self.parent.name), msg.dumps(), pipe=pipe
        )
        pipe.execute()

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
        old_scanID = self.parent.scaninfo.scanID
        self.parent.scaninfo.load_scan_metadata()
        if self.parent.scaninfo.scanID != old_scanID:
            self.parent._stopped = True

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
            self.stop_detector()
            self.stop_detector_backend()
            raise EigerTimeoutError(
                f"Reached timeout with detector state {signal_conditions[0][0]}, std_daq state {signal_conditions[1][0]} and received frames of {signal_conditions[2][0]} for the file writer"
            )
        self.stop_detector()
        self.stop_detector_backend()


class SLSDetectorCam(Device):
    """SLS Detector Camera - Eiger 9M

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


class PSIDetectorBase(Device):
    """
    Abstract base class for SLS detectors

    Args:
        prefix (str): EPICS PV prefix for component (optional)
        name (str): name of the device, as will be reported via read()
        kind (str): member of class 'ophydobj.Kind', defaults to Kind.normal
                    omitted -> readout ignored for read 'ophydobj.read()'
                    normal -> readout for read
                    config -> config parameter for 'ophydobj.read_configuration()'
                    hinted -> which attribute is readout for read
        read_attrs (list): sequence of attribute names to read
        configuration_attrs (list): sequence of attribute names via config_parameters
        parent (object): instance of the parent device
        device_manager (object): bec device manager
        sim_mode (bool): simulation mode, if True, no device manager is required
        **kwargs: keyword arguments

        attributes: lazy_wait_for_connection : bool
    """

    custom_prepare_cls = CustomDetectorMixin
    # Specify which functions are revealed to the user in BEC client
    USER_ACCESS = [
        "describe",
    ]

    # cam = ADCpt(SLSDetectorCam, "cam1:")

    def __init__(
        self,
        prefix="",
        *,
        name,
        kind=None,
        read_attrs=None,
        configuration_attrs=None,
        parent=None,
        device_manager=None,
        sim_mode=False,
        **kwargs,
    ):
        super().__init__(
            prefix=prefix,
            name=name,
            kind=kind,
            read_attrs=read_attrs,
            configuration_attrs=configuration_attrs,
            parent=parent,
            **kwargs,
        )
        if device_manager is None and not sim_mode:
            raise EigerInitError(
                f"No device manager for device: {name}, and not started sim_mode: {sim_mode}. Add DeviceManager to initialization or init with sim_mode=True"
            )
        # sim_mode True allows the class to be started without BEC running
        # Init variables
        self.sim_mode = sim_mode
        self._lock = threading.RLock()
        self._stopped = False
        self.name = name
        self.service_cfg = None
        self.std_client = None
        self.scaninfo = None
        self.filewriter = None
        self.readout_time_min = MIN_READOUT
        self.timeout = 5
        self.wait_for_connection(all_signals=True)
        # Init custom prepare class with BL specific logic
        self.custom_prepare = self.custom_prepare_cls(
            parent=self, **kwargs
        )  # Eiger9MSetup(parent=self, **kwargs)
        if not sim_mode:
            self._update_service_config()
            self.device_manager = device_manager
        else:
            self.device_manager = bec_utils.DMMock()
            base_path = kwargs["basepath"] if "basepath" in kwargs else "~/Data10/"
            self.service_cfg = {"base_path": os.path.expanduser(base_path)}
        self._producer = self.device_manager.producer
        self._update_scaninfo()
        self._update_filewriter()
        self._init()

    def _update_filewriter(self) -> None:
        """Update filewriter with service config"""
        self.filewriter = FileWriterMixin(self.service_cfg)

    def _update_scaninfo(self) -> None:
        """Update scaninfo from BecScaninfoMixing
        This depends on device manager and operation/sim_mode
        """
        self.scaninfo = BecScaninfoMixin(self.device_manager, self.sim_mode)
        self.scaninfo.load_scan_metadata()

    def _update_service_config(self) -> None:
        """Update service config from BEC service config"""
        self.service_cfg = SERVICE_CONFIG.config["service_config"]["file_writer"]

    def _init(self) -> None:
        """Initialize detector, filewriter and set default parameters"""
        self.custom_prepare.initialize_default_parameter()
        self.custom_prepare.initialize_detector()
        self.custom_prepare.initialize_detector_backend()

    def stage(self) -> List[object]:
        """
         Stage device in preparation for a scan

        Internal Calls:
        - _prep_backend           : prepare detector filewriter for measurement
        - _prep_detector              : prepare detector for measurement

        Returns:
            List(object): list of objects that were staged

        """
        # Method idempotent, should rais ;obj;'RedudantStaging' if staged twice
        if self._staged != Staged.no:
            return super().stage()

        # Reset flag for detector stopped
        self._stopped = False
        # Load metadata of the scan
        self.scaninfo.load_scan_metadata()
        # Prepare detector and file writer
        self.custom_prepare.prepare_data_backend()
        self.custom_prepare.prepare_detector()
        state = False
        self.custom_prepare.publish_file_location(done=state)
        self.custom_prepare.arm_acquisition()
        # At the moment needed bc signal is not reliable, BEC too fast
        time.sleep(0.05)
        return super().stage()

    def set_trigger(self, trigger_source: TriggerSource) -> None:
        """Set trigger source for the detector.
        Check the TriggerSource enum for possible values

        Args:
            trigger_source (TriggerSource): Trigger source for the detector

        """
        value = trigger_source
        self.cam.trigger_mode.put(value)

    def _publish_file_location(self, done: bool = False, successful: bool = None) -> None:
        """Publish the filepath to REDIS.
        We publish two events here:
        - file_event: event for the filewriter
        - public_file: event for any secondary service (e.g. radial integ code)

        Args:
            done (bool): True if scan is finished
            successful (bool): True if scan was successful

        """
        pipe = self._producer.pipeline()
        if successful is None:
            msg = messages.FileMessage(file_path=self.filepath, done=done)
        else:
            msg = messages.FileMessage(file_path=self.filepath, done=done, successful=successful)
        self._producer.set_and_publish(
            MessageEndpoints.public_file(self.scaninfo.scanID, self.name), msg.dumps(), pipe=pipe
        )
        self._producer.set_and_publish(
            MessageEndpoints.file_event(self.name), msg.dumps(), pipe=pipe
        )
        pipe.execute()

    # TODO function for abstract class?
    def _arm_acquisition(self) -> None:
        """Arm Eiger detector for acquisition"""
        timer = 0
        self.cam.acquire.put(1)
        while True:
            det_ctrl = self.cam.detector_state.read()[self.cam.detector_state.name]["value"]
            if det_ctrl == DetectorState.RUNNING:
                break
            if self._stopped == True:
                break
            time.sleep(0.01)
            timer += 0.01
            if timer > 5:
                self.stop()
                raise EigerTimeoutError("Failed to arm the acquisition. IOC did not update.")

    # TODO function for abstract class?
    def trigger(self) -> DeviceStatus:
        """Trigger the detector, called from BEC."""
        self.custom_prepare.on_trigger()
        return super().trigger()

    def unstage(self) -> List[object]:
        """
        Unstage device in preparation for a scan

        Returns directly if self._stopped,
        otherwise checks with self._finished
        if data acquisition on device finished (an was successful)

        Internal Calls:
        - custom_prepare.check_scanID          : check if scanID changed or detector stopped
        - custom_prepare.finished              : check if device finished acquisition (succesfully)
        - custom_prepare.publish_file_location : publish file location to bec

        Returns:
            List(object): list of objects that were unstaged
        """
        self.custom_prepare.check_scanID()
        if self._stopped == True:
            return super().unstage()
        self.custom_prepare.finished()
        state = True
        self.custom_prepare.publish_file_location(done=state, successful=state)
        self._stopped = False
        return super().unstage()

    def stop(self, *, success=False) -> None:
        """
        Stop the scan, with camera and file writer

        Internal Calls:
        - custom_prepare.stop_detector     : stop detector
        - custom_prepare.stop_backend : stop detector filewriter
        """
        self.custom_prepare.stop_detector()
        self.custom_prepare.stop_detector_backend()
        super().stop(success=success)
        self._stopped = True

    # def set_trigger(self, trigger_source: TriggerSource) -> None:
    #     """Set trigger source for the detector.
    #     Check the TriggerSource enum for possible values

    #     Args:
    #         trigger_source (TriggerSource): Trigger source for the detector

    #     """
    #     value = trigger_source
    #     self.cam.trigger_mode.put(value)


class Eiger9McSAXS(PSIDetectorBase):
    custom_prepare_cls = Eiger9MSetup
    cam = ADCpt(SLSDetectorCam, "cam1:")

    def __init__(
        self,
        prefix="",
        *,
        name,
        kind=None,
        read_attrs=None,
        configuration_attrs=None,
        parent=None,
        device_manager=None,
        sim_mode=False,
        **kwargs,
    ):
        super().__init__(
            prefix,
            name=name,
            kind=kind,
            read_attrs=read_attrs,
            configuration_attrs=configuration_attrs,
            parent=parent,
            device_manager=device_manager,
            sim_mode=sim_mode,
            **kwargs,
        )

    def set_trigger(self, trigger_source: TriggerSource) -> None:
        """Set trigger source for the detector.
        Check the TriggerSource enum for possible values

        Args:
            trigger_source (TriggerSource): Trigger source for the detector

        """
        value = trigger_source
        self.cam.trigger_mode.put(value)


# class Eiger9McSAXS(Eiger9M):
#     def __init__(
#         self,
#         prefix="",
#         *,
#         name,
#         kind=None,
#         read_attrs=None,
#         configuration_attrs=None,
#         parent=None,
#         device_manager=None,
#         sim_mode=False,
#         **kwargs,
#     ):
#         super().__init__(
#             prefix=prefix,
#             name=name,
#             kind=kind,
#             read_attrs=read_attrs,
#             configuration_attrs=configuration_attrs,
#             parent=parent,
#             **kwargs,
#         )
#         # self.custom_prepare = Eiger9MSetup(parent=self, **kwargs)


if __name__ == "__main__":
    eiger = Eiger9McSAXS(name="eiger", prefix="X12SA-ES-EIGER9M:", sim_mode=True)
