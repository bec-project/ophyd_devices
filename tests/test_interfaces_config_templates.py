"""Module to test the ophyd device config templates interface."""

from ophyd_devices.interfaces.device_config_templates.ophyd_templates import (
    OPHYD_DEVICE_TEMPLATES,
    EpicsMotorDeviceConfigTemplate,
    EpicsSignalDeviceConfigTemplate,
    EpicsSignalRODeviceConfigTemplate,
    EpicsSignalWithRBVDeviceConfigTemplate,
)


def test_interfaces_OPHYD_DEVICE_TEMPLATES():
    """Test that the OPHYD_DEVICE_TEMPLATES dictionary is correctly defined."""
    # Group level checks
    assert "EpicsMotor" in OPHYD_DEVICE_TEMPLATES
    assert "EpicsSignal" in OPHYD_DEVICE_TEMPLATES
    assert "CustomDevice" in OPHYD_DEVICE_TEMPLATES

    # Component level checks
    assert "EpicsMotor" in OPHYD_DEVICE_TEMPLATES["EpicsMotor"]
    template_info = OPHYD_DEVICE_TEMPLATES["EpicsMotor"]["EpicsMotor"]
    assert "ophyd.EpicsMotor" == template_info.get("deviceClass", "")
    assert issubclass(template_info.get("deviceConfig", object), EpicsMotorDeviceConfigTemplate)

    assert "EpicsSignalRO" in OPHYD_DEVICE_TEMPLATES["EpicsSignal"]
    template_info = OPHYD_DEVICE_TEMPLATES["EpicsSignal"]["EpicsSignalRO"]
    assert "ophyd.EpicsSignalRO" == template_info.get("deviceClass", "")
    assert issubclass(template_info.get("deviceConfig", object), EpicsSignalRODeviceConfigTemplate)

    assert "EpicsSignalWithRBV" in OPHYD_DEVICE_TEMPLATES["EpicsSignal"]
    template_info = OPHYD_DEVICE_TEMPLATES["EpicsSignal"]["EpicsSignalWithRBV"]
    assert "ophyd.EpicsSignalWithRBV" == template_info.get("deviceClass", "")
    assert issubclass(
        template_info.get("deviceConfig", object), EpicsSignalWithRBVDeviceConfigTemplate
    )

    assert "EpicsSignal" in OPHYD_DEVICE_TEMPLATES["EpicsSignal"]
    template_info = OPHYD_DEVICE_TEMPLATES["EpicsSignal"]["EpicsSignal"]
    assert "ophyd.EpicsSignal" == template_info.get("deviceClass", "")
    assert issubclass(template_info.get("deviceConfig", object), EpicsSignalDeviceConfigTemplate)

    assert "CustomDevice" in OPHYD_DEVICE_TEMPLATES["CustomDevice"]
    template_info = OPHYD_DEVICE_TEMPLATES["CustomDevice"]["CustomDevice"]
    assert template_info.get("deviceConfig", None) == {}


def test_interfaces_templates():
    """Test the individual device config templates."""
    # pylint: disable=unsupported-assignment-operation
    # Epics Motor Template
    assert "prefix" in EpicsMotorDeviceConfigTemplate.model_fields
    assert "EPICS IOC prefix" in EpicsMotorDeviceConfigTemplate.model_fields["prefix"].description
    assert "limits" in EpicsMotorDeviceConfigTemplate.model_fields
    assert "limits" in EpicsMotorDeviceConfigTemplate.model_fields["limits"].description

    # Epics Signal Template
    assert "read_pv" in EpicsSignalDeviceConfigTemplate.model_fields
    assert "EPICS read PV" in EpicsSignalDeviceConfigTemplate.model_fields["read_pv"].description
    assert "write_pv" in EpicsSignalDeviceConfigTemplate.model_fields
    assert "EPICS write PV" in EpicsSignalDeviceConfigTemplate.model_fields["write_pv"].description

    # Epics Signal RO Template
    assert "read_pv" in EpicsSignalRODeviceConfigTemplate.model_fields
    assert "EPICS read PV" in EpicsSignalRODeviceConfigTemplate.model_fields["read_pv"].description

    # Epics Signal With RBV Template
    assert "prefix" in EpicsSignalWithRBVDeviceConfigTemplate.model_fields
    assert (
        "EPICS IOC prefix"
        in EpicsSignalWithRBVDeviceConfigTemplate.model_fields["prefix"].description
    )
