# pylint: skip-file
import threading
from unittest import mock

import ophyd
import pytest
from bec_lib import MessageEndpoints, messages

from ophyd_devices.epics.devices.mcs_csaxs import (
    MCScSAXS,
    MCSError,
    MCSTimeoutError,
    ReadoutMode,
    TriggerSource,
)
from tests.utils import DMMock, MockPV


def patch_dual_pvs(device):
    for walk in device.walk_signals():
        if not hasattr(walk.item, "_read_pv"):
            continue
        if not hasattr(walk.item, "_write_pv"):
            continue
        if walk.item._read_pv.pvname.endswith("_RBV"):
            walk.item._read_pv = walk.item._write_pv


@pytest.fixture(scope="function")
def mock_det():
    name = "mcs"
    prefix = "X12SA-MCS:"
    sim_mode = False
    dm = DMMock()
    with mock.patch.object(dm, "connector"):
        with (
            mock.patch("ophyd_devices.epics.devices.psi_detector_base.FileWriter") as filemixin,
            mock.patch(
                "ophyd_devices.epics.devices.psi_detector_base.PSIDetectorBase._update_service_config"
            ) as mock_service_config,
        ):
            with mock.patch.object(ophyd, "cl") as mock_cl:
                mock_cl.get_pv = MockPV
                mock_cl.thread_class = threading.Thread
                with mock.patch.object(MCScSAXS, "_init"):
                    det = MCScSAXS(name=name, prefix=prefix, device_manager=dm, sim_mode=sim_mode)
                    patch_dual_pvs(det)
                    yield det


def test_init():
    """Test the _init function:"""
    name = "eiger"
    prefix = "X12SA-ES-EIGER9M:"
    sim_mode = False
    dm = DMMock()
    with mock.patch.object(dm, "connector"):
        with (
            mock.patch("ophyd_devices.epics.devices.psi_detector_base.FileWriter"),
            mock.patch(
                "ophyd_devices.epics.devices.psi_detector_base.PSIDetectorBase._update_service_config"
            ),
        ):
            with mock.patch.object(ophyd, "cl") as mock_cl:
                mock_cl.get_pv = MockPV
                with (
                    mock.patch(
                        "ophyd_devices.epics.devices.mcs_csaxs.MCSSetup.initialize_default_parameter"
                    ) as mock_default,
                    mock.patch(
                        "ophyd_devices.epics.devices.mcs_csaxs.MCSSetup.initialize_detector"
                    ) as mock_init_det,
                    mock.patch(
                        "ophyd_devices.epics.devices.mcs_csaxs.MCSSetup.initialize_detector_backend"
                    ) as mock_init_backend,
                ):
                    MCScSAXS(name=name, prefix=prefix, device_manager=dm, sim_mode=sim_mode)
                    mock_default.assert_called_once()
                    mock_init_det.assert_called_once()
                    mock_init_backend.assert_called_once()


@pytest.mark.parametrize(
    "trigger_source, channel_advance, channel_source1, pv_channels",
    [
        (
            3,
            1,
            0,
            {
                "user_led": 0,
                "mux_output": 5,
                "input_pol": 0,
                "output_pol": 1,
                "count_on_start": 0,
                "stop_all": 1,
            },
        )
    ],
)
def test_initialize_detector(
    mock_det, trigger_source, channel_advance, channel_source1, pv_channels
):
    """Test the _init function:

    This includes testing the functions:
    - initialize_detector
    - stop_det
    - parent.set_trigger
    --> Testing the filewriter is done in test_init_filewriter

    Validation upon setting the correct PVs

    """
    mock_det.custom_prepare.initialize_detector()  # call the method you want to test
    assert mock_det.channel_advance.get() == channel_advance
    assert mock_det.channel1_source.get() == channel_source1
    assert mock_det.user_led.get() == pv_channels["user_led"]
    assert mock_det.mux_output.get() == pv_channels["mux_output"]
    assert mock_det.input_polarity.get() == pv_channels["input_pol"]
    assert mock_det.output_polarity.get() == pv_channels["output_pol"]
    assert mock_det.count_on_start.get() == pv_channels["count_on_start"]
    assert mock_det.input_mode.get() == trigger_source


def test_trigger(mock_det):
    """Test the trigger function:
    Validate that trigger calls the custom_prepare.on_trigger() function
    """
    with mock.patch.object(mock_det.custom_prepare, "on_trigger") as mock_on_trigger:
        mock_det.trigger()
        mock_on_trigger.assert_called_once()


@pytest.mark.parametrize(
    "value, num_lines, num_points, done", [(100, 5, 500, False), (500, 5, 500, True)]
)
def test_progress_update(mock_det, value, num_lines, num_points, done):
    mock_det.num_lines.set(num_lines)
    mock_det.scaninfo.num_points = num_points
    calls = mock.call(sub_type="progress", value=value, max_value=num_points, done=done)
    with mock.patch.object(mock_det, "_run_subs") as mock_run_subs:
        mock_det.custom_prepare._progress_update(value=value)
        mock_run_subs.assert_called_once()
        assert mock_run_subs.call_args == calls


@pytest.mark.parametrize(
    "values, expected_nothing",
    [([[100, 120, 140], [200, 220, 240], [300, 320, 340]], False), ([100, 200, 300], True)],
)
def test_on_mca_data(mock_det, values, expected_nothing):
    """Test the on_mca_data function:
    Validate that on_mca_data calls the custom_prepare.on_mca_data() function
    """
    with mock.patch.object(mock_det.custom_prepare, "_send_data_to_bec") as mock_send_data:
        mock_object = mock.MagicMock()
        for ii, name in enumerate(mock_det.custom_prepare.mca_names):
            mock_object.attr_name = name
            mock_det.custom_prepare._on_mca_data(obj=mock_object, value=values[ii])
            if not expected_nothing and ii < (len(values) - 1):
                assert mock_det.custom_prepare.mca_data[name] == values[ii]

        if not expected_nothing:
            mock_send_data.assert_called_once()
            assert mock_det.custom_prepare.acquisition_done is True


@pytest.mark.parametrize(
    "metadata, mca_data",
    [
        (
            {"scan_id": 123},
            {"mca1": [100, 120, 140], "mca3": [200, 220, 240], "mca4": [300, 320, 340]},
        )
    ],
)
def test_send_data_to_bec(mock_det, metadata, mca_data):
    mock_det.scaninfo.scan_msg = mock.MagicMock()
    mock_det.scaninfo.scan_msg.metadata = metadata
    mock_det.scaninfo.scan_id = metadata["scan_id"]
    mock_det.custom_prepare.mca_data = mca_data
    mock_det.custom_prepare._send_data_to_bec()
    device_metadata = mock_det.scaninfo.scan_msg.metadata
    metadata.update({"async_update": "append", "num_lines": mock_det.num_lines.get()})
    data = messages.DeviceMessage(signals=dict(mca_data), metadata=device_metadata)
    calls = mock.call(
        topic=MessageEndpoints.device_async_readback(
            scan_id=metadata["scan_id"], device=mock_det.name
        ),
        msg={"data": data},
        expire=1800,
    )

    assert mock_det.connector.xadd.call_args == calls


@pytest.mark.parametrize(
    "scaninfo, triggersource, stopped, expected_exception",
    [
        (
            {"num_points": 500, "frames_per_trigger": 1, "scan_type": "step"},
            TriggerSource.MODE3,
            False,
            False,
        ),
        (
            {"num_points": 500, "frames_per_trigger": 1, "scan_type": "fly"},
            TriggerSource.MODE3,
            False,
            False,
        ),
        (
            {"num_points": 5001, "frames_per_trigger": 2, "scan_type": "step"},
            TriggerSource.MODE3,
            False,
            True,
        ),
        (
            {"num_points": 500, "frames_per_trigger": 2, "scan_type": "random"},
            TriggerSource.MODE3,
            False,
            True,
        ),
    ],
)
def test_stage(mock_det, scaninfo, triggersource, stopped, expected_exception):
    mock_det.scaninfo.num_points = scaninfo["num_points"]
    mock_det.scaninfo.frames_per_trigger = scaninfo["frames_per_trigger"]
    mock_det.scaninfo.scan_type = scaninfo["scan_type"]
    mock_det.stopped = stopped
    with mock.patch.object(mock_det.custom_prepare, "prepare_detector_backend") as mock_prep_fw:
        if expected_exception:
            with pytest.raises(MCSError):
                mock_det.stage()
                mock_prep_fw.assert_called_once()
        else:
            mock_det.stage()
            mock_prep_fw.assert_called_once()
            # Check set_trigger
            mock_det.input_mode.get() == triggersource
            if scaninfo["scan_type"] == "step":
                assert mock_det.num_use_all.get() == int(scaninfo["frames_per_trigger"]) * int(
                    scaninfo["num_points"]
                )
            elif scaninfo["scan_type"] == "fly":
                assert mock_det.num_use_all.get() == int(scaninfo["num_points"])
            mock_det.preset_real.get() == 0

        # # CHeck custom_prepare.arm_acquisition
        # assert mock_det.custom_prepare.counter == 0
        # assert mock_det.erase_start.get() == 1
        # mock_prep_fw.assert_called_once()
        # # Check _prep_det
        # assert mock_det.cam.num_images.get() == int(
        #     scaninfo["num_points"] * scaninfo["frames_per_trigger"]
        # )
        # assert mock_det.cam.num_frames.get() == 1

        # mock_publish_file_location.assert_called_with(done=False)
        # assert mock_det.cam.acquire.get() == 1


def test_prepare_detector_backend(mock_det):
    mock_det.custom_prepare.prepare_detector_backend()
    assert mock_det.erase_all.get() == 1
    assert mock_det.read_mode.get() == ReadoutMode.EVENT


@pytest.mark.parametrize("stopped, expected_exception", [(False, False), (True, True)])
def test_unstage(mock_det, stopped, expected_exception):
    with (
        mock.patch.object(mock_det.custom_prepare, "finished") as mock_finished,
        mock.patch.object(
            mock_det.custom_prepare, "publish_file_location"
        ) as mock_publish_file_location,
    ):
        mock_det.stopped = stopped
        if expected_exception:
            mock_det.unstage()
            assert mock_det.stopped is True
        else:
            mock_det.unstage()
            mock_finished.assert_called_once()
            mock_publish_file_location.assert_called_with(done=True, successful=True)
            assert mock_det.stopped is False


def test_stop_detector_backend(mock_det):
    mock_det.custom_prepare.stop_detector_backend()
    assert mock_det.custom_prepare.acquisition_done is True


def test_stop(mock_det):
    with (
        mock.patch.object(mock_det.custom_prepare, "stop_detector") as mock_stop_det,
        mock.patch.object(
            mock_det.custom_prepare, "stop_detector_backend"
        ) as mock_stop_detector_backend,
    ):
        mock_det.stop()
        mock_stop_det.assert_called_once()
        mock_stop_detector_backend.assert_called_once()
        assert mock_det.stopped is True


@pytest.mark.parametrize(
    "stopped, acquisition_done, acquiring_state, expected_exception",
    [
        (False, True, 0, False),
        (False, False, 0, True),
        (False, True, 1, True),
        (True, True, 0, True),
    ],
)
def test_finished(mock_det, stopped, acquisition_done, acquiring_state, expected_exception):
    mock_det.custom_prepare.acquisition_done = acquisition_done
    mock_det.acquiring._read_pv.mock_data = acquiring_state
    mock_det.scaninfo.num_points = 500
    mock_det.num_lines.put(500)
    mock_det.current_channel._read_pv.mock_data = 1
    mock_det.stopped = stopped

    if expected_exception:
        with pytest.raises(MCSTimeoutError):
            mock_det.timeout = 0.1
            mock_det.custom_prepare.finished()
    else:
        mock_det.custom_prepare.finished()
        if stopped:
            assert mock_det.stopped is stopped
