import threading
import time
from importlib.util import find_spec, module_from_spec, spec_from_file_location
from pathlib import Path

import pytest
from ophyd import Component as Cpt
from ophyd import Signal

from ophyd_devices.devices.simple_positioner import PSISimplePositioner

if find_spec("caproto") is None:
    pytest.skip("caproto is not installed", allow_module_level=True)

from caproto.server import run

IOC_PREFIX = "SIM:MOTOR:"
MOTOR_PREFIX = f"{IOC_PREFIX}mtr1"
IOC_SCRIPT = Path(__file__).with_name("caproto_simple_positioner_ioc.py")
SUFFIXES = {
    "user_readback": ".RBV",
    "user_setpoint": ".VAL",
    "velocity": ".VELO",
    "motor_done_move": ".DMOV",
}


def _load_ioc_module():
    ioc_spec = spec_from_file_location("caproto_simple_positioner_ioc", IOC_SCRIPT)
    assert ioc_spec is not None and ioc_spec.loader is not None
    ioc_module = module_from_spec(ioc_spec)
    ioc_spec.loader.exec_module(ioc_module)
    return ioc_module


def _caput(*args, **kwargs):
    from epics import caput

    return caput(*args, **kwargs)


def wait_for(condition, timeout: float = 5.0, interval: float = 0.05, label: str = "condition"):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return
        time.sleep(interval)
    raise TimeoutError(f"Timed out waiting for {label}")


@pytest.fixture(scope="module")
def caproto_simple_positioner_ioc():
    ioc_module = _load_ioc_module()
    ioc_module.ensure_repeater()
    ioc = ioc_module.MotorIOC(prefix=IOC_PREFIX)
    thread = threading.Thread(
        target=run, args=(ioc.pvdb,), kwargs={"interfaces": ["127.0.0.1"]}, daemon=True
    )
    thread.start()
    time.sleep(0.5)
    yield ioc


@pytest.fixture()
def live_simple_positioner(caproto_simple_positioner_ioc):
    pos = PSISimplePositioner(name="test", prefix=MOTOR_PREFIX, override_suffixes=SUFFIXES)
    pos.tolerance.put(0.001)
    pos.wait_for_connection(timeout=10)
    wait_for(
        lambda: pos.motor_done_move.get(use_monitor=False) == 1, timeout=10, label="initial DMOV=1"
    )
    yield pos


def test_live_simple_positioner_move_succeeds_within_tolerance(live_simple_positioner):
    _caput(f"{MOTOR_PREFIX}final_offset", 0.0005, wait=True, timeout=1)

    status = live_simple_positioner.move(1.0, wait=False, timeout=5)
    status.wait(timeout=5)

    assert status.done
    assert status.success
    assert live_simple_positioner.user_readback.get() == pytest.approx(1.0005)


def test_live_simple_positioner_move_fails_outside_tolerance(live_simple_positioner):
    _caput(f"{MOTOR_PREFIX}final_offset", 0.005, wait=True, timeout=1)

    status = live_simple_positioner.move(2.0, wait=False, timeout=5)

    with pytest.raises(RuntimeError, match="outside of tolerance"):
        status.wait(timeout=5)

    assert status.done
    assert not status.success
    assert live_simple_positioner.user_readback.get() == pytest.approx(2.005)
