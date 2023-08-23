import time
from typing import List
import numpy as np

from ophyd import EpicsSignal, EpicsSignalRO, EpicsSignalWithRBV
from ophyd import CamBase, DetectorBase
from ophyd import ADComponent as ADCpt
from ophyd.areadetector.plugins import FileBase

from bec_lib.core import BECMessage, MessageEndpoints
from bec_lib.core.file_utils import FileWriterMixin
from bec_lib.core import bec_logger

from std_daq_client import StdDaqClient

from .bec_scaninfo_mixin import BecScaninfoMixin


logger = bec_logger.logger


class SlsDetectorCam(CamBase, FileBase):
    detector_type = ADCpt(EpicsSignalRO, "DetectorType_RBV")
    setting = ADCpt(EpicsSignalWithRBV, "Setting")
    delay_time = ADCpt(EpicsSignalWithRBV, "DelayTime")
    threshold_energy = ADCpt(EpicsSignalWithRBV, "ThresholdEnergy")
    enable_trimbits = ADCpt(EpicsSignalWithRBV, "Trimbits")
    bit_depth = ADCpt(EpicsSignalWithRBV, "BitDepth")
    num_gates = ADCpt(EpicsSignalWithRBV, "NumGates")
    num_cycles = ADCpt(EpicsSignalWithRBV, "NumCycles")
    num_frames = ADCpt(EpicsSignalWithRBV, "NumFrames")
    timing_mode = ADCpt(EpicsSignalWithRBV, "TimingMode")
    trigger_software = ADCpt(EpicsSignal, "TriggerSoftware")
    high_voltage = ADCpt(EpicsSignalWithRBV, "HighVoltage")
    # Receiver and data callback
    receiver_mode = ADCpt(EpicsSignalWithRBV, "ReceiverMode")
    receiver_stream = ADCpt(EpicsSignalWithRBV, "ReceiverStream")
    enable_data = ADCpt(EpicsSignalWithRBV, "UseDataCallback")
    missed_packets = ADCpt(EpicsSignalRO, "ReceiverMissedPackets_RBV")
    # Direct settings access
    setup_file = ADCpt(EpicsSignal, "SetupFile")
    load_setup = ADCpt(EpicsSignal, "LoadSetup")
    command = ADCpt(EpicsSignal, "Command")
    # Mythen 3
    counter_mask = ADCpt(EpicsSignalWithRBV, "CounterMask")
    counter1_threshold = ADCpt(EpicsSignalWithRBV, "Counter1Threshold")
    counter2_threshold = ADCpt(EpicsSignalWithRBV, "Counter2Threshold")
    counter3_threshold = ADCpt(EpicsSignalWithRBV, "Counter3Threshold")
    gate1_delay = ADCpt(EpicsSignalWithRBV, "Gate1Delay")
    gate1_width = ADCpt(EpicsSignalWithRBV, "Gate1Width")
    gate2_delay = ADCpt(EpicsSignalWithRBV, "Gate2Delay")
    gate2_width = ADCpt(EpicsSignalWithRBV, "Gate2Width")
    gate3_delay = ADCpt(EpicsSignalWithRBV, "Gate3Delay")
    gate3_width = ADCpt(EpicsSignalWithRBV, "Gate3Width")
    # Moench
    json_frame_mode = ADCpt(EpicsSignalWithRBV, "JsonFrameMode")
    json_detector_mode = ADCpt(EpicsSignalWithRBV, "JsonDetectorMode")


class Eiger9mCsaxs(DetectorBase):
    """Eiger 9M detector for CSAXS

    Parent class: DetectorBase
    Device class: SlsDetectorCam

    Attributes:
        name str: 'eiger'
        prefix (str): PV prefix (X12SA-ES-EIGER9M:)

    """

    cam = ADCpt(SlsDetectorCam, "cam1:")

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
        self.name = name
        self.scaninfo.username = "e21206"
        # TODO once running from BEC
        # self.scaninfo.username = self.device_manager.producer.get(MessageEndpoints.account()).decode()
        self.wait_for_connection()  # Make sure to be connected before talking to PVs
        self._init_eiger9m()
        self._init_standard_daq()

        self.service_cfg = {"base_path": f"/sls/X12SA/data/{self.scaninfo.username}/Data10/data/"}
        self.filewriter = FileWriterMixin(self.service_cfg)
        self.scaninfo = BecScaninfoMixin(device_manager)
        self._producer = self.device_manager.producer
        self.readout = 0.003  # 3 ms
        self.triggermode = 0  # 0 : internal, scan must set this if hardware triggered

    def _init_eiger9m(self) -> None:
        """Init parameters for Eiger 9m"""
        pass

    def _init_standard_daq(self) -> None:
        self.std_rest_server_url = "http://xbl-daq-29:5000"
        self.std_client = StdDaqClient(url_base=self.std_rest_server_url)
        timeout = 0
        # TODO check std_daq status
        while not self.std_client.std_status["state"] == "READY":
            time.sleep(0.1)
            timeout = timeout + 0.1
            if timeout > 2:
                logger.info("Timeout of STD")

        # TODO check status after sleep

    def _prep_det(self) -> None:
        self._set_det_threshold()
        self._set_acquisition_params()

    def _set_det_threshold(self) -> None:
        # threshold_energy PV exists on Eiger 9M?
        threshold = self.cam.threshold_energy.read()[self.cam.threshold_energy.name]["value"]
        if not np.isclose(self.mokev / 2, threshold, rtol=0.05):
            self.cam.threshold_energy.set(self.mokev / 2)

    def _set_acquisition_params(self) -> None:
        self.cam.acquire_time.set(self.scaninfo.exp_time)
        self.cam.acquire_period.set(self.scaninfo.exp_time + self.readout)
        self.cam.num_images.set(self.scaninfo.num_frames)
        self.cam.num_exposures.set(1)
        # trigger_mode vs timing mode ??!!
        self.cam.timing_mode.set(self.triggermode)

    def _prep_file_writer(self) -> None:
        self.filepath = self.filewriter.compile_full_filename(
            self.scaninfo.scan_number, "eiger", 1000, 5, True
        )
        self.std_client.start_writer_async(
            {"output_file": self.filepath, "n_images": self.scaninfo.num_frames}
        )

    def _close_file_writer(self) -> None:
        pass

    def stage(self) -> List[object]:
        """stage the detector and file writer"""
        # TODO remove once running from BEC
        # self.scaninfo.load_scan_metadata()
        self.scaninfo.scan_number = 10
        self.scaninfo.exp_time = 0.5
        self.scaninfo.num_frames = 3
        self.mokev = 12
        self.triggermode = 0

        self._prep_det()
        self._prep_file_writer()

        msg = BECMessage.FileMessage(file_path=self.filepath, done=False)
        self._producer.set_and_publish(
            MessageEndpoints.public_file(self.scaninfo.scanID, "eiger9m"),
            msg.dumps(),
        )

        return super().stage()

    def unstage(self) -> List[object]:
        """unstage the detector and file writer"""
        self.timing_mode = 0
        self._close_file_writer()
        std_status = self.std_client.get_status()
        if (
            not std_status["acquisition"]["message"] == "Completed"
            or std_status["acquisition"]["state"] == "FINISHED"
        ):
            logger.info(std_status)
            # TODO add BEC error message
            # raise
        # TODO check detector stateX12SA-ES-EIGER9M:cam1:DetectorState_RBV

        state = True
        msg = BECMessage.FileMessage(file_path=self.filepath, done=True, successful=state)
        self.producer.set_and_publish(
            MessageEndpoints.public_file(self.metadata["scanID"], self.name),
            msg.dumps(),
        )
        return super().unstage()

    def acquire(self) -> None:
        """Start acquisition in software trigger mode,
        or arm the detector in hardware of the detector
        """
        self.cam.acquire.set(1)

    def stop(self, *, success=False) -> None:
        """Stop the scan, with camera and file writer"""
        self.cam.acquire.set(0)
        self.std_client.stop_writer()
        self.unstage()
        super().stop(success=success)
        self._stopped = True
