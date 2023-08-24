import os

from bec_lib.core import DeviceManagerBase, BECMessage, MessageEndpoints


class BecScaninfoMixin:
    def __init__(self, device_manager: DeviceManagerBase = None, sim_mode=False) -> None:
        self.device_manager = device_manager
        self.sim_mode = sim_mode

    def _get_current_scan_msg(self) -> BECMessage.ScanStatusMessage:
        if not self.sim_mode:
            msg = self.device_manager.producer.get(MessageEndpoints.scan_status())
            return BECMessage.ScanStatusMessage.loads(msg)

        return BECMessage.ScanStatusMessage(
            scanID="1",
            status={},
            info={
                "RID": "mockrid",
                "queueID": "mockqueuid",
                "scan_number": 1,
                "exp_time": 0.1,
                "num_points": 10,
                "readout_time": 3e-3,
                "scan_type": "fly",
            },
        )

    def _get_username(self) -> str:
        if not self.sim_mode:
            return self.device_manager.producer.get(MessageEndpoints.account()).decode()
        return os.getlogin()

    def load_scan_metadata(self) -> None:
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
        self.scan_type = scan_msg.content["info"].get("scan_type", "step")
        self.readout_time = scan_msg.content["info"]["readout_time"]
        self.username = self._get_username()
