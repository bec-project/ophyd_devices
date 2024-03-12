import enum
import os

from ophyd import EpicsSignal, EpicsSignalRO, EpicsSignalWithRBV, Component as Cpt
from ophyd.mca import EpicsMCARecord
from ophyd import Device


from bec_lib.endpoints import MessageEndpoints
from bec_lib import messages
from bec_lib.logger import bec_logger


from ophyd_devices.epics.devices.psi_detector_base import PSIDetectorBase, CustomDetectorMixin


logger = bec_logger.logger


class FalconError(Exception):
    """Base class for exceptions in this module."""


class FalconTimeoutError(FalconError):
    """Raised when the Falcon does not respond in time."""


class DetectorState(enum.IntEnum):
    """Detector states for Falcon detector"""

    DONE = 0
    ACQUIRING = 1


class TriggerSource(enum.IntEnum):
    """Trigger source for Falcon detector"""

    USER = 0
    GATE = 1
    SYNC = 2


class MappingSource(enum.IntEnum):
    """Mapping source for Falcon detector"""

    SPECTRUM = 0
    MAPPING = 1


class EpicsDXPFalcon(Device):
    """
    DXP parameters for Falcon detector

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
    """
    HDF5 parameters for Falcon detector

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


class FalconSetup(CustomDetectorMixin):
    """
    Falcon setup class for cSAXS

    Parent class: CustomDetectorMixin

    """

    def initialize_default_parameter(self) -> None:
        """
        Set default parameters for Falcon

        This will set:
        - readout (float): readout time in seconds
        - value_pixel_per_buffer (int): number of spectra in buffer of Falcon Sitoro

        """
        self.parent.value_pixel_per_buffer = 20
        self.update_readout_time()

    def update_readout_time(self) -> None:
        """Set readout time for Eiger9M detector"""
        readout_time = (
            self.parent.scaninfo.readout_time
            if hasattr(self.parent.scaninfo, "readout_time")
            else self.parent.MIN_READOUT
        )
        self.parent.readout_time = max(readout_time, self.parent.MIN_READOUT)

    def initialize_detector(self) -> None:
        """Initialize Falcon detector"""
        self.stop_detector()
        self.stop_detector_backend()
        self.parent.set_trigger(
            mapping_mode=MappingSource.MAPPING, trigger_source=TriggerSource.GATE, ignore_gate=0
        )
        # 1 Realtime
        self.parent.preset_mode.put(1)
        # 0 Normal, 1 Inverted
        self.parent.input_logic_polarity.put(0)
        # 0 Manual 1 Auto
        self.parent.auto_pixels_per_buffer.put(0)
        # Sets the number of pixels/spectra in the buffer
        self.parent.pixels_per_buffer.put(self.parent.value_pixel_per_buffer)

    def stop_detector(self) -> None:
        """Stops detector"""

        self.parent.stop_all.put(1)
        self.parent.erase_all.put(1)

        signal_conditions = [
            (
                lambda: self.parent.state.read()[self.parent.state.name]["value"],
                DetectorState.DONE,
            ),
        ]

        if not self.wait_for_signals(
            signal_conditions=signal_conditions,
            timeout=self.parent.timeout - self.parent.timeout // 2,
            all_signals=False,
        ):
            # Retry stop detector and wait for remaining time
            raise FalconTimeoutError(
                f"Failed to stop detector, timeout with state {signal_conditions[0][0]}"
            )

    def stop_detector_backend(self) -> None:
        """Stop the detector backend"""
        self.parent.hdf5.capture.put(0)

    def initialize_detector_backend(self) -> None:
        """Initialize the detector backend for Falcon."""
        self.parent.hdf5.enable.put(1)
        # file location of h5 layout for cSAXS
        self.parent.hdf5.xml_file_name.put("layout.xml")
        # TODO Check if lazy open is needed and wanted!
        self.parent.hdf5.lazy_open.put(1)
        self.parent.hdf5.temp_suffix.put("")
        # size of queue for number of spectra allowed in the buffer, if too small at high throughput, data is lost
        self.parent.hdf5.queue_size.put(2000)
        # Segmentation into Spectra within EPICS, 1 is activate, 0 is deactivate
        self.parent.nd_array_mode.put(1)

    def prepare_detector(self) -> None:
        """Prepare detector for acquisition"""
        self.parent.set_trigger(
            mapping_mode=MappingSource.MAPPING, trigger_source=TriggerSource.GATE, ignore_gate=0
        )
        self.parent.preset_real.put(self.parent.scaninfo.exp_time)
        self.parent.pixels_per_run.put(
            int(self.parent.scaninfo.num_points * self.parent.scaninfo.frames_per_trigger)
        )

    def prepare_data_backend(self) -> None:
        """Prepare data backend for acquisition"""
        self.parent.filepath = self.parent.filewriter.compile_full_filename(
            self.parent.scaninfo.scan_number, f"{self.parent.name}.h5", 1000, 5, True
        )
        file_path, file_name = os.path.split(self.parent.filepath)
        self.parent.hdf5.file_path.put(file_path)
        self.parent.hdf5.file_name.put(file_name)
        self.parent.hdf5.file_template.put("%s%s")
        self.parent.hdf5.num_capture.put(
            int(self.parent.scaninfo.num_points * self.parent.scaninfo.frames_per_trigger)
        )
        self.parent.hdf5.file_write_mode.put(2)
        # Reset spectrum counter in filewriter, used for indexing & identifying missing triggers
        self.parent.hdf5.array_counter.put(0)
        # Start file writing
        self.parent.hdf5.capture.put(1)

    def arm_acquisition(self) -> None:
        """Arm detector for acquisition"""
        self.parent.start_all.put(1)
        signal_conditions = [
            (
                lambda: self.parent.state.read()[self.parent.state.name]["value"],
                DetectorState.ACQUIRING,
            )
        ]
        if not self.wait_for_signals(
            signal_conditions=signal_conditions,
            timeout=self.parent.timeout,
            check_stopped=True,
            all_signals=False,
        ):
            raise FalconTimeoutError(
                f"Failed to arm the acquisition. Detector state {signal_conditions[0][0]}"
            )

    def check_scanID(self) -> None:
        """Checks if scanID has changed and stops the scan if it has"""
        old_scanID = self.parent.scaninfo.scanID
        self.parent.scaninfo.load_scan_metadata()
        if self.parent.scaninfo.scanID != old_scanID:
            self.parent.stopped = True

    def publish_file_location(self, done: bool = False, successful: bool = None) -> None:
        """
        Publish the filepath to REDIS.

        We publish two events here:
        - file_event: event for the filewriter
        - public_file: event for any secondary service (e.g. radial integ code)

        Args:
            done (bool): True if scan is finished
            successful (bool): True if scan was successful
        """
        pipe = self.parent.connector.pipeline()
        if successful is None:
            msg = messages.FileMessage(file_path=self.parent.filepath, done=done)
        else:
            msg = messages.FileMessage(
                file_path=self.parent.filepath, done=done, successful=successful
            )
        self.parent.connector.set_and_publish(
            MessageEndpoints.public_file(self.parent.scaninfo.scanID, self.parent.name),
            msg,
            pipe=pipe,
        )
        self.parent.connector.set_and_publish(
            MessageEndpoints.file_event(self.parent.name), msg, pipe=pipe
        )
        pipe.execute()

    def finished(self) -> None:
        """Check if scan finished succesfully"""
        total_frames = int(
            self.parent.scaninfo.num_points * self.parent.scaninfo.frames_per_trigger
        )
        signal_conditions = [
            (
                self.parent.dxp.current_pixel.get,
                total_frames,
            ),
            (
                self.parent.hdf5.array_counter.get,
                total_frames,
            ),
        ]
        if not self.wait_for_signals(
            signal_conditions=signal_conditions,
            timeout=self.parent.timeout,
            check_stopped=True,
            all_signals=True,
        ):
            logger.debug(
                f"Falcon missed a trigger: received trigger {self.parent.dxp.current_pixel.get()},"
                f" send data {self.parent.hdf5.array_counter.get()} from total_frames"
                f" {total_frames}"
            )
        self.stop_detector()
        self.stop_detector_backend()


class FalconcSAXS(PSIDetectorBase):
    """
    Falcon Sitoro detector for CSAXS

    Parent class: PSIDetectorBase

    class attributes:
        custom_prepare_cls (FalconSetup)        : Custom detector setup class for cSAXS,
                                                  inherits from CustomDetectorMixin
        PSIDetectorBase.set_min_readout (float) : Minimum readout time for the detector
        dxp (EpicsDXPFalcon)                    : DXP parameters for Falcon detector
        mca (EpicsMCARecord)                    : MCA parameters for Falcon detector
        hdf5 (FalconHDF5Plugins)                : HDF5 parameters for Falcon detector
        MIN_READOUT (float)                     : Minimum readout time for the detector
    """

    # Specify which functions are revealed to the user in BEC client
    USER_ACCESS = [
        "describe",
    ]

    # specify Setup class
    custom_prepare_cls = FalconSetup
    # specify minimum readout time for detector
    MIN_READOUT = 3e-3

    # specify class attributes
    dxp = Cpt(EpicsDXPFalcon, "dxp1:")
    mca = Cpt(EpicsMCARecord, "mca1")
    hdf5 = Cpt(FalconHDF5Plugins, "HDF1:")

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

    def set_trigger(
        self, mapping_mode: MappingSource, trigger_source: TriggerSource, ignore_gate: int = 0
    ) -> None:
        """
        Set triggering mode for detector

        Args:
            mapping_mode (MappingSource): Mapping mode for the detector
            trigger_source (TriggerSource): Trigger source for the detector, pixel_advance_signal
            ignore_gate (int): Ignore gate from TTL signal; defaults to 0

        """
        mapping = int(mapping_mode)
        trigger = trigger_source
        self.collect_mode.put(mapping)
        self.pixel_advance_mode.put(trigger)
        self.ignore_gate.put(ignore_gate)

    def stage(self) -> list[object]:
        """Stage"""
        rtr = super().stage()
        self.custom_prepare.arm_acquisition()
        return rtr


if __name__ == "__main__":
    falcon = FalconcSAXS(name="falcon", prefix="X12SA-SITORO:", sim_mode=True)
