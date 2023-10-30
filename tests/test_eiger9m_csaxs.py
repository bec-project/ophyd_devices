import pytest
from unittest import mock

from ophyd.signal import Signal

from bec_lib.core import BECMessage, MessageEndpoints
from bec_lib.core.devicemanager import DeviceContainer
from bec_lib.core.tests.utils import ProducerMock


class MockSignal(Signal):
    def __init__(self, read_pv, *, name=None, parent=None, **kwargs):
        self.read_pv = read_pv
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
    from ophyd_devices.epics.devices.eiger9m_csaxs import Eiger9mCsaxs


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
    name = "eiger"
    prefix = "X12SA-ES-EIGER9M:"
    sim_mode = False
    dm = DMMock()
    # dm.add_device("mokev", value=12.4)
    with mock.patch.object(dm, "producer"):
        with mock.patch(
            "ophyd_devices.epics.devices.eiger9m_csaxs.BecScaninfoMixin"
        ) as mixin, mock.patch(
            "ophyd_devices.epics.devices.eiger9m_csaxs.FileWriterMixin"
        ) as filemixin, mock.patch(
            "ophyd_devices.epics.devices.eiger9m_csaxs.Eiger9mCsaxs._update_service_config"
        ) as mock_service_config:
            with mock.patch.object(Eiger9mCsaxs, "_init"):
                yield Eiger9mCsaxs(name=name, prefix=prefix, device_manager=dm, sim_mode=sim_mode)


@pytest.mark.parametrize(
    "trigger_source, stopped, detector_state, expected_exception",
    [
        (2, True, 1, False),
        (2, False, 0, True),
    ],
)
# TODO rewrite this one, write test for init_detector, init_filewriter is tested
def test_init(
    trigger_source,
    stopped,
    detector_state,
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
    name = "eiger"
    prefix = "X12SA-ES-EIGER9M:"
    sim_mode = False
    dm = DMMock()
    # dm.add_device("mokev", value=12.4)
    with mock.patch.object(dm, "producer"):
        with mock.patch(
            "ophyd_devices.epics.devices.eiger9m_csaxs.BecScaninfoMixin"
        ) as mixin, mock.patch(
            "ophyd_devices.epics.devices.eiger9m_csaxs.FileWriterMixin"
        ) as filemixin, mock.patch(
            "ophyd_devices.epics.devices.eiger9m_csaxs.Eiger9mCsaxs._update_service_config"
        ) as mock_service_config:
            with mock.patch.object(Eiger9mCsaxs, "_init_filewriter") as mock_init_fw:
                mock_det = Eiger9mCsaxs(
                    name=name, prefix=prefix, device_manager=dm, sim_mode=sim_mode
                )
                mock_det.cam.detector_state.put(detector_state)
                mock_det._stopped = stopped
                if expected_exception:
                    with pytest.raises(Exception):
                        mock_det._init()
                        mock_init_fw.assert_called_once()
                else:
                    mock_det._init()  # call the method you want to test
                    assert mock_det.cam.acquire.get() == 0
                    assert mock_det.cam.detector_state.get() == detector_state
                    assert mock_det.cam.trigger_mode.get() == trigger_source
                    mock_init_fw.assert_called()
                    assert mock_init_fw.call_count == 2


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
def test_init_filewriter(mock_det, eacc, exp_url, daq_status, daq_cfg, expected_exception):
    """Test _init_filewriter (std daq in this case)

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
                mock_det._init_filewriter()
        else:
            mock_det._init_filewriter()

            assert mock_det.std_rest_server_url == exp_url
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
    with mock.patch.object(mock_det, "std_client") as mock_std_daq, mock.patch.object(
        Eiger9mCsaxs, "_publish_file_location"
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
        mock_det._stopped = stopped
        mock_det.cam.detector_state.put(detector_state)
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
def test_prep_file_writer(mock_det, scaninfo, daq_status, expected_exception):
    with mock.patch.object(mock_det, "std_client") as mock_std_daq, mock.patch.object(
        mock_det, "_filepath_exists"
    ) as mock_file_path_exists, mock.patch.object(
        mock_det, "_stop_file_writer"
    ) as mock_stop_file_writer:
        # mock_det = eiger_factory(name, prefix, sim_mode)
        mock_det.std_client = mock_std_daq
        mock_std_daq.start_writer_async.return_value = None
        mock_std_daq.get_status.return_value = daq_status
        mock_det.filewriter.compile_full_filename.return_value = scaninfo["filepath"]
        mock_det.scaninfo.num_points = scaninfo["num_points"]
        mock_det.scaninfo.frames_per_trigger = scaninfo["frames_per_trigger"]

        if expected_exception:
            with pytest.raises(Exception):
                mock_det._prep_file_writer()
                mock_file_path_exists.assert_called_once()
                assert mock_stop_file_writer.call_count == 2

        else:
            mock_det._prep_file_writer()
            mock_file_path_exists.assert_called_once()
            mock_stop_file_writer.assert_called_once()

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
    with mock.patch.object(mock_det, "_finished") as mock_finished, mock.patch.object(
        mock_det, "_publish_file_location"
    ) as mock_publish_file_location:
        mock_det._stopped = stopped
        if expected_exception:
            mock_det.unstage()
            assert mock_det._stopped == True
        else:
            mock_det.unstage()
            mock_finished.assert_called_once()
            mock_publish_file_location.assert_called_with(done=True, successful=True)
            assert mock_det._stopped == False


def test_stop_fw(mock_det):
    with mock.patch.object(mock_det, "std_client") as mock_std_daq:
        mock_std_daq.stop_writer.return_value = None
        mock_det.std_client = mock_std_daq
        mock_det._stop_file_writer()
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


def test_stop(mock_det):
    with mock.patch.object(mock_det, "_stop_det") as mock_stop_det, mock.patch.object(
        mock_det, "_stop_file_writer"
    ) as mock_stop_file_writer:
        mock_det.stop()
        mock_stop_det.assert_called_once()
        mock_stop_file_writer.assert_called_once()
        assert mock_det._stopped == True


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
    with mock.patch.object(mock_det, "std_client") as mock_std_daq, mock.patch.object(
        mock_det, "_stop_file_writer"
    ) as mock_stop_file_friter, mock.patch.object(mock_det, "_stop_det") as mock_stop_det:
        mock_std_daq.get_status.return_value = daq_status
        mock_det.cam.acquire.put(cam_state)
        mock_det.scaninfo.num_points = scaninfo["num_points"]
        mock_det.scaninfo.frames_per_trigger = scaninfo["frames_per_trigger"]
        if expected_exception:
            with pytest.raises(Exception):
                mock_det._finished()
                assert mock_det._stopped == stopped
                mock_stop_file_friter.assert_called()
                mock_stop_det.assert_called_once()
        else:
            mock_det._finished()
            if stopped:
                assert mock_det._stopped == stopped

            mock_stop_file_friter.assert_called()
            mock_stop_det.assert_called_once()
