"""
Module for virtual slits. The device receives two positioners as input, and allows to control the
width and center. The positioners are expected to be orthogonal, and the width is defined as the
distance between the two positioners. Both positioners are expected to share the same xy, xz or
yz plane, and the center is defined as the midpoint between the two positioners. The assumption
is that the first positioner is the one with the smaller position value, and the second one
with the larger one.

Please adjust the input parameters accordingly. Additionally, an optional sign_flip is available
for both positioners, which allows to flip the sign of the position value. This can be useful if
the positioners coordinates are flipped in the control system below.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from threading import RLock
from typing import TYPE_CHECKING, Tuple

from ophyd import Component as Cpt
from ophyd import Device, Kind, PositionerBase, Signal
from ophyd.status import wait as status_wait
from ophyd.utils.errors import ReadOnlyError, UnknownStatusFailure

from ophyd_devices import PSIDeviceBase, StatusBase

if TYPE_CHECKING:  # pragma: no cover
    from bec_lib.devicemanager import DeviceManagerBase


class _VirtualSlitSignal(ABC, Signal):
    """Computed width signal for a virtual slit positioner."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._positioner_low = None
        self._sign_flip_low = False
        self._positioner_high = None
        self._sign_flip_high = False
        self._rlock = RLock()
        self._metadata["connected"] = False

    def set_positioner_low(self, positioner: Device, sign_flip=False):
        """
        Set the low positioner for the width calculation. The positioner must adhere to the
        conventions of a positoner in ophyd. This means that the 'set' method will initialized
        a motion and the 'read' method will return a dictionary, with the positioner.name as key
        to the readback positioner of the positioner.

        Args:
            positioner (Device): The positioner to use as the low positioner for width calculation.
        """
        self._positioner_low = positioner
        self._sign_flip_low = sign_flip

    def set_positioner_high(self, positioner: Device, sign_flip=False):
        """
        Set the high positioner for the width calculation. The positioner must adhere to the
        conventions of a positoner in ophyd. This means that the 'set' method will initialized
        a motion and the 'read' method will return a dictionary, with the positioner.name as key
        to the readback positioner of the positioner.

        Args:
            positioner (Device): The positioner to use as the high positioner for width calculation.
        """
        self._positioner_high = positioner
        self._sign_flip_high = sign_flip

    def wait_for_connection(self, timeout=0):
        if self._positioner_low is None or self._positioner_high is None:
            raise ConnectionError(
                f"Positioners must be set for device {self.root.name} to setup WidthSignal."
            )
        connected_low = self._positioner_low.connected
        connected_high = self._positioner_high.connected
        if connected_low and connected_high:
            self._metadata["connected"] = True
            return
        raise ConnectionError(
            f"Both positioners must be connected. Positioner {self._positioner_low.name} connected: {connected_low}"
            f", Positioner {self._positioner_high.name} connected: {connected_high}."
        )

    @abstractmethod
    def get(self):
        """Get the current width by calculating the difference between the two positioners."""

    @abstractmethod
    def put(self, value, *, timestamp=None, force=False):
        """
        Set the width by calculating the new positions for both positioners
        based on the current center and the desired width.
        """

    def read(self):
        """Read the current width by calculating the difference between the two positioners."""
        if not self.connected:
            raise ConnectionError(
                f"Device {self.root.name} is not connected, can't read from signal {self.name}."
            )
        return super().read()

    def get_positions_low_high(self) -> Tuple[float, float]:
        """
        Get the current positions (readback with device.name) of the low and high positioners.

        Returns:
            Tuple[float, float]: The current positions of the low and high positioners. Including
                                 the sign flip if it is set.
        """
        pos_low = self._positioner_low.read()[self._positioner_low.name]["value"]
        pos_high = self._positioner_high.read()[self._positioner_high.name]["value"]
        if self._sign_flip_low:
            pos_low = -pos_low
        if self._sign_flip_high:
            pos_high = -pos_high
        return pos_low, pos_high


class SlitWidthReadback(_VirtualSlitSignal):
    """Computed width signal for a virtual slit positioner."""

    def get(self):
        old_value = self._readback
        pos_low, pos_high = self.get_positions_low_high()
        self._readback = pos_high - pos_low
        self._run_subs(sub_type=self.SUB_VALUE, old_value=old_value, value=self._readback)
        return self._readback

    def put(self, value, *, timestamp=None, force=False):
        raise ReadOnlyError(
            f"WidthReadback {self.name} is read-only, use the slit width to set the width."
        )


class SlitWidthSetpoint(_VirtualSlitSignal):
    """Computed width signal for a virtual slit positioner."""

    def get(self):
        old_value = self._readback
        pos_low, pos_high = self.get_positions_low_high()
        self._readback = pos_high - pos_low
        self._run_subs(sub_type=self.SUB_VALUE, old_value=old_value, value=self._readback)
        return self._readback

    def check_value(self, value):
        """
        Check if the value is valid for the width. The width must be non-negative.

        Args:
            value (float): The value to check for validity as a width.
        """
        if value < 0:
            raise ValueError(
                f"Width must be non-negative, got {value} for device {self.root.name}."
            )

    def put(self, value, *, timestamp=None, force=False):
        self.check_value(value)
        pos_low, pos_high = self.get_positions_low_high()
        center = (pos_high + pos_low) / 2
        new_pos_low = center - value / 2
        new_pos_high = center + value / 2
        self._positioner_low.set(new_pos_low)
        self._positioner_high.set(new_pos_high)

    def set(self, value, timestamp=None, force=False):
        """Alias for put to adhere to the set interface of a signal."""
        self.check_value(value)
        status = StatusBase(obj=self)

        def _status_callback(success, exception=None, **kwargs):
            with self._rlock:
                if status.done:
                    return
                if success:
                    status.set_finished()
                else:
                    if exception is None:
                        exception = UnknownStatusFailure(f"{self.name} failed to move to {value}")
                    status.set_exception(exception)

        pos_low, pos_high = self.get_positions_low_high()
        center = (pos_high + pos_low) / 2
        new_pos_low = center - value / 2
        new_pos_high = center + value / 2
        self._positioner_low.set(new_pos_low)
        self._positioner_high.set(new_pos_high)
        self._positioner_low.subscribe(
            _status_callback, event_type=self._positioner_low._SUB_REQ_DONE, run=False
        )
        self._positioner_high.subscribe(
            _status_callback, event_type=self._positioner_high._SUB_REQ_DONE, run=False
        )
        return status


class SlitCenterReadback(_VirtualSlitSignal):
    """Computed center signal for a virtual slit positioner."""

    def get(self):
        old_value = self._readback
        pos_low, pos_high = self.get_positions_low_high()
        self._readback = (pos_high + pos_low) / 2
        self._run_subs(sub_type=self.SUB_VALUE, old_value=old_value, value=self._readback)
        return self._readback

    def put(self, value, *, timestamp=None, force=False):
        raise ReadOnlyError(
            f"CenterReadback {self.name} is read-only, use the slit width to set the center."
        )


class SlitCenterSetpoint(_VirtualSlitSignal):
    """Computed center signal for a virtual slit positioner."""

    def get(self):
        old_value = self._readback
        pos_low, pos_high = self.get_positions_low_high()
        self._readback = (pos_high + pos_low) / 2
        self._run_subs(sub_type=self.SUB_VALUE, old_value=old_value, value=self._readback)
        return self._readback

    def put(self, value, *, timestamp=None, force=False):
        pos_low, pos_high = self.get_positions_low_high()
        width = pos_high - pos_low
        new_pos_low = value - width / 2
        new_pos_high = value + width / 2
        self._positioner_low.set(new_pos_low)
        self._positioner_high.set(new_pos_high)

    def set(self, value, timestamp=None, force=False):
        """Alias for put to adhere to the set interface of a signal."""
        status = StatusBase(obj=self)

        def _status_callback(success, exception=None, **kwargs):
            if status.done:
                return
            if success:
                status.set_finished()
            else:
                if exception is None:
                    exception = UnknownStatusFailure(f"{self.name} failed to move to {value}")
                status.set_exception(exception)

        pos_low, pos_high = self.get_positions_low_high()
        width = pos_high - pos_low
        new_pos_low = value - width / 2
        new_pos_high = value + width / 2
        self._positioner_low.set(new_pos_low)
        self._positioner_high.set(new_pos_high)
        self._positioner_low.subscribe(
            _status_callback, event_type=self._positioner_low._SUB_REQ_DONE, run=False
        )
        self._positioner_high.subscribe(
            _status_callback, event_type=self._positioner_high._SUB_REQ_DONE, run=False
        )
        return status


class _VirtualSlitPositioner(ABC, PSIDeviceBase, PositionerBase):

    user_readback: _VirtualSlitSignal
    user_setpoint: _VirtualSlitSignal

    motor_is_moving = Cpt(Signal, value=0, kind=Kind.omitted)

    def __init__(
        self,
        name: str,
        positioner_low_name: str,
        positioner_high_name: str,
        device_manager: DeviceManagerBase,
        sign_flip_low=False,
        sign_flip_high=False,
    ):
        super().__init__(name=name, device_manager=device_manager)
        self.positioner_low_name = positioner_low_name
        self.positioner_high_name = positioner_high_name
        self.sign_flip_low = sign_flip_low
        self.sign_flip_high = sign_flip_high
        self._positioner_low = None
        self._positioner_high = None
        self.user_readback.name = self.name

    def _get_positioners(self) -> Tuple[Device, Device]:
        positioner_low = self.device_manager.devices.get(self.positioner_low_name)
        positioner_high = self.device_manager.devices.get(self.positioner_high_name)
        if positioner_low is None:
            raise ConnectionError(
                f"Low positioner {self.positioner_low_name} not found in device manager for device {self.name}."
            )
        if positioner_high is None:
            raise ConnectionError(
                f"High positioner {self.positioner_high_name} not found in device manager for device {self.name}."
            )
        return positioner_low, positioner_high

    def wait_for_connection(self, **kwargs):
        self._positioner_low, self._positioner_high = self._get_positioners()
        if not self._positioner_low.connected or not self._positioner_high.connected:
            raise ConnectionError(
                f"Both Positioners must be connected for device {self.name}."
                f"Device {self._positioner_low.name} : connected {self._positioner_low.connected},"
                f"device {self._positioner_high.name} : connected {self._positioner_high.connected}."
            )
        if self.user_readback is None or self.user_setpoint is None:
            raise ConnectionError(
                f"User readback and setpoint must be defined for device {self.name} and class {self.__class__.__name__}."
            )
        for sig in [self.user_readback, self.user_setpoint]:
            sig.set_positioner_low(self._positioner_low, sign_flip=self.sign_flip_low)
            sig.set_positioner_high(self._positioner_high, sign_flip=self.sign_flip_high)
            sig.wait_for_connection()

        self._setup_subscriptions()

    def _setup_subscriptions(self):
        self._positioner_low.subscribe(
            self._readback_callback, event_type=self._positioner_low.SUB_READBACK
        )
        self._positioner_high.subscribe(
            self._readback_callback, event_type=self._positioner_high.SUB_READBACK
        )

    def _readback_callback(self, **kwargs):
        """Callback to update readbacks."""
        self.user_readback.read()

    def move(self, position, wait=False, timeout=None, **kwargs) -> StatusBase:
        """Move to the given position by setting the user_setpoint."""

        self.motor_is_moving.put(1)

        def _move_finished_callback(status, exception=None, **kwargs):
            if status.done:
                self.motor_is_moving.put(0)

        status = self.user_setpoint.set(position)
        status.add_callback(_move_finished_callback)
        try:
            if wait:
                status_wait(status)
        except KeyboardInterrupt:
            self.stop()
            raise
        return status

    def stop(self, **kwargs):
        """Stop the motion by stopping both positioners."""
        if self._positioner_low is not None:
            self._positioner_low.stop()
        if self._positioner_high is not None:
            self._positioner_high.stop()


class SlitCenter(_VirtualSlitPositioner):
    """
    Virtual slit positioner for controlling the center of the slit.

    Args:
        positioner_low_name (str): Name of the low positioner as specified in BEC's device config
        positioner_high_name (str): Name of the high positioner as specified in BEC's device config
        sign_flip_low Optional(bool): Indicate if the positions of low positioner should be flipped. Default is False.
        sign_flip_high Optional(bool): Indicate if the positions of high positioner should be flipped. Default is False.
    """

    user_readback = Cpt(SlitCenterReadback, kind=Kind.normal)
    user_setpoint = Cpt(SlitCenterSetpoint, kind=Kind.normal)


class SlitWidth(_VirtualSlitPositioner):
    """
    Virtual slit positioner for controlling the width of the slit.

    Args:
        positioner_low_name (str): Name of the low positioner as specified in BEC's device config
        positioner_high_name (str): Name of the high positioner as specified in BEC's device config
        sign_flip_low Optional(bool): Indicate if the positions of low positioner should be flipped. Default is False.
        sign_flip_high Optional(bool): Indicate if the positions of high positioner should be flipped. Default is False.
    """

    user_readback = Cpt(SlitWidthReadback, kind=Kind.normal)
    user_setpoint = Cpt(SlitWidthSetpoint, kind=Kind.normal)
