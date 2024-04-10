# pylint: skip-file
from unittest import mock

import pytest

from ophyd_devices.epics.devices.grashopper_tomcat import (
    COLORMODE,
    AutoMode,
    DetectorState,
    GrashopperError,
    GrashopperTimeoutError,
    GrashopperTOMCATSetup,
    ImageBinning,
    ImageMode,
    MemoryPolling,
    PixelFormat,
    TriggerSource,
    VideoMode,
)


def patch_dual_pvs(device):
    for walk in device.walk_signals():
        if not hasattr(walk.item, "_read_pv"):
            continue
        if not hasattr(walk.item, "_write_pv"):
            continue
        if walk.item._read_pv.pvname.endswith("_RBV"):
            walk.item._read_pv = walk.item._write_pv


@pytest.fixture(scope="function")
def mock_GrashopperSetup():
    mock_Grashopper = mock.MagicMock()
    yield GrashopperTOMCATSetup(parent=mock_Grashopper)


# Fixture for scaninfo
@pytest.fixture(
    params=[
        {
            "scan_id": "1234",
            "scan_type": "step",
            "num_points": 500,
            "frames_per_trigger": 1,
            "exp_time": 0.1,
            "readout_time": 0.1,
        },
        {
            "scan_id": "1234",
            "scan_type": "step",
            "num_points": 500,
            "frames_per_trigger": 5,
            "exp_time": 0.01,
            "readout_time": 0,
        },
        {
            "scan_id": "1234",
            "scan_type": "fly",
            "num_points": 500,
            "frames_per_trigger": 1,
            "exp_time": 1,
            "readout_time": 0.2,
        },
        {
            "scan_id": "1234",
            "scan_type": "fly",
            "num_points": 500,
            "frames_per_trigger": 5,
            "exp_time": 0.1,
            "readout_time": 0.4,
        },
    ]
)
def scaninfo(request):
    return request.param


def test_initialize_detector(mock_GrashopperSetup):
    """Test the initialize_detector method."""
    # Call the function you want to test
    mock_GrashopperSetup.initialize_detector()

    # Assert the correct methods are called with the expected arguments
    mock_GrashopperSetup.parent.cam.acquire.put.assert_called_once_with(0)
    mock_GrashopperSetup.parent.cam.acquire_time_auto.put.assert_called_once_with(
        AutoMode.CONTINUOUS
    )
    mock_GrashopperSetup.parent.cam.gain_auto.put.assert_called_once_with(AutoMode.CONTINUOUS)
    mock_GrashopperSetup.parent.cam.image_mode.put.assert_called_once_with(ImageMode.MULTIPLE)
    mock_GrashopperSetup.parent.cam.image_binning.put.assert_called_once_with(ImageBinning.X1)
    mock_GrashopperSetup.parent.cam.video_mode.put.assert_called_once_with(VideoMode.MODE0)
    mock_GrashopperSetup.parent.cam.pixel_format.put.assert_called_once_with(PixelFormat.MONO16)
    mock_GrashopperSetup.parent.cam.trigger_source.put.assert_called_once_with(
        TriggerSource.SOFTWARE
    )
    mock_GrashopperSetup.parent.cam.memory_polling.put.assert_called_once_with(
        MemoryPolling.SECONDS1
    )
    mock_GrashopperSetup.parent.cam.set_image_counter.put.assert_called_once_with(0)


def test_initialize_detector_backend(mock_GrashopperSetup):
    """Test the initialize_detector_backend method."""
    # Call the function you want to test
    mock_GrashopperSetup.initialize_detector_backend()

    # Assert the correct methods are called with the expected arguments
    mock_GrashopperSetup.parent.image.queue_size.put.assert_called_once_with(5)
    mock_GrashopperSetup.parent.image.array_port.put.assert_called_once_with(
        mock_GrashopperSetup.parent.cam.port_name.get()
    )
    mock_GrashopperSetup.parent.image.enable_cb.put.assert_called_once_with(1)
    mock_GrashopperSetup.parent.image.set_array_counter.put.assert_called_once_with(0)


@pytest.mark.parametrize("exposure_time", [1, 0.1, 0.01, 0.001, 0.0001])
def test_set_exposure_time(mock_GrashopperSetup, exposure_time):
    """Test the set_exposure_time method."""
    # Call the function you want to test
    frame_rate = 1 / exposure_time
    if frame_rate > mock_GrashopperSetup.low_frame_rate:
        with pytest.raises(GrashopperError):
            mock_GrashopperSetup.set_exposure_time(exposure_time)
    else:
        mock_GrashopperSetup.set_exposure_time(exposure_time)
        mock_GrashopperSetup.parent.cam.frame_rate.put.assert_called_once_with(frame_rate)


def test_prepare_detector(mock_GrashopperSetup, scaninfo):
    """Test the prepare_detector method."""
    # setup scaninof
    for k, v in scaninfo.items():
        setattr(mock_GrashopperSetup.parent.scaninfo, k, v)

    # Call the function you want to test
    with (
        mock.patch.object(
            mock_GrashopperSetup, "set_acquisition_params"
        ) as mock_set_acquisition_params,
        mock.patch.object(mock_GrashopperSetup, "set_exposure_time") as mock_set_exposure_time,
    ):
        mock_GrashopperSetup.prepare_detector()

        # Assert the correct methods are called with the expected arguments
        mock_GrashopperSetup.parent.cam.image_mode.put.assert_called_once_with(ImageMode.MULTIPLE)
        mock_GrashopperSetup.parent.cam.acquire_time_auto.put.assert_called_once_with(
            AutoMode.CONTINUOUS
        )
        mock_GrashopperSetup.parent.set_trigger.assert_called_once_with(TriggerSource.SOFTWARE)
        mock_GrashopperSetup.parent.cam.set_image_counter.put.assert_called_once_with(0)
        mock_set_acquisition_params.assert_called_once()
        mock_set_exposure_time.assert_called_once_with(scaninfo["exp_time"])


def test_prepare_detector_backend(mock_GrashopperSetup):
    """Test the prepare_detector_backend method."""
    # Call the function you want to test
    mock_GrashopperSetup.prepare_detector_backend()
    mock_GrashopperSetup.parent.image.set_array_counter.put.assert_called_once_with(0)
    assert mock_GrashopperSetup.monitor_thread is None
    assert not mock_GrashopperSetup.stop_monitor


@pytest.mark.parametrize("detector_state", [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
def test_arm_acquisition(mock_GrashopperSetup, detector_state):
    """Test the arm_acquisition method."""
    # Call the function you want to test
    mock_GrashopperSetup.parent.cam.detector_state.get.return_value = detector_state
    mock_GrashopperSetup.parent.timeout = 0.1

    if detector_state != DetectorState.WAITING:
        with pytest.raises(GrashopperTimeoutError):
            mock_GrashopperSetup.arm_acquisition()
            assert mock_GrashopperSetup.parent.cam.acquire.put.call_count == 1
            assert mock_GrashopperSetup.parent.cam.acquire.put.call_args == mock.call(1)
    else:
        mock_GrashopperSetup.arm_acquisition()
        assert mock_GrashopperSetup.parent.cam.acquire.put.call_count == 1
        assert mock_GrashopperSetup.parent.cam.acquire.put.call_args == mock.call(1)


@pytest.mark.parametrize("trigger_source", [0, 1, 2, 3])
def test_on_trigger(mock_GrashopperSetup, trigger_source):
    """Test the on_trigger method."""
    # Call the function you want to test
    mock_GrashopperSetup.parent.cam.trigger_source.get.return_value = trigger_source
    with mock.patch.object(mock_GrashopperSetup, "send_data") as mock_send_data:
        mock_GrashopperSetup.on_trigger()

    # Assert the correct methods are called with the expected arguments
    if trigger_source == TriggerSource.SOFTWARE:
        mock_GrashopperSetup.parent.cam.software_trigger_device.put.assert_called_once_with(1)
        assert mock_send_data.call_count == 1


def test_set_acquisition_params(mock_GrashopperSetup, scaninfo):
    """Test the set_acquisition_params method."""
    # Setup scaninfo
    mock_GrashopperSetup.parent.scaninfo.num_points = scaninfo["num_points"]
    mock_GrashopperSetup.parent.scaninfo.frames_per_trigger = scaninfo["frames_per_trigger"]

    # Call the function you want to test
    mock_GrashopperSetup.set_acquisition_params()

    # Assert the correct methods are called with the expected arguments
    expected_num_images = scaninfo["num_points"] * scaninfo["frames_per_trigger"]
    mock_GrashopperSetup.parent.cam.num_images.put.assert_called_once_with(expected_num_images)


@pytest.mark.parametrize("detector_state", [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
def test_stop_detector(mock_GrashopperSetup, detector_state):
    """Test the arm_acquisition method."""
    # Call the function you want to test
    mock_GrashopperSetup.parent.cam.detector_state.get.return_value = detector_state
    mock_GrashopperSetup.parent.timeout = 0.1

    if detector_state != DetectorState.IDLE:
        with pytest.raises(GrashopperTimeoutError):
            mock_GrashopperSetup.stop_detector()
            assert mock_GrashopperSetup.parent.cam.acquire.put.call_count == 2
            assert mock_GrashopperSetup.parent.cam.acquire.put.call_args == mock.call(0)
    else:
        mock_GrashopperSetup.stop_detector()
        assert mock_GrashopperSetup.parent.cam.acquire.put.call_count == 1
        assert mock_GrashopperSetup.parent.cam.acquire.put.call_args == mock.call(0)
