"""Module for simulated monitor devices."""

import numpy as np
from bec_lib import messages
from bec_lib.endpoints import MessageEndpoints
from bec_lib.logger import bec_logger
from ophyd import Component as Cpt
from ophyd import Device, Kind, StatusBase

from ophyd_devices.interfaces.base_classes.psi_device_base import PSIDeviceBase
from ophyd_devices.sim.sim_data import SimulatedDataMonitor
from ophyd_devices.sim.sim_signals import ReadOnlySignal, SetableSignal
from ophyd_devices.utils import bec_utils

logger = bec_logger.logger


class SimMonitor(ReadOnlySignal):
    """
    A simulated device mimic any 1D Axis (position, temperature, beam).

    It's readback is a computed signal, which is configurable by the user and from the command line.
    The corresponding simulation class is sim_cls=SimulatedDataMonitor, more details on defaults
    within the simulation class.

    >>> monitor = SimMonitor(name="monitor")

    Parameters
    ----------
    name (string)           : Name of the device. This is the only required argmuent,
                              passed on to all signals of the device.
    precision (integer)     : Precision of the readback in digits, written to .describe().
                              Default is 3 digits.
    sim_init (dict)         : Dictionary to initiate parameters of the simulation,
                              check simulation type defaults for more details.
    parent                  : Parent device, optional, is used internally if this
                              signal/device is part of a larger device.
    kind                    : A member the Kind IntEnum (or equivalent integer), optional.
                              Default is Kind.normal. See Kind for options.
    device_manager          : DeviceManager from BEC, optional . Within startup of simulation,
                              device_manager is passed on automatically.

    """

    USER_ACCESS = ["sim", "registered_proxies"]

    sim_cls = SimulatedDataMonitor
    BIT_DEPTH = np.uint32

    def __init__(
        self,
        name,
        *,
        precision: int = 3,
        sim_init: dict = None,
        parent=None,
        kind: Kind = None,
        device_manager=None,
        **kwargs,
    ):
        self.precision = precision
        self.sim_init = sim_init
        self.device_manager = device_manager
        self.sim = self.sim_cls(parent=self, **kwargs)
        self._registered_proxies = {}

        super().__init__(
            name=name,
            parent=parent,
            kind=kind,
            value=self.BIT_DEPTH(0),
            compute_readback=True,
            sim=self.sim,
            **kwargs,
        )
        if self.sim_init:
            self.sim.set_init(self.sim_init)

    @property
    def registered_proxies(self) -> None:
        """Dictionary of registered signal_names and proxies."""
        return self._registered_proxies


class SimMonitorAsyncControl(Device):
    """SimMonitor Sync Control Device"""

    USER_ACCESS = ["sim", "registered_proxies", "async_update"]

    sim_cls = SimulatedDataMonitor
    BIT_DEPTH = np.uint32

    readback = Cpt(ReadOnlySignal, value=BIT_DEPTH(0), kind=Kind.hinted, compute_readback=True)
    current_trigger = Cpt(SetableSignal, value=BIT_DEPTH(0), kind=Kind.config)
    async_update = Cpt(SetableSignal, value="extend", kind=Kind.config)

    SUB_READBACK = "readback"
    SUB_PROGRESS = "progress"
    _default_sub = SUB_READBACK

    def __init__(self, name, *, sim_init: dict = None, parent=None, device_manager=None, **kwargs):
        if device_manager:
            self.device_manager = device_manager
        else:
            self.device_manager = bec_utils.DMMock()
        self.connector = self.device_manager.connector
        self.sim_init = sim_init
        self.sim = self.sim_cls(parent=self, **kwargs)
        self._registered_proxies = {}

        super().__init__(name=name, parent=parent, **kwargs)
        self.sim.sim_state[self.name] = self.sim.sim_state.pop(self.readback.name, None)
        self.readback.name = self.name
        self._data_buffer = {"value": [], "timestamp": []}
        if self.sim_init:
            self.sim.set_init(self.sim_init)

    @property
    def data_buffer(self) -> list:
        """Buffer for data to be sent asynchronously."""
        return self._data_buffer

    @property
    def registered_proxies(self) -> None:
        """Dictionary of registered signal_names and proxies."""
        return self._registered_proxies


class SimMonitorAsync(PSIDeviceBase, SimMonitorAsyncControl):
    """
    A simulated device to mimic the behaviour of an asynchronous monitor.

    During a scan, this device will send data not in sync with the point ID to BEC,
    but buffer data and send it in random intervals.s
    """

    def __init__(
        self, name: str, scan_info=None, parent: Device = None, device_manager=None, **kwargs
    ) -> None:
        super().__init__(
            name=name, scan_info=scan_info, parent=parent, device_manager=device_manager, **kwargs
        )
        self._stream_ttl = 1800
        self._random_send_interval = None
        self._counter = 0
        self.prep_random_interval()

    def on_connected(self):
        self.current_trigger.subscribe(self._progress_update, run=False)

    def clear_buffer(self):
        """Clear the data buffer."""
        self.data_buffer["value"].clear()
        self.data_buffer["timestamp"].clear()

    def prep_random_interval(self):
        """Prepare counter and random interval to send data to BEC."""
        self._random_send_interval = np.random.randint(1, 10)
        self.current_trigger.set(0).wait()
        self._counter = self.current_trigger.get()

    def on_stage(self):
        """Prepare the device for staging."""
        self.clear_buffer()
        self.prep_random_interval()

    def on_complete(self) -> StatusBase:
        """Prepare the device for completion."""

        def complete_action():
            if self.data_buffer["value"]:
                self._send_data_to_bec()

        status = self.task_handler.submit_task(complete_action)
        return status

    def _send_data_to_bec(self) -> None:
        """Sends bundled data to BEC"""
        async_update = self.async_update.get()
        if async_update not in ["extend", "append"]:
            raise ValueError(f"Invalid async_update value for device {self.name}: {async_update}")

        metadata = None
        if async_update == "extend":
            metadata = {"async_update": {"type": "add", "max_shape": [None]}}
        elif async_update == "append":
            metadata = {"async_update": {"type": "add", "max_shape": [None, None]}}

        msg = messages.DeviceMessage(
            signals={self.readback.name: self.data_buffer}, metadata=metadata
        )
        self.connector.xadd(
            MessageEndpoints.device_async_readback(
                scan_id=self.scan_info.msg.scan_id, device=self.name
            ),
            {"data": msg},
            expire=self._stream_ttl,
        )
        self.clear_buffer()

    def on_trigger(self):
        """Prepare the device for triggering."""

        def trigger_action():
            """Trigger actions"""
            self.data_buffer["value"].append(self.readback.get())
            self.data_buffer["timestamp"].append(self.readback.timestamp)
            self._counter += 1
            self.current_trigger.set(self._counter).wait()
            if self._counter % self._random_send_interval == 0:
                self._send_data_to_bec()

        status = self.task_handler.submit_task(trigger_action)
        return status

    def _progress_update(self, value: int, **kwargs):
        """Update the progress of the device."""
        max_value = self.scan_info.msg.num_points
        # pylint: disable=protected-access
        self._run_subs(
            sub_type=self.SUB_PROGRESS,
            value=value,
            max_value=max_value,
            done=bool(max_value == value),
        )

    def on_stop(self):
        """Stop the device."""
        self.task_handler.shutdown()
