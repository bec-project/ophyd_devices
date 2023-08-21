import json
import os
import requests
import numpy as np

from typing import List

from ophyd import EpicsSignal, EpicsSignalRO, EpicsSignalWithRBV
from ophyd import CamBase, DetectorBase
from ophyd import ADComponent as ADCpt
from ophyd.areadetector.plugins import FileBase

from bec_lib.core import BECMessage, MessageEndpoints, RedisConnector
from bec_lib.core.file_utils import FileWriterMixin
from bec_lib.core import bec_logger

from std_daq_client import StdDaqClient


logger = bec_logger.logger


class slsDetectorCam(CamBase, FileBase):
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


# TODO refactor class -> move away from DetectorBase and PilatusDetectorCamEx class to Device. -> this will be cleaner
class Eiger9mCsaxs(DetectorBase):
    """

    in device config, device_access needs to be set true to inject the device manager
    """

    cam = ADCpt(slsDetectorCam, "cam1:")

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
        self.username = "e21206"  #
        # self.username = self.device_manager.producer.get(MessageEndpoints.account()).decode()

        self._init_eiger9m()
        self._init_standard_daq()

        self.service_cfg = {"base_path": f"/sls/X12SA/data/{self.username}/Data10/data/"}
        self.filewriter = FileWriterMixin(self.service_cfg)  # TODO check FileWriterMixin if generix
        self._producer = RedisConnector(["localhost:6379"]).producer()
        # self.num_frames = 0
        self.readout = 0.003  # 3 ms
        self.triggermode = 0  # 0 : internal, scan must set this if hardware triggered

    def _init_eiger9m(self) -> None:
        """Init parameters for Eiger 9m"""
        pass

    def _init_standard_daq(self) -> None:
        self.std_rest_server_url = "http://xbl-daq-29:5000"
        self.std_client = StdDaqClient(url_base=self.std_rest_server_url)

    def _get_current_scan_msg(self) -> BECMessage.ScanStatusMessage:
        msg = self.device_manager.producer.get(MessageEndpoints.scan_status())
        return BECMessage.ScanStatusMessage.loads(msg)

    def _prepare_standard_daq(self) -> None:
        self.std_client.start_writer_async({"output_file": filename, "n_images": self.num_frames})

    def stage(self) -> List[object]:
        # TODO remove
        # scan_msg = self._get_current_scan_msg()
        # self.metadata = {
        #     "scanID": scan_msg.content["scanID"],
        #     "RID": scan_msg.content["info"]["RID"],
        #     "queueID": scan_msg.content["info"]["queueID"],
        # }
        self.scan_number = 10  # scan_msg.content["info"]["scan_number"]
        self.exp_time = 0.5  # scan_msg.content["info"]["exp_time"]
        self.num_frames = 3  # scan_msg.content["info"]["num_points"]
        self.mokev = 12  # self.device_manager.devices.mokev.read()['mokev']['value']
        # TODO remove
        # self.username = self.device_manager.producer.get(MessageEndpoints.account()).decode()

        # set pilatus threshold
        self._set_eiger_threshold()
        self._set_acquisition_params(
            exp_time=self.exp_time,
            readout=self.readout,
            num_frames=self.num_frames,
            triggermode=self.triggermode,
        )

        return super().stage()

    def unstage(self) -> List[object]:
        return super().unstage()

    def _set_eiger_threshold(self) -> None:
        pil_threshold = self.cam.threshold_energy.read()[self.cam.threshold_energy.name]["value"]
        if not np.isclose(self.mokev / 2, pil_threshold, rtol=0.05):
            self.cam.threshold_energy.set(self.mokev / 2)

    def _set_acquisition_params(
        self, exp_time: float, readout: float, num_frames: int, triggermode: int
    ) -> None:
        """set acquisition parameters on the detector

        Args:
            exp_time (float): exposure time
            readout (float): readout time
            num_frames (int): images per scan
            triggermode (int):
                0 Internal
                1 Ext. Enable
                2 Ext. Trigger
                3 Mult. Trigger
                4 Alignment
        Returns:
            None
        """
        self.cam.acquire_time.set(exp_time)
        self.cam.acquire_period.set(exp_time + readout)
        self.cam.num_images.set(num_frames)
        self.cam.num_exposures.set(1)
        # trigger_mode exists in baseclass
        self.cam.timing_mode.set(triggermode)

    def acquire(self) -> None:
        self.cam.acquire.set(1)

    def stop(self, *, success=False) -> None:
        self.cam.acquire.set(0)
        self.unstage()
        super().stop(success=success)
        self._stopped = True
