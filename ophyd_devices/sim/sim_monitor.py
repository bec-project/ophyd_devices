"""Module for simulated monitor devices."""

import traceback
from threading import Thread

import numpy as np
from bec_lib import messages
from bec_lib.endpoints import MessageEndpoints
from bec_lib.logger import bec_logger
from ophyd import Component as Cpt
from ophyd import Device, DeviceStatus, Kind

from ophyd_devices.interfaces.base_classes.psi_detector_base import (
    CustomDetectorMixin,
    PSIDetectorBase,
)
from ophyd_devices.sim.sim_data import SimulatedDataMonitor
from ophyd_devices.sim.sim_signals import ReadOnlySignal, SetableSignal
from ophyd_devices.utils.errors import DeviceStopError

logger = bec_logger.logger


class SimMonitor(ReadOnlySignal):
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
        # TODO remove after refactoring, this is a temporary bodge to avoid breaking tests
        self.readback = self

    @property
    def registered_proxies(self) -> None:
        """Dictionary of registered signal_names and proxies."""
        return self._registered_proxies


class SimMonitorAsyncPrepare(CustomDetectorMixin):
    """Custom prepare for the SimMonitorAsync class."""

    def __init__(self, *args, parent: Device = None, **kwargs) -> None:
        super().__init__(*args, parent=parent, **kwargs)
        self._stream_ttl = 1800
        self._random_send_interval = None
        self._counter = 0
        self._thread_trigger = None
        self._thread_complete = None
        self.prep_random_interval()
        self.parent.current_trigger.subscribe(self._progress_update, run=False)

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

    def on_complete(self):
        """Prepare the device for completion."""
        status = DeviceStatus(self.parent)

        def on_complete_call(status: DeviceStatus) -> None:
            try:
                if self.parent.data_buffer["value"]:
                    self._send_data_to_bec()
                if self.parent.stopped:
                    raise DeviceStopError(f"{self.parent.name} was stopped")
                status.set_finished()
            # pylint: disable=broad-except
            except Exception as exc:
                content = traceback.format_exc()
                status.set_exception(exc=exc)
                logger.warning(f"Error in {self.parent.name} on_complete; Traceback: {content}")

        self._thread_complete = Thread(target=on_complete_call, args=(status,))
        self._thread_complete.start()
        return status

    def _send_data_to_bec(self) -> None:
        """Sends bundled data to BEC"""
        if self.parent.scaninfo.scan_msg is None:
            return
        metadata = self.parent.scaninfo.scan_msg.metadata
        metadata.update({"async_update": self.parent.async_update.get()})

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
        status = DeviceStatus(self.parent)

        def on_trigger_call(status: DeviceStatus) -> None:
            try:
                self.parent.data_buffer["value"].append(self.parent.readback.get())
                self.parent.data_buffer["timestamp"].append(self.parent.readback.timestamp)
                self._counter += 1
                self.parent.current_trigger.set(self._counter).wait()
                if self._counter % self._random_send_interval == 0:
                    self._send_data_to_bec()
                if self.parent.stopped:
                    raise DeviceStopError(f"{self.parent.name} was stopped")
                status.set_finished()
            # pylint: disable=broad-except
            except Exception as exc:
                content = traceback.format_exc()
                logger.warning(
                    f"Error in on_trigger_call in device {self.parent.name}; Traceback: {content}"
                )
                status.set_exception(exc=exc)

        self._thread_trigger = Thread(target=on_trigger_call, args=(status,))
        self._thread_trigger.start()
        return status

    def _progress_update(self, value: int, **kwargs):
        """Update the progress of the device."""
        max_value = self.parent.scaninfo.num_points
        # pylint: disable=protected-access
        self.parent._run_subs(
            sub_type=self.parent.SUB_PROGRESS,
            value=value,
            max_value=max_value,
            done=bool(max_value == value),
        )

    def on_stop(self):
        """Stop the device."""
        if self._thread_trigger:
            self._thread_trigger.join()
        if self._thread_complete:
            self._thread_complete.join()
        self._thread_trigger = None
        self._thread_complete = None


class SimMonitorAsync(PSIDetectorBase):
    """
    A simulated device to mimic the behaviour of an asynchronous monitor.

    During a scan, this device will send data not in sync with the point ID to BEC,
    but buffer data and send it in random intervals.s
    """

    USER_ACCESS = ["sim", "registered_proxies", "async_update"]

    custom_prepare_cls = SimMonitorAsyncPrepare
    sim_cls = SimulatedDataMonitor
    BIT_DEPTH = np.uint32

    readback = Cpt(ReadOnlySignal, value=BIT_DEPTH(0), kind=Kind.hinted, compute_readback=True)
    current_trigger = Cpt(SetableSignal, value=BIT_DEPTH(0), kind=Kind.config)
    async_update = Cpt(SetableSignal, value="extend", kind=Kind.config)

    SUB_READBACK = "readback"
    SUB_PROGRESS = "progress"
    _default_sub = SUB_READBACK

    def __init__(
        self, name, *, sim_init: dict = None, parent=None, kind=None, device_manager=None, **kwargs
    ):
        self.sim_init = sim_init
        self.device_manager = device_manager
        self.sim = self.sim_cls(parent=self, **kwargs)
        self._registered_proxies = {}

        super().__init__(
            name=name, parent=parent, kind=kind, device_manager=device_manager, **kwargs
        )
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
