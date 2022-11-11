from ophyd import Component as Cpt
from ophyd import Device, EpicsSignal


class Xeye(Device):
    save_frame = Cpt(EpicsSignal, "XOMNY-XEYE-SAVEFRAME:0")
    acquisition_done = Cpt(EpicsSignal, "XOMNY-XEYE-ACQDONE:0")
    acquisition = Cpt(EpicsSignal, "XOMNY-XEYE-ACQ:0")
    x_width = Cpt(EpicsSignal, "XOMNY-XEYE-XWIDTH_X:0")
