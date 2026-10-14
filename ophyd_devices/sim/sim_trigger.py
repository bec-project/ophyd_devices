"""Simulation gate for BEC queue-control integration tests."""

from __future__ import annotations

import threading

from ophyd import Component as Cpt
from ophyd import Kind, Signal

from ophyd_devices.interfaces.base_classes.psi_device_base import PSIDeviceBase
from ophyd_devices.utils.psi_device_base_utils import DeviceStatus, StatusBase


class SimTriggerWithGate(PSIDeviceBase):
    """Keep a simulated BEC scan active for queue-control integration tests.

    The gate gives tests a predictable point at which to exercise pause, abort,
    restart, and cleanup without relying on hardware timing. Triggers normally
    finish immediately. After ``arm()``, the first two triggers finish and the
    third stays pending until ``release()`` lets the scan continue or a lifecycle
    operation interrupts it.

    ``value`` counts triggers, restarting at 1 after arming; ``waiting`` is True
    while the third trigger is pending. Tests can call ``arm()`` and ``release()``
    through BEC's device RPC interface.
    """

    USER_ACCESS = ["arm", "release"]
    value = Cpt(Signal, value=0, kind=Kind.normal)
    waiting = Cpt(Signal, value=False, kind=Kind.omitted)
    _armed_count: int | None
    _readback_value: int
    _held: StatusBase | None
    _claimed: bool
    _closing: bool

    def arm(self) -> None:
        """Hold the third upcoming trigger until released or stopped."""
        with self._gate_lock:
            self._check_idle()
            self._armed_count = 0

    def release(self) -> None:
        """Release the held trigger and leave subsequent triggers unblocked."""
        self._resolve(success=True)

    def stop(self, *, success: bool = False) -> None:
        """Preserve successful stops while running the base lifecycle cleanup."""
        if success:
            self._resolve(success=True)
        super().stop(success=success)

    ########################################
    #  Beamline Specific Implementations   #
    ########################################

    def on_init(self) -> None:
        """
        Called when the device is initialized.

        No signals are connected at this point. If you like to
        set default values on signals, please use on_connected instead.
        """
        self._gate_lock = threading.Lock()
        self._armed_count = None
        self._readback_value = 0
        self._held = None
        self._claimed = False
        self._closing = False

    def on_connected(self) -> None:
        """
        Called after the device is connected and its signals are connected.
        Default values for signals should be set here.
        """

    def on_stage(self) -> DeviceStatus | StatusBase | None:
        """
        Called while staging the device.

        Information about the upcoming scan can be accessed from the scan_info
        (self.scan_info.msg) object.
        """

    def on_unstage(self) -> DeviceStatus | StatusBase | None:
        """Called while unstaging the device."""
        self._resolve(success=False)

    def on_pre_scan(self) -> DeviceStatus | StatusBase | None:
        """Called right before the scan starts on all devices automatically."""

    def on_trigger(self) -> DeviceStatus | StatusBase | None:
        """Called when the device is triggered."""
        with self._gate_lock:
            self._check_idle()
            status = StatusBase(self, description=f"{self.name} trigger gate")
            if self._armed_count is None:
                self._readback_value += 1
            else:
                self._armed_count += 1
                self._readback_value = self._armed_count
            held = self._armed_count == 3
            if held:
                self._held = status
                self._claimed = False
                self.cancel_on_stop(status)
        if held:
            status.add_callback(self._trigger_finished)
        self._publish_value()
        if not held:
            status.set_finished()
        self._publish_waiting()
        return status

    def on_complete(self) -> DeviceStatus | StatusBase | None:
        """Called to inquire if a device has completed a scans."""
        with self._gate_lock:
            status = self._held
        if status is None:
            return None
        # The composite gives BEC a separate status for each completion instruction.
        ready = StatusBase(self)
        ready.set_finished()
        return status & ready

    def on_kickoff(self) -> DeviceStatus | StatusBase | None:
        """Called to kickoff a device for a fly scan. Has to be called explicitly."""

    def on_stop(self) -> None:
        """Called when the device is stopped."""
        self._resolve(success=False)

    def on_destroy(self) -> None:
        """Called when the device is destroyed. Cleanup resources here."""
        with self._gate_lock:
            self._closing = True
        self._resolve(success=False)

    ########################################
    #            Helper Methods            #
    ########################################

    def _check_idle(self) -> None:
        if self._closing or self.destroyed:
            raise RuntimeError("Trigger gate destroyed")
        if self._held is not None and not self._held.done:
            raise RuntimeError("A trigger is already held")

    def _resolve(self, success: bool) -> None:
        with self._gate_lock:
            self._armed_count = None
            status = self._held
            if status is None or status.done or self._claimed:
                return
            self._claimed = True
            # A concurrent base stop must not cancel an outcome already claimed here.
            self._stoppable_status_objects.remove(status)
        if success:
            status.set_finished()
        else:
            status.set_exception(RuntimeError("Trigger gate stopped"))

    def _trigger_finished(self, status: StatusBase) -> None:
        with self._gate_lock:
            if self._held is status:
                self._held = None
                self._claimed = False
        self._publish_waiting()

    def _publish_value(self) -> None:
        # Subscribers can trigger again; publish the latest counter after callbacks return.
        while True:
            with self._gate_lock:
                if self._closing:
                    return
                value = self._readback_value
            if self.value.get() != value:
                self.value.put(value)
            with self._gate_lock:
                if value == self._readback_value:
                    return

    def _publish_waiting(self) -> None:
        # Release can race a waiting update. Recheck state without holding locks in callbacks.
        while True:
            with self._gate_lock:
                if self._closing:
                    return
                waiting = self._held is not None and not self._held.done
            if self.waiting.get() != waiting:
                self.waiting.put(waiting)
            with self._gate_lock:
                current = self._held is not None and not self._held.done
                if current == waiting:
                    return
