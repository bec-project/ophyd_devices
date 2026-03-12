"""Module for virtual slit center implementation."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ophyd_devices.interfaces.base_classes.psi_pseudo_motor_base import PSIPseudoMotorBase

if TYPE_CHECKING:  # pragma: no cover
    from bec_lib.devicemanager import DeviceManagerBase
    from ophyd import PositionerBase, Signal


class VirtualSlitCenter(PSIPseudoMotorBase):
    """
    Virtual slit center implementation. It expects the left and right slit positioner names to be passed
    as arguments. The named devices must be positioners and available in the device_manager. In addition,
    it must have a readback (user_readback), setpoint (user_setpoint) and motor_is_moving signal.

    Args:
        name (str): The name of the virtual slit center.
        left_slit (str): The name of the left slit positioner in the device manager.
        right_slit (str): The name of the right slit positioner in the device manager.
        device_manager (DeviceManagerBase): The device manager to use for connecting to the positioners.
    """

    def __init__(
        self,
        name: str,
        left_slit: str,
        right_slit: str,
        device_manager: DeviceManagerBase,
        offset: float = 0,
        **kwargs,
    ):
        positioners = self.get_positioner_objects(
            name=name,
            positioners={"left": left_slit, "right": right_slit},
            device_manager=device_manager,
        )
        self._offset = offset
        super().__init__(
            name=name, device_manager=device_manager, positioners=positioners, **kwargs
        )

    def _get_pos_motor(self, motor: PositionerBase) -> float:
        """
        Helper method to get the position of a motor.

        Args:
            motor (PositionerBase): The motor to get the position of.
        """
        return motor.read()[motor.name]["value"]

    # pylint: disable=arguments-differ
    def forward_calculation(self, left: Signal, right: Signal) -> float:
        """
        Forward calculation to compute the value for the pseudo motor readback
        and setpoint based on the position of the left and right slit.

        Args:
            left (Signal): The left slit positioner signal.
            right (Signal): The right slit positioner signal.

        Returns:
            float: The center position of the slit.
        """
        left_pos = left.get()
        right_pos = right.get()
        center = (left_pos + right_pos) / 2 + self._offset
        return float(center)

    def inverse_calculation(self, position: float, left: Signal, right: Signal) -> dict[str, float]:
        """
        Inverse calculation to compute the position of the left and right slit based on the center position.

        Args:
            center (float): The center position of the slit.
            left (Signal): The left slit positioner signal.
            right (Signal): The right slit positioner signal.

        Returns:
            dict[str, float]: The positions of the left and right slit.
        """
        position_with_offset = position - self._offset
        # To access position, run read on the root (PositionerBase) of the signal
        left_pos = self._get_pos_motor(left.root)
        right_pos = self._get_pos_motor(right.root)
        width = right_pos - left_pos
        new_left_pos = position_with_offset - width / 2
        new_right_pos = position_with_offset + width / 2
        return {"left": new_left_pos, "right": new_right_pos}

    def motors_are_moving(self, left: Signal, right: Signal) -> int:
        """
        Calculate whether the motors are moving based on the motor_is_moving signal of the left and right slit.

        Args:
            left (Signal): The left slit positioner signal.
            right (Signal): The right slit positioner signal.
        Returns:
            int: 1 if either motor is moving, 0 otherwise.
        """
        left_moving = left.get()
        right_moving = right.get()
        return int(left_moving or right_moving)


class VirtualSlitWidth(PSIPseudoMotorBase):

    def __init__(
        self,
        name: str,
        left_slit: str,
        right_slit: str,
        device_manager: DeviceManagerBase,
        **kwargs,
    ):
        positioners = self.get_positioner_objects(
            name=name,
            positioners={"left": left_slit, "right": right_slit},
            device_manager=device_manager,
        )
        super().__init__(
            name=name, device_manager=device_manager, positioners=positioners, **kwargs
        )

    def _get_pos_motor(self, motor: PositionerBase) -> float:
        """
        Helper method to get the position of a motor.

        Args:
            motor (PositionerBase): The motor to get the position of.
        """
        return motor.read()[motor.name]["value"]

    # pylint: disable=arguments-differ
    def forward_calculation(self, left: Signal, right: Signal) -> float:
        """
        Forward calculation to compute the value for the pseudo motor readback
        and setpoint based on the position of the left and right slit.

        Args:
            left (Signal): The left slit positioner signal.
            right (Signal): The right slit positioner signal.

        Returns:
            float: The center position of the slit.
        """
        left_pos = left.get()
        right_pos = right.get()
        width = right_pos - left_pos
        return float(width)

    def inverse_calculation(self, position: float, left: Signal, right: Signal) -> dict[str, float]:
        """
        Inverse calculation to compute the position of the left and right slit based on the center position.

        Args:
            position (float): The center position of the slit.

        Returns:
            dict[str, float]: The positions of the left and right slit.
        """
        left_pos = self._get_pos_motor(left.root)
        right_pos = self._get_pos_motor(right.root)
        center = (left_pos + right_pos) / 2
        width = right_pos - left_pos
        new_right_pos = center + width / 2
        new_left_pos = center - width / 2
        return {"left": new_left_pos, "right": new_right_pos}

    def motors_are_moving(self, left: Signal, right: Signal) -> int:
        """
        Calculate whether the motors are moving based on the motor_is_moving signal of the left and right slit.

        Args:
            left (Signal): The left slit positioner signal.
            right (Signal): The right slit positioner signal.
        Returns:
            int: 1 if either motor is moving, 0 otherwise.
        """
        left_moving = left.get()
        right_moving = right.get()
        return int(left_moving or right_moving)


if __name__ == "__main__":  # pragma: no cover
    from ophyd import Component as Cpt

    from ophyd_devices.sim.sim_positioner import SimPositioner

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
