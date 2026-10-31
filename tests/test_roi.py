"""Configuration-only ROI components forward typed shapes without processing machinery."""

from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest
from bec_lib.messages import CircleROIConfig, RectROIConfig, ROIConfigurationMessage
from bec_server.device_server.tests.utils import DMMock
from ophyd import Component, Device

from ophyd_devices.utils.bec_roi_signals import ROI


class BackendROI(ROI):
    """Example backend: send the full configuration before recording applied state."""

    def _on_config_update(self, value: ROIConfigurationMessage, **kwargs) -> None:
        self.validate_configuration(value)
        self.parent.backend.set_roi(value)
        super()._on_config_update(value, **kwargs)


class Detector(Device):
    roi = Component(
        BackendROI, "", roi_config={"type": "rect", "x": 1, "y": 2, "width": 3, "height": 4}
    )


@pytest.fixture
def detector():
    device = Detector(name="det")
    device.device_manager = DMMock()
    device.backend = Mock()
    try:
        device.roi.on_connected()
        yield device
    finally:
        device.roi.destroy()
        device.destroy()


def request(shape=None, **kwargs):
    return ROIConfigurationMessage(
        device="det",
        signal="roi",
        name="backend roi",
        active=True,
        roi_config=shape or CircleROIConfig(x=5, y=6, radius=7),
        selected_operations=[],
        **kwargs,
    )


def test_configuration_only_roi_initializes_backend_without_processing(detector):
    roi = detector.roi
    detector.backend.set_roi.assert_called_once()
    initial = detector.backend.set_roi.call_args.args[0]
    assert not initial.active
    assert initial.roi_config == RectROIConfig(x=1, y=2, width=3, height=4)
    assert initial.selected_operations == []
    for name in (
        "result_scalar",
        "result_waveform",
        "available_operations",
        "selected_operations",
        "get_scalar_outputs",
        "get_waveform_outputs",
        "get_available_analysis_operations",
    ):
        assert not hasattr(roi, name)
    roi.on_connected()
    detector.backend.set_roi.assert_called_once()


def test_configuration_only_roi_applies_and_publishes_full_shape(detector):
    roi = detector.roi
    update = request()
    roi._receive_roi_configuration_message(SimpleNamespace(value=update))
    detector.backend.set_roi.assert_called_with(update)
    published = detector.device_manager.connector.message_sent[-1]["msg"]
    assert published.roi_config == update.roi_config
    assert published.selected_operations == []
    assert published.signal == "roi"


@pytest.mark.parametrize("deferred", [False, True])
def test_device_metadata_refresh_after_typed_roi_request(detector, deferred):
    """Accepted command messages stay describable during later BEC config updates."""
    from bec_server.device_server.devices.device_serializer import get_device_info

    roi = detector.roi
    signal = roi.update_received
    get_device_info(detector)
    if deferred:
        signal.block_updates()
    update = request()
    signal.set(update).wait(timeout=1)
    if deferred:
        signal.unblock_updates()

    assert signal.get() is update
    descriptor = signal.describe()[signal.name]
    assert descriptor == {"source": signal.source_name, "dtype": "array", "shape": []}
    info = get_device_info(detector)
    assert info["signals"]["roi.update_received"]["describe"] == descriptor

    roi.roi_name.set("renamed ROI").wait(timeout=1)
    refreshed = get_device_info(detector)
    assert refreshed["signals"]["roi.update_received"]["describe"] == descriptor
    assert roi.geometry.radius.get() == update.roi_config.radius


def test_configuration_only_roi_defers_scans_and_propagates_failures(detector):
    roi = detector.roi
    detector.backend.reset_mock()
    roi.update_received.block_updates()
    update = request()
    roi.update_received.put(update)
    detector.backend.set_roi.assert_not_called()
    detector.backend.set_roi.side_effect = RuntimeError("backend unavailable")
    with pytest.raises(RuntimeError, match="backend unavailable"):
        roi.update_received.unblock_updates()
    assert roi.update_received.next_config == update
    assert isinstance(roi._roi_config, RectROIConfig)
    detector.backend.set_roi.side_effect = None
    roi.update_received.unblock_updates()
    assert roi._roi_config == update.roi_config
    detector.backend.set_roi.side_effect = RuntimeError("backend unavailable")
    with pytest.raises(RuntimeError, match="backend unavailable"):
        roi.update_received.set(request(RectROIConfig(x=9, y=8, width=7, height=6))).wait(timeout=1)
    assert roi._roi_config == update.roi_config


def test_configuration_only_roi_rejects_processing_operations_before_backend(detector):
    detector.backend.reset_mock()
    update = request().model_copy(update={"selected_operations": ["basic_statistics"]})
    with pytest.raises(ValueError, match="does not support analysis"):
        detector.roi.update_received.set(update).wait(timeout=1)
    detector.backend.set_roi.assert_not_called()


@pytest.mark.parametrize("allowed", [[RectROIConfig], [RectROIConfig, CircleROIConfig], None])
def test_allowed_roi_config_types_are_component_arguments(allowed):
    class RestrictedDetector(Device):
        roi = Component(BackendROI, "", allowed_roi_config_types=allowed)

    device = RestrictedDetector(name="det")
    device.device_manager = DMMock()
    device.backend = Mock()
    try:
        device.roi.on_connected()
        device.backend.reset_mock()
        if allowed == [RectROIConfig]:
            device.roi.update_received.block_updates()
            with pytest.raises(TypeError, match="only supports RectROIConfig"):
                device.roi.update_received.set(request()).wait(timeout=1)
            assert not device.roi.update_received.has_pending_update
            device.backend.set_roi.assert_not_called()
        else:
            device.roi.update_received.set(request()).wait(timeout=1)
            device.backend.set_roi.assert_called_with(request())
    finally:
        device.roi.destroy()
        device.destroy()


def test_allowed_roi_config_types_validate_initial_configuration():
    with pytest.raises(TypeError, match="only supports RectROIConfig"):
        ROI(
            name="roi",
            roi_config=CircleROIConfig(x=1, y=2, radius=3),
            allowed_roi_config_types=[RectROIConfig],
        )


@pytest.mark.parametrize("allowed", [[], ["rect"], [object]])
def test_invalid_allowed_roi_config_types_are_rejected(allowed):
    with pytest.raises((TypeError, ValueError), match="allowed_roi_config_types"):
        ROI(name="roi", allowed_roi_config_types=allowed)


def test_geometry_is_readonly_configuration_before_connection():
    """
    Geometry can be described and saved without connecting a backend or taking a frame.
    """
    from ophyd.utils import ReadOnlyError

    detector = Detector(name="cold")
    try:
        roi = detector.roi
        expected = {"type": "rect", "x": 1, "y": 2, "width": 3, "height": 4}
        configuration = detector.read_configuration()
        description = detector.describe_configuration()
        for name, value in expected.items():
            field = getattr(roi.geometry, name)
            assert configuration[field.name]["value"] == value
            assert description[field.name]["dtype"] == ("string" if name == "type" else "number")
            assert not field.write_access
            for method in (field.put, field.set):
                with pytest.raises(ReadOnlyError):
                    method(value)
    finally:
        detector.destroy()


@pytest.mark.parametrize(
    "shape", [RectROIConfig(x=8, y=9, width=10, height=11), CircleROIConfig(x=5, y=6, radius=7)]
)
def test_geometry_configuration_tracks_applied_shapes(detector, shape):
    """
    Configuration stores the complete applied shape and does not expose pending edits.
    """
    roi = detector.roi
    previous = roi.geometry.read_configuration()
    roi.update_received.block_updates()
    update = request(shape)
    roi.update_received.set(update).wait(timeout=1)
    np.testing.assert_equal(roi.geometry.read_configuration(), previous)
    roi.update_received.unblock_updates()
    configuration = detector.read_configuration()
    for name, value in shape.model_dump().items():
        assert configuration[getattr(roi.geometry, name).name]["value"] == value


def test_failed_backend_update_preserves_geometry_configuration(detector):
    """
    A rejected backend update must not enter saved scan configuration.
    """
    roi = detector.roi
    previous = roi.geometry.read_configuration()
    detector.backend.set_roi.side_effect = RuntimeError("backend rejected shape")
    with pytest.raises(RuntimeError, match="backend rejected shape"):
        roi.update_received.set(request()).wait(timeout=1)
    np.testing.assert_equal(roi.geometry.read_configuration(), previous)


@pytest.mark.parametrize("first_release", ["scan", "capture"])
def test_independent_scan_and_capture_locks_hold_pending_configuration(detector, first_release):
    """
    Neither scan completion nor capture shutdown can release another owner's lock.
    """
    roi = detector.roi
    detector.backend.reset_mock()
    previous = roi.geometry.read_configuration()
    roi.update_received.block_updates(owner="scan")
    roi.update_received.block_updates(owner="capture")
    roi.update_received.put(request())
    assert roi.update_received.unblock_updates(owner=first_release) is None
    assert roi.update_received.updates_blocked
    np.testing.assert_equal(roi.geometry.read_configuration(), previous)
    detector.backend.set_roi.assert_not_called()
    other = "capture" if first_release == "scan" else "scan"
    roi.update_received.unblock_updates(owner=other)
    assert not roi.update_received.updates_blocked
    detector.backend.set_roi.assert_called_once()
    assert roi._roi_config == request().roi_config


@pytest.mark.parametrize("status", ["open", "paused"])
def test_connecting_roi_during_existing_scan_blocks_requests(status):
    """
    Read the stored scan status after subscribing rather than waiting for a new event.
    """
    from unittest.mock import patch

    from bec_lib.messages import ScanStatusMessage

    device = Detector(name="det")
    device.device_manager = DMMock()
    device.backend = Mock()
    scan = ScanStatusMessage.model_construct(status=status)
    try:
        with patch.object(device.device_manager.connector, "get", return_value=scan):
            device.roi.on_connected()
        device.backend.reset_mock()
        device.roi.update_received.put(request())
        assert device.roi.update_received.updates_blocked
        device.backend.set_roi.assert_not_called()
        device.roi.update_received._handle_scan_status_update(
            SimpleNamespace(value=ScanStatusMessage.model_construct(status="closed"))
        )
        device.backend.set_roi.assert_called_once()
    finally:
        device.destroy()


@pytest.mark.parametrize("signal_name,value", [("active", True), ("roi_name", "new name")])
@pytest.mark.parametrize("method", ["put", "set"])
def test_direct_roi_setting_writes_cannot_bypass_scan_lock(detector, signal_name, value, method):
    """
    Direct put and set fail before changing local state, even with force=True.
    """
    roi = detector.roi
    signal = getattr(roi, signal_name)
    previous = signal.get()
    roi.update_received.block_updates(owner="scan")
    with pytest.raises(RuntimeError, match="ROI configuration is locked"):
        result = getattr(signal, method)(value, force=True)
        if method == "set":
            result.wait(timeout=1)
    assert signal.get() == previous


def test_explicit_scan_override_still_applies_a_complete_validated_request(detector):
    """
    The existing request-level opt-out remains explicit and does not release locks.
    """
    roi = detector.roi
    roi.update_received.block_updates(owner="scan")
    update = request(block_while_scanning=False)
    roi.update_received.set(update).wait(timeout=1)
    assert roi._roi_config == update.roi_config
    assert roi.active.get()
    assert roi.update_received.updates_blocked


def test_geometry_fields_are_limited_to_allowed_schemas():
    """
    Rectangle-only ROIs expose just their five fields, independently of other ROIs.
    """
    restricted = ROI(name="rect", allowed_roi_config_types=[RectROIConfig])
    flexible = ROI(name="flexible", allowed_roi_config_types=[RectROIConfig, CircleROIConfig])
    try:
        assert restricted.geometry.component_names == ("type", "x", "y", "width", "height")
        assert flexible.geometry.component_names == ("type", "x", "y", "width", "height", "radius")
        assert not hasattr(restricted.geometry, "radius")
        assert restricted.geometry.x.describe()[restricted.geometry.x.name]["dtype"] == "integer"
    finally:
        restricted.destroy()
        flexible.destroy()


@pytest.mark.parametrize("shape_name", ["pixelmap", "polygon"])
def test_geometry_arrays_are_native_readonly_configuration(shape_name, detector):
    """
    Masks and vertices remain numeric arrays and can be written directly to HDF5.
    """
    import h5py
    from bec_lib.messages import CustomAnchorROIConfig, PixelMapROIConfig

    if shape_name == "pixelmap":
        shape = PixelMapROIConfig(mask=np.array([[True, False], [False, True]]))
        field_name, expected = "mask", np.array(shape.mask, dtype=bool)
    else:
        shape = CustomAnchorROIConfig(vertices=np.array([[0.0, 0.0], [1.0, 0.0], [1.0, 1.0]]))
        field_name, expected = "vertices", np.array(shape.vertices, dtype=float)
    roi = detector.roi
    original_fields = roi.geometry.component_names
    roi.update_received.set(request(shape)).wait(timeout=1)
    field = getattr(roi.geometry, field_name)
    value = detector.read_configuration()[field.name]["value"]
    assert isinstance(value, np.ndarray)
    np.testing.assert_array_equal(value, expected)
    assert roi.geometry.component_names == original_fields
    description = detector.describe_configuration()[field.name]
    assert description["dtype"] == "array"
    assert description["shape"] == list(expected.shape)
    assert not field.write_access
    with h5py.File("geometry", "w", driver="core", backing_store=False) as output:
        output.create_dataset(field.name, data=value)
        np.testing.assert_array_equal(output[field.name][()], expected)


def test_switching_geometry_clears_fields_absent_from_new_shape(detector):
    """
    A fixed field layout must not retain stale coordinates from a previous shape.
    """
    roi = detector.roi
    fields = roi.geometry.component_names
    roi.update_received.set(request(CircleROIConfig(x=1, y=2, radius=3))).wait(timeout=1)
    assert roi.geometry.radius.get() == 3
    assert roi.geometry.width.get() == 0
    roi.update_received.set(request(RectROIConfig(x=4, y=5, width=6, height=7))).wait(timeout=1)
    assert roi.geometry.radius.get() == 0
    assert roi.geometry.width.get() == 6
    assert roi.geometry.type.get() == "rect"
    assert roi.geometry.component_names == fields


@pytest.mark.parametrize(
    "field,value,key", [("active", True, "active"), ("roi_name", "renamed", "name")]
)
@pytest.mark.parametrize("method", ["put", "set"])
def test_direct_setting_applies_complete_configuration(detector, field, value, key, method):
    """
    Individual settings use the same backend and publication path as full requests.
    """
    roi = detector.roi
    detector.backend.reset_mock()
    previous = roi._configuration_message()
    result = getattr(getattr(roi, field), method)(value)
    if method == "set":
        result.wait(timeout=1)
    detector.backend.set_roi.assert_called_once()
    applied = detector.backend.set_roi.call_args.args[0]
    expected = previous.model_dump()
    expected[key] = value
    assert applied.model_dump(exclude={"metadata"}) == ROIConfigurationMessage.model_validate(
        expected
    ).model_dump(exclude={"metadata"})
    assert getattr(roi, field).get() == value
    assert detector.device_manager.connector.message_sent[-1]["msg"].model_dump(
        exclude={"metadata"}
    ) == applied.model_dump(exclude={"metadata"})


@pytest.mark.parametrize("field,value", [("active", True), ("roi_name", "rejected")])
@pytest.mark.parametrize("method", ["put", "set"])
def test_direct_setting_preserves_applied_state_on_backend_failure(detector, field, value, method):
    """
    Backend failures propagate without recording or publishing the proposed setting.
    """
    roi = detector.roi
    previous = roi._configuration_message()
    sent = detector.device_manager.connector.message_sent
    sent.clear()
    detector.backend.set_roi.side_effect = TimeoutError("backend write failed")
    with pytest.raises(TimeoutError, match="backend write failed"):
        result = getattr(getattr(roi, field), method)(value)
        if method == "set":
            result.wait(timeout=1)
    assert roi._configuration_message().model_dump(exclude={"metadata"}) == previous.model_dump(
        exclude={"metadata"}
    )
    assert not sent


@pytest.mark.parametrize("direct_setting", [False, True])
def test_new_successful_request_supersedes_failed_deferred_request(detector, direct_setting):
    """
    A failed queued edit must never reappear after a newer edit has reached the backend.
    """
    roi = detector.roi
    requests = roi.update_received
    requests.block_updates()
    requests.put(request(RectROIConfig(x=1, y=2, width=3, height=4)))
    detector.backend.set_roi.side_effect = TimeoutError("backend offline")
    with pytest.raises(TimeoutError, match="backend offline"):
        requests.unblock_updates()
    assert requests.has_pending_update
    detector.backend.set_roi.side_effect = None
    if direct_setting:
        roi.roi_name.set("newer edit").wait(timeout=1)
    else:
        requests.set(request(RectROIConfig(x=99, y=2, width=3, height=4))).wait(timeout=1)
    applied = roi._configuration_message().model_dump(exclude={"metadata"})
    detector.backend.reset_mock()
    assert not requests.has_pending_update
    assert requests.next_config is None
    requests.unblock_updates()
    requests.block_updates(owner="scan")
    requests.unblock_updates(owner="scan")
    detector.backend.set_roi.assert_not_called()
    assert roi._configuration_message().model_dump(exclude={"metadata"}) == applied


def test_failed_newer_request_keeps_previous_deferred_request_for_retry(detector):
    """
    Supersession happens after successful application, never after a rejected edit.
    """
    requests = detector.roi.update_received
    requests.block_updates()
    previous = request()
    requests.put(previous)
    detector.backend.set_roi.side_effect = TimeoutError("offline")
    with pytest.raises(TimeoutError):
        requests.unblock_updates()
    with pytest.raises(TimeoutError):
        requests.put(request(RectROIConfig(x=99, y=2, width=3, height=4)))
    assert requests.next_config == previous
    assert requests.has_pending_update


def test_roi_destroy_finishes_children_when_request_unregistration_fails(detector):
    """
    Redis failure on one channel must not skip the scan subscription or native children.
    """
    from unittest.mock import patch

    from bec_lib.endpoints import MessageEndpoints

    connector = detector.device_manager.connector
    original = connector.unregister
    calls = []

    def unregister(*args, **kwargs):
        endpoint = kwargs.get("patterns", args[0] if args else None)
        calls.append(endpoint)
        if endpoint == MessageEndpoints.scan_status():
            return original(*args, **kwargs)
        raise RuntimeError("request unsubscribe failed")

    with (
        patch.object(connector, "unregister", side_effect=unregister),
        pytest.raises(RuntimeError, match="request unsubscribe failed"),
    ):
        detector.roi.destroy()
    assert MessageEndpoints.scan_status() in calls
    assert detector.roi._destroyed
    assert detector.roi.geometry._destroyed
    assert detector.roi.update_received._destroyed


def test_request_signal_is_destroyed_even_when_scan_unregistration_fails(detector):
    """
    A failing scan-status unsubscribe must still release native signal resources.
    """
    from unittest.mock import patch

    with (
        patch.object(
            detector.device_manager.connector,
            "unregister",
            side_effect=RuntimeError("Redis unavailable"),
        ),
        pytest.raises(RuntimeError, match="Redis unavailable"),
    ):
        detector.roi.update_received.destroy()
    assert detector.roi.update_received._destroyed
    assert detector.roi.update_received._connector is None


@pytest.mark.parametrize("signal_name", ["active", "update_received"])
@pytest.mark.parametrize("error_name", ["WaitTimeoutError", "StatusTimeoutError"])
def test_roi_set_reports_reserved_backend_timeouts(detector, signal_name, error_name):
    from ophyd.utils import errors

    original = getattr(errors, error_name)("backend acknowledgement timed out")
    detector.backend.set_roi.side_effect = original
    signal = getattr(detector.roi, signal_name)
    value = False if signal_name == "active" else request()
    status = signal.set(value)
    with pytest.raises(TimeoutError, match="backend acknowledgement timed out") as caught:
        status.wait(timeout=1)
    assert caught.value.__cause__ is original
