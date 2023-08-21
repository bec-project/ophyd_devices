from ophyd import EpicsSignal, EpicsSignalRO, Component as Cpt, Device
from ophyd.mca import EpicsMCARecord, EpicsDXPMapping, EpicsDXPLowLevel, EpicsDXPMultiElementSystem
from ophyd.scaler import ScalerCH


class SIS38XX(Device):
    """SIS38XX control"""

    # Acquisition
    erase_all = Cpt(EpicsSignal, "EraseAll")
    erase_start = Cpt(EpicsSignal, "EraseStart", trigger_value=1)
    start_all = Cpt(EpicsSignal, "StartAll")
    stop_all = Cpt(EpicsSignal, "StopAll")

    acquiring = Cpt(EpicsSignal, "Acquiring")

    preset_real = Cpt(EpicsSignal, "PresetReal")
    elapsed_real = Cpt(EpicsSignal, "ElapsedReal")

    read_all = Cpt(EpicsSignal, "ReadAll")
    num_use_all = Cpt(EpicsSignal, "NuseAll")
    current_channel = Cpt(EpicsSignal, "CurrentChannel")
    dwell = Cpt(EpicsSignal, "Dwell")
    channel_advance = Cpt(EpicsSignal, "ChannelAdvance")
    count_on_start = Cpt(EpicsSignal, "CountOnStart")
    software_channel_advance = Cpt(EpicsSignal, "SoftwareChannelAdvance")
    channel1_source = Cpt(EpicsSignal, "Channel1Source")
    prescale = Cpt(EpicsSignal, "Prescale")
    enable_client_wait = Cpt(EpicsSignal, "EnableClientWait")
    client_wait = Cpt(EpicsSignal, "ClientWait")
    acquire_mode = Cpt(EpicsSignal, "AcquireMode")
    mux_output = Cpt(EpicsSignal, "MUXOutput")
    user_led = Cpt(EpicsSignal, "UserLED")
    input_mode = Cpt(EpicsSignal, "InputMode")
    input_polarity = Cpt(EpicsSignal, "InputPolarity")
    output_mode = Cpt(EpicsSignal, "OutputMode")
    output_polarity = Cpt(EpicsSignal, "OutputPolarity")
    model = Cpt(EpicsSignalRO, "Model", string=True)
    firmware = Cpt(EpicsSignalRO, "Firmware")
    max_channels = Cpt(EpicsSignalRO, "MaxChannels")


class SIS3820(SIS38XX):
    scaler = Cpt(ScalerCH, "scaler1")

    mca1 = Cpt(EpicsMCARecord, "mca1")
    mca2 = Cpt(EpicsMCARecord, "mca2")
    mca3 = Cpt(EpicsMCARecord, "mca3")
    mca4 = Cpt(EpicsMCARecord, "mca4")
    mca5 = Cpt(EpicsMCARecord, "mca5")
    # mca6 = Cpt(EpicsMCARecord, "mca6")
    # mca7 = Cpt(EpicsMCARecord, "mca7")
    # mca8 = Cpt(EpicsMCARecord, "mca8")
    # mca9 = Cpt(EpicsMCARecord, "mca9")
    # mca10 = Cpt(EpicsMCARecord, "mca10")
    # mca11 = Cpt(EpicsMCARecord, "mca11")
    # mca12 = Cpt(EpicsMCARecord, "mca12")
    # mca13 = Cpt(EpicsMCARecord, "mca13")
    # mca14 = Cpt(EpicsMCARecord, "mca14")
    # mca15 = Cpt(EpicsMCARecord, "mca15")
    # mca16 = Cpt(EpicsMCARecord, "mca16")
    # mca17 = Cpt(EpicsMCARecord, "mca17")
    # mca18 = Cpt(EpicsMCARecord, "mca18")
    # mca19 = Cpt(EpicsMCARecord, "mca19")
    # mca20 = Cpt(EpicsMCARecord, "mca20")
    # mca21 = Cpt(EpicsMCARecord, "mca21")
    # mca22 = Cpt(EpicsMCARecord, "mca22")
    # mca23 = Cpt(EpicsMCARecord, "mca23")
    # mca24 = Cpt(EpicsMCARecord, "mca24")
    # mca25 = Cpt(EpicsMCARecord, "mca25")
    # mca26 = Cpt(EpicsMCARecord, "mca26")
    # mca27 = Cpt(EpicsMCARecord, "mca27")
    # mca28 = Cpt(EpicsMCARecord, "mca28")
    # mca29 = Cpt(EpicsMCARecord, "mca29")
    # mca30 = Cpt(EpicsMCARecord, "mca30")
    # mca31 = Cpt(EpicsMCARecord, "mca31")
    # mca32 = Cpt(EpicsMCARecord, "mca32")
