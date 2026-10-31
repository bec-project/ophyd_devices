"""Tests for ROI processing signals."""

# pylint: disable=protected-access,redefined-outer-name,too-many-arguments

from types import SimpleNamespace

import numpy as np
import pytest
from bec_lib import messages
from bec_server.device_server.tests.utils import DMMock
from ophyd import Component, Kind

from ophyd_devices import PSIDeviceBase
from ophyd_devices.utils.bec_roi_signals import ROIProcessing


class MockROIProcessing(ROIProcessing):
    def get_scalar_outputs(self):
        return ["sum", "mean", "min", "max"]

    def get_waveform_outputs(self):
        return []

    def get_available_analysis_operations(self):
        return ["basic_statistics"]


class Detector(PSIDeviceBase):
    roi_processing = Component(
        MockROIProcessing,
        "",
        active=True,
        roi_config={"type": "rect", "x": 25, "y": 25, "width": 50, "height": 50},
        selected_operations=["basic_statistics"],
    )


@pytest.fixture(scope="function")
def camera_with_roi(name="camera"):
    """Fixture for a detector with ROI processing connected."""
    dm = DMMock()
    cam = Detector(name=name, device_manager=dm)
    cam.wait_for_connection()
    cam.roi_processing.on_connected()
    yield cam
    cam.destroy()


@pytest.fixture(scope="function")
def roi_processing(camera_with_roi):
    """Fixture for the detector ROI processing signal."""
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


def test_selected_operations_reject_unknown_operation(roi_processing):
    """Test that selected operations are validated against the available operations."""
    with pytest.raises(ValueError, match="Invalid operation"):
        roi_processing.selected_operations.put(["does_not_exist"])


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


def test_wait_for_connection_has_no_redis_side_effects():
    """A plain Ophyd root needs no Redis until its ROI hook is dispatched."""
    from ophyd import Device

    class PlainCamera(Device):
        roi = Component(MockROIProcessing, "", active=True)

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

    cam = Detector(name="retry", device_manager=DMMock())
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

    cam = Detector(name="requests", device_manager=DMMock())
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


@pytest.fixture
def single_output_roi():
    """A backend declaring one scalar and one waveform, without a Redis connection."""
    from ophyd import Component, Device

    from ophyd_devices.utils.bec_roi_signals import ROIProcessing

    class SingleOutputROI(ROIProcessing):
        def get_scalar_outputs(self):
            return ["counts"]

        def get_waveform_outputs(self):
            return ["spectrum"]

        def get_available_analysis_operations(self):
            return ["spectroscopy"]

    class Detector(Device):
        roi = Component(SingleOutputROI, "")

    detector = Detector(name="detector")
    try:
        yield detector.roi
    finally:
        detector.roi.destroy()
        detector.destroy()


@pytest.mark.filterwarnings("error:BECMessageSignal.signals is deprecated:DeprecationWarning")
def test_result_schema_metadata_event_advertises_final_output_names(single_output_roi):
    roi = single_output_roi
    for signal in (roi.result_scalar, roi.result_waveform):
        events = []
        token = signal.subscribe(
            lambda *, value, **_: events.append(value),
            event_type=signal.SUB_SIGNAL_INFO_CHANGED,
            run=True,
        )
        try:
            assert len(events) == 1
            assert events[0].signals == [(signal.name, Kind.hinted.value)]
        finally:
            signal.unsubscribe(token)


def test_put_results_publishes_single_scalar_and_waveform_outputs(single_output_roi):
    """Short result names work for both streams while their public signal names stay stable."""
    roi = single_output_roi
    scalar = {"counts": {"value": 3.0, "timestamp": 1.0}}
    roi.put_results("scalar", scalar)
    assert roi.result_scalar.get().signals == {roi.result_scalar.name: scalar["counts"]}
    assert list(scalar) == ["counts"]

    waveform = np.array([1.0, 2.0, 3.0])
    append = {"type": "add", "max_shape": [None, 3]}
    roi.put_results(
        "waveform", {"spectrum": {"value": waveform, "timestamp": 2.0}}, async_update=append
    )
    message = roi.result_waveform.get()
    assert list(message.signals) == [roi.result_waveform.name]
    np.testing.assert_array_equal(message.signals[roi.result_waveform.name]["value"], waveform)
    assert message.metadata["async_update"] == append
    assert message.signals[roi.result_waveform.name]["timestamp"] == 2.0


@pytest.mark.parametrize(
    "kind,results,message",
    [
        ("scalar", {"unknown": {"value": 1, "timestamp": 0}}, "Unknown scalar result"),
        ("waveform", {"unknown": {"value": [1], "timestamp": 0}}, "Unknown waveform result"),
        ("image", {}, "Unknown result kind"),
    ],
)
def test_put_results_rejects_unknown_names_and_streams(single_output_roi, kind, results, message):
    with pytest.raises(ValueError, match=message):
        single_output_roi.put_results(kind, results)
    assert single_output_roi.result_scalar.get() is None
    assert single_output_roi.result_waveform.get() is None


def test_put_results_empty_updates_do_not_publish(single_output_roi):
    single_output_roi.put_results("scalar", {})
    single_output_roi.put_results("waveform", {})
    assert single_output_roi.result_scalar.get() is None
    assert single_output_roi.result_waveform.get() is None


def test_put_results_keeps_multi_output_schema_validation(roi_processing):
    """A partial update keeps existing prefixing and the default append metadata."""
    payload = {"sum": {"value": 7.0, "timestamp": 1.0}}
    roi_processing.put_results("scalar", payload)
    message = roi_processing.result_scalar.get()
    assert message.signals == {f"{roi_processing.result_scalar.name}_sum": payload["sum"]}
    assert message.metadata["async_update"] == {"type": "add", "max_shape": [None]}
    assert list(payload) == ["sum"]
    with pytest.raises(ValueError, match="Unknown scalar result"):
        roi_processing.put_results("scalar", {"counts": {"value": 1, "timestamp": 0}})
