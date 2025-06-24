from ophyd import Component as Cpt
from ophyd import EpicsSignal

from ophyd_devices.interfaces.base_classes.psi_positioner_base import PSISimplePositionerBase


class PSISimplePositioner(PSISimplePositionerBase):
    user_readback = Cpt(EpicsSignal, "R")
    user_setpoint = Cpt(EpicsSignal, "S")
    velocity = Cpt(EpicsSignal, "V")
    motor_done_move = Cpt(EpicsSignal, "D")


if __name__ == "__main__":  # pragma: no cover
    """You can use this to test against e.g. the Caproto fake motor IOC"""
    suffixes = {
        "user_readback": ".RBV",
        "user_setpoint": ".VAL",
        "velocity": ".VELO",
        "motor_done_move": ".DMOV",
    }
    pos = PSISimplePositioner(name="test", prefix="SIM:MOTOR", override_suffixes=suffixes)
    pos.wait_for_connection()
    st = pos.move(5, wait=False)
