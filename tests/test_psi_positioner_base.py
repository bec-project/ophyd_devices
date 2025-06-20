import sys
import time
from multiprocessing import Process
from unittest.mock import MagicMock, patch

import pytest
from caproto.ioc_examples import fake_motor_record as fmr
from caproto.server import ioc_arg_parser, run
from caproto.sync.client import read
from ophyd.device import Component as Cpt
from ophyd.signal import EpicsSignal
from ophyd.sim import FakeEpicsSignal, FakeEpicsSignalRO

from ophyd_devices.interfaces.base_classes.psi_positioner_base import (
    PSIPositionerBase,
    RequiredSignalNotSpecified,
)


@pytest.fixture
def sim_motor():
    with patch.object(sys, "argv", [sys.executable]):
        ioc_options, run_options = ioc_arg_parser(
            default_prefix="sim:", desc=fmr.FakeMotorIOC.__doc__
        )
    ioc = fmr.FakeMotorIOC(**ioc_options)
    p = Process(target=fmr.run, args=[ioc.pvdb], kwargs=run_options, daemon=True)
    p.start()

    import epics

    start = time.monotonic()
    time.sleep(0.1)
    while True:
        try:
            rd = epics.caget("sim:mtr1.RBV")
        except Exception as e:
            print(e)
            rd = None
        rd
        if time.monotonic() - start > 100:
            raise TimeoutError("Failed waiting for IOC to start")
    yield
    p.kill()
    p.join()


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


def test_against_ioc(sim_motor):
    assert 1
