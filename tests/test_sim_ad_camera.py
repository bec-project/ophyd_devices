"""The sim AD camera is loadable through the normal BEC device-server path."""

import threading
from types import SimpleNamespace
from unittest import mock

import ophyd
import pytest
from bec_server.device_server.devices.devicemanager import DeviceManagerDS
from bec_server.device_server.tests.utils import DMMock

from ophyd_devices.interfaces.base_classes.camera_base import CameraBase
from ophyd_devices.tests.utils import MockPV


def test_device_server_constructs_sim_ad_with_prefix_and_bec_context():
    manager = DMMock()
    manager.scan_info = SimpleNamespace(msg=None)
    with mock.patch.object(ophyd, "cl") as control_layer:
        control_layer.get_pv = MockPV
        control_layer.thread_class = threading.Thread
        camera, remaining = DeviceManagerDS.construct_device_obj(
            {
                "name": "adsim",
                "deviceClass": "ophyd_devices.sim.sim_ad_camera.SimADCamera",
                "deviceConfig": {
                    "prefix": "BEC:SIM:",
                    "live_enabled": False,
                    "acquisition_source": "internal",
                    "acquisition_mode": "fixed",
                    "redis_update_frequency": 0,
                    "async_frame_limit": 2048,
                    "hdf5_path_mapping": {"/host/data": "/data"},
                },
            },
            device_manager=manager,
        )
        try:
            assert isinstance(camera, CameraBase)
            assert camera.prefix == "BEC:SIM:"
            assert camera.device_manager is manager
            assert camera.scan_info is manager.scan_info
            assert remaining == {"hdf5_path_mapping": {"/host/data": "/data"}}
            DeviceManagerDS.update_config(
                SimpleNamespace(
                    connector=mock.Mock(),
                    devices={},
                    publish_device_info=mock.Mock(return_value=None),
                ),
                camera,
                remaining,
            )
            assert not camera.live_enabled.get()
            assert camera.acquisition_source.get() == "internal"
            assert camera.acquisition_mode.get() == "fixed"
            assert camera.hdf5_path_mapping == {"/host/data": "/data"}
            assert camera.file_event.parent is camera
            assert camera.file_event.name == "adsim_file_event"
            assert camera.cam.prefix == "BEC:SIM:cam1:"
            assert camera.hdf5.prefix == "BEC:SIM:HDF1:"
            assert camera.hdf5.kind == ophyd.Kind.omitted
            assert camera.roi1.roi1.prefix == "BEC:SIM:ROI1:"
            assert camera.roi2.stats1.prefix == "BEC:SIM:Stats2:"
        finally:
            camera.destroy()


def test_sim_ad_metadata_has_unique_signal_names():
    from bec_server.device_server.devices.device_serializer import get_device_info

    from ophyd_devices.sim.sim_ad_camera import SimADCamera
    from ophyd_devices.tests.utils import patched_device

    with patched_device(
        SimADCamera, prefix="BEC:SIM:", name="adsim", device_manager=DMMock()
    ) as camera:
        try:
            info = get_device_info(camera)
            signals = info["signals"]
            assert "roi1.stats1.sigma.x" in signals
            assert "roi2.stats1.sigma.y" in signals
            assert "roi1.stats1.sigma_x" not in signals
            assert camera.roi1.result_scalar.name == "adsim_roi1"
            assert camera.roi2.result_scalar.name == "adsim_roi2"
            camera.roi1.result_scalar.put({"mean_value": {"value": 3.0, "timestamp": 1.0}})
            assert "adsim_roi1_mean_value" in camera.roi1.result_scalar.get().signals
            names = [signal["obj_name"] for signal in signals.values()]
            assert len(names) == len(set(names))
        finally:
            camera.destroy()


def test_camera_controller_settings_are_configuration():
    from ophyd import Kind

    from ophyd_devices.sim.sim_ad_camera import SimADCamera
    from ophyd_devices.tests.utils import patched_device

    with patched_device(
        SimADCamera, prefix="BEC:SIM:", name="adsim", device_manager=DMMock()
    ) as camera:
        try:
            assert camera.cam.kind == Kind.config
            configuration = camera.read_configuration()
            description = camera.describe_configuration()
            assert not any(name.endswith("configuration_names") for name in configuration)
            assert not any(name.endswith("configuration_names") for name in description)
            assert camera.configuration_names.kind == Kind.omitted
            assert camera.cam.configuration_names.kind == Kind.omitted
            for signal in (
                camera.cam.acquire_time,
                camera.cam.acquire_period,
                camera.cam.num_images,
                camera.cam.trigger_mode,
                camera.cam.gain,
                camera.cam.size.size_x,
                camera.cam.gain_rgb.gain_red,
                camera.cam.noise,
                camera.cam.sim_mode,
            ):
                assert signal.kind == Kind.config
                assert signal.name in camera.describe_configuration()
                assert signal.name not in camera.describe()
            for signal in (camera.cam.acquire, camera.cam.array_counter, camera.cam.reset):
                assert signal.kind == Kind.config
                assert signal.name in camera.describe_configuration()
        finally:
            camera.destroy()


@pytest.mark.parametrize("camera_type", ["sim", "alliedvision"])
def test_camera_metadata_before_first_ioc_frame(camera_type):
    """Metadata is available while the image plugin still reports zero dimensions."""
    from bec_server.device_server.devices.device_serializer import get_device_info

    from ophyd_devices.devices.areadetector.alliedvision_camera import AlliedVisionCamera
    from ophyd_devices.sim.sim_ad_camera import SimADCamera
    from ophyd_devices.tests.utils import patched_device

    cls = SimADCamera if camera_type == "sim" else AlliedVisionCamera
    with patched_device(
        cls, prefix="DET:", name="cold", device_manager=DMMock(), live_enabled=False
    ) as camera:
        assert camera.image.array_size.get() == (0, 0, 0)
        assert camera.image.shaped_image is None
        assert "shaped_image" not in camera.image.component_names
        info = get_device_info(camera)
        assert "image.array_data" in info["signals"]
        assert "image.shaped_image" not in info["signals"]


def test_sim_ad_kind_conversion_only_copies_component_definitions():
    from ophyd import Kind

    from ophyd_devices.devices.areadetector.cam import SimDetectorCam
    from ophyd_devices.sim.sim_ad_camera import SimADCameraSignals, _configuration_signals

    original = {item.dotted_name: item.item.kind for item in SimADCameraSignals.walk_components()}
    with mock.patch.object(ophyd.cl, "get_pv", side_effect=AssertionError("Unexpected PV access")):
        configured = _configuration_signals(SimADCameraSignals)
    for item in configured.walk_components():
        kind = original[item.dotted_name]
        assert item.item.kind == (Kind.config if kind & Kind.normal else kind), item.dotted_name
    assert SimADCameraSignals.cam.cls is not SimDetectorCam
    assert SimDetectorCam.acquire.kind & Kind.normal
    assert SimADCameraSignals.cam.cls.acquire.kind == Kind.config
    assert SimADCameraSignals.image.kind == Kind.omitted


@pytest.mark.parametrize("camera_type", ["sim", "alliedvision"])
def test_ad_plugin_branches_are_omitted_from_configuration(camera_type):
    from ophyd import Kind

    from ophyd_devices.devices.areadetector.alliedvision_camera import AlliedVisionCamera
    from ophyd_devices.sim.sim_ad_camera import SimADCamera
    from ophyd_devices.tests.utils import patched_device

    cls = SimADCamera if camera_type == "sim" else AlliedVisionCamera
    with patched_device(
        cls, prefix="DET:", name="camera", device_manager=DMMock(), live_enabled=False
    ) as camera:
        rois = camera.components.get_rois()
        branches = [plugin for roi in rois for plugin in (roi.roi1, roi.stats1)]
        if camera_type == "sim":
            branches.extend([camera.transform, camera.hdf5])
        configuration = camera.read_configuration()
        description = camera.describe_configuration()
        for branch in branches:
            assert branch.kind == Kind.omitted
            for item in branch.walk_signals(include_lazy=True):
                assert item.item.name not in configuration
                assert item.item.name not in description
        for roi in rois:
            for name in ("x", "y", "width", "height"):
                assert name not in roi.component_names
                assert not hasattr(roi, name)
            for name in ("active", "roi_name", "selected_operations", "average_frames_per_trigger"):
                signal = getattr(roi, name)
                assert signal.name in configuration
                assert signal.name in description
        assert camera.cam.acquire_time.name in configuration


@pytest.mark.parametrize("camera_type", ["sim", "alliedvision"])
def test_camera_configuration_readbacks_are_monitored(camera_type):
    """
    Settings used for conditional writes monitor IOC edits without changing shared drivers.
    """
    from ophyd_devices.devices.areadetector.alliedvision_camera import AlliedVisionCamera
    from ophyd_devices.devices.areadetector.cam import SimDetectorCam, VimbaDetectorCam
    from ophyd_devices.sim.sim_ad_camera import SimADCamera
    from ophyd_devices.tests.utils import patched_device

    original = SimDetectorCam if camera_type == "sim" else VimbaDetectorCam
    original_monitor = original.acquire_time.kwargs.get("auto_monitor")
    cls = SimADCamera if camera_type == "sim" else AlliedVisionCamera
    with patched_device(
        cls, prefix="DET:", name="camera", device_manager=DMMock(), live_enabled=False
    ) as camera:
        signals = [
            camera.cam.acquire_time,
            camera.cam.acquire_period,
            camera.cam.num_images,
            camera.cam.image_mode,
            camera.cam.trigger_mode,
            camera.cam.array_callbacks,
            camera.image.enable,
        ]
        for roi in camera.components.get_rois():
            signals.extend(
                [
                    roi.roi1.enable,
                    roi.stats1.enable,
                    roi.roi1.min_xyz.min_x,
                    roi.roi1.min_xyz.min_y,
                    roi.roi1.size.x,
                    roi.roi1.size.y,
                    roi.stats1.ts_acquire_mode,
                    roi.stats1.ts_read_mode,
                    roi.stats1.ts_num_points,
                    roi.stats1.nd_array_port,
                    roi.stats1.compute_statistics,
                    roi.stats1.compute_centroid,
                ]
            )
        if camera_type == "sim":
            signals.extend(
                [
                    camera.hdf5.file_path,
                    camera.hdf5.file_name,
                    camera.hdf5.file_template,
                    camera.hdf5.file_write_mode,
                    camera.hdf5.num_capture,
                    camera.hdf5.enable,
                    camera.hdf5.array_size.width,
                    camera.hdf5.array_size.height,
                    camera.hdf5.array_size.depth,
                ]
            )
        assert all(signal._auto_monitor for signal in signals)
    assert original.acquire_time.kwargs.get("auto_monitor") == original_monitor


@pytest.mark.parametrize("saved", [False, True])
def test_roi_saving_preference_is_visible_in_initial_device_metadata(saved):
    """
    BEC sees the saved flag before connection; ROI signals stay enabled for streaming.
    """
    from bec_server.device_server.devices.device_serializer import get_device_info

    from ophyd_devices.sim.sim_ad_camera import SimADCamera
    from ophyd_devices.tests.utils import patched_device

    with patched_device(
        SimADCamera,
        prefix="DET:",
        name="camera",
        device_manager=DMMock(),
        live_enabled=False,
        save_roi_data=saved,
    ) as camera:
        info = get_device_info(camera)
        assert camera.save_roi_data is saved
        for roi in camera.components.get_rois():
            for signal in (roi.result_scalar, roi.result_waveform):
                assert signal.signal_info.saved is saved
                assert signal.signal_info.enabled
                entries = [
                    entry
                    for entry in info["signals"].values()
                    if entry["component_name"] == signal.dotted_name
                    and "signal_info" in entry["describe"]
                ]
                if signal.signal_info.signals:
                    assert entries
                assert signal.describe()[signal.name]["signal_info"]["saved"] is saved
                assert all(entry["describe"]["signal_info"]["saved"] is saved for entry in entries)

        # Exercise the actual BEC writer's stream selection using published metadata.
        from bec_server.file_writer.async_writer import AsyncWriter

        writer = AsyncWriter(
            file_path="unused.h5",
            scan_id="scan",
            scan_number=1,
            connector=mock.Mock(),
            devices=[],
            async_signals=[
                (camera.name, entry["component_name"], entry)
                for entry in info["signals"].values()
                if entry["signal_class"] == "DynamicSignal"
            ],
        )
        writer.initialize_stream_keys()
        assert bool(writer.stream_keys) is saved


def test_roi_component_can_override_camera_saving_preference():
    """
    A detector can keep selected ROI results saved while disabling saving by default.
    """
    from ophyd import Component

    from ophyd_devices.sim.sim_ad_camera import SimADCamera
    from ophyd_devices.tests.utils import patched_device
    from ophyd_devices.utils.bec_roi_signals.ad_roi_signal import ADROIProcessing

    class CameraWithSavedROI(SimADCamera):
        roi1 = Component(
            ADROIProcessing,
            "",
            roi_suffix="ROI1:",
            stats_suffix="Stats1:",
            manage_capture=False,
            selected_operations=["basic_statistics"],
            saved=True,
        )

    with patched_device(
        CameraWithSavedROI,
        prefix="DET:",
        name="camera",
        device_manager=DMMock(),
        live_enabled=False,
        save_roi_data=False,
    ) as camera:
        assert camera.roi1.result_scalar.signal_info.saved
        assert not camera.roi2.result_scalar.signal_info.saved


def test_roi_saving_can_change_between_scans_but_not_while_staged():
    """
    Runtime config changes affect saved metadata without disabling ROI processing.
    """
    from ophyd import Staged

    from ophyd_devices.sim.sim_ad_camera import SimADCamera
    from ophyd_devices.tests.utils import patched_device

    with patched_device(
        SimADCamera, prefix="DET:", name="camera", device_manager=DMMock(), live_enabled=False
    ) as camera:
        for value in (False, True):
            camera.save_roi_data = value
            assert camera.save_roi_data is value
            for roi in camera.components.get_rois():
                assert roi.result_scalar.signal_info.saved is value
                assert roi.result_waveform.signal_info.saved is value
                assert roi.result_scalar.signal_info.enabled
        camera._staged = Staged.yes
        with pytest.raises(RuntimeError, match="between scans"):
            camera.save_roi_data = False
        assert camera.save_roi_data
        assert camera.roi1.result_scalar.signal_info.saved
        camera._staged = Staged.no


def test_cold_hdf5_native_staging_defers_preparation_to_camera_hook():
    """
    Native child staging reaches on_stage before any image has been acquired.
    """
    from ophyd_devices.sim.sim_ad_camera import SimADCamera
    from ophyd_devices.tests.utils import patched_device

    with patched_device(
        SimADCamera,
        prefix="DET:",
        name="cold",
        device_manager=DMMock(),
        live_enabled=False,
        save_frame_data=False,
    ) as camera:
        assert sum(camera.hdf5.array_size.get()) == 0
        with mock.patch.object(camera, "on_stage", return_value=None) as hook:
            camera.stage()
        hook.assert_called_once_with()
        assert sum(camera.hdf5.array_size.get()) == 0
        camera.unstage()


@pytest.mark.parametrize("scan_status", ["open", "paused"])
def test_roi_saving_locked_for_entire_scan_even_when_unstaged(scan_status):
    """
    The writer freezes saved streams at open, before stage and until scan closure.
    """
    from ophyd_devices.sim.sim_ad_camera import SimADCamera
    from ophyd_devices.tests.utils import patched_device

    with patched_device(
        SimADCamera, prefix="DET:", name="camera", device_manager=DMMock(), live_enabled=False
    ) as camera:
        camera.scan_info = SimpleNamespace(msg=SimpleNamespace(status=scan_status))
        with pytest.raises(RuntimeError, match="between scans"):
            camera.save_roi_data = False
        assert camera.save_roi_data
        assert camera.roi1.result_scalar.signal_info.saved
        assert camera.roi2.result_waveform.signal_info.saved
        camera.scan_info.msg.status = "closed"
        camera.save_roi_data = False
        assert not camera.save_roi_data
        assert not camera.roi1.result_scalar.signal_info.saved
        assert not camera.roi2.result_waveform.signal_info.saved
