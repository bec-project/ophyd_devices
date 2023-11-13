import time

from bec_lib import bec_logger
from bec_lib.devicemanager import DeviceContainer

from ophyd import Signal, Kind

from ophyd_devices.utils.socket import data_shape, data_type


logger = bec_logger.logger
DEFAULT_EPICSSIGNAL_VALUE = object()


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


class ProducerMock:
    def __init__(self, store_data=True) -> None:
        self.message_sent = []
        self._get_buffer = {}
        self.store_data = store_data

    def set(self, topic, msg, pipe=None, expire: int = None):
        if pipe:
            pipe._pipe_buffer.append(("set", (topic, msg), {"expire": expire}))
            return
        self.message_sent.append({"queue": topic, "msg": msg, "expire": expire})

    def send(self, topic, msg, pipe=None):
        if pipe:
            pipe._pipe_buffer.append(("send", (topic, msg), {}))
            return
        self.message_sent.append({"queue": topic, "msg": msg})

    def set_and_publish(self, topic, msg, pipe=None, expire: int = None):
        if pipe:
            pipe._pipe_buffer.append(("set_and_publish", (topic, msg), {"expire": expire}))
            return
        self.message_sent.append({"queue": topic, "msg": msg, "expire": expire})

    def lpush(self, topic, msg, pipe=None):
        if pipe:
            pipe._pipe_buffer.append(("lpush", (topic, msg), {}))
            return

    def rpush(self, topic, msg, pipe=None):
        if pipe:
            pipe._pipe_buffer.append(("rpush", (topic, msg), {}))
            return
        pass

    def lrange(self, topic, start, stop, pipe=None):
        if pipe:
            pipe._pipe_buffer.append(("lrange", (topic, start, stop), {}))
            return
        return []

    def get(self, topic, pipe=None):
        if pipe:
            pipe._pipe_buffer.append(("get", (topic,), {}))
            return
        val = self._get_buffer.get(topic)
        if isinstance(val, list):
            return val.pop(0)
        self._get_buffer.pop(topic, None)
        return val

    def keys(self, pattern: str) -> list:
        return []

    def pipeline(self):
        return PipelineMock(self)

    def delete(self, topic, pipe=None):
        if pipe:
            pipe._pipe_buffer.append(("delete", (topic,), {}))
            return

    def lset(self, topic: str, index: int, msgs: str, pipe=None) -> None:
        if pipe:
            pipe._pipe_buffer.append(("lrange", (topic, index, msgs), {}))
            return


class PipelineMock:
    _pipe_buffer = []
    _producer = None

    def __init__(self, producer) -> None:
        self._producer = producer

    def execute(self):
        if not self._producer.store_data:
            self._pipe_buffer = []
            return []
        res = [
            getattr(self._producer, method)(*args, **kwargs)
            for method, args, kwargs in self._pipe_buffer
        ]
        self._pipe_buffer = []
        return res


class DMMock:
    """Mock for DeviceManager

    The mocked DeviceManager creates a device containert and a producer.

    """

    def __init__(self):
        self.devices = DeviceContainer()
        self.producer = ProducerMock()

    def add_device(self, name: str, value: float = 0.0):
        self.devices[name] = DeviceMock(name, value)


# class MockProducer:
#     def set_and_publish(self, endpoint: str, msgdump: str):
#         logger.info(f"BECMessage to {endpoint} with msg dump {msgdump}")


# class MockDeviceManager:
#     def __init__(self) -> None:
#         self.devices = devices()


# class OphydObject:
#     def __init__(self) -> None:
#         self.name = "mock_mokev"
#         self.obj = mokev()


# class devices:
#     def __init__(self):
#         self.mokev = OphydObject()


# class mokev:
#     def __init__(self):
#         self.name = "mock_mokev"

#     def read(self):
#         return {self.name: {"value": 16.0, "timestamp": time.time()}}


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

    def put(
        self,
        value,
        connection_timeout=1,
        callback=None,
        timeout=1,
        **kwargs,
    ):
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
            sub_type=self.SUB_VALUE,
            old_value=old_value,
            value=value,
            timestamp=timestamp,
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
