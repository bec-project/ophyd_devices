import os
import threading
import time as ttime

import numpy as np
from bec_lib import MessageEndpoints, bec_logger, messages
from ophyd import Component as Cpt
from ophyd import Device, DeviceStatus
from ophyd import DynamicDeviceComponent as Dcpt
from ophyd import Kind, PositionerBase
from ophyd.flyers import FlyerInterface
from ophyd.sim import SynSignal
from ophyd.status import StatusBase
from ophyd.utils import LimitError

from ophyd_devices.sim.sim_data import (
    SimulatedDataCamera,
    SimulatedDataMonitor,
    SimulatedPositioner,
)
from ophyd_devices.sim.sim_signals import ReadOnlySignal, SetableSignal
from ophyd_devices.sim.sim_test_devices import DummyController
from ophyd_devices.utils.bec_scaninfo_mixin import BecScaninfoMixin

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

    USER_ACCESS = ["sim", "registered_proxies"]

    sim_cls = SimulatedDataMonitor
    BIT_DEPTH = np.uint32

    readback = Cpt(ReadOnlySignal, value=BIT_DEPTH(0), kind=Kind.hinted, compute_readback=True)

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
        self._registered_proxies = {}

        super().__init__(name=name, parent=parent, kind=kind, **kwargs)
        self.sim.sim_state[self.name] = self.sim.sim_state.pop(self.readback.name, None)
        self.readback.name = self.name

    @property
    def registered_proxies(self) -> None:
        """Dictionary of registered signal_names and proxies."""
        return self._registered_proxies


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

    USER_ACCESS = ["sim", "registered_proxies"]

    sim_cls = SimulatedDataCamera
    SHAPE = (100, 100)
    BIT_DEPTH = np.uint16

    SUB_MONITOR = "monitor"
    _default_sub = SUB_MONITOR

    exp_time = Cpt(SetableSignal, name="exp_time", value=1, kind=Kind.config)
    file_path = Cpt(SetableSignal, name="file_path", value="", kind=Kind.config)
    file_pattern = Cpt(SetableSignal, name="file_pattern", value="", kind=Kind.config)
    frames = Cpt(SetableSignal, name="frames", value=1, kind=Kind.config)
    burst = Cpt(SetableSignal, name="burst", value=1, kind=Kind.config)

    image_shape = Cpt(SetableSignal, name="image_shape", value=SHAPE, kind=Kind.config)
    image = Cpt(
        ReadOnlySignal,
        name="image",
        value=np.empty(SHAPE, dtype=BIT_DEPTH),
        compute_readback=True,
        kind=Kind.omitted,
    )

    def __init__(
        self, name, *, kind=None, parent=None, sim_init: dict = None, device_manager=None, **kwargs
    ):
        self.device_manager = device_manager
        self.init_sim_params = sim_init
        self._registered_proxies = {}
        self.sim = self.sim_cls(parent=self, device_manager=device_manager, **kwargs)

        super().__init__(name=name, parent=parent, kind=kind, **kwargs)
        self._stopped = False
        self._staged = False
        self.scaninfo = None
        self._update_scaninfo()

    @property
    def registered_proxies(self) -> None:
        """Dictionary of registered signal_names and proxies."""
        return self._registered_proxies

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

    >>> motor = SimPositioner(name="motor")

    Parameters
    ----------
    name (string)           : Name of the device. This is the only required argmuent, passed on to all signals of the device.\
    Optional parameters:
    ----------
    delay (int)             : If 0, execution of move will be instant. If 1, exectution will depend on motor velocity. Default is 1.
    update_frequency (int)  : Frequency in Hz of the update of the simulated state during a move. Default is 2 Hz.
    precision (integer)     : Precision of the readback in digits, written to .describe(). Default is 3 digits.
    tolerance (float)       : Tolerance of the positioner to accept reaching target positions. Default is 0.5.
    limits (tuple)          : Tuple of the low and high limits of the positioner. Overrides low/high_limit_travel is specified. Default is None.
    parent                  : Parent device, optional, is used internally if this signal/device is part of a larger device.
    kind                    : A member the Kind IntEnum (or equivalent integer), optional. Default is Kind.normal. See Kind for options.
    device_manager          : DeviceManager from BEC, optional . Within startup of simulation, device_manager is passed on automatically.
    sim_init (dict)         : Dictionary to initiate parameters of the simulation, check simulation type defaults for more details.

    """

    # Specify which attributes are accessible via BEC client
    USER_ACCESS = ["sim", "readback", "speed", "dummy_controller", "registered_proxies"]

    sim_cls = SimulatedPositioner

    # Define the signals as class attributes
    readback = Cpt(ReadOnlySignal, name="readback", value=0, kind=Kind.hinted)
    setpoint = Cpt(SetableSignal, value=0, kind=Kind.normal)
    motor_is_moving = Cpt(SetableSignal, value=0, kind=Kind.normal)

    # Config signals
    velocity = Cpt(SetableSignal, value=100, kind=Kind.config)
    acceleration = Cpt(SetableSignal, value=1, kind=Kind.config)

    # Ommitted signals
    high_limit_travel = Cpt(SetableSignal, value=0, kind=Kind.omitted)
    low_limit_travel = Cpt(SetableSignal, value=0, kind=Kind.omitted)
    unused = Cpt(SetableSignal, value=1, kind=Kind.omitted)

    SUB_READBACK = "readback"
    _default_sub = SUB_READBACK

    # pylint: disable=too-many-arguments
    def __init__(
        self,
        name,
        *,
        delay: int = 1,
        update_frequency=2,
        precision=3,
        tolerance: float = 0.5,
        limits=None,
        parent=None,
        kind=None,
        device_manager=None,
        sim_init: dict = None,
        # TODO remove after refactoring config
        speed: float = 100,
        **kwargs,
    ):
        self.delay = delay
        self.device_manager = device_manager
        self.precision = precision
        self.tolerance = tolerance
        self.init_sim_params = sim_init
        self._registered_proxies = {}

        self.update_frequency = update_frequency
        self._stopped = False
        self.dummy_controller = DummyController()

        self.sim = self.sim_cls(parent=self, **kwargs)

        super().__init__(name=name, parent=parent, kind=kind, **kwargs)
        self.sim.sim_state[self.name] = self.sim.sim_state.pop(self.readback.name, None)
        self.readback.name = self.name
        if limits is not None:
            assert len(limits) == 2
            self.low_limit_travel.put(limits[0])
            self.high_limit_travel.put(limits[1])

    # @property
    # def connected(self):
    #     """Return the connected state of the simulated device."""
    #     return self.dummy_controller.connected

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

    def registered_proxies(self) -> None:
        """Dictionary of registered signal_names and proxies."""
        return self._registered_proxies

    # pylint: disable=arguments-differ
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

            def move_and_finish():
                """Move the simulated device and finish the motion."""
                success = True
                try:
                    move_val = self._get_sim_state(
                        self.setpoint.name
                    ) + self.tolerance * np.random.uniform(-1, 1)

                    updates = np.ceil(
                        np.abs(old_setpoint - move_val)
                        / self.velocity.get()
                        * self.update_frequency
                    )

                    for ii in np.linspace(old_setpoint, move_val, int(updates)):
                        ttime.sleep(1 / self.update_frequency)
                        update_state(ii)

                    update_state(move_val)
                    self._set_sim_state(self.motor_is_moving, 0)
                except DeviceStop:
                    success = False
                finally:
                    self._stopped = False
                self._done_moving(success=success)
                self._set_sim_state(self.motor_is_moving.name, 0)
                st.set_finished()

            threading.Thread(target=move_and_finish, daemon=True).start()

        else:
            update_state(value)
            self._done_moving()
            self._set_sim_state(self.motor_is_moving.name, 0)
            st.set_finished()
        return st

    def stop(self, *, success=False):
        """Stop the motion of the simulated device."""
        super().stop(success=success)
        self._stopped = True

    @property
    def position(self) -> float:
        """Return the current position of the simulated device."""
        return self.readback.get()

    @property
    def egu(self):
        """Return the engineering units of the simulated device."""
        return "mm"


class SimFlyer(Device, PositionerBase, FlyerInterface):
    """A simulated device mimicing any 2D Flyer device (position, temperature, rotation).

    The corresponding simulation class is sim_cls=SimulatedPositioner, more details on defaults within the simulation class.

    >>> flyer = SimFlyer(name="flyer")

    Parameters
    ----------
    name (string)           : Name of the device. This is the only required argmuent, passed on to all signals of the device.
    precision (integer)     : Precision of the readback in digits, written to .describe(). Default is 3 digits.
    parent                  : Parent device, optional, is used internally if this signal/device is part of a larger device.
    kind                    : A member the Kind IntEnum (or equivalent integer), optional. Default is Kind.normal. See Kind for options.
    device_manager          : DeviceManager from BEC, optional . Within startup of simulation, device_manager is passed on automatically.
    """

    USER_ACCESS = ["sim", "registered_proxies"]

    sim_cls = SimulatedPositioner

    readback = Cpt(
        ReadOnlySignal, name="readback", value=0, kind=Kind.hinted, compute_readback=False
    )

    def __init__(
        self,
        name: str,
        *,
        precision: int = 3,
        parent=None,
        kind=None,
        device_manager=None,
        # TODO remove after refactoring config
        speed: float = 100,
        delay: int = 1,
        update_frequency: int = 100,
        **kwargs,
    ):

        self.sim = self.sim_cls(parent=self, device_manager=device_manager, **kwargs)
        self.precision = precision
        self.device_manager = device_manager
        self._registered_proxies = {}

        super().__init__(name=name, parent=parent, kind=kind, **kwargs)
        self.sim.sim_state[self.name] = self.sim.sim_state.pop(self.readback.name, None)
        self.readback.name = self.name

    @property
    def registered_proxies(self) -> None:
        """Dictionary of registered signal_names and proxies."""
        return self._registered_proxies

    @property
    def hints(self):
        """Return the hints of the simulated device."""
        return {"fields": ["flyer_samx", "flyer_samy"]}

    @property
    def egu(self) -> str:
        """Return the engineering units of the simulated device."""
        return "mm"

    def complete(self) -> StatusBase:
        """Complete the motion of the simulated device."""
        status = DeviceStatus(self)
        status.set_finished()
        return status

    def kickoff(self, metadata, num_pos, positions, exp_time: float = 0):
        """Kickoff the flyer to execute code during the scan."""
        positions = np.asarray(positions)

        def produce_data(device, metadata):
            """Simulate the data being produced by the flyer."""
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
                    )
                )
                ttime.sleep(exp_time)
                elapsed_time += exp_time
                if elapsed_time > buffer_time:
                    elapsed_time = 0
                    device.device_manager.connector.set_and_publish(
                        MessageEndpoints.device_read(device.name), bundle
                    )
                    bundle = messages.BundleMessage()
                    device.device_manager.connector.set(
                        MessageEndpoints.device_status(device.name),
                        messages.DeviceStatusMessage(
                            device=device.name, status=1, metadata={"pointID": ii, **metadata}
                        ),
                    )
            device.device_manager.connector.set_and_publish(
                MessageEndpoints.device_read(device.name), bundle
            )
            device.device_manager.connector.set(
                MessageEndpoints.device_status(device.name),
                messages.DeviceStatusMessage(
                    device=device.name, status=0, metadata={"pointID": num_pos, **metadata}
                ),
            )
            print("done")

        flyer = threading.Thread(target=produce_data, args=(self, metadata))
        flyer.start()


class SynDeviceSubOPAAS(Device):
    zsub = Cpt(SimPositioner, name="zsub")


class SynDeviceOPAAS(Device):
    x = Cpt(SimPositioner, name="x")
    y = Cpt(SimPositioner, name="y")
    z = Cpt(SynDeviceSubOPAAS, name="z")


class SynDynamicComponents(Device):
    messages = Dcpt({f"message{i}": (SynSignal, None, {"name": f"msg{i}"}) for i in range(1, 6)})


if __name__ == "__main__":
    cam = SimCamera(name="cam")
    cam.image.read()
