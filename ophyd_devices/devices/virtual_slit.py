"""Pseudo-motor implementations for slit center and slit width.

Both devices map one pseudo axis onto two real motors (left and right slit
edges). They can be instantiated from names resolved through the BEC device
manager and support an optional offset term in their coordinate transforms.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from bec_lib.logger import bec_logger
from ophyd import Component as Cpt
from ophyd import Kind
from ophyd.signal import SignalRO

from ophyd_devices.interfaces.base_classes.psi_pseudo_motor_base import PSIPseudoMotorBase

if TYPE_CHECKING:  # pragma: no cover
    from bec_lib.devicemanager import DeviceManagerBase
    from ophyd import PositionerBase, Signal


logger = bec_logger.logger


class VirtualSlitCenter(PSIPseudoMotorBase):
    """Pseudo motor controlling slit center from two edge motors.

    Both positioners must be present in the device manager, and the pseudo
    motor entry in the current session config must declare them in ``needs``.

    The forward calculation computes the center position based on the positions of the left and right positioners,
    while the inverse calculation computes the setpoints for the left and right positioners based on a desired center
    position. The motors_are_moving method checks if either of the positioners is currently moving.

    Args:
        name (str): The name of the pseudo motor device.
        left_slit (str): The name of the left slit positioner device in the device manager.
        right_slit (str): The name of the right slit positioner device in the device manager.
        device_manager (DeviceManagerBase): The device manager instance to fetch the positioner devices from.
        offset (float, optional): Constant center offset added in forward
            calculation and removed in inverse calculation.
        egu (str | None, optional): Engineering units. If omitted, units are
            taken from the left positioner.
    """

    offset = Cpt(
        SignalRO,
        name="offset",
        kind=Kind.config,
        doc="Offset applied to the position of the slit center when calculating the width.",
    )

    def __init__(
        self,
        name: str,
        left_slit: str,
        right_slit: str,
        device_manager: DeviceManagerBase,
        offset: float = 0,
        egu: str | None = None,
        **kwargs,
    ):
        positioners = self.get_positioner_objects(
            name=name,
            positioners={"left": left_slit, "right": right_slit},
            device_manager=device_manager,
        )
        if egu is None:  # if not specified, fetch it from the left positioner
            egu = positioners["left"].egu
            if positioners["right"].egu != egu:
                logger.warning(
                    f"Device {name} found inconsistency for egu for positioner left {left_slit} and right {right_slit}. Using egu {egu}."
                )
        self._offset = offset
        super().__init__(
            name=name, device_manager=device_manager, positioners=positioners, egu=egu, **kwargs
        )

    def wait_for_connection(self, *args, **kwargs):
        """Connect and initialize the read-only ``offset`` configuration signal."""
        super().wait_for_connection(*args, **kwargs)
        # Set the initial value of the offset signal
        # Config values are read by back after wait_for_connection is called.
        self.offset._readback = self._offset

    def _get_pos_motor(self, motor: PositionerBase) -> float:
        """Return the current position read from ``motor``.

        Args:
            motor (PositionerBase): The positioner motor to read the position from.
        Returns:
            float: Current motor position.
        """
        return motor.read()[motor.name]["value"]

    # pylint: disable=arguments-differ
    def forward_calculation(self, left: Signal, right: Signal) -> float:
        """Compute slit center from left and right positions.

        Args:
            left (Signal): The signal representing the position of the left slit positioner.
            right (Signal): The signal representing the position of the right slit positioner.

        Returns:
            float: Center position ``(left + right) / 2 + offset``.
        """
        left_pos = left.get()
        right_pos = right.get()
        center = (left_pos + right_pos) / 2 + self._offset
        return float(center)

    def inverse_calculation(self, position: float, left: Signal, right: Signal) -> dict[str, float]:
        """Compute left/right setpoints for a target center.

        The current slit width is preserved.

        Args:
            position (float): The desired center position of the slit.
            left (Signal): The signal representing the position of the left slit positioner.
            right (Signal): The signal representing the position of the right slit positioner.
        Returns:
            A dictionary with the new setpoints for the left and right positioners, with keys "left" and "right".
        """
        position_with_offset = position - self._offset
        # To access position, run read on the root (PositionerBase) of the signal
        left_pos = left.get()
        right_pos = right.get()
        width = right_pos - left_pos
        new_left_pos = position_with_offset - width / 2
        new_right_pos = position_with_offset + width / 2
        return {"left": new_left_pos, "right": new_right_pos}

    def motors_are_moving(self, left: Signal, right: Signal) -> int:
        """Return 1 when either left or right motor is moving, else 0.

        Args:
            left (Signal): The signal representing the position of the left slit positioner.
            right (Signal): The signal representing the position of the right slit positioner.

        Returns:
            int: 1 if either motor is moving, 0 otherwise.
        """
        left_moving = left.get()
        right_moving = right.get()
        return int(left_moving or right_moving)


class VirtualSlitWidth(PSIPseudoMotorBase):
    """Pseudo motor controlling slit width from two edge motors.

    Both positioners must be present in the device manager, and the pseudo
    motor entry in the current session config must declare them in ``needs``.

    Args:
        name (str): The name of the pseudo motor device.
        left_slit (str): The name of the left slit positioner device in the device manager.
        right_slit (str): The name of the right slit positioner device in the device manager.
        device_manager (DeviceManagerBase): The device manager instance to fetch the positioner devices from.
        offset (float, optional): Constant width offset added in forward
            calculation and removed in inverse calculation.
        egu (str | None, optional): Engineering units. If omitted, units are
            taken from the left positioner.
    """

    offset = Cpt(
        SignalRO,
        name="offset",
        kind=Kind.config,
        doc="Offset applied to the position of the slit center when calculating the width.",
    )

    def __init__(
        self,
        name: str,
        left_slit: str,
        right_slit: str,
        device_manager: DeviceManagerBase,
        offset: float = 0,
        egu: str | None = None,
        **kwargs,
    ):
        positioners = self.get_positioner_objects(
            name=name,
            positioners={"left": left_slit, "right": right_slit},
            device_manager=device_manager,
        )
        if egu is None:  # if not specified, fetch it from the left positioner
            egu = positioners["left"].egu
            if positioners["right"].egu != egu:
                logger.warning(
                    f"Device {name} found inconsistency for egu for positioner left {left_slit} and right {right_slit}. Using egu {egu}."
                )
        self._offset = offset
        super().__init__(
            name=name, device_manager=device_manager, positioners=positioners, egu=egu, **kwargs
        )

    def wait_for_connection(self, *args, **kwargs):
        """Connect and initialize the read-only ``offset`` configuration signal."""
        super().wait_for_connection(*args, **kwargs)
        # Set the initial value of the offset signal
        # Config values are read by back after wait_for_connection is called.
        self.offset._readback = self._offset

    # pylint: disable=arguments-differ
    def forward_calculation(self, left: Signal, right: Signal) -> float:
        """Compute slit width from left and right positions.

        Args:
            left (Signal): The signal representing the position of the left slit positioner.
            right (Signal): The signal representing the position of the right slit positioner.

        Returns:
            float: Width ``right - left + offset``.
        """
        left_pos = left.get()
        right_pos = right.get()
        width = right_pos - left_pos + self._offset
        return float(width)

    def inverse_calculation(self, position: float, left: Signal, right: Signal) -> dict[str, float]:
        """Compute left/right setpoints for a target width.

        The current slit center is preserved.

        Args:
            position (float): The desired width of the slit.
            left (Signal): The signal representing the position of the left slit positioner.
            right (Signal): The signal representing the position of the right slit positioner.
        Returns:
            A dictionary with the new setpoints for the left and right positioners, with keys "left" and "right".
        """
        left_pos = left.get()
        right_pos = right.get()
        center = (left_pos + right_pos) / 2
        width = position - self._offset
        new_right_pos = center + width / 2
        new_left_pos = center - width / 2
        return {"left": new_left_pos, "right": new_right_pos}

    def motors_are_moving(self, left: Signal, right: Signal) -> int:
        """Return 1 when either left or right motor is moving, else 0.

        Args:
            left (Signal): The signal representing the position of the left slit positioner.
            right (Signal): The signal representing the position of the right slit positioner.
        Returns:
            int: 1 if either motor is moving, 0 otherwise.
        """
        left_moving = left.get()
        right_moving = right.get()
        return int(left_moving or right_moving)


if __name__ == "__main__":  # pragma: no cover
    # pylint: disable=import-outside-toplevel, unused-import, missing-docstring, ungrouped-imports, arguments-differ, protected-access
    from ophyd import Component as Cpt

    from ophyd_devices.sim.sim_positioner import SimPositioner

    ###########
    ## Alternative approach for virtual slit center
    ###########
    class TestPseudoMotor(PSIPseudoMotorBase):

        motor_a = Cpt(SimPositioner, name="motor_a")
        motor_b = Cpt(SimPositioner, name="motor_b")

        def __init__(self, name: str, device_manager: DeviceManagerBase, **kwargs):
            super().__init__(name=name, device_manager=device_manager, **kwargs)
            positioners = {"a": self.motor_a, "b": self.motor_b}
            self.set_positioner_objects(positioners)

        def _get_pos_motor(self, motor: PositionerBase) -> float:
            return motor.readback.get()

        def forward_calculation(self, a: Signal, b: Signal) -> float:
            return float(a.get() + b.get())

        def inverse_calculation(self, value: float, a: Signal, b: Signal) -> dict[str, float]:
            a_val = self._get_pos_motor(a.root)
            b_val = value - a_val
            return {"a": a_val, "b": b_val}

        def motors_are_moving(self, a: Signal, b: Signal) -> int:
            return int(a.get() or b.get())

    import time

    from bec_server.device_server.tests.utils import DMMock

    dm = DMMock()

    samx = SimPositioner(name="samx")
    samx.velocity.set(0.5)
    samy = SimPositioner(name="samy")
    samy.velocity.set(0.5)

    dm.devices._add_device("samx", samx)
    dm.devices._add_device("samy", samy)

    # Fix the current session config to include the needs for the slit center device
    setattr(
        dm, "current_session", {"devices": [{"name": "slit_center", "needs": ["samx", "samy"]}]}
    )

    slit_center = VirtualSlitCenter(
        name="slit_center", device_manager=dm, left_slit="samx", right_slit="samy"
    )

    test = TestPseudoMotor(name="test_pseudo", device_manager=dm)

    for dev in [samx, samy, slit_center, test]:
        dev.wait_for_connection()

    test.motor_a.move(5).wait()
    test.motor_b.move(-5).wait()

    print(test.read())
    test.move(2).wait()

    print(test.read())

    samx.tolerance.put(0.01)
    samy.tolerance.put(0.01)
    samx.move(1).wait()
    samy.move(3).wait()
    samx.velocity.set(1)
    samy.velocity.set(1)

    print(slit_center.read())
    print(samx.read())
    print(samy.read())

    st = slit_center.move(3)
    start_time = time.time()
    while not st.done:
        if (time.time() - start_time) > 10:
            break
        time.sleep(0.3)
        print(f"Running move, status done: {st.done}")

    print("Move completed or timed out.")
    print(slit_center.read())
    print(samx.read())
    print(samy.read())
    print("Done!!")
