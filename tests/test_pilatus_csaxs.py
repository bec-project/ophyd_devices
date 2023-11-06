import pytest
from unittest import mock

from ophyd.signal import Signal
from ophyd import Staged

from bec_lib.core import BECMessage, MessageEndpoints
from bec_lib.core.devicemanager import DeviceContainer
from bec_lib.core.tests.utils import ProducerMock
import requests


class MockSignal(Signal):
    def __init__(self, read_pv, *, string=False, name=None, parent=None, **kwargs):
        self.read_pv = read_pv
        self._string = bool(string)
        super().__init__(name=name, parent=parent, **kwargs)
        self._waited_for_connection = False
        self._subscriptions = []

    def wait_for_connection(self):
        self._waited_for_connection = True

    def subscribe(self, method, event_type, **kw):
        self._subscriptions.append((method, event_type, kw))

    def describe_configuration(self):
        return {self.name + "_conf": {"source": "SIM:test"}}

    def read_configuration(self):
        return {self.name + "_conf": {"value": 0}}


with mock.patch("ophyd.EpicsSignal", new=MockSignal), mock.patch(
    "ophyd.EpicsSignalRO", new=MockSignal
), mock.patch("ophyd.EpicsSignalWithRBV", new=MockSignal):
    from ophyd_devices.epics.devices.pilatus_csaxs import PilatuscSAXS


# TODO maybe specify here that this DeviceMock is for usage in the DeviceServer
class DeviceMock:
    def __init__(self, name: str, value: float = 0.0):
        self.name = name
        self.read_buffer = value
        self._config = {"deviceConfig": {"limits": [-50, 50]}, "userParameter": None}
        self._enabled_set = True
        self._enabled = True

    def read(self):
        return {self.name: {"value": self.read_buffer}}

    def readback(self):
        return self.read_buffer

    @property
    def enabled_set(self) -> bool:
        return self._enabled_set

    @enabled_set.setter
    def enabled_set(self, val: bool):
        self._enabled_set = val

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, val: bool):
        self._enabled = val

    @property
    def user_parameter(self):
        return self._config["userParameter"]

    @property
    def obj(self):
        return self


class DMMock:
    """Mock for DeviceManager

    The mocked DeviceManager creates a device containert and a producer.

    """

    def __init__(self):
        self.devices = DeviceContainer()
        self.producer = ProducerMock()

    def add_device(self, name: str, value: float = 0.0):
        self.devices[name] = DeviceMock(name, value)


@pytest.fixture(scope="function")
def mock_det():
    name = "pilatus"
    prefix = "X12SA-ES-PILATUS300K:"
    sim_mode = False
    dm = DMMock()
    # dm.add_device("mokev", value=12.4)
    with mock.patch.object(dm, "producer"):
        with mock.patch.object(
            PilatuscSAXS, "_update_service_config"
        ) as mock_update_service_config, mock.patch(
            "ophyd_devices.epics.devices.pilatus_csaxs.FileWriterMixin"
        ) as filemixin:
            with mock.patch.object(PilatuscSAXS, "_init"):
                yield PilatuscSAXS(name=name, prefix=prefix, device_manager=dm, sim_mode=sim_mode)


@pytest.mark.parametrize(
    "trigger_source, sim_mode, scan_status_msg, expected_exception",
    [
        (
            1,
            True,
            BECMessage.ScanStatusMessage(
                scanID="1",
                status={},
                info={
                    "RID": "mockrid1111",
                    "queueID": "mockqueueID111",
                    "scan_number": 1,
                    "exp_time": 0.012,
                    "num_points": 500,
                    "readout_time": 0.003,
                    "scan_type": "fly",
                    "num_lines": 0.012,
                    "frames_per_trigger": 1,
                },
            ),
            True,
        ),
        (
            1,
            False,
            BECMessage.ScanStatusMessage(
                scanID="1",
                status={},
                info={
                    "RID": "mockrid1111",
                    "queueID": "mockqueueID111",
                    "scan_number": 1,
                    "exp_time": 0.012,
                    "num_points": 500,
                    "readout_time": 0.003,
                    "scan_type": "fly",
                    "num_lines": 0.012,
                    "frames_per_trigger": 1,
                },
            ),
            False,
        ),
    ],
)
# TODO rewrite this one, write test for init_detector, init_filewriter is tested
def test_init(
    trigger_source,
    sim_mode,
    scan_status_msg,
    expected_exception,
):
    """Test the _init function:

    This includes testing the functions:
    - _set_default_parameter
    - _init_detector
    - _stop_det
    - _set_trigger
    --> Testing the filewriter is done in test_init_filewriter

    Validation upon setting the correct PVs

    """
    name = "pilatus"
    prefix = "X12SA-ES-PILATUS300K:"
    sim_mode = sim_mode
    dm = DMMock()
    with mock.patch.object(dm, "producer") as producer, mock.patch.object(
        PilatuscSAXS, "_init_filewriter"
    ) as mock_init_fw, mock.patch.object(
        PilatuscSAXS, "_update_scaninfo"
    ) as mock_update_scaninfo, mock.patch.object(
        PilatuscSAXS, "_update_filewriter"
    ) as mock_update_filewriter, mock.patch.object(
        PilatuscSAXS, "_update_service_config"
    ) as mock_update_service_config:
        mock_det = PilatuscSAXS(name=name, prefix=prefix, device_manager=dm, sim_mode=sim_mode)
        if expected_exception:
            with pytest.raises(Exception):
                mock_det._init()
                mock_init_fw.assert_called_once()
        else:
            mock_det._init()  # call the method you want to test
            assert mock_det.cam.acquire.get() == 0
            assert mock_det.cam.trigger_mode.get() == trigger_source
            mock_init_fw.assert_called()
            mock_update_scaninfo.assert_called_once()
            mock_update_filewriter.assert_called_once()
            mock_update_service_config.assert_called_once()

            assert mock_init_fw.call_count == 2


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
    with mock.patch.object(PilatuscSAXS, "_publish_file_location") as mock_publish_file_location:
        mock_det.scaninfo.num_points = scaninfo["num_points"]
        mock_det.scaninfo.frames_per_trigger = scaninfo["frames_per_trigger"]
        mock_det.filewriter.compile_full_filename.return_value = scaninfo["filepath"]
        # TODO consider putting energy as variable in scaninfo
        mock_det.device_manager.add_device("mokev", value=12.4)
        mock_det._stopped = stopped
        with mock.patch.object(mock_det, "_prep_file_writer") as mock_prep_fw:
            mock_det.filepath = scaninfo["filepath"]
            if expected_exception:
                with pytest.raises(Exception):
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


def test_pre_scan(mock_det):
    mock_det.pre_scan()
    assert mock_det.cam.acquire.get() == 1


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
        msg = BECMessage.FileMessage(file_path=scaninfo["filepath"], done=scaninfo["done"]).dumps()
    else:
        msg = BECMessage.FileMessage(
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
    "requests_state, expected_exception, url",
    [
        (
            True,
            False,
            "http://x12sa-pd-2:8080/stream/pilatus_2",
        ),
        (
            False,
            False,
            "http://x12sa-pd-2:8080/stream/pilatus_2",
        ),
    ],
)
def test_close_file_writer(mock_det, requests_state, expected_exception, url):
    with mock.patch.object(mock_det, "_send_requests_delete") as mock_send_requests_delete:
        instance = mock_send_requests_delete.return_value
        instance.ok = requests_state
        if expected_exception:
            mock_det._close_file_writer()
            mock_send_requests_delete.assert_called_once_with(url=url)
            instance.raise_for_status.called_once()
        else:
            mock_det._close_file_writer()
            mock_send_requests_delete.assert_called_once_with(url=url)


@pytest.mark.parametrize(
    "requests_state, expected_exception, url",
    [
        (
            True,
            False,
            "http://xbl-daq-34:8091/pilatus_2/stop",
        ),
        (
            False,
            True,
            "http://xbl-daq-34:8091/pilatus_2/stop",
        ),
    ],
)
def test_stop_file_writer(mock_det, requests_state, expected_exception, url):
    with mock.patch.object(mock_det, "_send_requests_put") as mock_send_requests_put:
        instance = mock_send_requests_put.return_value
        instance.ok = requests_state
        instance.raise_for_status.side_effect = Exception
        if expected_exception:
            with pytest.raises(Exception):
                mock_det._stop_file_writer()
                mock_send_requests_put.assert_called_once_with(url=url)
                instance.raise_for_status.called_once()
        else:
            mock_det._stop_file_writer()
            mock_send_requests_put.assert_called_once_with(url=url)


# @pytest.mark.parametrize(
#     "scaninfo, daq_status, expected_exception",
#     [
#         (
#             {
#                 "eacc": "e12345",
#                 "num_points": 500,
#                 "frames_per_trigger": 1,
#                 "filepath": "test.h5",
#                 "scanID": "123",
#             },
#             {"state": "BUSY", "acquisition": {"state": "WAITING_IMAGES"}},
#             False,
#         ),
#         (
#             {
#                 "eacc": "e12345",
#                 "num_points": 500,
#                 "frames_per_trigger": 1,
#                 "filepath": "test.h5",
#                 "scanID": "123",
#             },
#             {"state": "BUSY", "acquisition": {"state": "WAITING_IMAGES"}},
#             False,
#         ),
#         (
#             {
#                 "eacc": "e12345",
#                 "num_points": 500,
#                 "frames_per_trigger": 1,
#                 "filepath": "test.h5",
#                 "scanID": "123",
#             },
#             {"state": "BUSY", "acquisition": {"state": "ERROR"}},
#             True,
#         ),
#     ],
# )
# def test_prep_file_writer(mock_det, scaninfo, daq_status, expected_exception):
#     with mock.patch.object(mock_det, "std_client") as mock_std_daq, mock.patch.object(
#         mock_det, "_filepath_exists"
#     ) as mock_file_path_exists, mock.patch.object(
#         mock_det, "_stop_file_writer"
#     ) as mock_stop_file_writer, mock.patch.object(
#         mock_det, "scaninfo"
#     ) as mock_scaninfo:
#         # mock_det = eiger_factory(name, prefix, sim_mode)
#         mock_det.std_client = mock_std_daq
#         mock_std_daq.start_writer_async.return_value = None
#         mock_std_daq.get_status.return_value = daq_status
#         mock_det.filewriter.compile_full_filename.return_value = scaninfo["filepath"]
#         mock_det.scaninfo.num_points = scaninfo["num_points"]
#         mock_det.scaninfo.frames_per_trigger = scaninfo["frames_per_trigger"]

#         if expected_exception:
#             with pytest.raises(Exception):
#                 mock_det._prep_file_writer()
#                 mock_file_path_exists.assert_called_once()
#                 assert mock_stop_file_writer.call_count == 2

#         else:
#             mock_det._prep_file_writer()
#             mock_file_path_exists.assert_called_once()
#             mock_stop_file_writer.assert_called_once()

#         daq_writer_call = {
#             "output_file": scaninfo["filepath"],
#             "n_images": int(scaninfo["num_points"] * scaninfo["frames_per_trigger"]),
#         }
#         mock_std_daq.start_writer_async.assert_called_with(daq_writer_call)


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
    with mock.patch.object(mock_det, "_finished") as mock_finished, mock.patch.object(
        mock_det, "_publish_file_location"
    ) as mock_publish_file_location, mock.patch.object(
        mock_det, "_start_h5converter"
    ) as mock_start_h5converter:
        mock_det._stopped = stopped
        if expected_exception:
            mock_det.unstage()
            assert mock_det._stopped == True
        else:
            mock_det.unstage()
            mock_finished.assert_called_once()
            mock_publish_file_location.assert_called_with(done=True, successful=True)
            mock_start_h5converter.assert_called_once()
            assert mock_det._stopped == False


# def test_stop_fw(mock_det):
#     with mock.patch.object(mock_det, "std_client") as mock_std_daq:
#         mock_std_daq.stop_writer.return_value = None
#         mock_det.std_client = mock_std_daq
#         mock_det._stop_file_writer()
#         mock_std_daq.stop_writer.assert_called_once()


def test_stop(mock_det):
    with mock.patch.object(mock_det, "_stop_det") as mock_stop_det, mock.patch.object(
        mock_det, "_stop_file_writer"
    ) as mock_stop_file_writer, mock.patch.object(
        mock_det, "_close_file_writer"
    ) as mock_close_file_writer:
        mock_det.stop()
        mock_stop_det.assert_called_once()
        mock_stop_file_writer.assert_called_once()
        mock_close_file_writer.assert_called_once()
        assert mock_det._stopped == True


@pytest.mark.parametrize(
    "stopped, mcs_stage_state, expected_exception",
    [
        (
            False,
            Staged.no,
            False,
        ),
        (
            True,
            Staged.no,
            False,
        ),
        (
            False,
            Staged.yes,
            True,
        ),
    ],
)
def test_finished(mock_det, stopped, mcs_stage_state, expected_exception):
    with mock.patch.object(mock_det, "device_manager") as mock_dm, mock.patch.object(
        mock_det, "_stop_file_writer"
    ) as mock_stop_file_friter, mock.patch.object(
        mock_det, "_stop_det"
    ) as mock_stop_det, mock.patch.object(
        mock_det, "_close_file_writer"
    ) as mock_close_file_writer:
        mock_dm.devices.mcs.obj._staged = mcs_stage_state
        mock_det._stopped = stopped
        if expected_exception:
            with pytest.raises(Exception):
                mock_det._finished()
                assert mock_det._stopped == stopped
                mock_stop_file_friter.assert_called()
                mock_stop_det.assert_called_once()
                mock_close_file_writer.assert_called_once()
        else:
            mock_det._finished()
            if stopped:
                assert mock_det._stopped == stopped

            mock_stop_file_friter.assert_called()
            mock_stop_det.assert_called_once()
            mock_close_file_writer.assert_called_once()
