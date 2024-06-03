"""This module provides an asynchronous monitor to simulate the behaviour of a device sending data not in sync with the point ID."""

from typing import Literal

import numpy as np
from bec_lib import messages
from bec_lib.endpoints import MessageEndpoints
from ophyd import Component as Cpt
from ophyd import Device, Kind
from typeguard import typechecked

from ophyd_devices.interfaces.base_classes.psi_detector_base import (
    CustomDetectorMixin,
    PSIDetectorBase,
)
from ophyd_devices.sim.sim_data import SimulatedDataMonitor
from ophyd_devices.sim.sim_signals import ReadOnlySignal, SetableSignal


class SimMonitorAsyncPrepare(CustomDetectorMixin):
    """Custom prepare for the SimMonitorAsync class."""

    def __init__(self, *args, parent: Device = None, **kwargs) -> None:
        super().__init__(*args, parent=parent, **kwargs)
        self._stream_ttl = 1800
        self._random_send_interval = None
        self._counter = 0
        self.prep_random_interval()

    def clear_buffer(self):
        """Clear the data buffer."""
        self.parent.data_buffer["value"].clear()
        self.parent.data_buffer["timestamp"].clear()

    def prep_random_interval(self):
        """Prepare counter and random interval to send data to BEC."""
        self._random_send_interval = np.random.randint(1, 10)
        self.parent.current_trigger.set(0).wait()
        self._counter = self.parent.current_trigger.get()

    def on_stage(self):
        """Prepare the device for staging."""
        self.clear_buffer()
        self.prep_random_interval()
        self.parent.current_trigger.subscribe(self._progress_update, run=False)

    def on_complete(self):
        """Prepare the device for completion."""
        if self.parent.data_buffer["value"]:
            self._send_data_to_bec()

    def _send_data_to_bec(self) -> None:
        """Sends bundled data to BEC"""
        if self.parent.scaninfo.scan_msg is None:
            return
        metadata = self.parent.scaninfo.scan_msg.metadata
        metadata.update({"async_update": self.parent.async_update})

        msg = messages.DeviceMessage(
            signals={self.parent.readback.name: self.parent.data_buffer},
            metadata=self.parent.scaninfo.scan_msg.metadata,
        )
        self.parent.connector.xadd(
            MessageEndpoints.device_async_readback(
                scan_id=self.parent.scaninfo.scan_id, device=self.parent.name
            ),
            {"data": msg},
            expire=self._stream_ttl,
        )
        self.clear_buffer()

    def on_trigger(self):
        """Prepare the device for triggering."""
        self.parent.data_buffer["value"].append(self.parent.readback.get())
        self.parent.data_buffer["timestamp"].append(self.parent.readback.timestamp)
        self._counter += 1
        self.parent.current_trigger.set(self._counter).wait()
        if self._counter % self._random_send_interval == 0:
            self._send_data_to_bec()

    def _progress_update(self, value: int):
        """Update the progress of the device."""
        max_value = self.parent.scaninfo.num_points
        self.parent._run_subs(
            sub_type=self.parent.SUB_PROGRESS,
            value=value,
            max_value=max_value,
            done=bool(max_value == value),
        )


class SimMonitorAsync(PSIDetectorBase):
    """
    A simulated device to mimic the behaviour of an asynchronous monitor.

    During a scan, this device will send data not in sync with the point ID to BEC,
    but buffer data and send it in random intervals.
    """

    USER_ACCESS = ["sim", "registered_proxies", "async_update"]

    custom_prepare_cls = SimMonitorAsyncPrepare
    sim_cls = SimulatedDataMonitor
    BIT_DEPTH = np.uint32

    readback = Cpt(ReadOnlySignal, value=BIT_DEPTH(0), kind=Kind.hinted, compute_readback=True)
    current_trigger = Cpt(SetableSignal, value=BIT_DEPTH(0), kind=Kind.config)

    SUB_READBACK = "readback"
    SUB_PROGRESS = "progress"
    _default_sub = SUB_READBACK

    def __init__(
        self, name, *, sim_init: dict = None, parent=None, kind=None, device_manager=None, **kwargs
    ):
        self.init_sim_params = sim_init
        self.device_manager = device_manager
        self.sim = self.sim_cls(parent=self, **kwargs)
        self._registered_proxies = {}

        super().__init__(
            name=name, parent=parent, kind=kind, device_manager=device_manager, **kwargs
        )
        self.sim.sim_state[self.name] = self.sim.sim_state.pop(self.readback.name, None)
        self.readback.name = self.name
        self._data_buffer = {"value": [], "timestamp": []}
        self._async_update = "extend"

    @property
    def data_buffer(self) -> list:
        """Buffer for data to be sent asynchronously."""
        return self._data_buffer

    @property
    def registered_proxies(self) -> None:
        """Dictionary of registered signal_names and proxies."""
        return self._registered_proxies

    @property
    def async_update(self) -> str:
        """Update method for the asynchronous monitor."""
        return self._async_update

    @async_update.setter
    @typechecked
    def async_update(self, value: Literal["extend", "append"]) -> None:
        """Set the update method for the asynchronous monitor.

        Args:
            value (str): Can only be "extend" or "append".
        """
        self._async_update = value
