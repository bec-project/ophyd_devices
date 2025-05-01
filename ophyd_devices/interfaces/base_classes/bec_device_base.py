"""
This module contains the base class for custom device integrations at PSI.
Please check the device section in BEC's developer documentation
(https://bec.readthedocs.io/en/latest/) for more information about device integration.
"""

import os
import threading
import time
import traceback
from typing import Generic, TypeVar

from bec_lib.file_utils import FileWriter
from bec_lib.logger import bec_logger
from ophyd import Device, DeviceStatus, Kind
from ophyd.device import Staged

from ophyd_devices.utils import bec_utils
from ophyd_devices.utils.bec_scaninfo_mixin import BecScaninfoMixin
from ophyd_devices.utils.errors import DeviceStopError, DeviceTimeoutError

logger = bec_logger.logger

T = TypeVar("T", bound="BECDeviceBase")


class BECDeviceBaseError(Exception):
    """Error class for BECDeviceBase."""


class CustomPrepare(Generic[T]):
    """Custom prepare class for beamline specific logic.

    This class provides a set of hooks for beamline specific logic to be implemented.
    BECDeviceBase will be injected as the parent device.

    To implement custom logic, inherit from this class and implement the desired methods.
    If the __init__ method is overwritten, please ensure the proper initialisation.
    It is important to pass the parent device to the custom prepare class as this
    will allow the custom prepare class to access the parent device with all its signals.
    """

    def __init__(self, *_args, parent: T = None, **_kwargs) -> None:
        """
        Initialize the custom prepare class.

        Args:
            parent (BECDeviceBase): The parent device which gives access to all methods and signals.
        """
        self.parent = parent

    def on_init(self) -> None:
        """
        Hook for beamline specific logic during class initialization.

        This method is called during the initialization of the device class.
        It should not be used to set any of the class's signals as they may not
        be connected yet.
        """
        pass

    def on_wait_for_connection(self) -> None:
        """
        Hook for beamline specific logic during the wait_for_connection method.

        This method is called after Ophyd's wait_for_connection method was called,
        meaning that signals will be connected at this point. It can be used to check
        signal values, or set default values for those.
        """

    def on_stage(self) -> None:
        """
        Hook for beamline specific logic during the stage method.

        This method is called during the stage method of the device class.
        It is used to implement logic in preparation for a scan."""

    def on_unstage(self) -> None:
        """
        Hook for beamline specific logic during the unstage method.

        This method is called during the unstage method of the device class.
        It is used to implement logic to clean up the device after a scan.
        """

    def on_stop(self) -> None:
        """Hook for beamline specific logic during the stop method."""

    def on_trigger(self) -> None | DeviceStatus:
        """
        Hook for beamline specific logic during the trigger method.

        This method has to be non-blocking, and if time-consuming actions are necessary,
        they should be implemented asynchronously. Please check the wait_with_status
        method to implement asynchronous checks.

        The softwareTrigger config value needs to be set to True to indicate to BEC
        that the device should be triggered from the software during the scan.

        Returns:
            DeviceStatus: DeviceStatus object that BEC will use to check if the trigger was successful
        """

    def on_pre_scan(self) -> None:
        """
        Hook for beamline specific logic during the pre_scan method.

        This method is called from BEC just before the scan core starts, and be used
        to execute time-critical actions, e.g. arming a detector in case there is a risk of timing out.
        Note, this method should not be used to implement blocking logic.
        """

    def on_complete(self) -> None | DeviceStatus:
        """
        Hook for beamline specific logic during the complete method.

        This method is used to check whether the device has successfully completed its acquisition.
        For example, a detector may want to check if it has received the correct number of frames, or
        if it's data backend has finished writing the data to disk. The method should be implemented
        asynchronously. Please check the wait_with_status method on how to implement asynchronous checks.

        Returns:
            DeviceStatus: DeviceStatus object that BEC will use to check if the device has successfully completed
        """

    def on_kickoff(self) -> None | DeviceStatus:
        """
        Hook for beamline specific logic during the kickoff method.

        This method is called to kickoff the flyer acquisition. BEC will not call this method in general
        for its scans, but only if the scan explicitly implements this. The method should be non-blocking,
        and if time-consuming actions are necessary, they should be implemented asynchronously.
        Please check the wait_with_status method on how to implement asynchronous checks.

        Returns:
            DeviceStatus: DeviceStatus object that BEC will use to check if the kickoff was successful
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
        Utility method to implement waiting for signals to reach a certain condition. It accepts
        a list of conditions passed as tuples of executable calls for conditions (get_current_state, condition) to check.
        It can further be specified if all signals should be True or if any signal should be True.
        If the timeout is reached, it will return False.

        Args:
            signal_conditions (list[tuple]): tuple of executable calls for conditions (get_current_state, condition) to check
            timeout (float): timeout in seconds
            check_stopped (bool): True if stopped flag should be checked
            interval (float): interval in seconds
            all_signals (bool): True if all signals should be True, False if any signal should be True

        Returns:
            bool: True if all signals are in the desired state, False if timeout is reached

        Example:
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
        """
        Utility method to implement asynchronous waiting for signals to reach a certain condition.
        It accepts a list of conditions passed as tuples of executable calls.

        Please check the wait_for_signals method as it is used to implement the waiting logic.
        It returns a DeviceStatus object that can be used to check if the asynchronous action is done
        through 'status.done', and if it was successful through 'status.success'. An exception can be
        passed to the method which will be raised if the timeout is reached. If the device was stopped
        during the waiting, a DeviceStopError will be raised.

        Args:
            signal_conditions (list[tuple]): tuple of executable calls for conditions (get_current_state, condition) to check
            timeout (float): timeout in seconds
            check_stopped (bool): True if stopped flag should be checked
            interval (float): interval in seconds
            all_signals (bool): True if all signals should be True, False if any signal should be True
            exception_on_timeout (Exception): Exception to raise on timeout

        Returns:
            DeviceStatus: DeviceStatus object to check the state of the asynchronous action (status.done, status.success)

        Example:
            >>> status = self.wait_with_status(signal_conditions=[(self.acquiring.get, False)], timeout=5, interval=0.05, check_stopped=True, all_signals=True)
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


class BECDeviceBase(Device):
    """
    Base class for custom device integrations at PSI. This class wraps around the ophyd's standard
    set of methods, providing hooks for custom logic to be implemented in the custom_prepare_cls.

    Please check the device section in BEC's developer documentation
    (https://bec.readthedocs.io/en/latest/) for more information about device integration.
    """

    custom_prepare_cls = CustomPrepare

    # All possible subscription types that the Device Manager subscribes to
    # Run the command _run_subs(sub_type=self.SUB_VALUE, value=value) to trigger
    # the subscription of type value. Please be aware that the signature of
    # the subscription callbacks needs to be matched.
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
        """
        Initialize the device.

        Args:
            name (str): name of the device
            prefix (str): prefix of the device
            kind (Kind): kind of the device
            parent (Device): parent device
            device_manager (DeviceManager): device manager. BEC will inject the device manager as a dependency.
        """
        super().__init__(prefix=prefix, name=name, kind=kind, parent=parent, **kwargs)
        self._stopped = False
        self.service_cfg = None
        self.scaninfo = None
        self.filewriter = None

        if not issubclass(self.custom_prepare_cls, CustomPrepare):
            raise BECDeviceBaseError(
                f"Custom prepare class must be subclass of CustomDetectorMixin, provided: {self.custom_prepare_cls}"
            )
        self.custom_prepare = self.custom_prepare_cls(parent=self, **kwargs)

        if device_manager:
            self._update_service_config()
            self.device_manager = device_manager
        else:
            # If device manager is not provided through dependency injection
            # A mock device manager is created. This is necessary to be able
            # to use the device class in a standalone context without BEC.
            self.device_manager = bec_utils.DMMock()
            base_path = kwargs["basepath"] if "basepath" in kwargs else "."
            self.service_cfg = {"base_path": os.path.abspath(base_path)}

        self.connector = self.device_manager.connector
        self._update_scaninfo()
        self._update_filewriter()
        self._init()

    @property
    def stopped(self) -> bool:
        """Property to indicate if the device was stopped."""
        return self._stopped

    @stopped.setter
    def stopped(self, value: bool) -> None:
        self._stopped = value

    def _update_filewriter(self) -> None:
        """Initialise the file writer utility class."""
        self.filewriter = FileWriter(service_config=self.service_cfg, connector=self.connector)

    def _update_scaninfo(self) -> None:
        """Initialise the utility class to get scan metadata from BEC."""
        self.scaninfo = BecScaninfoMixin(self.device_manager)
        self.scaninfo.load_scan_metadata()

    def _update_service_config(self) -> None:
        """Update the Service Config. This has the info on where REDIS and other services are running."""
        # pylint: disable=import-outside-toplevel
        from bec_lib.bec_service import SERVICE_CONFIG

        if SERVICE_CONFIG:
            self.service_cfg = SERVICE_CONFIG.config["service_config"]["file_writer"]
            return
        self.service_cfg = {"base_path": os.path.abspath(".")}

    def check_scan_id(self) -> None:
        """
        Check if the scan ID has changed, if yes, set the stopped property to True.

        The idea is that if the scan ID on the device and the scan ID from BEC are different,
        the device is out of sync with the scan and should be stopped.
        """
        old_scan_id = self.scaninfo.scan_id
        self.scaninfo.load_scan_metadata()
        if self.scaninfo.scan_id != old_scan_id:
            self.stopped = True

    def _init(self) -> None:
        """
        Hook for beamline specific logic during class initialization.

        Please to not set any of the class's signals during intialisation, but
        instead use the wait_for_connection.
        """
        self.custom_prepare.on_init()

    def wait_for_connection(self, all_signals=False, timeout=5) -> None:
        """
        Thin wrapper around ophyd's wait_for_connection.

        Calling Ophyd's wait_for_connection will ensure that signals are connected. BEC
        will call this method if a device is not connected yet. This method should
        be used to set up default values for signals, or to check if the device signals
        are in the expected state.

        Args:
            all_signals (bool): True if all signals should be considered. Default is False.
            timeout (float): timeout in seconds. Default is 5 seconds.
        """
        super().wait_for_connection(all_signals, timeout)
        self.custom_prepare.on_wait_for_connection()

    def stage(self) -> list[object]:
        """
        Thin wrapper around ophyd's stage, the method called in preparation for a scan.

        Stage is idempotent, if staged twice it should raise (we let ophyd.Device handle the raise here).
        Other that that, we reset the stopped property in case the device was stopped before, and
        pull the latest scan metadata from BEC. Ater that, we allow for beamline specific logic to
        be implemented through the custom_prepare.on_stage method.

        Returns:
            list(object): list of objects that were staged
        """
        if self._staged != Staged.no:
            return super().stage()
        self.stopped = False
        self.scaninfo.load_scan_metadata()
        self.custom_prepare.on_stage()
        return super().stage()

    def unstage(self) -> list[object]:
        """
        This wrapper around ophyd's unstage method, which is called to clean up the device.

        It must be possible to call unstage multiple times without raising an exception. It should
        be implemented to clean up the device if it is in a staged state.

        Beamline specific logic can be implemented through the custom_prepare.on_unstage method.

        Returns:
            list(object): list of objects that were unstaged
        """
        self.check_scan_id()
        self.custom_prepare.on_unstage()
        self.stopped = False
        return super().unstage()

    def pre_scan(self) -> None:
        """
        Pre-scan is a method introduced by BEC that is not native to the ophyd interface.

        This method is called from BEC just before the scan core starts, and therefore should only
        implement time-critical actions. I.e. Arming a detector in case there is a risk of timing out.
        """
        self.custom_prepare.on_pre_scan()

    def trigger(self) -> DeviceStatus:
        """
        Thin wrapper around the trigger method of the device, for which the config value
        softwareTrigger needs to be set to True, which will indicate to BEC that the device
        should be triggered from the software during the scan.

        Custom logic should be implemented non-blocking, i.e. be fast, or implemented asynchroniously.

        Returns:
            DeviceStatus: DeviceStatus object that BEC will use to check if the trigger was successful.
        """
        # pylint: disable=assignment-from-no-return
        status = self.custom_prepare.on_trigger()
        if isinstance(status, DeviceStatus):
            return status
        return super().trigger()

    def complete(self) -> DeviceStatus:
        """
        Thin wrapper around ophyd's complete method. Complete is called once the scan core
        has finished, but before the scan is closed. It will be called before unstage.
        It can also be used for fly scans to track the status of the flyer, and indicate if the
        flyer has completed.

        The method is used to check whether the device has successfully completed the acquisition.
        Actions are implemented in custom_prepare.on_complete since they are beamline specific.

        This method has to be non-blocking. If checks are necessary, they should be implemented asynchronously.

        Returns:
            DeviceStatus: DeviceStatus object that BEC will use to check if the device has successfully completed.
        """
        # pylint: disable=assignment-from-no-return
        status = self.custom_prepare.on_complete()
        if isinstance(status, DeviceStatus):
            return status
        status = DeviceStatus(self)
        status.set_finished()
        return status

    def stop(self, *, success=False) -> None:
        """Stop the device.

        Args:
            success (bool): Argument from ophyd's stop method. Default is False.
        """
        self.custom_prepare.on_stop()
        super().stop(success=success)
        self.stopped = True

    def kickoff(self) -> DeviceStatus:
        """
        This wrapper around Ophyd's kickoff method.

        Kickoff is a method native to the flyer interface of Ophyd. It is called to
        start the flyer acquisition. This method is not called by BEC in general, but
        only if the scan explicitly implements this.

        The method should be non-blocking, and if time-consuming actions are necessary,
        they should be implemented asynchronously.

        Returns:
            DeviceStatus: DeviceStatus object that BEC will use to check if the kickoff was successful.
        """
        # pylint: disable=assignment-from-no-return
        status = self.custom_prepare.on_kickoff()
        if isinstance(status, DeviceStatus):
            return status
        status = DeviceStatus(self)
        status.set_finished()
        return status
