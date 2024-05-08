import threading
import time

import numpy as np
from bec_lib import messages
from bec_lib.endpoints import MessageEndpoints
from ophyd import Component as Cpt
from ophyd import Device, Kind, Signal
from ophyd.flyers import FlyerInterface
from ophyd.ophydobj import Kind
from ophyd.status import DeviceStatus, SubscriptionStatus
from ophyd.utils import ReadOnlyError


class SynSetpoint(Signal):
    def __init__(
        self,
        name,
        *,
        value=0,
        dtype=float,
        timestamp=None,
        parent=None,
        labels=None,
        kind=Kind.hinted,
        tolerance=None,
        rtolerance=None,
        metadata=None,
        cl=None,
        attr_name="",
        auto_monitor=False,
    ):
        self._dtype = dtype
        if self._dtype == str and value == 0:
            value = ""
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

    def put(self, value, *, timestamp=None, force=False):
        old_val = self._readback
        self._readback = self._dtype(value)
        self._run_subs(
            sub_type="value", old_value=old_val, value=self._readback, timestamp=time.time()
        )

    def get(self):
        return self._readback

    def describe(self):
        res = super().describe()
        # There should be only one key here, but for the sake of generality....
        for k in res:
            res[k]["precision"] = self.parent.precision
        return res


class SynData(Signal):
    _default_sub = "value"

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
        auto_monitor=False,
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
        self._reset_data()

    def _reset_data(self):
        self._readback = np.array([])

    def get(self):
        return self._readback

    def append(self, val: float):
        self._readback = np.append(self._readback, val)

    def describe(self):
        res = super().describe()
        # There should be only one key here, but for the sake of
        # generality....
        for k in res:
            res[k]["precision"] = self.parent.precision
        return res

    @property
    def timestamp(self):
        """Timestamp of the readback value"""
        return time.time()

    def put(self, value, *, timestamp=None, force=False):
        raise ReadOnlyError("The signal {} is readonly.".format(self.name))

    def set(self, value, *, timestamp=None, force=False):
        raise ReadOnlyError("The signal {} is readonly.".format(self.name))


class SynXtremeOtf(FlyerInterface, Device):
    """
    PGM on-the-fly scan
    """

    SUB_VALUE = "value"
    SUB_FLYER = "flyer"
    _default_sub = SUB_VALUE

    e1 = Cpt(SynSetpoint, kind=Kind.config)
    e2 = Cpt(SynSetpoint, kind=Kind.config)
    time = Cpt(SynSetpoint, kind=Kind.config)
    folder = Cpt(SynSetpoint, dtype=str, value="", kind=Kind.config)
    file = Cpt(SynSetpoint, dtype=str, value="", kind=Kind.config)
    acquire = Cpt(SynSetpoint, auto_monitor=True)
    edata = Cpt(SynData, kind=Kind.hinted, auto_monitor=True)
    data = Cpt(SynData, kind=Kind.hinted, auto_monitor=True)
    idata = Cpt(SynData, kind=Kind.hinted, auto_monitor=True)
    fdata = Cpt(SynData, kind=Kind.hinted, auto_monitor=True)
    count = Cpt(SynData, kind=Kind.omitted, auto_monitor=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._start_time = 0
        self.acquire.subscribe(self._update_status, run=False)
        self.count.subscribe(self._update_data, run=False)
        self._data_event = threading.Event()
        self.precision = 3

    def kickoff(self):
        self._start_time = time.time()
        self.acquire.put(1)
        status = DeviceStatus(self)
        status.set_finished()
        return status

    def complete(self):
        def check_value(*, old_value, value, **kwargs):
            return old_value == 1 and value == 0

        status = SubscriptionStatus(self.acquire, check_value, event_type=self.acquire.SUB_VALUE)
        return status

    def collect(self):
        data = {"time": self._start_time, "data": {}, "timestamps": {}}
        for attr in ("edata", "data", "idata", "fdata"):
            obj = getattr(self, attr)
            data["data"][obj.name] = obj.get()
            data["timestamps"][obj.name] = obj.timestamp

        return data

    def describe_collect(self):
        desc = {}
        for attr in ("edata", "data", "idata", "fdata"):
            desc.update(getattr(self, attr).describe())
        return desc

    def _update_status(self, *, old_value, value, **kwargs):
        if old_value == 1 and value == 0:
            self._done_acquiring()
            return
        if old_value == 0 and value == 1:
            threading.Thread(target=self._start_acquiring, daemon=True).start()

    def _reset_data(self):
        for entry in ("edata", "data", "idata", "fdata"):
            getattr(self, entry)._reset_data()
        self.count._readback = 0
        self._data_event.clear()

    def _populate_data(self):
        self._reset_data()
        while not self._data_event.is_set():
            for entry in ("edata", "data", "idata", "fdata"):
                getattr(self, entry).append(np.random.rand())
            self.count._readback = len(self.edata.get())
            self.count._run_subs(
                sub_type="value",
                old_value=self.count._readback - 1,
                value=self.count._readback,
                timestamp=time.time(),
            )
            time.sleep(0.2)
        self._data_event.clear()

    def _start_acquiring(self):
        threading.Thread(target=self._populate_data, daemon=True).start()
        timeout_event = threading.Event()
        flag = timeout_event.wait(self.time.get())
        if not flag:
            self._data_event.set()
            self.acquire.put(0)

    def _update_data(self, value, **kwargs):
        if value == 0:
            return
        data = self.collect()
        self._run_subs(sub_type=self.SUB_FLYER, value=data)


class SynXtremeOtfReplay(FlyerInterface, Device):
    """
    PGM on-the-fly scan
    """

    SUB_VALUE = "value"
    SUB_FLYER = "flyer"
    _default_sub = SUB_VALUE

    e1 = Cpt(SynSetpoint, kind=Kind.config)
    e2 = Cpt(SynSetpoint, kind=Kind.config)
    time = Cpt(SynSetpoint, kind=Kind.config)
    folder = Cpt(SynSetpoint, dtype=str, value="", kind=Kind.config)
    file = Cpt(SynSetpoint, dtype=str, value="", kind=Kind.config)
    acquire = Cpt(SynSetpoint, auto_monitor=True)
    edata = Cpt(SynData, kind=Kind.hinted, auto_monitor=True)
    data = Cpt(SynData, kind=Kind.hinted, auto_monitor=True)
    idata = Cpt(SynData, kind=Kind.hinted, auto_monitor=True)
    fdata = Cpt(SynData, kind=Kind.hinted, auto_monitor=True)
    count = Cpt(SynData, kind=Kind.omitted, auto_monitor=True)

    def __init__(self, *args, device_manager=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._start_time = 0
        self.acquire.subscribe(self._update_status, run=False)
        self.count.subscribe(self._update_data, run=False)
        self._data_event = threading.Event()
        self.precision = 3
        self._measurement_data = {}
        self._device_manager = device_manager

    def kickoff(self):
        self._read_file()
        self._start_time = time.time()
        self.acquire.put(1)
        status = DeviceStatus(self)
        status.set_finished()
        return status

    def _read_file(self):
        data = {}  # Create an empty dictionary to store the data

        # Read the input file
        with open(self.file.get(), "r") as file:
            lines = file.readlines()

        # Extract column titles and data types
        titles = lines[0].strip().split("\t")
        data_types = lines[1].strip().split("\t")

        # Initialize the dictionary with empty lists for each title
        for title in titles:
            data[title] = []

        # Process the data lines and populate the dictionary
        for line in lines[2:]:
            values = line.strip().split("\t")
            for title, value, data_type in zip(titles, values, data_types):
                if data_type == "java.lang.Double":
                    data[title].append(float(value))
                else:
                    data[title].append(value)
        self._measurement_data = data

    def complete(self):
        def check_value(*, old_value, value, **kwargs):
            return old_value == 1 and value == 0

        if self.acquire.get() == 0:
            status = DeviceStatus(self)
            status.set_finished()
            return status
        status = SubscriptionStatus(self.acquire, check_value, event_type=self.acquire.SUB_VALUE)
        return status

    def collect(self):
        self._update_measurement_data()
        data = {"time": self._start_time, "data": {}, "timestamps": {}}
        for attr in ("edata", "data", "idata", "fdata"):
            obj = getattr(self, attr)
            if attr == "edata":
                data["data"][obj.name] = np.asarray(
                    [float(x) for x in self._measurement_data["#Ecrbk"][7 : 7 + self.count.get()]]
                )
            else:
                data["data"][obj.name] = obj.get()
            data["timestamps"][obj.name] = obj.timestamp

        return data

    def _update_measurement_data(self):
        timestamp = time.time()
        signals = {
            "signals_s1": {
                "value": self._measurement_data["CADC1"][self.count.get()],
                "timestamp": timestamp,
            },
            "signals_s2": {
                "value": self._measurement_data["CADC2"][self.count.get()],
                "timestamp": timestamp,
            },
            "signals_s3": {
                "value": self._measurement_data["CADC3"][self.count.get()],
                "timestamp": timestamp,
            },
            "signals_s4": {
                "value": self._measurement_data["CADC4"][self.count.get()],
                "timestamp": timestamp,
            },
            "signals_s5": {
                "value": self._measurement_data["CADC5"][self.count.get()],
                "timestamp": timestamp,
            },
            "signals_norm_tey": {
                "value": self._measurement_data["CADC1"][self.count.get()]
                / self._measurement_data["CADC2"][self.count.get()],
                "timestamp": timestamp,
            },
            "signals_norm_diode": {
                "value": self._measurement_data["CADC1"][self.count.get()]
                / self._measurement_data["CADC3"][self.count.get()],
                "timestamp": timestamp,
            },
        }
        msg = messages.DeviceMessage(
            signals=signals, metadata=self._device_manager.devices.otf.metadata
        )
        self._device_manager.connector.set_and_publish(
            MessageEndpoints.device_readback("signals"), msg
        )

    def describe_collect(self):
        desc = {}
        for attr in ("edata", "data", "idata", "fdata"):
            desc.update(getattr(self, attr).describe())
        return desc

    def _update_status(self, *, old_value, value, **kwargs):
        if old_value == 1 and value == 0:
            self._done_acquiring()
            return
        if old_value == 0 and value == 1:
            threading.Thread(target=self._start_acquiring, daemon=True).start()

    def _reset_data(self):
        for entry in ("edata", "data", "idata", "fdata"):
            getattr(self, entry)._reset_data()
        self.count._readback = 0
        self._data_event.clear()

    def _populate_data(self):
        self._reset_data()
        while not self._data_event.is_set():
            for entry in ("edata", "data", "idata", "fdata"):
                getattr(self, entry).append(np.random.rand())
            self.count._readback = len(self.edata.get())
            self.count._run_subs(
                sub_type="value",
                old_value=self.count._readback - 1,
                value=self.count._readback,
                timestamp=time.time(),
            )
            time.sleep(0.1)
        self._data_event.clear()

    def _start_acquiring(self):
        threading.Thread(target=self._populate_data, daemon=True).start()
        timeout_event = threading.Event()
        flag = timeout_event.wait(self.time.get())
        if not flag:
            self._data_event.set()
            self.acquire.put(0)

    def _update_data(self, value, **kwargs):
        if value == 0:
            return
        data = self.collect()
        self._run_subs(sub_type=self.SUB_FLYER, value=data)


if __name__ == "__main__":
    obj = SynXtremeOtf(name="otf")
    status = obj.time.set(4)
    status.wait()
    status = obj.kickoff()
    status.wait()
    while obj.acquire.get():
        time.sleep(0.2)
    print("done")
