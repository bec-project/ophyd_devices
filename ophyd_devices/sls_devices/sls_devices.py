from ophyd import Component as Cpt
from ophyd import Device, EpicsSignalRO


class SLSOperatorMessages(Device):
    message1 = Cpt(EpicsSignalRO, f"ACOAU-ACCU:OP-MSG1", auto_monitor=True)
    message_date1 = Cpt(EpicsSignalRO, f"ACOAU-ACCU:OP-DATE1", auto_monitor=True)
    message2 = Cpt(EpicsSignalRO, f"ACOAU-ACCU:OP-MSG2", auto_monitor=True)
    message_date2 = Cpt(EpicsSignalRO, f"ACOAU-ACCU:OP-DATE2", auto_monitor=True)
    message3 = Cpt(EpicsSignalRO, f"ACOAU-ACCU:OP-MSG3", auto_monitor=True)
    message_date3 = Cpt(EpicsSignalRO, f"ACOAU-ACCU:OP-DATE3", auto_monitor=True)
    message4 = Cpt(EpicsSignalRO, f"ACOAU-ACCU:OP-MSG4", auto_monitor=True)
    message_date4 = Cpt(EpicsSignalRO, f"ACOAU-ACCU:OP-DATE4", auto_monitor=True)
    message5 = Cpt(EpicsSignalRO, f"ACOAU-ACCU:OP-MSG5", auto_monitor=True)
    message_date5 = Cpt(EpicsSignalRO, f"ACOAU-ACCU:OP-DATE5", auto_monitor=True)


# class SLSOperatorMessages(Device):
#     pass

# for i in range(5):
#     setattr(SLSOperatorMessages, f"message{i}", Cpt(EpicsSignalRO, f"ACOAU-ACCU:OP-MSG{i}", auto_monitor=True))
#     setattr(SLSOperatorMessages, f"message_date{i}", Cpt(EpicsSignalRO, f"ACOAU-ACCU:OP-DATE{i}", auto_monitor=True))


class BeamlineInfo(Device):
    eh_t02_avg_temperature = Cpt(EpicsSignalRO, "ILUUL-02AV:TEMP", auto_monitor=True)
    eh_t02_temperature_t0204_axis_16 = Cpt(
        EpicsSignalRO, "ILUUL-0200-EB104:TEMP", auto_monitor=True
    )
    eh_t02_temperature_t0205_axis_18 = Cpt(
        EpicsSignalRO, "ILUUL-0200-EB105:TEMP", auto_monitor=True
    )
    operation = Cpt(EpicsSignalRO, "ACOAU-ACCU:OP-MODE.VAL", auto_monitor=True)
    injection_mode = Cpt(EpicsSignalRO, "ALIRF-GUN:INJ-MODE", auto_monitor=True)
    current_threshold = Cpt(EpicsSignalRO, "ALIRF-GUN:CUR-LOWLIM", auto_monitor=True)
    current_deadband = Cpt(EpicsSignalRO, "ALIRF-GUN:CUR-DBAND", auto_monitor=True)
    filling_pattern = Cpt(EpicsSignalRO, "ACORF-FILL:PAT-SELECT", auto_monitor=True)
    filling_life_time = Cpt(EpicsSignalRO, "ARIDI-PCT:TAU-HOUR", auto_monitor=True)
    orbit_feedback_mode = Cpt(EpicsSignalRO, "ARIDI-BPM:OFB-MODE", auto_monitor=True)
    fast_orbit_feedback = Cpt(EpicsSignalRO, "ARIDI-BPM:FOFBSTATUS-G", auto_monitor=True)
    ring_current = Cpt(EpicsSignalRO, "ARIDI-PCT:CURRENT", auto_monitor=True)
