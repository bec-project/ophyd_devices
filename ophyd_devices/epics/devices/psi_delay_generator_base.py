import time
from typing import Any, List
from ophyd import Device, Component, EpicsSignal, EpicsSignalRO, Kind
from ophyd import PVPositioner, Signal, DeviceStatus
from ophyd.pseudopos import (
    pseudo_position_argument,
    real_position_argument,
    PseudoSingle,
    PseudoPositioner,
)
from ophyd.device import Staged

from ophyd_devices.epics.devices.bec_scaninfo_mixin import BecScaninfoMixin
from ophyd_devices.utils import bec_utils

from bec_lib import bec_logger


logger = bec_logger.logger


class DelayGeneratorError(Exception):
    """Exception raised for errors in the Delay Generator."""


class DeviceInitError(DelayGeneratorError):
    """Error raised when init of device class fails due to missing device manager or not started in sim_mode."""


class DelayStatic(Device):
    """Static axis for the T0 output channel

    It allows setting the logic levels, but the timing is fixed.
    The signal is high after receiving the trigger until the end
    of the holdoff period.
    """

    # Other channel stuff
    ttl_mode = Component(EpicsSignal, "OutputModeTtlSS.PROC", kind=Kind.config)
    nim_mode = Component(EpicsSignal, "OutputModeNimSS.PROC", kind=Kind.config)
    polarity = Component(
        EpicsSignal,
        "OutputPolarityBI",
        write_pv="OutputPolarityBO",
        name="polarity",
        kind=Kind.config,
    )
    amplitude = Component(
        EpicsSignal,
        "OutputAmpAI",
        write_pv="OutputAmpAO",
        name="amplitude",
        kind=Kind.config,
    )
    offset = Component(
        EpicsSignal,
        "OutputOffsetAI",
        write_pv="OutputOffsetAO",
        name="offset",
        kind=Kind.config,
    )


class DummyPositioner(PVPositioner):
    """Dummy positioner for the DG645"""

    setpoint = Component(EpicsSignal, "DelayAO", put_complete=True, kind=Kind.config)
    readback = Component(EpicsSignalRO, "DelayAI", kind=Kind.config)
    done = Component(Signal, value=1)
    reference = Component(EpicsSignal, "ReferenceMO", put_complete=True, kind=Kind.config)


class DelayPair(PseudoPositioner):
    """Delay pair interface for DG645

    Virtual motor interface to a pair of signals (on the frontpanel).
    It offers a simple delay and pulse width interface for scanning.
    """

    # The pseudo positioner axes
    delay = Component(PseudoSingle, limits=(0, 2000.0), name="delay")
    width = Component(PseudoSingle, limits=(0, 2000.0), name="pulsewidth")
    ch1 = Component(DummyPositioner, name="ch1")
    ch2 = Component(DummyPositioner, name="ch2")
    io = Component(DelayStatic, name="io")

    def __init__(self, *args, **kwargs):
        # Change suffix names before connecting (a bit of dynamic connections)
        self.__class__.__dict__["ch1"].suffix = kwargs["channel"][0]
        self.__class__.__dict__["ch2"].suffix = kwargs["channel"][1]
        self.__class__.__dict__["io"].suffix = kwargs["channel"]

        del kwargs["channel"]
        # Call parent to start the connections
        super().__init__(*args, **kwargs)

    @pseudo_position_argument
    def forward(self, pseudo_pos):
        """Run a forward (pseudo -> real) calculation"""
        return self.RealPosition(ch1=pseudo_pos.delay, ch2=pseudo_pos.delay + pseudo_pos.width)

    @real_position_argument
    def inverse(self, real_pos):
        """Run an inverse (real -> pseudo) calculation"""
        return self.PseudoPosition(delay=real_pos.ch1, width=real_pos.ch2 - real_pos.ch1)


class DDGCustomMixin:
    """
    Mixin class for custom DelayGenerator logic

    This class is used to implement BL specific logic for the DDG.
    It is used in the PSIDelayGeneratorBase class.
    """

    def __init__(self, *_args, parent: Device = None, **_kwargs) -> None:
        self.parent = parent

    def initialize_default_parameter(self) -> None:
        """
        Initialize default parameters for DDG

        This method is called upon initiating the class.
        It can be conveniently used to set default parameters for the DDG.
        These may include, amplitudes, offsets, delays, etc.
        """

    def prepare_ddg(self) -> None:
        """
        Prepare the DDG for the upcoming scan

        This methods hosts the full logic for the upcoming scan.
        It is called by the stage method and needs to fully prepare the DDGs for the upcoming scan.
        """

    def on_trigger(self) -> None:
        """Define action executed on trigger methods"""

    def finished(self) -> None:
        """Checks if DDG finished acquisition"""

    def on_pre_scan(self) -> None:
        """
        Called by pre scan hook

        These actions get executed just before the trigger method/start of scan
        """

    def check_scanID(self) -> None:
        """
        Check if BEC is running on a new scanID
        """

    def is_ddg_okay(self, raise_on_error=False) -> None:
        """Check if DDG is okay, if not try to clear error"""
        status = self.parent.status.read()[self.parent.status.name]["value"]
        if status != "STATUS OK" and not raise_on_error:
            logger.warning(f"DDG returns {status}, trying to clear ERROR")
            self.parent.clear_error()
            time.sleep(1)
            self.is_ddg_okay(raise_on_error=True)
        elif status != "STATUS OK":
            raise Exception(f"DDG failed to start with status: {status}")


class PSIDelayGeneratorBase(Device):
    """
    Abstract base class for DelayGenerator DG645

    This class implements a thin Ophyd wrapper around the Stanford Research DG645
    digital delay generator.

    Internally, the DG645 generates 8+1 signals:  A, B, C, D, E, F, G, H and T0
    Front panel outputs T0, AB, CD, EF and GH are a combination of these signals.
    Back panel outputs are directly routed signals. So signals are NOT INDEPENDENT.

    Front panel signals:
    All signals go high after their defined delays and go low after the trigger
    holdoff period, i.e. this is the trigger window. Front panel outputs provide
    a combination of these events.

    Class attributes:
        custom_prepare_cls (object): class for custom prepare logic (BL specific)

    Args:
        prefix (str): EPICS PV prefix for component (optional)
        name (str): name of the device, as will be reported via read()
        kind (str): member of class 'ophydobj.Kind', defaults to Kind.normal
                    omitted -> readout ignored for read 'ophydobj.read()'
                    normal -> readout for read
                    config -> config parameter for 'ophydobj.read_configuration()'
                    hinted -> which attribute is readout for read
        read_attrs (list): sequence of attribute names to read
        configuration_attrs (list): sequence of attribute names via config_parameters
        parent (object): instance of the parent device
        device_manager (object): bec device manager
        sim_mode (bool): simulation mode, if True, no device manager is required
        **kwargs: keyword arguments

        attributes: lazy_wait_for_connection : bool
    """

    # Custom_prepare_cls
    custom_prepare_cls = DDGCustomMixin

    SUB_PROGRESS = "progress"
    SUB_VALUE = "value"
    _default_sub = SUB_VALUE

    USER_ACCESS = [
        "set_channels",
        "_set_trigger",
        "burst_enable",
        "burst_disable",
        "reload_config",
    ]

    trigger_burst_readout = Component(
        EpicsSignal, "EventStatusLI.PROC", name="trigger_burst_readout"
    )
    burst_cycle_finished = Component(EpicsSignalRO, "EventStatusMBBID.B3", name="read_burst_state")
    delay_finished = Component(EpicsSignalRO, "EventStatusMBBID.B2", name="delay_finished")
    status = Component(EpicsSignalRO, "StatusSI", name="status")
    clear_error = Component(EpicsSignal, "StatusClearBO", name="clear_error")

    # Front Panel
    channelT0 = Component(DelayStatic, "T0", name="T0")
    channelAB = Component(DelayPair, "", name="AB", channel="AB")
    channelCD = Component(DelayPair, "", name="CD", channel="CD")
    channelEF = Component(DelayPair, "", name="EF", channel="EF")
    channelGH = Component(DelayPair, "", name="GH", channel="GH")

    # Minimum time between triggers
    holdoff = Component(
        EpicsSignal,
        "TriggerHoldoffAI",
        write_pv="TriggerHoldoffAO",
        name="trigger_holdoff",
        kind=Kind.config,
    )
    inhibit = Component(
        EpicsSignal,
        "TriggerInhibitMI",
        write_pv="TriggerInhibitMO",
        name="trigger_inhibit",
        kind=Kind.config,
    )
    source = Component(
        EpicsSignal,
        "TriggerSourceMI",
        write_pv="TriggerSourceMO",
        name="trigger_source",
        kind=Kind.config,
    )
    level = Component(
        EpicsSignal,
        "TriggerLevelAI",
        write_pv="TriggerLevelAO",
        name="trigger_level",
        kind=Kind.config,
    )
    rate = Component(
        EpicsSignal,
        "TriggerRateAI",
        write_pv="TriggerRateAO",
        name="trigger_rate",
        kind=Kind.config,
    )
    trigger_shot = Component(EpicsSignal, "TriggerDelayBO", name="trigger_shot", kind="config")
    # Burst mode
    burstMode = Component(
        EpicsSignal,
        "BurstModeBI",
        write_pv="BurstModeBO",
        name="burstmode",
        kind=Kind.config,
    )
    burstConfig = Component(
        EpicsSignal,
        "BurstConfigBI",
        write_pv="BurstConfigBO",
        name="burstconfig",
        kind=Kind.config,
    )
    burstCount = Component(
        EpicsSignal,
        "BurstCountLI",
        write_pv="BurstCountLO",
        name="burstcount",
        kind=Kind.config,
    )
    burstDelay = Component(
        EpicsSignal,
        "BurstDelayAI",
        write_pv="BurstDelayAO",
        name="burstdelay",
        kind=Kind.config,
    )
    burstPeriod = Component(
        EpicsSignal,
        "BurstPeriodAI",
        write_pv="BurstPeriodAO",
        name="burstperiod",
        kind=Kind.config,
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
            raise DeviceInitError(
                f"No device manager for device: {name}, and not started sim_mode: {sim_mode}. Add"
                " DeviceManager to initialization or init with sim_mode=True"
            )
        # Init variables
        self.sim_mode = sim_mode
        self.stopped = False
        self.name = name
        self.scaninfo = None
        self.timeout = 5
        self.all_channels = [
            "channelT0",
            "channelAB",
            "channelCD",
            "channelEF",
            "channelGH",
        ]
        self.all_delay_pairs = ["AB", "CD", "EF", "GH"]
        self.wait_for_connection(all_signals=True)

        # Init custom prepare class with BL specific logic
        self.custom_prepare = self.custom_prepare_cls(parent=self, **kwargs)
        if not sim_mode:
            self.device_manager = device_manager
        else:
            self.device_manager = bec_utils.DMMock()
        self.producer = self.device_manager.producer
        self._update_scaninfo()
        self._init()
        self.custom_prepare.is_ddg_okay()

    def _update_scaninfo(self) -> None:
        """Update scaninfo from BecScaninfoMixing
        This depends on device manager and operation/sim_mode
        """
        self.scaninfo = BecScaninfoMixin(self.device_manager, self.sim_mode)
        self.scaninfo.load_scan_metadata()

    def _init(self) -> None:
        """Initialize detector, filewriter and set default parameters"""
        self.custom_prepare.initialize_default_parameter()

    def set_channels(self, signal: str, value: Any, channels: List = None) -> None:
        """
        Sets value on signal in list all_channels

        Setting values works on DelayPair and DelayStatic channels.

        Args:
            signal (str): signal to set
            value (Any): value to set
            channels (List, optional): list of channels to set. Defaults to self.all_channels.

        """
        if not channels:
            channels = self.all_channels
        for chname in channels:
            channel = getattr(self, chname, None)
            if not channel:
                continue
            if signal in channel.component_names:
                getattr(channel, signal).set(value)
                continue
            if "io" in channel.component_names and signal in channel.io.component_names:
                getattr(channel.io, signal).set(value)

    def stage(self) -> List[object]:
        """
         Stage device in preparation for a scan

        Internal Calls:
        - scaninfo.load_scan_metadata        : load scan metadata
        - custom_prepare.prepare_ddg         : prepare DDG for measurement

        Returns:
            List(object): list of objects that were staged

        """
        # Method idempotent, should rais ;obj;'RedudantStaging' if staged twice
        if self._staged != Staged.no:
            return super().stage()
        self.stopped = False
        self.scaninfo.load_scan_metadata()
        self.custom_prepare.prepare_ddg()
        self.custom_prepare.is_ddg_okay()
        # At the moment needed bc signal might not be reliable, BEC too fast.
        # Consider removing this overhead in future!
        time.sleep(0.05)
        return super().stage()

    def trigger(self) -> DeviceStatus:
        """Trigger the detector, called from BEC."""
        self.custom_prepare.on_trigger()
        return super().trigger()

    def pre_scan(self) -> None:
        """Pre scan hook, called before the scan starts"""
        self.custom_prepare.on_pre_scan()

    def unstage(self) -> List[object]:
        """
        Unstage device in preparation for a scan

        Returns directly if self.stopped,
        otherwise checks with self._finished
        if data acquisition on device finished (an was successful)

        Internal Calls:
        - custom_prepare.check_scanID          : check if scanID changed or detector stopped
        - custom_prepare.finished              : check if device finished acquisition (succesfully)

        Returns:
            List(object): list of objects that were unstaged
        """
        self.custom_prepare.check_scanID()
        if self.stopped is True:
            return super().unstage()
        self.custom_prepare.finished()
        self.custom_prepare.is_ddg_okay()
        self.stopped = False
        return super().unstage()

    def stop(self, *, success=False) -> None:
        """
        Stop the DDG

        #TODO check if the pulse sequence can be stopped, which PV should be called?
        """
        self.custom_prepare.is_ddg_okay()
        super().stop(success=success)
        self.stopped = True
