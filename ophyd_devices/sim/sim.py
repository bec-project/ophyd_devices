from ophyd import Component as Cpt
from ophyd import Device
from ophyd import DynamicDeviceComponent as Dcpt

from ophyd_devices.sim.sim_positioner import SimPositioner
from ophyd_devices.sim.sim_signals import SetableSignal as SynSignal


class SynDeviceSubOPAAS(Device):
    zsub = Cpt(SimPositioner, name="zsub")


class SynDeviceOPAAS(Device):
    x = Cpt(SimPositioner, name="x")
    y = Cpt(SimPositioner, name="y")
    z = Cpt(SynDeviceSubOPAAS, name="z")


class SynDynamicComponents(Device):
    messages = Dcpt({f"message{i}": (SynSignal, None, {"name": f"msg{i}"}) for i in range(1, 6)})
