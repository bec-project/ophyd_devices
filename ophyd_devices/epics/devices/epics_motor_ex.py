from ophyd import Component as Cpt, EpicsSignal, EpicsMotor


class EpicsMotorEx(EpicsMotor):
    """Extend EpicsMotor with extra configuration fields.
    motor_done_move
    motor_is_moving
    """

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
            # print out attributes that are being configured
            print("setting ", key, "=", value)
            getattr(self, key).put(value)

        # self.motor_done_move.subscribe(self._progress_update, run=False)

    # def kickoff(self) -> DeviceStatus:
    #     status = DeviceStatus(self)
    #     self.move(
    #         self._kickoff_params.get("position"),
    #         wait = False
    #     )
    #     return status

    # def _progress_update(self, value, **kwargs) -> None:
    #     self._run_subs(
    #         sub_type=self.SUB_PROGRESS,
    #         value=value ,
    #         done= 1,
    #     )
