import time

from ophyd import Component as Cpt
from ophyd import Device
from ophyd import DynamicDeviceComponent as Dcpt
from ophyd import EpicsSignal
from prettytable import PrettyTable, FRAME


class OMNYSampleStorageError(Exception):
    pass


class OMNYSampleStorage(Device):
    USER_ACCESS = [
        "is_sample_slot_used",
        "is_sample_in_gripper",
        "set_sample_slot",
        "unset_sample_slot",
        "set_sample_in_gripper",
        "unset_sample_in_gripper",
        "set_sample_in_samplestage",
        "unset_sample_in_samplestage",
        "get_sample_name_in_samplestage",
        "get_sample_name",
        "is_sample_in_samplestage",
        "set_shuttle_slot",
        "unset_shuttle_slot",
        "get_shuttle_name_slot",
        "is_shuttle_slot_used",
        "show_all",
    ]
    SUB_VALUE = "value"
    _default_sub = SUB_VALUE

    sample_shuttle_A_placed = {
        f"sample{i}": (EpicsSignal, f"XOMNY-SAMPLE_DB_shuttle_A:{i}", {}) for i in range(1, 7)
    }
    sample_shuttle_A_placed = Dcpt(sample_shuttle_A_placed)

    sample_shuttle_B_placed = {
        f"sample{i}": (EpicsSignal, f"XOMNY-SAMPLE_DB_shuttle_B:{i}", {}) for i in range(1, 7)
    }
    sample_shuttle_B_placed = Dcpt(sample_shuttle_B_placed)

    sample_shuttle_C_placed = {
        f"sample{i}": (EpicsSignal, f"XOMNY-SAMPLE_DB_shuttle_C:{i}", {}) for i in range(1, 7)
    }
    sample_shuttle_C_placed = Dcpt(sample_shuttle_C_placed)

    sample_shuttle_C_placed = {
        f"sample{i}": (EpicsSignal, f"XOMNY-SAMPLE_DB_shuttle_C:{i}", {}) for i in range(1, 7)
    }
    sample_shuttle_C_placed = Dcpt(sample_shuttle_C_placed)

    parking_placed = {
        f"parking{i}": (EpicsSignal, f"XOMNY-SAMPLE_DB_parking:{i}", {}) for i in range(1, 7)
    }
    parking_placed = Dcpt(parking_placed)

    sample_placed = {
        f"parking{i}": (EpicsSignal, f"XOMNY-SAMPLE_DB_omny:{i}", {})
        for i in [10, 11, 12, 13, 14, 32, 33, 34, 100, 101]
    }
    sample_placed = Dcpt(sample_placed)

    sample_shuttle_A_names = {
        f"sample{i}": (EpicsSignal, f"XOMNY-SAMPLE_DB_shuttle_A:{i}.DESC", {"string": True})
        for i in range(1, 7)
    }
    sample_shuttle_A_names = Dcpt(sample_shuttle_A_names)

    sample_shuttle_B_names = {
        f"sample{i}": (EpicsSignal, f"XOMNY-SAMPLE_DB_shuttle_B:{i}.DESC", {"string": True})
        for i in range(1, 7)
    }
    sample_shuttle_B_names = Dcpt(sample_shuttle_B_names)

    sample_shuttle_C_names = {
        f"sample{i}": (EpicsSignal, f"XOMNY-SAMPLE_DB_shuttle_C:{i}.DESC", {"string": True})
        for i in range(1, 7)
    }
    sample_shuttle_C_names = Dcpt(sample_shuttle_C_names)

    parking_names = {
        f"parking{i}": (EpicsSignal, f"XOMNY-SAMPLE_DB_parking:{i}.DESC", {"string": True})
        for i in range(1, 7)
    }
    parking_names = Dcpt(parking_names)

    sample_names = {
        f"sample{i}": (EpicsSignal, f"XOMNY-SAMPLE_DB_omny:{i}.DESC", {"string": True})
        for i in [10, 11, 12, 13, 14, 32, 33, 34, 100, 101]
    }
    sample_names = Dcpt(sample_names)

    sample_in_gripper = Cpt(
        EpicsSignal, name="sample_in_gripper", read_pv="XOMNY-SAMPLE_DB_omny:110.VAL"
    )
    sample_in_gripper_name = Cpt(
        EpicsSignal,
        name="sample_in_gripper_name",
        read_pv="XOMNY-SAMPLE_DB_omny:110.DESC",
        string=True,
    )

    sample_in_samplestage = Cpt(
        EpicsSignal, name="sample_in_samplestage", read_pv="XOMNY-SAMPLE_DB_omny:0.VAL"
    )
    sample_in_samplestage_name = Cpt(
        EpicsSignal,
        name="sample_in_samplestage_name",
        read_pv="XOMNY-SAMPLE_DB_omny:0.DESC",
        string=True,
    )

    def __init__(self, prefix="", *, name, **kwargs):
        super().__init__(prefix, name=name, **kwargs)
        self.sample_shuttle_A_placed.sample1.subscribe(self._emit_value)

    def _emit_value(self, **kwargs):
        timestamp = kwargs.pop("timestamp", time.time())
        self.wait_for_connection()
        self._run_subs(sub_type=self.SUB_VALUE, timestamp=timestamp, obj=self)

    def set_sample_slot(self, container: str, slot_nr: int, name: str) -> bool:
        if slot_nr > 20:
            raise OMNYSampleStorageError(f"Invalid slot number {slot_nr}.")

        if container == "A":
            getattr(self.sample_shuttle_A_placed, f"sample{slot_nr}").set(1)
            getattr(self.sample_shuttle_A_names, f"sample{slot_nr}").set(name)
        elif container == "B":
            getattr(self.sample_shuttle_B_placed, f"sample{slot_nr}").set(1)
            getattr(self.sample_shuttle_B_names, f"sample{slot_nr}").set(name)
        elif container == "C":
            getattr(self.sample_shuttle_C_placed, f"sample{slot_nr}").set(1)
            getattr(self.sample_shuttle_C_names, f"sample{slot_nr}").set(name)

    def unset_sample_slot(self, shuttle: str, slot_nr: int) -> bool:
        if slot_nr > 20:
            raise OMNYSampleStorageError(f"Invalid slot number {slot_nr}.")

        if shuttle == "A":
            getattr(self.sample_shuttle_A_placed, f"sample{slot_nr}").set(0)
            getattr(self.sample_shuttle_A_names, f"sample{slot_nr}").set("-")
        if shuttle == "B":
            getattr(self.sample_shuttle_B_placed, f"sample{slot_nr}").set(0)
            getattr(self.sample_shuttle_B_names, f"sample{slot_nr}").set("-")
        if shuttle == "C":
            getattr(self.sample_shuttle_C_placed, f"sample{slot_nr}").set(0)
            getattr(self.sample_shuttle_C_names, f"sample{slot_nr}").set("-")

    def set_shuttle_slot(self, container: str, slot_nr: int) -> bool:
        if slot_nr > 6:
            raise OMNYSampleStorageError(f"Invalid slot number {slot_nr}.")
        getattr(self.parking_placed, f"parking{slot_nr}").set(1)
        getattr(self.parking_names, f"parking{slot_nr}").set(container)

    def unset_shuttle_slot(self, slot_nr: int) -> bool:
        if slot_nr > 6:
            raise OMNYSampleStorageError(f"Invalid slot number {slot_nr}.")
        getattr(self.parking_placed, f"parking{slot_nr}").set(0)
        getattr(self.parking_names, f"parking{slot_nr}").set("none")

    def set_sample_in_gripper(self, name: str) -> bool:
        self.sample_in_gripper.set(1)
        self.sample_in_gripper_name.set(name)

    def unset_sample_in_gripper(self) -> bool:
        self.sample_in_gripper.set(0)
        self.sample_in_gripper_name.set("-")

    def set_sample_in_samplestage(self, name: str) -> bool:
        self.sample_in_samplestage.set(1)
        self.sample_in_samplestage_name.set(name)

    def unset_sample_in_samplestage(self) -> bool:
        self.sample_in_samplestage.set(0)
        self.sample_in_samplestage_name.set("-")

    def is_sample_slot_used(self, container, slot_nr: int) -> bool:
        if container == "A":
            val = getattr(self.sample_shuttle_A_placed, f"sample{slot_nr}").get()
        if container == "B":
            val = getattr(self.sample_shuttle_B_placed, f"sample{slot_nr}").get()
        if container == "C":
            val = getattr(self.sample_shuttle_C_placed, f"sample{slot_nr}").get()
        elif container == "O":
            val = getattr(self.sample_placed, f"sample{slot_nr}").get()
        return bool(val)

    def is_shuttle_slot_used(self, slot_nr: int) -> bool:
        val = getattr(self.parking_placed, f"parking{slot_nr}").get()
        return bool(val)

    def is_sample_in_gripper(self) -> bool:
        val = self.sample_in_gripper.get()
        return bool(val)

    def is_sample_in_samplestage(self) -> bool:
        val = self.sample_in_samplestage.get()
        return bool(val)

    def get_sample_name(self, container, slot_nr) -> str:
        if container == "A":
            val = getattr(self.sample_shuttle_A_names, f"sample{slot_nr}").get()
        elif container == "B":
            val = getattr(self.sample_shuttle_B_names, f"sample{slot_nr}").get()
        elif container == "C":
            val = getattr(self.sample_shuttle_C_names, f"sample{slot_nr}").get()
        elif container == "O":
            val = getattr(self.sample_names, f"sample{slot_nr}").get()
        else:
            val = "unknown container"
        return str(val)

    def get_shuttle_name_slot(self, slot_nr: int) -> str:
        val = getattr(self.parking_names, f"parking{slot_nr}").get()
        return str(val)

    def get_sample_name_in_gripper(self) -> str:
        val = self.sample_in_gripper_name.get()
        return str(val)

    def get_sample_name_in_samplestage(self) -> str:
        val = self.sample_in_samplestage_name.get()
        return str(val)

    def show_all(self):
        t = PrettyTable()
        for ch in ["A", "B", "C"]:
            t.clear()
            t.title = "Shuttle " + ch
            field_names = [""]
            for ax in [1, 3, 5]:
                row = []
                row.extend([self.get_sample_name(ch, ax)])
                row.extend(str(ax))
                row.extend(str(ax + 1))
                row.extend([self.get_sample_name(ch, ax + 1)])
                t.add_row(row)
            t.header = False
            t.vrules = FRAME
            print(t)

        if self.is_sample_in_samplestage():
            print(f"\n\n  Sample stage:   {self.get_sample_name_in_samplestage()}")
        else:
            print(f"\n\n  Sample stage:   no sample")

        if self.is_sample_in_gripper():
            print(f"\n  Gripper:        {self.get_sample_name_in_gripper()}\n")
        else:
            print(f"\n  Gripper:        no sample\n")

        t.clear()
        t.title = "Fixed positions in OMNY"
        for i in [10, 11, 12, 13, 14, 32, 33, 34, 100, 101]:
            row = []
            row.extend([f"Position {i:3d}"])
            if self.is_sample_slot_used("O", i):
                row.extend(self.get_sample_name("O", i))
            else:
                row.extend(["free"])
            t.add_row(row)
        print(t)
