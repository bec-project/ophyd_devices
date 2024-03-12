import enum
import threading
from collections import defaultdict
import numpy as np

from ophyd import EpicsSignal, EpicsSignalRO, Device, Component as Cpt
from ophyd_devices.utils import bec_utils
from ophyd_devices.epics.devices.psi_detector_base import PSIDetectorBase, CustomDetectorMixin

from bec_lib import messages, MessageEndpoints, bec_logger, threadlocked


logger = bec_logger.logger


class MCSError(Exception):
    """Base class for exceptions in this module."""


class MCSTimeoutError(MCSError):
    """Raise when MCS card runs into a timeout"""


class TriggerSource(int, enum.Enum):
    """Trigger source for mcs card - see manual for more information"""

    MODE0 = 0
    MODE1 = 1
    MODE2 = 2
    MODE3 = 3
    MODE4 = 4
    MODE5 = 5
    MODE6 = 6


class ChannelAdvance(int, enum.Enum):
    """Channel advance pixel mode for mcs card - see manual for more information"""

    INTERNAL = 0
    EXTERNAL = 1


class ReadoutMode(int, enum.Enum):
    """Readout mode for mcs card - see manual for more information"""

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


class MCSSetup(CustomDetectorMixin):
    """Setup mixin class for the MCS card"""

    def __init__(self, *args, parent: Device = None, **kwargs) -> None:
        super().__init__(*args, parent=parent, **kwargs)
        self._lock = threading.RLock()
        self._stream_ttl = 1800
        self.acquisition_done = False
        self.counter = 0
        self.n_points = 0
        self.mca_names = [
            signal for signal in self.parent.component_names if signal.startswith("mca")
        ]
        self.mca_data = defaultdict(lambda: [])

    def initialize_detector(self) -> None:
        """Initialize detector"""
        # External trigger for pixel advance
        self.parent.channel_advance.set(ChannelAdvance.EXTERNAL)
        # Use internal clock for channel 1
        self.parent.channel1_source.set(ChannelAdvance.INTERNAL)
        self.parent.user_led.set(0)
        # Set number of channels to 5
        self.parent.mux_output.set(5)
        # Trigger Mode used for cSAXS
        self.parent.set_trigger(TriggerSource.MODE3)
        # specify polarity of trigger signals
        self.parent.input_polarity.set(0)
        self.parent.output_polarity.set(1)
        # do not start counting on start
        self.parent.count_on_start.set(0)
        self.stop_detector()

    def initialize_detector_backend(self) -> None:
        """Initialize detector backend"""
        for mca in self.mca_names:
            signal = getattr(self.parent, mca)
            signal.subscribe(self._on_mca_data, run=False)
        self.parent.current_channel.subscribe(self._progress_update, run=False)

    def _progress_update(self, value, **kwargs) -> None:
        """Progress update on the scan"""
        num_lines = self.parent.num_lines.get()
        max_value = self.parent.scaninfo.num_points
        # self.counter seems to be a deprecated variable from a former implementation of the mcs card
        # pylint: disable=protected-access
        self.parent._run_subs(
            sub_type=self.parent.SUB_PROGRESS,
            value=self.counter * int(self.parent.scaninfo.num_points / num_lines) + value,
            max_value=max_value,
            # TODO check if that is correct with
            done=bool(max_value == value),  # == self.counter),
        )

    @threadlocked
    def _on_mca_data(self, *args, obj=None, value=None, **kwargs) -> None:
        """Callback function for scan progress"""
        if not isinstance(value, (list, np.ndarray)):
            return
        self.mca_data[obj.attr_name] = value
        if len(self.mca_names) != len(self.mca_data):
            return
        self.acquisition_done = True
        self._send_data_to_bec()
        self.mca_data = defaultdict(lambda: [])

    def _send_data_to_bec(self) -> None:
        """Sends bundled data to BEC"""
        if self.parent.scaninfo.scan_msg is None:
            return
        metadata = self.parent.scaninfo.scan_msg.metadata
        metadata.update(
            {
                "async_update": "append",
                "num_lines": self.parent.num_lines.get(),
            }
        )
        msg = messages.DeviceMessage(
            signals=dict(self.mca_data),
            metadata=self.parent.scaninfo.scan_msg.metadata,
        )
        self.parent.connector.xadd(
            topic=MessageEndpoints.device_async_readback(
                scanID=self.parent.scaninfo.scanID, device=self.parent.name
            ),
            msg={"data": msg},
            expire=self._stream_ttl,
        )

    def prepare_detector(self) -> None:
        """Prepare detector for scan"""
        self.set_acquisition_params()
        self.parent.set_trigger(TriggerSource.MODE3)

    def set_acquisition_params(self) -> None:
        """Set acquisition parameters for scan"""
        if self.parent.scaninfo.scan_type == "step":
            self.n_points = int(self.parent.scaninfo.frames_per_trigger) * int(
                self.parent.scaninfo.num_points
            )
        elif self.parent.scaninfo.scan_type == "fly":
            self.n_points = int(self.parent.scaninfo.num_points)  # / int(self.num_lines.get()))
        else:
            raise MCSError(f"Scantype {self.parent.scaninfo} not implemented for MCS card")
        if self.n_points > 10000:
            raise MCSError(
                f"Requested number of points N={self.n_points} exceeds hardware limit of mcs card"
                " 10000 (N-1)"
            )
        self.parent.num_use_all.set(self.n_points)
        self.parent.preset_real.set(0)

    def prepare_detector_backend(self) -> None:
        """Prepare detector backend for scan"""
        self.parent.erase_all.set(1)
        self.parent.read_mode.set(ReadoutMode.EVENT)

    def arm_acquisition(self) -> None:
        """Arm detector for acquisition"""
        self.counter = 0
        self.parent.erase_start.set(1)

    def finished(self) -> None:
        """Check if acquisition is finished, if not successful, rais MCSTimeoutError"""
        signal_conditions = [
            (
                lambda: self.acquisition_done,
                True,
            ),
            (
                self.parent.acquiring.get,
                0,  # Considering making a enum.Int class for this state
            ),
        ]
        if not self.wait_for_signals(
            signal_conditions=signal_conditions,
            timeout=self.parent.timeout,
            check_stopped=True,
            all_signals=True,
        ):
            total_frames = self.counter * int(
                self.parent.scaninfo.num_points / self.parent.num_lines.get()
            ) + max(self.parent.current_channel.get(), 0)
            raise MCSTimeoutError(
                f"Reached timeout with mcs in state {self.parent.acquiring.get()} and"
                f" {total_frames} frames arriving at the mcs card"
            )

    def stop_detector(self) -> None:
        """Stop detector"""
        self.parent.stop_all.set(1)

        return super().stop_detector()

    def stop_detector_backend(self) -> None:
        """Stop acquisition of data"""
        self.acquisition_done = True


class SIS38XX(Device):
    """SIS38XX card for access to EPICs PVs at cSAXS beamline"""


class MCScSAXS(PSIDetectorBase):
    """MCS card for cSAXS for implementation at cSAXS beamline"""

    USER_ACCESS = ["describe", "_init_mcs"]
    SUB_PROGRESS = "progress"
    SUB_VALUE = "value"
    _default_sub = SUB_VALUE

    # specify Setup class
    custom_prepare_cls = MCSSetup
    # specify minimum readout time for detector
    MIN_READOUT = 0

    # PV access to SISS38XX card
    # Acquisition
    erase_all = Cpt(EpicsSignal, "EraseAll")
    erase_start = Cpt(EpicsSignal, "EraseStart")  # ,trigger_value=1
    start_all = Cpt(EpicsSignal, "StartAll")
    stop_all = Cpt(EpicsSignal, "StopAll")
    acquiring = Cpt(EpicsSignal, "Acquiring")
    preset_real = Cpt(EpicsSignal, "PresetReal")
    elapsed_real = Cpt(EpicsSignal, "ElapsedReal")
    read_mode = Cpt(EpicsSignal, "ReadAll.SCAN")
    read_all = Cpt(EpicsSignal, "DoReadAll.VAL")  # ,trigger_value=1
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

    # PV access to MCA signals
    mca1 = Cpt(EpicsSignalRO, "mca1.VAL", auto_monitor=True)
    mca3 = Cpt(EpicsSignalRO, "mca3.VAL", auto_monitor=True)
    mca4 = Cpt(EpicsSignalRO, "mca4.VAL", auto_monitor=True)
    current_channel = Cpt(EpicsSignalRO, "CurrentChannel", auto_monitor=True)

    # Custom signal readout from device config
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
            # pylint: disable=expression-not-assigned
            [self.mcs_config.update({f"{name}_{key}": value}) for key, value in mcs_config.items()]

        super().__init__(
            prefix=prefix,
            name=name,
            kind=kind,
            read_attrs=read_attrs,
            configuration_attrs=configuration_attrs,
            parent=parent,
            device_manager=device_manager,
            sim_mode=sim_mode,
            **kwargs,
        )

    def set_trigger(self, trigger_source: TriggerSource) -> None:
        """Set trigger mode from TriggerSource"""
        value = int(trigger_source)
        self.input_mode.set(value)

    def stage(self) -> list[object]:
        """stage the detector for upcoming acquisition"""
        rtr = super().stage()
        self.custom_prepare.arm_acquisition()
        return rtr


# Automatically connect to test environmenr if directly invoked
if __name__ == "__main__":
    mcs = MCScSAXS(name="mcs", prefix="X12SA-MCS:", sim_mode=True)
