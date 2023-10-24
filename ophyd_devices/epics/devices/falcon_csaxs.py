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
    """Base class for exceptions in this module."""

    pass


class FalconTimeoutError(Exception):
    """Raised when the Falcon does not respond in time during unstage."""

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
        """Initialize detector, filewriter and set default parameters"""
        self._default_parameter()
        self._init_detector()
        self._init_filewriter()

    def _default_parameter(self) -> None:
        """Set default parameters for Falcon
        readout (float): readout time in seconds
        _value_pixel_per_buffer (int): number of spectra in buffer of Falcon Sitoro"""
        self.readout = 1e-3
        self._value_pixel_per_buffer = 20  # 16
        self._stop_det()
        self._stop_file_writer()

    def _stop_det(self) -> None:
        """ "Stop detector"""
        self.stop_all.put(1)
        self.erase_all.put(1)

    def _stop_file_writer(self) -> None:
        """ "Stop the file writer"""
        self.hdf5.capture.put(0)

    def _init_filewriter(self) -> None:
        """Initialize file writer for Falcon.
        This includes setting variables for the HDF5 plugin (EPICS) that is used to write the data.
        """
        self.hdf5.enable.put(1)  # EnableCallbacks
        self.hdf5.xml_file_name.put("layout.xml")  # Points to hardcopy of HDF5 Layout xml file
        self.hdf5.lazy_open.put(
            1
        )  # Potentially not needed, means a temp data file is created first, could be 0
        self.hdf5.temp_suffix.put("")  # -> To be checked how to add FilePlugin_V22+
        self.hdf5.queue_size.put(2000)  # size of queue for spectra in the buffer

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
        self.nd_array_mode.put(1)  # Segmentation happens in EPICS

    def stage(self) -> List[object]:
        """Stage command, called from BEC in preparation of a scan.
        This will iniate the preparation of detector and file writer.
        The following functuions are called:
            - _prep_file_writer
            - _prep_det
            - _publish_file_location
            - _arm_acquisition
        The device returns a List[object] from the Ophyd Device class.

        #TODO make sure this is fullfiled

        Staging not idempotent and should raise
        :obj:`RedundantStaging` if staged twice without an
        intermediate :meth:`~BlueskyInterface.unstage`.
        """
        self._stopped = False
        self.scaninfo.load_scan_metadata()
        self.mokev = self.device_manager.devices.mokev.obj.read()[
            self.device_manager.devices.mokev.name
        ]["value"]
        self._prep_file_writer()
        self._prep_det()
        state = False
        self._publish_file_location(done=state, successful=state)
        self._arm_acquisition()
        return super().stage()

    def _prep_det(self) -> None:
        """Prepare detector for acquisition"""
        self.collect_mode.put(1)
        self.preset_real.put(self.scaninfo.exp_time)
        self.pixels_per_run.put(int(self.scaninfo.num_points * self.scaninfo.frames_per_trigger))

    def _prep_file_writer(self) -> None:
        """Prepare filewriting from HDF5 plugin"""
        self.filepath = self.filewriter.compile_full_filename(
            self.scaninfo.scan_number, f"{self.name}.h5", 1000, 5, True
        )
        file_path, file_name = os.path.split(self.filepath)
        self.hdf5.file_path.put(file_path)
        self.hdf5.file_name.put(file_name)
        self.hdf5.file_template.put(f"%s%s")
        self.hdf5.num_capture.put(int(self.scaninfo.num_points * self.scaninfo.frames_per_trigger))
        self.hdf5.file_write_mode.put(2)
        self.hdf5.array_counter.put(0)
        self.hdf5.capture.put(1)

    def _publish_file_location(self, done=False, successful=False) -> None:
        """Publish the filepath to REDIS
        First msg for file writer and the second one for other listeners (e.g. radial integ)
        """
        pipe = self._producer.pipeline()
        msg = BECMessage.FileMessage(file_path=self.filepath, done=done, successful=successful)
        self._producer.set_and_publish(
            MessageEndpoints.public_file(self.scaninfo.scanID, self.name), msg.dumps(), pipe=pipe
        )
        self._producer.set_and_publish(
            MessageEndpoints.file_event(self.name), msg.dumps(), pip=pipe
        )
        pipe.execute()

    def _arm_acquisition(self) -> None:
        """Arm Falcon detector for acquisition"""
        self.start_all.put(1)
        while True:
            det_ctrl = self.state.read()[self.state.name]["value"]
            if det_ctrl == int(DetectorState.ACQUIRING):
                break
            if self._stopped == True:
                break
            time.sleep(0.005)

    def unstage(self) -> List[object]:
        """Unstage the device.

        This method must be idempotent, multiple calls (without a new
        call to 'stage') have no effect.

        Functions called:
            - _finished
            - _publish_file_location
        """
        old_scanID = self.scaninfo.scanID
        self.scaninfo.load_scan_metadata()
        logger.info(f"Old scanID: {old_scanID}, ")
        if self.scaninfo.scanID != old_scanID:
            self._stopped = True
        if self._stopped:
            return super().unstage()
        self._finished()
        state = True
        self._publish_file_location(done=state, successful=state)
        self._stopped = False
        return super().unstage()

    def _finished(self):
        """Check if acquisition is finished.

        This function is called from unstage and stop
        and will check detector and file backend status.
        Timeouts after given time

        Functions called:
            - _stop_det
            - _stop_file_writer
        """
        sleep_time = 0.1
        timeout = 5
        timer = 0
        while True:
            det_ctrl = self.state.read()[self.state.name]["value"]
            writer_ctrl = self.hdf5.capture.get()
            received_frames = self.dxp.current_pixel.get()
            written_frames = self.hdf5.array_counter.get()
            total_frames = int(self.scaninfo.num_points * self.scaninfo.frames_per_trigger)
            # TODO Could check state of detector (det_ctrl) and file writer (writer_ctrl)
            if total_frames == received_frames and total_frames == written_frames:
                break
            if self._stopped == True:
                break
            time.sleep(sleep_time)
            timer += sleep_time
            if timer > timeout:
                logger.info(
                    f"Falcon missed a trigger: received trigger {received_frames}, send data {written_frames} from total_frames {total_frames}"
                )
                break
        self._stop_det()
        self._stop_file_writer()

    def stop(self, *, success=False) -> None:
        """Stop the scan, with camera and file writer"""
        self._stop_det()
        self._stop_file_writer()
        super().stop(success=success)
        self._stopped = True


if __name__ == "__main__":
    falcon = FalconCsaxs(name="falcon", prefix="X12SA-SITORO:", sim_mode=True)
