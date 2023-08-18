import os
from typing import List
from ophyd import EpicsSignal, EpicsSignalRO, EpicsSignalWithRBV, Component as Cpt, Device

from ophyd.mca import EpicsMCARecord, EpicsDXPMapping, EpicsDXPLowLevel, EpicsDXPMultiElementSystem
from ophyd.areadetector.plugins import HDF5Plugin, HDF5Plugin_V21, FilePlugin_V22

from bec_lib.core.file_utils import FileWriterMixin
from bec_lib.core import bec_logger

logger = bec_logger.logger


class EpicsDXPFalcon(Device):
    """All high-level DXP parameters for each channel"""

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


class FalconHDF5Plugins(HDF5Plugin_V21, FilePlugin_V22):
    pass


class FalconCsaxs(Device):
    """FalxonX1 with HDF5 writer"""

    dxp = Cpt(EpicsDXPFalcon, "dxp1:")
    mca = Cpt(EpicsMCARecord, "mca1")
    hdf5 = Cpt(FalconHDF5Plugins, "HDF1:")

    # Preset options
    stop_all = Cpt(EpicsSignal, "StopAll")
    erase_all = Cpt(EpicsSignal, "EraseAll")
    # 0 No preset 1 Real time 2 Events 3 Triggers
    preset_real = Cpt(EpicsSignal, "PresetReal")
    preset_triggers = Cpt(EpicsSignal, "PresetTriggers")
    preset_events = Cpt(EpicsSignal, "PresetEvents")
    # read-only diagnostics
    triggers = Cpt(EpicsSignalRO, "Triggers", lazy=True)
    events = Cpt(EpicsSignalRO, "Events", lazy=True)
    input_count_rate = Cpt(EpicsSignalRO, "InputCountRate", lazy=True)
    output_count_rate = Cpt(EpicsSignalRO, "OutputCountRate", lazy=True)
    # current_pixel = Cpt(EpicsSignal, "CurrentPixel")

    #     # Trace options
    # trace_data = Cpt(EpicsSignal, "TraceData")

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
        self.username = (
            "e21206"  # self.device_manager.producer.get(MessageEndpoints.account()).decode()
        )
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
        # TODO meaningful to use FileWriterMixin
        self.service_cfg = {"base_path": f"/sls/X12SA/data/{self.username}/Data10/falcon/"}
        self.filewriter = FileWriterMixin(self.service_cfg)
        self.num_frames = 0
        self.readout = 0.003  # 3 ms
        self.triggermode = 0  # 0 : internal, scan must set this if hardware triggered
        # Init script for falcon

        # self._clean_up_dxp()
        self._init_hdf5_saving()

        # self._set_up_mapping_mode()

    def stage(self) -> List[object]:
        # scan_msg = self._get_current_scan_msg()
        # self.metadata = {
        #     "scanID": scan_msg.content["scanID"],
        #     "RID": scan_msg.content["info"]["RID"],
        #     "queueID": scan_msg.content["info"]["queueID"],
        # }
        self.scan_number = 10  # scan_msg.content["info"]["scan_number"]
        self.exp_time = 0.5  # scan_msg.content["info"]["exp_time"]
        self.num_frames = 3  # scan_msg.content["info"]["num_points"]
        # TODO remove
        # self.username = self.device_manager.producer.get(MessageEndpoints.account()).decode()

        self.destination_path = os.path.join(self.service_cfg["base_path"])

        return super().stage()

    def unstage(self) -> List[object]:
        return super().unstage()

    def _clean_up_hdf5plugin(self) -> None:
        # TODO propably better monitored! similar as threshold
        self.hdf5.capture.set(0)

    def _clean_up_dxp(self) -> None:
        """Clean up"""
        self.stop_all.set(1)
        self.erase_all.set(1)

    def _acquisition_parameters(self) -> None:
        self.preset_real_time.set(self.exposure_time)

    def _init_hdf5_saving(self) -> None:
        """Set up hdf5 save parameters"""
        self.hdf5.enable.set(1)  # EnableCallbacks
        self.hdf5.xml_file_name.set("layout.xml")
        self.hdf5.lazy_open.set(1)  # Yes -> To be checked how to add FilePlugin_V21+
        self.hdf5.temp_suffix.set("temps")  # -> To be checked how to add FilePlugin_V22+

    def _set_up_mapping_mode(self) -> None:
        """Set up mapping mode params"""
        self.input_logic_polarity.set(0)
        self.preset_mode.set(1)
        self.collect_mode.set(1)
        self.pixel_advance_mode.set(1)
        self.ignore_gate.set(1)
        self.auto_pixels_per_buffer.set(0)  # 0 Manual 1 Auto
        # self.auto
        # self.ignore
