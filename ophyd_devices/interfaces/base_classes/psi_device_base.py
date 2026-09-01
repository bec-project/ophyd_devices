"""
Base class for all PSI ophyd device integration to ensure consistent configuration
"""

from __future__ import annotations

import inspect
import math
import time
from typing import TYPE_CHECKING, Callable

from ophyd import Device, Staged
from ophyd.status import StatusBase as OphydStatusBase

from ophyd_devices.tests.utils import get_mock_scan_info
from ophyd_devices.utils.psi_device_base_utils import (
    NO_TIMEOUT,
    DeviceStatus,
    FileHandler,
    TaskHandler,
)

if TYPE_CHECKING:  # pragma: no cover
    from bec_lib.devicemanager import DeviceManagerBase, ScanInfo


class DeviceStoppedError(Exception):
    """Exception raised when a device is stopped"""


class PSIDeviceBase(Device):
    """
    Base class for all PSI ophyd devices to ensure consistent configuration
    and communication with BEC services.
    """

    # These are all possible subscription types that the device_manager supports
    # and automatically subscribes to
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
        *,
        name: str,
        prefix: str = "",
        timeout: float | None = None,
        scan_info: ScanInfo | None = None,
        device_manager: DeviceManagerBase | None = None,
        **kwargs,
    ):
        """
        Initialize the PSI Device Base class.

        Args:
            name (str) : Name of the device
            prefix (str): The prefix for the device.
            timeout (float): The default timeout for status objects created on this device,
                in seconds. None, non-positive, NaN or inf means no default timeout.
            scan_info (ScanInfo): The scan info to use.
            device_manager (DeviceManagerBase): The device manager to use.
        """
        timeout = self._normalize_timeout(timeout)
        self._timeout = timeout
        # Make sure device_manager is not passed to super().__init__ if not specified
        # This is to avoid issues with ophyd.OphydObject.__init__ when the parent is ophyd.Device
        # and the device_manager is passed to it. This will cause a TypeError.
        self.device_manager = device_manager
        sig = inspect.signature(super().__init__)
        if "device_manager" in sig.parameters:
            super().__init__(device_manager=device_manager, prefix=prefix, name=name, **kwargs)
        else:
            super().__init__(prefix=prefix, name=name, **kwargs)
        # PositionerBase.__init__ resets self._timeout to its own default (None); re-assert ours
        # so both the status default and PositionerBase.move() use the configured value.
        self._timeout = timeout
        self._set_timeout_signal(timeout)
        self._stopped = False
        self._stoppable_status_objects: list[OphydStatusBase] = []
        self.task_handler = TaskHandler(parent=self)
        self.file_utils = FileHandler()
        if scan_info is None:
            scan_info = get_mock_scan_info(device=self)
        self.scan_info = scan_info
        self.on_init()

    ########################################
    # Additional Properties and Attributes #
    ########################################

    @property
    def destroyed(self) -> bool:
        """Check if the device has been destroyed."""
        return self._destroyed

    @property
    def staged(self) -> Staged:
        """Check if the device has been staged."""
        return self._staged

    @property
    def stopped(self) -> bool:
        """Check if the device has been stopped."""
        return self._stopped

    @stopped.setter
    def stopped(self, value: bool):
        self._stopped = value

    @staticmethod
    def _normalize_timeout(timeout: float | int | None) -> float | None:
        """Normalize to a finite positive float; None, non-positive, NaN and inf mean no timeout."""
        if timeout is None:
            return None
        if isinstance(timeout, (bool, str, bytes)):
            raise TypeError(f"Timeout must be a number or None, got {timeout!r}")
        try:
            timeout = float(timeout)
        except (TypeError, ValueError) as exc:
            raise TypeError(f"Timeout must be a number or None, got {timeout!r}") from exc
        if not math.isfinite(timeout) or timeout <= 0:
            return None
        return timeout

    def _set_timeout_signal(self, timeout: float | None) -> None:
        """Initialize an optional timeout component from the normalized constructor value."""
        if timeout is None or "timeout" not in getattr(self, "component_names", ()):
            return
        self.timeout.put(timeout)

    ########################################
    # Wrapper around Device class methods  #
    ########################################

    def stage(self) -> list[object] | DeviceStatus | OphydStatusBase:  # type: ignore
        """Stage the device."""
        if self.staged != Staged.no:
            return super().stage()
        self.stopped = False
        super_staged = super().stage()
        status = self.on_stage()  # pylint: disable=assignment-from-no-return
        if isinstance(status, OphydStatusBase):
            return status
        return super_staged

    def unstage(self) -> list[object] | DeviceStatus | OphydStatusBase:  # type: ignore
        """Unstage the device."""
        super_unstage = super().unstage()
        status = self.on_unstage()  # pylint: disable=assignment-from-no-return
        self._stop_stoppable_status_objects()
        if isinstance(status, OphydStatusBase):
            return status
        return super_unstage

    def pre_scan(self) -> DeviceStatus | OphydStatusBase | None:
        """Pre-scan function."""
        status = self.on_pre_scan()  # pylint: disable=assignment-from-no-return
        return status

    def trigger(self) -> DeviceStatus | OphydStatusBase:
        """Trigger the device."""
        super_trigger = super().trigger()
        status = self.on_trigger()  # pylint: disable=assignment-from-no-return
        return status if status else super_trigger

    def complete(self) -> DeviceStatus | OphydStatusBase:
        """Complete the device."""
        status = self.on_complete()  # pylint: disable=assignment-from-no-return
        if isinstance(status, OphydStatusBase):
            return status
        # The fallback status is finished immediately; a timeout would only spawn
        # a wait thread and make .done flip asynchronously.
        status = DeviceStatus(self, timeout=NO_TIMEOUT)
        status.set_finished()
        return status

    def kickoff(self) -> DeviceStatus | OphydStatusBase:
        """Kickoff the device."""
        status = self.on_kickoff()  # pylint: disable=assignment-from-no-return
        if isinstance(status, OphydStatusBase):
            return status
        status = DeviceStatus(self, timeout=NO_TIMEOUT)
        status.set_finished()
        return status

    def stop(self, *, success: bool = False) -> None:
        """Stop the device.

        Args:
            success (bool): True if the action was successful, False otherwise.
        """
        self.on_stop()
        self.stopped = True  # Set stopped flag to True, in case a custom stop method listens to stopped property
        # Stop all stoppable status objects
        self._stop_stoppable_status_objects()
        super().stop(success=success)

    def destroy(self):
        """Destroy the device."""
        self.on_destroy()  # Call the on_destroy method
        self._stop_stoppable_status_objects()
        self.task_handler.shutdown()
        return super().destroy()

    ########################################
    # Stoppable Status Objects Management   #
    ########################################

    def cancel_on_stop(self, status: OphydStatusBase) -> None:
        """
        Register a status object to be cancelled when the device is stopped.

        Args:
            status (OphydStatusBase): The status object to be cancelled.
        """
        if not isinstance(status, OphydStatusBase):
            raise TypeError("status must be an instance of ophyd.StatusBase")
        self._stoppable_status_objects.append(status)

    def _clear_stoppable_status_objects(self) -> None:
        """
        Clear all registered stoppable status objects.

        This is useful to reset the list of status objects that should be cancelled
        when the device is stopped.
        """
        self._stoppable_status_objects = []

    def _stop_stoppable_status_objects(self) -> None:
        """
        Stop all registered stoppable status objects.

        This method will cancel all status objects that have been registered
        to be stopped when the device is stopped.
        """
        for status in self._stoppable_status_objects:
            if not status.done:
                status.set_exception(DeviceStoppedError(f"Device {self.name} has been stopped"))
        self._clear_stoppable_status_objects()

    ########################################
    # Utility Method to wait for signals   #
    ########################################

    def wait_for_condition(
        self,
        condition: Callable[[], bool],
        timeout: float,
        check_stopped: bool = False,
        interval: float = 0.05,
    ) -> bool:
        """
        Utility method to easily wait for signals or methods to reach an expected state.

        Args:
            condition (Callable): function that returns True if the condition is met, False otherwise
            timeout (float): timeout in seconds
            check_stopped (bool): True if stopped flag should be checked
            interval (float): interval in seconds

        Returns:
            bool: True if all signals are in the desired state, False if timeout is reached

        Example:
            >>> self.wait_for_condition(condition=my_condition, timeout=5, interval=0.05, check_stopped=True)
        """

        start_time = time.time()
        while time.time() < start_time + timeout:
            if condition() is True:
                return True
            if check_stopped is True and self.stopped is True:
                raise DeviceStoppedError(f"Device {self.name} has been stopped")
            time.sleep(interval)
        return False

    ########################################
    #  Beamline Specific Implementations   #
    ########################################

    def on_init(self) -> None:
        """
        Called when the device is initialized.

        No signals are connected at this point. If you like to
        set default values on signals, please use on_connected instead.
        """

    def on_connected(self) -> None:
        """
        Called after the device is connected and its signals are connected.
        Default values for signals should be set here.
        """

    def on_stage(self) -> DeviceStatus | OphydStatusBase | None:
        """
        Called while staging the device.

        Information about the upcoming scan can be accessed from the scan_info (self.scan_info.msg) object.
        """

    def on_unstage(self) -> DeviceStatus | OphydStatusBase | None:
        """Called while unstaging the device."""

    def on_pre_scan(self) -> DeviceStatus | OphydStatusBase | None:
        """Called right before the scan starts on all devices automatically."""

    def on_trigger(self) -> DeviceStatus | OphydStatusBase | None:
        """Called when the device is triggered."""

    def on_complete(self) -> DeviceStatus | OphydStatusBase | None:
        """Called to inquire if a device has completed a scans."""

    def on_kickoff(self) -> DeviceStatus | OphydStatusBase | None:
        """Called to kickoff a device for a fly scan. Has to be called explicitly."""

    def on_stop(self) -> None:
        """Called when the device is stopped."""

    def on_destroy(self) -> None:
        """Called when the device is destroyed. Cleanup resources here."""
