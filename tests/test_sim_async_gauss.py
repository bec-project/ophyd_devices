"""Tests for the simulated asynchronous 2D Gaussian device."""

import threading

import numpy as np
import pytest
from bec_lib import messages

from ophyd_devices.interfaces.base_classes.psi_device_base import DeviceStoppedError
from ophyd_devices.interfaces.protocols.bec_protocols import BECDeviceProtocol
from ophyd_devices.sim.sim_async_gauss import PATTERNS, SimAsyncGauss2D, compute_trajectory

# pylint: disable=protected-access


@pytest.fixture
def gauss():
    """SimAsyncGauss2D streaming fast, recording every emitted message."""
    dev = SimAsyncGauss2D(name="gauss")
    dev.rate.put(1e6)
    dev.num_points.put(100)
    dev.chunk_size.put(30)
    dev.noise.put(0.0)
    dev.emitted = []
    dev.data.subscribe(lambda value=None, **_: dev.emitted.append(value), run=False)
    yield dev
    dev.destroy()


def test_gauss_init(gauss):
    assert isinstance(gauss, BECDeviceProtocol)
    info = gauss.data.describe()[gauss.data.name]["signal_info"]
    assert info["ndim"] == 0
    assert [name for name, _ in info["signals"]] == ["x", "y", "intensity"]


@pytest.mark.parametrize("pattern", PATTERNS)
def test_compute_trajectory_covers_the_ranges(pattern):
    x, y = compute_trajectory(pattern, 400, (-2, 2), (10, 20), rng=np.random.default_rng(0))
    assert len(x) == len(y) == 400
    assert x.min() >= -2 and x.max() <= 2
    assert y.min() >= 10 and y.max() <= 20


def test_compute_trajectory_snake_alternates_rows():
    x, y = compute_trajectory("snake", 9, (0, 2), (0, 2))
    np.testing.assert_allclose(x, [0, 1, 2, 2, 1, 0, 0, 1, 2])
    np.testing.assert_allclose(y, [0, 0, 0, 1, 1, 1, 2, 2, 2])


def test_compute_trajectory_rejects_invalid_input():
    with pytest.raises(ValueError):
        compute_trajectory("zigzag", 10, (0, 1), (0, 1))
    with pytest.raises(ValueError):
        compute_trajectory("snake", 0, (0, 1), (0, 1))


def test_compute_intensity_peaks_at_the_centre(gauss):
    peak = gauss.compute_intensity(gauss.center_x.get(), gauss.center_y.get(), noise=False)
    assert peak == pytest.approx(gauss.amplitude.get() + gauss.background.get())
    far = gauss.compute_intensity(100.0, 100.0, noise=False)
    assert far == pytest.approx(gauss.background.get())


def test_compute_intensity_adds_noise_when_enabled(gauss):
    gauss.noise.put(5.0)
    x = np.zeros(1000)
    noisy = gauss.compute_intensity(x, x)
    clean = gauss.compute_intensity(x, x, noise=False)
    assert np.std(noisy - clean) == pytest.approx(5.0, rel=0.2)


def test_complete_without_stage_computes_the_trajectory(gauss):
    assert gauss._trajectory is None
    gauss.complete().wait(timeout=5)
    assert len(gauss._trajectory[0]) == 100
    assert sum(len(msg.signals["gauss_data_x"]["value"]) for msg in gauss.emitted) == 100


def test_stream_emits_all_sub_signals_together(gauss):
    gauss.stage()
    gauss.pre_scan()
    status = gauss.complete()
    status.wait(timeout=5)
    gauss.unstage()

    assert len(gauss.emitted) == 4  # 100 samples in chunks of 30
    for msg in gauss.emitted:
        assert isinstance(msg, messages.DeviceMessage)
        assert set(msg.signals) == {"gauss_data_x", "gauss_data_y", "gauss_data_intensity"}
        assert msg.metadata["async_update"] == {"type": "add", "max_shape": [None]}
        lengths = {len(sig["value"]) for sig in msg.signals.values()}
        assert len(lengths) == 1
    x, y, intensity = (
        np.concatenate([msg.signals[f"gauss_data_{name}"]["value"] for msg in gauss.emitted])
        for name in ("x", "y", "intensity")
    )
    np.testing.assert_allclose(x, gauss._trajectory[0])
    np.testing.assert_allclose(intensity, gauss.compute_intensity(x, y, noise=False))
    assert gauss.progress.get().done


def test_complete_without_pre_scan_still_streams(gauss):
    gauss.stage()
    gauss.complete().wait(timeout=5)
    assert sum(len(msg.signals["gauss_data_x"]["value"]) for msg in gauss.emitted) == 100


def test_stop_cancels_a_running_stream(gauss):
    gauss.rate.put(50.0)
    gauss.chunk_size.put(1)
    gauss.stage()
    gauss.pre_scan()
    status = gauss.complete()
    gauss.stop()
    gauss.stop()  # repeated calls are safe
    with pytest.raises(DeviceStoppedError):
        status.wait(timeout=5)
    assert not status.success
    assert len(gauss.emitted) < 100
    assert not any(t.name == "gauss_stream" for t in threading.enumerate())


def test_stream_failure_fails_the_status(gauss):
    gauss.stage()
    gauss.data.put = lambda *_, **__: (_ for _ in ()).throw(RuntimeError("boom"))
    status = gauss.complete()
    with pytest.raises(RuntimeError, match="boom"):
        status.wait(timeout=5)
