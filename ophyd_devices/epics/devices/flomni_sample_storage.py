import time

from ophyd import Component as Cpt
from ophyd import Device
from ophyd import DynamicDeviceComponent as Dcpt
from ophyd import EpicsSignal


class FlomniSampleStorageError(Exception):
    pass


class FlomniSampleStorage(Device):
    USER_ACCESS = [
        "is_sample_slot_used",
        "is_sample_in_gripper",
        "set_sample_slot",
        "unset_sample_slot",
        "set_sample_in_gripper",
        "unset_sample_in_gripper",
    ]
    SUB_VALUE = "value"
    _default_sub = SUB_VALUE
    sample_placed = {
        f"sample{i}": (EpicsSignal, f"XOMNY-SAMPLE_DB_flomni{i}:GET", {}) for i in range(21)
    }
    sample_placed = Dcpt(sample_placed)

    sample_names = {
        f"sample{i}": (EpicsSignal, f"XOMNY-SAMPLE_DB_flomni{i}:GET.DESC", {"string": True})
        for i in range(21)
    }
    sample_names = Dcpt(sample_names)

    sample_in_gripper = Cpt(
        EpicsSignal, name="sample_in_gripper", read_pv="XOMNY-SAMPLE_DB_flomni100:GET"
    )
    sample_in_gripper_name = Cpt(
        EpicsSignal,
        name="sample_in_gripper_name",
        read_pv="XOMNY-SAMPLE_DB_flomni100:GET.DESC",
        string=True,
    )

    def __init__(self, prefix="", *, name, **kwargs):
        super().__init__(prefix, name=name, **kwargs)
        self.sample_placed.sample1.subscribe(self._emit_value)

    def _emit_value(self, **kwargs):
        timestamp = kwargs.pop("timestamp", time.time())
        self.wait_for_connection()
        self._run_subs(sub_type=self.SUB_VALUE, timestamp=timestamp, obj=self)

    def set_sample_slot(self, slot_nr: int, name: str) -> bool:
        if slot_nr > 20:
            raise FlomniSampleStorageError(f"Invalid slot number {slot_nr}.")

        getattr(self.sample_placed, f"sample{slot_nr}").set(1)
        getattr(self.sample_names, f"sample{slot_nr}").set(name)

    def unset_sample_slot(self, slot_nr: int) -> bool:
        if slot_nr > 20:
            raise FlomniSampleStorageError(f"Invalid slot number {slot_nr}.")

        getattr(self.sample_placed, f"sample{slot_nr}").set(0)
        getattr(self.sample_names, f"sample{slot_nr}").set("-")

    def set_sample_in_gripper(self, name: str) -> bool:
        self.sample_in_gripper.set(1)
        self.sample_in_gripper_name.set(name)

    def unset_sample_in_gripper(self) -> bool:
        self.sample_in_gripper.set(0)
        self.sample_in_gripper_name.set("-")

    def is_sample_slot_used(self, slot_nr: int) -> bool:
        val = getattr(self.sample_placed, f"sample{slot_nr}").get()
        return bool(val)

    def is_sample_in_gripper(self) -> bool:
        val = self.sample_in_gripper.get()
        return bool(val)
