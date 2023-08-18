import json
import os
import requests
import numpy as np

from typing import List

from ophyd.areadetector import ADComponent as ADCpt, PilatusDetectorCam, DetectorBase
from ophyd.areadetector.plugins import FileBase

from bec_lib.core import BECMessage, MessageEndpoints
from bec_lib.core.file_utils import FileWriterMixin
from bec_lib.core import bec_logger

logger = bec_logger.logger


class PilatusDetectorCamEx(PilatusDetectorCam, FileBase):
    pass


# TODO refactor class -> move away from DetectorBase and PilatusDetectorCamEx class to Device. -> this will be cleaner
class PilatusCsaxs(DetectorBase):
    """

    in device config, device_access needs to be set true to inject the device manager
    """

    _html_docs = ["PilatusDoc.html"]
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
        self.device_manager = device_manager
        self.username = "e21206"  # TODO get from config
        # self.username = self.device_manager.producer.get(MessageEndpoints.account()).decode()
        super().__init__(
            prefix=prefix,
            name=name,
            kind=kind,
            read_attrs=read_attrs,
            configuration_attrs=configuration_attrs,
            parent=parent,
            **kwargs,
        )
        # TODO how to get base_path
        self.service_cfg = {"base_path": f"/sls/X12SA/data/{self.username}/Data10/pilatus_2/"}
        self.filewriter = FileWriterMixin(self.service_cfg)
        self.num_frames = 0
        self.readout = 0.003  # 3 ms
        self.triggermode = 0  # 0 : internal, scan must set this if hardware triggered

    def _get_current_scan_msg(self) -> BECMessage.ScanStatusMessage:
        msg = self.device_manager.producer.get(MessageEndpoints.scan_status())
        return BECMessage.ScanStatusMessage.loads(msg)

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
        # TODO remove
        # self.username = self.device_manager.producer.get(MessageEndpoints.account()).decode()

        # set pilatus threshol
        self._set_threshold()

        # set Epic PVs for filewriting
        self.cam.file_path.set(f"/dev/shm/zmq/")
        self.cam.file_name.set(f"{self.username}_2_{self.scan_number:05d}")
        self.cam.auto_increment.set(1)  # auto increment
        self.cam.file_number.set(0)  # first iter
        self.cam.file_format.set(0)  # 0: TIFF
        self.cam.file_template.set("%s%s_%5.5d.cbf")

        # compile zmq stream for data transfer
        scan_dir = self.filewriter._get_scan_directory(
            scan_bundle=1000, scan_number=self.scan_number, leading_zeros=5
        )
        self.destination_path = os.path.join(
            self.service_cfg["base_path"]
        )  # os.path.join(self.service_cfg["base_path"], scan_dir)

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

        self._set_acquisition_params(
            exp_time=self.exp_time,
            readout=self.readout,
            num_frames=self.num_frames,
            triggermode=self.triggermode,
        )

        return super().stage()

    def unstage(self) -> List[object]:
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
        # Reset triggermode to internal
        self.triggermode = 0

        if not res.ok:
            res.raise_for_status()

        res = requests.delete(url="http://x12sa-pd-2:8080/stream/pilatus_2")
        if not res.ok:
            res.raise_for_status()
        return super().unstage()

    def _set_threshold(self) -> None:
        # TODO readout mono, monitor threshold and set it if mokev is different
        # mokev = self.device_manager.devices.mokev.obj.read()["mokev"]["value"]
        # TODO remove
        mokev = 16
        # TODO refactor naming from name, pilatus_2
        pil_threshold = self.cam.threshold_energy.read()["pilatus_2_cam_threshold_energy"]["value"]
        if not np.isclose(mokev / 2, pil_threshold, rtol=0.05):
            self.cam.threshold_energy.set(mokev / 2)

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
        self.cam.trigger_mode.set(triggermode)

    def acquire(self) -> None:
        self.cam.acquire.set(1)

    def stop(self, *, success=False) -> None:
        self.cam.acquire.set(0)
        self.unstage()
        super().stop(success=success)
        self._stopped = True
