import json
import os
from typing import List
import requests
import numpy as np

from ophyd.areadetector import ADComponent as ADCpt, PilatusDetectorCam, DetectorBase
from ophyd.areadetector.plugins import FileBase

from bec_lib.core import BECMessage, MessageEndpoints, RedisConnector
from bec_lib.core.file_utils import FileWriterMixin
from bec_lib.core import bec_logger


logger = bec_logger.logger


class PilatusDetectorCamEx(PilatusDetectorCam, FileBase):
    pass


class PilatusCsaxs(DetectorBase):
    """Pilatus_2 300k detector for CSAXS

    Parent class: DetectorBase
    Device class: PilatusDetectorCamEx

    Attributes:
        name str: 'eiger'
        prefix (str): PV prefix (X12SA-ES-PILATUS300K:)

    """

    cam = ADCpt(PilatusDetectorCamEx, "cam1:")

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
        self.username = "e21206"
        # TODO once running from BEC
        # self.username = self.device_manager.producer.get(MessageEndpoints.account()).decode()

        self.service_cfg = {"base_path": f"/sls/X12SA/data/{self.username}/Data10/data/"}
        self.filewriter = FileWriterMixin(self.service_cfg)
        self._producer = RedisConnector(["localhost:6379"]).producer()
        self.readout = 0.003  # 3 ms
        self.triggermode = 0  # 0 : internal, scan must set this if hardware triggered

    def _get_current_scan_msg(self) -> BECMessage.ScanStatusMessage:
        msg = self.device_manager.producer.get(MessageEndpoints.scan_status())
        return BECMessage.ScanStatusMessage.loads(msg)

    def _load_scan_metadata(self) -> None:
        scan_msg = self._get_current_scan_msg()
        self.metadata = {
            "scanID": scan_msg.content["scanID"],
            "RID": scan_msg.content["info"]["RID"],
            "queueID": scan_msg.content["info"]["queueID"],
        }
        self.scanID = scan_msg.content["scanID"]
        self.scan_number = scan_msg.content["info"]["scan_number"]
        self.exp_time = scan_msg.content["info"]["exp_time"]
        self.num_frames = scan_msg.content["info"]["num_points"]
        self.username = self.device_manager.producer.get(MessageEndpoints.account()).decode()
        self.device_manager.devices.mokev.read()["mokev"]["value"]
        # self.triggermode = scan_msg.content["info"]["trigger_mode"]
        # self.filename = self.filewriter.compile_full_filename(
        #     self.scan_number, "pilatus_2", 1000, 5, True
        # )
        # TODO fix with BEC running
        # self.filename = '/sls/X12SA/Data10/e21206/data/test.h5'

    def _prep_det(self) -> None:
        # TODO slow reaction, seemed to have timeout.
        self._set_det_threshold()
        self._set_acquisition_params()

    def _set_det_threshold(self) -> None:
        threshold = self.cam.threshold_energy.read()[self.cam.threshold_energy.name]["value"]
        # threshold = self.cam.threshold_energy.read()[self.cam.threshold_energy.name]['value']
        if not np.isclose(self.mokev / 2, threshold, rtol=0.05):
            self.cam.threshold_energy.set(self.mokev / 2)

    def _set_acquisition_params(self) -> None:
        """set acquisition parameters on the detector"""
        self.cam.acquire_time.set(self.exp_time)
        self.cam.acquire_period.set(self.exp_time + self.readout)
        self.cam.num_images.set(self.num_frames)
        self.cam.num_exposures.set(1)
        self.cam.trigger_mode.set(self.triggermode)

    def _prep_file_writer(self) -> None:
        """Prepare the file writer for pilatus_2
        a zmq service is running on xbl-daq-34 that is waiting
        for a zmq message to start the writer for the pilatus_2 x12sa-pd-2
        """
        self.cam.file_path.set(f"/dev/shm/zmq/")
        self.cam.file_name.set(f"{self.username}_2_{self.scan_number:05d}")
        self.cam.auto_increment.set(1)  # auto increment
        self.cam.file_number.set(0)  # first iter
        self.cam.file_format.set(0)  # 0: TIFF
        self.cam.file_template.set("%s%s_%5.5d.cbf")

        # TODO Filewriter Plugin to write cbfs to h5!
        # Pilatus_2 writes cbf files -> where do we like to write those!
        # scan_dir = self.filewriter._get_scan_directory(
        #     scan_bundle=1000, scan_number=self.scan_number, leading_zeros=5
        # ) # os.path.join(self.service_cfg["base_path"], scan_dir)
        self.destination_path = "/sls/X12SA/data/{self.username}/Data10/pilatus_2/"

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

        if not res.ok:
            res.raise_for_status()

        # prepare writer
        data_msg = [
            "zmqWriter",
            self.username,
            {
                "addr": "tcp://x12sa-pd-2:8888",
                "dst": ["file"],
                "numFrm": self.num_frames,
                "timeout": 2000,
                "ifType": "PULL",
                "user": self.username,
            },
        ]

        res = requests.put(
            url="http://xbl-daq-34:8091/pilatus_2/run",
            data=json.dumps(data_msg),
            headers=headers,
        )

        if not res.ok:
            res.raise_for_status()

    def _close_file_writer(self) -> None:
        """Close the file writer for pilatus_2
        a zmq service is running on xbl-daq-34 that is waiting
        for a zmq message to stop the writer for the pilatus_2 x12sa-pd-2
        """
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        data_msg = [
            "zmqWriter",
            self.username,
            {
                "frmCnt": self.num_frames,
                "timeout": 2000,
            },
        ]
        logger.info(data_msg)

        res = requests.put(
            url="http://xbl-daq-34:8091/pilatus_2/wait",
            data=json.dumps(data_msg),
            headers=headers,
        )

        if not res.ok:
            res.raise_for_status()

        res = requests.delete(url="http://x12sa-pd-2:8080/stream/pilatus_2")
        if not res.ok:
            res.raise_for_status()

    def stage(self) -> List[object]:
        """stage the detector and file writer"""
        # TODO remove once running from BEC
        # self._load_scan_metadata()
        self.scan_number = 10
        self.exp_time = 0.5
        self.num_frames = 3
        self.mokev = 12

        self._prep_det()
        self._prep_file_writer()

        # msg = BECMessage.FileMessage(file_path=self.filename, done=False)
        # self._producer.set_and_publish(
        #     MessageEndpoints.public_file(self.scanID, "pilatus_2"),
        #     msg.dumps(),
        # )

        return super().stage()

    def unstage(self) -> List[object]:
        """unstage the detector and file writer"""
        # Reset to software trigger
        self.triggermode = 0
        self._close_file_writer()
        # TODO check if acquisition is done and successful!
        state = True
        # msg = BECMessage.FileMessage(file_path=self.filepath, done=True, successful=state)
        # self.producer.set_and_publish(
        #     MessageEndpoints.public_file(self.metadata["scanID"], self.name),
        #     msg.dumps(),
        # )
        return super().unstage()

    def acquire(self) -> None:
        """Start acquisition in software trigger mode,
        or arm the detector in hardware of the detector
        """
        self.cam.acquire.set(1)

    def stop(self, *, success=False) -> None:
        """Stop the scan, with camera and file writer"""
        self.cam.acquire.set(0)
        self.unstage()
        super().stop(success=success)
        self._stopped = True


# Automatically connect to test environmenr if directly invoked
if __name__ == "__main__":
    pilatus_2 = PilatusCsaxs(name="pilatus_2", prefix="X12SA-ES-PILATUS300K:", sim_mode=True)
    pilatus_2.stage()
