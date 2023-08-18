from ophyd import EpicsSignal, EpicsSignalRO, EpicsSignalWithRBV, Component as Cpt, Device

from ophyd.mca import EpicsMCARecord, EpicsDXPMapping, EpicsDXPLowLevel, EpicsDXPMultiElementSystem
from ophyd.areadetector.plugins import HDF5Plugin


class EpicsDXPFalcon(Device):
    """All high-level DXP parameters for each channel"""

    # Preset options
    preset_mode = Cpt(EpicsSignalWithRBV, "PresetMode", string=True)
    preset_real = Cpt(EpicsSignalWithRBV, "PresetReal")
    preset_triggers = Cpt(EpicsSignalWithRBV, "PresetTriggers")
    preset_events = Cpt(EpicsSignalWithRBV, "PresetEvents")

    elapsed_live_time = Cpt(EpicsSignal, "ElapsedLiveTime")
    elapsed_real_time = Cpt(EpicsSignal, "ElapsedRealTime")
    elapsed_trigger_live_time = Cpt(EpicsSignal, "ElapsedTriggerLiveTime")

    # Energy Filter PVs
    energy_threshold = Cpt(EpicsSignalWithRBV, "DetectionThreshold")
    min_pulse_separation = Cpt(EpicsSignalWithRBV, "MinPulsePairSeparation")
    detection_filter = Cpt(EpicsSignalWithRBV, "DetectionFilter", string=True)
    scale_factor = Cpt(EpicsSignalWithRBV, "ScaleFactor")
    risetime_optimisation = Cpt(EpicsSignalWithRBV, "RisetimeOptimization")

    # Misc PVs
    detector_polarity = Cpt(EpicsSignalWithRBV, "DetectorPolarity")
    decay_time = Cpt(EpicsSignalWithRBV, "DecayTime")

    # read-only diagnostics
    triggers = Cpt(EpicsSignalRO, "Triggers", lazy=True)
    events = Cpt(EpicsSignalRO, "Events", lazy=True)
    input_count_rate = Cpt(EpicsSignalRO, "InputCountRate", lazy=True)
    output_count_rate = Cpt(EpicsSignalRO, "OutputCountRate", lazy=True)
    current_pixel = Cpt(EpicsSignal, "CurrentPixel")

    # Trace options
    trace_data = Cpt(EpicsSignal, "TraceData")


class FalconDxp(EpicsDXPFalcon, EpicsDXPLowLevel):
    pass


class FalconCsaxs(EpicsDXPMultiElementSystem, EpicsDXPMapping):
    """FalxonX1 with HDF5 writer"""

    dxp = Cpt(FalconDxp, "dxp1:")
    mca = Cpt(EpicsMCARecord, "mca1")
    hdf5 = Cpt(HDF5Plugin, "HDF1:")

    def __init__(
        self,
        prefix="",
        *,
        name,
        kind=None,
        read_attrs=None,
        configuration_attrs=None,
        parent=None,
        device_manager=None,
        **kwargs,
    ):
        self.device_manager = device_manager
        self.username = "e21206"  # TODO get from config
        # self.username = self.device_manager.producer.get(MessageEndpoints.account()).decode()
        super().__init__(
            prefix=prefix,
            name=name,
            kind=kind,
            read_attrs=read_attrs,
            configuration_attrs=configuration_attrs,
            parent=parent,
            **kwargs,
        )
        # TODO how to get base_path
        self.service_cfg = {"base_path": f"/sls/X12SA/data/{self.username}/Data10/falcon/"}
        self.filewriter = FileWriterMixin(self.service_cfg)
        self.num_frames = 0
        self.readout = 0.003  # 3 ms
        self.triggermode = 0  # 0 : internal, scan must set this if hardware triggered

    def stage(self) -> List[object]:
        return super().stage()

    def unstage(self) -> List[object]:
        return super().unstage()
