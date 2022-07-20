import threading
import time as ttime
import warnings

import numpy as np
from ophyd import Component as Cpt
from ophyd import Device, DeviceStatus, PositionerBase, Signal
from ophyd.sim import _ReadbackSignal, _SetpointSignal
from ophyd.utils import LimitError, ReadOnlyError


class DeviceStop(Exception):
    pass


class _ReadbackSignal(Signal):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._metadata.update(
            connected=True,
            write_access=False,
        )

    def get(self):
        self._readback = self.parent.sim_state["readback"]
        return self._readback

    def describe(self):
        res = super().describe()
        # There should be only one key here, but for the sake of
        # generality....
        for k in res:
            res[k]["precision"] = self.parent.precision
        return res

    @property
    def timestamp(self):
        """Timestamp of the readback value"""
        return self.parent.sim_state["readback_ts"]

    def put(self, value, *, timestamp=None, force=False):
        raise ReadOnlyError("The signal {} is readonly.".format(self.name))

    def set(self, value, *, timestamp=None, force=False):
        raise ReadOnlyError("The signal {} is readonly.".format(self.name))


class _ReadbackSignalRand(Signal):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._metadata.update(
            connected=True,
            write_access=False,
        )

    def get(self):
        self._readback = np.random.rand()
        return self._readback

    def describe(self):
        res = super().describe()
        # There should be only one key here, but for the sake of
        # generality....
        for k in res:
            res[k]["precision"] = self.parent.precision
        return res

    @property
    def timestamp(self):
        """Timestamp of the readback value"""
        return self.parent.sim_state["readback_ts"]

    def put(self, value, *, timestamp=None, force=False):
        raise ReadOnlyError("The signal {} is readonly.".format(self.name))

    def set(self, value, *, timestamp=None, force=False):
        raise ReadOnlyError("The signal {} is readonly.".format(self.name))


class _SetpointSignal(Signal):
    def put(self, value, *, timestamp=None, force=False):
        self._readback = float(value)
        self.parent.set(float(value))

    def get(self):
        self._readback = self.parent.sim_state["setpoint"]
        return self.parent.sim_state["setpoint"]

    def describe(self):
        res = super().describe()
        # There should be only one key here, but for the sake of generality....
        for k in res:
            res[k]["precision"] = self.parent.precision
        return res

    @property
    def timestamp(self):
        """Timestamp of the readback value"""
        return self.parent.sim_state["setpoint_ts"]


class _IsMovingSignal(Signal):
    def put(self, value, *, timestamp=None, force=False):
        self._readback = float(value)
        self.parent.set(float(value))

    def get(self):
        self._readback = self.parent.sim_state["is_moving"]
        return self.parent.sim_state["is_moving"]

    def describe(self):
        res = super().describe()
        # There should be only one key here, but for the sake of generality....
        for k in res:
            res[k]["precision"] = self.parent.precision
        return res

    @property
    def timestamp(self):
        """Timestamp of the readback value"""
        return self.parent.sim_state["is_moving_ts"]


class SynAxisMonitor(Device):
    """
    A synthetic settable Device mimic any 1D Axis (position, temperature).

    Parameters
    ----------
    name : string, keyword only
    readback_func : callable, optional
        When the Device is set to ``x``, its readback will be updated to
        ``f(x)``. This can be used to introduce random noise or a systematic
        offset.
        Expected signature: ``f(x) -> value``.
    value : object, optional
        The initial value. Default is 0.
    delay : number, optional
        Simulates how long it takes the device to "move". Default is 0 seconds.
    precision : integer, optional
        Digits of precision. Default is 3.
    parent : Device, optional
        Used internally if this Signal is made part of a larger Device.
    kind : a member the Kind IntEnum (or equivalent integer), optional
        Default is Kind.normal. See Kind for options.
    """

    readback = Cpt(_ReadbackSignalRand, value=0, kind="hinted")

    SUB_READBACK = "readback"
    _default_sub = SUB_READBACK

    def __init__(
        self,
        *,
        name,
        readback_func=None,
        value=0,
        delay=0,
        precision=3,
        parent=None,
        labels=None,
        kind=None,
        **kwargs,
    ):
        if readback_func is None:

            def readback_func(x):
                return x

        sentinel = object()
        loop = kwargs.pop("loop", sentinel)
        if loop is not sentinel:
            warnings.warn(
                f"{self.__class__} no longer takes a loop as input.  "
                "Your input will be ignored and may raise in the future",
                stacklevel=2,
            )
        self.sim_state = {}
        self._readback_func = readback_func
        self.delay = delay
        self.precision = precision
        self.tolerance = kwargs.pop("tolerance", 0.5)

        # initialize values
        self.sim_state["readback"] = readback_func(value)
        self.sim_state["readback_ts"] = ttime.time()

        super().__init__(name=name, parent=parent, labels=labels, kind=kind, **kwargs)
        self.readback.name = self.name


class DummyController:
    USER_ACCESS = ["some_var", "controller_show_all"]
    some_var = 10
    another_var = 20

    def controller_show_all(self):
        """dummy controller show all

        Raises:
            in: _description_
            LimitError: _description_

        Returns:
            _type_: _description_
        """
        print(self.some_var)


class SynAxisOPAAS(Device, PositionerBase):
    """
    A synthetic settable Device mimic any 1D Axis (position, temperature).

    Parameters
    ----------
    name : string, keyword only
    readback_func : callable, optional
        When the Device is set to ``x``, its readback will be updated to
        ``f(x)``. This can be used to introduce random noise or a systematic
        offset.
        Expected signature: ``f(x) -> value``.
    value : object, optional
        The initial value. Default is 0.
    delay : number, optional
        Simulates how long it takes the device to "move". Default is 0 seconds.
    precision : integer, optional
        Digits of precision. Default is 3.
    parent : Device, optional
        Used internally if this Signal is made part of a larger Device.
    kind : a member the Kind IntEnum (or equivalent integer), optional
        Default is Kind.normal. See Kind for options.
    """

    USER_ACCESS = ["sim_state", "readback", "speed", "dummy_controller"]
    readback = Cpt(_ReadbackSignal, value=0, kind="hinted")
    setpoint = Cpt(_SetpointSignal, value=0, kind="normal")
    motor_is_moving = Cpt(_IsMovingSignal, value=0, kind="normal")

    velocity = Cpt(Signal, value=1, kind="config")
    acceleration = Cpt(Signal, value=1, kind="config")

    high_limit_travel = Cpt(Signal, value=0, kind="omitted")
    low_limit_travel = Cpt(Signal, value=0, kind="omitted")
    unused = Cpt(Signal, value=1, kind="omitted")

    SUB_READBACK = "readback"
    _default_sub = SUB_READBACK

    def __init__(
        self,
        *,
        name,
        readback_func=None,
        value=0,
        delay=0,
        speed=1,
        update_frequency=2,
        precision=3,
        parent=None,
        labels=None,
        kind=None,
        limits=None,
        **kwargs,
    ):
        if readback_func is None:

            def readback_func(x):
                return x

        sentinel = object()
        loop = kwargs.pop("loop", sentinel)
        if loop is not sentinel:
            warnings.warn(
                f"{self.__class__} no longer takes a loop as input.  "
                "Your input will be ignored and may raise in the future",
                stacklevel=2,
            )
        self.sim_state = {}
        self._readback_func = readback_func
        self.delay = delay
        self.precision = precision
        self.speed = speed
        self.update_frequency = update_frequency
        self.tolerance = kwargs.pop("tolerance", 0.05)
        self._stopped = False

        self.dummy_controller = DummyController()

        # initialize values
        self.sim_state["setpoint"] = value
        self.sim_state["setpoint_ts"] = ttime.time()
        self.sim_state["readback"] = readback_func(value)
        self.sim_state["readback_ts"] = ttime.time()
        self.sim_state["is_moving"] = 0
        self.sim_state["is_moving_ts"] = ttime.time()

        super().__init__(name=name, parent=parent, labels=labels, kind=kind, **kwargs)
        self.readback.name = self.name
        if limits is not None:
            assert len(limits) == 2
            self.low_limit_travel.put(limits[0])
            self.high_limit_travel.put(limits[1])

    @property
    def limits(self):
        return (self.low_limit_travel.get(), self.high_limit_travel.get())

    @property
    def low_limit(self):
        return self.limits[0]

    @property
    def high_limit(self):
        return self.limits[1]

    def check_value(self, pos):
        """Check that the position is within the soft limits"""
        low_limit, high_limit = self.limits

        if low_limit < high_limit and not (low_limit <= pos <= high_limit):
            raise LimitError(f"position={pos} not within limits {self.limits}")

    def set(self, value):
        self._stopped = False
        self.check_value(value)
        old_setpoint = self.sim_state["setpoint"]
        self.sim_state["is_moving"] = 1
        self.motor_is_moving._run_subs(
            sub_type=self.motor_is_moving.SUB_VALUE,
            old_value=0,
            value=1,
            timestamp=self.sim_state["is_moving_ts"],
        )
        self.sim_state["setpoint"] = value
        self.sim_state["setpoint_ts"] = ttime.time()
        self.setpoint._run_subs(
            sub_type=self.setpoint.SUB_VALUE,
            old_value=old_setpoint,
            value=self.sim_state["setpoint"],
            timestamp=self.sim_state["setpoint_ts"],
        )

        def update_state(val):
            if self._stopped:
                raise DeviceStop
            old_readback = self.sim_state["readback"]
            self.sim_state["readback"] = val
            self.sim_state["readback_ts"] = ttime.time()
            self.readback._run_subs(
                sub_type=self.readback.SUB_VALUE,
                old_value=old_readback,
                value=self.sim_state["readback"],
                timestamp=self.sim_state["readback_ts"],
            )
            self._run_subs(
                sub_type=self.SUB_READBACK,
                old_value=old_readback,
                value=self.sim_state["readback"],
                timestamp=self.sim_state["readback_ts"],
            )

        st = DeviceStatus(device=self)
        if self.delay:

            def move_and_finish():
                success = True
                try:
                    move_val = self.sim_state["setpoint"] + self.tolerance * np.random.uniform(
                        -1, 1
                    )
                    updates = np.ceil(
                        np.abs(old_setpoint - move_val) / self.speed * self.update_frequency
                    )
                    for ii in np.linspace(old_setpoint, move_val, int(updates)):
                        ttime.sleep(1 / self.update_frequency)
                        update_state(ii)
                    update_state(move_val)
                    self.sim_state["is_moving"] = 0
                    self.sim_state["is_moving_ts"] = ttime.time()
                    self.motor_is_moving._run_subs(
                        sub_type=self.motor_is_moving.SUB_VALUE,
                        old_value=1,
                        value=0,
                        timestamp=self.sim_state["is_moving_ts"],
                    )
                except DeviceStop:
                    success = False
                finally:
                    self._stopped = False
                self._done_moving(success=success)
                st.set_finished()

            threading.Thread(target=move_and_finish, daemon=True).start()
            # raise TimeoutError

        else:
            update_state(value)
            self._done_moving()
        return st

    def stop(self, *, success=False):
        super().stop(success=success)
        self._stopped = True

    @property
    def position(self):
        return self.readback.get()

    def egu(self):
        return "mm"
