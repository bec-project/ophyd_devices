""" Module for Tomcat rotation motors.

The following classes implement the rotation motors for:

- AerotechAutomation1 (Tomcat), based on EpicsMotorIOC.

"""

import threading
import time

import numpy as np
from bec_lib import threadlocked
from ophyd import DeviceStatus

from ophyd_devices.epics.devices.ophyd_base_devices.bec_protocols import (
    BECFlyerProtocol,
    BECScanProtocol,
)
from ophyd_devices.epics.devices.ophyd_base_devices.ophyd_rotation_base import (
    EpicsRotationBase,
)


class TomcatAerotechRotation(EpicsRotationBase, BECFlyerProtocol, BECScanProtocol):
    """Special motor class that provides flyer interface and progress bar."""

    SUB_PROGRESS = "progress"

    def __init__(
        self,
        prefix="",
        *,
        name,
        kind=None,
        read_attrs=None,
        configuration_attrs=None,
        parent=None,
        **kwargs,
    ):
        """Implementation of the Tomcat AerotechAutomation 1 rotation motor class.

        This motor class is based on EpicsRotationBase and provides in addition the flyer interface for BEC
        and a progress update.
        """
        super().__init__(
            prefix=prefix,
            name=name,
            kind=kind,
            read_attrs=read_attrs,
            configuration_attrs=configuration_attrs,
            parent=parent,
            **kwargs,
        )
        self._start_position = None
        self._target_position = None
        self._stopped = False
        self._rlock = threading.RLock()
        self.subscribe(self._progress_update, run=False)

    # ------------------ alternative to using configure method --------------------- #
    @property
    def start_position(self) -> float:
        """Get the start position."""
        return self._start_position

    @start_position.setter
    def start_position(self, value: float) -> None:
        """Set the start position."""
        self._start_position = value

    @property
    def target_position(self) -> float:
        """Get the start position."""
        return self._target_position

    @target_position.setter
    def target_position(self, value: float) -> None:
        """Set the start position."""
        self._target_position = value

    # ------------------ alternative to using configure method --------------------- #

    def configure(self, d: dict) -> dict:
        """Configure method from the device.

        This method is usually used to set configuration parameters for the device.

        Args:
            d (dict): Dictionary with configuration parameters.

        """
        if "target" in d:
            self._target_position = d["target"]
            del d["target"]
        if "position" in d:
            self._target_position = d["position"]
            del d["position"]
        return super().configure(d)

    def pre_scan(self):
        """Perform pre-scan operation, e.g. move to start position."""
        if self._start_position:
            self.move(self._start_position, wait=True)

    def kickoff(self) -> DeviceStatus:
        """Kickoff the scan.

        The kickoff method should return a status object that is set to finish once the flyer flys, and is ready for the next actions.
        I would consider the following implementation.
        """
        self._start_position = float(self.position)
        self.move(self._target_position, wait=False)
        status = DeviceStatus(self)
        status.set_finished()
        return status

    def complete(self) -> DeviceStatus:
        """Complete method of the scan.

        This will be called in a fly scan after the kickoff, thus, the stage will be moving to it's target position.
        It should

        The complete method should return a status object that is set to finish once the flyer is done and the scan is complete.
        I would consider the following implementation.
        """
        threading.Thread(target=self._is_motor_moving, daemon=True).start()
        status = DeviceStatus(self)
        self.subscribe(status.set_finished, event_type=self.SUB_DONE, run=False)
        return status

    def stage(self) -> list[object]:
        """Stage the scan.

        We add here in addition the setting of the _stopped flag to False for the thread.
        """
        self._stopped = False
        return super().stage()

    def stop(self, success: bool = False) -> None:
        """Stop the scan.

        If the device is stopped, the _stopped flag is set to True.
        """
        self._stopped = True
        super().stop(success=success)

    @threadlocked
    def _is_motor_moving(self):
        """Function to check if the motor is moving.

        This function is used in a thread to check if the motor is moving.
        It resolves by running"""
        while self.motor_done_move.get():
            if self._stopped:
                self._done_moving(success=False)
                return
            time.sleep(0.1)
        self._done_moving(success=True)

    def _progress_update(self, value, **kwargs) -> None:
        """Progress update on the scan"""
        if (self._start_position is None) or (self._target_position is None) or (not self.moving):
            self._run_subs(
                sub_type=self.SUB_PROGRESS,
                value=1,
                max_value=1,
                done=1,
            )
            return

        progress = np.abs(
            (value - self._start_position) / (self._target_position - self._start_position)
        )
        max_value = 100
        self._run_subs(
            sub_type=self.SUB_PROGRESS,
            value=int(100 * progress),
            max_value=max_value,
            done=int(np.isclose(max_value, progress, 1e-3)),
        )
