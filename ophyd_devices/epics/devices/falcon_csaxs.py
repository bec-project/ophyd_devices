import os
import time
from typing import List
from ophyd import EpicsSignal, EpicsSignalRO, EpicsSignalWithRBV, Component as Cpt, Device

from ophyd.mca import EpicsMCARecord, EpicsDXPMapping, EpicsDXPLowLevel, EpicsDXPMultiElementSystem
from ophyd.areadetector.plugins import HDF5Plugin, HDF5Plugin_V21, FilePlugin_V22

from bec_lib.core.file_utils import FileWriterMixin
from bec_lib.core import MessageEndpoints, BECMessage, RedisConnector
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

    current_pixel = Cpt(EpicsSignalRO, "CurrentPixel")


class FalconHDF5Plugins(HDF5Plugin_V21, FilePlugin_V22):
    pass


class FalconCsaxs(Device):
    """FalxonX1 with HDF5 writer"""

    dxp = Cpt(EpicsDXPFalcon, "dxp1:")
    mca = Cpt(EpicsMCARecord, "mca1")
    hdf5 = Cpt(FalconHDF5Plugins, "HDF1:")

    # Control
    stop_all = Cpt(EpicsSignal, "StopAll")
    erase_all = Cpt(EpicsSignal, "EraseAll")
    start_all = Cpt(EpicsSignal, "StartAll")
    state = Cpt(EpicsSignal, "Acquiring")
    # Preset options
    preset_mode = Cpt(EpicsSignal, "PresetMode")  # 0 No preset 1 Real time 2 Events 3 Triggers
    preset_real = Cpt(EpicsSignal, "PresetReal")
    preset_events = Cpt(EpicsSignal, "PresetEvents")
    preset_triggers = Cpt(EpicsSignal, "PresetTriggers")
    # read-only diagnostics
    triggers = Cpt(EpicsSignalRO, "MaxTriggers", lazy=True)
    events = Cpt(EpicsSignalRO, "MaxEvents", lazy=True)
    input_count_rate = Cpt(EpicsSignalRO, "MaxInputCountRate", lazy=True)
    output_count_rate = Cpt(EpicsSignalRO, "MaxOutputCountRate", lazy=True)

    # Mapping control
    collect_mode = Cpt(EpicsSignal, "CollectMode")  # 0 MCA spectra, 1 MCA mapping
    pixel_advance_mode = Cpt(EpicsSignal, "PixelAdvanceMode")
    ignore_gate = Cpt(EpicsSignal, "IgnoreGate")
    input_logic_polarity = Cpt(EpicsSignal, "InputLogicPolarity")
    auto_pixels_per_buffer = Cpt(EpicsSignal, "AutoPixelsPerBuffer")
    pixels_per_buffer = Cpt(EpicsSignal, "PixelsPerBuffer")
    pixels_per_run = Cpt(EpicsSignal, "PixelsPerRun")

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
        super().__init__(
            prefix=prefix,
            name=name,
            kind=kind,
            read_attrs=read_attrs,
            configuration_attrs=configuration_attrs,
            parent=parent,
            **kwargs,
        )
        self.device_manager = device_manager
        self.username = (
            "e21206"  # self.device_manager.producer.get(MessageEndpoints.account()).decode()
        )
        # self.username = self.device_manager.producer.get(MessageEndpoints.account()).decode()
        self.name = name
        # TODO meaningful to use FileWriterMixin
        self.service_cfg = {"base_path": f"/sls/X12SA/data/{self.username}/Data10/falcon/"}
        self.filewriter = FileWriterMixin(self.service_cfg)
        self.num_frames = 0
        self.readout = 0.003  # 3 ms
        self._value_pixel_per_buffer = 16
        self._file_template = f"%s%s_{self.name}.h5"
        # TODO localhost:6379
        self._producer = RedisConnector(["localhost:6379"]).producer()
        # Init script for falcon

        self._clean_up()
        self._init_hdf5_saving()
        self._init_mapping_mode()

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
        # TODO update service config for file path gen.. - But problem with path
        # self.username = self.device_manager.producer.get(MessageEndpoints.account()).decode()
        self.destination_path = os.path.join(self.service_cfg["base_path"])
        self.filename = f"test_{self.scan_number}"
        self._prep_mca_acquisition()

        # Filename to Redis
        path_to_file = self._file_template % (self.destination_path, self.filename)
        msg = BECMessage.FileMessage(file_path=path_to_file, done=False)
        self.producer.set_and_publish(
            MessageEndpoints.public_file(self.metadata["scanID"], self.name),
            msg.dumps(),
        )

        # TODO BEC message on where file is going to be written to

        return super().stage()

    def acquire(self) -> None:
        self.start_all.set(1)

    def unstage(self) -> List[object]:
        # Check number of acquisitions
        while not self._check_falcon_done():
            logger.info("Waiting for acquisition to finish, sleeping 0.1s ")
            time.sleep(0.1)
        # Compare expected vs measured number of pixel
        # logger.info(
        #     f'Falcon: number of measured frames from expected {self.current_pixel.read()}/{self.pixels_per_run.read()}'
        # )
        # logger.info(
        #     "Falcon write file state{self.hdf5.capture.read()}/{self.hdf5.writestatus}"
        # )
        # if not self.hdf5.write_status.read()[f'{self.name}_hdf5_write_status']['value'] :
        # state = self.hdf5.write_status.read()[f'{self.name}_hdf5']

        self._clean_up()
        msg = BECMessage.FileMessage(file_path=path_to_file, done=True, successful=state)
        self.producer.set_and_publish(
            MessageEndpoints.public_file(self.metadata["scanID"], self.name),
            msg.dumps(),
        )

        return super().unstage()

    def _clean_up(self) -> None:
        """Clean up"""
        self.hdf5.capture.set(0)
        self.stop_all.set(1)
        self.erase_all.set(1)

    def _init_hdf5_saving(self) -> None:
        """Set up hdf5 save parameters"""
        self.hdf5.enable.set(1)  # EnableCallbacks
        self.hdf5.xml_file_name.set("layout.xml")  # Points to hardcopy of HDF5 Layout xml file
        self.hdf5.lazy_open.set(1)  # Yes -> To be checked how to add FilePlugin_V21+
        self.hdf5.temp_suffix.set("temps")  # -> To be checked how to add FilePlugin_V22+

    def _init_mapping_mode(self) -> None:
        """Set up mapping mode params"""
        self.collect_mode.set(1)  # 1 MCA Mapping, 0 MCA Spectrum
        self.preset_mode.set(1)  # 1 Realtime
        self.input_logic_polarity.set(0)  # 0 Normal, 1 Inverted
        self.pixel_advance_mode.set(1)  # 0 User, 1 Gate, 2 Sync
        self.ignore_gate.set(1)  # 1 Yes
        self.auto_pixels_per_buffer.set(0)  # 0 Manual 1 Auto
        self.pixels_per_buffer.set(16)  #

    def _prep_mca_acquisition(self) -> None:
        """Prepare detector for acquisition"""
        self.collect_mode.set(1)
        self.preset_real.set(self.exposure_time)
        self.pixels_per_run.set(self.num_frames)
        self.auto_pixels_per_buffer.set(0)
        self.pixels_per_buffer.set(self._value_pixel_per_buffer)

        # HDF prep
        self.hdf5.file_path.set(self.destination_path)
        self.hdf5.file_name.set(self.filename)
        self.hdf5.file_template.set(self._file_template)
        self.hdf5.num_capture.set(self.num_frames // self._value_pixel_per_buffer + 1)
        self.hdf5.file_write_mode.set(2)
        self.hdf5.capture.set(1)

        # Start acquisition
        # Check falcon status?? self.state --> 1 for acquiring.

    def _check_falcon_done(self) -> bool:
        state = self.state.read()[f"{self.name }_state"]["value"]
        if state is [0, 1]:
            return not bool(state)
        else:
            # TODO raise error
            logger.warning("Returned in unknown state")
            return state
