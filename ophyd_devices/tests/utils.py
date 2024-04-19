from unittest import mock

from bec_lib.devicemanager import DeviceContainer
from bec_lib.tests.utils import ConnectorMock


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
            callback(None, None, None)

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
