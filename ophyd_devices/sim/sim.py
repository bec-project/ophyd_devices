from collections import defaultdict
import os
import threading
import time as ttime
import warnings

import numpy as np
from bec_lib import MessageEndpoints, bec_logger, messages
from ophyd import Component as Cpt
from ophyd import Device, DeviceStatus, Kind
from ophyd import DynamicDeviceComponent as Dcpt
from ophyd import OphydObject, PositionerBase, Signal
from ophyd.sim import EnumSignal, SynSignal
from ophyd.utils import LimitError, ReadOnlyError
from ophyd_devices.sim.sim_data import SimulatedDataBase, SimulatedDataCamera, SimulatedDataMonitor

from ophyd_devices.sim.sim_signals import SetableSignal, ReadOnlySignal, ComputedReadOnlySignal

logger = bec_logger.logger


class DeviceStop(Exception):
    pass


class SimMonitor(Device):
    """
    A simulated device mimic any 1D Axis (position, temperature, beam).

    Readback functionality can be configured

    Parameters
    ----------
    name : string, keyword only
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

    USER_ACCESS = ["sim"]

    sim_cls = SimulatedDataMonitor

    readback = Cpt(ComputedReadOnlySignal, value=0, kind=Kind.hinted)

    SUB_READBACK = "readback"
    _default_sub = SUB_READBACK

    def __init__(
        self,
        *,
        name,
        value=0,
        delay=0,
        precision=3,
        tolerance: float = 0.5,
        sim_init: dict = None,
        parent=None,
        labels=None,
        kind=None,
        device_manager=None,
        **kwargs,
    ):
        self.delay = delay
        self.precision = precision
        self.tolerance = tolerance
        self.init_sim_params = sim_init
        self.sim = self.sim_cls(parent=self, device_manager=device_manager, **kwargs)

        super().__init__(name=name, parent=parent, labels=labels, kind=kind, **kwargs)
        self.sim.sim_state[self.name] = self.sim.sim_state.pop(self.readback.name, None)
        self.readback.name = self.name


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

    val = Cpt(ComputedReadOnlySignal, value=0, kind=Kind.hinted)
    Imax = Cpt(Signal, value=10, kind=Kind.config)
    center = Cpt(Signal, value=0, kind=Kind.config)
    sigma = Cpt(Signal, value=1, kind=Kind.config)
    motor = Cpt(Signal, value="samx", kind=Kind.config)
    noise = Cpt(
        EnumSignal,
        value="none",
        kind=Kind.config,
        enum_strings=("none", "poisson", "uniform"),
    )
    noise_multiplier = Cpt(Signal, value=1, kind=Kind.config)

    def __init__(self, name, *, device_manager=None, random_state=None, **kwargs):
        self.device_manager = device_manager
        set_later = {}
        for k in ("sigma", "noise", "noise_multiplier"):
            v = kwargs.pop(k, None)
            if v is not None:
                set_later[k] = v
        self.sim_state = defaultdict(lambda: {})
        super().__init__(name=name, **kwargs)
        self.sim_state[self.name] = self.sim_state.pop(self.val.name, None)
        self.val.name = self.name

        self.random_state = random_state or np.random
        self.precision = 3

        for k, v in set_later.items():
            getattr(self, k).put(v)

    def _compute_sim_state(self, signal_name: str) -> None:
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
            self.sim_state[signal_name]["value"] = v
            self.sim_state[signal_name]["timestamp"] = ttime.time()
        except Exception as exc:
            logger.warning(f"Failed to compute sim state with exception {exc}")
            self.sim_state[signal_name]["value"] = 0
            self.sim_state[signal_name]["timestamp"] = ttime.time()

    def get(self, *args, **kwargs):
        self.sim_state["readback"] = self._compute()
        self.sim_state["readback_ts"] = ttime.time()
        return self.val.get()


class _SLSDetectorConfigSignal(Signal):
    def put(self, value, *, timestamp=None, force=False):
        self._readback = value
        self.parent.sim_state[self.name] = value

    def get(self):
        self._readback = self.parent.sim_state[self.name]
        return self.parent.sim_state[self.name]


class SimCamera(Device):
    USER_ACCESS = ["sim"]

    sim_cls = SimulatedDataCamera
    SHAPE = (100, 100)

    SUB_MONITOR = "monitor"
    _default_sub = SUB_MONITOR

    exp_time = Cpt(SetableSignal, name="exp_time", value=1, kind=Kind.config)
    file_path = Cpt(SetableSignal, name="file_path", value="", kind=Kind.config)
    file_pattern = Cpt(SetableSignal, name="file_pattern", value="", kind=Kind.config)
    frames = Cpt(SetableSignal, name="frames", value=1, kind=Kind.config)
    burst = Cpt(SetableSignal, name="burst", value=1, kind=Kind.config)
    save_file = Cpt(SetableSignal, name="save_file", value=False, kind=Kind.config)

    # image shape, only adjustable via config.
    image_shape = Cpt(SetableSignal, name="image_shape", value=SHAPE, kind=Kind.config)
    image = Cpt(
        ComputedReadOnlySignal,
        name="image",
        value=np.empty(SHAPE, dtype=np.uint16),
        kind=Kind.omitted,
    )

    def __init__(
        self,
        *,
        name,
        kind=None,
        parent=None,
        sim_init: dict = None,
        device_manager=None,
        **kwargs,
    ):
        self.device_manager = device_manager
        self.init_sim_params = sim_init
        self.sim = self.sim_cls(parent=self, device_manager=device_manager, **kwargs)

        super().__init__(name=name, parent=parent, kind=kind, **kwargs)
        self._stopped = False
        self.file_name = ""
        self.metadata = {}

    def trigger(self):
        status = DeviceStatus(self)

        self.subscribe(status._finished, event_type=self.SUB_ACQ_DONE, run=False)

        def acquire():
            try:
                for _ in range(self.burst.get()):
                    # Send data for each trigger
                    self._run_subs(sub_type=self.SUB_MONITOR, value=self.image.get())
                    if self._stopped:
                        raise DeviceStop
            except DeviceStop:
                pass
            finally:
                self._stopped = False
                self._done_acquiring()

        threading.Thread(target=acquire, daemon=True).start()
        return status

    def stage(self) -> list[object]:
        """Stage the camera

        Receive scan message from REDIS first, extract relevant scan data,
        and set all signals for the scan, e.g. scan_number, file_name, frames, etc.
        """
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
        self._stopped = False
        return super().stage()

    def _send_data_to_bec(self) -> None:
        config_readout = {
            signal.item.name: signal.item.get()
            for signal in self.walk_signals()
            if signal.item._kind == Kind.config
        }

        signals = {"config": config_readout, "data": self.file_name}
        msg = messages.DeviceMessage(signals=signals, metadata=self.metadata)
        self.device_manager.producer.set_and_publish(
            MessageEndpoints.device_read(self.name), msg.dumps()
        )

    def unstage(self) -> list[object]:
        """Unstage the device

        Send reads from all config signals to redis
        """
        if self._stopped is True or not self._staged:
            return super().unstage()
        self._send_data_to_bec()

        return super().unstage()

    def stop(self, *, success=False):
        self._stopped = True
        super().stop(success=success)


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


class SimPositioner(Device, PositionerBase):
    """
    A simulated device mimicing any 1D Axis device (position, temperature, rotation).

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

    # Specify which attributes are accessible via BEC client
    USER_ACCESS = ["sim", "readback", "speed", "dummy_controller"]

    sim_cls = SimulatedDataBase

    # Define the signals as class attributes
    readback = Cpt(ReadOnlySignal, name="readback", value=0, kind=Kind.hinted)
    setpoint = Cpt(SetableSignal, value=0, kind=Kind.normal)
    motor_is_moving = Cpt(SetableSignal, value=0, kind=Kind.normal)

    # Config signals
    velocity = Cpt(SetableSignal, value=1, kind=Kind.config)
    acceleration = Cpt(SetableSignal, value=1, kind=Kind.config)

    # Ommitted signals
    high_limit_travel = Cpt(SetableSignal, value=0, kind=Kind.omitted)
    low_limit_travel = Cpt(SetableSignal, value=0, kind=Kind.omitted)
    unused = Cpt(Signal, value=1, kind=Kind.omitted)

    # TODO add short description to these two lines and explain what this does
    SUB_READBACK = "readback"
    _default_sub = SUB_READBACK

    def __init__(
        self,
        *,
        name,
        readback_func=None,
        value=0,
        delay=1,
        speed=1,
        update_frequency=2,
        precision=3,
        parent=None,
        labels=None,
        kind=None,
        limits=None,
        tolerance: float = 0.5,
        sim: dict = None,
        **kwargs,
    ):
        # Whether motions should be instantaneous or depend on motor velocity
        self.delay = delay
        self.precision = precision
        self.tolerance = tolerance
        self.init_sim_params = sim

        self.speed = speed
        self.update_frequency = update_frequency
        self._stopped = False
        self.dummy_controller = DummyController()

        # initialize inner dictionary with simulated state
        self.sim = self.sim_cls(parent=self, **kwargs)

        super().__init__(name=name, labels=labels, kind=kind, **kwargs)
        # Rename self.readback.name to self.name, also in self.sim_state
        self.sim.sim_state[self.name] = self.sim.sim_state.pop(self.readback.name, None)
        self.readback.name = self.name
        # Init limits from deviceConfig
        if limits is not None:
            assert len(limits) == 2
            self.low_limit_travel.put(limits[0])
            self.high_limit_travel.put(limits[1])

    @property
    def limits(self):
        """Return the limits of the simulated device."""
        return (self.low_limit_travel.get(), self.high_limit_travel.get())

    @property
    def low_limit(self):
        """Return the low limit of the simulated device."""
        return self.limits[0]

    @property
    def high_limit(self):
        """Return the high limit of the simulated device."""
        return self.limits[1]

    def check_value(self, value: any):
        """
        Check that requested position is within existing limits.

        This function has to be implemented on the top level of the positioner.
        """
        low_limit, high_limit = self.limits

        if low_limit < high_limit and not low_limit <= value <= high_limit:
            raise LimitError(f"position={value} not within limits {self.limits}")

    def _set_sim_state(self, signal_name: str, value: any) -> None:
        """Update the simulated state of the device."""
        self.sim.sim_state[signal_name]["value"] = value
        self.sim.sim_state[signal_name]["timestamp"] = ttime.time()

    def _get_sim_state(self, signal_name: str) -> any:
        """Return the simulated state of the device."""
        return self.sim.sim_state[signal_name]["value"]

    def move(self, value: float, **kwargs) -> DeviceStatus:
        """Change the setpoint of the simulated device, and simultaneously initiated a motion."""
        self._stopped = False
        self.check_value(value)
        old_setpoint = self._get_sim_state(self.setpoint.name)
        self._set_sim_state(self.motor_is_moving.name, 1)
        self._set_sim_state(self.setpoint.name, value)

        def update_state(val):
            """Update the state of the simulated device."""
            if self._stopped:
                raise DeviceStop
            old_readback = self._get_sim_state(self.readback.name)
            self._set_sim_state(self.readback.name, val)

            # Run subscription on "readback"
            self._run_subs(
                sub_type=self.SUB_READBACK,
                old_value=old_readback,
                value=self.sim.sim_state[self.readback.name]["value"],
                timestamp=self.sim.sim_state[self.readback.name]["timestamp"],
            )

        st = DeviceStatus(device=self)
        if self.delay:
            # If self.delay is not 0, we use the speed and updated frequency of the device to compute the motion
            def move_and_finish():
                """Move the simulated device and finish the motion."""
                success = True
                try:
                    # Compute final position with some jitter
                    move_val = self._get_sim_state(
                        self.setpoint.name
                    ) + self.tolerance * np.random.uniform(-1, 1)
                    # Compute the number of updates needed to reach the final position with the given speed
                    updates = np.ceil(
                        np.abs(old_setpoint - move_val) / self.speed * self.update_frequency
                    )
                    # Loop over the updates and update the state of the simulated device
                    for ii in np.linspace(old_setpoint, move_val, int(updates)):
                        ttime.sleep(1 / self.update_frequency)
                        update_state(ii)
                    # Update the state of the simulated device to the final position
                    update_state(move_val)
                    self._set_sim_state(self.motor_is_moving, 0)
                except DeviceStop:
                    success = False
                finally:
                    self._stopped = False
                # Call function from positioner base to indicate that motion finished with success
                self._done_moving(success=success)
                # Set status to finished
                st.set_finished()

            # Start motion in Thread
            threading.Thread(target=move_and_finish, daemon=True).start()

        else:
            # If self.delay is 0, we move the simulated device instantaneously
            update_state(value)
            self._done_moving()
            st.set_finished()
        return st

    def stop(self, *, success=False):
        """Stop the motion of the simulated device."""
        super().stop(success=success)
        self._stopped = True

    @property
    def position(self):
        """Return the current position of the simulated device."""
        return self.readback.get()

    @property
    def egu(self):
        """Return the engineering units of the simulated device."""
        return "mm"


class SynDynamicComponents(Device):
    messages = Dcpt({f"message{i}": (SynSignal, None, {"name": f"msg{i}"}) for i in range(1, 6)})


class SynDeviceSubOPAAS(Device):
    zsub = Cpt(SimPositioner, name="zsub")


class SynDeviceOPAAS(Device):
    x = Cpt(SimPositioner, name="x")
    y = Cpt(SimPositioner, name="y")
    z = Cpt(SynDeviceSubOPAAS, name="z")


if __name__ == "__main__":
    gauss = SynGaussBEC(name="gauss")
