import enum
import os
import time

from typing import List

from ophyd import EpicsSignal, EpicsSignalRO, EpicsSignalWithRBV, Component as Cpt, Device
from ophyd.mca import EpicsMCARecord

from bec_lib.core.file_utils import FileWriterMixin
from bec_lib.core import MessageEndpoints, BECMessage
from bec_lib.core import bec_logger

from ophyd_devices.epics.devices.bec_scaninfo_mixin import BecScaninfoMixin
from ophyd_devices.utils import bec_utils

logger = bec_logger.logger


class FalconError(Exception):
    '''Base class for exceptions in this module.'''
    pass


class FalconTimeoutError(Exception):
    '''Raised when the Falcon does not respond in time during unstage.'''
    pass


class DetectorState(int, enum.Enum):
    """Detector states for Falcon detector"""
    DONE = 0
    ACQUIRING = 1


class EpicsDXPFalcon(Device):
    """DXP parameters for Falcon detector

    Base class to map EPICS PVs from DXP parameters to ophyd signals.
    """

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


class FalconHDF5Plugins(Device):
    """HDF5 parameters for Falcon detector
    
    Base class to map EPICS PVs from HDF5 Plugin to ophyd signals.
    """
    capture = Cpt(EpicsSignalWithRBV, "Capture")
    enable = Cpt(EpicsSignalWithRBV, "EnableCallbacks", string=True, kind="config")
    xml_file_name = Cpt(EpicsSignalWithRBV, "XMLFileName", string=True, kind="config")
    lazy_open = Cpt(EpicsSignalWithRBV, "LazyOpen", string=True, doc="0='No' 1='Yes'")
    temp_suffix = Cpt(EpicsSignalWithRBV, "TempSuffix", string=True)
    file_path = Cpt(EpicsSignalWithRBV, "FilePath", string=True, kind="config")
    file_name = Cpt(EpicsSignalWithRBV, "FileName", string=True, kind="config")
    file_template = Cpt(EpicsSignalWithRBV, "FileTemplate", string=True, kind="config")
    num_capture = Cpt(EpicsSignalWithRBV, "NumCapture", kind="config")
    file_write_mode = Cpt(EpicsSignalWithRBV, "FileWriteMode", kind="config")
    queue_size = Cpt(EpicsSignalWithRBV, "QueueSize", kind="config")
    array_counter = Cpt(EpicsSignalWithRBV, "ArrayCounter", kind="config")


class FalconCsaxs(Device):
    """Falcon Sitoro detector for CSAXS

    Parent class: Device
    Device classes: EpicsDXPFalcon dxp1:, EpicsMCARecord mca1, FalconHDF5Plugins HDF1:

    Attributes:
        name str: 'falcon'
        prefix (str): PV prefix ("X12SA-SITORO:)

    """

    # Specify which functions are revealed to the user in BEC client
    USER_ACCESS = [
        "describe",
    ]

    dxp = Cpt(EpicsDXPFalcon, "dxp1:")
    mca = Cpt(EpicsMCARecord, "mca1")
    hdf5 = Cpt(FalconHDF5Plugins, "HDF1:")

    # specify Epics PVs for Falcon
    # TODO consider moving this outside of this class! 
    stop_all = Cpt(EpicsSignal, "StopAll")
    erase_all = Cpt(EpicsSignal, "EraseAll")
    start_all = Cpt(EpicsSignal, "StartAll")
    state = Cpt(EpicsSignal, "Acquiring")
    preset_mode = Cpt(EpicsSignal, "PresetMode")  # 0 No preset 1 Real time 2 Events 3 Triggers
    preset_real = Cpt(EpicsSignal, "PresetReal")
    preset_events = Cpt(EpicsSignal, "PresetEvents")
    preset_triggers = Cpt(EpicsSignal, "PresetTriggers")
    triggers = Cpt(EpicsSignalRO, "MaxTriggers", lazy=True)
    events = Cpt(EpicsSignalRO, "MaxEvents", lazy=True)
    input_count_rate = Cpt(EpicsSignalRO, "MaxInputCountRate", lazy=True)
    output_count_rate = Cpt(EpicsSignalRO, "MaxOutputCountRate", lazy=True)
    collect_mode = Cpt(EpicsSignal, "CollectMode")  # 0 MCA spectra, 1 MCA mapping
    pixel_advance_mode = Cpt(EpicsSignal, "PixelAdvanceMode")
    ignore_gate = Cpt(EpicsSignal, "IgnoreGate")
    input_logic_polarity = Cpt(EpicsSignal, "InputLogicPolarity")
    auto_pixels_per_buffer = Cpt(EpicsSignal, "AutoPixelsPerBuffer")
    pixels_per_buffer = Cpt(EpicsSignal, "PixelsPerBuffer")
    pixels_per_run = Cpt(EpicsSignal, "PixelsPerRun")
    nd_array_mode = Cpt(EpicsSignal, "NDArrayMode")

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
        sim_mode=False,
        **kwargs,
    ):
        """Initialize Falcon detector
        Args:
        #TODO add here the parameters for kind, read_attrs, configuration_attrs, parent
            prefix (str): PV prefix ("X12SA-SITORO:)
            name (str): 'falcon'
            kind (str): 
            read_attrs (list): 
            configuration_attrs (list): 
            parent (object): 
            device_manager (object): BEC device manager
            sim_mode (bool): simulation mode to start the detector without BEC, e.g. from ipython shell
        """
        super().__init__(
            prefix=prefix,
            name=name,
            kind=kind,
            read_attrs=read_attrs,
            configuration_attrs=configuration_attrs,
            parent=parent,
            **kwargs,
        )
        if device_manager is None and not sim_mode:
            raise FalconError("Add DeviceManager to initialization or init with sim_mode=True")
        self._stopped = False
        self.name = name
        self.wait_for_connection()
        # Spin up connections for simulation or BEC mode  
        if not sim_mode:
            from bec_lib.core.bec_service import SERVICE_CONFIG

            self.device_manager = device_manager
            self._producer = self.device_manager.producer
            self.service_cfg = SERVICE_CONFIG.config["service_config"]["file_writer"]
        else:
            base_path = f"/sls/X12SA/data/{self.scaninfo.username}/Data10/"
            self._producer = bec_utils.MockProducer()
            self.device_manager = bec_utils.MockDeviceManager()
            self.scaninfo = BecScaninfoMixin(device_manager, sim_mode)
            self.scaninfo.load_scan_metadata()
            self.service_cfg = {"base_path": base_path}

        self.scaninfo = BecScaninfoMixin(device_manager, sim_mode)
        self.scaninfo.load_scan_metadata()
        self.filewriter = FileWriterMixin(self.service_cfg)
        self._init()
    
    def _init(self) -> None:
        """Initialize detector, filewriter and set default parameters 
        """
        self._default_parameter()
        self._init_detector()
        self._init_filewriter()
    
    def _default_parameter(self) -> None:
        """Set default parameters for Falcon
        readout (float): readout time in seconds
        _value_pixel_per_buffer (int): number of spectra in buffer of Falcon Sitoro"""
        self.readout = 1e-3
        self._value_pixel_per_buffer = 20  # 16
        self._clean_up()        

    def _clean_up(self) -> None:
        """Clean up"""
        #TODO clarify when to use put and when to use set!
        self.hdf5.capture.put(0)
        self.stop_all.put(1)
        self.erase_all.put(1)

    def _init_filewriter(self) -> None:
        """Initialize file writer for Falcon.
        This includes setting variables for the HDF5 plugin (EPICS) that is used to write the data.
        """
        self.hdf5.enable.put(1)  # EnableCallbacks
        self.hdf5.xml_file_name.put("layout.xml")  # Points to hardcopy of HDF5 Layout xml file
        self.hdf5.lazy_open.put(1)  # Potentially not needed, means a temp data file is created first, could be 0
        self.hdf5.temp_suffix.put("")  # -> To be checked how to add FilePlugin_V22+
        self.hdf5.queue_size.put(2000) # size of queue for spectra in the buffer 

    def _init_detector(self) -> None:
        """Initialize Falcon detector.
        The detector is operated in MCA mapping mode. 
        Parameters here affect the triggering, gating  etc. 
        This includes also the readout chunk size and whether data is segmented into spectra in EPICS.
        """
        self.collect_mode.put(1)  # 1 MCA Mapping, 0 MCA Spectrum
        self.preset_mode.put(1)  # 1 Realtime
        self.input_logic_polarity.put(0)  # 0 Normal, 1 Inverted
        self.pixel_advance_mode.put(1)  # 0 User, 1 Gate, 2 Sync
        self.ignore_gate.put(0)  # 1 Yes, 0 No
        self.auto_pixels_per_buffer.put(0)  # 0 Manual 1 Auto
        self.pixels_per_buffer.put(self._value_pixel_per_buffer)  #
        self.nd_array_mode.put(1) # Segmentation happens in EPICS

    def _prep_det(self) -> None:
        """Prepare detector for acquisition"""
        self.collect_mode.put(1)
        self.preset_real.put(self.scaninfo.exp_time)
        self.pixels_per_run.put(int(self.scaninfo.num_points * self.scaninfo.frames_per_trigger))
        # self.auto_pixels_per_buffer.put(0)
        # self.pixels_per_buffer.put(self._value_pixel_per_buffer)

    def _prep_file_writer(self) -> None:
        """Prep HDF5 weriting"""
        # TODO creta filename and destination path from filepath
        self.destination_path = self.filewriter.compile_full_filename(
            self.scaninfo.scan_number, f"{self.name}.h5", 1000, 5, True
        )
        # self.hdf5.file_path.set(self.destination_path)
        file_path, file_name = os.path.split(self.destination_path)
        self.hdf5.file_path.put(file_path)
        self.hdf5.file_name.put(file_name)
        self.hdf5.file_template.put(f"%s%s")
        self.hdf5.num_capture.put(int(self.scaninfo.num_points * self.scaninfo.frames_per_trigger))
        self.hdf5.file_write_mode.put(2)
        self.hdf5.array_counter.put(0)
        self.hdf5.capture.put(1)

    def stage(self) -> List[object]:
        """stage the detector and file writer"""
        # TODO clean up needed?
        self._stopped = False
        self.scaninfo.load_scan_metadata()
        self.mokev = self.device_manager.devices.mokev.obj.read()[
            self.device_manager.devices.mokev.name
        ]["value"]

        logger.info("Waiting for pilatus2 to be armed")
        self._prep_det()
        logger.info("Pilatus2 armed")
        logger.info("Waiting for pilatus2 zmq stream to be ready")
        self._prep_file_writer()
        logger.info("Pilatus2 zmq ready")

        msg = BECMessage.FileMessage(file_path=self.destination_path, done=False)
        self._producer.set_and_publish(
            MessageEndpoints.public_file(self.scaninfo.scanID, self.name),
            msg.dumps(),
        )
        self.arm_acquisition()
        logger.info("Waiting for Falcon to be armed")
        while True:
            det_ctrl = self.state.read()[self.state.name]["value"]
            if det_ctrl == int(DetectorState.ACQUIRING):
                break
            if self._stopped == True:
                break
            time.sleep(0.005)
        logger.info("Falcon is armed")
        return super().stage()

    def arm_acquisition(self) -> None:
        self.start_all.put(1)

    def unstage(self) -> List[object]:
        logger.info("Waiting for Falcon to return from acquisition")
        old_scanID = self.scaninfo.scanID
        self.scaninfo.load_scan_metadata()
        logger.info(f"Old scanID: {old_scanID}, ")
        if self.scaninfo.scanID != old_scanID:
            self._stopped = True
        if self._stopped:
            return super().unstage()
        self._falcon_finished()
        self._clean_up()
        state = True
        msg = BECMessage.FileMessage(file_path=self.destination_path, done=True, successful=state)
        self._producer.set_and_publish(
            MessageEndpoints.public_file(self.scaninfo.metadata["scanID"], self.name),
            msg.dumps(),
        )
        self._stopped = False
        logger.info("Falcon done")
        return super().unstage()

    def _falcon_finished(self):
        """Function with 10s timeout"""
        timer = 0
        while True:
            det_ctrl = self.state.read()[self.state.name]["value"]
            writer_ctrl = self.hdf5.capture.get()
            received_frames = self.dxp.current_pixel.get()
            written_frames = self.hdf5.array_counter.get()
            total_frames = int(self.scaninfo.num_points * self.scaninfo.frames_per_trigger)
            # TODO if no writing was performed before
            if total_frames == received_frames and total_frames == written_frames:
                break
            if self._stopped == True:
                break
            time.sleep(0.1)
            timer += 0.1
            if timer > 5:
                logger.info(
                    f"Falcon missed a trigger: received trigger {received_frames}, send data {written_frames} from total_frames {total_frames}"
                )
                break
                # raise FalconTimeoutError
                #     f"Reached timeout with detector state {det_ctrl}, falcon state {writer_ctrl}, received trigger {received_frames} and files written {written_frames}"
                # )

    def stop(self, *, success=False) -> None:
        """Stop the scan, with camera and file writer"""
        self._clean_up()
        super().stop(success=success)
        self._stopped = True


if __name__ == "__main__":
    falcon = FalconCsaxs(name="falcon", prefix="X12SA-SITORO:", sim_mode=True)
