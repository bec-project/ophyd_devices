from unittest.mock import MagicMock

import pytest
from ophyd.device import Component as Cpt
from ophyd.signal import EpicsSignal
from ophyd.sim import FakeEpicsSignal, FakeEpicsSignalRO

from ophyd_devices.interfaces.base_classes.psi_positioner_base import (
    PSIPositionerBase,
    RequiredSignalNotSpecified,
)


def test_cannot_isntantiate_without_required_signals():
    class PSITestPositionerWOSignal(PSIPositionerBase): ...

    class PSITestPositionerWithSignal(PSIPositionerBase):
        user_setpoint: EpicsSignal = Cpt(FakeEpicsSignal, ".VAL", limits=True, auto_monitor=True)
        user_readback = Cpt(FakeEpicsSignalRO, ".RBV", kind="hinted", auto_monitor=True)

    with pytest.raises(RequiredSignalNotSpecified) as e:
        PSITestPositionerWOSignal("", name="")
        assert e.match("user_setpoint")
        assert e.match("user_readback")

    dev = PSITestPositionerWithSignal("", name="")
    assert dev.user_setpoint.get() == 0
