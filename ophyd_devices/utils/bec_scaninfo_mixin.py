import getpass

from bec_lib import bec_logger, messages
from bec_lib.devicemanager import DeviceManagerBase
from bec_lib.endpoints import MessageEndpoints

from ophyd_devices.utils.bec_utils import DMMock

logger = bec_logger.logger


class BECInfoMsgMock:
    """Mock BECInfoMsg class

    This class is used for mocking BECInfoMsg for testing purposes
    """

    def __init__(
        self,
        mockrid: str = "mockrid1111",
        mockqueueid: str = "mockqueue_id111",
        scan_number: int = 1,
        exp_time: float = 15e-3,
        num_points: int = 500,
        readout_time: float = 3e-3,
        scan_type: str = "fly",
        num_lines: int = 1,
        frames_per_trigger: int = 1,
    ) -> None:
        self.mockrid = mockrid
        self.mockqueueid = mockqueueid
        self.scan_number = scan_number
        self.exp_time = exp_time
        self.num_points = num_points
        self.readout_time = readout_time
        self.scan_type = scan_type
        self.num_lines = num_lines
        self.frames_per_trigger = frames_per_trigger

    def get_bec_info_msg(self) -> dict:
        """Get BECInfoMsg object"""
        info_msg = {
            "RID": self.mockrid,
            "queue_id": self.mockqueueid,
            "scan_number": self.scan_number,
            "exp_time": self.exp_time,
            "num_points": self.num_points,
            "readout_time": self.readout_time,
            "scan_type": self.scan_type,
            "num_lines": self.exp_time,
            "frames_per_trigger": self.frames_per_trigger,
        }

        return info_msg


class BecScaninfoMixin:
    """BecScaninfoMixin class

    Args:
        device_manager (DeviceManagerBase): DeviceManagerBase object
        sim_mode (bool): Simulation mode flag
        bec_info_msg (dict): BECInfoMsg object
    Returns:
        BecScaninfoMixin: BecScaninfoMixin object
    """

    def __init__(self, device_manager: DeviceManagerBase = None, bec_info_msg=None) -> None:
        self.sim_mode = bool(isinstance(device_manager, DMMock))
        self.device_manager = device_manager
        self.scan_msg = None
        self.scan_id = None
        if bec_info_msg is None:
            infomsgmock = BECInfoMsgMock()
            self.bec_info_msg = infomsgmock.get_bec_info_msg()
        else:
            self.bec_info_msg = bec_info_msg

        self.metadata = None
        self.scan_id = None
        self.scan_number = None
        self.exp_time = None
        self.frames_per_trigger = None
        self.num_points = None
        self.scan_type = None

    def get_bec_info_msg(self) -> None:
        """Get BECInfoMsg object"""
        return self.bec_info_msg

    def change_config(self, bec_info_msg: dict) -> None:
        """Change BECInfoMsg object"""
        self.bec_info_msg = bec_info_msg

    def _get_current_scan_msg(self) -> messages.ScanStatusMessage:
        """Get current scan message

        Returns:
            messages.ScanStatusMessage: messages.ScanStatusMessage object
        """
        if not self.sim_mode:
            msg = self.device_manager.connector.get(MessageEndpoints.scan_status())
            if not isinstance(msg, messages.ScanStatusMessage):
                return None
            return msg

        return messages.ScanStatusMessage(scan_id="1", status="open", info=self.bec_info_msg)

    def get_username(self) -> str:
        """Get username"""
        if self.sim_mode:
            return getpass.getuser()

        msg = self.device_manager.connector.get(MessageEndpoints.account())
        if msg:
            return msg
        return getpass.getuser()

    def load_scan_metadata(self) -> None:
        """Load scan metadata

        This function loads scan metadata from the current scan message
        """
        self.scan_msg = scan_msg = self._get_current_scan_msg()
        try:
            logger.info(f"Received scan msg for {self.scan_msg.content['scan_id']}")
            self.metadata = {
                "scan_id": scan_msg.content["scan_id"],
                "RID": scan_msg.content["info"]["RID"],
                "queue_id": scan_msg.content["info"]["queue_id"],
            }
            self.scan_id = scan_msg.content["scan_id"]
            self.scan_number = scan_msg.content["info"]["scan_number"]
            self.exp_time = scan_msg.content["info"]["exp_time"]
            self.frames_per_trigger = scan_msg.content["info"]["frames_per_trigger"]
            self.num_points = scan_msg.content["info"]["num_points"]
            self.scan_type = scan_msg.content["info"].get("scan_type", "step")
            self.readout_time = scan_msg.content["info"]["readout_time"]
        except Exception as exc:
            logger.error(f"Failed to load scan metadata: {exc}.")

        self.username = self.get_username()
