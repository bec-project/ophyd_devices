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
    """
    Class for custom detector errors

    Specifying different types of errors can be helpful and used
    for error handling, e.g. scan repetitions.

    An suggestion/example would be to have 3 class types for errors
        - EigerError : base error class for the detector (e.g. Eiger here)
        - EigerTimeoutError(EigerError) : timeout error, inherits from EigerError
        - EigerInitError(EigerError) : initialization error, inherits from EigerError
    """

    pass


class TriggerSource(enum.IntEnum):
    """
    Class for trigger signals

    Here we would map trigger options from EPICS, example  implementation:
    AUTO = 0
    TRIGGER = 1
    GATING = 2
    BURST_TRIGGER = 3

    To set the trigger source to gating, call TriggerSource.Gating
    """
    pass

    

class SLSDetectorBase(ABC, Device):
    """
    Abstract base class for SLS detectors
    """

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
        """
        Update service configuration from BEC SERVICE CONFIG
        """
        self.service_cfg = SERVICE_CONFIG.config["service_config"]["file_writer"]

    def _update_scaninfo(self) -> None:
        """
        Update scaninfo from BecScaninfoMixing
        """
        self.scaninfo = BecScaninfoMixin(self.device_manager, self.sim_mode)
        self.scaninfo.load_scan_metadata()

    def _update_filewriter(self) -> None:
        """
        Update filewriter with service config
        """
        self.filewriter = FileWriterMixin(self.service_cfg)

    @abstractmethod
    def _init(self) -> None:
        """
        Initialize detector & filewriter

        Can also be used to init default parameters

        Internal Calls:
        - _init_detector   : Init detector
        - _init_filewriter : Init file_writer

        """
        self._init_detector()
        self._init_filewriter()
        pass

    @abstractmethod
    def _init_detector(self):
        """
        Init parameters for the detector
        """
        pass

    @abstractmethod
    def _init_filewriter(self):
        """
        Init parameters for filewriter
        """
        pass

        @abstractmethod
    def _set_trigger(self, trigger_source) -> None:
        """
        Set trigger source for the detector

        Args:
            trigger_source (enum.IntEnum): trigger source
        """
        pass

    @abstractmethod
    def _prep_file_writer(self) -> None:
        """
        Prepare file writer for scan
        """
        pass

    @abstractmethod
    def _stop_file_writer(self) -> None:
        """
        Close file writer
        """
        pass

    @abstractmethod
    def _prep_det(self) -> None:
        """
        Prepare detector for scans
        """
        pass

    @abstractmethod
    def _stop_det(self) -> None:
        """
        Stop the detector and wait for the proper status message
        """
        pass

    @abstractmethod
    def _arm_acquisition(self) -> None:
        """Arm detector for acquisition"""
        pass

    @abstractmethod
    def trigger(self) -> None:
        """
        Trigger the detector, called from BEC

        Internal Calls:
        - _on_trigger     : call trigger action
        """
        self._on_trigger()
        pass

    @abstractmethod
    def _on_trigger(self) -> None:
        """
        Specify action that should be taken upon trigger signal
        """
        pass

    @abstractmethod
    def stop(self, *, success=False) -> None:
        """
        Stop the scan, with camera and file writer
        """
        pass

    
