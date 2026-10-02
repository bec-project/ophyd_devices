"""
Simulated asynchronous 2D Gaussian scan published through a single AsyncMultiSignal.

The device mimics a detector that samples its own encoders: while a scan runs it streams
``x`` and ``y`` positions along a trajectory (snake raster, spiral, Lissajous or random)
together with a Gaussian ``intensity`` evaluated at those positions. All three are
sub-signals of one ``AsyncMultiSignal`` and are always emitted together, so every sample
of ``intensity`` belongs to exactly one ``(x, y)`` pair. The stream is independent of the
scan points: it starts at ``pre_scan`` and the scan completes once all samples are sent.

Typical use in BEC::

    dev.gauss_async.pattern.set("spiral")
    scans.acquire(exp_time=0.1)

and plot ``gauss_async_data_intensity`` against ``gauss_async_data_x`` /
``gauss_async_data_y`` (heatmap, scatter or waveform).
"""

from __future__ import annotations

import threading
import time

import numpy as np
from bec_lib.logger import bec_logger
from ophyd import Component as Cpt
from ophyd import Device, Kind

from ophyd_devices.interfaces.base_classes.psi_device_base import PSIDeviceBase
from ophyd_devices.sim.sim_signals import SetableSignal
from ophyd_devices.utils.bec_signals import AsyncMultiSignal, ProgressSignal
from ophyd_devices.utils.psi_device_base_utils import DeviceStatus, StatusBase

logger = bec_logger.logger

PATTERNS = ("snake", "spiral", "lissajous", "random")


def compute_trajectory(
    pattern: str,
    num_points: int,
    x_range: tuple[float, float],
    y_range: tuple[float, float],
    rng: np.random.Generator | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Compute ``num_points`` (x, y) positions covering the given ranges.

    Args:
        pattern (str): One of ``"snake"``, ``"spiral"``, ``"lissajous"`` or ``"random"``.
        num_points (int): Number of samples.
        x_range (tuple[float, float]): Lower and upper x limit.
        y_range (tuple[float, float]): Lower and upper y limit.
        rng (np.random.Generator | None): Random generator for the ``"random"`` pattern.

    Returns:
        tuple[np.ndarray, np.ndarray]: The x and y positions, both of length ``num_points``.
    """
    if pattern not in PATTERNS:
        raise ValueError(f"Unknown pattern {pattern!r}; choose one of {PATTERNS}.")
    if num_points < 1:
        raise ValueError(f"num_points must be positive, got {num_points}.")
    (x_lo, x_hi), (y_lo, y_hi) = x_range, y_range
    x_mid, x_half = (x_lo + x_hi) / 2, (x_hi - x_lo) / 2
    y_mid, y_half = (y_lo + y_hi) / 2, (y_hi - y_lo) / 2
    if pattern == "snake":
        num_rows = max(1, int(round(np.sqrt(num_points))))
        num_cols = int(np.ceil(num_points / num_rows))
        col = np.arange(num_points) % num_cols
        row = np.arange(num_points) // num_cols
        col = np.where(row % 2 == 0, col, num_cols - 1 - col)
        u = col / max(num_cols - 1, 1)
        v = row / max(num_rows - 1, 1)
        return x_lo + u * (x_hi - x_lo), y_lo + v * (y_hi - y_lo)
    if pattern == "spiral":
        # Fermat spiral: uniform point density over the disc inscribed in the ranges.
        index = np.arange(num_points)
        radius = np.sqrt((index + 0.5) / num_points)
        angle = index * np.pi * (3 - np.sqrt(5))
        return x_mid + x_half * radius * np.cos(angle), y_mid + y_half * radius * np.sin(angle)
    if pattern == "lissajous":
        t = np.linspace(0, 2 * np.pi, num_points)
        return x_mid + x_half * np.sin(13 * t + np.pi / 2), y_mid + y_half * np.sin(14 * t)
    rng = rng or np.random.default_rng()
    return rng.uniform(x_lo, x_hi, num_points), rng.uniform(y_lo, y_hi, num_points)


class SimAsyncGauss2DControl(Device):
    """Signals of the simulated asynchronous 2D Gaussian device."""

    data = Cpt(
        AsyncMultiSignal,
        signals=["x", "y", "intensity"],
        ndim=0,
        max_size=100_000,
        async_update={"type": "add", "max_shape": [None]},
        doc="Asynchronous x/y positions and the Gaussian intensity sampled at them",
    )
    progress = Cpt(ProgressSignal, doc="Number of streamed samples")

    pattern = Cpt(SetableSignal, value="snake", kind=Kind.config, doc=f"One of {PATTERNS}")
    num_points = Cpt(SetableSignal, value=2500, kind=Kind.config, doc="Samples per scan")
    rate = Cpt(SetableSignal, value=500.0, kind=Kind.config, doc="Samples per second")
    chunk_size = Cpt(SetableSignal, value=50, kind=Kind.config, doc="Samples per message")
    x_min = Cpt(SetableSignal, value=-5.0, kind=Kind.config)
    x_max = Cpt(SetableSignal, value=5.0, kind=Kind.config)
    y_min = Cpt(SetableSignal, value=-5.0, kind=Kind.config)
    y_max = Cpt(SetableSignal, value=5.0, kind=Kind.config)
    center_x = Cpt(SetableSignal, value=1.0, kind=Kind.config, doc="Gaussian centre in x")
    center_y = Cpt(SetableSignal, value=-0.5, kind=Kind.config, doc="Gaussian centre in y")
    sigma_x = Cpt(SetableSignal, value=1.5, kind=Kind.config, doc="Gaussian width in x")
    sigma_y = Cpt(SetableSignal, value=1.0, kind=Kind.config, doc="Gaussian width in y")
    amplitude = Cpt(SetableSignal, value=1000.0, kind=Kind.config, doc="Gaussian peak height")
    background = Cpt(SetableSignal, value=10.0, kind=Kind.config, doc="Constant offset")
    noise = Cpt(SetableSignal, value=5.0, kind=Kind.config, doc="Gaussian noise sigma")


class SimAsyncGauss2D(PSIDeviceBase, SimAsyncGauss2DControl):
    """
    Simulated device streaming x, y and a 2D Gaussian intensity asynchronously.

    The three values are sub-signals of the ``data`` AsyncMultiSignal (``<name>_data_x``,
    ``<name>_data_y``, ``<name>_data_intensity``). They are emitted together in chunks of
    ``chunk_size`` samples at ``rate`` samples per second, starting at ``pre_scan``;
    ``complete`` resolves when all ``num_points`` samples have been sent. The trajectory
    and the Gaussian are configured through the config signals of the device.
    """

    USER_ACCESS = ["compute_intensity"]

    def __init__(self, *, name: str, scan_info=None, device_manager=None, **kwargs):
        super().__init__(name=name, scan_info=scan_info, device_manager=device_manager, **kwargs)
        self._rng = np.random.default_rng()
        self._trajectory: tuple[np.ndarray, np.ndarray] | None = None
        self._stream_thread: threading.Thread | None = None
        self._stream_status: DeviceStatus | None = None
        self._stop_event = threading.Event()

    def compute_intensity(self, x, y, noise: bool = True) -> np.ndarray:
        """
        Evaluate the simulated Gaussian at the given positions.

        Args:
            x: x position(s).
            y: y position(s).
            noise (bool): Add Gaussian noise of width ``noise``.

        Returns:
            np.ndarray: The intensity at each position.
        """
        x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
        exponent = ((x - self.center_x.get()) / self.sigma_x.get()) ** 2 + (
            (y - self.center_y.get()) / self.sigma_y.get()
        ) ** 2
        intensity = self.background.get() + self.amplitude.get() * np.exp(-0.5 * exponent)
        noise_sigma = self.noise.get()
        if noise and noise_sigma > 0:
            intensity = intensity + self._rng.normal(0, noise_sigma, intensity.shape)
        return intensity

    ########################################
    #  Beamline Specific Implementations   #
    ########################################

    def on_init(self) -> None:
        """
        Called when the device is initialized.

        No signals are connected at this point. If you like to
        set default values on signals, please use on_connected instead.
        """

    def on_connected(self) -> None:
        """
        Called after the device is connected and its signals are connected.
        Default values for signals should be set here.
        """

    def on_stage(self) -> DeviceStatus | StatusBase | None:
        """
        Called while staging the device.

        Computes the trajectory of the upcoming scan from the config signals.
        """
        self._stop_stream()
        self._stop_event.clear()
        self._stream_status = None
        self._trajectory = compute_trajectory(
            pattern=str(self.pattern.get()),
            num_points=int(self.num_points.get()),
            x_range=(float(self.x_min.get()), float(self.x_max.get())),
            y_range=(float(self.y_min.get()), float(self.y_max.get())),
            rng=self._rng,
        )

    def on_unstage(self) -> DeviceStatus | StatusBase | None:
        """Called while unstaging the device. Stops a stream that is still running."""
        self._stop_stream()

    def on_pre_scan(self) -> DeviceStatus | StatusBase | None:
        """Called right before the scan starts on all devices automatically. Starts the stream."""
        self._start_stream()

    def on_trigger(self) -> DeviceStatus | StatusBase | None:
        """Called when the device is triggered."""

    def on_complete(self) -> DeviceStatus | StatusBase | None:
        """Called to inquire if a device has completed a scans. Resolves after the last sample."""
        # Scans that skip pre_scan still get their data.
        return self._start_stream()

    def on_kickoff(self) -> DeviceStatus | StatusBase | None:
        """Called to kickoff a device for a fly scan. Has to be called explicitly."""

    def on_stop(self) -> None:
        """Called when the device is stopped."""
        self._stop_stream()

    def on_destroy(self) -> None:
        """Called when the device is destroyed. Cleanup resources here."""
        self._stop_stream()

    ########################################
    #            Helper Methods            #
    ########################################

    def _start_stream(self) -> DeviceStatus:
        """Start streaming the staged trajectory unless it already runs; return its status."""
        if self._stream_status is not None:
            return self._stream_status
        if self._trajectory is None:
            self.on_stage()
        status = DeviceStatus(self, description=f"{self.name} streaming samples")
        self.cancel_on_stop(status)
        self._stream_status = status
        self._stream_thread = threading.Thread(
            target=self._stream, args=(status,), name=f"{self.name}_stream", daemon=True
        )
        self._stream_thread.start()
        return status

    def _stop_stream(self) -> None:
        """Interrupt the running stream; safe to call repeatedly."""
        self._stop_event.set()
        thread, self._stream_thread = self._stream_thread, None
        if thread is not None and thread is not threading.current_thread():
            thread.join()

    def _stream(self, status: DeviceStatus) -> None:
        """Emit the trajectory chunk by chunk at the configured rate."""
        try:
            x_all, y_all = self._trajectory
            total = len(x_all)
            chunk = max(1, int(self.chunk_size.get()))
            period = chunk / max(float(self.rate.get()), 1e-6)
            next_emit = time.monotonic()
            for start in range(0, total, chunk):
                if self._stop_event.wait(timeout=max(0.0, next_emit - time.monotonic())):
                    return
                next_emit += period
                x, y = x_all[start : start + chunk], y_all[start : start + chunk]
                now = time.time()
                timestamps = (now - period + period * np.arange(1, len(x) + 1) / len(x)).tolist()
                self.data.put(
                    {
                        "x": {"value": x.tolist(), "timestamp": timestamps},
                        "y": {"value": y.tolist(), "timestamp": timestamps},
                        "intensity": {
                            "value": self.compute_intensity(x, y).tolist(),
                            "timestamp": timestamps,
                        },
                    }
                )
                sent = min(start + chunk, total)
                self.progress.put(value=sent, max_value=total, done=sent == total)
            if not status.done:
                status.set_finished()
        except Exception as exc:  # pylint: disable=broad-except
            logger.error(f"Streaming of {self.name} failed: {exc}")
            if not status.done:
                status.set_exception(exc)


if __name__ == "__main__":  # pragma: no cover
    gauss = SimAsyncGauss2D(name="gauss_async")
    gauss.stage()
    gauss.pre_scan()
    gauss.complete().wait()
    gauss.unstage()
