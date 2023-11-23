import time
import os

from typing import List

from ophyd import Device
from ophyd.device import Staged

from bec_lib.file_utils import FileWriterMixin
from bec_lib.bec_service import SERVICE_CONFIG
from bec_lib.devicemanager import DeviceStatus

from ophyd_devices.epics.devices.bec_scaninfo_mixin import BecScaninfoMixin
from ophyd_devices.utils import bec_utils


class DetectorInitError(Exception):
    """Raised when initiation of the device class fails,
    due to missing device manager or not started in sim_mode."""


class CustomDetectorMixin:
    """
    Mixin class for custom detector logic

    This class is used to implement BL specific logic for the detector.
    It is used in the PSIDetectorBase class.

    For the integration of a new detector, the following functions should
    help with integrating functionality, but additional ones can be added.

    Check PSIDetectorBase for the functions that are called during relevant function calls of
    stage, unstage, trigger, stop and _init.
    """

    def __init__(self, *_args, parent: Device = None, **_kwargs) -> None:
        self.parent = parent

    def initialize_default_parameter(self) -> None:
        """
        Init parameters for the detector

        Raises (optional):
            DetectorTimeoutError: if detector cannot be initialized
        """

    def initialize_detector(self) -> None:
        """
        Init parameters for the detector

        Raises (optional):
            DetectorTimeoutError: if detector cannot be initialized
        """

    def initialize_detector_backend(self) -> None:
        """
        Init parameters for teh detector backend (filewriter)

        Raises (optional):
            DetectorTimeoutError: if filewriter cannot be initialized
        """

    def prepare_detector(self) -> None:
        """
        Prepare detector for the scan
        """

    def prepare_detector_backend(self) -> None:
        """
        Prepare detector backend for the scan
        """

    def stop_detector(self) -> None:
        """
        Stop the detector
        """

    def stop_detector_backend(self) -> None:
        """
        Stop the detector backend
        """

    def on_trigger(self) -> None:
        """
        Specify actions to be executed upon receiving trigger signal
        """

    def pre_scan(self) -> None:
        """
        Specify actions to be executed right before a scan

        BEC calls pre_scan just before execution of the scan core.
        It is convenient to execute time critical features of the detector,
        e.g. arming it, but it is recommended to keep this function as short/fast as possible.
        """

    def finished(self) -> None:
        """
        Specify actions to be executed during unstage

        This may include checks if acquisition was succesful

        Raises (optional):
            DetectorTimeoutError: if detector cannot be stopped
        """

    def check_scanID(self) -> None:
        """
        Check if BEC is running on a new scanID
        """

    def publish_file_location(self, done: bool = False, successful: bool = None) -> None:
        """
        Publish the designated filepath from data backend to REDIS.

        Typically, the following two message types are published:

        - file_event: event for the filewriter
        - public_file: event for any secondary service (e.g. radial integ code)
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
            if check_stopped is True and self.parent.stopped is True:
                return False
            if (all_signals and all(checks)) or (not all_signals and any(checks)):
                return True
            if timer > timeout:
                return False
            time.sleep(interval)
            timer += interval


class PSIDetectorBase(Device):
    """
    Abstract base class for SLS detectors

    Class attributes:
        custom_prepare_cls (object): class for custom prepare logic (BL specific)
        Min_readout (float): minimum readout time for detector

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

    MIN_READOUT = 1e-3

    # Specify which functions are revealed to the user in BEC client
    USER_ACCESS = [
        "describe",
    ]

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
            raise DetectorInitError(
                f"No device manager for device: {name}, and not started sim_mode: {sim_mode}. Add"
                " DeviceManager to initialization or init with sim_mode=True"
            )
        # Init variables
        self.sim_mode = sim_mode
        self.stopped = False
        self.name = name
        self.service_cfg = None
        self.scaninfo = None
        self.filewriter = None
        self.timeout = 5
        self.wait_for_connection(all_signals=True)

        # Init custom prepare class with BL specific logic
        self.custom_prepare = self.custom_prepare_cls(parent=self, **kwargs)
        if not sim_mode:
            self._update_service_config()
            self.device_manager = device_manager
        else:
            self.device_manager = bec_utils.DMMock()
            base_path = kwargs["basepath"] if "basepath" in kwargs else "~/Data10/"
            self.service_cfg = {"base_path": os.path.expanduser(base_path)}
        self.producer = self.device_manager.producer
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
        self.stopped = False
        # Load metadata of the scan
        self.scaninfo.load_scan_metadata()
        # Prepare detector and file writer
        self.custom_prepare.prepare_detector_backend()
        self.custom_prepare.prepare_detector()
        state = False
        self.custom_prepare.publish_file_location(done=state)
        # At the moment needed bc signal might not be reliable, BEC too fast.
        # Consider removing this overhead in future!
        time.sleep(0.05)
        return super().stage()

    def trigger(self) -> DeviceStatus:
        """Trigger the detector, called from BEC."""
        self.custom_prepare.on_trigger()
        return super().trigger()

    def unstage(self) -> List[object]:
        """
        Unstage device in preparation for a scan

        Returns directly if self.stopped,
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
        if self.stopped is True:
            return super().unstage()
        self.custom_prepare.finished()
        state = True
        self.custom_prepare.publish_file_location(done=state, successful=state)
        self.stopped = False
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
        self.stopped = True
