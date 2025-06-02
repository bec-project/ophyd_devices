import threading
import time as ttime
import traceback

import numpy as np
from bec_lib import messages
from bec_lib.endpoints import MessageEndpoints
from bec_lib.logger import bec_logger
from ophyd import Component as Cpt
from ophyd import Device, DeviceStatus, Kind, OphydObject, PositionerBase, Staged

from ophyd_devices.sim.sim_camera import SimCamera
from ophyd_devices.sim.sim_positioner import SimPositioner
from ophyd_devices.sim.sim_signals import SetableSignal
from ophyd_devices.utils.bec_signals import (
    DynamicSignal,
    FileEventSignal,
    PreviewSignal,
    ProgressSignal,
)

logger = bec_logger.logger


class DummyControllerDevice(Device):
    USER_ACCESS = ["controller"]


class DummyController:
    USER_ACCESS = [
        "some_var",
        "some_var_property",
        "controller_show_all",
        "_func_with_args",
        "_func_with_args_and_kwargs",
        "_func_with_kwargs",
        "_func_without_args_kwargs",
    ]
    some_var = 10
    another_var = 20

    def __init__(self) -> None:
        self._some_var_property = None
        self.connected = False

    @property
    def some_var_property(self):
        return self._some_var_property

    def on(self):
        self.connected = True

    def off(self):
        self.connected = False

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


class SimDeviceWithStatusStageUnstage(Device):
    """SimDevice with stage and unstage methods that return a status object.

    Methods resolve once the stage_thread_event or unstage_thread_event is set.
    Stop always resolves immediately.
    """

    def __init__(self, name, **kwargs):
        super().__init__(name=name, **kwargs)
        self.stage_thread = None
        self.stage_thread_event = None
        self.stopped = False

    def stage(self) -> DeviceStatus:
        """Stage the device and return a status object."""
        self.stopped = False
        if self.stage_thread is not None:
            self.stage_thread_event.set()
            self.stage_thread.join()
        self.stage_thread_event = threading.Event()
        status = DeviceStatus(self)

        def stage_device(status: DeviceStatus):

            self.stage_thread_event.wait()

            if self.stopped is True:
                exc = RuntimeError(f"Device {self.name} was stopped")
                status.set_exception(exc)
            else:
                self._staged = Staged.yes
                status.set_finished()

        self.stage_thread = threading.Thread(target=stage_device, args=(status,))
        self.stage_thread.start()
        return status

    def unstage(self) -> DeviceStatus:
        """Unstage the device and return a status object."""
        self.stopped = False
        return super().unstage()

    def stop(self, success: bool = False):
        """Stop the device and set the stopped flag."""
        self.stopped = True
        if self.stage_thread_event:
            self.stage_thread_event.set()
        super().stop(success=success)


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
                            "flyer_samx": {"value": positions[ii, 0], "timestamp": 0},
                            "flyer_samy": {"value": positions[ii, 1], "timestamp": 0},
                        },
                        metadata={"point_id": ii, **metadata},
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
                            device=device.name, status=1, metadata={"point_id": ii, **metadata}
                        ),
                    )
            device.device_manager.connector.send(MessageEndpoints.device_read(device.name), bundle)
            device.device_manager.connector.set(
                MessageEndpoints.device_status(device.name),
                messages.DeviceStatusMessage(
                    device=device.name, status=0, metadata={"point_id": num_pos, **metadata}
                ),
            )
            print("done")

        flyer = threading.Thread(target=produce_data, args=(self, metadata))
        flyer.start()


class SimPositionerWithCommFailure(SimPositioner):
    fails = Cpt(SetableSignal, value=0)

    def move(self, value: float, **kwargs) -> DeviceStatus:
        if self.fails.get() == 1:
            raise RuntimeError("Communication failure")
        if self.fails.get() == 2:
            while not self._stopped:
                ttime.sleep(1)
            status = DeviceStatus(self)
            status.set_exception(RuntimeError("Communication failure"))
        return super().move(value, **kwargs)


class SimPositionerWithDescribeFailure(SimPositioner):
    """
    Simulated positioner that raises a RuntimeError if the 'e2e_test_<name>_fail' endpoint is set to 1 using
    a DeviceStatusMessage. This is used to test the behavior of the device when the describe method fails.
    """

    def __init__(self, *args, device_manager=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.device_manager = device_manager

    def _get_fail_state(self):
        msg = self.device_manager.connector.get(f"e2e_test_{self.name}_fail")
        if not msg:
            return 0
        return msg.status

    def describe(self):
        if self._get_fail_state() == 1:
            raise RuntimeError("Communication failure")
        return super().describe()


class SimPositionerWithController(SimPositioner):
    USER_ACCESS = ["sim", "readback", "dummy_controller", "registered_proxies"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.dummy_controller = DummyController()


class SimCameraWithStageStatus(SimCamera):
    """Simulated camera which returns a status object when staged.

    Note: This is a minimum implementation for test purposes without refactoring
    the super().stage() method. In theory, the super().stage() method should take
    into account a thread event to stop the staging process if the device is stopped.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.raise_on_stage = False
        if "raise_on_stage" in kwargs:
            self.raise_on_stage = kwargs.pop("raise_on_stage")

    def stage(self):
        status = DeviceStatus(self)

        def _stage_device(obj, status: DeviceStatus):
            """Start thread to stage the device"""
            try:
                logger.info(f"Staging device {obj.name} with status object")
                super(SimCamera, obj).stage()
                if obj.raise_on_stage is True:
                    raise RuntimeError(f"Error during staging in {obj.name}")
            # pylint: disable=broad-except
            except Exception as exc:
                content = traceback.format_exc()
                logger.warning(f"Error in staging of {obj.name}; Traceback: {content}")
                status.set_exception(exc=exc)
            else:
                status.set_finished()

        thread = threading.Thread(target=_stage_device, args=(self, status), daemon=True)
        thread.start()
        return status

    def unstage(self):
        status = DeviceStatus(self)

        def _unstage_device(obj, status: DeviceStatus):
            """Start thread to stage the device"""
            try:
                logger.info(f"Unstaging device {obj.name} with status object")
                super(SimCamera, obj).unstage()
                if obj.raise_on_stage is True:
                    raise RuntimeError(f"Error during unstaging in {obj.name}")
            # pylint: disable=broad-except
            except Exception as exc:
                content = traceback.format_exc()
                logger.warning(f"Error in unstaging of {obj.name}; Traceback: {content}")
                status.set_exception(exc=exc)
            else:
                status.set_finished()

        thread = threading.Thread(target=_unstage_device, args=(self, status), daemon=True)
        thread.start()
        return status


class SimCameraWithPSIComponents(SimCamera):
    """Test Device for PSIComponents"""

    preview_2d = Cpt(
        PreviewSignal, ndim=2, doc="2D preview signal", num_rotation_90=2, transpose=True
    )
    preview_1d = Cpt(PreviewSignal, ndim=1, doc="1D preview signal")
    file_event = Cpt(FileEventSignal, doc="File event signal")
    progress = Cpt(ProgressSignal, doc="Progress signal")
    dynamic_signal = Cpt(
        DynamicSignal, doc="Dynamic signals", signals=["dyn_signal1", "dyn_signal2"]
    )
    # TODO Handling of AsyncComponents is postponed, issue #104 is created

    # Define signals for the async components
    # signal_dict = {
    #     "signal1": {"kind": Kind.hinted, "doc": "Signal 1"},
    #     "signal2": {"kind": Kind.normal, "doc": "Signal 2"},
    #     "signal3": {"kind": Kind.config, "doc": "Signal 3"},
    #     "signal4": {"kind": Kind.omitted, "doc": "Signal 4"},
    # }

    # async_1d = Async1DComponent(doc="Async 1D signal", signal_def=signal_dict)
    # async_2d = Async2DComponent(doc="Async 2D signal", signal_def=signal_dict)

    def __init__(self, name: str, scan_info=None, device_manager=None, **kwargs):
        super().__init__(name=name, scan_info=scan_info, device_manager=device_manager, **kwargs)
        self._triggers_received = 0

    def on_stage(self):
        """Stage device"""
        self.file_path = self.file_utils.get_full_path(
            scan_status_msg=self.scan_info.msg, name=self.name
        )
        self.frames.set(
            self.scan_info.msg.num_points * self.scan_info.msg.scan_parameters["frames_per_trigger"]
        ).wait()
        self.exp_time.set(self.scan_info.msg.scan_parameters["exp_time"]).wait()
        self.burst.set(self.scan_info.msg.scan_parameters["frames_per_trigger"]).wait()
        # Always emit a file event
        msg = messages.FileMessage(
            file_path=self.file_path, done=False, successful=False, device_name=self.name
        )
        self.file_event.put(file_path=self.file_path, done=False, successful=False)
        self.file_event.set(msg).wait()
        self._triggers_received = 0

    def on_trigger(self):
        """Trigger device"""
        self._triggers_received += 1

        def trigger_cam():
            for _ in range(self.burst.get()):
                data = self.image.get()
                self.preview_2d.put(data)
                # sum array in one dimension
                self.preview_1d.put(np.sum(data, 1))
                self.dynamic_signal.put(
                    {"preview_2d": {"value": data}, "preview_1d": {"value": np.sum(data, 1)}}
                )
                progress = {
                    "value": self._triggers_received,
                    "max_value": self.scan_info.msg.num_points,
                    "done": (self._triggers_received == self.scan_info.msg.num_points),
                }
                progress = messages.ProgressMessage(**progress)
                self.progress.put(progress)
                self._set_async_signal()

        status = self.task_handler.submit_task(trigger_cam)
        return status

    def _set_async_signal(self, update_all: bool = False):
        """Set the async signal values.

        Args:
            update_all (bool): If True, update all signals. If False, update only hinted and normal signals.
        """
        # pylint: disable=protected-access
        for sig in self.async_1d._signals.values():
            if update_all is True:
                sig.put(np.random.random())
                continue
            if sig.kind in [Kind.hinted, Kind.normal]:
                sig.put(np.random.random())
        for sig in self.async_2d._signals.values():
            if update_all is True:
                sig.put(np.random.random())
                continue
            if sig.kind in [Kind.hinted, Kind.normal]:
                sig.put(np.random.random())

    def on_unstage(self):
        """Unstage device"""
        self._triggers_received = 0

    def on_complete(self):
        """Complete device"""

        def complete_cam():
            """Complete the camera acquisition."""
            msg = messages.FileMessage(
                file_path=self.file_path if self.file_path else "",
                done=True,
                successful=True,
                device_name=self.name,
            )
            self.file_event.set(msg).wait()
            progress = {
                "value": self._triggers_received,
                "max_value": self.scan_info.msg.num_points,
                "done": True,
            }
            progress = messages.ProgressMessage(**progress)
            self.progress.set(progress).wait()
            self._set_async_signal(update_all=True)

        status = self.task_handler.submit_task(complete_cam)
        return status


if __name__ == "__main__":
    cam = SimCameraWithPSIComponents(name="cam")
    cam.read()
