import enum
import threading
import time
from typing import Any, List
import numpy as np

from ophyd import EpicsSignal, EpicsSignalRO
from ophyd import EpicsSignal, EpicsSignalRO, Component as Cpt, Device
from ophyd.mca import EpicsMCARecord
from ophyd.scaler import ScalerCH

from ophyd_devices.epics.devices.bec_scaninfo_mixin import BecScaninfoMixin
from ophyd_devices.utils import bec_utils

from bec_lib import messages, MessageEndpoints, bec_logger, threadlocked
from bec_lib.file_utils import FileWriterMixin
from collections import defaultdict

logger = bec_logger.logger


class McsError(Exception):
    pass


class McsTimeoutError(Exception):
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
    read_all = Cpt(EpicsSignal, "DoReadAll.VAL", trigger_value=1)
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
    USER_ACCESS = ["_init_mcs"]
    SUB_PROGRESS = "progress"
    SUB_VALUE = "value"
    _default_sub = SUB_VALUE
    # scaler = Cpt(ScalerCH, "scaler1")

    # mca2 = Cpt(EpicsMCARecord, "mca2")
    mca1 = Cpt(EpicsSignalRO, "mca1.VAL", auto_monitor=True)
    mca3 = Cpt(EpicsSignalRO, "mca3.VAL", auto_monitor=True)
    mca4 = Cpt(EpicsSignalRO, "mca4.VAL", auto_monitor=True)
    # mca5 = Cpt(EpicsMCARecord, "mca5")
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
    current_channel = Cpt(EpicsSignalRO, "CurrentChannel", auto_monitor=True)

    num_lines = Cpt(
        bec_utils.ConfigSignal,
        name="num_lines",
        kind="config",
        config_storage_name="mcs_config",
    )

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
        mcs_config=None,
        **kwargs,
    ):
        self.mcs_config = {
            f"{name}_num_lines": 1,
        }
        if mcs_config is not None:
            [self.mcs_config.update({f"{name}_{key}": value}) for key, value in mcs_config.items()]

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
            raise McsError("Add DeviceManager to initialization or init with sim_mode=True")

        self.name = name
        self._stream_ttl = 1800
        self.wait_for_connection()  # Make sure to be connected before talking to PVs

        if not sim_mode:
            self.device_manager = device_manager
            self._producer = self.device_manager.producer
        else:
            self._producer = bec_utils.MockProducer()
            self.device_manager = bec_utils.MockDeviceManager()
            # TODO mack mock connector class
            # self._consumer = self.device_manager.connector.consumer
        self.scaninfo = BecScaninfoMixin(device_manager, sim_mode)
        # TODO
        self.scaninfo.username = "e21206"
        self.service_cfg = {"base_path": f"/sls/X12SA/data/{self.scaninfo.username}/Data10/"}
        self.filewriter = FileWriterMixin(self.service_cfg)
        self._stopped = False
        self._acquisition_done = False
        self._lock = threading.RLock()
        self.counter = 0
        self.n_points = 0
        self._init_mcs()
        self.mca_names = [signal for signal in self.component_names if signal.startswith("mca")]
        self.mca_data = defaultdict(lambda: [])
        for mca in self.mca_names:
            signal = getattr(self, mca)
            signal.subscribe(self._on_mca_data, run=False)
        self.current_channel.subscribe(self._progress_update, run=False)

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
        self.output_polarity.set(1)
        self.count_on_start.set(0)
        self.stop_all.set(1)

    def _progress_update(self, value, **kwargs) -> None:
        num_lines = self.num_lines.get()
        max_value = self.scaninfo.num_points
        self._run_subs(
            sub_type=self.SUB_PROGRESS,
            value=self.counter * int(self.scaninfo.num_points / num_lines) + value,
            max_value=max_value,
            done=bool(max_value == self.counter),
        )

    @threadlocked
    def _on_mca_data(self, *args, obj=None, **kwargs) -> None:
        if not isinstance(kwargs["value"], (list, np.ndarray)):
            return
        # self.mca_data[obj.attr_name] = kwargs["value"][1:]
        self.mca_data[obj.attr_name] = kwargs["value"]
        if len(self.mca_names) != len(self.mca_data):
            return
        # logger.info("Entered _on_mca_data")
        # self._updated = True
        # self.counter += 1
        # logger.info(f'data from mca {self.mca_data["mca1"]} and {self.mca_data["mca4"]}')
        # if (self.scaninfo.scan_type == "fly" and self.counter == self.num_lines.get()) or (
        #     self.scaninfo.scan_type == "step" and self.counter == self.scaninfo.num_points
        # ):
        #     self._acquisition_done = True
        #     self.stop_all.put(1, use_complete=False)
        #     self._send_data_to_bec()
        #     self.erase_all.put(1)
        #     #logger.info("Entered _on_mca_data, acquisition finished")
        #     # Require wait for
        #     # time.sleep(0.01)
        #     self.mca_data = defaultdict(lambda: [])
        #     self.counter = 0
        #     return
        # self.erase_start.set(1)
        # self._send_data_to_bec()
        # self.mca_data = defaultdict(lambda: [])
        self._acquisition_done = True
        self._send_data_to_bec()
        self.mca_data = defaultdict(lambda: [])

    def _send_data_to_bec(self) -> None:
        if self.scaninfo.scan_msg is None:
            return
        metadata = self.scaninfo.scan_msg.metadata
        metadata.update(
            {
                "async_update": "append",
                "num_lines": self.num_lines.get(),
            }
        )
        msg = messages.DeviceMessage(
            signals=dict(self.mca_data),
            metadata=self.scaninfo.scan_msg.metadata,
        ).dumps()
        self._producer.xadd(
            topic=MessageEndpoints.device_async_readback(
                scanID=self.scaninfo.scanID, device=self.name
            ),
            msg={"data": msg},
            expire=self._stream_ttl,
        )

    def _prep_det(self) -> None:
        self._set_acquisition_params()
        self._set_trigger(TriggerSource.MODE3)

    def _set_acquisition_params(self) -> None:
        if self.scaninfo.scan_type == "step":
            self.n_points = int(self.scaninfo.frames_per_trigger) * int(self.scaninfo.num_points)
        elif self.scaninfo.scan_type == "fly":
            self.n_points = int(self.scaninfo.num_points)  # / int(self.num_lines.get()))
        else:
            raise McsError(f"Scantype {self.scaninfo} not implemented for MCS card")
        if self.n_points > 10000:
            raise McsError(
                f"Requested number of points N={self.n_points} exceeds hardware limit of mcs card 10000 (N-1)"
            )
        self.num_use_all.set(self.n_points)
        self.preset_real.set(0)

    def _set_trigger(self, trigger_source: TriggerSource) -> None:
        """7 Modes, see TriggerSource
        Mode3 for cSAXS"""
        value = int(trigger_source)
        self.input_mode.set(value)

    def _prep_readout(self) -> None:
        """Set readout mode of mcs card
        Check ReadoutMode class for more information about options
        """
        # self.read_mode.set(ReadoutMode.EVENT)
        self.erase_all.set(1)
        self.read_mode.set(ReadoutMode.EVENT)

    def _force_readout_mcs_card(self) -> None:
        self.read_all.put(1, use_complete=False)

    def stage(self) -> List[object]:
        """stage the detector and file writer"""
        self._stopped = False
        self._acquisition_done = False
        logger.info("Stage mcs")
        self.scaninfo.load_scan_metadata()
        self._prep_det()
        self._prep_readout()

        # msg = messages.FileMessage(file_path=self.filepath, done=False)
        # self._producer.set_and_publish(
        #     MessageEndpoints.public_file(self.scaninfo.scanID, "mcs_csaxs"),
        #     msg.dumps(),
        # )
        self.arm_acquisition()
        logger.info("Waiting for mcs to be armed")
        while True:
            det_ctrl = self.acquiring.read()[self.acquiring.name]["value"]
            if det_ctrl == 1:
                break
            time.sleep(0.005)
        logger.info("mcs is ready and running")
        # time.sleep(5)
        return super().stage()

    def unstage(self) -> List[object]:
        """unstage"""
        logger.info("Waiting for mcs to finish acquisition")
        old_scanID = self.scaninfo.scanID
        self.scaninfo.load_scan_metadata()
        logger.info(f"Old scanID: {old_scanID}, ")
        if self.scaninfo.scanID != old_scanID:
            self._stopped = True
        if self._stopped is True:
            logger.info("Entered unstage _stopped =True")
            return super().unstage()
        self._mcs_finished()
        self._acquisition_done = False
        self._stopped = False
        logger.info("mcs done")
        return super().unstage()

    def _mcs_finished(self):
        """Function with 10s timeout"""
        timer = 0
        logger.info("Entered _mcs_finished loop")
        while True:
            if self._acquisition_done == True and self.acquiring.get() == 0:
                break
            if self._stopped == True:
                break
            time.sleep(0.1)
            timer += 0.1
            if timer > 8:
                total_frames = self.counter * int(
                    self.scaninfo.num_points / self.num_lines.get()
                ) + max(self.current_channel.get(), 0)
                raise McsTimeoutError(
                    f"Reached timeout with mcs in state {self.acquiring.get()} and {total_frames} frames arriving at the mcs card"
                )
        logger.info("Finished _mcs_finished loop")

    def arm_acquisition(self) -> None:
        """Arm acquisition
        Options:
        Start: start_all
        Erase/Start: erase_start
        """
        logger.info("Entered mcs arm_acquisition")
        self.counter = 0
        self.erase_start.set(1)
        # self.start_all.set(1)

    def stop(self, *, success=False) -> None:
        """Stop acquisition
        Stop or Stop and Erase
        """
        logger.info("Entered mcs stop")
        self.stop_all.set(1)
        # self.erase_all.set(1)
        self._stopped = True
        self._acquisition_done = True
        super().stop(success=success)


# Automatically connect to test environmenr if directly invoked
if __name__ == "__main__":
    mcs = McsCsaxs(name="mcs", prefix="X12SA-MCS:", sim_mode=True)
    mcs.stage()
    mcs.unstage()
