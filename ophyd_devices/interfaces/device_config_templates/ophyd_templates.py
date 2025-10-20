"""
Module with templates for configs of common device classes from ophyd.

- EpicsMotor
- EpicsSignal
- EpicsSignalRO
- EpicsSignalWithRBV
"""

from pydantic import BaseModel, Field


class EpicsMotorDeviceConfigTemplate(BaseModel):
    """
    Template for the deviceConfig field for the BEC configuration if
    the deviceClass is 'ophyd.EpicsMotor'.
    """

    prefix: str = Field(..., description="EPICS IOC prefix, e.g. X25DA-ES1-MOT:")
    limits: tuple[float, float] | None = Field(None, description="Soft limits of the motor.")


class EpicsSignalDeviceConfigTemplate(BaseModel):
    """
    Template for the deviceConfig field for the BEC configuration if
    the deviceClass is 'ophyd.EpicsSignal'.
    """

    read_pv: str = Field(..., description="EPICS read PV: e.g. X25DA-ES1-MOT:GET")
    write_pv: str | None = Field(
        None, description="EPICS write PV (if different from read_pv): e.g. X25DA-ES1-MOT:SET"
    )


class EpicsSignalRODeviceConfigTemplate(BaseModel):
    """
    Template for the deviceConfig field for the BEC configuration if
    the deviceClass is 'ophyd.EpicsSignalRO'.
    """

    read_pv: str = Field(..., description="EPICS read PV: e.g. X25DA-ES1-MOT:GET")


class EpicsSignalWithRBVDeviceConfigTemplate(BaseModel):
    """
    Template for the deviceConfig field for the BEC configuration if
    the deviceClass is 'ophyd.EpicsSignalWithRBV'.
    """

    prefix: str = Field(..., description="EPICS IOC prefix, e.g. X25DA-ES1-DET:ACQUIRE")


# Dictionary mapping device groups to supported device class templates/variants.
OPHYD_DEVICE_TEMPLATES: dict[str, dict[str, dict[str, type]]] = {
    "EpicsMotor": {
        "EpicsMotor": {
            "deviceClass": "ophyd.EpicsMotor",  # "ophyd_devices.devices.EpicsMotor",
            "deviceConfig": EpicsMotorDeviceConfigTemplate,
        }
    },
    "EpicsSignal": {
        "EpicsSignal": {
            "deviceClass": "ophyd.EpicsSignal",
            "deviceConfig": EpicsSignalDeviceConfigTemplate,
        },
        "EpicsSignalRO": {
            "deviceClass": "ophyd.EpicsSignalRO",
            "deviceConfig": EpicsSignalRODeviceConfigTemplate,
        },
        "EpicsSignalWithRBV": {
            "deviceClass": "ophyd.EpicsSignalWithRBV",
            "deviceConfig": EpicsSignalWithRBVDeviceConfigTemplate,
        },
    },
    "CustomDevice": {"CustomDevice": {"deviceConfig": {}}},
}
