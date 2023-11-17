import os
import threading
import time as ttime
import warnings
from typing import List

import numpy as np
from bec_lib import MessageEndpoints, bec_logger, messages
from ophyd import Component as Cpt
from ophyd import Device, DeviceStatus
from ophyd import DynamicDeviceComponent as Dcpt
from ophyd import OphydObject, PositionerBase, Signal
from ophyd.sim import EnumSignal, SynSignal, _ReadbackSignal, _SetpointSignal
from ophyd.utils import LimitError, ReadOnlyError

logger = bec_logger.logger


class DeviceStop(Exception):
    pass


class SynSignalRO(Signal):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._metadata.update(
            write_access=False,
        )

    def wait_for_connection(self, timeout=0):
        super().wait_for_connection(timeout)
        self._metadata.update(connected=True)

    def get(self, **kwargs):
        self._readback = np.random.rand()
        return self._readback


class _ReadbackSignal(Signal):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._metadata.update(
            connected=True,
            write_access=False,
        )

    def get(self):
        self._readback = self.parent.sim_state["readback"]
        self.parent.sim_state["readback_ts"] = ttime.time()
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


class _ReadbackSignalCompute(Signal):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._metadata.update(
            connected=True,
            write_access=False,
        )

    def get(self):
        readback = self.parent._compute()
        self._readback = self.parent.sim_state["readback"] = readback
        return readback

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


class _SLSDetectorConfigSignal(Signal):
    def put(self, value, *, timestamp=None, force=False):
        self._readback = value
        self.parent.sim_state[self.name] = value

    def get(self):
        self._readback = self.parent.sim_state[self.name]
        return self.parent.sim_state[self.name]


class SynSLSDetector(Device):
    USER_ACCESS = []
    exp_time = Cpt(_SLSDetectorConfigSignal, name="exp_time", value=1, kind="config")
    file_path = Cpt(_SLSDetectorConfigSignal, name="file_path", value="", kind="config")
    file_pattern = Cpt(_SLSDetectorConfigSignal, name="file_pattern", value="", kind="config")
    frames = Cpt(_SLSDetectorConfigSignal, name="frames", value=1, kind="config")
    burst = Cpt(_SLSDetectorConfigSignal, name="burst", value=1, kind="config")
    save_file = Cpt(_SLSDetectorConfigSignal, name="save_file", value=False, kind="config")

    def __init__(self, *, name, kind=None, parent=None, device_manager=None, **kwargs):
        self.device_manager = device_manager
        super().__init__(name=name, parent=parent, kind=kind, **kwargs)
        self.sim_state = {
            f"{self.name}_file_path": "~/Data10/data/",
            f"{self.name}_file_pattern": f"{self.name}_{{:05d}}.h5",
            f"{self.name}_frames": 1,
            f"{self.name}_burst": 1,
            f"{self.name}_save_file": False,
            f"{self.name}_exp_time": 0,
        }
        self._stopped = False
        self.file_name = ""
        self.metadata = {}

    def trigger(self):
        status = DeviceStatus(self)

        self.subscribe(status._finished, event_type=self.SUB_ACQ_DONE, run=False)

        def acquire():
            try:
                for _ in range(self.burst.get()):
                    ttime.sleep(self.exp_time.get())
                    if self._stopped:
                        raise DeviceStop
            except DeviceStop:
                pass
            finally:
                self._stopped = False
                self._done_acquiring()

        threading.Thread(target=acquire, daemon=True).start()
        return status

    def stage(self) -> List[object]:
        msg = self.device_manager.producer.get(MessageEndpoints.scan_status())
        scan_msg = messages.ScanStatusMessage.loads(msg)
        self.metadata = {
            "scanID": scan_msg.content["scanID"],
            "RID": scan_msg.content["info"]["RID"],
            "queueID": scan_msg.content["info"]["queueID"],
        }
        scan_number = scan_msg.content["info"]["scan_number"]
        self.frames.set(scan_msg.content["info"]["num_points"])
        self.file_name = os.path.join(
            self.file_path.get(), self.file_pattern.get().format(scan_number)
        )
        return super().stage()

    def unstage(self) -> List[object]:
        signals = {"config": self.sim_state, "data": self.file_name}
        msg = messages.DeviceMessage(signals=signals, metadata=self.metadata)
        self.device_manager.producer.set_and_publish(
            MessageEndpoints.device_read(self.name), msg.dumps()
        )
        return super().unstage()

    def stop(self, *, success=False):
        super().stop(success=success)
        self._stopped = True


class DummyController:
    USER_ACCESS = [
        "some_var",
        "controller_show_all",
        "_func_with_args",
        "_func_with_args_and_kwargs",
        "_func_with_kwargs",
        "_func_without_args_kwargs",
    ]
    some_var = 10
    another_var = 20

    def on(self):
        self._connected = True

    def off(self):
        self._connected = False

    def _func_with_args(self, *args):
        return args

    def _func_with_args_and_kwargs(self, *args, **kwargs):
        return args, kwargs

    def _func_with_kwargs(self, **kwargs):
        return kwargs

    def _func_without_args_kwargs(self):
        return None

    def controller_show_all(self):
        """dummy controller show all

        Raises:
            in: _description_
            LimitError: _description_

        Returns:
            _type_: _description_
        """
        print(self.some_var)


class DummyControllerDevice(Device):
    USER_ACCESS = ["controller"]


class SynFlyer(Device, PositionerBase):
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
        device_manager=None,
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
        self.device_manager = device_manager

        # initialize values
        self.sim_state["readback"] = readback_func(value)
        self.sim_state["readback_ts"] = ttime.time()

        super().__init__(name=name, parent=parent, labels=labels, kind=kind, **kwargs)

    @property
    def hints(self):
        return {"fields": ["flyer_samx", "flyer_samy"]}

    def kickoff(self, metadata, num_pos, positions, exp_time: float = 0):
        positions = np.asarray(positions)

        def produce_data(device, metadata):
            buffer_time = 0.2
            elapsed_time = 0
            bundle = messages.BundleMessage()
            for ii in range(num_pos):
                bundle.append(
                    messages.DeviceMessage(
                        signals={
                            self.name: {
                                "flyer_samx": {"value": positions[ii, 0], "timestamp": 0},
                                "flyer_samy": {"value": positions[ii, 1], "timestamp": 0},
                            }
                        },
                        metadata={"pointID": ii, **metadata},
                    ).dumps()
                )
                ttime.sleep(exp_time)
                elapsed_time += exp_time
                if elapsed_time > buffer_time:
                    elapsed_time = 0
                    device.device_manager.producer.send(
                        MessageEndpoints.device_read(device.name), bundle.dumps()
                    )
                    bundle = messages.BundleMessage()
                    device.device_manager.producer.set_and_publish(
                        MessageEndpoints.device_status(device.name),
                        messages.DeviceStatusMessage(
                            device=device.name,
                            status=1,
                            metadata={"pointID": ii, **metadata},
                        ).dumps(),
                    )
            device.device_manager.producer.send(
                MessageEndpoints.device_read(device.name), bundle.dumps()
            )
            device.device_manager.producer.set_and_publish(
                MessageEndpoints.device_status(device.name),
                messages.DeviceStatusMessage(
                    device=device.name,
                    status=0,
                    metadata={"pointID": num_pos, **metadata},
                ).dumps(),
            )
            print("done")

        flyer = threading.Thread(target=produce_data, args=(self, metadata))
        flyer.start()


class SynController(OphydObject):
    def on(self):
        pass

    def off(self):
        pass


class SynFlyerLamNI(Device, PositionerBase):
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
        device_manager=None,
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
        self.device_manager = device_manager

        # initialize values
        self.sim_state["readback"] = readback_func(value)
        self.sim_state["readback_ts"] = ttime.time()

        super().__init__(name=name, parent=parent, labels=labels, kind=kind, **kwargs)
        self.controller = SynController(name="SynController")

    def kickoff(self, metadata, num_pos, positions, exp_time: float = 0):
        positions = np.asarray(positions)

        def produce_data(device, metadata):
            buffer_time = 0.2
            elapsed_time = 0
            bundle = messages.BundleMessage()
            for ii in range(num_pos):
                bundle.append(
                    messages.DeviceMessage(
                        signals={
                            "syn_flyer_lamni": {
                                "flyer_samx": {"value": positions[ii, 0], "timestamp": 0},
                                "flyer_samy": {"value": positions[ii, 1], "timestamp": 0},
                            }
                        },
                        metadata={"pointID": ii, **metadata},
                    ).dumps()
                )
                ttime.sleep(exp_time)
                elapsed_time += exp_time
                if elapsed_time > buffer_time:
                    elapsed_time = 0
                    device.device_manager.producer.send(
                        MessageEndpoints.device_read(device.name), bundle.dumps()
                    )
                    bundle = messages.BundleMessage()
                    device.device_manager.producer.set_and_publish(
                        MessageEndpoints.device_status(device.name),
                        messages.DeviceStatusMessage(
                            device=device.name,
                            status=1,
                            metadata={"pointID": ii, **metadata},
                        ).dumps(),
                    )
            device.device_manager.producer.send(
                MessageEndpoints.device_read(device.name), bundle.dumps()
            )
            device.device_manager.producer.set_and_publish(
                MessageEndpoints.device_status(device.name),
                messages.DeviceStatusMessage(
                    device=device.name,
                    status=0,
                    metadata={"pointID": num_pos, **metadata},
                ).dumps(),
            )
            print("done")

        flyer = threading.Thread(target=produce_data, args=(self, metadata))
        flyer.start()


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
            st.set_finished()
        return st

    def stop(self, *, success=False):
        super().stop(success=success)
        self._stopped = True

    @property
    def position(self):
        return self.readback.get()

    def egu(self):
        return "mm"


class SynGaussBEC(Device):
    """
    Evaluate a point on a Gaussian based on the value of a motor.

    Parameters
    ----------
    name : string
    motor : Device
    motor_field : string
    center : number
        center of peak
    Imax : number
        max intensity of peak
    sigma : number, optional
        Default is 1.
    noise : {'poisson', 'uniform', None}, optional
        Add noise to the gaussian peak.
    noise_multiplier : float, optional
        Only relevant for 'uniform' noise. Multiply the random amount of
        noise by 'noise_multiplier'
    random_state : numpy random state object, optional
        np.random.RandomState(0), to generate random number with given seed

    Example
    -------
    motor = SynAxis(name='motor')
    det = SynGauss('det', motor, 'motor', center=0, Imax=1, sigma=1)
    """

    val = Cpt(_ReadbackSignalCompute, value=0, kind="hinted")
    Imax = Cpt(Signal, value=10, kind="config")
    center = Cpt(Signal, value=0, kind="config")
    sigma = Cpt(Signal, value=1, kind="config")
    motor = Cpt(Signal, value="samx", kind="config")
    noise = Cpt(
        EnumSignal,
        value="none",
        kind="config",
        enum_strings=("none", "poisson", "uniform"),
    )
    noise_multiplier = Cpt(Signal, value=1, kind="config")

    def __init__(self, name, *, device_manager=None, random_state=None, **kwargs):
        self.device_manager = device_manager
        set_later = {}
        for k in ("sigma", "noise", "noise_multiplier"):
            v = kwargs.pop(k, None)
            if v is not None:
                set_later[k] = v
        super().__init__(name=name, **kwargs)

        self.random_state = random_state or np.random
        self.val.name = self.name
        self.precision = 3
        self.sim_state = {"readback": 0, "readback_ts": ttime.time()}
        for k, v in set_later.items():
            getattr(self, k).put(v)

    def _compute(self):
        try:
            m = self.device_manager.devices[self.motor.get()].obj.read()[self.motor.get()]["value"]
            # we need to do this one at a time because
            #   - self.read() may be screwed with by the user
            #   - self.get() would cause infinite recursion
            Imax = self.Imax.get()
            center = self.center.get()
            sigma = self.sigma.get()
            noise = self.noise.get()
            noise_multiplier = self.noise_multiplier.get()
            v = Imax * np.exp(-((m - center) ** 2) / (2 * sigma**2))
            if noise == "poisson":
                v = int(self.random_state.poisson(np.round(v), 1))
            elif noise == "uniform":
                v += self.random_state.uniform(-1, 1) * noise_multiplier
            return v
        except Exception:
            return 0

    def get(self, *args, **kwargs):
        self.sim_state["readback"] = self._compute()
        self.sim_state["readback_ts"] = ttime.time()
        return self.val.get()


class SynDynamicComponents(Device):
    messages = Dcpt({f"message{i}": (SynSignal, None, {"name": f"msg{i}"}) for i in range(1, 6)})


class SynDeviceSubOPAAS(Device):
    zsub = Cpt(SynAxisOPAAS, name="zsub")


class SynDeviceOPAAS(Device):
    x = Cpt(SynAxisOPAAS, name="x")
    y = Cpt(SynAxisOPAAS, name="y")
    z = Cpt(SynDeviceSubOPAAS, name="z")


if __name__ == "__main__":
    det = SynSLSDetector(name="moench")
    det.trigger()
