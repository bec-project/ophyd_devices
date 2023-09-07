import os

from bec_lib.core import DeviceManagerBase, BECMessage, MessageEndpoints
from bec_lib.core import bec_logger

logger = bec_logger.logger


class BecScaninfoMixin:
    def __init__(self, device_manager: DeviceManagerBase = None, sim_mode=False) -> None:
        self.device_manager = device_manager
        self.sim_mode = sim_mode
        self.scan_msg = None
        self.scanID = None
        self.bec_info_msg = {
            "RID": "mockrid",
            "queueID": "mockqueuid",
            "scan_number": 1,
            "exp_time": 12e-3,
            "num_points": 500,
            "readout_time": 3e-3,
            "scan_type": "fly",
            "num_lines": 1,
            "frames_per_trigger": 1,
        }

    def get_bec_info_msg(self) -> None:
        return self.bec_info_msg

    def change_config(self, bec_info_msg: dict) -> None:
        self.bec_info_msg = bec_info_msg

    def _get_current_scan_msg(self) -> BECMessage.ScanStatusMessage:
        if not self.sim_mode:
            # TODO what if no scan info is there yet!
            msg = self.device_manager.producer.get(MessageEndpoints.scan_status())
            return BECMessage.ScanStatusMessage.loads(msg)

        return BECMessage.ScanStatusMessage(
            scanID="1",
            status={},
            info=self.bec_info_msg,
        )

    def get_username(self) -> str:
        if not self.sim_mode:
            return self.device_manager.producer.get(MessageEndpoints.account()).decode()
        return os.getlogin()

    def load_scan_metadata(self) -> None:
        self.scan_msg = scan_msg = self._get_current_scan_msg()
        logger.info(f"{self.scan_msg}")
        try:
            self.metadata = {
                "scanID": scan_msg.content["scanID"],
                "RID": scan_msg.content["info"]["RID"],
                "queueID": scan_msg.content["info"]["queueID"],
            }
            self.scanID = scan_msg.content["scanID"]
            self.scan_number = scan_msg.content["info"]["scan_number"]
            self.exp_time = scan_msg.content["info"]["exp_time"]
            self.frames_per_trigger = scan_msg.content["info"]["frames_per_trigger"]
            self.num_points = scan_msg.content["info"]["num_points"]
            self.scan_type = scan_msg.content["info"].get("scan_type", "step")
            self.readout_time = scan_msg.content["info"]["readout_time"]
        except Exception as exc:
            logger.error(f"Failed to load scan metadata: {exc}.")

        self.username = self.get_username()
