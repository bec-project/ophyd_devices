import enum
import threading
import time
from typing import Any, List
import numpy as np
import os
from ophyd import EpicsSignal, EpicsSignalRO, EpicsSignalWithRBV
from ophyd import DetectorBase, Device
from ophyd import ADComponent as ADCpt

from bec_lib.core import BECMessage, MessageEndpoints, threadlocked
from bec_lib.core.file_utils import FileWriterMixin
from bec_lib.core import bec_logger
from ophyd_devices.utils import bec_utils as bec_utils

from std_daq_client import StdDaqClient

from ophyd_devices.epics.devices.bec_scaninfo_mixin import BecScaninfoMixin


logger = bec_logger.logger


class EigerError(Exception):
    pass


class EigerTimeoutError(Exception):
    pass


class SlsDetectorCam(Device):
    detector_type = ADCpt(EpicsSignalRO, "DetectorType_RBV")
    setting = ADCpt(EpicsSignalWithRBV, "Setting")
    delay_time = ADCpt(EpicsSignalWithRBV, "DelayTime")
    threshold_energy = ADCpt(EpicsSignalWithRBV, "ThresholdEnergy")
    beam_energy = ADCpt(EpicsSignalWithRBV, "BeamEnergy")
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

    # fixes due to missing PVs from CamBase
    acquire = ADCpt(EpicsSignal, "Acquire")
    detector_state = ADCpt(EpicsSignalRO, "DetectorState_RBV")


class TriggerSource(int, enum.Enum):
    AUTO = 0
    TRIGGER = 1
    GATING = 2
    BURST_TRIGGER = 3


class DetectorState(int, enum.Enum):
    IDLE = 0
    ERROR = 1
    WAITING = 2
    FINISHED = 3
    TRANSMITTING = 4
    RUNNING = 5
    STOPPED = 6
    STILL_WAITING = 7
    INITIALIZING = 8
    DISCONNECTED = 9
    ABORTED = 10


class Eiger9mCsaxs(DetectorBase):
    """Eiger 9M detector for CSAXS

    Parent class: DetectorBase
    Device class: SlsDetectorCam

    Attributes:
        name str: 'eiger'
        prefix (str): PV prefix (X12SA-ES-EIGER9M:)

    """

    USER_ACCESS = [
        "describe",
    ]

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
        sim_mode=False,
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
        self._stopped = False
        self._lock = threading.RLock()
        if device_manager is None and not sim_mode:
            raise EigerError("Add DeviceManager to initialization or init with sim_mode=True")

        self.name = name
        self.wait_for_connection()  # Make sure to be connected before talking to PVs
        if not sim_mode:
            from bec_lib.core.bec_service import SERVICE_CONFIG

            self.device_manager = device_manager
            self._producer = self.device_manager.producer
            self.service_cfg = SERVICE_CONFIG.config["service_config"]["file_writer"]
        else:
            self._producer = bec_utils.MockProducer()
            self.device_manager = bec_utils.MockDeviceManager()
            self.scaninfo = BecScaninfoMixin(device_manager, sim_mode)
            self.scaninfo.load_scan_metadata()
            self.service_cfg = {"base_path": f"/sls/X12SA/data/{self.scaninfo.username}/Data10/"}
        self.scaninfo = BecScaninfoMixin(device_manager, sim_mode)
        self.scaninfo.load_scan_metadata()
        # TODO
        self.filepath = ""

        self.filewriter = FileWriterMixin(self.service_cfg)
        self.reduce_readout = 1e-3  # 3 ms
        self.triggermode = 0  # 0 : internal, scan must set this if hardware triggered
        self._init_eiger9m()
        self._init_standard_daq()

        # self.mokev = self.device_manager.devices.mokev.read()[
        #     self.device_manager.devices.mokev.name
        # ]["value"]

    def _init_eiger9m(self) -> None:
        """Init parameters for Eiger 9m"""
        self._set_trigger(TriggerSource.GATING)
        self.cam.acquire.set(0)

    def _update_std_cfg(self, cfg_key: str, value: Any) -> None:
        cfg = self.std_client.get_config()
        old_value = cfg.get(cfg_key)
        logger.info(old_value)
        if old_value is None:
            raise EigerError(
                f"Tried to change entry for key {cfg_key} in std_config that does not exist"
            )
        if not isinstance(value, type(old_value)):
            raise EigerError(
                f"Type of new value {type(value)}:{value} does not match old value {type(old_value)}:{old_value}"
            )
        cfg.update({cfg_key: value})
        logger.info(cfg)
        logger.info(f"Updated std_daq config for key {cfg_key} from {old_value} to {value}")
        self.std_client.set_config(cfg)

    def _init_standard_daq(self) -> None:
        self.std_rest_server_url = "http://xbl-daq-29:5000"
        self.std_client = StdDaqClient(url_base=self.std_rest_server_url)
        self.std_client.stop_writer()
        timeout = 0
        # TODO put back change of e-account!
        # self._update_std_cfg("writer_user_id", int(self.scaninfo.username.strip(" e")))
        # time.sleep(5)
        while not self.std_client.get_status()["state"] == "READY":
            time.sleep(0.1)
            timeout = timeout + 0.1
            logger.info("Waiting for std_daq init.")
            if timeout > 5:
                if not self.std_client.get_status()["state"]:
                    raise EigerError(
                        f"Std client not in READY state, returns: {self.std_client.get_status()}"
                    )
                else:
                    return

    def _prep_det(self) -> None:
        self._set_det_threshold()
        self._set_acquisition_params()
        self._set_trigger(TriggerSource.GATING)

    def _set_det_threshold(self) -> None:
        # threshold_energy PV exists on Eiger 9M?
        factor = 1
        if self.cam.threshold_energy._metadata["units"] == "eV":
            factor = 1000
        setp_energy = int(self.mokev * factor)
        energy = self.cam.beam_energy.read()[self.cam.beam_energy.name]["value"]
        if setp_energy != energy:
            self.cam.beam_energy.set(setp_energy)  # .wait()
        threshold = self.cam.threshold_energy.read()[self.cam.threshold_energy.name]["value"]
        if not np.isclose(setp_energy / 2, threshold, rtol=0.05):
            self.cam.threshold_energy.set(setp_energy / 2)  # .wait()

    def _set_acquisition_params(self) -> None:
        # self.cam.acquire_time.set(self.scaninfo.exp_time)
        # Set acquisition parameters slightly shorter then cycle
        # self.cam.acquire_period.set(
        #    self.scaninfo.exp_time + (self.scaninfo.readout_time - self.reduce_readout)
        # )
        self.cam.num_cycles.put(int(self.scaninfo.num_points * self.scaninfo.frames_per_trigger))
        self.cam.num_frames.put(1)

    def _set_trigger(self, trigger_source: TriggerSource) -> None:
        """Set trigger source for the detector, either directly to value or TriggerSource.* with
        AUTO = 0
        TRIGGER = 1
        GATING = 2
        BURST_TRIGGER = 3
        """
        value = int(trigger_source)
        self.cam.timing_mode.put(value)

    def _prep_file_writer(self) -> None:
        self.filepath = self.filewriter.compile_full_filename(
            self.scaninfo.scan_number, f"{self.name}.h5", 1000, 5, True
        )
        while not os.path.exists(os.path.dirname(self.filepath)):
            time.sleep(0.1)
        self._close_file_writer()
        logger.info(f" std_daq output filepath {self.filepath}")
        try:
            self.std_client.start_writer_async(
                {
                    "output_file": self.filepath,
                    "n_images": int(self.scaninfo.num_points * self.scaninfo.frames_per_trigger),
                }
            )
        except Exception as exc:
            time.sleep(5)
            if self.std_client.get_status()["state"] == "READY":
                raise EigerError(f"Timeout of start_writer_async with {exc}")

        while True:
            det_ctrl = self.std_client.get_status()["acquisition"]["state"]
            if det_ctrl == "WAITING_IMAGES":
                break
            time.sleep(0.005)

    def _close_file_writer(self) -> None:
        self.std_client.stop_writer()
        pass

    def stage(self) -> List[object]:
        """stage the detector and file writer"""
        self._stopped = False
        self._acquisition_done = False
        self.scaninfo.load_scan_metadata()
        self.mokev = self.device_manager.devices.mokev.obj.read()[
            self.device_manager.devices.mokev.name
        ]["value"]

        self._prep_file_writer()
        self._prep_det()
        logger.info("Waiting for std daq to be armed")
        logger.info("std_daq is ready")

        msg = BECMessage.FileMessage(file_path=self.filepath, done=False)
        self._producer.set_and_publish(
            MessageEndpoints.public_file(self.scaninfo.scanID, self.name),
            msg.dumps(),
        )
        msg = BECMessage.FileMessage(file_path=self.filepath, done=False)
        self._producer.set_and_publish(
            MessageEndpoints.file_event(self.name),
            msg.dumps(),
        )
        self.arm_acquisition()
        logger.info("Waiting for Eiger9m to be armed")
        while True:
            det_ctrl = self.cam.detector_state.read()[self.cam.detector_state.name]["value"]
            if det_ctrl == int(DetectorState.RUNNING):
                break
            if self._stopped == True:
                break
            time.sleep(0.005)
        logger.info("Eiger9m is armed")
        self._stopped = False
        return super().stage()

    @threadlocked
    def unstage(self) -> List[object]:
        """unstage the detector and file writer"""
        logger.info("Waiting for Eiger9M to finish")
        old_scanID = self.scaninfo.scanID
        self.scaninfo.load_scan_metadata()
        logger.info(f"Old scanID: {old_scanID}, ")
        if self.scaninfo.scanID != old_scanID:
            self._stopped = True
        if self._stopped == True:
            return super().unstage()
        self._eiger9M_finished()
        # Message to BEC
        state = True

        msg = BECMessage.FileMessage(file_path=self.filepath, done=True, successful=state)
        self._producer.set_and_publish(
            MessageEndpoints.public_file(self.scaninfo.scanID, self.name),
            msg.dumps(),
        )
        self._stopped = False
        logger.info("Eiger9M finished")
        return super().unstage()

    @threadlocked
    def _eiger9M_finished(self):
        """Function with 10s timeout"""
        timer = 0
        while True:
            det_ctrl = self.cam.acquire.read()[self.cam.acquire.name]["value"]
            std_ctrl = self.std_client.get_status()["acquisition"]["state"]
            status = self.std_client.get_status()
            received_frames = status["acquisition"]["stats"]["n_write_completed"]
            total_frames = int(self.scaninfo.num_points * self.scaninfo.frames_per_trigger)
            # TODO if no writing was performed before
            if det_ctrl == 0 and std_ctrl == "FINISHED" and total_frames == received_frames:
                break
            if self._stopped == True:
                self._close_file_writer()
                break
            time.sleep(0.1)
            timer += 0.1
            if timer > 5:
                self._stopped == True
                self._close_file_writer()
                raise EigerTimeoutError(
                    f"Reached timeout with detector state {det_ctrl}, std_daq state {std_ctrl} and received frames of {received_frames} for the file writer"
                )
        self._close_file_writer()

    def arm_acquisition(self) -> None:
        """Start acquisition in software trigger mode,
        or arm the detector in hardware of the detector
        """
        self.cam.acquire.set(1)

    def stop(self, *, success=False) -> None:
        """Stop the scan, with camera and file writer"""
        self.cam.acquire.set(0)
        self._close_file_writer()
        super().stop(success=success)
        self._stopped = True


if __name__ == "__main__":
    eiger = Eiger9mCsaxs(name="eiger", prefix="X12SA-ES-EIGER9M:", sim_mode=True)
