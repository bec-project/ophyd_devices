# pylint: skip-file
import pytest
import threading
from unittest import mock

import ophyd

from bec_lib import messages, MessageEndpoints
from ophyd_devices.epics.devices.eiger9m_csaxs import Eiger9McSAXS

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
    name = "eiger"
    prefix = "X12SA-ES-EIGER9M:"
    sim_mode = False
    dm = DMMock()
    with mock.patch.object(dm, "connector"):
        with mock.patch(
            "ophyd_devices.epics.devices.psi_detector_base.FileWriterMixin"
        ), mock.patch(
            "ophyd_devices.epics.devices.psi_detector_base.PSIDetectorBase._update_service_config"
        ):
            with mock.patch.object(ophyd, "cl") as mock_cl:
                mock_cl.get_pv = MockPV
                mock_cl.thread_class = threading.Thread
                with mock.patch.object(Eiger9McSAXS, "_init"):
                    det = Eiger9McSAXS(
                        name=name, prefix=prefix, device_manager=dm, sim_mode=sim_mode
                    )
                    patch_dual_pvs(det)
                    yield det


def test_init():
    """Test the _init function:"""
    name = "eiger"
    prefix = "X12SA-ES-EIGER9M:"
    sim_mode = False
    dm = DMMock()
    with mock.patch.object(dm, "connector"):
        with mock.patch(
            "ophyd_devices.epics.devices.psi_detector_base.FileWriterMixin"
        ), mock.patch(
            "ophyd_devices.epics.devices.psi_detector_base.PSIDetectorBase._update_service_config"
        ):
            with mock.patch.object(ophyd, "cl") as mock_cl:
                mock_cl.get_pv = MockPV
                with mock.patch(
                    "ophyd_devices.epics.devices.eiger9m_csaxs.Eiger9MSetup.initialize_default_parameter"
                ) as mock_default, mock.patch(
                    "ophyd_devices.epics.devices.eiger9m_csaxs.Eiger9MSetup.initialize_detector"
                ) as mock_init_det, mock.patch(
                    "ophyd_devices.epics.devices.eiger9m_csaxs.Eiger9MSetup.initialize_detector_backend"
                ) as mock_init_backend:
                    Eiger9McSAXS(name=name, prefix=prefix, device_manager=dm, sim_mode=sim_mode)
                    mock_default.assert_called_once()
                    mock_init_det.assert_called_once()
                    mock_init_backend.assert_called_once()


@pytest.mark.parametrize(
    "trigger_source, detector_state, expected_exception",
    [
        (
            2,
            1,
            True,
        ),
        (
            2,
            0,
            False,
        ),
    ],
)
def test_initialize_detector(
    mock_det,
    trigger_source,
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
    mock_det.cam.detector_state._read_pv.mock_data = detector_state
    if expected_exception:
        with pytest.raises(Exception):
            mock_det.timeout = 0.1
            mock_det.custom_prepare.initialize_detector()
    else:
        mock_det.custom_prepare.initialize_detector()  # call the method you want to test
        assert mock_det.cam.acquire.get() == 0
        assert mock_det.cam.detector_state.get() == detector_state
        assert mock_det.cam.trigger_mode.get() == trigger_source


def test_trigger(mock_det):
    """Test the trigger function:
    Validate that trigger calls the custom_prepare.on_trigger() function
    """
    with mock.patch.object(mock_det.custom_prepare, "on_trigger") as mock_on_trigger:
        mock_det.trigger()
        mock_on_trigger.assert_called_once()


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
    if readout_time is None:
        mock_det.custom_prepare.update_readout_time()
        assert mock_det.readout_time == expected_value
    else:
        mock_det.scaninfo.readout_time = readout_time
        mock_det.custom_prepare.update_readout_time()
        assert mock_det.readout_time == expected_value


@pytest.mark.parametrize(
    "eacc, exp_url, daq_status, daq_cfg, expected_exception",
    [
        (
            "e12345",
            "http://xbl-daq-29:5000",
            {"state": "READY"},
            {"writer_user_id": 12543},
            False,
        ),
        (
            "e12345",
            "http://xbl-daq-29:5000",
            {"state": "READY"},
            {"writer_user_id": 15421},
            False,
        ),
        (
            "e12345",
            "http://xbl-daq-29:5000",
            {"state": "BUSY"},
            {"writer_user_id": 15421},
            True,
        ),
        (
            "e12345",
            "http://xbl-daq-29:5000",
            {"state": "READY"},
            {"writer_ud": 12345},
            True,
        ),
    ],
)
def test_initialize_detector_backend(
    mock_det, eacc, exp_url, daq_status, daq_cfg, expected_exception
):
    """Test self.custom_prepare.initialize_detector_backend (std daq in this case)

    This includes testing the functions:

    - _update_service_config

    Validation upon checking set values in mocked std_daq instance
    """
    with mock.patch("ophyd_devices.epics.devices.eiger9m_csaxs.StdDaqClient") as mock_std_daq:
        instance = mock_std_daq.return_value
        instance.stop_writer.return_value = None
        instance.get_status.return_value = daq_status
        instance.get_config.return_value = daq_cfg
        mock_det.scaninfo.username = eacc
        # scaninfo.username.return_value = eacc
        if expected_exception:
            with pytest.raises(Exception):
                mock_det.timeout = 0.1
                mock_det.custom_prepare.initialize_detector_backend()
        else:
            mock_det.custom_prepare.initialize_detector_backend()

            instance.stop_writer.assert_called_once()
            instance.get_status.assert_called()
            instance.set_config.assert_called_once_with(daq_cfg)


@pytest.mark.parametrize(
    "scaninfo, daq_status, daq_cfg, detector_state, stopped, expected_exception",
    [
        (
            {
                "eacc": "e12345",
                "num_points": 500,
                "frames_per_trigger": 1,
                "filepath": "test.h5",
                "scanID": "123",
                "mokev": 12.4,
            },
            {"state": "READY"},
            {"writer_user_id": 12543},
            5,
            False,
            False,
        ),
        (
            {
                "eacc": "e12345",
                "num_points": 500,
                "frames_per_trigger": 1,
                "filepath": "test.h5",
                "scanID": "123",
                "mokev": 12.4,
            },
            {"state": "BUSY"},
            {"writer_user_id": 15421},
            5,
            False,
            False,
        ),
        (
            {
                "eacc": "e12345",
                "num_points": 500,
                "frames_per_trigger": 1,
                "filepath": "test.h5",
                "scanID": "123",
                "mokev": 18.4,
            },
            {"state": "READY"},
            {"writer_user_id": 12345},
            4,
            False,
            True,
        ),
    ],
)
def test_stage(
    mock_det,
    scaninfo,
    daq_status,
    daq_cfg,
    detector_state,
    stopped,
    expected_exception,
):
    with mock.patch.object(
        mock_det.custom_prepare, "std_client"
    ) as mock_std_daq, mock.patch.object(
        mock_det.custom_prepare, "publish_file_location"
    ) as mock_publish_file_location:
        mock_std_daq.stop_writer.return_value = None
        mock_std_daq.get_status.return_value = daq_status
        mock_std_daq.get_config.return_value = daq_cfg
        mock_det.scaninfo.num_points = scaninfo["num_points"]
        mock_det.scaninfo.frames_per_trigger = scaninfo["frames_per_trigger"]
        mock_det.filewriter.compile_full_filename.return_value = scaninfo["filepath"]
        # TODO consider putting energy as variable in scaninfo
        mock_det.device_manager.add_device("mokev", value=12.4)
        mock_det.cam.beam_energy.put(scaninfo["mokev"])
        mock_det.stopped = stopped
        mock_det.cam.detector_state._read_pv.mock_data = detector_state
        with mock.patch.object(mock_det.custom_prepare, "prepare_detector_backend") as mock_prep_fw:
            mock_det.filepath = scaninfo["filepath"]
            if expected_exception:
                with pytest.raises(Exception):
                    mock_det.timeout = 0.1
                    mock_det.stage()
            else:
                mock_det.stage()
                mock_prep_fw.assert_called_once()
                # Check _prep_det
                assert mock_det.cam.num_images.get() == int(
                    scaninfo["num_points"] * scaninfo["frames_per_trigger"]
                )
                assert mock_det.cam.num_frames.get() == 1

                mock_publish_file_location.assert_called_with(done=False)
                assert mock_det.cam.acquire.get() == 1


@pytest.mark.parametrize(
    "scaninfo, daq_status, expected_exception",
    [
        (
            {
                "eacc": "e12345",
                "num_points": 500,
                "frames_per_trigger": 1,
                "filepath": "test.h5",
                "scanID": "123",
            },
            {"state": "BUSY", "acquisition": {"state": "WAITING_IMAGES"}},
            False,
        ),
        (
            {
                "eacc": "e12345",
                "num_points": 500,
                "frames_per_trigger": 1,
                "filepath": "test.h5",
                "scanID": "123",
            },
            {"state": "BUSY", "acquisition": {"state": "WAITING_IMAGES"}},
            False,
        ),
        (
            {
                "eacc": "e12345",
                "num_points": 500,
                "frames_per_trigger": 1,
                "filepath": "test.h5",
                "scanID": "123",
            },
            {"state": "BUSY", "acquisition": {"state": "ERROR"}},
            True,
        ),
    ],
)
def test_prepare_detector_backend(mock_det, scaninfo, daq_status, expected_exception):
    with mock.patch.object(
        mock_det.custom_prepare, "std_client"
    ) as mock_std_daq, mock.patch.object(
        mock_det.custom_prepare, "filepath_exists"
    ) as mock_file_path_exists, mock.patch.object(
        mock_det.custom_prepare, "stop_detector_backend"
    ) as mock_stop_backend, mock.patch.object(
        mock_det, "scaninfo"
    ):
        mock_std_daq.start_writer_async.return_value = None
        mock_std_daq.get_status.return_value = daq_status
        mock_det.filewriter.compile_full_filename.return_value = scaninfo["filepath"]
        mock_det.scaninfo.num_points = scaninfo["num_points"]
        mock_det.scaninfo.frames_per_trigger = scaninfo["frames_per_trigger"]

        if expected_exception:
            with pytest.raises(Exception):
                mock_det.timeout = 0.1
                mock_det.custom_prepare.prepare_data_backend()
                mock_file_path_exists.assert_called_once()
                assert mock_stop_backend.call_count == 2

        else:
            mock_det.custom_prepare.prepare_data_backend()
            mock_file_path_exists.assert_called_once()
            mock_stop_backend.assert_called_once()

        daq_writer_call = {
            "output_file": scaninfo["filepath"],
            "n_images": int(scaninfo["num_points"] * scaninfo["frames_per_trigger"]),
        }
        mock_std_daq.start_writer_async.assert_called_with(daq_writer_call)


@pytest.mark.parametrize(
    "stopped, expected_exception",
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
    expected_exception,
):
    with mock.patch.object(mock_det.custom_prepare, "finished") as mock_finished, mock.patch.object(
        mock_det.custom_prepare, "publish_file_location"
    ) as mock_publish_file_location:
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
    with mock.patch.object(mock_det.custom_prepare, "std_client") as mock_std_daq:
        mock_std_daq.stop_writer.return_value = None
        mock_det.std_client = mock_std_daq
        mock_det.custom_prepare.stop_detector_backend()
        mock_std_daq.stop_writer.assert_called_once()


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
    mock_det.custom_prepare.publish_file_location(
        done=scaninfo["done"], successful=scaninfo["successful"]
    )
    if scaninfo["successful"] is None:
        msg = messages.FileMessage(file_path=scaninfo["filepath"], done=scaninfo["done"])
    else:
        msg = messages.FileMessage(
            file_path=scaninfo["filepath"], done=scaninfo["done"], successful=scaninfo["successful"]
        )
    expected_calls = [
        mock.call(
            MessageEndpoints.public_file(scaninfo["scanID"], mock_det.name),
            msg,
            pipe=mock_det.connector.pipeline.return_value,
        ),
        mock.call(
            MessageEndpoints.file_event(mock_det.name),
            msg,
            pipe=mock_det.connector.pipeline.return_value,
        ),
    ]
    assert mock_det.connector.set_and_publish.call_args_list == expected_calls


def test_stop(mock_det):
    with mock.patch.object(
        mock_det.custom_prepare, "stop_detector"
    ) as mock_stop_det, mock.patch.object(
        mock_det.custom_prepare, "stop_detector_backend"
    ) as mock_stop_detector_backend:
        mock_det.stop()
        mock_stop_det.assert_called_once()
        mock_stop_detector_backend.assert_called_once()
        assert mock_det.stopped is True


@pytest.mark.parametrize(
    "stopped, scaninfo, cam_state, daq_status, expected_exception",
    [
        (
            False,
            {
                "num_points": 500,
                "frames_per_trigger": 4,
            },
            0,
            {"acquisition": {"state": "FINISHED", "stats": {"n_write_completed": 2000}}},
            False,
        ),
        (
            False,
            {
                "num_points": 500,
                "frames_per_trigger": 4,
            },
            0,
            {"acquisition": {"state": "FINISHED", "stats": {"n_write_completed": 1999}}},
            True,
        ),
        (
            False,
            {
                "num_points": 500,
                "frames_per_trigger": 1,
            },
            1,
            {"acquisition": {"state": "READY", "stats": {"n_write_completed": 500}}},
            True,
        ),
        (
            False,
            {
                "num_points": 500,
                "frames_per_trigger": 1,
            },
            0,
            {"acquisition": {"state": "FINISHED", "stats": {"n_write_completed": 500}}},
            False,
        ),
    ],
)
def test_finished(mock_det, stopped, cam_state, daq_status, scaninfo, expected_exception):
    with mock.patch.object(
        mock_det.custom_prepare, "std_client"
    ) as mock_std_daq, mock.patch.object(
        mock_det.custom_prepare, "stop_detector_backend"
    ) as mock_stop_backend, mock.patch.object(
        mock_det.custom_prepare, "stop_detector"
    ) as mock_stop_det:
        mock_std_daq.get_status.return_value = daq_status
        mock_det.cam.acquire._read_pv.mock_state = cam_state
        mock_det.scaninfo.num_points = scaninfo["num_points"]
        mock_det.scaninfo.frames_per_trigger = scaninfo["frames_per_trigger"]
        if expected_exception:
            with pytest.raises(Exception):
                mock_det.timeout = 0.1
                mock_det.custom_prepare.finished()
                assert mock_det.stopped is stopped
        else:
            mock_det.custom_prepare.finished()
            if stopped:
                assert mock_det.stopped is stopped

            mock_stop_backend.assert_called()
            mock_stop_det.assert_called_once()
