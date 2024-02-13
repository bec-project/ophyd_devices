# pylint: skip-file
import os
import pytest
import threading
from unittest import mock

import ophyd

from bec_lib import messages, MessageEndpoints
from ophyd_devices.epics.devices.pilatus_csaxs import PilatuscSAXS

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
    name = "pilatus"
    prefix = "X12SA-ES-PILATUS300K:"
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
                with mock.patch.object(PilatuscSAXS, "_init"):
                    det = PilatuscSAXS(
                        name=name, prefix=prefix, device_manager=dm, sim_mode=sim_mode
                    )
                    patch_dual_pvs(det)
                    yield det


@pytest.mark.parametrize(
    "trigger_source, detector_state",
    [
        (1, 0),
    ],
)
# TODO rewrite this one, write test for init_detector, init_filewriter is tested
def test_init_detector(
    mock_det,
    trigger_source,
    detector_state,
):
    """Test the _init function:

    This includes testing the functions:
    - _init_detector
    - _stop_det
    - _set_trigger
    --> Testing the filewriter is done in test_init_filewriter

    Validation upon setting the correct PVs

    """
    mock_det.custom_prepare.initialize_detector()  # call the method you want to test
    assert mock_det.cam.acquire.get() == detector_state
    assert mock_det.cam.trigger_mode.get() == trigger_source


@pytest.mark.parametrize(
    "scaninfo, stopped, expected_exception",
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
            True,
            False,
        ),
    ],
)
def test_stage(
    mock_det,
    scaninfo,
    stopped,
    expected_exception,
):
    with mock.patch.object(
        mock_det.custom_prepare, "publish_file_location"
    ) as mock_publish_file_location:
        mock_det.scaninfo.num_points = scaninfo["num_points"]
        mock_det.scaninfo.frames_per_trigger = scaninfo["frames_per_trigger"]
        mock_det.filewriter.compile_full_filename.return_value = scaninfo["filepath"]
        mock_det.device_manager.add_device("mokev", value=12.4)
        mock_det.stopped = stopped
        with mock.patch.object(
            mock_det.custom_prepare, "prepare_detector_backend"
        ) as mock_data_backend, mock.patch.object(
            mock_det.custom_prepare, "update_readout_time"
        ) as mock_update_readout_time:
            mock_det.filepath = scaninfo["filepath"]
            if expected_exception:
                with pytest.raises(Exception):
                    mock_det.timeout = 0.1
                    mock_det.stage()
            else:
                mock_det.stage()
                mock_data_backend.assert_called_once()
                mock_update_readout_time.assert_called()
                # Check _prep_det
                assert mock_det.cam.num_images.get() == int(
                    scaninfo["num_points"] * scaninfo["frames_per_trigger"]
                )
                assert mock_det.cam.num_frames.get() == 1

                mock_publish_file_location.assert_called_with(done=False)


def test_pre_scan(mock_det):
    mock_det.custom_prepare.pre_scan()
    assert mock_det.cam.acquire.get() == 1


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
    "scaninfo",
    [
        (
            {
                "filepath": "test.h5",
                "filepath_raw": "test5_raw.h5",
                "successful": True,
                "done": False,
                "scanID": "123",
            }
        ),
        (
            {
                "filepath": "test.h5",
                "filepath_raw": "test5_raw.h5",
                "successful": False,
                "done": True,
                "scanID": "123",
            }
        ),
        (
            {
                "filepath": "test.h5",
                "filepath_raw": "test5_raw.h5",
                "successful": None,
                "done": True,
                "scanID": "123",
            }
        ),
    ],
)
def test_publish_file_location(mock_det, scaninfo):
    mock_det.scaninfo.scanID = scaninfo["scanID"]
    mock_det.filepath = scaninfo["filepath"]
    mock_det.filepath_raw = scaninfo["filepath_raw"]
    mock_det.custom_prepare.publish_file_location(
        done=scaninfo["done"], successful=scaninfo["successful"]
    )
    if scaninfo["successful"] is None:
        msg = messages.FileMessage(
            file_path=scaninfo["filepath"],
            done=scaninfo["done"],
            metadata={"input_path": scaninfo["filepath_raw"]},
        )
    else:
        msg = messages.FileMessage(
            file_path=scaninfo["filepath"],
            done=scaninfo["done"],
            metadata={"input_path": scaninfo["filepath_raw"]},
            successful=scaninfo["successful"],
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


@pytest.mark.parametrize(
    "requests_state, expected_exception, url_delete, url_put",
    [
        (
            True,
            False,
            "http://x12sa-pd-2:8080/stream/pilatus_2",
            "http://xbl-daq-34:8091/pilatus_2/stop",
        ),
        (
            False,
            False,
            "http://x12sa-pd-2:8080/stream/pilatus_2",
            "http://xbl-daq-34:8091/pilatus_2/stop",
        ),
    ],
)
def test_stop_detector_backend(mock_det, requests_state, expected_exception, url_delete, url_put):
    with mock.patch.object(
        mock_det.custom_prepare, "send_requests_delete"
    ) as mock_send_requests_delete, mock.patch.object(
        mock_det.custom_prepare, "send_requests_put"
    ) as mock_send_requests_put:
        instance_delete = mock_send_requests_delete.return_value
        instance_delete.ok = requests_state
        instance_put = mock_send_requests_put.return_value
        instance_put.ok = requests_state
        if expected_exception:
            mock_det.custom_prepare.stop_detector_backend()
            mock_send_requests_delete.assert_called_once_with(url=url_delete)
            mock_send_requests_put.assert_called_once_with(url=url_put)
            instance_delete.raise_for_status.called_once()
            instance_put.raise_for_status.called_once()
        else:
            mock_det.custom_prepare.stop_detector_backend()
            mock_send_requests_delete.assert_called_once_with(url=url_delete)
            mock_send_requests_put.assert_called_once_with(url=url_put)


@pytest.mark.parametrize(
    "scaninfo, data_msgs, urls, requests_state, expected_exception",
    [
        (
            {
                "filepath_raw": "pilatus_2.h5",
                "eacc": "e12345",
                "scan_number": 1000,
                "scan_directory": "S00000_00999",
                "num_points": 500,
                "frames_per_trigger": 1,
                "headers": {"Content-Type": "application/json", "Accept": "application/json"},
            },
            [
                {
                    "source": [
                        {
                            "searchPath": "/",
                            "searchPattern": "glob:*.cbf",
                            "destinationPath": (
                                "/sls/X12SA/data/e12345/Data10/pilatus_2/S00000_00999"
                            ),
                        }
                    ]
                },
                [
                    "zmqWriter",
                    "e12345",
                    {
                        "addr": "tcp://x12sa-pd-2:8888",
                        "dst": ["file"],
                        "numFrm": 500,
                        "timeout": 2000,
                        "ifType": "PULL",
                        "user": "e12345",
                    },
                ],
                [
                    "zmqWriter",
                    "e12345",
                    {
                        "frmCnt": 500,
                        "timeout": 2000,
                    },
                ],
            ],
            [
                "http://x12sa-pd-2:8080/stream/pilatus_2",
                "http://xbl-daq-34:8091/pilatus_2/run",
                "http://xbl-daq-34:8091/pilatus_2/wait",
            ],
            True,
            False,
        ),
        (
            {
                "filepath_raw": "pilatus_2.h5",
                "eacc": "e12345",
                "scan_number": 1000,
                "scan_directory": "S00000_00999",
                "num_points": 500,
                "frames_per_trigger": 1,
                "headers": {"Content-Type": "application/json", "Accept": "application/json"},
            },
            [
                {
                    "source": [
                        {
                            "searchPath": "/",
                            "searchPattern": "glob:*.cbf",
                            "destinationPath": (
                                "/sls/X12SA/data/e12345/Data10/pilatus_2/S00000_00999"
                            ),
                        }
                    ]
                },
                [
                    "zmqWriter",
                    "e12345",
                    {
                        "addr": "tcp://x12sa-pd-2:8888",
                        "dst": ["file"],
                        "numFrm": 500,
                        "timeout": 2000,
                        "ifType": "PULL",
                        "user": "e12345",
                    },
                ],
                [
                    "zmqWriter",
                    "e12345",
                    {
                        "frmCnt": 500,
                        "timeout": 2000,
                    },
                ],
            ],
            [
                "http://x12sa-pd-2:8080/stream/pilatus_2",
                "http://xbl-daq-34:8091/pilatus_2/run",
                "http://xbl-daq-34:8091/pilatus_2/wait",
            ],
            False,  # return of res.ok is False!
            True,
        ),
    ],
)
def test_prep_file_writer(mock_det, scaninfo, data_msgs, urls, requests_state, expected_exception):
    with mock.patch.object(
        mock_det.custom_prepare, "close_file_writer"
    ) as mock_close_file_writer, mock.patch.object(
        mock_det.custom_prepare, "stop_file_writer"
    ) as mock_stop_file_writer, mock.patch.object(
        mock_det, "filewriter"
    ) as mock_filewriter, mock.patch.object(
        mock_det.custom_prepare, "create_directory"
    ) as mock_create_directory, mock.patch.object(
        mock_det.custom_prepare, "send_requests_put"
    ) as mock_send_requests_put:
        mock_det.scaninfo.scan_number = scaninfo["scan_number"]
        mock_det.scaninfo.num_points = scaninfo["num_points"]
        mock_det.scaninfo.frames_per_trigger = scaninfo["frames_per_trigger"]
        mock_det.scaninfo.username = scaninfo["eacc"]
        mock_filewriter.compile_full_filename.return_value = scaninfo["filepath_raw"]
        mock_filewriter.get_scan_directory.return_value = scaninfo["scan_directory"]
        instance = mock_send_requests_put.return_value
        instance.ok = requests_state
        instance.raise_for_status.side_effect = Exception

        if expected_exception:
            with pytest.raises(Exception):
                mock_det.timeout = 0.1
                mock_det.custom_prepare.prepare_data_backend()
                mock_close_file_writer.assert_called_once()
                mock_stop_file_writer.assert_called_once()
                instance.raise_for_status.assert_called_once()
        else:
            mock_det.custom_prepare.prepare_data_backend()

            mock_close_file_writer.assert_called_once()
            mock_stop_file_writer.assert_called_once()

            # Assert values set on detector
            assert mock_det.cam.file_path.get() == "/dev/shm/zmq/"
            assert (
                mock_det.cam.file_name.get()
                == f"{scaninfo['eacc']}_2_{scaninfo['scan_number']:05d}"
            )
            assert mock_det.cam.auto_increment.get() == 1
            assert mock_det.cam.file_number.get() == 0
            assert mock_det.cam.file_format.get() == 0
            assert mock_det.cam.file_template.get() == "%s%s_%5.5d.cbf"
            # Remove last / from destinationPath
            mock_create_directory.assert_called_once_with(
                os.path.join(data_msgs[0]["source"][0]["destinationPath"])
            )
            assert mock_send_requests_put.call_count == 3

            calls = [
                mock.call(url=url, data=data_msg, headers=scaninfo["headers"])
                for url, data_msg in zip(urls, data_msgs)
            ]
            for call, mock_call in zip(calls, mock_send_requests_put.call_args_list):
                assert call == mock_call


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


def test_stop(mock_det):
    with mock.patch.object(
        mock_det.custom_prepare, "stop_detector"
    ) as mock_stop_det, mock.patch.object(
        mock_det.custom_prepare, "stop_file_writer"
    ) as mock_stop_file_writer, mock.patch.object(
        mock_det.custom_prepare, "close_file_writer"
    ) as mock_close_file_writer:
        mock_det.stop()
        mock_stop_det.assert_called_once()
        mock_stop_file_writer.assert_called_once()
        mock_close_file_writer.assert_called_once()
        assert mock_det.stopped is True


@pytest.mark.parametrize(
    "stopped, mcs_stage_state, expected_exception",
    [
        (
            False,
            ophyd.Staged.no,
            False,
        ),
        (
            True,
            ophyd.Staged.no,
            True,
        ),
        (
            False,
            ophyd.Staged.yes,
            True,
        ),
    ],
)
def test_finished(mock_det, stopped, mcs_stage_state, expected_exception):
    with mock.patch.object(mock_det, "device_manager") as mock_dm, mock.patch.object(
        mock_det.custom_prepare, "stop_file_writer"
    ) as mock_stop_file_friter, mock.patch.object(
        mock_det.custom_prepare, "stop_detector"
    ) as mock_stop_det, mock.patch.object(
        mock_det.custom_prepare, "close_file_writer"
    ) as mock_close_file_writer:
        mock_dm.devices.mcs.obj._staged = mcs_stage_state
        mock_det.stopped = stopped
        if expected_exception:
            with pytest.raises(Exception):
                mock_det.timeout = 0.1
                mock_det.custom_prepare.finished()
                assert mock_det.stopped is stopped
                mock_stop_file_friter.assert_called()
                mock_stop_det.assert_called_once()
                mock_close_file_writer.assert_called_once()
        else:
            mock_det.custom_prepare.finished()
            if stopped:
                assert mock_det.stopped is stopped

            mock_stop_file_friter.assert_called()
            mock_stop_det.assert_called_once()
            mock_close_file_writer.assert_called_once()
