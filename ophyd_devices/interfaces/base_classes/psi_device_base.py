"""This module contains the base class for SLS detectors. We follow the approach to integrate
PSI detectors into the BEC system based on this base class. The base class is used to implement
certain methods that are expected by BEC, such as stage, unstage, trigger, stop, etc...
We use composition with a custom prepare class to implement BL specific logic for the detector.
The beamlines need to inherit from the CustomDetectorMixing for their mixin classes."""

import os
import threading
import time
import traceback

from bec_lib.file_utils import FileWriter
from bec_lib.logger import bec_logger
from ophyd import Device, DeviceStatus, Kind
from ophyd.device import Staged

from ophyd_devices.utils import bec_utils
from ophyd_devices.utils.bec_scaninfo_mixin import BecScaninfoMixin
from ophyd_devices.utils.errors import DeviceStopError, DeviceTimeoutError

logger = bec_logger.logger


class PSIDeviceBaseError(Exception):
    """Error specific for the PSIDeviceBase class."""


class CustomPrepare:
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

    def on_init(self) -> None:
        """
        Init sequence for the Device. This method should be fast and not rely on setting any signals.
        """

    def on_wait_for_connection(self) -> None:
        """
        Specify actions to be executed when waiting for the device to connect.
        The on method is called after the device is connected, thus, signals are ready to be set.
        This should be used to set initial values for signals, e.g. setting the velocity of a motor.
        """

    def on_stage(self) -> None:
        """
        Specify actions to be executed during stage in preparation for a scan.
        self.parent.scaninfo already has all current parameters for the upcoming scan.

        In case the backend service is writing data on disk, this step should include publishing
        a file_event and file_message to BEC to inform the system where the data is written to.

        IMPORTANT:
        It must be safe to assume that the device is ready for the scan
        to start immediately once this function is finished.
        """

    def on_unstage(self) -> None:
        """
        Specify actions to be executed during unstage.

        This step should include checking if the acqusition was successful,
        and publishing the file location and file event message,
        with flagged done to BEC.
        """

    def on_stop(self) -> None:
        """
        Specify actions to be executed during stop.
        This must also set self.parent.stopped to True.

        This step should include stopping the detector and backend service.
        """

    def on_trigger(self) -> None | DeviceStatus:
        """
        Specify actions to be executed upon receiving trigger signal.
        Return a DeviceStatus object or None
        """

    def on_pre_scan(self) -> None:
        """
        Specify actions to be executed right before a scan starts.

        Only use if needed, and it is recommended to keep this function as short/fast as possible.
        """

    def on_complete(self) -> None | DeviceStatus:
        """
        Specify actions to be executed when the scan is complete.

        This can for instance be to check with the detector and backend if all data is written succsessfully.
        """

    def on_kickoff(self) -> None | DeviceStatus:
        """Flyer specific method to kickoff the device.

        Actions should be fast or, if time consuming,
        implemented non-blocking and return a DeviceStatus object.
        """

    def wait_for_signals(
        self,
        signal_conditions: list[tuple],
        timeout: float,
        check_stopped: bool = False,
        interval: float = 0.05,
        all_signals: bool = False,
    ) -> bool:
        """
        Convenience wrapper to allow waiting for signals to reach a certain condition.
        For EPICs PVs, an example usage is pasted at the bottom.

        Args:
            signal_conditions (list[tuple]): tuple of executable calls for conditions (get_current_state, condition) to check
            timeout (float): timeout in seconds
            interval (float): interval in seconds
            all_signals (bool): True if all signals should be True, False if any signal should be True

        Returns:
            bool: True if all signals are in the desired state, False if timeout is reached

            >>> Example usage for EPICS PVs:
            >>> self.wait_for_signals(signal_conditions=[(self.acquiring.get, False)], timeout=5, interval=0.05, check_stopped=True, all_signals=True)
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

    def wait_with_status(
        self,
        signal_conditions: list[tuple],
        timeout: float,
        check_stopped: bool = False,
        interval: float = 0.05,
        all_signals: bool = False,
        exception_on_timeout: Exception = None,
    ) -> DeviceStatus:
        """Utility function to wait for signals in a thread.
        Returns a DevicesStatus object that resolves either to set_finished or set_exception.
        The DeviceStatus is attached to the paent device, i.e. the detector object inheriting from PSIDetectorBase.

        Usage:
        This function should be used to wait for signals to reach a certain condition, especially in the context of
        on_trigger and on_complete. If it is not used, functions may block and slow down the performance of BEC.
        It will return a DeviceStatus object that is to be returned from the function. Once the conditions are met,
        the DeviceStatus will be set to set_finished in case of success or set_exception in case of a timeout or exception.
        The exception can be specified with the exception_on_timeout argument. The default exception is a TimeoutError.

        Args:
            signal_conditions (list[tuple]): tuple of executable calls for conditions (get_current_state, condition) to check
            timeout (float): timeout in seconds
            check_stopped (bool): True if stopped flag should be checked
            interval (float): interval in seconds
            all_signals (bool): True if all signals should be True, False if any signal should be True
            exception_on_timeout (Exception): Exception to raise on timeout

        Returns:
            DeviceStatus: DeviceStatus object that resolves either to set_finished or set_exception
        """
        if exception_on_timeout is None:
            exception_on_timeout = DeviceTimeoutError(
                f"Timeout error for {self.parent.name} while waiting for signals {signal_conditions}"
            )

        status = DeviceStatus(self.parent)

        # utility function to wrap the wait_for_signals function
        def wait_for_signals_wrapper(
            status: DeviceStatus,
            signal_conditions: list[tuple],
            timeout: float,
            check_stopped: bool,
            interval: float,
            all_signals: bool,
            exception_on_timeout: Exception,
        ):
            """Convenient wrapper around wait_for_signals to set status based on the result.

            Args:
                status (DeviceStatus): DeviceStatus object to be set
                signal_conditions (list[tuple]): tuple of executable calls for conditions (get_current_state, condition) to check
                timeout (float): timeout in seconds
                check_stopped (bool): True if stopped flag should be checked
                interval (float): interval in seconds
                all_signals (bool): True if all signals should be True, False if any signal should be True
                exception_on_timeout (Exception): Exception to raise on timeout
            """
            try:
                result = self.wait_for_signals(
                    signal_conditions, timeout, check_stopped, interval, all_signals
                )
                if result:
                    status.set_finished()
                else:
                    if self.parent.stopped:
                        # INFO This will execute a callback to the parent device.stop() method
                        status.set_exception(exc=DeviceStopError(f"{self.parent.name} was stopped"))
                    else:
                        # INFO This will execute a callback to the parent device.stop() method
                        status.set_exception(exc=exception_on_timeout)
            # pylint: disable=broad-except
            except Exception as exc:
                content = traceback.format_exc()
                logger.warning(
                    f"Error in wait_for_signals in {self.parent.name}; Traceback: {content}"
                )
                # INFO This will execute a callback to the parent device.stop() method
                status.set_exception(exc=exc)

        thread = threading.Thread(
            target=wait_for_signals_wrapper,
            args=(
                status,
                signal_conditions,
                timeout,
                check_stopped,
                interval,
                all_signals,
                exception_on_timeout,
            ),
            daemon=True,
        )
        thread.start()
        return status


class PSIDeviceBase(Device):
    """
    Base class for custom device integrations at PSI. This class wraps around the ophyd's standard
    set of methods, providing hooks for custom logic to be implemented in the custom_prepare_cls.

    Please check the device section in the developer section within the BEC documentation
    (https://bec.readthedocs.io/en/latest/) for more information on how to integrate a new device using
    this base class.
    """

    custom_prepare_cls = CustomPrepare

    # It can not hurt to define all just in case, or will it?
    SUB_READBACK = "readback"
    SUB_VALUE = "value"
    SUB_DONE_MOVING = "done_moving"
    SUB_MOTOR_IS_MOVING = "motor_is_moving"
    SUB_PROGRESS = "progress"
    SUB_FILE_EVENT = "file_event"
    SUB_DEVICE_MONITOR_1D = "device_monitor_1d"
    SUB_DEVICE_MONITOR_2D = "device_monitor_2d"
    _default_sub = SUB_VALUE

    def __init__(
        self,
        name: str,
        prefix: str = "",
        kind: Kind | None = None,
        parent=None,
        device_manager=None,
        **kwargs,
    ):
        super().__init__(prefix=prefix, name=name, kind=kind, parent=parent, **kwargs)
        self._stopped = False
        self.service_cfg = None
        self.scaninfo = None
        self.filewriter = None

        if not issubclass(self.custom_prepare_cls, CustomPrepare):
            raise PSIDeviceBaseError(
                f"Custom prepare class must be subclass of CustomDetectorMixin, provided: {self.custom_prepare_cls}"
            )
        self.custom_prepare = self.custom_prepare_cls(parent=self, **kwargs)

        if device_manager:
            self._update_service_config()
            self.device_manager = device_manager
        else:
            self.device_manager = bec_utils.DMMock()
            base_path = kwargs["basepath"] if "basepath" in kwargs else "."
            self.service_cfg = {"base_path": os.path.abspath(base_path)}

        self.connector = self.device_manager.connector
        self._update_scaninfo()
        self._update_filewriter()
        self._init()

    @property
    def stopped(self) -> bool:
        """Flag to indicate if the device is stopped"""
        return self._stopped

    @stopped.setter
    def stopped(self, value: bool) -> None:
        """Set the stopped flag"""
        self._stopped = value

    def _update_filewriter(self) -> None:
        """Update filewriter with service config"""
        self.filewriter = FileWriter(service_config=self.service_cfg, connector=self.connector)

    def _update_scaninfo(self) -> None:
        """Update scaninfo from BecScaninfoMixing
        This depends on device manager and operation/sim_mode
        """
        self.scaninfo = BecScaninfoMixin(self.device_manager)
        self.scaninfo.load_scan_metadata()

    def _update_service_config(self) -> None:
        """Update service config from BEC service config

        If bec services are not running and SERVICE_CONFIG is NONE, we fall back to the current directory.
        """
        # pylint: disable=import-outside-toplevel
        from bec_lib.bec_service import SERVICE_CONFIG

        if SERVICE_CONFIG:
            self.service_cfg = SERVICE_CONFIG.config["service_config"]["file_writer"]
            return
        self.service_cfg = {"base_path": os.path.abspath(".")}

    def check_scan_id(self) -> None:
        """Checks if scan_id has changed and set stopped flagged to True if it has."""
        old_scan_id = self.scaninfo.scan_id
        self.scaninfo.load_scan_metadata()
        if self.scaninfo.scan_id != old_scan_id:
            self.stopped = True

    def _init(self) -> None:
        """Initialize detector, filewriter and set default parameters"""
        self.custom_prepare.on_init()

    def stage(self) -> list[object]:
        """
        Stage device in preparation for a scan.
        First we check if the device is already staged. Stage is idempotent,
        if staged twice it should raise (we let ophyd.Device handle the raise here).
        We reset the stopped flag and get the scaninfo from BEC, before calling custom_prepare.on_stage.

        Returns:
            list(object): list of objects that were staged

        """
        if self._staged != Staged.no:
            return super().stage()
        self.stopped = False
        self.scaninfo.load_scan_metadata()
        self.custom_prepare.on_stage()
        return super().stage()

    def pre_scan(self) -> None:
        """Pre-scan logic.

        This function will be called from BEC directly before the scan core starts, and should only implement
        time-critical actions. Therefore, it should also be kept as short/fast as possible.
        I.e. Arming a detector in case there is a risk of timing out.
        """
        self.custom_prepare.on_pre_scan()

    def trigger(self) -> DeviceStatus:
        """Trigger the detector, called from BEC."""
        # pylint: disable=assignment-from-no-return
        status = self.custom_prepare.on_trigger()
        if isinstance(status, DeviceStatus):
            return status
        return super().trigger()

    def complete(self) -> None:
        """Complete the acquisition, called from BEC.

        This function is called after the scan is complete, just before unstage.
        We can check here with the data backend and detector if the acquisition successfully finished.

        Actions are implemented in custom_prepare.on_complete since they are beamline specific.
        """
        # pylint: disable=assignment-from-no-return
        status = self.custom_prepare.on_complete()
        if isinstance(status, DeviceStatus):
            return status
        status = DeviceStatus(self)
        status.set_finished()
        return status

    def unstage(self) -> list[object]:
        """
        Unstage device after a scan.

        We first check if the scanID has changed, thus, the scan was unexpectedly interrupted but the device was not stopped.
        If that is the case, the stopped flag is set to True, which will immediately unstage the device.

        Custom_prepare.on_unstage is called to allow for BL specific logic to be executed.

        Returns:
            list(object): list of objects that were unstaged
        """
        self.check_scan_id()
        self.custom_prepare.on_unstage()
        self.stopped = False
        return super().unstage()

    def stop(self, *, success=False) -> None:
        """
        Stop the scan, with camera and file writer

        """
        self.custom_prepare.on_stop()
        super().stop(success=success)
        self.stopped = True

    def wait_for_connection(self, all_signals=False, timeout=5) -> None:
        super().wait_for_connection(all_signals, timeout)
        self.custom_prepare.on_wait_for_connection()

    def kickoff(self) -> None:
        """Kickoff the device"""
        status = self.custom_prepare.on_kickoff()
        if isinstance(status, DeviceStatus):
            return status
        status = DeviceStatus(self)
        status.set_finished()
        return status
