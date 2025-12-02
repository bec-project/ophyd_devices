# """Module extending EpicsMotor for VME based User motors with extra configuration fields."""

# from ophyd import Component as Cpt
# from ophyd import EpicsSignal

# # from ophyd_devices.devices.psi_motor import EpicsUserMotors


# class EpicsMotorEx(EpicsUserMotors):
#     """
#     EpicsMotor that extends a VME based user motor with additional configuration signals,
#     motor_resolution, base_velocity and backlash_distance.
#     """

#     # configuration
#     motor_resolution = Cpt(EpicsSignal, ".MRES", kind="config", auto_monitor=True)
#     base_velocity = Cpt(EpicsSignal, ".VBAS", kind="config", auto_monitor=True)
#     backlash_distance = Cpt(EpicsSignal, ".BDST", kind="config", auto_monitor=True)
