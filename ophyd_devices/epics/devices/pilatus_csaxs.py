import enum
import json
import os
import subprocess
import time
from typing import List
import requests
import numpy as np

from ophyd import EpicsSignal, EpicsSignalRO, EpicsSignalWithRBV
from ophyd import DetectorBase, Device, Staged
from ophyd import ADComponent as ADCpt
from ophyd_devices.utils import bec_utils as bec_utils

from bec_lib.core import BECMessage, MessageEndpoints
from bec_lib.core.file_utils import FileWriterMixin
from bec_lib.core import bec_logger


from ophyd_devices.epics.devices.bec_scaninfo_mixin import BecScaninfoMixin

logger = bec_logger.logger


class PilatusError(Exception):
    pass


class PilatusTimeoutError(Exception):
    pass


class TriggerSource(int, enum.Enum):
    INTERNAL = 0
    EXT_ENABLE = 1
    EXT_TRIGGER = 2
    MULTI_TRIGGER = 3
    ALGINMENT = 4


class SlsDetectorCam(Device):  # CamBase, FileBase):
    # detector_type = ADCpt(EpicsSignalRO, "DetectorType_RBV")
    # setting = ADCpt(EpicsSignalWithRBV, "Setting")
    # beam_energy = ADCpt(EpicsSignalWithRBV, "BeamEnergy")
    # enable_trimbits = ADCpt(EpicsSignalWithRBV, "Trimbits")
    # bit_depth = ADCpt(EpicsSignalWithRBV, "BitDepth")
    # trigger_software = ADCpt(EpicsSignal, "TriggerSoftware")
    # high_voltage = ADCpt(EpicsSignalWithRBV, "HighVoltage")
    # Receiver and data callback
    # receiver_mode = ADCpt(EpicsSignalWithRBV, "ReceiverMode")
    # receiver_stream = ADCpt(EpicsSignalWithRBV, "ReceiverStream")
    # enable_data = ADCpt(EpicsSignalWithRBV, "UseDataCallback")
    # missed_packets = ADCpt(EpicsSignalRO, "ReceiverMissedPackets_RBV")
    # # Direct settings access
    # setup_file = ADCpt(EpicsSignal, "SetupFile")
    # load_setup = ADCpt(EpicsSignal, "LoadSetup")
    # command = ADCpt(EpicsSignal, "Command")
    # Mythen 3
    # counter_mask = ADCpt(EpicsSignalWithRBV, "CounterMask")
    # counter1_threshold = ADCpt(EpicsSignalWithRBV, "Counter1Threshold")
    # counter2_threshold = ADCpt(EpicsSignalWithRBV, "Counter2Threshold")
    # counter3_threshold = ADCpt(EpicsSignalWithRBV, "Counter3Threshold")
    # gate1_delay = ADCpt(EpicsSignalWithRBV, "Gate1Delay")
    # gate1_width = ADCpt(EpicsSignalWithRBV, "Gate1Width")
    # gate2_delay = ADCpt(EpicsSignalWithRBV, "Gate2Delay")
    # gate2_width = ADCpt(EpicsSignalWithRBV, "Gate2Width")
    # gate3_delay = ADCpt(EpicsSignalWithRBV, "Gate3Delay")
    # gate3_width = ADCpt(EpicsSignalWithRBV, "Gate3Width")
    # Moench
    # json_frame_mode = ADCpt(EpicsSignalWithRBV, "JsonFrameMode")
    # json_detector_mode = ADCpt(EpicsSignalWithRBV, "JsonDetectorMode")

    # Eiger9M
    # delay_time = ADCpt(EpicsSignalWithRBV, "DelayTime")
    # num_frames = ADCpt(EpicsSignalWithRBV, "NumFrames")
    # acquire = ADCpt(EpicsSignal, "Acquire")
    # acquire_time = ADCpt(EpicsSignal, 'AcquireTime')
    # detector_state = ADCpt(EpicsSignalRO, "DetectorState_RBV")
    # threshold_energy = ADCpt(EpicsSignalWithRBV, "ThresholdEnergy")
    # num_gates = ADCpt(EpicsSignalWithRBV, "NumGates")
    # num_cycles = ADCpt(EpicsSignalWithRBV, "NumCycles")
    # timing_mode = ADCpt(EpicsSignalWithRBV, "TimingMode")

    # Pilatus_2 300k
    num_images = ADCpt(EpicsSignalWithRBV, "NumImages")
    num_exposures = ADCpt(EpicsSignalWithRBV, "NumExposures")
    delay_time = ADCpt(EpicsSignalWithRBV, "NumExposures")
    trigger_mode = ADCpt(EpicsSignalWithRBV, "TriggerMode")
    acquire = ADCpt(EpicsSignal, "Acquire")
    armed = ADCpt(EpicsSignalRO, "Armed")

    read_file_timeout = ADCpt(EpicsSignal, "ImageFileTmot")
    detector_state = ADCpt(EpicsSignalRO, "StatusMessage_RBV")
    status_message_camserver = ADCpt(EpicsSignalRO, "StringFromServer_RBV", string=True)
    acquire_time = ADCpt(EpicsSignal, "AcquireTime")
    acquire_period = ADCpt(EpicsSignal, "AcquirePeriod")
    threshold_energy = ADCpt(EpicsSignalWithRBV, "ThresholdEnergy")
    file_path = ADCpt(EpicsSignalWithRBV, "FilePath")
    file_name = ADCpt(EpicsSignalWithRBV, "FileName")
    file_number = ADCpt(EpicsSignalWithRBV, "FileNumber")
    auto_increment = ADCpt(EpicsSignalWithRBV, "AutoIncrement")
    file_template = ADCpt(EpicsSignalWithRBV, "FileTemplate")
    file_format = ADCpt(EpicsSignalWithRBV, "FileNumber")
    gap_fill = ADCpt(EpicsSignalWithRBV, "GapFill")


class PilatusCsaxs(DetectorBase):
    """Pilatus_2 300k detector for CSAXS

    Parent class: DetectorBase
    Device class: PilatusDetectorCamEx

    Attributes:
        name str: 'pilatus_2'
        prefix (str): PV prefix (X12SA-ES-PILATUS300K:)

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
        if device_manager is None and not sim_mode:
            raise PilatusError("Add DeviceManager to initialization or init with sim_mode=True")

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
        self.filepath_h5 = ""

        self.filewriter = FileWriterMixin(self.service_cfg)
        self.readout = 1e-3  # 3 ms

        # TODO maybe needed
        # self._close_file_writer()

    def _get_current_scan_msg(self) -> BECMessage.ScanStatusMessage:
        msg = self.device_manager.producer.get(MessageEndpoints.scan_status())
        return BECMessage.ScanStatusMessage.loads(msg)

    def _prep_det(self) -> None:
        # TODO slow reaction, seemed to have timeout.
        self._set_det_threshold()
        self._set_acquisition_params()

    def _set_det_threshold(self) -> None:
        # threshold_energy PV exists on Eiger 9M?
        factor = 1
        if self.cam.threshold_energy._metadata["units"] == "eV":
            factor = 1000
        setp_energy = int(self.mokev * factor)
        threshold = self.cam.threshold_energy.read()[self.cam.threshold_energy.name]["value"]
        if not np.isclose(setp_energy / 2, threshold, rtol=0.05):
            self.cam.threshold_energy.set(setp_energy / 2)

    def _set_acquisition_params(self) -> None:
        """set acquisition parameters on the detector"""
        # self.cam.acquire_time.set(self.exp_time)
        # self.cam.acquire_period.set(self.exp_time + self.readout)
        self.cam.num_images.set(int(self.scaninfo.num_points * self.scaninfo.frames_per_trigger))
        self.cam.num_exposures.set(1)
        self._set_trigger(TriggerSource.EXT_ENABLE)  # EXT_TRIGGER)

    def _set_trigger(self, trigger_source: TriggerSource) -> None:
        """Set trigger source for the detector, either directly to value or TriggerSource.* with
        INTERNAL = 0
        EXT_ENABLE = 1
        EXT_TRIGGER = 2
        MULTI_TRIGGER = 3
        ALGINMENT = 4
        """
        value = int(trigger_source)
        self.cam.trigger_mode.set(value)

    def _prep_file_writer(self) -> None:
        """Prepare the file writer for pilatus_2
        a zmq service is running on xbl-daq-34 that is waiting
        for a zmq message to start the writer for the pilatus_2 x12sa-pd-2
        """
        # TODO worked reliable with time.sleep(2)
        # self._close_file_writer()
        # time.sleep(2)
        # self._stop_file_writer()
        # time.sleep(2)
        self._close_file_writer()
        time.sleep(0.1)
        self._stop_file_writer()
        time.sleep(0.1)

        self.filepath_h5 = self.filewriter.compile_full_filename(
            self.scaninfo.scan_number, "pilatus_2.h5", 1000, 5, True
        )
        self.cam.file_path.put(f"/dev/shm/zmq/")
        self.cam.file_name.put(f"{self.scaninfo.username}_2_{self.scaninfo.scan_number:05d}")
        self.cam.auto_increment.put(1)  # auto increment
        self.cam.file_number.put(0)  # first iter
        self.cam.file_format.put(0)  # 0: TIFF
        self.cam.file_template.put("%s%s_%5.5d.cbf")

        # compile filename
        basepath = f"/sls/X12SA/data/{self.scaninfo.username}/Data10/pilatus_2/"
        self.destination_path = os.path.join(
            basepath,
            self.filewriter.get_scan_directory(self.scaninfo.scan_number, 1000, 5),
        )
        # Make directory if needed
        os.makedirs(self.destination_path, exist_ok=True)

        data_msg = {
            "source": [
                {
                    "searchPath": "/",
                    "searchPattern": "glob:*.cbf",
                    "destinationPath": self.destination_path,
                }
            ]
        }

        logger.info(data_msg)
        headers = {"Content-Type": "application/json", "Accept": "application/json"}

        res = requests.put(
            url="http://x12sa-pd-2:8080/stream/pilatus_2",
            data=json.dumps(data_msg),
            headers=headers,
        )
        logger.info(f"{res.status_code} -  {res.text} - {res.content}")

        if not res.ok:
            res.raise_for_status()

        # prepare writer
        data_msg = [
            "zmqWriter",
            self.scaninfo.username,
            {
                "addr": "tcp://x12sa-pd-2:8888",
                "dst": ["file"],
                "numFrm": int(self.scaninfo.num_points * self.scaninfo.frames_per_trigger),
                "timeout": 2000,
                "ifType": "PULL",
                "user": self.scaninfo.username,
            },
        ]

        res = requests.put(
            url="http://xbl-daq-34:8091/pilatus_2/run",
            data=json.dumps(data_msg),
            headers=headers,
        )
        # subprocess.run("curl -i -s -X PUT http://xbl-daq-34:8091/pilatus_2/run -d '[\"zmqWriter\",\"e20636\",{\"addr\":\"tcp://x12sa-pd-2:8888\",\"dst\":[\"file\"],\"numFrm\":10,\"timeout\":2000,\"ifType\":\"PULL\",\"user\":\"e20636\"}]'", shell=True)

        logger.info(f"{res.status_code}  - {res.text} - {res.content}")

        if not res.ok:
            res.raise_for_status()

        # Wait for server to become available again
        time.sleep(0.1)

        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        data_msg = [
            "zmqWriter",
            self.scaninfo.username,
            {
                "frmCnt": int(self.scaninfo.num_points * self.scaninfo.frames_per_trigger),
                "timeout": 2000,
            },
        ]
        logger.info(f"{res.status_code} -{res.text} - {res.content}")

        try:
            res = requests.put(
                url="http://xbl-daq-34:8091/pilatus_2/wait",
                data=json.dumps(data_msg),
                #            headers=headers,
            )

            logger.info(f"{res}")

            if not res.ok:
                res.raise_for_status()
        except Exception as exc:
            logger.info(f"Pilatus2 wait threw Exception: {exc}")

    def _close_file_writer(self) -> None:
        """Close the file writer for pilatus_2
        a zmq service is running on xbl-daq-34 that is waiting
        for a zmq message to stop the writer for the pilatus_2 x12sa-pd-2
        """
        try:
            res = requests.delete(url="http://x12sa-pd-2:8080/stream/pilatus_2")
            if not res.ok:
                res.raise_for_status()
        except Exception as exc:
            logger.info(f"Pilatus2 delete threw Exception: {exc}")

    def _stop_file_writer(self) -> None:
        res = requests.put(
            url="http://xbl-daq-34:8091/pilatus_2/stop",
            # data=json.dumps(data_msg),
            #            headers=headers,
        )

        if not res.ok:
            res.raise_for_status()

    def stage(self) -> List[object]:
        """stage the detector and file writer"""
        self._acquisition_done = False
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
        msg = BECMessage.FileMessage(
            file_path=self.filepath_h5, done=False, metadata={"input_path": self.destination_path}
        )
        return super().stage()

    def pre_scan(self) -> None:
        self.acquire()

    def unstage(self) -> List[object]:
        """unstage the detector and file writer"""
        # Reset to software trigger
        logger.info("Waiting for Pilatus to return from acquisition")
        old_scanID = self.scaninfo.scanID
        self.scaninfo.load_scan_metadata()
        logger.info(f"Old scanID: {old_scanID}, ")
        if self.scaninfo.scanID != old_scanID:
            self._stopped = True
        if self._stopped:
            return super().unstage()
        self._pilatus_finished()
        msg = BECMessage.FileMessage(
            file_path=self.filepath_h5, done=True, metadata={"input_path": self.destination_path}
        )
        self._producer.set_and_publish(
            MessageEndpoints.public_file(self.scaninfo.scanID, self.name),
            msg.dumps(),
        )
        self._producer.set_and_publish(
            MessageEndpoints.file_event(self.name),
            msg.dumps(),
        )
        logger.info("Pilatus2 done")
        return super().unstage()

    def _pilatus_finished(self) -> None:
        # time.sleep(2)
        while True:
            if self.device_manager.devices.mcs.obj._staged != Staged.yes:
                break
            time.sleep(0.1)
        # time.sleep(2)
        # timer = 0
        # while True:
        #     # rtr = self.cam.status_message_camserver.get()
        #     #if self.cam.acquire.get() == 0 and rtr == "Camserver returned OK":
        #     # if rtr == "Camserver returned OK":
        #     #     break
        #     if self._stopped == True:
        #         break
        #     time.sleep(0.1)
        #     timer += 0.1
        #     if timer > 5:
        #         self._close_file_writer()
        #         self._stop_file_writer()
        #         self._stopped == True
        #         # raise PilatusTimeoutError(
        #         #     f"Pilatus timeout with detector state {self.cam.acquire.get()} and camserver return status: {rtr} "
        #         # )

        self._stop_file_writer()
        time.sleep(2)
        self._close_file_writer()

    def acquire(self) -> None:
        """Start acquisition in software trigger mode,
        or arm the detector in hardware of the detector
        """
        self.cam.acquire.put(1)
        time.sleep(1)

    def stop(self, *, success=False) -> None:
        """Stop the scan, with camera and file writer"""
        self.cam.acquire.put(0)
        self._stop_file_writer()
        # TODO maybe needed
        self._close_file_writer()
        # self.unstage()
        super().stop(success=success)
        self._stopped = True


# Automatically connect to test environmenr if directly invoked
if __name__ == "__main__":
    pilatus_2 = PilatusCsaxs(name="pilatus_2", prefix="X12SA-ES-PILATUS300K:", sim_mode=True)
