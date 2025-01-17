""" Utility class linked to BEC"""

import time

from bec_lib import bec_logger
from bec_lib.devicemanager import DeviceContainer
from bec_lib.tests.utils import ConnectorMock
from ophyd import Device, Kind, Signal

from ophyd_devices.utils.socket import data_shape, data_type

logger = bec_logger.logger
DEFAULT_EPICSSIGNAL_VALUE = object()


class DeviceMock:
    """Mock for Device"""

    def __init__(self, name: str, value: float = 0.0):
        self.name = name
        self.read_buffer = value
        self._config = {"deviceConfig": {"limits": [-50, 50]}, "userParameter": None}
        self._read_only = False
        self._enabled = True

    def read(self):
        """Return the current value of the device"""
        return {self.name: {"value": self.read_buffer}}

    def readback(self):
        """Return the current value of the device"""
        return self.read_buffer

    @property
    def read_only(self) -> bool:
        """Get the read only status of the device"""
        return self._read_only

    @read_only.setter
    def read_only(self, val: bool):
        self._read_only = val

    @property
    def enabled(self) -> bool:
        """Get the enabled status of the device"""
        return self._enabled

    @enabled.setter
    def enabled(self, val: bool):
        self._enabled = val

    @property
    def user_parameter(self):
        """Get the user parameter of the device"""
        return self._config["userParameter"]

    @property
    def obj(self):
        """Get the device object"""
        return self


class DMMock:
    """Mock for DeviceManager

    The mocked DeviceManager creates a device containert and a connector.

    """

    def __init__(self):
        self.devices = DeviceContainer()
        self.connector = ConnectorMock()

    def add_device(self, name: str, value: float = 0.0):
        self.devices[name] = DeviceMock(name, value)


class ConfigSignal(Signal):
    def __init__(
        self,
        *,
        name,
        value=0,
        timestamp=None,
        parent=None,
        labels=None,
        kind=Kind.hinted,
        tolerance=None,
        rtolerance=None,
        metadata=None,
        cl=None,
        attr_name="",
        config_storage_name: str = "config_storage",
    ):
        super().__init__(
            name=name,
            value=value,
            timestamp=timestamp,
            parent=parent,
            labels=labels,
            kind=kind,
            tolerance=tolerance,
            rtolerance=rtolerance,
            metadata=metadata,
            cl=cl,
            attr_name=attr_name,
        )

        self.storage_name = config_storage_name

    def get(self):
        self._readback = getattr(self.parent, self.storage_name)[self.name]
        return self._readback

    def put(self, value, connection_timeout=1, callback=None, timeout=1, **kwargs):
        """Using channel access, set the write PV to `value`.

        Keyword arguments are passed on to callbacks

        Parameters
        ----------
        value : any
            The value to set
        connection_timeout : float, optional
            If not already connected, allow up to `connection_timeout` seconds
            for the connection to complete.
        use_complete : bool, optional
            Override put completion settings
        callback : callable
            Callback for when the put has completed
        timeout : float, optional
            Timeout before assuming that put has failed. (Only relevant if
            put completion is used.)
        """

        old_value = self.get()
        timestamp = time.time()
        getattr(self.parent, self.storage_name)[self.name] = value
        super().put(value, timestamp=timestamp, force=True)
        self._run_subs(
            sub_type=self.SUB_VALUE, old_value=old_value, value=value, timestamp=timestamp
        )

    def describe(self):
        """Provide schema and meta-data for :meth:`~BlueskyInterface.read`

        This keys in the `OrderedDict` this method returns must match the
        keys in the `OrderedDict` return by :meth:`~BlueskyInterface.read`.

        This provides schema related information, (ex shape, dtype), the
        source (ex PV name), and if available, units, limits, precision etc.

        Returns
        -------
        data_keys : OrderedDict
            The keys must be strings and the values must be dict-like
            with the ``event_model.event_descriptor.data_key`` schema.
        """
        if self._readback is DEFAULT_EPICSSIGNAL_VALUE:
            val = self.get()
        else:
            val = self._readback
        return {
            self.name: {
                "source": f"{self.parent.prefix}:{self.name}",
                "dtype": data_type(val),
                "shape": data_shape(val),
            }
        }


class DeviceClassConnectionError(Device):
    """
    Device that always raises a connection error when trying to connect.
    It is used to test the wait_for_connection method in the DeviceServer.
    """

    @property
    def connected(self):
        return False

    def wait_for_connection(self, all_signals=False, timeout=2):
        raise RuntimeError("Connection error")


class DeviceClassInitError(Device):
    """
    Device that always raises an error when trying to construct the object.
    It is used to test the error handling in the DeviceServer.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        raise RuntimeError("Init error")
