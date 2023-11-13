import pytest
from unittest import mock
import threading
import os
import ophyd

from ophyd_devices.epics.devices.falcon_csaxs import FalconcSAXS, FalconTimeoutError

from tests.utils import DMMock, MockPV
from bec_lib import messages, MessageEndpoints


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
    name = "falcon"
    prefix = "X12SA-SITORO:"
    sim_mode = False
    dm = DMMock()
    with mock.patch.object(dm, "producer"):
        with mock.patch(
            "ophyd_devices.epics.devices.falcon_csaxs.FileWriterMixin"
        ) as filemixin, mock.patch(
            "ophyd_devices.epics.devices.falcon_csaxs.FalconcSAXS._update_service_config"
        ) as mock_service_config:
            with mock.patch.object(ophyd, "cl") as mock_cl:
                mock_cl.get_pv = MockPV
                mock_cl.thread_class = threading.Thread
                with mock.patch.object(FalconcSAXS, "_init"):
                    det = FalconcSAXS(
                        name=name, prefix=prefix, device_manager=dm, sim_mode=sim_mode
                    )
                    patch_dual_pvs(det)
                    yield det


@pytest.mark.parametrize(
    "trigger_source, mapping_source, ignore_gate, pixels_per_buffer, detector_state, expected_exception",
    [
        (1, 1, 0, 20, 0, False),
        (1, 1, 0, 20, 1, True),
    ],
)
# TODO rewrite this one, write test for init_detector, init_filewriter is tested
def test_init_detector(
    mock_det,
    trigger_source,
    mapping_source,
    ignore_gate,
    pixels_per_buffer,
    detector_state,
    expected_exception,
):
    """Test the _init function:

    This includes testing the functions:
    - _init_detector
    - _stop_det
    - _set_trigger
    --> Testing the filewriter is done in test_init_filewriter

    Validation upon setting the correct PVs

    """
    mock_det._value_pixel_per_buffer = pixels_per_buffer
    mock_det.state._read_pv.mock_data = detector_state
    if expected_exception:
        with pytest.raises(FalconTimeoutError):
            mock_det.timeout = 0.1
            mock_det._init_detector()
    else:
        mock_det._init_detector()  # call the method you want to test
        assert mock_det.state.get() == detector_state
        assert mock_det.collect_mode.get() == mapping_source
        assert mock_det.pixel_advance_mode.get() == trigger_source
        assert mock_det.ignore_gate.get() == ignore_gate

        assert mock_det.preset_mode.get() == 1
        assert mock_det.erase_all.get() == 1
        assert mock_det.input_logic_polarity.get() == 0
        assert mock_det.auto_pixels_per_buffer.get() == 0
        assert mock_det.pixels_per_buffer.get() == pixels_per_buffer


@pytest.mark.parametrize(
    "readout_time, expected_value",
    [
        (1e-3, 3e-3),
        (3e-3, 3e-3),
        (5e-3, 5e-3),
        (None, 3e-3),
    ],
)
def test_update_readout_time(mock_det, readout_time, expected_value):
    # mock_det.scaninfo.readout_time = readout_time
    if readout_time is None:
        mock_det._update_readout_time()
        assert mock_det.readout_time == expected_value
    else:
        mock_det.scaninfo.readout_time = readout_time
        mock_det._update_readout_time()
        assert mock_det.readout_time == expected_value


def test_default_parameter(mock_det):
    with mock.patch.object(mock_det, "_update_readout_time") as mock_update_readout_time:
        mock_det._default_parameter()
        assert mock_det._value_pixel_per_buffer == 20
        mock_update_readout_time.assert_called_once()


@pytest.mark.parametrize(
    "scaninfo",
    [
        (
            {
                "eacc": "e12345",
                "num_points": 500,
                "frames_per_trigger": 1,
                "exp_time": 0.1,
                "filepath": "test.h5",
                "scanID": "123",
                "mokev": 12.4,
            }
        ),
    ],
)
def test_stage(mock_det, scaninfo):
    """Test the stage function:

    This includes testing _prep_det
    """
    with mock.patch.object(mock_det, "_set_trigger") as mock_set_trigger, mock.patch.object(
        mock_det, "_prep_file_writer"
    ) as mock_prep_file_writer, mock.patch.object(
        mock_det, "_publish_file_location"
    ) as mock_publish_file_location, mock.patch.object(
        mock_det, "_arm_acquisition"
    ) as mock_arm_acquisition:
        mock_det.scaninfo.exp_time = scaninfo["exp_time"]
        mock_det.scaninfo.num_points = scaninfo["num_points"]
        mock_det.scaninfo.frames_per_trigger = scaninfo["frames_per_trigger"]
        mock_det.stage()
        mock_set_trigger.assert_called_once()
        assert mock_det.preset_real.get() == scaninfo["exp_time"]
        assert mock_det.pixels_per_run.get() == int(
            scaninfo["num_points"] * scaninfo["frames_per_trigger"]
        )
        mock_prep_file_writer.assert_called_once()
        mock_publish_file_location.assert_called_once_with(done=False)
        mock_arm_acquisition.assert_called_once()


@pytest.mark.parametrize(
    "scaninfo",
    [
        (
            {
                "filepath": "/das/work/p18/p18533/data/S00000-S00999/S00001/data.h5",
                "num_points": 500,
                "frames_per_trigger": 1,
            }
        ),
        (
            {
                "filepath": "/das/work/p18/p18533/data/S00000-S00999/S00001/data1234.h5",
                "num_points": 500,
                "frames_per_trigger": 1,
            }
        ),
    ],
)
def test_prep_file_writer(mock_det, scaninfo):
    mock_det.filewriter.compile_full_filename.return_value = scaninfo["filepath"]
    mock_det.scaninfo.num_points = scaninfo["num_points"]
    mock_det.scaninfo.frames_per_trigger = scaninfo["frames_per_trigger"]
    mock_det.scaninfo.scan_number = 1
    mock_det._prep_file_writer()
    file_path, file_name = os.path.split(scaninfo["filepath"])
    assert mock_det.hdf5.file_path.get() == file_path
    assert mock_det.hdf5.file_name.get() == file_name
    assert mock_det.hdf5.file_template.get() == "%s%s"
    assert mock_det.hdf5.num_capture.get() == int(
        scaninfo["num_points"] * scaninfo["frames_per_trigger"]
    )
    assert mock_det.hdf5.file_write_mode.get() == 2
    assert mock_det.hdf5.array_counter.get() == 0
    assert mock_det.hdf5.capture.get() == 1


@pytest.mark.parametrize(
    "scaninfo",
    [
        ({"filepath": "test.h5", "successful": True, "done": False, "scanID": "123"}),
        ({"filepath": "test.h5", "successful": False, "done": True, "scanID": "123"}),
        ({"filepath": "test.h5", "successful": None, "done": True, "scanID": "123"}),
    ],
)
def test_publish_file_location(mock_det, scaninfo):
    mock_det.scaninfo.scanID = scaninfo["scanID"]
    mock_det.filepath = scaninfo["filepath"]
    mock_det._publish_file_location(done=scaninfo["done"], successful=scaninfo["successful"])
    if scaninfo["successful"] is None:
        msg = messages.FileMessage(file_path=scaninfo["filepath"], done=scaninfo["done"]).dumps()
    else:
        msg = messages.FileMessage(
            file_path=scaninfo["filepath"], done=scaninfo["done"], successful=scaninfo["successful"]
        ).dumps()
    expected_calls = [
        mock.call(
            MessageEndpoints.public_file(scaninfo["scanID"], mock_det.name),
            msg,
            pipe=mock_det._producer.pipeline.return_value,
        ),
        mock.call(
            MessageEndpoints.file_event(mock_det.name),
            msg,
            pipe=mock_det._producer.pipeline.return_value,
        ),
    ]
    assert mock_det._producer.set_and_publish.call_args_list == expected_calls


@pytest.mark.parametrize(
    "detector_state, expected_exception",
    [
        (1, False),
        (0, True),
    ],
)
def test_arm_acquisition(mock_det, detector_state, expected_exception):
    with mock.patch.object(mock_det, "stop") as mock_stop:
        mock_det.state._read_pv.mock_data = detector_state
        if expected_exception:
            with pytest.raises(FalconTimeoutError):
                mock_det.timeout = 0.1
                mock_det._arm_acquisition()
                mock_stop.assert_called_once()
        else:
            mock_det._arm_acquisition()
            assert mock_det.start_all.get() == 1


def test_trigger(mock_det):
    with mock.patch.object(mock_det, "_on_trigger") as mock_on_trigger:
        mock_det.trigger()
        mock_on_trigger.assert_called_once()


@pytest.mark.parametrize(
    "stopped, expected_abort",
    [
        (
            False,
            False,
        ),
        (
            True,
            True,
        ),
    ],
)
def test_unstage(
    mock_det,
    stopped,
    expected_abort,
):
    with mock.patch.object(mock_det, "_finished") as mock_finished, mock.patch.object(
        mock_det, "_publish_file_location"
    ) as mock_publish_file_location:
        mock_det._stopped = stopped
        if expected_abort:
            mock_det.unstage()
            assert mock_det._stopped == stopped
            assert mock_publish_file_location.call_count == 0
        else:
            mock_det.unstage()
            mock_finished.assert_called_once()
            mock_publish_file_location.assert_called_with(done=True, successful=True)
            assert mock_det._stopped == False


def test_stop(mock_det):
    with mock.patch.object(mock_det, "_stop_det") as mock_stop_det, mock.patch.object(
        mock_det, "_stop_file_writer"
    ) as mock_stop_file_writer:
        mock_det.stop()
        mock_stop_det.assert_called_once()
        mock_stop_file_writer.assert_called_once()
        assert mock_det._stopped == True


@pytest.mark.parametrize(
    "stopped, scaninfo",
    [
        (False, {"num_points": 500, "frames_per_trigger": 1}),
        (True, {"num_points": 500, "frames_per_trigger": 1}),
    ],
)
def test_finished(mock_det, stopped, scaninfo):
    with mock.patch.object(mock_det, "_stop_det") as mock_stop_det, mock.patch.object(
        mock_det, "_stop_file_writer"
    ) as mock_stop_file_writer:
        mock_det._stopped = stopped
        mock_det.dxp.current_pixel._read_pv.mock_data = int(
            scaninfo["num_points"] * scaninfo["frames_per_trigger"]
        )
        mock_det.hdf5.array_counter._read_pv.mock_data = int(
            scaninfo["num_points"] * scaninfo["frames_per_trigger"]
        )
        mock_det.scaninfo.frames_per_trigger = scaninfo["frames_per_trigger"]
        mock_det.scaninfo.num_points = scaninfo["num_points"]
        mock_det._finished()
        assert mock_det._stopped == stopped
        mock_stop_det.assert_called_once()
        mock_stop_file_writer.assert_called_once()
