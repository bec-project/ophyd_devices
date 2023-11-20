import enum
import json
import os
import time
import requests
import numpy as np

from ophyd import EpicsSignal, EpicsSignalRO, EpicsSignalWithRBV
from ophyd import Device, Staged
from ophyd import ADComponent as ADCpt

from bec_lib import messages, MessageEndpoints, bec_logger

from ophyd_devices.epics.devices.psi_detector_base import PSIDetectorBase, CustomDetectorMixin

logger = bec_logger.logger

MIN_READOUT = 3e-3


class PilatusError(Exception):
    """Base class for exceptions in this module."""


class PilatusTimeoutError(PilatusError):
    """Raised when the Pilatus does not respond in time during unstage."""


class TriggerSource(enum.IntEnum):
    """Trigger source options for the detector"""

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


class PilatusSetup(CustomDetectorMixin):
    """Pilatus setup class for cSAXS

    Parent class: CustomDetectorMixin

    """

    def initialize_default_parameter(self) -> None:
        """Set default parameters for Eiger9M detector"""
        self.update_readout_time()

    def update_readout_time(self) -> None:
        """Set readout time for Eiger9M detector"""
        readout_time = (
            self.parent.scaninfo.readout_time
            if hasattr(self.parent.scaninfo, "readout_time")
            else self.parent.MIN_READOUT
        )
        self.parent.readout_time = max(readout_time, self.parent.MIN_READOUT)

    def initialize_detector(self) -> None:
        """Initialize detector"""
        # Stops the detector
        self.stop_detector()
        # Sets the trigger source to GATING
        self.parent.set_trigger(TriggerSource.EXT_ENABLE)

    def prepare_detector(self) -> None:
        """
        Prepare detector for scan.

        Includes checking the detector threshold,
        setting the acquisition parameters and setting the trigger source
        """
        self.set_detector_threshold()
        self.set_acquisition_params()
        self.parent.set_trigger(TriggerSource.EXT_ENABLE)

    def set_detector_threshold(self) -> None:
        """
        Set correct detector threshold to 1/2 of current X-ray energy, allow 5% tolerance

        Threshold might be in ev or keV
        """

        # get current beam energy from device manageer
        mokev = self.parent.device_manager.devices.mokev.obj.read()[
            self.parent.device_manager.devices.mokev.name
        ]["value"]
        factor = 1

        # Check if energies are eV or keV, assume keV as the default
        unit = getattr(self.parent.cam.threshold_energy, "units", None)
        if unit is not None and unit == "eV":
            factor = 1000

        # set energy on detector
        setpoint = int(mokev * factor)

        # set threshold on detector
        threshold = self.parent.cam.threshold_energy.read()[self.parent.cam.threshold_energy.name][
            "value"
        ]
        if not np.isclose(setpoint / 2, threshold, rtol=0.05):
            self.parent.cam.threshold_energy.set(setpoint / 2)

    def set_acquisition_params(self) -> None:
        """Set acquisition parameters for the detector"""

        # Set number of images and frames (frames is for internal burst of detector)
        self.parent.cam.num_images.put(
            int(self.parent.scaninfo.num_points * self.parent.scaninfo.frames_per_trigger)
        )
        self.parent.cam.num_frames.put(1)

        # Update the readout time of the detector
        self.update_readout_time()

    def create_directory(self, filepath: str) -> None:
        """Create directory if it does not exist"""
        os.makedirs(filepath, exist_ok=True)

    def stop_detector_backend(self) -> None:
        """Stop the file writer zmq service for pilatus_2"""
        self.close_file_writer()
        time.sleep(0.1)
        self.stop_file_writer()
        time.sleep(0.1)

    def close_file_writer(self) -> None:
        """
        Close the file writer for pilatus_2

        Delete the data from x12sa-pd-2

        """
        url = "http://x12sa-pd-2:8080/stream/pilatus_2"
        try:
            res = self.send_requests_delete(url=url)
            if not res.ok:
                res.raise_for_status()
        except Exception as exc:
            logger.info(f"Pilatus2 close threw Exception: {exc}")

    def stop_file_writer(self) -> None:
        """
        Stop the file writer for pilatus_2

        Runs on xbl-daq-34
        """
        url = "http://xbl-daq-34:8091/pilatus_2/stop"
        res = self.send_requests_put(url=url)
        if not res.ok:
            res.raise_for_status()

    def prepare_data_backend(self) -> None:
        """
        Prepare the detector backend of pilatus for a scan

        A zmq service is running on xbl-daq-34 that is waiting
        for a zmq message to start the writer for the pilatus_2 x12sa-pd-2

        """

        self.stop_detector_backend()

        self.parent.filepath = self.parent.filewriter.compile_full_filename(
            self.parent.scaninfo.scan_number, "pilatus_2.h5", 1000, 5, True
        )
        self.parent.cam.file_path.put("/dev/shm/zmq/")
        self.parent.cam.file_name.put(
            f"{self.parent.scaninfo.username}_2_{self.parent.scaninfo.scan_number:05d}"
        )
        self.parent.cam.auto_increment.put(1)  # auto increment
        self.parent.cam.file_number.put(0)  # first iter
        self.parent.cam.file_format.put(0)  # 0: TIFF
        self.parent.cam.file_template.put("%s%s_%5.5d.cbf")

        # TODO better to remove hard coded path with link to home directory/pilatus_2
        basepath = f"/sls/X12SA/data/{self.parent.scaninfo.username}/Data10/pilatus_2/"
        self.parent.filepath_raw = os.path.join(
            basepath,
            self.parent.filewriter.get_scan_directory(self.parent.scaninfo.scan_number, 1000, 5),
        )
        # Make directory if needed
        self.create_directory(self.parent.filepath_raw)

        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        # start the stream on x12sa-pd-2
        url = "http://x12sa-pd-2:8080/stream/pilatus_2"
        data_msg = {
            "source": [
                {
                    "searchPath": "/",
                    "searchPattern": "glob:*.cbf",
                    "destinationPath": self.parent.filepath_raw,
                }
            ]
        }
        res = self.send_requests_put(url=url, data=data_msg, headers=headers)
        logger.info(f"{res.status_code} -  {res.text} - {res.content}")

        if not res.ok:
            res.raise_for_status()

        # start the data receiver on xbl-daq-34
        url = "http://xbl-daq-34:8091/pilatus_2/run"
        data_msg = [
            "zmqWriter",
            self.parent.scaninfo.username,
            {
                "addr": "tcp://x12sa-pd-2:8888",
                "dst": ["file"],
                "numFrm": int(
                    self.parent.scaninfo.num_points * self.parent.scaninfo.frames_per_trigger
                ),
                "timeout": 2000,
                "ifType": "PULL",
                "user": self.parent.scaninfo.username,
            },
        ]
        res = self.send_requests_put(url=url, data=data_msg, headers=headers)
        logger.info(f"{res.status_code}  - {res.text} - {res.content}")

        if not res.ok:
            res.raise_for_status()

        # Wait for server to become available again
        time.sleep(0.1)
        logger.info(f"{res.status_code} -{res.text} - {res.content}")

        # Send requests.put to xbl-daq-34 to wait for data
        url = "http://xbl-daq-34:8091/pilatus_2/wait"
        data_msg = [
            "zmqWriter",
            self.parent.scaninfo.username,
            {
                "frmCnt": int(
                    self.parent.scaninfo.num_points * self.parent.scaninfo.frames_per_trigger
                ),
                "timeout": 2000,
            },
        ]
        try:
            res = self.send_requests_put(url=url, data=data_msg, headers=headers)
            logger.info(f"{res}")

            if not res.ok:
                res.raise_for_status()
        except Exception as exc:
            logger.info(f"Pilatus2 wait threw Exception: {exc}")

    def send_requests_put(self, url: str, data: list = None, headers: dict = None) -> object:
        """
        Send a put request to the given url

        Args:
            url (str): url to send the request to
            data (dict): data to be sent with the request (optional)
            headers (dict): headers to be sent with the request (optional)

        Returns:
            status code of the request
        """
        return requests.put(url=url, data=json.dumps(data), headers=headers, timeout=5)

    def send_requests_delete(self, url: str, headers: dict = None) -> object:
        """
        Send a delete request to the given url

        Args:
            url (str): url to send the request to
            headers (dict): headers to be sent with the request (optional)

        Returns:
            status code of the request
        """
        return requests.delete(url=url, headers=headers, timeout=5)

    def pre_scan(self) -> None:
        """
        Pre_scan function call

        This function is called just before the scan core.
        Here it is used to arm the detector for the acquisition

        """
        self.arm_acquisition()

    def arm_acquisition(self) -> None:
        """Arms the detector for the acquisition"""
        self.parent.cam.acquire.put(1)
        # TODO is this sleep needed? to be tested with detector and for how long
        time.sleep(0.5)

    def publish_file_location(self, done: bool = False, successful: bool = None) -> None:
        """
        Publish the filepath to REDIS and publish the event for the h5_converter

        We publish two events here:
        - file_event: event for the filewriter
        - public_file: event for any secondary service (e.g. radial integ code)

        Args:
            done (bool): True if scan is finished
            successful (bool): True if scan was successful
        """
        pipe = self.parent.producer.pipeline()
        if successful is None:
            msg = messages.FileMessage(
                file_path=self.parent.filepath,
                done=done,
                metadata={"input_path": self.parent.filepath_raw},
            )
        else:
            msg = messages.FileMessage(
                file_path=self.parent.filepath,
                done=done,
                successful=successful,
                metadata={"input_path": self.parent.filepath_raw},
            )
        self.parent.producer.set_and_publish(
            MessageEndpoints.public_file(self.parent.scaninfo.scanID, self.parent.name),
            msg.dumps(),
            pipe=pipe,
        )
        self.parent.producer.set_and_publish(
            MessageEndpoints.file_event(self.parent.name), msg.dumps(), pipe=pipe
        )
        pipe.execute()

    def finished(self) -> None:
        """Check if acquisition is finished."""
        # pylint: disable=protected-access
        # TODO: at the moment this relies on device.mcs.obj._staged attribute
        signal_conditions = [
            (
                lambda: self.parent.device_manager.devices.mcs.obj._staged,
                Staged.no,
            ),
        ]
        if not self.wait_for_signals(
            signal_conditions=signal_conditions,
            timeout=self.parent.timeout,
            check_stopped=True,
            all_signals=True,
        ):
            raise PilatusTimeoutError(
                f"Reached timeout with detector state {signal_conditions[0][0]}, std_daq state"
                f" {signal_conditions[1][0]} and received frames of {signal_conditions[2][0]} for"
                " the file writer"
            )
        self.stop_detector()
        self.stop_detector_backend()

    def stop_detector(self) -> None:
        """Stop detector"""
        self.parent.cam.acquire.put(0)

    def check_scanID(self) -> None:
        """Checks if scanID has changed and stops the scan if it has"""
        old_scanID = self.parent.scaninfo.scanID
        self.parent.scaninfo.load_scan_metadata()
        if self.parent.scaninfo.scanID != old_scanID:
            self.parent.stopped = True


class PilatuscSAXS(PSIDetectorBase):
    """Pilatus_2 300k detector for CSAXS

    Parent class: PSIDetectorBase

    class attributes:
        custom_prepare_cls (Eiger9MSetup)   : Custom detector setup class for cSAXS,
                                              inherits from CustomDetectorMixin
        cam (SLSDetectorCam)                : Detector camera
        MIN_READOUT (float)                 : Minimum readout time for the detector

    """

    # Specify which functions are revealed to the user in BEC client
    USER_ACCESS = [
        "describe",
    ]

    # specify Setup class
    custom_prepare_cls = PilatusSetup
    # specify minimum readout time for detector
    MIN_READOUT = 3e-3
    # specify class attributes
    cam = ADCpt(SLSDetectorCam, "cam1:")

    def set_trigger(self, trigger_source: TriggerSource) -> None:
        """Set trigger source for the detector"""
        value = trigger_source
        self.cam.trigger_mode.put(value)


if __name__ == "__main__":
    pilatus_2 = PilatuscSAXS(name="pilatus_2", prefix="X12SA-ES-PILATUS300K:", sim_mode=True)
