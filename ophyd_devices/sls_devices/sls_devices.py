from ophyd import Component as Cpt, DynamicDeviceComponent as Dcpt
from ophyd import Device, EpicsSignalRO


class SLSOperatorMessages(Device):
    messages_info = {
        f"message{i}": (EpicsSignalRO, f"ACOAU-ACCU:OP-MSG{i}", {}) for i in range(1, 6)
    }
    messages = Dcpt(messages_info)
    date_info = {f"message{i}": (EpicsSignalRO, f"ACOAU-ACCU:OP-DATE{i}", {}) for i in range(1, 6)}
    date = Dcpt(date_info)


class SLSInfo(Device):
    # eh_t02_avg_temperature = Cpt(EpicsSignalRO, "ILUUL-02AV:TEMP", auto_monitor=True)
    # eh_t02_temperature_t0204_axis_16 = Cpt(
    #     EpicsSignalRO, "ILUUL-0200-EB104:TEMP", auto_monitor=True
    # )
    # eh_t02_temperature_t0205_axis_18 = Cpt(
    #     EpicsSignalRO, "ILUUL-0200-EB105:TEMP", auto_monitor=True
    # )
    operation = Cpt(EpicsSignalRO, "ACOAU-ACCU:OP-MODE", auto_monitor=True, string=True)
    injection_mode = Cpt(EpicsSignalRO, "ALIRF-GUN:INJ-MODE", auto_monitor=True, string=True)
    current_threshold = Cpt(EpicsSignalRO, "ALIRF-GUN:CUR-LOWLIM", auto_monitor=True)
    current_deadband = Cpt(EpicsSignalRO, "ALIRF-GUN:CUR-DBAND", auto_monitor=True)
    filling_pattern = Cpt(EpicsSignalRO, "ACORF-FILL:PAT-SELECT", auto_monitor=True, string=True)
    filling_life_time = Cpt(EpicsSignalRO, "ARIDI-PCT:TAU-HOUR", auto_monitor=True)
    orbit_feedback_mode = Cpt(EpicsSignalRO, "ARIDI-BPM:OFB-MODE", auto_monitor=True, string=True)
    fast_orbit_feedback = Cpt(
        EpicsSignalRO, "ARIDI-BPM:FOFBSTATUS-G", auto_monitor=True, string=True
    )
    ring_current = Cpt(EpicsSignalRO, "ARIDI-PCT:CURRENT", auto_monitor=True)
    machine_status = Cpt(EpicsSignalRO, "ACOAU-ACCU:OP-MODE", auto_monitor=True, string=True)
    crane_usage = Cpt(
        EpicsSignalRO, "IBWKR-0101-QH10003:D01_H_D-WA", auto_monitor=True, string=True
    )
