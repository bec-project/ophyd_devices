"""Tests for the AreaDetector ROI processing component."""

# pylint: disable=protected-access,redefined-outer-name

import threading
from types import SimpleNamespace
from unittest import mock

import numpy as np
import ophyd
import pytest
from bec_server.device_server.tests.utils import DMMock

from ophyd_devices.devices.areadetector.sim_detector_roi import SimDetectorROI
from ophyd_devices.tests.utils import MockPV, get_mock_scan_info, patch_dual_pvs
from ophyd_devices.utils.bec_roi_signals.ad_roi_signal import (
    NDPLUGIN_STATS_CONFIG,
    ADROIProcessing,
    fetch_scan_info,
)


def _stats_update_self(*, average: bool, frames_per_trigger: int = 5, num_points: int = 10):
    """A stand-in for ADROIProcessing exposing only what _on_stats_signal_update touches."""
    fake = mock.MagicMock()
    fake.is_operation_active.return_value = True
    fake.scan_server_scan_info = SimpleNamespace(
        positions=np.zeros((num_points, 1)), frames_per_trigger=frames_per_trigger
    )
    fake.average_frames_per_trigger.get.return_value = average
    return fake


def test_stats_update_averages_frames_per_trigger():
    """Test that the time series of one trigger is averaged into one scalar per point."""
    fake = _stats_update_self(average=True)
    ADROIProcessing._on_stats_signal_update(
        fake,
        operation="basic_statistics",
        result_name="total",
        output_kind="scalar",
        value=np.array([1.0, 2.0, 3.0, 4.0, 5.0]),
        timestamp=None,
    )
    fake.put_results.assert_called_once()
    kind, results = fake.put_results.call_args.args
    assert kind == "scalar"
    assert results["total"]["value"] == 3.0
    assert isinstance(results["total"]["timestamp"], float)
    assert fake.put_results.call_args.kwargs["async_update"] == {"type": "add", "max_shape": [10]}


def test_stats_update_without_averaging_keeps_frames():
    """Test that without averaging every frame of the time series is appended."""
    fake = _stats_update_self(average=False)
    value = [1.0, 2.0, 3.0, 4.0, 5.0]
    ADROIProcessing._on_stats_signal_update(
        fake,
        operation="basic_statistics",
        result_name="total",
        output_kind="waveform",
        value=value,
        timestamp=12.0,
    )
    kind, results = fake.put_results.call_args.args
    assert kind == "waveform"
    assert results["total"] == {"value": value, "timestamp": 12.0}
    assert fake.put_results.call_args.kwargs["async_update"] == {
        "type": "add",
        "max_shape": [50, None],
    }


def test_stats_update_ignores_inactive_operations():
    fake = _stats_update_self(average=True)
    fake.is_operation_active.return_value = False
    ADROIProcessing._on_stats_signal_update(
        fake, operation="centroid", result_name="centroid_x", output_kind="scalar", value=1.0
    )
    fake.put_results.assert_not_called()


def test_fetch_scan_info_does_not_mutate_scan_info():
    """Test that normalising the scan info leaves the shared message untouched."""
    scan_info = get_mock_scan_info(device=None)
    original = {
        key: (list(v) if isinstance(v, list) else v) for key, v in scan_info.msg.info.items()
    }

    info = fetch_scan_info(scan_info)

    assert isinstance(info.positions, np.ndarray)
    assert "num_monitored_readouts" not in scan_info.msg.info
    assert isinstance(scan_info.msg.info["positions"], list)
    for key, value in original.items():
        assert scan_info.msg.info[key] == value


@pytest.fixture
def sim_detector_roi():
    with mock.patch.object(ophyd, "cl") as mock_cl:
        mock_cl.get_pv = MockPV
        mock_cl.thread_class = threading.Thread
        det = SimDetectorROI(name="det", prefix="X:", device_manager=DMMock())
        patch_dual_pvs(det)
        yield det
        det.destroy()


def test_sim_detector_roi_connects_and_wires_plugins(sim_detector_roi):
    """Test that connecting the root applies the ROI geometry and subscribes to the stats outputs."""
    roi = sim_detector_roi.roi_processing
    n_outputs = sum(len(cfg["scalar_outputs"]) for cfg in NDPLUGIN_STATS_CONFIG.values())
    assert roi._selection_subscription is not None
    assert len(roi._stats_subscriptions) == n_outputs
    assert roi._missing_stats_paths == set()
    assert roi.roi1.min_xyz.min_x.get() == 400
    assert roi.roi1.size.x.get() == 100
    assert roi.stats1.ts_acquire_mode.get() == 0
    assert "det_roi_processing_x" not in sim_detector_roi.read()


def test_sim_detector_roi_forwards_scan_hooks(sim_detector_roi):
    """Test that stage/trigger/stop/destroy reach the ROI component."""
    roi = sim_detector_roi.roi_processing
    sim_detector_roi.on_stage()
    assert roi.scan_server_scan_info is not None
    assert roi.stats1.ts_num_points.get() == roi.scan_server_scan_info.frames_per_trigger

    status = sim_detector_roi.on_trigger()
    assert roi.stats1.ts_acquire.get() == 1
    roi.stats1.ts_acquire_status._read_pv.mock_data = 1  # MockPV runs the callbacks on set
    roi.stats1.ts_acquire_status._read_pv.mock_data = 0
    status.wait(timeout=1)
    assert status.done and status.success

    sim_detector_roi.on_stop()
    assert roi.stats1.ts_acquire.get() == 0
    sim_detector_roi.on_destroy()
    assert roi._stats_subscriptions == {}
