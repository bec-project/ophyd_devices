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
    cam.roi_processing.on_connected()
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
        roi_config=messages.RectROIConfig(x=x, y=y, width=width, height=height),
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
    roi_processing.update_received.put(_roi_config_message(x=-1, y=1, width=4, height=3))

    np.testing.assert_array_equal(roi_processing._extract_roi(image), image[1:4, 0:3])


@pytest.mark.parametrize(
    "x, y, width, height", [(10, 0, 2, 2), (0, 10, 2, 2), (0, 0, 0, 2), (0, 0, 2, -1)]
)
def test_sim_camera_roi_processing_extracts_empty_roi(roi_processing, x, y, width, height):
    """Test that out-of-bounds or non-positive ROIs produce empty arrays."""
    roi_processing.update_received.put(_roi_config_message(x=x, y=y, width=width, height=height))

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
    assert roi_processing._roi_config.x == 3
    assert roi_processing._roi_config.y == 4
    assert roi_processing._roi_config.width == 5
    assert roi_processing._roi_config.height == 6
    assert roi_processing.selected_operations.get() == ["basic_statistics"]


def test_roi_configuration_message_for_other_signal_is_ignored(roi_processing):
    """Test that ROI configuration messages are scoped to the matching signal."""
    initial_x = roi_processing._roi_config.x
    message = _roi_config_message(signal="other_roi_processing", x=99)

    roi_processing._receive_roi_configuration_message(SimpleNamespace(value=message))

    assert roi_processing._roi_config.x == initial_x


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
    assert roi_processing._roi_config.x == 7
    assert roi_processing._roi_config.width == 8


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
    roi.update_received.put(_roi_config_message(x=1, y=2, width=3, height=2))

    image = camera_with_roi.image.get()

    assert image.shape == (6, 6)
    assert _scalar_result_values(roi) == {"sum": 30.0, "mean": 5.0, "min": 5.0, "max": 5.0}


def test_sim_camera_image_update_does_not_publish_when_roi_inactive(roi_processing):
    """Test inactive ROI processing ignores image updates."""
    roi_processing.active.put(False)

    roi_processing._on_image_update(np.ones((3, 3)))

    assert roi_processing.result_scalar.get() is None


def test_wait_for_connection_has_no_redis_side_effects():
    """A plain Ophyd root needs no Redis until its ROI hook is dispatched."""
    from ophyd import Component, Device, Signal

    from ophyd_devices.sim.sim_camera import SimCameraROIProcessing

    class PlainCamera(Device):
        image = Component(Signal, value=None)
        roi = Component(SimCameraROIProcessing, "", active=True)

    cam = PlainCamera(name="plain")
    try:
        cam.wait_for_connection(all_signals=True)
        assert cam.roi._connector is None
        assert cam.roi.update_received.connected
        cam.device_manager = DMMock()
        cam.roi.on_connected()
        sent = len(cam.device_manager.connector.message_sent)
        cam.roi.on_connected()
        assert len(cam.device_manager.connector.message_sent) == sent
        assert cam.roi.active.get() is True
    finally:
        cam.destroy()


def test_roi_connection_retry_does_not_duplicate_subscriptions():
    """A failed metadata publication can be retried without registering twice."""
    from unittest import mock

    cam = SimCamera(name="retry", device_manager=DMMock())
    try:
        cam.wait_for_connection()
        roi = cam.roi_processing
        connector = cam.device_manager.connector
        with (
            mock.patch.object(connector, "register", wraps=connector.register) as register,
            mock.patch.object(
                roi, "_publish_available_analysis", side_effect=[RuntimeError("publish"), None]
            ),
        ):
            with pytest.raises(RuntimeError, match="publish"):
                roi.on_connected()
            roi.on_connected()
            roi.on_connected()
            assert register.call_count == 2  # One scan-status and one ROI-config callback.
    finally:
        cam.destroy()


def test_current_configuration_published_at_connection(roi_processing):
    from bec_lib.endpoints import MessageEndpoints

    connector = roi_processing.root.device_manager.connector
    configs = [
        item["msg"]
        for item in connector.message_sent
        if isinstance(item["msg"], messages.ROIConfigurationMessage)
    ]
    assert configs[-1].roi_config.x == roi_processing._roi_config.x
    assert configs[-1].active == roi_processing.active.get()
    assert configs[-1].metadata["timestamp"] > 0
    assert MessageEndpoints.roi_config_request("cam", "roi", username="test-user").endpoint != (
        MessageEndpoints.roi_config("cam", "roi").endpoint
    )


def test_deferred_request_publishes_only_when_applied(roi_processing):
    connector = roi_processing.root.device_manager.connector
    connector.message_sent.clear()
    roi_processing.update_received.block_updates()
    roi_processing._receive_roi_configuration_message(
        SimpleNamespace(value=_roi_config_message(x=13))
    )
    assert not any(
        isinstance(item["msg"], messages.ROIConfigurationMessage) for item in connector.message_sent
    )
    roi_processing.update_received.unblock_updates()
    configs = [
        item["msg"]
        for item in connector.message_sent
        if isinstance(item["msg"], messages.ROIConfigurationMessage)
    ]
    assert len(configs) == 1
    assert configs[0].roi_config.x == 13


def test_failed_backend_update_does_not_publish_current(roi_processing, monkeypatch):
    connector = roi_processing.root.device_manager.connector
    connector.message_sent.clear()

    def fail(*args, **kwargs):
        raise RuntimeError("backend failed")

    monkeypatch.setattr(roi_processing, "_on_config_update", fail)
    with pytest.raises(RuntimeError, match="backend failed"):
        roi_processing._apply_requested_config(_roi_config_message(x=13))
    assert not any(
        isinstance(item["msg"], messages.ROIConfigurationMessage) for item in connector.message_sent
    )


def test_roi_requests_subscribe_and_unsubscribe_all_users():
    """
    Use a user wildcard pattern, scoped to this device and ROI, for the full lifecycle.
    """
    from unittest import mock

    from bec_lib.endpoints import MessageEndpoints

    cam = SimCamera(name="requests", device_manager=DMMock())
    connector = cam.device_manager.connector
    roi = cam.roi_processing
    endpoint = MessageEndpoints.roi_config_request(
        device=cam.name, signal=roi.dotted_name, username="*"
    )
    try:
        with (
            mock.patch.object(connector, "register", wraps=connector.register) as register,
            mock.patch.object(connector, "unregister", wraps=connector.unregister) as unregister,
        ):
            roi.on_connected()
            register.assert_any_call(patterns=endpoint, cb=roi._receive_roi_configuration_message)
            # Request callbacks must not register the wildcard as a literal topic.
            assert not any(
                call.args and call.args[0] == endpoint for call in register.call_args_list
            )
            roi.destroy()
            unregister.assert_any_call(patterns=endpoint, cb=roi._receive_roi_configuration_message)
    finally:
        cam.destroy()


@pytest.mark.parametrize("deferred", [False, True])
def test_request_failure_propagates_and_preserves_deferred_configuration(roi_processing, deferred):
    """
    A failed application is not a successful set or a discarded queued request.
    """
    from unittest.mock import patch

    roi = roi_processing
    request = _roi_config_message(x=12)
    previous = roi._roi_config.model_copy(deep=True)
    with patch.object(roi, "_on_config_update", side_effect=RuntimeError("backend failed")):
        if deferred:
            roi.update_received.block_updates()
            roi.update_received.put(request)
            with pytest.raises(RuntimeError, match="backend failed"):
                roi.update_received.unblock_updates()
            assert roi.update_received.has_pending_update
            assert roi.update_received.next_config == request
        else:
            status = roi.update_received.set(request)
            with pytest.raises(RuntimeError, match="backend failed"):
                status.wait(timeout=1)
        assert roi._roi_config == previous
    if deferred:
        roi.update_received.unblock_updates()
        assert not roi.update_received.has_pending_update
        assert roi._roi_config == request.roi_config


def test_shared_roi_configuration_preserves_nonrectangular_shape():
    """
    Shared request/publication code handles typed shapes without rectangular mirrors.
    """
    from ophyd import Component

    from ophyd_devices import PSIDeviceBase
    from ophyd_devices.tests.utils import patched_device
    from ophyd_devices.utils.bec_roi_signals.roi_processing import ROIProcessing

    class CircleProcessing(ROIProcessing):
        def get_scalar_outputs(self):
            return []

        def get_waveform_outputs(self):
            return []

        def get_available_analysis_operations(self):
            return []

    class Detector(PSIDeviceBase):
        roi = Component(
            CircleProcessing, "", roi_config={"type": "circle", "x": 1, "y": 2, "radius": 3}
        )

    with patched_device(Detector, name="det", device_manager=DMMock()) as detector:
        roi = detector.roi
        roi.on_connected()
        request = messages.ROIConfigurationMessage(
            device="det",
            signal="roi",
            name="circle",
            active=True,
            roi_config=messages.CircleROIConfig(x=5, y=6, radius=7),
            selected_operations=[],
        )
        roi.update_received.set(request).wait(timeout=1)
        published = [
            item["msg"]
            for item in detector.device_manager.connector.message_sent
            if isinstance(item["msg"], messages.ROIConfigurationMessage)
        ]
        assert published[-1].roi_config == request.roi_config
        assert not any(name in roi.component_names for name in ("x", "y", "width", "height"))


def test_sim_roi_rejects_nonrectangular_initial_configuration():
    """
    Unsupported shapes fail at construction rather than on the first image.
    """
    from ophyd_devices.sim.sim_camera import SimCameraROIProcessing

    with pytest.raises(TypeError, match="only supports RectROIConfig"):
        SimCameraROIProcessing(name="roi", roi_config=messages.CircleROIConfig(x=1, y=2, radius=3))


@pytest.mark.parametrize(
    "allowed", [[messages.CircleROIConfig], [messages.RectROIConfig, messages.CircleROIConfig]]
)
def test_sim_roi_cannot_enable_unsupported_shape_types(allowed):
    """
    Component arguments cannot widen the simulated backend's shape support.
    """
    from ophyd_devices.sim.sim_camera import SimCameraROIProcessing

    with pytest.raises(ValueError, match="only supports RectROIConfig"):
        SimCameraROIProcessing(name="roi", allowed_roi_config_types=allowed)


@pytest.mark.parametrize("locked", [False, True])
def test_sim_roi_rejects_nonrectangular_updates_before_queueing(roi_processing, locked):
    """
    Invalid shapes neither replace the rectangle nor enter the deferred request queue.
    """
    roi = roi_processing
    original = roi._roi_config.model_copy(deep=True)
    request = _roi_config_message()
    request.roi_config = messages.CircleROIConfig(x=1, y=2, radius=3)
    if locked:
        roi.update_received.block_updates()
    with pytest.raises(TypeError, match="only supports RectROIConfig"):
        roi.update_received.set(request).wait(timeout=1)
    assert roi._roi_config == original
    assert not roi.update_received.has_pending_update
    roi._extract_roi(np.ones((10, 10)))


@pytest.mark.parametrize("method", ["put", "set"])
def test_direct_processing_selection_cannot_change_during_scan(roi_processing, method):
    """
    Operation selection is protected just like ROI enablement and name.
    """
    roi = roi_processing
    previous = roi.selected_operations.get()
    roi.update_received.block_updates(owner="scan")
    with pytest.raises(RuntimeError, match="ROI configuration is locked"):
        result = getattr(roi.selected_operations, method)([], force=True)
        if method == "set":
            result.wait(timeout=1)
    assert roi.selected_operations.get() == previous
    update = _roi_config_message(selected_operations=["basic_statistics"])
    roi.update_received.set(update).wait(timeout=1)
    assert roi.update_received.has_pending_update
    roi.update_received.unblock_updates(owner="scan")
    assert roi.selected_operations.get() == ["basic_statistics"]
