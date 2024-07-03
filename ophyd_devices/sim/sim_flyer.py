import threading
import time

import numpy as np
from bec_lib import messages
from bec_lib.endpoints import MessageEndpoints
from bec_lib.logger import bec_logger
from ophyd import Component as Cpt
from ophyd import Device, DeviceStatus, Kind
from ophyd.flyers import FlyerInterface
from ophyd.status import StatusBase

from ophyd_devices.sim.sim_data import SimulatedPositioner
from ophyd_devices.sim.sim_signals import ReadOnlySignal

logger = bec_logger.logger


class SimFlyer(Device, FlyerInterface):
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
        sim_init: dict = None,
        # TODO remove after refactoring config
        delay: int = 1,
        update_frequency: int = 100,
        **kwargs,
    ):

        self.sim = self.sim_cls(parent=self, **kwargs)
        self.sim_init = sim_init
        self.precision = precision
        self.device_manager = device_manager
        self._registered_proxies = {}

        super().__init__(name=name, parent=parent, kind=kind, **kwargs)
        self.sim.sim_state[self.name] = self.sim.sim_state.pop(self.readback.name, None)
        self.readback.name = self.name
        if self.sim_init:
            self.sim.set_init(self.sim_init)

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
                            "flyer_samx": {"value": positions[ii, 0], "timestamp": 0},
                            "flyer_samy": {"value": positions[ii, 1], "timestamp": 0},
                        },
                        metadata={"point_id": ii, **metadata},
                    )
                )
                time.sleep(exp_time)
                elapsed_time += exp_time
                if elapsed_time > buffer_time:
                    elapsed_time = 0
                    logger.info(f"Sending data point {ii} for {device.name}.")
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
            device.device_manager.connector.set_and_publish(
                MessageEndpoints.device_read(device.name), bundle
            )
            device.device_manager.connector.set(
                MessageEndpoints.device_status(device.name),
                messages.DeviceStatusMessage(
                    device=device.name, status=0, metadata={"point_id": num_pos, **metadata}
                ),
            )
            print("done")

        flyer = threading.Thread(target=produce_data, args=(self, metadata))
        flyer.start()
