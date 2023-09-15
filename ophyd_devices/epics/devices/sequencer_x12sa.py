from ophyd import Component as Cpt, EpicsSignal, EpicsSignalRO, Device


class SequencerX12SA(Device):
    """Sequencer for flyscans with epics motor controller and owis stages"""

    desired_output_link_1 = Cpt(Signal, "DOL1")
    desired_output_value_1 = Cpt(EpicsSignal, "DO1")
    output_link_1 = Cpt(EpicsSignal, "LNK1")
    delay_time_1 = Cpt(EpicsSignal, "DLY1")
    desired_output_link_2 = Cpt(EpicsSignal, "DOL2")
    desired_output_value_2 = Cpt(EpicsSignal, "DO2")
    output_link_2 = Cpt(EpicsSignal, "LNK2")
    delay_time_2 = Cpt(EpicsSignal, "DLY2")

    select_mechanism = Cpt(EpicsSignal, "SELM", string=True)
    link_selection = Cpt(EpicsSignal, "SELN")
    process = Cpt(EpicsSignal, "PROC", string=True)

    status = Cpt(EpicsSignalRO, "STAT", string=True)
    processing_active = Cpt(EpicsSignalRO, "PACT")

    # def __init__(
    #     self,
    #     prefix="",
    #     *,
    #     name,
    #     kind=None,
    #     read_attrs=None,
    #     configuration_attrs=None,
    #     parent=None,
    #     **kwargs
    # ):
    # # get configuration attributes from kwargs and then remove them
    # attrs = {}
    # for key, value in kwargs.items():
    #     if hasattr(EpicsMotorEx, key) and isinstance(getattr(EpicsMotorEx, key), Cpt):
    #         attrs[key] = value
    # for key in attrs:
    #     kwargs.pop(key)

    # super().__init__(
    #     prefix,
    #     name=name,
    #     kind=kind,
    #     read_attrs=read_attrs,
    #     configuration_attrs=configuration_attrs,
    #     parent=parent,
    #     **kwargs
    # )

    # # set configuration attributes
    # for key, value in attrs.items():
    #     # print out attributes that are being configured
    #     print("setting ", key, "=", value)
    #     getattr(self, key).put(value)
