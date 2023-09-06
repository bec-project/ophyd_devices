from ophyd import Component as Cpt, EpicsSignal, EpicsMotor


class EpicsMotorEx(EpicsMotor):
    """Extend EpicsMotor with extra configuration fields."""

    # configuration
    motor_resolution = Cpt(EpicsSignal, ".MRES", kind="config", auto_monitor=True)
    base_velocity = Cpt(EpicsSignal, ".VBAS", kind="config", auto_monitor=True)
    backlash_distance = Cpt(EpicsSignal, ".BDST", kind="config", auto_monitor=True)

    def __init__(
        self,
        prefix="",
        *,
        name,
        kind=None,
        read_attrs=None,
        configuration_attrs=None,
        parent=None,
        **kwargs
    ):
        # get configuration attributes from kwargs and then remove them
        attrs = {}
        for key, value in kwargs.items():
            if hasattr(EpicsMotorEx, key) and isinstance(getattr(EpicsMotorEx, key), Cpt):
                attrs[key] = value
        for key in attrs:
            kwargs.pop(key)

        super().__init__(
            prefix,
            name=name,
            kind=kind,
            read_attrs=read_attrs,
            configuration_attrs=configuration_attrs,
            parent=parent,
            **kwargs
        )

        # set configuration attributes
        for key, value in attrs.items():
            print("setting ", key, "=", value)
            getattr(self, key).put(value)
