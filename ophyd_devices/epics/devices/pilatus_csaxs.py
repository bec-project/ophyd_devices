import enum
import json
import os
import time
import requests
import numpy as np

from typing import List

from ophyd import EpicsSignal, EpicsSignalRO, EpicsSignalWithRBV
from ophyd import DetectorBase, Device, Staged
from ophyd import ADComponent as ADCpt

from bec_lib import messages, MessageEndpoints, bec_logger
from bec_lib.file_utils import FileWriterMixin
from bec_lib.bec_service import SERVICE_CONFIG
from bec_lib.devicemanager import DeviceStatus

from ophyd_devices.utils import bec_utils as bec_utils
from ophyd_devices.epics.devices.bec_scaninfo_mixin import BecScaninfoMixin

logger = bec_logger.logger

PILATUS_MIN_READOUT = 3e-3


class PilatusError(Exception):
    """Base class for exceptions in this module."""

    pass


class PilatusTimeoutError(PilatusError):
    """Raised when the Pilatus does not respond in time during unstage."""

    pass


class PilatusInitError(PilatusError):
    """Raised when initiation of the device class fails,
    due to missing device manager or not started in sim_mode."""

    pass


class TriggerSource(enum.IntEnum):
    INTERNAL = 0
    EXT_ENABLE = 1
    EXT_TRIGGER = 2
    MULTI_TRIGGER = 3
    ALGINMENT = 4


class SLSDetectorCam(Device):
    """SLS Detector Camera - Pilatus

    Base class to map EPICS PVs to ophyd signals.
    """

    num_images = ADCpt(EpicsSignalWithRBV, "NumImages")
    num_frames = ADCpt(EpicsSignalWithRBV, "NumExposures")
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


class PilatuscSAXS(DetectorBase):
    """Pilatus_2 300k detector for CSAXS

    Parent class: DetectorBase
    Device class: PilatusDetectorCamEx

    Attributes:
        name str: 'pilatus_2'
        prefix (str): PV prefix (X12SA-ES-PILATUS300K:)

    """

    # Specify which functions are revealed to the user in BEC client
    USER_ACCESS = [
        "describe",
    ]

    cam = ADCpt(SLSDetectorCam, "cam1:")

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
        """Initialize the Pilatus detector
        Args:
        #TODO add here the parameters for kind, read_attrs, configuration_attrs, parent
            prefix (str): PV prefix ("X12SA-ES-PILATUS300K:)
            name (str): 'pilatus_2'
            kind (str):
            read_attrs (list):
            configuration_attrs (list):
            parent (object):
            device_manager (object): BEC device manager
            sim_mode (bool): simulation mode to start the detector without BEC, e.g. from ipython shell
        """
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
            raise PilatusInitError(
                f"No device manager for device: {name}, and not started sim_mode: {sim_mode}. Add DeviceManager to initialization or init with sim_mode=True"
            )
        self.sim_mode = sim_mode
        self._stopped = False
        self.name = name
        self.service_cfg = None
        self.std_client = None
        self.scaninfo = None
        self.filewriter = None
        self.readout_time_min = PILATUS_MIN_READOUT
        self.timeout = 5
        self.wait_for_connection(all_signals=True)
        if not sim_mode:
            self._update_service_config()
            self.device_manager = device_manager
        else:
            self.device_manager = bec_utils.DMMock()
            base_path = kwargs["basepath"] if "basepath" in kwargs else "~/Data10/"
            self.service_cfg = {"base_path": os.path.expanduser(base_path)}
        self._producer = self.device_manager.producer
        self._update_scaninfo()
        self._update_filewriter()
        self._init()

    def _update_filewriter(self) -> None:
        """Update filewriter with service config"""
        self.filewriter = FileWriterMixin(self.service_cfg)

    def _update_scaninfo(self) -> None:
        """Update scaninfo from BecScaninfoMixing
        This depends on device manager and operation/sim_mode
        """
        self.scaninfo = BecScaninfoMixin(self.device_manager, self.sim_mode)
        self.scaninfo.load_scan_metadata()

    def _update_service_config(self) -> None:
        """Update service config from BEC service config"""
        self.service_cfg = SERVICE_CONFIG.config["service_config"]["file_writer"]

    def _init(self) -> None:
        """Initialize detector, filewriter and set default parameters"""
        self._default_parameter()
        self._init_detector()
        self._init_filewriter()

    def _default_parameter(self) -> None:
        """Set default parameters for Pilatus300k detector
        readout (float): readout time in seconds
        """
        self._update_readout_time()

    def _update_readout_time(self) -> None:
        readout_time = (
            self.scaninfo.readout_time
            if hasattr(self.scaninfo, "readout_time")
            else self.readout_time_min
        )
        self.readout_time = max(readout_time, self.readout_time_min)

    def _init_detector(self) -> None:
        """Initialize the detector"""
        # TODO add check if detector is running
        self._stop_det()
        self._set_trigger(TriggerSource.EXT_ENABLE)

    def _init_filewriter(self) -> None:
        """Initialize the file writer"""
        # TODO in case the data backend is rewritten, add check if it is ready!
        pass

    def _prep_det(self) -> None:
        # TODO slow reaction, seemed to have timeout.
        self._set_det_threshold()
        self._set_acquisition_params()
        self._set_trigger(TriggerSource.EXT_ENABLE)

    def _set_det_threshold(self) -> None:
        # threshold_energy PV exists on Eiger 9M?
        factor = 1
        unit = getattr(self.cam.threshold_energy, "units", None)
        if unit != None and unit == "eV":
            factor = 1000
        setpoint = int(self.mokev * factor)
        threshold = self.cam.threshold_energy.read()[self.cam.threshold_energy.name]["value"]
        if not np.isclose(setpoint / 2, threshold, rtol=0.05):
            self.cam.threshold_energy.put(setpoint / 2)

    def _set_acquisition_params(self) -> None:
        """set acquisition parameters on the detector"""
        # self.cam.acquire_time.set(self.exp_time)
        # self.cam.acquire_period.set(self.exp_time + self.readout)
        self.cam.num_images.put(int(self.scaninfo.num_points * self.scaninfo.frames_per_trigger))
        self.cam.num_frames.put(1)
        self._update_readout_time()

    def _set_trigger(self, trigger_source: int) -> None:
        """Set trigger source for the detector, either directly to value or TriggerSource.* with
        INTERNAL = 0
        EXT_ENABLE = 1
        EXT_TRIGGER = 2
        MULTI_TRIGGER = 3
        ALGINMENT = 4
        """
        value = trigger_source
        self.cam.trigger_mode.put(value)

    def _create_directory(filepath: str) -> None:
        """Create directory if it does not exist"""
        os.makedirs(filepath, exist_ok=True)

    def _prep_file_writer(self) -> None:
        """
        Prepare the file writer for pilatus_2

        A zmq service is running on xbl-daq-34 that is waiting
        for a zmq message to start the writer for the pilatus_2 x12sa-pd-2

        """
        # TODO explore required sleep time here
        self._close_file_writer()
        time.sleep(0.1)
        self._stop_file_writer()
        time.sleep(0.1)

        self.filepath_raw = self.filewriter.compile_full_filename(
            self.scaninfo.scan_number, "pilatus_2.h5", 1000, 5, True
        )
        self.cam.file_path.put(f"/dev/shm/zmq/")
        self.cam.file_name.put(f"{self.scaninfo.username}_2_{self.scaninfo.scan_number:05d}")
        self.cam.auto_increment.put(1)  # auto increment
        self.cam.file_number.put(0)  # first iter
        self.cam.file_format.put(0)  # 0: TIFF
        self.cam.file_template.put("%s%s_%5.5d.cbf")

        # TODO remove hardcoded filepath here
        # compile filename
        basepath = f"/sls/X12SA/data/{self.scaninfo.username}/Data10/pilatus_2/"
        self.filepath = os.path.join(
            basepath,
            self.filewriter.get_scan_directory(self.scaninfo.scan_number, 1000, 5),
        )
        # Make directory if needed
        self._create_directory(self.filepath)

        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        # start the stream on x12sa-pd-2
        url = "http://x12sa-pd-2:8080/stream/pilatus_2"
        data_msg = {
            "source": [
                {
                    "searchPath": "/",
                    "searchPattern": "glob:*.cbf",
                    "destinationPath": self.filepath,
                }
            ]
        }
        res = self._send_requests_put(url=url, data=data_msg, headers=headers)
        logger.info(f"{res.status_code} -  {res.text} - {res.content}")

        if not res.ok:
            res.raise_for_status()

        # start the data receiver on xbl-daq-34
        url = "http://xbl-daq-34:8091/pilatus_2/run"
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
        res = self._send_requests_put(url=url, data=data_msg, headers=headers)
        logger.info(f"{res.status_code}  - {res.text} - {res.content}")

        if not res.ok:
            res.raise_for_status()

        # Wait for server to become available again
        time.sleep(0.1)
        logger.info(f"{res.status_code} -{res.text} - {res.content}")

        # Sent requests.put to xbl-daq-34 to wait for data
        url = "http://xbl-daq-34:8091/pilatus_2/wait"
        data_msg = [
            "zmqWriter",
            self.scaninfo.username,
            {
                "frmCnt": int(self.scaninfo.num_points * self.scaninfo.frames_per_trigger),
                "timeout": 2000,
            },
        ]
        try:
            res = self._send_requests_put(url=url, data=data_msg, headers=headers)
            logger.info(f"{res}")

            if not res.ok:
                res.raise_for_status()
        except Exception as exc:
            logger.info(f"Pilatus2 wait threw Exception: {exc}")

    def _send_requests_put(self, url: str, data_msg: list = None, headers: dict = None) -> object:
        """
        Send a put request to the given url

        Args:
            url (str): url to send the request to
            data (dict): data to be sent with the request (optional)
            headers (dict): headers to be sent with the request (optional)

        Returns:
            status code of the request
        """
        return requests.put(url=url, data=json.dumps(data_msg), headers=headers)

    def _send_requests_delete(self, url: str, headers: dict = None) -> object:
        """
        Send a delete request to the given url

        Args:
            url (str): url to send the request to
            headers (dict): headers to be sent with the request (optional)

        Returns:
            status code of the request
        """
        return requests.delete(url=url, headers=headers)

    def _close_file_writer(self) -> None:
        """
        Close the file writer for pilatus_2

        Delete the data from x12sa-pd-2

        """
        url = "http://x12sa-pd-2:8080/stream/pilatus_2"
        try:
            res = self._send_requests_delete(url=url)
            if not res.ok:
                res.raise_for_status()
        except Exception as exc:
            logger.info(f"Pilatus2 close threw Exception: {exc}")

    def _stop_file_writer(self) -> None:
        """
        Stop the file writer for pilatus_2

        Runs on xbl-daq-34
        """
        url = "http://xbl-daq-34:8091/pilatus_2/stop"
        res = self._send_requests_put(url=url)
        if not res.ok:
            res.raise_for_status()

    def stage(self) -> List[object]:
        """Stage command, called from BEC in preparation of a scan.
        This will iniate the preparation of detector and file writer.
        The following functuions are called:
            - _prep_file_writer
            - _prep_det
            - _publish_file_location

        The device returns a List[object] from the Ophyd Device class.

        #TODO make sure this is fullfiled

        Staging not idempotent and should raise
        :obj:`RedundantStaging` if staged twice without an
        intermediate :meth:`~BlueskyInterface.unstage`.
        """
        self._stopped = False
        self.scaninfo.load_scan_metadata()
        self.mokev = self.device_manager.devices.mokev.obj.read()[
            self.device_manager.devices.mokev.name
        ]["value"]
        # TODO refactor logger.info to DEBUG mode?
        self._prep_file_writer()
        self._prep_det()
        state = False
        self._publish_file_location(done=state)
        return super().stage()

    # TODO might be useful for base class
    def pre_scan(self) -> None:
        """Pre_scan is an (optional) function that is executed by BEC just before the scan core

        For the pilatus detector, it is used to arm the detector for the acquisition,
        because the detector times out after ˜7-8seconds without seeing a trigger.
        """
        self._arm_acquisition()

    def _arm_acquisition(self) -> None:
        self.cam.acquire.put(1)
        # TODO check if sleep of 1s is needed, could be that less is enough
        time.sleep(1)

    def _publish_file_location(self, done: bool = False, successful: bool = None) -> None:
        """Publish the filepath to REDIS.
        We publish two events here:
        - file_event: event for the filewriter
        - public_file: event for any secondary service (e.g. radial integ code)

        Args:
            done (bool): True if scan is finished
            successful (bool): True if scan was successful

        """
        pipe = self._producer.pipeline()
        if successful is None:
            msg = messages.FileMessage(file_path=self.filepath, done=done)
        else:
            msg = messages.FileMessage(file_path=self.filepath, done=done, successful=successful)
        self._producer.set_and_publish(
            MessageEndpoints.public_file(self.scaninfo.scanID, self.name), msg.dumps(), pipe=pipe
        )
        self._producer.set_and_publish(
            MessageEndpoints.file_event(self.name), msg.dumps(), pipe=pipe
        )
        pipe.execute()

    # TODO function for abstract class?
    def trigger(self) -> DeviceStatus:
        """Trigger the detector, called from BEC."""
        self._on_trigger()
        return super().trigger()

    # TODO function for abstract class?
    def _on_trigger(self):
        """Specify action that should be taken upon trigger signal."""
        pass

    def unstage(self) -> List[object]:
        """Unstage the device.

        This method must be idempotent, multiple calls (without a new
        call to 'stage') have no effect.

        Functions called:
            - _finished
            - _publish_file_location
        """
        old_scanID = self.scaninfo.scanID
        self.scaninfo.load_scan_metadata()
        logger.info(f"Old scanID: {old_scanID}, ")
        if self.scaninfo.scanID != old_scanID:
            self._stopped = True
        if self._stopped:
            return super().unstage()
        self._finished()
        state = True
        self._publish_file_location(done=state, successful=state)
        self._start_h5converter(done=state)
        return super().unstage()

    def _start_h5converter(self, done=False) -> None:
        """Start the h5converter"""
        msg = messages.FileMessage(
            file_path=self.filepath_raw, done=done, metadata={"input_path": self.filepath}
        )
        self._producer.set_and_publish(
            MessageEndpoints.public_file(self.scaninfo.scanID, self.name), msg.dumps()
        )

    def _finished(self) -> None:
        """Check if acquisition is finished.

        This function is called from unstage and stop
        and will check detector and file backend status.
        Timeouts after given time

        Functions called:
            - _stop_det
            - _stop_file_writer
        """
        timer = 0
        sleep_time = 0.1
        # TODO this is a workaround at the moment which relies on the status of the mcs device
        while True:
            if self.device_manager.devices.mcs.obj._staged != Staged.yes:
                break
            if self._stopped == True:
                break
            time.sleep(sleep_time)
            timer = timer + sleep_time
            if timer > self.timeout:
                self._stopped == True
                self._stop_det()
                self._stop_file_writer()
                # TODO explore if sleep is needed
                time.sleep(0.5)
                self._close_file_writer()
                raise PilatusTimeoutError(f"Timeout waiting for mcs device to unstage")

        self._stop_det()
        self._stop_file_writer()
        # TODO explore if sleep time  is needed
        time.sleep(0.5)
        self._close_file_writer()

    def _stop_det(self) -> None:
        """Stop the detector"""
        self.cam.acquire.put(0)

    def stop(self, *, success=False) -> None:
        """Stop the scan, with camera and file writer"""
        self._stop_det()
        self._stop_file_writer()
        self._close_file_writer()
        super().stop(success=success)
        self._stopped = True


# Automatically connect to test environmenr if directly invoked
if __name__ == "__main__":
    pilatus_2 = PilatuscSAXS(name="pilatus_2", prefix="X12SA-ES-PILATUS300K:", sim_mode=True)
