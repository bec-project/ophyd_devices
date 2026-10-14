"""Tests for ROI processing signals."""

# pylint: disable=protected-access,redefined-outer-name,too-many-arguments

from types import SimpleNamespace

import numpy as np
import pytest
from bec_lib import messages
from bec_server.device_server.tests.utils import DMMock

from ophyd_devices.sim.sim_camera import SimCamera


@pytest.fixture(scope="function")
def camera_with_roi(name="camera"):
    """Fixture for SimCamera with ROI processing connected."""
    dm = DMMock()
    cam = SimCamera(name=name, device_manager=dm)
    cam.wait_for_connection()
    yield cam
    cam.destroy()


@pytest.fixture(scope="function")
def roi_processing(camera_with_roi):
    """Fixture for the SimCamera ROI processing signal."""
    yield camera_with_roi.roi_processing


def _roi_config_message(
    *,
    device="camera",
    signal="roi_processing",
    name="roi",
    active=True,
    x=0,
    y=0,
    width=1,
    height=1,
    selected_operations=None,
    block_while_scanning=True,
):
    """Create a ROI configuration message."""
    return messages.ROIConfigurationMessage(
        device=device,
        signal=signal,
        name=name,
        active=active,
        roi_config=messages.ROIConfig(x=x, y=y, width=width, height=height),
        selected_operations=selected_operations or ["basic_statistics"],
        block_while_scanning=block_while_scanning,
    )


def _scalar_result_values(roi_processing):
    """Return scalar ROI results keyed by short result name."""
    message = roi_processing.result_scalar.get()
    prefix = f"{roi_processing.result_scalar.name}_"
    return {
        signal_name.removeprefix(prefix): data["value"]
        for signal_name, data in message.signals.items()
    }


def test_sim_camera_roi_processing_initializes_available_analysis(camera_with_roi):
    """Test that SimCamera exposes the available ROI analysis metadata."""
    roi = camera_with_roi.roi_processing

    assert roi.get_available_analysis_operations() == ["basic_statistics"]
    assert roi.available_operations.get() == ["basic_statistics"]
    assert roi.get_scalar_outputs() == ["sum", "mean", "min", "max"]
    assert roi.get_waveform_outputs() == []
    assert [name for name, _ in roi.result_scalar.signals] == ["sum", "mean", "min", "max"]
    assert roi.result_waveform.signals == []

    published = [
        item["msg"]
        for item in camera_with_roi.device_manager.connector.message_sent
        if isinstance(item["msg"], messages.ROIAvailableAnalysisMessage)
    ]
    assert len(published) == 1
    assert published[0].device == camera_with_roi.name
    assert published[0].signal == roi.dotted_name
    assert published[0].config.available_operations == ["basic_statistics"]
    assert published[0].config.scalar_results == ["sum", "mean", "min", "max"]
    assert published[0].config.waveform_results == []


def test_selected_operations_reject_unknown_operation(roi_processing):
    """Test that selected operations are validated against the available operations."""
    with pytest.raises(ValueError, match="Invalid operation"):
        roi_processing.selected_operations.put(["does_not_exist"])


def test_sim_camera_roi_processing_extracts_clipped_roi(roi_processing):
    """Test that ROI extraction clips negative starts to the image boundary."""
    image = np.arange(20).reshape(4, 5)
    roi_processing.x.put(-1)
    roi_processing.y.put(1)
    roi_processing.width.put(4)
    roi_processing.height.put(3)

    np.testing.assert_array_equal(roi_processing._extract_roi(image), image[1:4, 0:3])


@pytest.mark.parametrize(
    "x, y, width, height", [(10, 0, 2, 2), (0, 10, 2, 2), (0, 0, 0, 2), (0, 0, 2, -1)]
)
def test_sim_camera_roi_processing_extracts_empty_roi(roi_processing, x, y, width, height):
    """Test that out-of-bounds or non-positive ROIs produce empty arrays."""
    roi_processing.x.put(x)
    roi_processing.y.put(y)
    roi_processing.width.put(width)
    roi_processing.height.put(height)

    assert roi_processing._extract_roi(np.ones((4, 5))).size == 0


def test_sim_camera_roi_processing_computes_basic_statistics(roi_processing):
    """Test basic scalar statistics for a ROI image."""
    stats = roi_processing._compute_basic_statistics(np.array([[1, 2], [3, 4]]))

    assert set(stats) == {"sum", "mean", "min", "max"}
    assert stats["sum"]["value"] == 10
    assert stats["mean"]["value"] == 2.5
    assert stats["min"]["value"] == 1
    assert stats["max"]["value"] == 4
    assert all("timestamp" in entry for entry in stats.values())


def test_roi_configuration_message_updates_processing_signals(roi_processing):
    """Test that a received ROI configuration updates all processing signals."""
    message = _roi_config_message(
        name="beam",
        active=False,
        x=3,
        y=4,
        width=5,
        height=6,
        selected_operations=["basic_statistics"],
    )

    roi_processing._receive_roi_configuration_message(SimpleNamespace(value=message))

    assert roi_processing.active.get() is False
    assert roi_processing.roi_name.get() == "beam"
    assert roi_processing.x.get() == 3
    assert roi_processing.y.get() == 4
    assert roi_processing.width.get() == 5
    assert roi_processing.height.get() == 6
    assert roi_processing.selected_operations.get() == ["basic_statistics"]


def test_roi_configuration_message_for_other_signal_is_ignored(roi_processing):
    """Test that ROI configuration messages are scoped to the matching signal."""
    initial_x = roi_processing.x.get()
    message = _roi_config_message(signal="other_roi_processing", x=99)

    roi_processing._receive_roi_configuration_message(SimpleNamespace(value=message))

    assert roi_processing.x.get() == initial_x


def test_blocked_roi_configuration_updates_apply_latest_on_unblock(roi_processing):
    """Test that blocked ROI config updates cache and apply only the latest value."""
    roi_processing.update_received.block_updates()
    first = _roi_config_message(name="first", x=1)
    latest = _roi_config_message(name="latest", x=7, width=8)

    roi_processing.update_received.put(first)
    roi_processing.update_received.put(latest)

    assert roi_processing.update_received.has_pending_update is True
    assert roi_processing.roi_name.get() != "latest"

    released = roi_processing.update_received.unblock_updates()

    assert released == latest
    assert roi_processing.update_received.has_pending_update is False
    assert roi_processing.roi_name.get() == "latest"
    assert roi_processing.x.get() == 7
    assert roi_processing.width.get() == 8


def test_sim_camera_image_update_publishes_roi_scalar_results(camera_with_roi):
    """Test SimCamera image updates are processed into ROI scalar results."""
    camera_with_roi.image_shape.set((6, 6)).wait()
    camera_with_roi.sim.select_model("constant")
    camera_with_roi.sim.params = {
        "amplitude": 5,
        "noise": "none",
        "hot_pixel_coords": [],
        "hot_pixel_types": [],
        "hot_pixel_values": [],
    }
    roi = camera_with_roi.roi_processing
    roi.active.put(True)
    roi.selected_operations.put(["basic_statistics"])
    roi.x.put(1)
    roi.y.put(2)
    roi.width.put(3)
    roi.height.put(2)

    image = camera_with_roi.image.get()

    assert image.shape == (6, 6)
    assert _scalar_result_values(roi) == {"sum": 30.0, "mean": 5.0, "min": 5.0, "max": 5.0}


def test_sim_camera_image_update_does_not_publish_when_roi_inactive(roi_processing):
    """Test inactive ROI processing ignores image updates."""
    roi_processing.active.put(False)

    roi_processing._on_image_update(np.ones((3, 3)))

    assert roi_processing.result_scalar.get() is None
