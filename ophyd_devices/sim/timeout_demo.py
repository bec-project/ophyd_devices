"""
Simulated devices that make the PSIDeviceBase default-timeout behaviour observable.

Used by ``audit/timeout_bugs_demo.py`` (standalone, no BEC services needed) and by
``audit/timeout_demo_config.yaml`` (live, through the BEC IPython client). Simulation
only - nothing here touches hardware. Audit tooling, not part of the package API.

Exposure durations are device config values (``exposure`` signal), not the scan's
``exp_time``: in the current BEC the legacy ``scan_parameters["exp_time"]`` seen by
devices at stage time is 0 for v4 scans, which would make every demo exposure instant.
"""

from __future__ import annotations

import threading
import time

from ophyd import Component as Cpt
from ophyd import Device, Kind, Signal
from ophyd.sim import FakeEpicsSignal, FakeEpicsSignalRO

from ophyd_devices.interfaces.base_classes.psi_device_base import PSIDeviceBase
from ophyd_devices.interfaces.base_classes.psi_positioner_base import PSISimplePositionerBase
from ophyd_devices.sim.sim_camera import SimCamera
from ophyd_devices.utils.psi_device_base_utils import DeviceStatus, ExceptionStatus


class TimeoutDemoCamera(SimCamera):
    """SimCamera whose trigger task really takes ``exposure`` seconds, like a real exposure.

    With a ``timeout`` in the device config that is shorter than ``exposure``, every
    trigger status fails: background tasks (``task_handler.submit_task``) inherit the
    device default timeout.

    ``timeout`` is declared explicitly in ``__init__`` because the BEC device server only
    forwards ``deviceConfig`` keys that appear in the concrete class's own signature; a key
    that falls through to ``update_config`` is rejected with DeviceConfigError "Unknown config
    parameter timeout" (that is what happens to SimCamera, PandaBox and every other PSI
    device that relies on ``**kwargs``). Remove the parameter here to reproduce that.
    """

    exposure = Cpt(Signal, value=1.0, kind=Kind.config)

    def __init__(self, name: str, timeout: float | None = None, **kwargs):
        super().__init__(name=name, timeout=timeout, **kwargs)

    def on_trigger(self):
        def trigger_cam():
            time.sleep(self.exposure.get())
            for _ in range(self.burst.get()):
                self.preview.put(self.image.get())

        return self.task_handler.submit_task(trigger_cam)


class TimeoutDemoDetector(PSIDeviceBase, Device):
    """Detector whose trigger is a DeviceStatus finished after ``exposure`` seconds.

    Once the device default timeout is shorter than the exposure, two things happen:
    the trigger status fails, and ophyd's DeviceStatus failure handler calls
    ``device.stop()`` on the detector (visible as ``stop_count`` / ``stop_calls()``).
    """

    USER_ACCESS = ["stop_calls", "default_timeout"]

    readback = Cpt(Signal, value=0.0, kind=Kind.hinted)
    exposure = Cpt(Signal, value=1.0, kind=Kind.config)
    # Probes readable from the client: the device default the object holds, the timeout
    # the last trigger status was created with (0 = none), and device.stop() calls so far.
    applied_timeout = Cpt(Signal, value=-1.0, kind=Kind.hinted)
    status_timeout = Cpt(Signal, value=-1.0, kind=Kind.hinted)
    stop_count = Cpt(Signal, value=0.0, kind=Kind.hinted)

    # `timeout` is declared explicitly for the same reason as in TimeoutDemoCamera.
    def __init__(self, *, name: str, timeout: float | None = None, **kwargs):
        self._stop_calls = 0
        super().__init__(name=name, timeout=timeout, **kwargs)

    def stop_calls(self) -> int:
        """Number of times device.stop() was called on this detector."""
        return self._stop_calls

    def default_timeout(self) -> float | None:
        """The default status timeout this device currently applies (PSIDeviceBase._timeout)."""
        return self._timeout

    def on_stage(self):
        self.applied_timeout.put(self._timeout if self._timeout is not None else 0.0)

    def on_trigger(self):
        status = DeviceStatus(self)  # no explicit timeout -> inherits the device default
        self.status_timeout.put(status.timeout if status.timeout is not None else 0.0)

        def expose():
            time.sleep(self.exposure.get())
            self.readback.put(self.readback.get() + 1)
            if not status.done:
                status.set_finished()

        threading.Thread(target=expose, daemon=True).start()
        return status

    def on_stop(self):
        self._stop_calls += 1
        self.stop_count.put(float(self._stop_calls))


class TimeoutDemoWatchdogDetector(TimeoutDemoDetector):
    """Like TimeoutDemoDetector, but the exposure is guarded by an ExceptionStatus watchdog.

    The exposure status gets an explicit, generous timeout. The watchdog gets none - and
    therefore inherits the device default. When that fires, the watchdog fails and takes
    the composite status (and the scan) down although nothing went wrong.
    """

    error = Cpt(Signal, value=0, kind=Kind.omitted)

    def on_trigger(self):
        status = DeviceStatus(self, timeout=60)
        watchdog = ExceptionStatus(self.error, value=1)
        self.status_timeout.put(watchdog.timeout if watchdog.timeout is not None else 0.0)

        def expose():
            time.sleep(self.exposure.get())
            self.readback.put(self.readback.get() + 1)
            if not status.done:
                status.set_finished()

        threading.Thread(target=expose, daemon=True).start()
        return status & watchdog


class TimeoutDemoPositioner(PSISimplePositionerBase):
    """PSI positioner on fake EPICS signals whose motion never reports "done".

    Every move waits forever, which makes the timeout handling itself visible: which
    watchdog fires, with which exception, and whether an explicit per-move timeout is
    honoured.
    """

    user_setpoint = Cpt(FakeEpicsSignal, ".VAL", auto_monitor=True)
    user_readback = Cpt(FakeEpicsSignalRO, ".RBV", kind="hinted", auto_monitor=True)
    motor_done_move = Cpt(FakeEpicsSignalRO, ".DMOV", auto_monitor=True)

    # Like every production positioner, `timeout` is NOT in this signature: through BEC the
    # config value never reaches the PSIDeviceBase constructor. It reaches the device only
    # because ophyd's PositionerBase has a `timeout` property, which the device server sets
    # with setattr - unvalidated, so `timeout: -1` in the config means "fail instantly".
    def __init__(self, prefix: str = "SIM:TIMEOUT:", *, name: str, limits=(-1000, 1000), **kwargs):
        super().__init__(prefix, name=name, limits=limits, **kwargs)


class TimeoutDemoPositionerCtor(TimeoutDemoPositioner):
    """Same positioner, but `timeout` is declared in the signature: the PR's intended path."""

    def __init__(
        self, prefix: str = "SIM:TIMEOUT:", *, name: str, timeout: float | None = None, **kwargs
    ):
        super().__init__(prefix, name=name, timeout=timeout, **kwargs)
