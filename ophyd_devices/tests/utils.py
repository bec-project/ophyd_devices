""" Utilities to mock and test devices."""

from typing import TYPE_CHECKING
from unittest import mock

from bec_lib.devicemanager import ScanInfo
from bec_lib.logger import bec_logger
from bec_lib.utils.import_utils import lazy_import_from
from ophyd import Device

if TYPE_CHECKING:
    from bec_lib.messages import ScanStatusMessage
else:
    # TODO: put back normal import when Pydantic gets faster
    ScanStatusMessage = lazy_import_from("bec_lib.messages", ("ScanStatusMessage",))

logger = bec_logger.logger


def patch_dual_pvs(device):
    """Patch dual PVs"""
    patch_functions_required_for_connection(device)
    device.wait_for_connection(all_signals=True)
    for walk in device.walk_signals():
        if not hasattr(walk.item, "_read_pv"):
            continue
        if not hasattr(walk.item, "_write_pv"):
            continue
        if walk.item._read_pv.pvname != walk.item._write_pv.pvname:
            walk.item._read_pv = walk.item._write_pv


def patch_functions_required_for_connection(device):
    """Patch functions required for connection. This will run the subs for all sub devices and devices.
    This is needed to ensure that the wait_for_connection method of required for connections methods are properly patched.
    """
    for event in device.event_types:
        device._run_subs(sub_type=event, value=0, timestamp=0)
    for name, dev in device.walk_subdevices(include_lazy=True):
        for event in dev.event_types:
            dev._run_subs(sub_type=event, value=0, timestamp=0)


class SocketMock:
    """Socket Mock. Used for testing"""

    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.buffer_put = []
        self.buffer_recv = [b""]
        self.is_open = False
        self.sock = None
        self.open()

    def connect(self):
        """Mock connect method"""
        print(f"connecting to {self.host} port {self.port}")

    def _put(self, msg_bytes):
        """Mock put method"""
        self.buffer_put.append(msg_bytes)
        print(self.buffer_put)

    # pylint: disable=unused-argument
    def _recv(self, buffer_length=1024):
        """Mock receive method"""
        print(self.buffer_recv)
        if isinstance(self.buffer_recv, list):
            if len(self.buffer_recv) > 0:
                ret_val = self.buffer_recv.pop(0)
            else:
                ret_val = b""
            return ret_val
        return self.buffer_recv

    def _initialize_socket(self):
        """Mock initialize socket method"""

    def put(self, msg):
        """Mock put method"""
        return self._put(msg)

    def receive(self, buffer_length=1024):
        """Mock receive method"""
        return self._recv(buffer_length=buffer_length)

    def open(self):
        """Mock open method"""
        self._initialize_socket()
        self.is_open = True

    def close(self):
        """Mock close method"""
        self.sock = None
        self.is_open = False

    def flush_buffer(self):
        """Mock flush buffer method"""
        self.buffer_put = []
        self.buffer_recv = ""


class MockPV:
    """
    MockPV class

    This class is used for mocking pyepics signals for testing purposes

    """

    _fmtsca = "<PV '%(pvname)s', count=%(count)i, type=%(typefull)s, access=%(access)s>"
    _fmtarr = "<PV '%(pvname)s', count=%(count)i/%(nelm)i, type=%(typefull)s, access=%(access)s>"
    _fields = (
        "pvname",
        "value",
        "char_value",
        "status",
        "ftype",
        "chid",
        "host",
        "count",
        "access",
        "write_access",
        "read_access",
        "severity",
        "timestamp",
        "posixseconds",
        "nanoseconds",
        "precision",
        "units",
        "enum_strs",
        "upper_disp_limit",
        "lower_disp_limit",
        "upper_alarm_limit",
        "lower_alarm_limit",
        "lower_warning_limit",
        "upper_warning_limit",
        "upper_ctrl_limit",
        "lower_ctrl_limit",
    )

    def __init__(
        self,
        pvname,
        callback=None,
        form="time",
        verbose=False,
        auto_monitor=None,
        count=None,
        connection_callback=None,
        connection_timeout=None,
        access_callback=None,
    ):
        self.pvname = pvname.strip()
        self.form = form.lower()
        self.verbose = verbose
        self._auto_monitor = auto_monitor
        self.ftype = None
        self.connected = True
        self.connection_timeout = connection_timeout
        self._user_max_count = count

        if self.connection_timeout is None:
            self.connection_timeout = 3
        self._args = {}.fromkeys(self._fields)
        self._args["pvname"] = self.pvname
        self._args["count"] = count
        self._args["nelm"] = -1
        self._args["type"] = "unknown"
        self._args["typefull"] = "unknown"
        self._args["access"] = "unknown"
        self._args["status"] = 0
        self.connection_callbacks = []
        self.mock_data = 0

        if connection_callback is not None:
            self.connection_callbacks = [connection_callback]

        self.access_callbacks = []
        if access_callback is not None:
            self.access_callbacks = [access_callback]

        self.callbacks = {}
        self._put_complete = None
        self._monref = None  # holder of data returned from create_subscription
        self._monref_mask = None
        self._conn_started = False
        if isinstance(callback, (tuple, list)):
            for i, thiscb in enumerate(callback):
                if callable(thiscb):
                    self.callbacks[i] = (thiscb, {})
        elif callable(callback):
            self.callbacks[0] = (callback, {})

        self.chid = None
        self.context = mock.MagicMock()
        self._cache_key = (pvname, form, self.context)
        self._reference_count = 0
        for conn_cb in self.connection_callbacks:
            conn_cb(pvname=pvname, conn=True, pv=self)
        for acc_cb in self.access_callbacks:
            acc_cb(True, True, pv=self)

    # pylint disable: unused-argument
    def wait_for_connection(self, timeout=None):
        """Wait for connection"""
        return self.connected

    # pylint disable: unused-argument
    def get_all_metadata_blocking(self, timeout):
        """Get all metadata blocking"""
        md = self._args.copy()
        md.pop("value", None)
        return md

    def get_all_metadata_callback(self, callback, *, timeout):
        """Get all metadata callback"""

        def get_metadata_thread(pvname):
            md = self.get_all_metadata_blocking(timeout=timeout)
            callback(pvname, md)

        get_metadata_thread(pvname=self.pvname)

    # pylint disable: unused-argument
    def put(
        self, value, wait=False, timeout=None, use_complete=False, callback=None, callback_data=None
    ):
        """MOCK PV, put function"""
        self.mock_data = value
        if callback is not None:
            callback()

    # pylint: disable=unused-argument
    def add_callback(self, callback=None, index=None, run_now=False, with_ctrlvars=True, **kw):
        """Add callback"""
        return mock.MagicMock()

    # pylint: disable=unused-argument
    def get_with_metadata(
        self,
        count=None,
        as_string=False,
        as_numpy=True,
        timeout=None,
        with_ctrlvars=False,
        form=None,
        use_monitor=True,
        as_namespace=False,
    ):
        """Get MOCKPV data together with metadata"""
        return {"value": self.mock_data}

    def get(
        self,
        count=None,
        as_string=False,
        as_numpy=True,
        timeout=None,
        with_ctrlvars=False,
        use_monitor=True,
    ):
        """Get value from MOCKPV"""
        data = self.get_with_metadata(
            count=count,
            as_string=as_string,
            as_numpy=as_numpy,
            timeout=timeout,
            with_ctrlvars=with_ctrlvars,
            use_monitor=use_monitor,
        )
        return data["value"] if data is not None else None


def get_mock_scan_info(device: Device | None) -> ScanInfo:
    """
    Get a mock scan info object.
    """
    return ScanInfo(msg=fake_scan_status_msg(device=device))


def fake_scan_status_msg(device: Device | None = None) -> ScanStatusMessage:
    """
    Create a fake scan status message.

    Args:
        device: The device creating the fake scan status message.

    """
    if device is None:
        device = Device(name="mock_device")
    logger.warning(
        (
            f"Device {device.name} is not connected to a Redis server. Fetching mocked ScanStatusMessage."
        )
    )
    return ScanStatusMessage(
        metadata={},
        scan_id="mock_scan_id",
        status="closed",
        scan_number=0,
        session_id=None,
        num_points=11,
        scan_name="mock_line_scan",
        scan_type="step",
        dataset_number=0,
        scan_report_devices=["samx"],
        user_metadata={},
        readout_priority={
            "monitored": ["bpm4a", "samx"],
            "baseline": ["eyex"],
            "async": ["waveform"],
            "continuous": [],
            "on_request": ["flyer_sim"],
        },
        scan_parameters={
            "exp_time": 0,
            "frames_per_trigger": 1,
            "settling_time": 0,
            "readout_time": 0,
            "optim_trajectory": None,
            "return_to_start": True,
            "relative": True,
            "system_config": {"file_suffix": None, "file_directory": None},
        },
        request_inputs={
            "arg_bundle": ["samx", -10, 10],
            "inputs": {},
            "kwargs": {
                "steps": 11,
                "relative": True,
                "system_config": {"file_suffix": None, "file_directory": None},
            },
        },
        info={
            "readout_priority": {
                "monitored": ["bpm4a", "samx"],
                "baseline": ["eyex"],
                "async": ["waveform"],
                "continuous": [],
                "on_request": ["flyer_sim"],
            },
            "file_suffix": None,
            "file_directory": None,
            "user_metadata": {},
            "RID": "a1d86f61-191c-4460-bcd6-f33c61b395ea",
            "scan_id": "3edb8219-75a7-4791-8f86-d5ca112b771a",
            "queue_id": "0f3639ee-899f-4ad1-9e71-f40514c937ef",
            "scan_motors": ["samx"],
            "num_points": 11,
            "positions": [
                [-10.0],
                [-8.0],
                [-6.0],
                [-4.0],
                [-2.0],
                [0.0],
                [2.0],
                [4.0],
                [6.0],
                [8.0],
                [10.0],
            ],
            "file_path": "./data/test_file",
            "scan_name": "mock_line_scan",
            "scan_type": "step",
            "scan_number": 0,
            "dataset_number": 0,
            "exp_time": 0,
            "frames_per_trigger": 1,
            "settling_time": 0,
            "readout_time": 0,
            "scan_report_devices": ["samx"],
            "monitor_sync": "bec",
            "scan_parameters": {
                "exp_time": 0,
                "frames_per_trigger": 1,
                "settling_time": 0,
                "readout_time": 0,
                "optim_trajectory": None,
                "return_to_start": True,
                "relative": True,
                "system_config": {"file_suffix": None, "file_directory": None},
            },
            "request_inputs": {
                "arg_bundle": ["samx", -10, 10],
                "inputs": {},
                "kwargs": {
                    "steps": 11,
                    "relative": True,
                    "system_config": {"file_suffix": None, "file_directory": None},
                },
            },
            "scan_msgs": [
                "metadata={'file_suffix': None, 'file_directory': None, 'user_metadata': {}, 'RID': 'a1d86f61-191c-4460-bcd6-f33c61b395ea'} scan_type='mock_line_scan' parameter={'args': {'samx': [-10, 10]}, 'kwargs': {'steps': 11, 'relative': True, 'system_config': {'file_suffix': None, 'file_directory': None}}} queue='primary'"
            ],
            "args": {"samx": [-10, 10]},
            "kwargs": {
                "steps": 11,
                "relative": True,
                "system_config": {"file_suffix": None, "file_directory": None},
            },
        },
        timestamp=1737100681.694211,
    )
