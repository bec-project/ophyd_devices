"""Tests for configurable AreaDetector ROI and Stats plugin instances."""

import numpy as np
import pytest
from bec_server.device_server.tests.utils import DMMock
from ophyd import Component as Cpt
from ophyd import Device, Signal

from ophyd_devices import PSIDeviceBase
from ophyd_devices.tests.utils import patched_device
from ophyd_devices.utils.bec_roi_signals.ad_roi_signal import ADROIProcessing


def test_roi_geometry_monitoring_excludes_stats_axes():
    """Only ROI geometry axes receive automatic monitors, without changing shared plugins."""
    from ophyd_devices.devices.areadetector.plugins import ROIPlugin_V35

    roi = ADROIProcessing._sig_attrs["roi1"].cls
    for branch, fields in (("min_xyz", ("min_x", "min_y")), ("size", ("x", "y"))):
        for field in fields:
            assert roi._sig_attrs[branch].cls._sig_attrs[field].kwargs["auto_monitor"]
            original = ROIPlugin_V35._sig_attrs[branch].cls._sig_attrs[field]
            assert not original.kwargs.get("auto_monitor", False)

    stats = ADROIProcessing._sig_attrs["stats1"].cls
    for branch in ("centroid", "profile_average", "ts_min", "ts_centroid"):
        for field in ("x", "y"):
            assert (
                not stats._sig_attrs[branch].cls._sig_attrs[field].kwargs.get("auto_monitor", False)
            )


@pytest.mark.parametrize("complete_geometry", [False, True])
def test_monitor_interface_preserves_metadata_and_requires_complete_geometry(complete_geometry):
    """Partial geometry cannot enable axes; metadata and status policy always apply."""
    from ophyd import EpicsSignal, EpicsSignalRO, Kind

    from ophyd_devices.devices.areadetector.configuration import configure_ad_signals

    class Origin(Device):
        min_x = Cpt(EpicsSignal, "MinX")
        if complete_geometry:
            min_y = Cpt(EpicsSignal, "MinY")

    class Axes(Device):
        x = Cpt(EpicsSignal, "SizeX")
        y = Cpt(EpicsSignal, "SizeY")

    class Backend(Device):
        min_xyz = Cpt(Origin, "")
        size = Cpt(Axes, "")
        unrelated = Cpt(Axes, "Other:")
        gain = Cpt(EpicsSignal, "Gain", kind=Kind.normal)
        total = Cpt(EpicsSignalRO, "Total", kind=Kind.normal)
        acquire = Cpt(EpicsSignal, "Acquire", kind=Kind.normal)

    configured = configure_ad_signals(Backend, configuration_signals={"gain"})
    assert configured._sig_attrs["gain"].kind == Kind.config
    assert configured._sig_attrs["total"].kind == Kind.omitted
    assert configured._sig_attrs["acquire"].kind == Kind.omitted
    assert configured._sig_attrs["acquire"].kwargs["auto_monitor"]
    for field in ("x", "y"):
        assert (
            configured._sig_attrs["size"].cls._sig_attrs[field].kwargs.get("auto_monitor", False)
            is complete_geometry
        )
        assert (
            not configured._sig_attrs["unrelated"]
            .cls._sig_attrs[field]
            .kwargs.get("auto_monitor", False)
        )
        assert (
            not Backend._sig_attrs["size"].cls._sig_attrs[field].kwargs.get("auto_monitor", False)
        )


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


def test_roi_configuration_does_not_capture_or_subscribe_results():
    from unittest import mock

    from ophyd_devices.utils.bec_signals import DynamicSignal

    class Detector(PSIDeviceBase):
        cam = Cpt(Camera, "")
        processing = Cpt(ADROIProcessing, "", active=True, selected_operations=["basic_statistics"])

    with patched_device(Detector, name="det", prefix="DET:", device_manager=DMMock()) as detector:
        try:
            roi = detector.processing
            roi.roi1.nd_array_port.put("TRANS1")
            with mock.patch.object(roi.stats1.ts_acquire, "put") as acquire:
                roi.on_connected()
                acquire.assert_not_called()
                signal = roi.stats1.ts_mean_value
                assert not signal._callbacks[signal.SUB_VALUE]
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
        finally:
            detector.destroy()


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


def test_direct_roi_edits_publish_confirmed_configuration():
    from bec_lib.messages import ROIConfigurationMessage

    class Detector(PSIDeviceBase):
        processing = Cpt(
            ADROIProcessing,
            "",
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
def test_owner_destroy_closes_roi_resources_before_signals(nested):
    from unittest.mock import patch

    from bec_lib.endpoints import MessageEndpoints

    class Group(Device):
        processing = Cpt(ADROIProcessing, "")

    class Detector(PSIDeviceBase):
        group = Cpt(Group if nested else ADROIProcessing, "")

        def destroy(self):
            from ophyd_devices.utils.psi_device_base_utils import destroy_subdevices

            destroy_subdevices(self)
            super().destroy()

    with patched_device(Detector, name="det", prefix="DET:", device_manager=DMMock()) as detector:
        roi = detector.group.processing if nested else detector.group
        roi.on_connected()
        connector = detector.device_manager.connector
        with patch.object(connector, "unregister", wraps=connector.unregister) as unregister:
            detector.destroy()
        assert roi._ioc_config_closed
        assert roi._ioc_config_executor._shutdown
        assert not roi._ioc_config_subscriptions
        unregister.assert_any_call(
            patterns=MessageEndpoints.roi_config_request("det", roi.dotted_name, username="*"),
            cb=roi._receive_roi_configuration_message,
        )
        detector.destroy()  # Cleanup is idempotent.


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
        processing = Cpt(ADROIProcessing, "")

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
        processing = Cpt(ADROIProcessing, "")

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
        processing = Cpt(ADROIProcessing, "")

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
        roi._ioc_config_executor.submit(lambda: None).result(timeout=1)
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
        processing = Cpt(ADROIProcessing, "")

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
        with patch.object(
            roi, "_apply_roi_configuration", wraps=roi._apply_roi_configuration
        ) as apply:
            roi.stop_capture(io_timeout=1)
            assert roi.update_received.updates_blocked
            assert roi.update_received.has_pending_update
            np.testing.assert_equal(roi.geometry.read_configuration(), previous)
            apply.assert_not_called()
            roi.update_received.unblock_updates(owner="scan")
            apply.assert_called_once_with(request.roi_config)
        roi._ioc_config_executor.submit(lambda: None).result(timeout=1)
        assert roi._roi_config == request.roi_config


@pytest.mark.parametrize("failure_position", ["first", "middle", "last"])
def test_ioc_observer_installation_failure_can_retry_without_duplicate_callbacks(failure_position):
    """
    Failed connection removes partial observers and commits readiness only on success.
    """
    from unittest.mock import patch

    class Detector(PSIDeviceBase):
        roi = Cpt(ADROIProcessing, "")

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
        roi = Cpt(ADROIProcessing, "")

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
    from ophyd.utils.errors import UnknownStatusFailure

    class Detector(PSIDeviceBase):
        processing = Cpt(ADROIProcessing, "", active=True, selected_operations=["basic_statistics"])

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
            # Older ophyd wraps native write failures; newer versions preserve the error.
            with pytest.raises(
                (TimeoutError, UnknownStatusFailure),
                match=f"IOC rejected write|{rgetattr(roi, control).name}",
            ):
                result = getattr(getattr(roi, setting), method)(value)
                if method == "set":
                    result.wait(timeout=1)
            assert roi._configuration_message().model_dump(
                exclude={"metadata"}
            ) == previous.model_dump(exclude={"metadata"})
            publish.assert_not_called()


@pytest.mark.parametrize(
    "delayed_control,other_control",
    [
        ("stats1.compute_statistics", "stats1.compute_centroid"),
        ("roi1.enable", "stats1.compute_centroid"),
    ],
)
def test_configuration_submits_batch_and_waits_for_delayed_readback(delayed_control, other_control):
    """A delayed RBV blocks confirmation, while other settings in its batch still start."""
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from types import SimpleNamespace
    from unittest.mock import patch

    from bec_lib.messages import RectROIConfig, ROIConfigurationMessage
    from bec_lib.utils.rpc_utils import rgetattr

    class Detector(PSIDeviceBase):
        processing = Cpt(ADROIProcessing, "", active=True, selected_operations=["basic_statistics"])

    with patched_device(Detector, name="det", prefix="DET:", device_manager=DMMock()) as detector:
        roi = detector.processing
        try:
            roi.on_connected()
            roi._ioc_config_executor.submit(lambda: None).result(timeout=1)
            delayed, other = rgetattr(roi, delayed_control), rgetattr(roi, other_control)
            written, other_written, published = Event(), Event(), Event()
            pending, snapshots = [], []
            original_other_put = other._write_pv.put
            original_publish = roi._publish_configuration

            def delayed_put(value, **kwargs):
                pending.append(value)
                written.set()  # The write completes before its readback arrives.

            def other_put(value, **kwargs):
                original_other_put(value, **kwargs)
                other_written.set()

            def publish():
                snapshots.append(roi._configuration_message())
                published.set()
                original_publish()

            request = ROIConfigurationMessage(
                device="det",
                signal="processing",
                name="delayed",
                active=False,
                roi_config=RectROIConfig(x=9, y=2, width=40, height=4),
                selected_operations=["centroid"],
            )
            with (
                patch.object(delayed._write_pv, "put", delayed_put),
                patch.object(other._write_pv, "put", other_put),
                patch.object(roi, "_publish_configuration", publish),
                ThreadPoolExecutor(max_workers=1) as executor,
            ):
                future = executor.submit(
                    roi._receive_roi_configuration_message, SimpleNamespace(value=request)
                )
                try:
                    assert written.wait(timeout=1)
                    assert other_written.wait(timeout=1)
                    assert not published.wait(timeout=0.05)
                finally:
                    if pending:
                        delayed._read_pv.mock_data = pending[-1]
                future.result(timeout=2)
                roi._ioc_config_executor.submit(lambda: None).result(timeout=1)
            assert snapshots
            assert snapshots[-1].roi_config == request.roi_config
            for snapshot in snapshots:
                assert snapshot.active == request.active
                assert snapshot.selected_operations == request.selected_operations
        finally:
            roi.destroy()


def test_geometry_request_publishes_ioc_clipping_and_later_frame_adjustment():
    """Geometry need not match the request; controls still apply and monitors reconcile it."""
    from types import SimpleNamespace
    from unittest.mock import patch

    from bec_lib.messages import RectROIConfig, ROIConfigurationMessage

    class Detector(PSIDeviceBase):
        processing = Cpt(ADROIProcessing, "", active=True, selected_operations=["basic_statistics"])

    with patched_device(Detector, name="det", prefix="DET:", device_manager=DMMock()) as detector:
        roi = detector.processing
        try:
            roi.on_connected()
            roi._ioc_config_executor.submit(lambda: None).result(timeout=1)
            publications = []
            width = roi.roi1.size.x

            def clipped_put(value, **kwargs):
                pass  # Put completes before the readback monitor arrives.

            request = ROIConfigurationMessage(
                device="det",
                signal="processing",
                name="clipped",
                active=True,
                roi_config=RectROIConfig(x=9, y=2, width=40, height=4),
                selected_operations=["centroid"],
            )
            with (
                patch.object(width._write_pv, "put", clipped_put),
                patch.object(
                    roi,
                    "_publish_configuration",
                    lambda: publications.append(roi._configuration_message()),
                ),
            ):
                roi._receive_roi_configuration_message(SimpleNamespace(value=request))
                roi._ioc_config_executor.submit(lambda: None).result(timeout=1)
                assert publications
                assert roi._roi_config.width == 0
                assert all(message.roi_config.width != 40 for message in publications)
                width._read_pv.mock_data = 20
                roi._ioc_config_executor.submit(lambda: None).result(timeout=1)
                assert publications[-1].roi_config.width == 20
                assert publications[-1].name == "clipped"
                assert publications[-1].selected_operations == ["centroid"]
                assert roi.stats1.compute_centroid.get() == "Yes"
                # A later frame can change the applied rectangle again.
                width._read_pv.mock_data = 10
                roi._ioc_config_executor.submit(lambda: None).result(timeout=1)
                assert roi._roi_config.width == 10
                assert publications[-1].roi_config.width == 10
        finally:
            roi.destroy()


@pytest.mark.parametrize("owner", ["scan", "capture"])
@pytest.mark.parametrize("method", ["put", "set"])
def test_averaging_cannot_change_while_roi_configuration_is_locked(owner, method):
    """
    Ordinary and forced averaging edits preserve a scan's result cardinality.
    """

    class Detector(PSIDeviceBase):
        roi = Cpt(ADROIProcessing, "")

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


def test_roi_destroy_continues_after_unsubscribe_failure():
    """
    One failed unsubscribe must not strand the executor, Redis subscriptions or children.
    """
    from unittest.mock import Mock, patch

    class Detector(PSIDeviceBase):
        roi = Cpt(ADROIProcessing, "")

    with patched_device(Detector, name="det", prefix="DET:", device_manager=DMMock()) as detector:
        roi = detector.roi
        roi.on_connected()
        failed, other = Mock(), Mock()
        failed.unsubscribe.side_effect = RuntimeError("unsubscribe failed")
        roi._ioc_config_subscriptions.extend([(failed, 901), (other, 902)])
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


@pytest.mark.parametrize("other_owner", [None, "scan", "manual"])
def test_stop_capture_preserves_ioc_error_and_releases_capture_after_ack_race(
    monkeypatch, other_owner
):
    """
    A reserved idle success must not mask stop failures or skip capture-owned cleanup.
    """
    from threading import Event
    from unittest.mock import Mock

    from ophyd_devices.utils.psi_device_base_utils import StatusBase

    class Detector(PSIDeviceBase):
        processing = Cpt(ADROIProcessing, "")

        def on_stop(self):
            self.processing.stop_capture(io_timeout=1)

    with patched_device(Detector, name="det", prefix="DET:", device_manager=DMMock()) as detector:
        roi = detector.processing
        roi._capture_armed = True
        roi.update_received.block_updates(owner="capture")
        if other_owner is not None:
            roi.update_received.block_updates(owner=other_owner)
        roi.stats1.ts_acquire_status._read_pv.mock_data = 0
        release, entered = Event(), Event()
        statuses = []
        original = StatusBase._run_callbacks
        failure = RuntimeError("IOC stop failed")

        def delayed_callbacks(status):
            if status._timeout_diagnostics._description == "Stats capture stopped":
                statuses.append(status)
                entered.set()
                assert release.wait(timeout=2)
            return original(status)

        with monkeypatch.context() as patch:
            patch.setattr(StatusBase, "_run_callbacks", delayed_callbacks)
            patch.setattr(roi.stats1.ts_acquire, "put", Mock(side_effect=failure))
            try:
                with pytest.raises(RuntimeError, match="IOC stop failed") as caught:
                    detector.stop()
                assert caught.value is failure
                assert entered.wait(timeout=1)
                assert not roi._capture_armed
                assert "capture" not in roi.update_received._update_blocks
                assert roi.update_received._update_blocks == (
                    set() if other_owner is None else {other_owner}
                )
                assert not roi.stats1.ts_acquire_status._callbacks[
                    roi.stats1.ts_acquire_status.SUB_VALUE
                ]
            finally:
                release.set()
                for status in statuses:
                    status._callback_thread.join(timeout=1)
                    assert not status._callback_thread.is_alive()


def test_stop_capture_waits_when_cached_idle_disagrees_with_ioc(monkeypatch):
    """
    A cached zero cannot acknowledge shutdown while a fresh IOC read remains acquiring.
    """
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    class Detector(PSIDeviceBase):
        processing = Cpt(ADROIProcessing, "")

    with patched_device(Detector, name="det", prefix="DET:", device_manager=DMMock()) as detector:
        roi = detector.processing
        roi._capture_armed = True
        stats = roi.stats1
        actual = [1]
        fresh_read = Event()

        def read_status(*, use_monitor=True, **kwargs):
            if use_monitor:
                return 0
            fresh_read.set()
            return actual[0]

        monkeypatch.setattr(stats.ts_acquire_status, "get", read_status)
        monkeypatch.setattr(stats.ts_acquire, "put", lambda value, **kwargs: None)
        with ThreadPoolExecutor(max_workers=1) as callers:
            stopped = callers.submit(roi.stop_capture, io_timeout=1)
            assert fresh_read.wait(timeout=1)
            assert not stopped.done()
            actual[0] = 0
            stats.ts_acquire_status._read_pv.mock_data = 0
            stopped.result(timeout=2)
        assert not roi._capture_armed
        assert not stats.ts_acquire_status._callbacks[stats.ts_acquire_status.SUB_VALUE]


def test_live_centroid_results_use_structured_sigma_signals():
    """Live analysis resolves nested scalar PVs and preserves named dynamic outputs."""
    from threading import Event
    from types import SimpleNamespace

    from bec_lib import messages

    class Detector(PSIDeviceBase):
        processing = Cpt(ADROIProcessing, "")

    with patched_device(Detector, name="det", prefix="DET:", device_manager=DMMock()) as detector:
        roi = detector.processing
        roi.on_connected()
        roi.selected_operations.put(["centroid"])
        roi.stats1.sigma.x.get = lambda **_: 2.0
        roi.stats1.sigma.y.get = lambda **_: 3.0
        camera = SimpleNamespace(
            session_id="",
            _poll_stop=Event(),
            _read_preview_signal=lambda signal: signal.get(timeout=1, use_monitor=False),
        )
        roi.publish_live(camera=camera)
        result = roi.result_scalar.get()
        assert isinstance(result, messages.DeviceMessage)
        assert result.signals[f"{roi.result_scalar.name}_sigma_x"]["value"] == 2.0
        assert result.signals[f"{roi.result_scalar.name}_sigma_y"]["value"] == 3.0
        assert (
            result.signals[f"{roi.result_scalar.name}_sigma_x"]["timestamp"]
            == roi.stats1.sigma.x.timestamp
        )
        assert (
            result.signals[f"{roi.result_scalar.name}_sigma_y"]["timestamp"]
            == roi.stats1.sigma.y.timestamp
        )
