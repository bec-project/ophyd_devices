"""Module for simulated monitor devices."""

import time
from dataclasses import dataclass

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
from ophyd_devices.utils.bec_signals import AsyncMultiSignal, AsyncSignal, ProgressSignal

logger = bec_logger.logger


@dataclass
class RegisteredCallback:

    motor: str
    callback_id: int


class SimMonitor(ReadOnlySignal):
    """
    A simulated device mimic any 1D Axis (position, temperature, beam).

    It's readback is a computed signal, which is configurable by the user and from the command line.
    The corresponding simulation class is sim_cls=SimulatedDataMonitor, more details on defaults
    within the simulation class.

    >>> monitor = SimMonitor(name="monitor")

    Parameters
    ----------
    name (string)           : Name of the device. This is the only required argument,
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
        self._registered_proxies = {}
        self._registered_callback: RegisteredCallback | None = None
        self.sim = self.sim_cls(parent=self, **kwargs)

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
    def registered_proxies(self) -> dict:
        """Dictionary of registered signal_names and proxies."""
        return self._registered_proxies

    def setup_readback_monitor(self, motor_name: str) -> None:
        """
        Set up monitoring of the readback signal of a motor.

        Args:
            motor_name (str): The name of the motor to monitor.
        """
        if self._registered_callback and self._registered_callback.motor == motor_name:
            return  # Already registered callback for this motor
        self.unregister_readback_cb(motor_name)  # Unregister previous callback if necessary
        # Register new callback
        motor = self.device_manager.devices.get(motor_name, None)
        if motor:
            cb_id = motor.subscribe(self._update_readback, run=False)
            self._registered_callback = RegisteredCallback(motor=motor_name, callback_id=cb_id)

    def unregister_readback_cb(self, motor_name: str) -> None:
        """Unregister the callback from the motor."""
        if self._registered_callback:
            motor = self.device_manager.devices.get(self._registered_callback.motor, None)
            if motor:
                motor.unsubscribe(self._registered_callback.callback_id)
                self._registered_callback = None

    def _update_readback(self, value, **kwargs):
        """Callback function to update the readback value."""
        self.get()


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
        if not self.scan_info.msg:
            return
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


class SimMonitorMixedSignalsControl(Device):
    """Component container and simulation backend for ``SimMonitorMixedSignals``.

    Split out from the behaviour class (mirroring ``SimMonitorAsyncControl``) so that
    the simulation backend and the synchronous ``readback`` signal are wired up before
    :class:`PSIDeviceBase` runs its own initialisation.
    """

    USER_ACCESS = ["sim", "registered_proxies"]

    sim_cls = SimulatedDataMonitor
    BIT_DEPTH = np.uint32

    # --- Synchronous signal -------------------------------------------------
    # Read by BEC at every scan point (the device has readoutPriority 'monitored').
    # Its serialized signal_class is 'ReadOnlySignal', so it is classified as sync.
    readback = Cpt(ReadOnlySignal, value=BIT_DEPTH(0), kind=Kind.hinted, compute_readback=True)

    # --- Asynchronous signals (modern AsyncSignal family) -------------------
    # These carry signal_class 'AsyncSignal' / 'AsyncMultiSignal' in the device info,
    # so a signal-aware classifier marks them async even though the parent device sits
    # in the 'monitored' readout-priority group (the core of bec_widgets issue #1185).
    async_counts = Cpt(
        AsyncSignal, ndim=0, max_size=1000, doc="Scalar counts streamed asynchronously."
    )
    async_spectrum = Cpt(
        AsyncSignal, ndim=1, max_size=1000, doc="1D spectrum streamed asynchronously."
    )
    async_channels = Cpt(
        AsyncMultiSignal,
        signals=["ch1", "ch2"],
        ndim=0,
        max_size=1000,
        doc="Two scalar channels streamed asynchronously as one multi-signal.",
    )

    # --- Late-typed signal --------------------------------------------------
    # Declared as a plain (synchronous) SetableSignal, so its serialized signal_class
    # is 'SetableSignal'. Outside a scan it behaves synchronously, but once a scan
    # starts the device also streams it on the async readback endpoint. Its effective
    # data-delivery type is therefore only known at the first reported value /
    # beginning of the scan -- the case static, class-based classification cannot see.
    morphing = Cpt(SetableSignal, value=BIT_DEPTH(0), kind=Kind.normal)

    # --- Non-curve signal ---------------------------------------------------
    # role='progress' -> not curve data; a signal-aware classifier must ignore it.
    progress = Cpt(ProgressSignal, doc="Scan progress; not plotted as a curve.")

    # --- Config -------------------------------------------------------------
    spectrum_size = Cpt(SetableSignal, value=200, kind=Kind.config)
    # Whether the late-typed 'morphing' signal is streamed asynchronously during a scan.
    stream_morphing_async = Cpt(SetableSignal, value=1, kind=Kind.config)

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
        # Mirror SimMonitor(Async): expose the primary readback under the device name.
        self.sim.sim_state[self.name] = self.sim.sim_state.pop(self.readback.name, None)
        self.readback.name = self.name
        if self.sim_init:
            self.sim.set_init(self.sim_init)

    @property
    def registered_proxies(self) -> dict:
        """Dictionary of registered signal_names and proxies."""
        return self._registered_proxies


class SimMonitorMixedSignals(PSIDeviceBase, SimMonitorMixedSignalsControl):
    """A simulated *monitored* device that mixes synchronous and asynchronous signals.

    This device exists to reproduce and exercise bec_widgets issue #1185: a device whose
    readout priority is ``monitored`` can still expose asynchronous signals. Curves must
    therefore be classified per-signal (sync vs async), not by the parent device's
    readout-priority group.

    Signals exposed:

    * ``readback``         - synchronous, hinted; read at every scan point. (sync)
    * ``async_counts``     - ``AsyncSignal`` (scalar); appended on every trigger. (async)
    * ``async_spectrum``   - ``AsyncSignal`` (1D); the latest spectrum on every trigger. (async)
    * ``async_channels``   - ``AsyncMultiSignal`` (ch1/ch2); appended on every trigger. (async)
    * ``morphing``         - plain ``SetableSignal`` that is *also* streamed on the async
      endpoint during a scan. Its data-delivery type is only revealed at the first
      reported value / beginning of the scan -- a case static class-based classification
      cannot resolve, and which class-based classification will (incorrectly) treat as
      synchronous. Useful for validating any runtime/first-value reclassification.
    * ``progress``         - ``ProgressSignal`` (role 'progress'); never a curve.

    Intended config: ``readoutPriority: monitored`` and ``softwareTrigger: true`` so that
    the device is both read at every point (sync) and triggered to stream async data.
    """

    def __init__(
        self,
        name: str,
        *,
        scan_info=None,
        parent: Device = None,
        device_manager=None,
        sim_init: dict = None,
        **kwargs,
    ) -> None:
        super().__init__(
            name=name,
            scan_info=scan_info,
            parent=parent,
            device_manager=device_manager,
            sim_init=sim_init,
            **kwargs,
        )
        self._stream_ttl = 1800  # 30 min max
        self._counter = 0
        self._morphing_send_interval = 1  # flush the morphing buffer every trigger
        self._morphing_buffer: dict[str, list] = {"value": [], "timestamp": []}

    # ------------------------------------------------------------------ helpers
    def _clear_morphing_buffer(self) -> None:
        """Clear the buffer used for the late-typed ``morphing`` signal."""
        self._morphing_buffer["value"].clear()
        self._morphing_buffer["timestamp"].clear()

    def _generate_spectrum(self) -> np.ndarray:
        """Generate a noisy 1D spectrum whose peak drifts with the trigger counter."""
        size = int(self.spectrum_size.get())
        if size <= 0:
            raise ValueError(f"{self.name}: spectrum_size must be > 0, got {size}")
        x = np.arange(size)
        center = (self._counter * max(size // 20, 1)) % size
        spectrum = 100 * np.exp(-((x - center) ** 2) / (2 * (size / 20) ** 2))
        spectrum = spectrum + np.random.normal(0, 2, size)
        return self.BIT_DEPTH(np.clip(spectrum, 0, None))

    def _send_morphing_to_bec(self) -> None:
        """Stream the buffered ``morphing`` values on the async readback endpoint.

        This emulates a legacy/late-typed async signal: a plain signal whose values are
        delivered asynchronously even though its static signal_class looks synchronous.
        """
        msg = messages.DeviceMessage(
            signals={self.morphing.name: dict(self._morphing_buffer)},
            metadata={"async_update": {"type": "add", "max_shape": [None]}},
        )
        self.connector.xadd(
            MessageEndpoints.device_async_readback(
                scan_id=self.scan_info.msg.scan_id, device=self.name
            ),
            {"data": msg},
            expire=self._stream_ttl,
        )
        self._clear_morphing_buffer()

    # -------------------------------------------------------------- scan hooks
    def on_stage(self) -> None:
        """Reset counters and buffers for a fresh scan."""
        self._counter = 0
        self._clear_morphing_buffer()

    def on_trigger(self) -> StatusBase:
        """Read the sync readback and stream all async signals for one scan point."""

        def _acquire():
            self._counter += 1
            counts = int(self.readback.get())  # synchronous, computed readback

            # Modern AsyncSignal-family streams (classified async by signal_class).
            self.async_counts.put(counts, async_update={"type": "add", "max_shape": [None]})
            self.async_spectrum.put(self._generate_spectrum(), async_update={"type": "replace"})
            self.async_channels.put(
                {"ch1": {"value": counts}, "ch2": {"value": counts // 2}},
                async_update={"type": "add", "max_shape": [None]},
            )

            # Late-typed signal: also stream the plain 'morphing' signal asynchronously.
            if self.stream_morphing_async.get():
                self.morphing.put(self.BIT_DEPTH(counts))
                self._morphing_buffer["value"].append(counts)
                self._morphing_buffer["timestamp"].append(time.time())
                if self._counter % self._morphing_send_interval == 0:
                    self._send_morphing_to_bec()

            # Progress (role 'progress' -> never a curve).
            num_points = getattr(self.scan_info.msg, "num_points", 0) or 0
            self.progress.put(
                value=self._counter,
                max_value=num_points,
                done=bool(num_points and self._counter >= num_points),
            )

        return self.task_handler.submit_task(_acquire)

    def on_complete(self) -> StatusBase:
        """Flush any buffered late-typed data at the end of the scan."""

        def _complete():
            if self._morphing_buffer["value"]:
                self._send_morphing_to_bec()

        return self.task_handler.submit_task(_complete)

    def on_stop(self) -> None:
        """Stop the device and shut down background tasks."""
        self.task_handler.shutdown()


if __name__ == "__main__":  # pragma: no cover
    monitor = SimMonitorMixedSignals(name="mixed_mon")
    monitor.wait_for_connection()
    print("readback signal_class:", type(monitor.readback).__name__)
    print("async_counts signal_class:", type(monitor.async_counts).__name__)
