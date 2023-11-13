import enum
from abc import ABC, abstractmethod

from ophyd import Device
from ophyd_devices.utils import bec_utils

from bec_lib.bec_service import SERVICE_CONFIG
from bec_lib.file_utils import FileWriterMixin
from ophyd_devices.epics.devices.bec_scaninfo_mixin import BecScaninfoMixin


# Define here a minimum readout time for the detector
MIN_READOUT = None


# Custom exceptions specific to detectors
class CustomDetectorError(Exception):
    """Class for custom detector errors.

    Specifying different types of errors can be helpful and used
    for error handling, e.g. scan repetitions.

    An suggestion/example would be to have 3 class types for errors
    EigerError, EigerTimeoutError(EigerError), EigerInitError(EigerError)
    """

    pass


class SLSDetectorBase(ABC, Device):
    """Abstract base class for SLS detectors"""

    def __init____init__(
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
    ) -> None:
        super().__init__(
            prefix,
            name=name,
            kind=kind,
            read_attrs=read_attrs,
            configuration_attrs=configuration_attrs,
            parent=parent,
            device_manager=device_manager,
            **kwargs,
        )
        if device_manager is None and not sim_mode:
            raise CustomDetectorError(
                f"No device manager for device: {name}, and not started sim_mode: {sim_mode}. Add DeviceManager to initialization or init with sim_mode=True"
            )
        self.sim_mode = sim_mode
        # TODO check if threadlock is needed for unstage
        self._stopped = False
        self.name = name
        self.service_cfg = None
        self.std_client = None
        self.scaninfo = None
        self.filewriter = None
        self.readout_time_min = MIN_READOUT
        self.timeout = 5
        self.wait_for_connection(all_signals=True)
        if not self.sim_mode:
            self._update_service_cfg()
            self.device_manager = device_manager
        else:
            self.device_manager = bec_utils.DMMock()
            base_path = kwargs["basepath"] if "basepath" in kwargs else "~/Data10/"
            self.service_cfg = {"base_path": os.path.expanduser(base_path)}
        self._producer = self.device_manager.producer
        self._update_scaninfo()
        self._update_filewriter()
        self._init()

    def _update_service_cfg(self) -> None:
        """Update service configuration from BEC SERVICE CONFIG"""
        self.service_cfg = SERVICE_CONFIG.config["service_config"]["file_writer"]

    def _update_scaninfo(self) -> None:
        """Update scaninfo from BecScaninfoMixing"""
        self.scaninfo = BecScaninfoMixin(self.device_manager, self.sim_mode)
        self.scaninfo.load_scan_metadata()

    def _update_filewriter(self) -> None:
        """Update filewriter with service config"""
        self.filewriter = FileWriterMixin(self.service_cfg)

    @abstractmethod
    def _init(self):
        """Initialize detector, filewriter and set default parameters"""
        pass
