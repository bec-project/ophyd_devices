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
