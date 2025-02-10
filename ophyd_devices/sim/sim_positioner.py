""" Module for simulated positioner devices. """

import threading
import time as ttime
import traceback

import numpy as np
from bec_lib.logger import bec_logger
from ophyd import Component as Cpt
from ophyd import Device, DeviceStatus, Kind, PositionerBase
from ophyd.utils import LimitError
from typeguard import typechecked

from ophyd_devices.sim.sim_data import SimulatedPositioner
from ophyd_devices.sim.sim_signals import ReadOnlySignal, SetableSignal
from ophyd_devices.sim.sim_utils import LinearTrajectory, stop_trajectory
from ophyd_devices.utils.errors import DeviceStopError

logger = bec_logger.logger


class SimPositioner(Device, PositionerBase):
    """
    A simulated device mimicing any 1D Axis device (position, temperature, rotation).

    >>> motor = SimPositioner(name="motor")

    Parameters
    ----------
    name (string)           : Name of the device. This is the only required argmuent, passed on to all signals of the device.\
    Optional parameters:
    ----------
    delay (int)             : If 0, execution of move will be instant. If 1, exectution will depend on motor velocity. Default is 1.
    update_frequency (int)  : Frequency in Hz of the update of the simulated state during a move. Default is 2 Hz.
    precision (integer)     : Precision of the readback in digits, written to .describe(). Default is 3 digits.
    limits (tuple)          : Tuple of the low and high limits of the positioner. Overrides low/high_limit_travel is specified. Default is None.
    parent                  : Parent device, optional, is used internally if this signal/device is part of a larger device.
    kind                    : A member the Kind IntEnum (or equivalent integer), optional. Default is Kind.normal. See Kind for options.
    device_manager          : DeviceManager from BEC, optional . Within startup of simulation, device_manager is passed on automatically.
    sim_init (dict)         : Dictionary to initiate parameters of the simulation, check simulation type defaults for more details.

    """

    # Specify which attributes are accessible via BEC client
    USER_ACCESS = ["sim", "readback", "registered_proxies"]

    sim_cls = SimulatedPositioner

    # Define the signals as class attributes
    readback = Cpt(ReadOnlySignal, name="readback", value=0, kind=Kind.hinted)
    setpoint = Cpt(SetableSignal, value=0, kind=Kind.normal)
    motor_is_moving = Cpt(SetableSignal, value=0, kind=Kind.normal)

    # Config signals
    velocity = Cpt(SetableSignal, value=100, kind=Kind.config)
    acceleration = Cpt(SetableSignal, value=1, kind=Kind.config)
    tolerance = Cpt(SetableSignal, value=0.5, kind=Kind.config)

    # Ommitted signals
    high_limit_travel = Cpt(SetableSignal, value=0, kind=Kind.omitted)
    low_limit_travel = Cpt(SetableSignal, value=0, kind=Kind.omitted)
    unused = Cpt(SetableSignal, value=1, kind=Kind.omitted)

    SUB_READBACK = "readback"
    _default_sub = SUB_READBACK

    # pylint: disable=too-many-arguments
    def __init__(
        self,
        name,
        *,
        delay: int = 1,
        update_frequency=2,
        precision=3,
        limits=None,
        parent=None,
        kind=None,
        device_manager=None,
        sim_init: dict = None,
        **kwargs,
    ):
        self.move_thread = None
        self.delay = delay
        self.device_manager = device_manager
        self.precision = precision
        self.sim_init = sim_init
        self._registered_proxies = {}

        self.update_frequency = update_frequency
        self._stopped = False

        self.sim = self.sim_cls(parent=self, **kwargs)
        self._status_list = []

        super().__init__(name=name, parent=parent, kind=kind, **kwargs)
        self.sim.sim_state[self.name] = self.sim.sim_state.pop(self.readback.name, None)
        self.readback.name = self.name
        if limits is not None:
            assert len(limits) == 2
            self.low_limit_travel.put(limits[0])
            self.high_limit_travel.put(limits[1])
        if self.sim_init:
            self.sim.set_init(self.sim_init)

    @property
    def limits(self):
        """Return the limits of the simulated device."""
        return (self.low_limit_travel.get(), self.high_limit_travel.get())

    @property
    def low_limit(self):
        """Return the low limit of the simulated device."""
        return self.limits[0]

    @property
    def high_limit(self):
        """Return the high limit of the simulated device."""
        return self.limits[1]

    def registered_proxies(self) -> None:
        """Dictionary of registered signal_names and proxies."""
        return self._registered_proxies

    # pylint: disable=arguments-differ
    def check_value(self, value: any):
        """
        Check that requested position is within existing limits.

        This function has to be implemented on the top level of the positioner.
        """
        low_limit, high_limit = self.limits

        if low_limit < high_limit and not low_limit <= value <= high_limit:
            raise LimitError(f"position={value} not within limits {self.limits}")

    @typechecked
    def _set_sim_state(self, signal_name: str, value: any) -> None:
        """Update the simulated state of the device."""
        self.sim.sim_state[signal_name]["value"] = value
        self.sim.sim_state[signal_name]["timestamp"] = ttime.time()

    def _get_sim_state(self, signal_name: str) -> any:
        """Return the simulated state of the device."""
        return self.sim.sim_state[signal_name]["value"]

    def _update_state(self, val):
        """Update the state of the simulated device."""
        old_readback = self._get_sim_state(self.readback.name)
        self._set_sim_state(self.readback.name, val)

        # Run subscription on "readback"
        self._run_subs(
            sub_type=self.SUB_READBACK,
            old_value=old_readback,
            value=self.sim.sim_state[self.readback.name]["value"],
            timestamp=self.sim.sim_state[self.readback.name]["timestamp"],
        )

    def _move_to_setpoint(self) -> None:
        """Move the simulated device to the setpoint."""
        try:
            while True:
                setpoint = self.setpoint.get()
                value = self.readback.get()

                increment = np.sign(setpoint - value) * self.velocity.get() / self.update_frequency
                next_val = value + increment + np.random.uniform(-1, 1) * self.tolerance.get()

                # Check if next_val would overshoot the setpoint
                if (increment > 0 and next_val > setpoint) or (
                    increment < 0 and next_val < setpoint
                ):
                    next_val = setpoint + np.random.uniform(-1, 1) * self.tolerance.get()

                self._update_state(next_val)
                if np.isclose(setpoint, next_val, atol=self.tolerance.get()):
                    break
                if self._stopped:
                    raise DeviceStopError(f"{self.name} was stopped")
                ttime.sleep(1 / self.update_frequency)
            self._update_state(self.readback.get())
            for status in self._status_list:
                status.set_finished()
        # pylint: disable=broad-except
        except Exception as exc:
            content = traceback.format_exc()
            logger.warning(
                f"Error in on_complete call in device {self.name}. Error traceback: {content}"
            )
            for status in self._status_list:
                status.set_exception(exc=exc)
        finally:
            self.motor_is_moving.put(0)
            if not self._stopped:
                self._update_state(self.readback.get())
            self._status_list = []

    def move(self, value: float, **kwargs) -> DeviceStatus:
        """Change the setpoint of the simulated device, and simultaneously initiate a motion."""
        self._stopped = False
        self.check_value(value)
        self.motor_is_moving.put(1)
        self.setpoint.put(value)

        st = DeviceStatus(device=self)
        self._status_list.append(st)
        if self.delay:
            if self.move_thread is None or not self.move_thread.is_alive():
                self.move_thread = threading.Thread(target=self._move_to_setpoint)
                self.move_thread.start()
        else:
            self._done_moving()
            self.motor_is_moving.put(0)
            self._update_state(value)
            st.set_finished()
        return st

    def stop(self, *, success=False):
        """Stop the motion of the simulated device."""
        self._stopped = True
        if self.move_thread:
            self.move_thread.join()
        self.move_thread = None
        super().stop(success=success)

    @property
    def position(self) -> float:
        """Return the current position of the simulated device."""
        return self.readback.get()

    @property
    def egu(self):
        """Return the engineering units of the simulated device."""
        return "mm"


class SimLinearTrajectoryPositioner(SimPositioner):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def _move_and_finish(self, start_pos, end_pos, st):
        acc_time = (
            self.acceleration.get()
        )  # acceleration in Ophyd refers to acceleration time in seconds
        vel = self.velocity.get()
        acc = abs(vel / acc_time)
        traj = LinearTrajectory(start_pos, end_pos, vel, acc)

        try:
            while not traj.ended:
                ttime.sleep(1 / self.update_frequency)
                self._update_state(traj.position())
                if self._stopped:
                    # simulate deceleration
                    traj = stop_trajectory(traj)
                    while not traj.ended:
                        ttime.sleep(1 / self.update_frequency)
                        self._update_state(traj.position())
                    raise DeviceStopError(f"{self.name} was stopped")
            st.set_finished()
        # pylint: disable=broad-except
        except Exception as exc:
            content = traceback.format_exc()
            logger.warning(
                f"Error in on_complete call in device {self.name}. Error traceback: {content}"
            )
            st.set_exception(exc=exc)
        finally:
            self._set_sim_state(self.motor_is_moving.name, 0)

    def move(self, value: float, **kwargs) -> DeviceStatus:
        """Change the setpoint of the simulated device, and simultaneously initiate a motion."""
        self._stopped = False
        self.check_value(value)
        self._set_sim_state(self.motor_is_moving.name, 1)
        self._set_sim_state(self.setpoint.name, value)

        st = DeviceStatus(device=self)
        if self.delay:
            if self.move_thread is None or not self.move_thread.is_alive():
                self.move_thread = threading.Thread(
                    target=self._move_and_finish, args=(self.position, value, st)
                )
                self.move_thread.start()
            else:
                raise RuntimeError(f"{self.name} is already moving. Cannot start a new move.")
        else:
            self._done_moving()
            self._set_sim_state(self.motor_is_moving.name, 0)
            self._update_state(value)
            st.set_finished()
        return st
