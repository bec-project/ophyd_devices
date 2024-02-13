import os
import threading
import time as ttime
import warnings

import numpy as np
from bec_lib import MessageEndpoints, bec_logger, messages
from ophyd import Component as Cpt
from ophyd import DynamicDeviceComponent as Dcpt
from ophyd import Device, DeviceStatus, Kind
from ophyd import PositionerBase, Signal
from ophyd.sim import SynSignal

from ophyd.utils import LimitError
from ophyd_devices.utils.bec_scaninfo_mixin import BecScaninfoMixin
from ophyd_devices.sim.sim_data import SimulatedDataBase, SimulatedDataCamera, SimulatedDataMonitor
from ophyd_devices.sim.sim_test_devices import DummyController

from ophyd_devices.sim.sim_signals import SetableSignal, ReadOnlySignal, ComputedReadOnlySignal

logger = bec_logger.logger


class DeviceStop(Exception):
    pass


class SimMonitor(Device):
    """
    A simulated device mimic any 1D Axis (position, temperature, beam).

    It's readback is a computed signal, which is configurable by the user and from the command line.
    The corresponding simulation class is sim_cls=SimulatedDataMonitor, more details on defaults within the simulation class.

    >>> monitor = SimMonitor(name="monitor")

    Parameters
    ----------
    name (string)           : Name of the device. This is the only required argmuent, passed on to all signals of the device.
    precision (integer)     : Precision of the readback in digits, written to .describe(). Default is 3 digits.
    sim_init (dict)         : Dictionary to initiate parameters of the simulation, check simulation type defaults for more details.
    parent                  : Parent device, optional, is used internally if this signal/device is part of a larger device.
    kind                    : A member the Kind IntEnum (or equivalent integer), optional. Default is Kind.normal. See Kind for options.
    device_manager          : DeviceManager from BEC, optional . Within startup of simulation, device_manager is passed on automatically.

    """

    USER_ACCESS = ["sim"]

    sim_cls = SimulatedDataMonitor

    readback = Cpt(ComputedReadOnlySignal, value=0, kind=Kind.hinted)

    SUB_READBACK = "readback"
    _default_sub = SUB_READBACK

    def __init__(
        self,
        name,
        *,
        precision: int = 3,
        sim_init: dict = None,
        parent=None,
        kind=None,
        device_manager=None,
        **kwargs,
    ):
        self.precision = precision
        self.init_sim_params = sim_init
        self.sim = self.sim_cls(parent=self, device_manager=device_manager, **kwargs)

        super().__init__(name=name, parent=parent, kind=kind, **kwargs)
        self.sim.sim_state[self.name] = self.sim.sim_state.pop(self.readback.name, None)
        self.readback.name = self.name


class SimCamera(Device):
    """A simulated device mimic any 2D camera.

    It's image is a computed signal, which is configurable by the user and from the command line.
    The corresponding simulation class is sim_cls=SimulatedDataCamera, more details on defaults within the simulation class.

    >>> camera = SimCamera(name="camera")

    Parameters
    ----------
    name (string)           : Name of the device. This is the only required argmuent, passed on to all signals of the device.
    precision (integer)     : Precision of the readback in digits, written to .describe(). Default is 3 digits.
    sim_init (dict)         : Dictionary to initiate parameters of the simulation, check simulation type defaults for more details.
    parent                  : Parent device, optional, is used internally if this signal/device is part of a larger device.
    kind                    : A member the Kind IntEnum (or equivalent integer), optional. Default is Kind.normal. See Kind for options.
    device_manager          : DeviceManager from BEC, optional . Within startup of simulation, device_manager is passed on automatically.

    """

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

    image_shape = Cpt(SetableSignal, name="image_shape", value=SHAPE, kind=Kind.config)
    image = Cpt(
        ComputedReadOnlySignal,
        name="image",
        value=np.empty(SHAPE, dtype=np.uint16),
        kind=Kind.omitted,
    )

    def __init__(
        self,
        name,
        *,
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
        self._staged = False
        self.scaninfo = None
        self._update_scaninfo()

    def trigger(self) -> DeviceStatus:
        """Trigger the camera to acquire images.

        This method can be called from BEC during a scan. It will acquire images and send them to BEC.
        Whether the trigger is send from BEC is determined by the softwareTrigger argument in the device config.

        Here, we also run a callback on SUB_MONITOR to send the image data the device_monitor endpoint in BEC.
        """
        status = DeviceStatus(self)

        self.subscribe(status._finished, event_type=self.SUB_ACQ_DONE, run=False)

        def acquire():
            try:
                for _ in range(self.burst.get()):
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

    def _update_scaninfo(self) -> None:
        """Update scaninfo from BecScaninfoMixing
        This depends on device manager and operation/sim_mode
        """
        self.scaninfo = BecScaninfoMixin(self.device_manager)

    def stage(self) -> list[object]:
        """Stage the camera for upcoming scan

        This method is called from BEC in preparation of a scan.
        It receives metadata about the scan from BEC,
        compiles it and prepares the camera for the scan.

        FYI: No data is written to disk in the simulation, but upon each trigger it
        is published to the device_monitor endpoint in REDIS.
        """
        if self._staged:
            return super().stage()
        self.scaninfo.load_scan_metadata()
        self.file_path.set(
            os.path.join(
                self.file_path.get(), self.file_pattern.get().format(self.scaninfo.scan_number)
            )
        )
        self.frames.set(self.scaninfo.num_points * self.scaninfo.frames_per_trigger)
        self.exp_time.set(self.scaninfo.exp_time)
        self.burst.set(self.scaninfo.frames_per_trigger)
        self._stopped = False
        return super().stage()

    def unstage(self) -> list[object]:
        """Unstage the device

        Send reads from all config signals to redis
        """
        if self._stopped is True or not self._staged:
            return super().unstage()

        return super().unstage()

    def stop(self, *, success=False):
        """Stop the device"""
        self._stopped = True
        super().stop(success=success)


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


class SynDynamicComponents(Device):
    messages = Dcpt({f"message{i}": (SynSignal, None, {"name": f"msg{i}"}) for i in range(1, 6)})


class SynDeviceSubOPAAS(Device):
    zsub = Cpt(SimPositioner, name="zsub")


class SynDeviceOPAAS(Device):
    x = Cpt(SimPositioner, name="x")
    y = Cpt(SimPositioner, name="y")
    z = Cpt(SimPositioner, name="z")
