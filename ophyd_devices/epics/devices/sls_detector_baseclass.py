import enum
import os
from abc import ABC, abstractmethod
from typing import List

from ophyd import Device
from ophyd.device import Staged
from ophyd_devices.utils import bec_utils

from bec_lib.bec_service import SERVICE_CONFIG
from bec_lib.file_utils import FileWriterMixin
from bec_lib.messages import BECMessage, MessageEndpoints
from ophyd_devices.epics.devices.bec_scaninfo_mixin import BecScaninfoMixin


# Define here a minimum readout time for the detector
MIN_READOUT = None


# Custom exceptions specific to detectors
class DetectorError(Exception):
    """
    Class for custom detector errors

    Specifying different types of errors can be helpful and used
    for error handling, e.g. scan repetitions.

    An suggestion/example would be to have 3 class types for errors
        - EigerError : base error class for the detector (e.g. Eiger here)
        - EigerTimeoutError(EigerError) : timeout error, inherits from EigerError
        - EigerInitError(EigerError) : initialization error, inherits from EigerError
    """

    pass


class TriggerSource(enum.IntEnum):
    """
    Class for trigger signals

    Here we would map trigger options from EPICS, example  implementation:
    AUTO = 0
    TRIGGER = 1
    GATING = 2
    BURST_TRIGGER = 3

    To set the trigger source to gating, call TriggerSource.Gating
    """

    pass


class SLSDetectorBase(ABC, Device):
    """
    Abstract base class for SLS detectors
    """

    def __init____init__(
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
    ) -> None:
        super().__init__(
            prefix,
            name=name,
            kind=kind,
            read_attrs=read_attrs,
            configuration_attrs=configuration_attrs,
            parent=parent,
            device_manager=device_manager,
            **kwargs,
        )
        if device_manager is None and not sim_mode:
            raise DetectorError(
                f"No device manager for device: {name}, and not started sim_mode: {sim_mode}. Add DeviceManager to initialization or init with sim_mode=True"
            )
        self.sim_mode = sim_mode
        self._stopped = False
        self._staged = Staged.no
        self.name = name
        self.service_cfg = None
        self.std_client = None
        self.scaninfo = None
        self.filewriter = None
        self.readout_time_min = MIN_READOUT
        self.timeout = 5
        self.wait_for_connection(all_signals=True)
        if not self.sim_mode:
            self._update_service_cfg()
            self.device_manager = device_manager
        else:
            self.device_manager = bec_utils.DMMock()
            base_path = kwargs["basepath"] if "basepath" in kwargs else "~/Data10/"
            self.service_cfg = {"base_path": os.path.expanduser(base_path)}
        self._producer = self.device_manager.producer
        self._update_scaninfo()
        self._update_filewriter()
        self._init()

    def _update_service_cfg(self) -> None:
        """
        Update service configuration from BEC SERVICE CONFIG
        """
        self.service_cfg = SERVICE_CONFIG.config["service_config"]["file_writer"]

    def _update_scaninfo(self) -> None:
        """
        Update scaninfo from BecScaninfoMixing
        """
        self.scaninfo = BecScaninfoMixin(self.device_manager, self.sim_mode)
        self.scaninfo.load_scan_metadata()

    def _update_filewriter(self) -> None:
        """
        Update filewriter with service config
        """
        self.filewriter = FileWriterMixin(self.service_cfg)

    @abstractmethod
    def _init(self) -> None:
        """
        Initialize detector & detector filewriter

        Can also be used to init default parameters

        Internal Calls:
        - _init_detector   : Init detector
        - _init_det_fw : Init file_writer

        """
        self._init_det()
        self._init_det_fw()

    @abstractmethod
    def _init_det(self) -> None:
        """
        Init parameters for the detector

        Raises (optional):
            DetectorError: if detector cannot be initialized
        """
        pass

    @abstractmethod
    def _init_det_fw(self) -> None:
        """
        Init parameters for detector filewriter

        Raises (optional):
            DetectorError: if filewriter cannot be initialized
        """
        pass

    @abstractmethod
    def _set_trigger(self, trigger_source) -> None:
        """
        Set trigger source for the detector

        Args:
            trigger_source (enum.IntEnum): trigger source
        """
        pass

    @abstractmethod
    def _prep_det_fw(self) -> None:
        """
        Prepare detector file writer for scan

        Raises (optional):
            DetectorError: If file writer cannot be prepared
        """
        pass

    @abstractmethod
    def _stop_det_fw(self) -> None:
        """
        Stops detector file writer

        Raises (optional):
            DetectorError: If file writer cannot be stopped
        """
        pass

    @abstractmethod
    def _prep_det(self) -> None:
        """
        Prepare detector for scans
        """
        pass

    @abstractmethod
    def _stop_det(self) -> None:
        """
        Stop the detector and wait for the proper status message

        Raises (optional):
            DetectorError: If detector cannot be prepared
        """
        pass

    @abstractmethod
    def _arm_acquisition(self) -> None:
        """Arm detector for acquisition"""
        pass

    @abstractmethod
    def trigger(self) -> None:
        """
        Trigger the detector, called from BEC

        Internal Calls:
        - _on_trigger     : call trigger action
        """
        self._on_trigger()

    @abstractmethod
    def _on_trigger(self) -> None:
        """
        Specify action that should be taken upon trigger signal
        """
        pass

    @abstractmethod
    def stop(self, *, success=False) -> None:
        """
        Stop the scan, with camera and file writer

        Internal Calls:
        - _stop_det     : stop detector
        - _stop_det_fw : stop detector filewriter
        """
        pass

    # TODO maybe not required to overwrite, but simply used by the user.
    # If yes, then self.scaninfo.scanID & self.scaninfo.name  & self.filepath
    # should become input arguments
    @abstractmethod
    def _publish_file_location(self, done: bool = False, successful: bool = None) -> None:
        """Publish the file location/event to bec

        Two events are published:
        - file_event  : event for the filewriter
        - public_file : event for any secondary service (e.g. radial integ code)

        Args:
            done (bool): True if scan is finished
            successful (bool): True if scan was successful

        """
        pipe = self._producer.pipeline()
        if successful is None:
            msg = BECMessage.FileMessage(file_path=self.filepath, done=done)
        else:
            msg = BECMessage.FileMessage(file_path=self.filepath, done=done, successful=successful)
        self._producer.set_and_publish(
            MessageEndpoints.public_file(self.scaninfo.scanID, self.name), msg.dumps(), pipe=pipe
        )
        self._producer.set_and_publish(
            MessageEndpoints.file_event(self.name), msg.dumps(), pipe=pipe
        )
        pipe.execute()

    @abstractmethod
    def stage(self) -> List(object):
        """
        Stage device in preparation for a scan

        Internal Calls:
        - _prep_det_fw           : prepare detector filewriter for measurement
        - _prep_det              : prepare detector for measurement
        - _publish_file_location : publish file location to bec

        Returns:
            List(object): list of objects that were staged

        """
        # Method idempotent, should rais ;obj;'RedudantStaging' if staged twice
        if self._staged != Staged.no:
            return super().stage()
        else:
            # Reset flag for detector stopped
            self._stopped = False
            # Load metadata of the scan
            self.scaninfo.load_scan_metadata()
            # Prepare detector and file writer
            self._prep_det_fw()
            self._prep_det()
            state = False
            self._publish_file_location(done=state)
            return super().stage()

    @abstractmethod
    def unstage(self):
        """
        Unstage device in preparation for a scan

        Returns directly if self._stopped,
        otherwise checks with self._finished
        if data acquisition on device finished (an was successful)

        Internal Calls:
        - _finished              : check if device finished acquisition (succesfully)
        - _publish_file_location : publish file location to bec
        """
        # Check if scan was stopped
        old_scanID = self.scaninfo.scanID
        self.scaninfo.load_scan_metadata()
        if self.scaninfo.scanID != old_scanID:
            self._stopped = True
        if self._stopped == True:
            return super().unstage()
        # check if device finished acquisition
        self._finished()
        state = True
        # Publish file location to bec
        self._publish_file_location(done=state, successful=state)
        self._stopped = False
        return super().unstage()

    def _finished(self):
        """
        Check if acquisition on device finished (succesfully)

        This function is called from unstage, and will check if
        detector and filewriter of the detector return from acquisition.
        If desired, it can also raise in case data acquisition was incomplete

        Small examples:
            (1) check detector & detector filewriter status
            if both finished --> good, if either is not finished --> raise
            (2) (Optional) check if number of images received
            is equivalent to the number of images requested

        Raises (optional):
            TimeoutError: if data acquisition was incomplete
        """
        pass
