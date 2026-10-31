"""
Base class for all PSI ophyd device integration to ensure consistent configuration
"""

from __future__ import annotations

import inspect
import time
from collections.abc import Callable
from contextvars import ContextVar
from threading import Lock
from typing import TYPE_CHECKING

from ophyd import Device, DeviceStatus, Staged, StatusBase
from ophyd.utils.errors import InvalidState

from ophyd_devices.tests.utils import get_mock_scan_info
from ophyd_devices.utils.psi_device_base_utils import (
    DeviceCleanupBlockedError,
    FileHandler,
    TaskHandler,
    destroy_subdevices,
)

if TYPE_CHECKING:  # pragma: no cover
    from bec_lib.devicemanager import DeviceManagerBase, ScanInfo


class DeviceStoppedError(Exception):
    """Exception raised when a device is stopped"""


class PSIDeviceBase(Device):
    """
    Base class for all PSI ophyd devices to ensure consistent configuration
    and communication with BEC services.

    Callers must serialize stage(), unstage() and destroy(). Overlapping these
    transitions is unsupported; stop() may still cancel acquisition in progress.
    """

    # These are all possible subscription types that the device_manager supports
    # and automatically subscribes to
    SUB_READBACK = "readback"
    SUB_VALUE = "value"
    SUB_DONE_MOVING = "done_moving"
    SUB_MOTOR_IS_MOVING = "motor_is_moving"
    _default_sub = SUB_VALUE

    def __init__(
        self,
        prefix: str = "",
        *,
        name: str,
        scan_info: ScanInfo | None = None,
        device_manager: DeviceManagerBase | None = None,
        **kwargs,
    ):
        """
        Initialize the PSI Device Base class.

        Args:
            name (str) : Name of the device
            scan_info (ScanInfo): The scan info to use.
        """
        # Make sure device_manager is not passed to super().__init__ if not specified
        # This is to avoid issues with ophyd.OphydObject.__init__ when the parent is ophyd.Device
        # and the device_manager is passed to it. This will cause a TypeError.
        parent = kwargs.get("parent")
        ancestor = parent
        while ancestor is not None and (device_manager is None or scan_info is None):
            if device_manager is None:
                device_manager = getattr(ancestor, "device_manager", None)
            if scan_info is None:
                scan_info = getattr(ancestor, "scan_info", None)
            ancestor = getattr(ancestor, "parent", None)
        self.device_manager = device_manager
        if scan_info is not None:
            self.scan_info = scan_info
        sig = inspect.signature(super().__init__)
        if "device_manager" in sig.parameters:
            super().__init__(device_manager=device_manager, prefix=prefix, name=name, **kwargs)
        else:
            super().__init__(prefix=prefix, name=name, **kwargs)
        self._stopped = False
        self._lifecycle_lock = Lock()
        self._destroying = False
        self._destroy_in_progress = False
        self._device_stop_requests = 0
        self._lifecycle_token = object()
        self._lifecycle_context: ContextVar[object | None] = ContextVar(
            "device_lifecycle_owner", default=None
        )
        self._stoppable_status_objects: list[StatusBase] = []
        self._stoppable_status_lock = Lock()
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
        if value:
            self._lifecycle_token = object()
        self._stopped = value

    ########################################
    # Wrapper around Device class methods  #
    ########################################

    def stage(self) -> list[object] | DeviceStatus | StatusBase:  # type: ignore
        """
        Stage the device while retaining ownership through native setup and its hook.
        """
        with self._lifecycle_lock:
            if self._destroying or self.destroyed:
                raise DeviceStoppedError(f"Device {self.name} destruction has begun")
            if self._device_stop_requests:
                raise DeviceStoppedError(f"Device {self.name} stop is still in progress")
            already_staged = self.staged != Staged.no
            if not already_staged:
                self._lifecycle_token = object()
                self.stopped = False
            owner = self._lifecycle_token
        if already_staged:
            return super().stage()
        context = self._lifecycle_context.set(owner)
        try:
            super_staged = super().stage()
            if owner is not self._lifecycle_token:
                raise DeviceStoppedError(f"Device {self.name} staging was superseded")
            status = self.on_stage()  # pylint: disable=assignment-from-no-return
            if isinstance(status, StatusBase):
                return status
            return super_staged
        finally:
            self._lifecycle_context.reset(context)

    def unstage(self) -> list[object] | DeviceStatus | StatusBase:  # type: ignore
        """
        Unstage and cancel only work owned when this transition started.
        """
        owner = self._lifecycle_token = object()
        context = self._lifecycle_context.set(owner)
        retiring: tuple[StatusBase, ...] = ()
        try:
            with self._stoppable_status_lock:
                retiring = tuple(self._stoppable_status_objects)
            super_unstage = super().unstage()
            if owner is not self._lifecycle_token:
                raise DeviceStoppedError(f"Device {self.name} unstaging was superseded")
            status = self.on_unstage()  # pylint: disable=assignment-from-no-return
            if isinstance(status, StatusBase):
                return status
            return super_unstage
        finally:
            try:
                self._stop_stoppable_status_objects(statuses=retiring)
            finally:
                self._lifecycle_context.reset(context)

    def pre_scan(self) -> DeviceStatus | StatusBase | None:
        """Pre-scan function."""
        status = self.on_pre_scan()  # pylint: disable=assignment-from-no-return
        return status

    def trigger(self) -> StatusBase:  # pyright: ignore[reportIncompatibleMethodOverride]
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
        """Stop hardware and cancel pending work even if a shutdown hook fails.

        Preserve hook ordering and propagate the first error after status cancellation
        and native child shutdown have both been attempted.

        Args:
            success (bool): True if the action was successful, False otherwise.
        """
        with self._lifecycle_lock:
            self._device_stop_requests += 1
            self._lifecycle_token = object()
        try:
            errors = []
            try:
                self.on_stop()
            except Exception as error:  # noqa: BLE001 - cancellation must survive hook failure.
                errors.append(error)
            finally:
                self.stopped = True
            native_stop = super().stop
            for cleanup in (
                self._stop_stoppable_status_objects,
                lambda: native_stop(success=success),
            ):
                try:
                    cleanup()
                except Exception as error:  # noqa: BLE001 - attempt all shutdown work.
                    errors.append(error)
            if errors:
                for error in errors[1:]:
                    errors[0].add_note(f"Additional device stop failure: {error!r}")
                raise errors[0]

        finally:
            with self._lifecycle_lock:
                self._device_stop_requests -= 1

    def destroy(self):
        """
        Retire setup ownership before releasing root and child resources.

        Destruction permanently prevents new setup, even when cleanup fails.
        Overlapping or reentrant destroy calls do nothing while cleanup runs. If
        native destruction fails before marking the device destroyed, a later call
        may retry cleanup without permitting acquisition to restart in between.
        Callers must wait for stage()/unstage() to finish before destruction.
        Workers and statuses that still own resources block cleanup until their
        shutdown finishes. Retry after asynchronous cancellation cleanup completes.
        """
        with self._lifecycle_lock:
            if self.destroyed or self._destroy_in_progress:
                return
            self._destroying = self._destroy_in_progress = True
            self._lifecycle_token = object()
        try:
            errors = []
            for cleanup in (
                self.on_destroy,
                self._stop_stoppable_status_objects,
                self.task_handler.shutdown,
                self._check_status_cleanup,
                lambda: destroy_subdevices(self),
                super().destroy,
            ):
                try:
                    cleanup()
                except DeviceCleanupBlockedError as error:
                    for prior in errors:
                        error.add_note(f"Additional device cleanup failure: {prior!r}")
                    raise  # Preserve signals while owned cleanup can still use them.
                except Exception as error:  # noqa: BLE001 - always finish resource cleanup.
                    errors.append(error)
            if errors:
                for error in errors[1:]:
                    errors[0].add_note(f"Additional device cleanup failure: {error!r}")
                raise errors[0]
        finally:
            with self._lifecycle_lock:
                self._destroy_in_progress = False

    ########################################
    # Stoppable Status Objects Management   #
    ########################################

    def cancel_on_stop(self, status: StatusBase) -> None:
        """
        Register unfinished work for cancellation when the device is stopped.

        Completed statuses are removed automatically, including statuses that finish
        during registration. Completion and stop may run on different threads; the
        registry lock protects bookkeeping without holding a lock during cancellation
        or callback invocation. Registering the same pending status twice is harmless.
        Work registered while stopping, after stop or during destruction is cancelled
        immediately. Pending cancellation cleanup remains owned until it finishes.

        Args:
            status (StatusBase): The status object to be cancelled.
        """
        if not isinstance(status, StatusBase):
            raise TypeError("status must be an instance of StatusBase")
        with self._lifecycle_lock, self._stoppable_status_lock:
            if status.done or status in self._stoppable_status_objects:
                return
            self._stoppable_status_objects.append(status)
            cancel = (
                self.stopped or self._device_stop_requests or self._destroying or self.destroyed
            )

        def discard(completed: StatusBase) -> None:
            with self._stoppable_status_lock:
                try:
                    self._stoppable_status_objects.remove(completed)
                except ValueError:
                    pass  # Explicit registry cleanup has already removed this status.

        # add_callback also invokes discard if completion raced with registration.
        status.add_callback(discard)
        if cancel:
            self._stop_stoppable_status_objects(statuses=(status,))

    def _clear_stoppable_status_objects(self) -> None:
        """
        Clear all registered stoppable status objects.

        This is useful to reset the list of status objects that should be cancelled
        when the device is stopped.
        """
        with self._stoppable_status_lock:
            self._stoppable_status_objects = []

    def _stop_stoppable_status_objects(
        self, *, statuses: tuple[StatusBase, ...] | None = None
    ) -> None:
        """
        Stop all registered stoppable status objects.

        Cancel the current registry or an explicit snapshot without retaining the
        bookkeeping lock while callbacks run. Pending statuses stay registered until
        their completion callbacks release ownership, including asynchronous failure
        cleanup. An unstage snapshot cannot cancel statuses registered by a replacement
        scan after its hook has completed.

        Args:
            statuses (tuple[StatusBase, ...] | None): Retiring work to cancel. None
                cancels every currently registered status.
        """
        with self._stoppable_status_lock:
            if statuses is None:
                statuses = tuple(self._stoppable_status_objects)
        for status in statuses:
            if not status.done:
                try:
                    status.set_exception(DeviceStoppedError(f"Device {self.name} has been stopped"))
                except InvalidState:
                    pass  # A completion callback already committed this status.

    def _check_status_cleanup(self) -> None:
        """
        Preserve device resources while cancelled statuses finish owned cleanup.

        Cancellation can return before a sequence's asynchronous failure cleanup
        finishes. Keep its signals connected and let the caller retry destruction
        once that cleanup commits completion. Native statuses can commit cancellation
        before their callback thread marks them done; that dispatch delay does not
        own additional cleanup and must not block destruction.

        Raises:
            DeviceCleanupBlockedError: Registered work has not finished cancellation.
        """
        with self._stoppable_status_lock:
            pending = sum(
                not status.done
                and not status._externally_initiated_completion  # pylint: disable=protected-access
                for status in self._stoppable_status_objects
            )
        if pending:
            raise DeviceCleanupBlockedError(
                f"Device {self.name} is waiting for cancellation cleanup of {pending} status(es); "
                "retry destruction after cleanup finishes"
            )

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

    def on_destroy(self) -> None:
        """Called when the device is destroyed. Cleanup resources here."""
