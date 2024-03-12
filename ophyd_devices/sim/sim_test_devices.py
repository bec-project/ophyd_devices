import threading
import time as ttime

import numpy as np
from bec_lib import MessageEndpoints, messages
from ophyd import Device, OphydObject, PositionerBase


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
                            "syn_flyer_lamni": {
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
            device.device_manager.connector.send(MessageEndpoints.device_read(device.name), bundle)
            device.device_manager.connector.set(
                MessageEndpoints.device_status(device.name),
                messages.DeviceStatusMessage(
                    device=device.name, status=0, metadata={"pointID": num_pos, **metadata}
                ),
            )
            print("done")

        flyer = threading.Thread(target=produce_data, args=(self, metadata))
        flyer.start()
