"""Module to test the virtual slit center and width classes."""

import pytest
from bec_server.device_server.tests.utils import DMMock
from ophyd import Component as Cpt

from ophyd_devices import TransitionStatus
from ophyd_devices.devices.virtual_slit import VirtualSlitCenter, VirtualSlitWidth
from ophyd_devices.interfaces.base_classes.psi_pseudo_motor_base import PSIPseudoMotorBase
from ophyd_devices.sim.sim_positioner import SimPositioner


class TestPseudoMotor(PSIPseudoMotorBase):
    """Pseudo motor fixture class with two sub-positioner components."""

    motor_a = Cpt(SimPositioner, name="motor_a", delay=0)
    motor_b = Cpt(SimPositioner, name="motor_b", delay=0)

    def __init__(self, name, device_manager, **kwargs):
        super().__init__(name=name, device_manager=device_manager, **kwargs)
        self.set_positioner_objects({"a": self.motor_a, "b": self.motor_b})

    def forward_calculation(self, a, b):
        """Forward calculation."""
        return float(a.get() + b.get())

    def inverse_calculation(self, position, a, b):
        """Inverse calculation."""
        a_val = a.get()
        b_val = position - a_val
        return {"a": a_val, "b": b_val}

    def motors_are_moving(self, a, b):
        """Check if the sub-positioners are moving."""
        return int(a.get() or b.get())


@pytest.fixture
def pseudo_motor_fixture():
    """Fixture for the TestPseudoMotor with a mock device manager."""
    dm = DMMock()
    pseudo = TestPseudoMotor(name="test_pseudo", device_manager=dm)
    pseudo.wait_for_connection()
    return pseudo


@pytest.fixture
def samx():
    """Positioner fixture for the left slit motor."""
    return SimPositioner(name="samx", delay=0)


@pytest.fixture
def samy():
    """Positioner fixture for the right slit motor."""
    return SimPositioner(name="samy", delay=0)


@pytest.fixture
def device_manager_with_slit_motors(samx, samy):
    """Device manager fixture with slit motors and session configuration for virtual slits."""
    dm = DMMock()
    dm.devices["samx"] = samx
    dm.devices["samy"] = samy
    dm.current_session = {
        "devices": [
            {"name": "slit_center", "needs": ["samx", "samy"]},
            {"name": "slit_width", "needs": ["samx", "samy"]},
        ]
    }
    return dm


@pytest.fixture
def slit_center(device_manager_with_slit_motors):
    """Slit Center fixture"""
    center = VirtualSlitCenter(
        name="slit_center",
        left_slit="samx",
        right_slit="samy",
        device_manager=device_manager_with_slit_motors,
    )
    center.wait_for_connection()
    return center


@pytest.fixture
def slit_width(device_manager_with_slit_motors):
    """Slit Width fixture"""
    width = VirtualSlitWidth(
        name="slit_width",
        left_slit="samx",
        right_slit="samy",
        device_manager=device_manager_with_slit_motors,
    )
    width.wait_for_connection()
    return width


def test_subcomponent_pseudo_motor_move(pseudo_motor_fixture):
    """
    Test that moving the pseudo motor correctly updates the positions of the sub-positioners
    and that the readback of the pseudo motor reflects the new position.
    """
    pseudo_motor_fixture.motor_a.move(5).wait(timeout=2)
    pseudo_motor_fixture.motor_b.move(-5).wait(timeout=2)

    status = pseudo_motor_fixture.move(2)
    status.wait(timeout=2)

    assert pseudo_motor_fixture.motor_a.readback.get() == pytest.approx(5)
    assert pseudo_motor_fixture.motor_b.readback.get() == pytest.approx(-3)
    assert pseudo_motor_fixture.readback.get() == pytest.approx(2)


def test_virtual_slit_center_forward_calculation(slit_center, samx, samy):
    """
    Test that the forward calculation for the virtual slit center correctly computes
    the center position based on the current positions of the left and right slit motors.
    """
    samx.move(1).wait(timeout=2)
    samy.move(3).wait(timeout=2)

    center = slit_center.forward_calculation(samx.readback, samy.readback)
    assert center == pytest.approx(2)


def test_virtual_slit_center_inverse_calculation(slit_center, samx, samy):
    """
    Test that the inverse calculation for the virtual slit center correctly
    computes the positions of the left and right slit motors based on the
    desired center position and current positions of the slit motors.
    """
    status = TransitionStatus(slit_center.motor_is_moving, transitions=[0, 1, 0])
    st_samx = samx.move(1)
    st_samy = samy.move(3)

    status.wait(timeout=2)
    assert status.done is True, "Expected the slit center to start moving the slit motors."
    assert status.success is True, "Expected the slit center to move the slit motors."
    assert st_samy.done is True, "Expected the slit center to finish moving the right slit motor."
    assert st_samy.success is True, "Expected the slit center to move the right slit motor."
    assert st_samx.done is True, "Expected the slit center to finish moving the left slit motor."
    assert st_samx.success is True, "Expected the slit center to move the left slit motor."

    pos = slit_center.inverse_calculation(4, samx.readback, samy.readback)
    assert pos["left"] == pytest.approx(3)
    assert pos["right"] == pytest.approx(5)


def test_virtual_slit_width_forward_calculation(slit_width, samx, samy):
    """
    Test that the forward calculation for the virtual slit width correctly computes
    the width based on the current positions of the left and right slit motors.
    """
    samx.move(1).wait(timeout=2)
    samy.move(3).wait(timeout=2)

    width = slit_width.forward_calculation(samx.readback, samy.readback)
    assert width == pytest.approx(2)


def test_virtual_slit_width_inverse_calculation(slit_width, samx, samy):
    """
    Test that the inverse calculation for the virtual slit width correctly
    computes the positions of the left and right slit motors based on the
    desired width and current positions of the slit motors.
    """
    samx.move(1).wait(timeout=2)
    samy.move(3).wait(timeout=2)

    pos = slit_width.inverse_calculation(6, samx.readback, samy.readback)
    assert pos["left"] == pytest.approx(-1)
    assert pos["right"] == pytest.approx(5)


def test_virtual_slit_center_move(slit_center, samx, samy):
    """
    Test that moving the virtual slit center correctly updates the
    positions of the left and right slit motors.
    """
    samx.move(1).wait(timeout=2)
    samy.move(3).wait(timeout=2)

    assert slit_center.readback.get() == pytest.approx(2)

    status = slit_center.move(5)
    status.wait(timeout=2)

    assert samx.readback.get() == pytest.approx(4)
    assert samy.readback.get() == pytest.approx(6)
    assert slit_center.readback.get() == pytest.approx(5)


def test_virtual_slit_width_move(slit_width, samx, samy):
    """
    Test that moving the virtual slit width correctly updates the
    positions of the left and right slit motors.
    """
    samx.move(1).wait(timeout=2)
    samy.move(3).wait(timeout=2)

    # EGU should be taken from the left slit motor.
    assert slit_width.egu == samx.egu
    assert slit_width.egu == samx.egu

    status = slit_width.move(6)
    status.wait(timeout=2)

    assert samx.readback.get() == pytest.approx(-1)
    assert samy.readback.get() == pytest.approx(5)
    assert slit_width.readback.get() == pytest.approx(6)


def test_virtual_slit_offset_applied_in_forward_and_inverse(
    device_manager_with_slit_motors, samx, samy
):
    """
    Test that the offset is correctly applied in both forward and
    inverse calculations for the virtual slit center and width.
    """
    samx.move(1).wait(timeout=2)
    samy.move(3).wait(timeout=2)

    slit_center_offset = VirtualSlitCenter(
        name="slit_center",
        left_slit="samx",
        right_slit="samy",
        device_manager=device_manager_with_slit_motors,
        offset=0.5,
        egu="new_egu",
    )
    slit_width_offset = VirtualSlitWidth(
        name="slit_width",
        left_slit="samx",
        right_slit="samy",
        device_manager=device_manager_with_slit_motors,
        offset=0.5,
        egu="new_egu",
    )
    assert slit_width_offset.egu == "new_egu"
    assert slit_center_offset.egu == "new_egu"
    slit_center_offset.wait_for_connection()
    slit_width_offset.wait_for_connection()

    assert slit_center_offset.forward_calculation(samx.readback, samy.readback) == pytest.approx(
        2.5
    )
    assert slit_width_offset.forward_calculation(samx.readback, samy.readback) == pytest.approx(2.5)

    center_pos = slit_center_offset.inverse_calculation(5.5, samx.readback, samy.readback)
    assert center_pos["left"] == pytest.approx(4)
    assert center_pos["right"] == pytest.approx(6)

    width_pos = slit_width_offset.inverse_calculation(6.5, samx.readback, samy.readback)
    assert width_pos["left"] == pytest.approx(-1)
    assert width_pos["right"] == pytest.approx(5)

    # Check offset signal
    assert slit_center_offset.offset.get() == pytest.approx(0.5)
    assert slit_width_offset.offset.get() == pytest.approx(0.5)
