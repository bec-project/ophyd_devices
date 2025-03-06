"""
Base class for all PSI ophyd device integration to ensure consistent configuration
"""

from __future__ import annotations

from bec_lib.devicemanager import ScanInfo
from ophyd import Device, DeviceStatus, Staged, StatusBase

from ophyd_devices.tests.utils import get_mock_scan_info
from ophyd_devices.utils.psi_device_base_utils import FileHandler, TaskHandler


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

    def __init__(self, name: str, scan_info: ScanInfo | None = None, **kwargs):  # type: ignore
        """
        Initialize the PSI Device Base class.

        Args:
            name (str) : Name of the device
            scan_info (ScanInfo): The scan info to use.
        """
        super().__init__(name=name, **kwargs)
        self._stopped = False
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

    ########################################
    # Wrapper around Device class methods  #
    ########################################

    def stage(self) -> list[object] | DeviceStatus | StatusBase:  # type: ignore
        """Stage the device."""
        if self.staged != Staged.no:
            return super().stage()
        self.stopped = False
        super_staged = super().stage()
        status = self.on_stage()  # pylint: disable=assignment-from-no-return
        if isinstance(status, DeviceStatus):
            return status
        return super_staged

    def unstage(self) -> list[object] | DeviceStatus | StatusBase:  # type: ignore
        """Unstage the device."""
        super_unstage = super().unstage()
        status = self.on_unstage()  # pylint: disable=assignment-from-no-return
        if isinstance(status, DeviceStatus):
            return status
        return super_unstage

    def pre_scan(self) -> DeviceStatus | StatusBase | None:
        """Pre-scan function."""
        status = self.on_pre_scan()  # pylint: disable=assignment-from-no-return
        return status

    def trigger(self) -> DeviceStatus | StatusBase:
        """Trigger the device."""
        super_trigger = super().trigger()
        status = self.on_trigger()  # pylint: disable=assignment-from-no-return
        return status if status else super_trigger

    def complete(self) -> DeviceStatus | StatusBase:
        """Complete the device."""
        status = self.on_complete()  # pylint: disable=assignment-from-no-return
        if isinstance(status, StatusBase):
            return status
        status = DeviceStatus(self)
        status.set_finished()
        return status

    def kickoff(self) -> DeviceStatus | StatusBase:
        """Kickoff the device."""
        status = self.on_kickoff()  # pylint: disable=assignment-from-no-return
        if isinstance(status, StatusBase):
            return status
        status = DeviceStatus(self)
        status.set_finished()
        return status

    def stop(self, *, success: bool = False) -> None:
        """Stop the device.

        Args:
            success (bool): True if the action was successful, False otherwise.
        """
        self.on_stop()
        super().stop(success=success)
        self.stopped = True

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

    def on_stage(self) -> DeviceStatus | StatusBase | None:
        """
        Called while staging the device.

        Information about the upcoming scan can be accessed from the scan_info (self.scan_info.msg) object.
        """

    def on_unstage(self) -> DeviceStatus | StatusBase | None:
        """Called while unstaging the device."""

    def on_pre_scan(self) -> DeviceStatus | StatusBase | None:
        """Called right before the scan starts on all devices automatically."""

    def on_trigger(self) -> DeviceStatus | StatusBase | None:
        """Called when the device is triggered."""

    def on_complete(self) -> DeviceStatus | StatusBase | None:
        """Called to inquire if a device has completed a scans."""

    def on_kickoff(self) -> DeviceStatus | StatusBase | None:
        """Called to kickoff a device for a fly scan. Has to be called explicitly."""

    def on_stop(self) -> None:
        """Called when the device is stopped."""
