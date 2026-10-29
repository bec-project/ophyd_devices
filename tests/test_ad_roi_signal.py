"""Tests for configurable AreaDetector ROI and Stats plugin instances."""

import numpy as np
import pytest
from bec_server.device_server.tests.utils import DMMock
from ophyd import Component as Cpt
from ophyd import Device, Signal

from ophyd_devices import PSIDeviceBase
from ophyd_devices.tests.utils import patched_device
from ophyd_devices.utils.bec_roi_signals.ad_roi_signal import ADROIProcessing


class Camera(Device):
    """Minimal camera port for testing plugin routing."""

    port_name = Cpt(Signal, value="CAM")


@pytest.mark.parametrize(
    "kwargs, roi_suffix, stats_suffix",
    [
        ({}, "ROI1:", "Stats1:"),
        ({"roi_suffix": "ROI2:", "stats_suffix": "Stats2:"}, "ROI2:", "Stats2:"),
        ({"roi_suffix": "Crop3:", "stats_suffix": "Analysis5:"}, "Crop3:", "Analysis5:"),
    ],
)
def test_plugin_suffixes(kwargs, roi_suffix, stats_suffix):
    """Suffixes select the actual plugin PVs while preserving existing defaults."""

    class Detector(PSIDeviceBase):
        cam = Cpt(Camera, "")
        processing = Cpt(ADROIProcessing, "", **kwargs)

    with patched_device(Detector, name="det", prefix="DET:", device_manager=DMMock()) as detector:
        roi = detector.processing
        assert roi.roi1.prefix == f"DET:{roi_suffix}"
        assert roi.stats1.prefix == f"DET:{stats_suffix}"
        assert roi.roi1.min_xyz.min_x.pvname == f"DET:{roi_suffix}MinX_RBV"
        assert roi.stats1.total.pvname == f"DET:{stats_suffix}Total_RBV"
        assert roi.stats1.ts_acquire.pvname == f"DET:{stats_suffix}TS:TSAcquire"


def test_two_roi_components_have_independent_plugins():
    """Two components resolve their own PVs and apply geometry independently."""

    class Detector(PSIDeviceBase):
        cam = Cpt(Camera, "")
        first = Cpt(
            ADROIProcessing,
            "",
            roi_config={"type": "rect", "x": 100, "y": 0, "width": 10, "height": 10},
        )
        second = Cpt(
            ADROIProcessing,
            "",
            roi_suffix="ROI2:",
            stats_suffix="Stats2:",
            roi_config={"type": "rect", "x": 300, "y": 0, "width": 10, "height": 10},
        )

    with patched_device(Detector, name="det", prefix="DET:", device_manager=DMMock()) as detector:
        first, second = detector.first, detector.second
        assert first.roi1.prefix == "DET:ROI1:"
        assert first.stats1.prefix == "DET:Stats1:"
        assert second.roi1.prefix == "DET:ROI2:"
        assert second.stats1.prefix == "DET:Stats2:"
        assert first.dotted_name == "first"
        assert second.dotted_name == "second"

        first._apply_roi_configuration()
        second._apply_roi_configuration()
        assert first.roi1.min_xyz.min_x.get() == 100
        assert second.roi1.min_xyz.min_x.get() == 300


def test_camera_managed_roi_does_not_capture_or_subscribe_results():
    from unittest import mock

    from ophyd_devices.utils.bec_signals import DynamicSignal

    class Detector(PSIDeviceBase):
        cam = Cpt(Camera, "")
        processing = Cpt(
            ADROIProcessing,
            "",
            manage_capture=False,
            active=True,
            selected_operations=["basic_statistics"],
        )

    with patched_device(Detector, name="det", prefix="DET:", device_manager=DMMock()) as detector:
        try:
            roi = detector.processing
            roi.roi1.nd_array_port.put("TRANS1")
            with mock.patch.object(roi.stats1.ts_acquire, "put") as acquire:
                roi.on_connected()
                assert roi._stats_subscriptions == {}
                assert roi.on_stage() is None
                assert roi.on_trigger() is None
                roi.on_stop()
                acquire.assert_not_called()
            assert isinstance(roi.result_scalar, DynamicSignal)
            assert roi.roi1.nd_array_port.get() == "TRANS1"
            assert roi.stats1.basic_sigma.pvname == "DET:Stats1:Sigma_RBV"
            assert roi.roi1.enable.get(as_string=True) == "Enable"
            assert roi.stats1.enable.get(as_string=True) == "Enable"
            roi.active.put(False)
            assert roi.roi1.enable.get(as_string=True) == "Disable"
            assert roi.stats1.enable.get(as_string=True) == "Disable"
            roi.active.put(True)
            assert roi.roi1.enable.get(as_string=True) == "Enable"
            assert roi.stats1.enable.get(as_string=True) == "Enable"
            assert roi._stats_subscriptions == {}
        finally:
            detector.destroy()


def test_centroid_preview_uses_structured_sigma_signals():
    class Detector(PSIDeviceBase):
        processing = Cpt(ADROIProcessing, "")

    with patched_device(Detector, name="det", prefix="DET:", device_manager=DMMock()) as detector:
        roi = detector.processing
        roi.on_connected()
        roi.selected_operations.put(["centroid"])
        roi.stats1.sigma.x.get = lambda **_: 2.0
        roi.stats1.sigma.y.get = lambda **_: 3.0
        values, names = roi.read_preview_values(io_timeout=1)
        assert values[names.index("sigma_x")] == 2.0
        assert values[names.index("sigma_y")] == 3.0


def test_ioc_readbacks_update_roi_configuration_without_writing_back():
    from unittest.mock import Mock, patch

    class Detector(PSIDeviceBase):
        processing = Cpt(ADROIProcessing, "")

    with patched_device(Detector, name="det", prefix="DET:", device_manager=DMMock()) as detector:
        roi = detector.processing
        readbacks = {
            key: Signal(name=key, value=value)
            for key, value in {
                "x": 15,
                "y": 25,
                "width": 80,
                "height": 60,
                "roi_enabled": 1,
                "stats_enabled": "Enable",
                "basic_statistics": "Yes",
                "centroid": 1,
            }.items()
        }
        roi._ioc_configuration_signals = lambda: readbacks
        roi._publish_configuration = Mock()
        with patch.object(roi, "_apply_stats_enable_signals") as write:
            roi._read_ioc_configuration()
            assert roi._roi_config.model_dump() == {
                "type": "rect",
                "x": 15,
                "y": 25,
                "width": 80,
                "height": 60,
            }
            configuration = detector.read_configuration()
            for name, value in roi._roi_config.model_dump().items():
                field = getattr(roi.geometry, name)
                assert configuration[field.name]["value"] == value
            assert roi.geometry.component_names == ("type", "x", "y", "width", "height")
            assert roi.active.get()
            assert roi.selected_operations.get() == ["basic_statistics", "centroid"]
            write.assert_not_called()
            roi._publish_configuration.assert_called_once()
            roi._read_ioc_configuration()
            roi._publish_configuration.assert_called_once()
            readbacks["roi_enabled"].put(0)
            roi._read_ioc_configuration()
            assert not roi.active.get()
            assert roi.selected_operations.get() == ["basic_statistics", "centroid"]
            write.assert_not_called()


@pytest.mark.parametrize("samples", [[2.0, 4.0], pytest.param(np.array([2.0, 4.0]), id="array")])
@pytest.mark.parametrize("timestamp", [None, 0.0, 12.0])
def test_standalone_roi_averages_frame_arrays(samples, timestamp):
    from types import SimpleNamespace
    from unittest.mock import patch

    class Detector(PSIDeviceBase):
        processing = Cpt(ADROIProcessing, "", active=True, selected_operations=["basic_statistics"])

    with patched_device(Detector, name="det", prefix="DET:", device_manager=DMMock()) as detector:
        roi = detector.processing
        roi.on_connected()
        roi.active.put(True)
        roi.selected_operations.put(["basic_statistics"])
        roi.scan_server_scan_info = SimpleNamespace(positions=[0, 1], frames_per_trigger=2)
        assert roi.manage_capture and roi.average_frames_per_trigger.get()
        with (
            patch.object(roi.result_scalar, "put") as publish,
            patch("ophyd_devices.utils.bec_roi_signals.ad_roi_signal.time", return_value=123.0),
        ):
            roi._on_stats_signal_update(
                operation="basic_statistics",
                result_name="mean_value",
                output_kind="scalar",
                value=samples,
                timestamp=timestamp,
            )
        data = publish.call_args.args[0]["mean_value"]
        assert data == {"value": 3.0, "timestamp": 123.0 if timestamp is None else timestamp}
        assert publish.call_args.kwargs["async_update"]["max_shape"] == [2]


def test_standalone_roi_waveform_average_preserves_pixels():
    from types import SimpleNamespace
    from unittest.mock import patch

    class Detector(PSIDeviceBase):
        processing = Cpt(ADROIProcessing, "")

    with patched_device(Detector, name="det", prefix="DET:", device_manager=DMMock()) as detector:
        roi = detector.processing
        roi.on_connected()
        roi.active.put(True)
        roi.selected_operations.put(["basic_statistics"])
        roi.scan_server_scan_info = SimpleNamespace(positions=[0], frames_per_trigger=2)
        with patch.object(roi.result_waveform, "put") as publish:
            roi._on_stats_signal_update(
                operation="basic_statistics",
                result_name="profile",
                output_kind="waveform",
                value=[[2, 4, 6], [4, 6, 8]],
                timestamp=1.0,
            )
        np.testing.assert_array_equal(publish.call_args.args[0]["profile"]["value"], [3, 5, 7])


def test_direct_roi_edits_publish_confirmed_configuration():
    from bec_lib.messages import ROIConfigurationMessage

    class Detector(PSIDeviceBase):
        processing = Cpt(
            ADROIProcessing,
            "",
            manage_capture=False,
            active=True,
            roi_config={"type": "rect", "x": 0, "y": 0, "width": 100, "height": 100},
            selected_operations=["basic_statistics"],
        )

    with patched_device(Detector, name="det", prefix="DET:", device_manager=DMMock()) as detector:
        roi = detector.processing
        roi.on_connected()
        sent = detector.device_manager.connector.message_sent
        for active, operations in [
            (False, ["basic_statistics"]),
            (True, ["basic_statistics"]),
            (True, ["centroid"]),
        ]:
            sent.clear()
            if roi.active.get() != active:
                roi.active.put(active)
            else:
                roi.selected_operations.put(operations)
            published = [
                item["msg"] for item in sent if isinstance(item["msg"], ROIConfigurationMessage)
            ]
            assert published
            assert published[-1].active == active
            assert published[-1].selected_operations == operations
            assert roi.roi1.enable.get(as_string=True) == ("Enable" if active else "Disable")


@pytest.mark.parametrize("nested", [False, True])
def test_root_destroy_closes_roi_resources_before_signals(nested):
    from unittest.mock import patch

    from bec_lib.endpoints import MessageEndpoints

    class Group(Device):
        processing = Cpt(ADROIProcessing, "", manage_capture=False)

    class Detector(PSIDeviceBase):
        group = Cpt(Group if nested else ADROIProcessing, "")

    with patched_device(Detector, name="det", prefix="DET:", device_manager=DMMock()) as detector:
        roi = detector.group.processing if nested else detector.group
        roi.on_connected()
        connector = detector.device_manager.connector
        with patch.object(connector, "unregister", wraps=connector.unregister) as unregister:
            detector.destroy()
        assert roi._ioc_config_closed
        assert roi._ioc_config_executor._shutdown
        assert not roi._ioc_config_subscriptions
        assert not roi._config_registered
        unregister.assert_any_call(
            patterns=MessageEndpoints.roi_config_request("det", roi.dotted_name, username="*"),
            cb=roi._receive_roi_configuration_message,
        )
        detector.destroy()  # Cleanup is idempotent.


def test_roi_preview_cancels_between_statistic_reads():
    from threading import Event

    from ophyd_devices.interfaces.base_classes.psi_device_base import DeviceStoppedError

    class Detector(PSIDeviceBase):
        processing = Cpt(ADROIProcessing, "")

    with patched_device(Detector, name="det", prefix="DET:", device_manager=DMMock()) as detector:
        roi = detector.processing
        roi.on_connected()
        roi.selected_operations.put(["centroid"])
        stopped = Event()
        calls = []

        def first(**kwargs):
            calls.append("x")
            stopped.set()
            return 1.0

        roi.stats1.centroid.x.get = first
        with pytest.raises(DeviceStoppedError, match="preview stopped"):
            roi.read_preview_values(io_timeout=1, stop_event=stopped)
        assert calls == ["x"]


@pytest.mark.parametrize(
    "shape",
    [
        {"type": "rotated_rect", "x": 1, "y": 2, "width": 3, "height": 4, "angle": 10},
        {"type": "circle", "x": 1, "y": 2, "radius": 3},
        {"type": "ellipse", "x": 1, "y": 2, "width": 3, "height": 4, "angle": 10},
        {"type": "pixelmap", "mask": [[True, False]]},
        {"type": "custom_anchor", "vertices": [(0, 0), (2, 0), (1, 1)]},
    ],
)
@pytest.mark.parametrize("route", ["request", "blocked_request", "direct"])
def test_ad_roi_rejects_nonrectangular_configuration_before_changes(shape, route):
    """
    Unsupported shapes never mutate signals, reach the IOC or replace queued requests.
    """
    from types import SimpleNamespace
    from unittest.mock import Mock, patch

    from bec_lib.messages import RectROIConfig, ROIConfigurationMessage

    class Detector(PSIDeviceBase):
        processing = Cpt(ADROIProcessing, "", manage_capture=False)

    with patched_device(Detector, name="det", prefix="DET:", device_manager=DMMock()) as detector:
        roi = detector.processing
        roi.on_connected()
        request = ROIConfigurationMessage(
            device=detector.name,
            signal=roi.dotted_name,
            name="unsupported",
            active=True,
            roi_config=shape,
            selected_operations=["basic_statistics"],
        )
        before = roi.read_configuration()
        roi._publish_configuration = Mock()
        if route == "blocked_request":
            roi.update_received.block_updates()
            pending = request.model_copy(
                update={"roi_config": RectROIConfig(x=1, y=2, width=3, height=4)}
            )
            roi.update_received.put(pending)
        else:
            pending = None
        with (
            patch.object(roi, "_apply_roi_configuration") as apply,
            pytest.raises(TypeError, match="only supports RectROIConfig"),
        ):
            if route == "direct":
                roi._on_config_update(request)
            else:
                roi._receive_roi_configuration_message(SimpleNamespace(value=request))
        np.testing.assert_equal(roi.read_configuration(), before)
        assert roi.update_received.next_config == pending
        apply.assert_not_called()
        roi._publish_configuration.assert_not_called()


@pytest.mark.parametrize("tagged", [False, True])
def test_ad_roi_accepts_rectangular_configuration(tagged):
    """
    Both typed rectangle payloads and legacy untagged rectangles configure the IOC.
    """
    from bec_lib.messages import RectROIConfig, ROIConfigurationMessage

    class Detector(PSIDeviceBase):
        processing = Cpt(ADROIProcessing, "", manage_capture=False)

    with patched_device(Detector, name="det", prefix="DET:", device_manager=DMMock()) as detector:
        roi = detector.processing
        roi.on_connected()
        geometry = {"x": 10, "y": 20, "width": 30, "height": 40}
        request = ROIConfigurationMessage(
            device=detector.name,
            signal=roi.dotted_name,
            name="rectangle",
            active=True,
            roi_config=RectROIConfig(**geometry) if tagged else geometry,
            selected_operations=["basic_statistics"],
        )
        roi._apply_requested_config(request)
        assert isinstance(request.roi_config, RectROIConfig)
        assert {
            key: signal.get()
            for key, signal in roi._ioc_configuration_signals().items()
            if key in geometry
        } == geometry


def test_complete_roi_request_updates_ioc_and_publishes_shape_without_mirrors():
    """
    One request configures the plugin and publishes the complete applied rectangle.
    """
    from bec_lib.messages import RectROIConfig, ROIConfigurationMessage

    class Detector(PSIDeviceBase):
        processing = Cpt(ADROIProcessing, "", manage_capture=False)

    with patched_device(Detector, name="det", prefix="DET:", device_manager=DMMock()) as detector:
        roi = detector.processing
        roi.on_connected()
        detector.device_manager.connector.message_sent.clear()
        request = ROIConfigurationMessage(
            device="det",
            signal="processing",
            name="rectangle",
            active=True,
            roi_config=RectROIConfig(x=20, y=30, width=80, height=60),
            selected_operations=["basic_statistics"],
        )
        roi.update_received.set(request).wait(timeout=1)
        for key, value in request.roi_config.model_dump(exclude={"type"}).items():
            assert roi._ioc_configuration_signals()[key].get() == value
            assert not hasattr(roi, key)
        published = [
            item["msg"]
            for item in detector.device_manager.connector.message_sent
            if isinstance(item["msg"], ROIConfigurationMessage)
        ]
        assert published[-1].roi_config == request.roi_config


def test_stopping_capture_keeps_scan_owned_roi_configuration_locked():
    """
    Capture shutdown must not apply a queued edit while the scan remains open.
    """
    from unittest.mock import Mock, patch

    from bec_lib.messages import RectROIConfig, ROIConfigurationMessage

    class Detector(PSIDeviceBase):
        processing = Cpt(ADROIProcessing, "", manage_capture=False)

    with patched_device(Detector, name="det", prefix="DET:", device_manager=DMMock()) as detector:
        roi = detector.processing
        roi.on_connected()
        roi.update_received.block_updates(owner="scan")
        roi.update_received.block_updates(owner="capture")
        previous = roi.geometry.read_configuration()
        request = ROIConfigurationMessage(
            device="det",
            signal="processing",
            name="queued",
            active=True,
            roi_config=RectROIConfig(x=5, y=6, width=7, height=8),
            selected_operations=["basic_statistics"],
        )
        roi.update_received.put(request)
        roi._publish_configuration = Mock()
        with patch.object(roi, "_apply_roi_configuration") as apply:
            roi.stop_capture(io_timeout=1)
            assert roi.update_received.updates_blocked
            assert roi.update_received.has_pending_update
            np.testing.assert_equal(roi.geometry.read_configuration(), previous)
            apply.assert_not_called()
            roi.update_received.unblock_updates(owner="scan")
            apply.assert_called_once_with(request.roi_config)
        assert roi._roi_config == request.roi_config


@pytest.mark.parametrize("failure_position", ["first", "middle", "last"])
def test_ioc_observer_installation_failure_can_retry_without_duplicate_callbacks(failure_position):
    """
    Failed connection removes partial observers and commits readiness only on success.
    """
    from unittest.mock import patch

    class Detector(PSIDeviceBase):
        roi = Cpt(ADROIProcessing, "", manage_capture=False)

    with patched_device(Detector, name="det", prefix="DET:", device_manager=DMMock()) as detector:
        roi = detector.roi
        signals = list(roi._ioc_configuration_signals().values())
        index = {"first": 0, "middle": len(signals) // 2, "last": len(signals) - 1}[
            failure_position
        ]
        previous = {signal: len(signal._callbacks[signal.SUB_VALUE]) for signal in signals}
        with (
            patch.object(
                signals[index], "subscribe", side_effect=RuntimeError("CA monitor creation failed")
            ),
            pytest.raises(RuntimeError, match="CA monitor creation failed"),
        ):
            roi.on_connected()
        assert not roi._ad_connection_initialized
        assert roi._ioc_config_subscriptions == []
        assert all(
            len(signal._callbacks[signal.SUB_VALUE]) == previous[signal] for signal in signals
        )
        roi.on_connected()
        assert roi._ad_connection_initialized
        assert len(roi._ioc_config_subscriptions) == len(signals)
        assert all(
            len(signal._callbacks[signal.SUB_VALUE]) == previous[signal] + 1 for signal in signals
        )
        registered = list(roi._ioc_config_subscriptions)
        roi.on_connected()
        assert roi._ioc_config_subscriptions == registered


def test_ioc_observer_retry_reuses_registration_when_rollback_fails():
    """
    Retain a failed cleanup token for destruction/retry instead of leaking a duplicate.
    """
    from unittest.mock import patch

    class Detector(PSIDeviceBase):
        roi = Cpt(ADROIProcessing, "", manage_capture=False)

    with patched_device(Detector, name="det", prefix="DET:", device_manager=DMMock()) as detector:
        roi = detector.roi
        signals = list(roi._ioc_configuration_signals().values())
        with (
            patch.object(signals[1], "subscribe", side_effect=RuntimeError("monitor unavailable")),
            patch.object(
                signals[0], "unsubscribe", side_effect=RuntimeError("cleanup unavailable")
            ),
            pytest.raises(RuntimeError, match="monitor unavailable") as failure,
        ):
            roi.on_connected()
        assert not roi._ad_connection_initialized
        assert len(roi._ioc_config_subscriptions) == 1
        assert "cleanup unavailable" in " ".join(failure.value.__notes__)
        retained = roi._ioc_config_subscriptions[0]
        roi.on_connected()
        assert roi._ad_connection_initialized
        assert len(roi._ioc_config_subscriptions) == len(signals)
        assert roi._ioc_config_subscriptions[0] == retained
        assert len(signals[0]._callbacks[signals[0].SUB_VALUE]) == 1


@pytest.mark.parametrize(
    "setting,value,control",
    [
        ("active", False, "roi1.enable"),
        ("selected_operations", ["centroid"], "stats1.compute_statistics"),
    ],
)
@pytest.mark.parametrize("method", ["put", "set"])
def test_direct_ad_setting_reports_backend_failure(setting, value, control, method):
    """
    A failed native control write cannot acknowledge or publish a local setting edit.
    """
    from unittest.mock import patch

    from bec_lib.utils.rpc_utils import rgetattr

    class Detector(PSIDeviceBase):
        processing = Cpt(
            ADROIProcessing,
            "",
            manage_capture=False,
            active=True,
            selected_operations=["basic_statistics"],
        )

    with patched_device(Detector, name="det", prefix="DET:", device_manager=DMMock()) as detector:
        roi = detector.processing
        # Isolate request failure from asynchronous readback reconciliation, tested above.
        with patch.object(roi, "_on_ioc_configuration_changed"):
            roi.on_connected()
        previous = roi._configuration_message()
        with (
            patch.object(
                rgetattr(roi, control), "put", side_effect=TimeoutError("IOC rejected write")
            ),
            patch.object(roi, "_publish_configuration") as publish,
        ):
            with pytest.raises(TimeoutError, match="IOC rejected write"):
                result = getattr(getattr(roi, setting), method)(value)
                if method == "set":
                    result.wait(timeout=1)
            assert roi._configuration_message().model_dump(
                exclude={"metadata"}
            ) == previous.model_dump(exclude={"metadata"})
            publish.assert_not_called()


@pytest.mark.parametrize("owner", ["scan", "capture"])
@pytest.mark.parametrize("method", ["put", "set"])
def test_averaging_cannot_change_while_roi_configuration_is_locked(owner, method):
    """
    Ordinary and forced averaging edits preserve a scan's result cardinality.
    """

    class Detector(PSIDeviceBase):
        roi = Cpt(ADROIProcessing, "", manage_capture=False)

    with patched_device(Detector, name="det", prefix="DET:", device_manager=DMMock()) as detector:
        roi = detector.roi
        roi.update_received.block_updates(owner=owner)
        with pytest.raises(RuntimeError, match="ROI configuration is locked"):
            result = getattr(roi.average_frames_per_trigger, method)(False, force=True)
            if method == "set":
                result.wait(timeout=1)
        assert roi.average_frames_per_trigger.get() is True
        roi.update_received.unblock_updates(owner=owner)
        roi.average_frames_per_trigger.set(False).wait(timeout=1)
        assert roi.average_frames_per_trigger.get() is False


@pytest.mark.parametrize("source", ["observer", "result"])
def test_roi_destroy_continues_after_unsubscribe_failure(source):
    """
    One failed unsubscribe must not strand the executor, Redis subscriptions or children.
    """
    from unittest.mock import Mock, patch

    from ophyd_devices.utils.bec_roi_signals.ad_roi_signal import StatsSubscription

    class Detector(PSIDeviceBase):
        roi = Cpt(ADROIProcessing, "", manage_capture=False)

    with patched_device(Detector, name="det", prefix="DET:", device_manager=DMMock()) as detector:
        roi = detector.roi
        roi.on_connected()
        failed, other = Mock(), Mock()
        failed.unsubscribe.side_effect = RuntimeError("unsubscribe failed")
        if source == "observer":
            roi._ioc_config_subscriptions.extend([(failed, 901), (other, 902)])
        else:
            roi._stats_subscriptions.update(
                {
                    "failed": StatsSubscription(failed, 901, "basic_statistics", "mean", "scalar"),
                    "other": StatsSubscription(other, 902, "basic_statistics", "mean", "scalar"),
                }
            )
        connector = detector.device_manager.connector
        with (
            patch.object(
                roi._ioc_config_executor, "shutdown", wraps=roi._ioc_config_executor.shutdown
            ) as shutdown,
            patch.object(connector, "unregister", wraps=connector.unregister) as unregister,
        ):
            with pytest.raises(RuntimeError, match="unsubscribe failed"):
                roi.destroy()
            shutdown.assert_called_once_with(wait=True, cancel_futures=True)
            other.unsubscribe.assert_called_once_with(902)
            assert unregister.call_count == 2
            assert roi._destroyed
            assert roi.update_received._destroyed
            assert roi.geometry._destroyed
