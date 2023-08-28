import enum
import time
from typing import Any, List
import numpy as np

from ophyd import EpicsSignal, EpicsSignalRO
from ophyd import EpicsSignal, EpicsSignalRO, Component as Cpt, Device
from ophyd.mca import EpicsMCARecord
from ophyd.scaler import ScalerCH

from bec_lib.core import BECMessage, MessageEndpoints
from bec_lib.core.file_utils import FileWriterMixin
from bec_lib.core import bec_loggers
from ophyd_devices.utils import bec_utils as bec_utils

from std_daq_client import StdDaqClient

from ophyd_devices.epics.devices.bec_scaninfo_mixin import BecScaninfoMixin

from ophyd_devices.utils import bec_utils

from ophyd_devices.epics.devices.bec_scaninfo_mixin import BecScaninfoMixin


class MCSError(Exception):
    pass


class TriggerSource(int, enum.Enum):
    MODE0 = 0
    MODE1 = 1
    MODE2 = 2
    MODE3 = 3
    MODE4 = 4
    MODE5 = 5
    MODE6 = 6


class ChannelAdvance(int, enum.Enum):
    INTERNAL = 0
    EXTERNAL = 1


class ReadoutMode(int, enum.Enum):
    PASSIVE = 0
    EVENT = 1
    IO_INTR = 2
    FREQ_0_1HZ = 3
    FREQ_0_2HZ = 4
    FREQ_0_5HZ = 5
    FREQ_1HZ = 6
    FREQ_2HZ = 7
    FREQ_5HZ = 8
    FREQ_10HZ = 9
    FREQ_100HZ = 10


class SIS38XX(Device):
    """SIS38XX control"""

    # Acquisition
    erase_all = Cpt(EpicsSignal, "EraseAll")
    erase_start = Cpt(EpicsSignal, "EraseStart", trigger_value=1)
    start_all = Cpt(EpicsSignal, "StartAll")
    stop_all = Cpt(EpicsSignal, "StopAll")

    acquiring = Cpt(EpicsSignal, "Acquiring")

    preset_real = Cpt(EpicsSignal, "PresetReal")
    elapsed_real = Cpt(EpicsSignal, "ElapsedReal")

    read_mode = Cpt(EpicsSignal, "ReadAll.SCAN")
    read_all = Cpt(EpicsSignal, "DoReadAll.VAL")
    num_use_all = Cpt(EpicsSignal, "NuseAll")
    current_channel = Cpt(EpicsSignal, "CurrentChannel")
    dwell = Cpt(EpicsSignal, "Dwell")
    channel_advance = Cpt(EpicsSignal, "ChannelAdvance")
    count_on_start = Cpt(EpicsSignal, "CountOnStart")
    software_channel_advance = Cpt(EpicsSignal, "SoftwareChannelAdvance")
    channel1_source = Cpt(EpicsSignal, "Channel1Source")
    prescale = Cpt(EpicsSignal, "Prescale")
    enable_client_wait = Cpt(EpicsSignal, "EnableClientWait")
    client_wait = Cpt(EpicsSignal, "ClientWait")
    acquire_mode = Cpt(EpicsSignal, "AcquireMode")
    mux_output = Cpt(EpicsSignal, "MUXOutput")
    user_led = Cpt(EpicsSignal, "UserLED")
    input_mode = Cpt(EpicsSignal, "InputMode")
    input_polarity = Cpt(EpicsSignal, "InputPolarity")
    output_mode = Cpt(EpicsSignal, "OutputMode")
    output_polarity = Cpt(EpicsSignal, "OutputPolarity")
    model = Cpt(EpicsSignalRO, "Model", string=True)
    firmware = Cpt(EpicsSignalRO, "Firmware")
    max_channels = Cpt(EpicsSignalRO, "MaxChannels")


class McsCsaxs(SIS38XX):
    scaler = Cpt(ScalerCH, "scaler1")

    mca1 = Cpt(EpicsMCARecord, "mca1")
    mca2 = Cpt(EpicsMCARecord, "mca2")
    mca3 = Cpt(EpicsMCARecord, "mca3")
    mca4 = Cpt(EpicsMCARecord, "mca4")
    mca5 = Cpt(EpicsMCARecord, "mca5")
    # mca6 = Cpt(EpicsMCARecord, "mca6")
    # mca7 = Cpt(EpicsMCARecord, "mca7")
    # mca8 = Cpt(EpicsMCARecord, "mca8")
    # mca9 = Cpt(EpicsMCARecord, "mca9")
    # mca10 = Cpt(EpicsMCARecord, "mca10")
    # mca11 = Cpt(EpicsMCARecord, "mca11")
    # mca12 = Cpt(EpicsMCARecord, "mca12")
    # mca13 = Cpt(EpicsMCARecord, "mca13")
    # mca14 = Cpt(EpicsMCARecord, "mca14")
    # mca15 = Cpt(EpicsMCARecord, "mca15")
    # mca16 = Cpt(EpicsMCARecord, "mca16")
    # mca17 = Cpt(EpicsMCARecord, "mca17")
    # mca18 = Cpt(EpicsMCARecord, "mca18")
    # mca19 = Cpt(EpicsMCARecord, "mca19")
    # mca20 = Cpt(EpicsMCARecord, "mca20")
    # mca21 = Cpt(EpicsMCARecord, "mca21")
    # mca22 = Cpt(EpicsMCARecord, "mca22")
    # mca23 = Cpt(EpicsMCARecord, "mca23")
    # mca24 = Cpt(EpicsMCARecord, "mca24")
    # mca25 = Cpt(EpicsMCARecord, "mca25")
    # mca26 = Cpt(EpicsMCARecord, "mca26")
    # mca27 = Cpt(EpicsMCARecord, "mca27")
    # mca28 = Cpt(EpicsMCARecord, "mca28")
    # mca29 = Cpt(EpicsMCARecord, "mca29")
    # mca30 = Cpt(EpicsMCARecord, "mca30")
    # mca31 = Cpt(EpicsMCARecord, "mca31")
    # mca32 = Cpt(EpicsMCARecord, "mca32")

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
            raise MCSError("Add DeviceManager to initialization or init with sim_mode=True")

        self.name = name
        self.wait_for_connection()  # Make sure to be connected before talking to PVs
        if not sim_mode:
            self._producer = self.device_manager.producer
            self.device_manager = device_manager
        else:
            self._producer = bec_utils.MockProducer()
            self.device_manager = bec_utils.MockDeviceManager()
        self.scaninfo = BecScaninfoMixin(device_manager, sim_mode)
        # TODO
        self.scaninfo.username = "e21206"
        self.service_cfg = {"base_path": f"/sls/X12SA/data/{self.scaninfo.username}/Data10/"}
        self.filewriter = FileWriterMixin(self.service_cfg)
        self._init_mcs()
        self._init_standard_daq()

    def _init_mcs(self) -> None:
        """Init parameters for mcs card 9m
        channel_advance: 0/1 -> internal / external
        channel1_source: 0/1 -> int clock / external source
        user_led: 0/1 -> off/on
        max_output :  num of channels 0...32, uncomment top for more than 5
        input_mode: operation mode -> Mode 3 for external trigger, check manual for more info
        input_polarity: triggered between falling and falling edge -> use inverted signal from ddg
        """
        self.channel_advance.set(ChannelAdvance.EXTERNAL)
        self.channel1_source.set(ChannelAdvance.INTERNAL)
        self.user_led.set(0)
        self.mux_output.set(5)
        self._set_trigger(TriggerSource.MODE3)
        self.input_polarity.set(0)

    def _prep_det(self) -> None:
        self._set_acquisition_params()
        self._set_trigger(TriggerSource.MODE3)

    def _set_acquisition_params(self) -> None:
        # max number of readings is limited to 10000, but device can be reseted.. needs to be included on scan level
        self.num_use_all.set(self.scaninfo.num_frames)
        self.preset_real.set(0)

        self.count_on_start.set(0)

        self.cam.num_frames.set(1)

    def _set_trigger(self, trigger_source: TriggerSource) -> None:
        """Set trigger source for the detector, either directly to value or TriggerSource.* with
        AUTO = 0
        TRIGGER = 1
        GATING = 2
        BURST_TRIGGER = 3
        """
        value = int(trigger_source)
        self.cam.timing_mode.set(value)

    def _prep_readout(self) -> None:
        """Set readout mode of mcs card
        Check ReadoutMode class for more information about options
        """
        self.read_mode.set(ReadoutMode.PASSIVE)

    def _readout(self) -> List:
        self.read_all.set(1)
        readback = []
        readback.append(self.scaler.read()[self.scaler.name]["value"])
        for ii in range(1, self.mux_output.get() + 1):
            readback.append(self._readout_mca(ii))
        return readback

    def _readout_mca(self, num: int) -> List[List]:
        signal = f"mca{num}"
        if signal in self.component_names:
            return getattr(self, signal).read()[getattr(self, signal).name]["value"]

    def stage(self) -> List[object]:
        """stage the detector and file writer"""
        self.scaninfo.load_scan_metadata()
        self.mokev = self.device_manager.devices.mokev.read()[
            self.device_manager.devices.mokev.name
        ]["value"]

        self._prep_det()
        self._prep_file_writer()

        msg = BECMessage.FileMessage(file_path=self.filepath, done=False)
        self._producer.set_and_publish(
            MessageEndpoints.public_file(self.scaninfo.scanID, "eiger9m"),
            msg.dumps(),
        )
        self.arm_acquisition()
        logger.info("Waiting for detector to be armed")
        while True:
            det_ctrl = self.cam.detector_state.read()[self.cam.detector_state.name]["value"]
            if det_ctrl == int(DetectorState.RUNNING):
                break
            time.sleep(0.005)
        logger.info("Detector is armed")

        return super().stage()

    def unstage(self) -> List[object]:
        """unstage the detector and file writer"""
        logger.info("Waiting for eiger9M to return from acquisition")
        while True:
            det_ctrl = self.cam.acquire.read()[self.cam.acquire.name]["value"]
            if det_ctrl == 0:
                break
            time.sleep(0.005)

        logger.info("Waiting for std daq to receive images")
        while True:
            det_ctrl = self.std_client.get_status()["acquisition"]["state"]
            if det_ctrl == "FINISHED":
                break
            time.sleep(0.005)
        # Message to BEC
        # state = True

        # msg = BECMessage.FileMessage(file_path=self.filepath, done=True, successful=state)
        # self._producer.set_and_publish(
        #     MessageEndpoints.public_file(self.metadata["scanID"], self.name),
        #     msg.dumps(),
        # )
        return super().unstage()

    def arm_acquisition(self) -> None:
        """Start acquisition in software trigger mode,
        or arm the detector in hardware of the detector
        """
        self.cam.acquire.set(1)

    def stop(self, *, success=False) -> None:
        """Stop the scan, with camera and file writer"""
        self.cam.acquire.set(0)
        self._close_file_writer()
        self.unstage()
        super().stop(success=success)
        self._stopped = True


# Automatically connect to test environmenr if directly invoked
if __name__ == "__main__":
    eiger = Eiger9mCsaxs(name="eiger", prefix="X12SA-ES-EIGER9M:", sim_mode=True)
    eiger.stage()
