import enum
import json
import os
import time
from typing import List
import requests
import numpy as np

from ophyd.areadetector import ADComponent as ADCpt, PilatusDetectorCam, DetectorBase
from ophyd.areadetector.plugins import FileBase
from ophyd_devices.utils import bec_utils as bec_utils

from bec_lib.core import BECMessage, MessageEndpoints, RedisConnector
from bec_lib.core.file_utils import FileWriterMixin
from bec_lib.core import bec_logger


from ophyd_devices.epics.devices.bec_scaninfo_mixin import BecScaninfoMixin

logger = bec_logger.logger


class PilatusError(Exception):
    pass


class PilatusDetectorCamEx(PilatusDetectorCam, FileBase):
    pass


class TriggerSource(int, enum.Enum):
    INTERNAL = 0
    EXT_ENABLE = 1
    EXT_TRIGGER = 2
    MULTI_TRIGGER = 3
    ALGINMENT = 4


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
        self.filepath = ""

        self.filewriter = FileWriterMixin(self.service_cfg)
        self.readout = 1e-3  # 3 ms

    def _get_current_scan_msg(self) -> BECMessage.ScanStatusMessage:
        msg = self.device_manager.producer.get(MessageEndpoints.scan_status())
        return BECMessage.ScanStatusMessage.loads(msg)

    # def _load_scan_metadata(self) -> None:
    #     scan_msg = self._get_current_scan_msg()
    #     self.metadata = {
    #         "scanID": scan_msg.content["scanID"],
    #         "RID": scan_msg.content["info"]["RID"],
    #         "queueID": scan_msg.content["info"]["queueID"],
    #     }
    #     self.scanID = scan_msg.content["scanID"]
    #     self.scan_number = scan_msg.content["info"]["scan_number"]
    #     self.exp_time = scan_msg.content["info"]["exp_time"]
    #     self.num_frames = scan_msg.content["info"]["num_points"]
    #     self.username = self.device_manager.producer.get(
    #         MessageEndpoints.account()
    #     ).decode()
    #     self.device_manager.devices.mokev.read()["mokev"]["value"]
    #     # self.triggermode = scan_msg.content["info"]["trigger_mode"]
    #     # self.filename = self.filewriter.compile_full_filename(
    #     #     self.scan_number, "pilatus_2", 1000, 5, True
    #     # )
    #     # TODO fix with BEC running
    #     # self.filename = '/sls/X12SA/Data10/e21206/data/test.h5'

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
        self._set_trigger(TriggerSource.INTERNAL)  # EXT_TRIGGER)

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
        self.filepath_h5 = self.filewriter.compile_full_filename(
            self.scaninfo.scan_number, "pilatus_2.h5", 1000, 5, True
        )
        self.cam.file_path.set(f"/dev/shm/zmq/")
        self.cam.file_name.set(f"{self.scaninfo.username}_2_{self.scaninfo.scan_number:05d}")
        self.cam.auto_increment.set(1)  # auto increment
        self.cam.file_number.set(0)  # first iter
        self.cam.file_format.set(0)  # 0: TIFF
        self.cam.file_template.set("%s%s_%5.5d.cbf")

        # compile filename
        basepath = f"/sls/X12SA/data/{self.scaninfo.username}/Data10/pilatus_2/"
        self.destination_path = os.path.join(
            basepath,
            self.filewriter.get_scan_directory(self.scaninfo.scan_number, 1000, 5),
        )
        # Make directory if needed
        os.makedirs(os.path.dirname(self.destination_path), exist_ok=True)

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
            logger.info("exc")

    def _close_file_writer(self) -> None:
        """Close the file writer for pilatus_2
        a zmq service is running on xbl-daq-34 that is waiting
        for a zmq message to stop the writer for the pilatus_2 x12sa-pd-2
        """

        res = requests.delete(url="http://x12sa-pd-2:8080/stream/pilatus_2")
        if not res.ok:
            res.raise_for_status()

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
        self.scaninfo.load_scan_metadata()
        self.mokev = self.device_manager.devices.mokev.obj.read()[
            self.device_manager.devices.mokev.name
        ]["value"]

        self._prep_det()
        self._prep_file_writer()
        self.acquire()

        return super().stage()

    def unstage(self) -> List[object]:
        """unstage the detector and file writer"""
        # Reset to software trigger
        self.triggermode = 0
        self._close_file_writer()
        self._stop_file_writer()
        # Only sent this out once data is written to disk since cbf to hdf5 converter will be triggered
        msg = BECMessage.FileMessage(file_path=self.filepath, done=True)
        self._producer.set_and_publish(
            MessageEndpoints.public_file(self.scaninfo.scanID, self.name),
            msg.dumps(),
        )
        msg = BECMessage.FileMessage(file_path=self.filepath, done=True)
        self._producer.set_and_publish(
            MessageEndpoints.file_event(self.name),
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
        self._stop_file_writer()
        # self.unstage()
        super().stop(success=success)
        self._stopped = True


# Automatically connect to test environmenr if directly invoked
if __name__ == "__main__":
    pilatus_2 = PilatusCsaxs(name="pilatus_2", prefix="X12SA-ES-PILATUS300K:", sim_mode=True)
    pilatus_2.stage()
