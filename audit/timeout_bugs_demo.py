"""
Live demonstration of the PR #225 default-timeout findings (ophyd_devices, branch
feature/default_timeout_arg). Simulation only - no hardware, no BEC services needed.

Run from the repository root with the ophyd_devices environment active:

    python audit/timeout_bugs_demo.py

Every section prints what the code does today and marks the problem with "BUG".
Numbers match the review findings. The demo device classes live in
ophyd_devices/sim/timeout_demo.py (simulation only).
"""

from __future__ import annotations

import collections
import logging
import sys
import threading
import time
from unittest.mock import MagicMock

import numpy as np
from ophyd import Component as Cpt
from ophyd import Device, Kind, Signal, SoftPositioner
from ophyd.sim import make_fake_device
from ophyd.utils import UnknownStatusFailure

from ophyd_devices.interfaces.base_classes.psi_device_base import PSIDeviceBase
from ophyd_devices.sim.timeout_demo import TimeoutDemoCamera, TimeoutDemoPositioner
from ophyd_devices.utils.psi_device_base_utils import (
    AndStatus,
    CompareStatus,
    DeviceStatus,
    ExceptionStatus,
    _get_default_timeout,
)

# Keep stdout/stderr in order and route library noise into evidence we print ourselves.
sys.stdout.reconfigure(line_buffering=True)
try:
    from bec_lib.logger import bec_logger

    bec_logger.logger.remove()
except Exception:  # pragma: no cover - logger setup differs between environments
    pass


class _CaptureHandler(logging.Handler):
    """Collects log records instead of printing them (ophyd logs swallowed callback errors)."""

    def __init__(self):
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


ophyd_log_capture = _CaptureHandler()
logging.getLogger("ophyd").addHandler(ophyd_log_capture)
logging.getLogger("ophyd").propagate = False


def section(number: int, title: str) -> None:
    print(f"\n{'=' * 78}\n#{number}  {title}\n{'=' * 78}")


def show(label: str, value) -> None:
    print(f"    {label:<58} {value}")


def bug(text: str) -> None:
    print(f"    BUG  {text}")


def run(number: int, title: str, func) -> None:
    section(number, title)
    try:
        func()
    except Exception as exc:  # pragma: no cover - keep the demo running
        print(f"    (demo section raised {type(exc).__name__}: {exc})")


class PlainDevice(PSIDeviceBase, Device):
    """A plain PSI device with one signal (a detector, a camera, ...)."""

    sig = Cpt(Signal, value=0)


# --------------------------------------------------------------------------------------
# 1  init ordering: _timeout is validated/assigned only after super().__init__()
# --------------------------------------------------------------------------------------
def demo_init_ordering():
    class CountingSignal(Signal):
        created = 0

        def __init__(self, *args, **kwargs):
            CountingSignal.created += 1
            super().__init__(*args, **kwargs)

    class LeakDemo(PSIDeviceBase, Device):
        sig = Cpt(CountingSignal, value=0)

    print("  (a) an invalid timeout is rejected only AFTER the ophyd device was built")
    CountingSignal.created = 0
    try:
        LeakDemo(name="leak", timeout="5")
    except TypeError as exc:
        show("TypeError raised:", exc)
        show("signals already instantiated before the check:", CountingSignal.created)
        bug("the half-built device is leaked; its destroy() raises AttributeError")

    print("  (b) a status created while the device initialises crashes the construction")

    class ArmsStatusOnInit(Device):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            DeviceStatus(self).set_finished()  # walks up to the still-initialising parent

    class MidInit(PSIDeviceBase, Device):
        child = Cpt(ArmsStatusOnInit)

    try:
        MidInit(name="midinit", timeout=3)
        show("device constructed:", "yes")
    except RuntimeError as exc:
        show("device construction failed with:", f"{type(exc).__name__}: {str(exc)[:70]}...")
        bug("during super().__init__() the instance has no _timeout attribute yet")

    print("  (c) positioners: the raw, un-normalized value is visible during init")

    class RecordsStatusTimeout(Device):
        seen = None

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            status = DeviceStatus(self)
            RecordsStatusTimeout.seen = status.timeout
            status.set_finished()

    class MidInitPositioner(PSIDeviceBase, SoftPositioner):
        child = Cpt(RecordsStatusTimeout)

    pos = MidInitPositioner("", name="pos", timeout=-5)
    show("timeout=-5 given (docs: non-positive = no timeout)", "")
    show("status created mid-init saw timeout:", RecordsStatusTimeout.seen)
    show("after init, pos._timeout is:", pos._timeout)
    bug("a status armed during init gets -5 s and fails instantly")


# --------------------------------------------------------------------------------------
# 2  NaN and inf pass the "non-positive means no timeout" guard
# --------------------------------------------------------------------------------------
def demo_nan_inf():
    show("_normalize_timeout(nan) ->", PSIDeviceBase._normalize_timeout(float("nan")))
    show("_normalize_timeout(inf) ->", PSIDeviceBase._normalize_timeout(float("inf")))

    dev = PlainDevice(name="nan_dev", timeout=float("nan"))
    status = DeviceStatus(dev)
    time.sleep(0.1)
    show("timeout=nan: status done/success after 0.1 s:", f"{status.done}/{status.success}")
    bug("every status on a NaN device fails instantly (NaN <= 0 is False)")

    # The wait thread crashes; capture the thread exception instead of letting it print.
    thread_errors = []
    previous_hook = threading.excepthook
    threading.excepthook = thread_errors.append
    try:
        dev = PlainDevice(name="inf_dev", timeout=float("inf"))
        status = DeviceStatus(dev)
        time.sleep(0.5)
    finally:
        threading.excepthook = previous_hook
    show("timeout=inf: status done after 0.5 s:", status.done)
    show("timeout=inf: wait thread still alive:", status._callback_thread.is_alive())
    crash = (
        f"{thread_errors[0].exc_type.__name__}: {thread_errors[0].exc_value}"
        if thread_errors
        else "<no thread exception captured>"
    )
    show("timeout=inf: wait thread died with:", crash)
    bug("the status can neither complete nor time out; .wait() on it hangs forever")


# --------------------------------------------------------------------------------------
# 3  watchdog statuses inherit the default and fail their composites
# --------------------------------------------------------------------------------------
def demo_watchdog():
    dev = PlainDevice(name="wd_dev", timeout=0.3)
    watchdog = ExceptionStatus(dev.sig, value=1, run=False)
    show("ExceptionStatus (must stay pending) got timeout:", watchdog.timeout)

    dev2 = PlainDevice(name="wd_dev2", timeout=0.3)
    primary = DeviceStatus(dev2, timeout=60)  # the real operation, healthy, 60 s budget
    composite = primary & ExceptionStatus(dev2.sig, value=1)
    time.sleep(0.5)
    show("composite done/success after 0.5 s:", f"{composite.done}/{composite.success}")
    show("composite failure type:", type(composite.exception()).__name__)
    bug("the watchdog timed out and took the healthy operation down with it")
    primary.set_finished()


# --------------------------------------------------------------------------------------
# 4  background tasks (submit_task) inherit the default
# --------------------------------------------------------------------------------------
def demo_submit_task():
    dev = PlainDevice(name="task_dev", timeout=0.3)
    status = dev.task_handler.submit_task(lambda: time.sleep(0.8))
    show("task status timeout:", status.timeout)
    time.sleep(1.2)
    show("task status done/success after the task finished:", f"{status.done}/{status.success}")
    show("task state:", status.state)
    bug("a 0.8 s task on a 0.3 s device: failed status, state says 'completed'")


# --------------------------------------------------------------------------------------
# 5  a timed-out DeviceStatus calls device.stop(); no way to opt out
# --------------------------------------------------------------------------------------
def demo_stop_on_timeout():
    class StopCounter(PSIDeviceBase, Device):
        stop_calls = 0

        def on_stop(self):
            StopCounter.stop_calls += 1

    dev = StopCounter(name="stop_dev", timeout=0.3)
    DeviceStatus(dev)
    time.sleep(0.5)
    show("device.stop() calls after the status timed out:", StopCounter.stop_calls)
    bug("a slow-but-fine operation now stops the hardware")
    for kwargs, label in (({"call_stop_on_failure": False}, "call_stop_on_failure=False"),):
        try:
            DeviceStatus(dev, **kwargs)
            show(f"DeviceStatus(dev, {label}):", "accepted")
        except TypeError as exc:
            show(f"DeviceStatus(dev, {label}):", f"TypeError: {exc}")
            bug("ophyd's opt-out cannot be passed through the wrapper anymore")
    try:
        DeviceStatus(dev, "my description")
    except TypeError as exc:
        show("DeviceStatus(dev, 'my description') (worked on main):", f"TypeError: {exc}")


# --------------------------------------------------------------------------------------
# 6  positioners: explicit move timeout ignored, two racing watchdogs
# --------------------------------------------------------------------------------------
def demo_positioner():
    pos = TimeoutDemoPositioner(name="demo_pos", timeout=0.3)
    pos.wait_for_connection()
    status = pos.move(1, wait=False, timeout=10)
    show("move(1, timeout=10): caller status timeout:", status.timeout)
    show("internal completion watchdog timeout:", pos._move_completion_status.timeout)
    time.sleep(0.6)
    show("move done/success after 0.6 s:", f"{status.done}/{status.success}")
    show("failure type:", type(status.exception()).__name__)
    bug("the internal watchdog fired at the device default; the explicit 10 s was ignored")

    print("  race: same move repeated, which watchdog wins decides the exception type")
    outcomes = collections.Counter()
    for i in range(6):
        pos = TimeoutDemoPositioner(name=f"race_pos{i}", timeout=0.25)
        pos.wait_for_connection()
        status = pos.move(1, wait=False)
        time.sleep(0.6)
        outcomes[type(status.exception()).__name__] += 1
    show("exception types over 6 identical moves:", dict(outcomes))
    if len(outcomes) > 1:
        bug("nondeterministic failure type for identical failures")


# --------------------------------------------------------------------------------------
# 7  deployed motor "move completion" config becomes the timeout for everything
# --------------------------------------------------------------------------------------
def demo_motor_config():
    from ophyd_devices.devices.psi_motor import EpicsUserMotorVME

    FakeVME = make_fake_device(EpicsUserMotorVME)
    motor = FakeVME("SIM:MOTOR", name="motor")
    motor.timeout.put(3)  # == the existing deviceConfig 'timeout' of deployed VME motors
    show("motor.timeout signal (documented: move completion):", motor.timeout.get())
    show(
        "CompareStatus(motor.motor_enable, 1).timeout:",
        CompareStatus(motor.motor_enable, 1, run=False).timeout,
    )
    show("DeviceStatus(motor).timeout (e.g. complete()):", DeviceStatus(motor).timeout)
    show("background task timeout:", motor.task_handler.submit_task(lambda: None).timeout)
    bug("existing move-timeout configs silently cap every status of the motor")


# --------------------------------------------------------------------------------------
# 8  pseudo motors: the default is armed on paper but inert for moves
# --------------------------------------------------------------------------------------
def demo_pseudo_motor():
    from ophyd_devices.interfaces.base_classes.psi_pseudo_motor_base import PSIPseudoMotorBase
    from ophyd_devices.sim.sim_positioner import SimPositioner

    class DemoPseudo(PSIPseudoMotorBase):
        def forward_calculation(self, m):
            return m

        def inverse_calculation(self, position, m):
            return {"m": position}

        def motors_are_moving(self, m):
            return m

    from types import SimpleNamespace

    child = SimPositioner(name="m", delay=0)
    pseudo = DemoPseudo(
        name="pseudo", device_manager=MagicMock(), positioners={"m": child}, timeout=3
    )
    # stand-in for the BEC-computed model inputs the real device manager would provide
    pseudo.readback.compute_model = SimpleNamespace(method_inputs={"m": child})
    show("pseudo._timeout / pseudo.timeout:", f"{pseudo._timeout} / {pseudo.timeout}")
    status = pseudo.move(5.0)
    show("pseudo.move(5) returns a status with timeout:", status.timeout)
    bug("the move status never sees the default: a stalled child would wait forever")


# --------------------------------------------------------------------------------------
# 9  ophyd's public pos.timeout setter silently rewrites the status default
# --------------------------------------------------------------------------------------
def demo_timeout_property():
    pos = TimeoutDemoPositioner(name="prop_pos", timeout=5)
    show("constructed with timeout=5 -> DeviceStatus(pos).timeout:", DeviceStatus(pos).timeout)
    pos.timeout = 30  # documented ophyd API: the MOVE timeout
    show("after pos.timeout = 30 -> DeviceStatus(pos).timeout:", DeviceStatus(pos).timeout)
    pos.timeout = -3
    show("after pos.timeout = -3 -> DeviceStatus(pos).timeout:", DeviceStatus(pos).timeout)
    bug("two different knobs share one attribute, and this path is never normalized")


# --------------------------------------------------------------------------------------
# 10  complete()/kickoff() fallback statuses are no longer synchronously done
# --------------------------------------------------------------------------------------
def demo_pre_finished():
    cam = TimeoutDemoCamera(name="sync_cam", timeout=3)
    status = cam.complete()  # SimCamera returns None -> PSIDeviceBase fallback status
    immediately = status.done
    time.sleep(0.05)
    show("complete().timeout:", status.timeout)
    show("complete().done right after the call / 50 ms later:", f"{immediately} / {status.done}")
    bug("callers checking .done immediately see a still-running status")


# --------------------------------------------------------------------------------------
# 11  no way to opt a status out of the default; explicit 0 fails instantly
# --------------------------------------------------------------------------------------
def demo_no_opt_out():
    dev = PlainDevice(name="optout_dev", timeout=3)
    show("DeviceStatus(dev, timeout=None).timeout:", DeviceStatus(dev, timeout=None).timeout)
    status = DeviceStatus(dev, timeout=0)
    time.sleep(0.1)
    show("DeviceStatus(dev, timeout=0) done/success:", f"{status.done}/{status.success}")
    bug("None means 'use the default', 0 means 'fail now' - nothing means 'no timeout'")


# --------------------------------------------------------------------------------------
# 12  nested PSI sub-devices never inherit the parent's default
# --------------------------------------------------------------------------------------
def demo_nested():
    class PsiChild(PSIDeviceBase, Device):
        sig = Cpt(Signal, value=0)

    class PlainChild(Device):
        sig = Cpt(Signal, value=0)

    class Parent(PSIDeviceBase, Device):
        psi_child = Cpt(PsiChild)
        plain_child = Cpt(PlainChild)

    parent = Parent(name="parent", timeout=5)
    show("parent._timeout:", parent._timeout)
    show("status on the plain child's signal:", _get_default_timeout(parent.plain_child.sig))
    show("status on the PSI child's signal:", _get_default_timeout(parent.psi_child.sig))
    bug("a PSI sub-device shadows the parent's default with its own None")


# --------------------------------------------------------------------------------------
# 13  numpy values and bool: the type check bites in the wrong places
# --------------------------------------------------------------------------------------
def demo_numpy_bool():
    for value in (np.float64(3), np.int64(3), np.float32(3), True):
        try:
            show(f"_normalize_timeout({value!r}) ->", PSIDeviceBase._normalize_timeout(value))
        except TypeError as exc:
            show(f"_normalize_timeout({value!r}) ->", f"TypeError: {exc}")
    bug("np.int64/np.float32 rejected, np.float64 accepted; True becomes a 1 s timeout")

    class SyncDevice(PSIDeviceBase, Device):
        """The signal-sync pattern from the PR's own tests (TimeoutSignalDevice)."""

        timeout = Cpt(Signal, value=10)

        def __init__(self, timeout=10, **kwargs):
            super().__init__(timeout=timeout, **kwargs)
            self.timeout.subscribe(self._on_timeout_change, run=False)

        def _on_timeout_change(self, value, **kwargs):
            self._timeout = self._normalize_timeout(value)

    dev = SyncDevice(name="sync_dev")
    ophyd_log_capture.records.clear()
    dev.timeout.set(np.int64(5)).wait()  # what an integer PV delivers
    swallowed = [
        f"{rec.exc_info[0].__name__}: {rec.exc_info[1]}"
        for rec in ophyd_log_capture.records
        if rec.exc_info and "callback exception" in rec.getMessage()
    ]
    show("signal reads:", dev.timeout.get())
    show("device _timeout still:", dev._timeout)
    show("error ophyd swallowed in the callback:", swallowed[0] if swallowed else "<none>")
    bug("the signal shows the new value while the device keeps the old timeout")


# --------------------------------------------------------------------------------------
# 14  PandaBox: the staging error handler is bypassed
# --------------------------------------------------------------------------------------
def demo_pandabox():
    from ophyd_devices.devices.panda_box.panda_box import PandaBox, PandaState

    panda = PandaBox(name="panda", host="localhost", timeout=1)  # default < 3 s stage timeout
    panda.panda_state = PandaState.READY  # not disarmed yet, so on_stage has to wait
    try:
        panda.on_stage()
        show("on_stage:", "returned")
    except RuntimeError as exc:
        show("on_stage raised the intended RuntimeError:", str(exc)[:60])
    except Exception as exc:  # pylint: disable=broad-except
        show("on_stage raised:", f"{type(exc).__name__}")
        bug("expected RuntimeError('PandaBox did not disarm'); the except clause was skipped")


# --------------------------------------------------------------------------------------
# 15  mocks: a spec'd PSI device mock crashes status construction
# --------------------------------------------------------------------------------------
def demo_mock():
    try:
        DeviceStatus(MagicMock(spec=PSIDeviceBase))
        show("DeviceStatus(MagicMock(spec=PSIDeviceBase)):", "ok")
    except AttributeError as exc:
        show("DeviceStatus(MagicMock(spec=PSIDeviceBase)):", f"AttributeError: {exc}")
        bug("downstream test suites that mock PSI devices break")


if __name__ == "__main__":
    print("PR #225 default-timeout demo (simulation only)")
    run(
        1,
        "init ordering: validation and _timeout assignment happen after super().__init__()",
        demo_init_ordering,
    )
    run(2, "NaN and inf pass the timeout guard", demo_nan_inf)
    run(3, "watchdog statuses inherit the default and fail composites", demo_watchdog)
    run(4, "background tasks inherit the default", demo_submit_task)
    run(5, "a timed-out DeviceStatus stops the device; opt-out dropped", demo_stop_on_timeout)
    run(6, "positioners: explicit move timeout ignored, racing watchdogs", demo_positioner)
    run(7, "deployed motor timeout config caps every status", demo_motor_config)
    run(8, "pseudo motors: default armed on paper, inert for moves", demo_pseudo_motor)
    run(9, "pos.timeout setter silently rewrites the status default", demo_timeout_property)
    run(10, "complete()/kickoff() fallbacks no longer synchronously done", demo_pre_finished)
    run(11, "no opt-out; explicit timeout=0 fails instantly", demo_no_opt_out)
    run(12, "nested PSI sub-devices never inherit the default", demo_nested)
    run(13, "numpy/bool handling and silent signal-sync failure", demo_numpy_bool)
    run(14, "PandaBox staging error handler bypassed", demo_pandabox)
    run(15, "spec'd mocks crash status construction", demo_mock)
    print("\ndone.")
