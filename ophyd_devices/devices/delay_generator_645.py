"""Module for integrating the Stanford Research DG645 Delay Generator"""

import enum
import time
from typing import Any, Literal

from bec_lib.logger import bec_logger
from ophyd import Component, Device, EpicsSignal, EpicsSignalRO, Kind, PVPositioner, Signal
from ophyd.pseudopos import (
    PseudoPositioner,
    PseudoSingle,
    pseudo_position_argument,
    real_position_argument,
)
from typeguard import typechecked

logger = bec_logger.logger


class DelayGeneratorError(Exception):
    """Exception raised for errors."""


class TriggerSource(enum.IntEnum):
    """
    Class for trigger options of DG645

    Used to set the trigger source of the DG645 by setting the value
    e.g. source.put(TriggerSource.Internal)
    Exp:
        TriggerSource.Internal
    """

    INTERNAL = 0
    EXT_RISING_EDGE = 1
    EXT_FALLING_EDGE = 2
    SS_EXT_RISING_EDGE = 3
    SS_EXT_FALLING_EDGE = 4
    SINGLE_SHOT = 5
    LINE = 6


class DelayStatic(Device):
    """
    Static axis for the T0 output channel

    It allows setting the logic levels, but the timing is fixed.
    The signal is high after receiving the trigger until the end
    of the holdoff period.
    """

    # Other channel stuff
    ttl_mode = Component(EpicsSignal, "OutputModeTtlSS.PROC", kind=Kind.config, auto_monitor=True)
    nim_mode = Component(EpicsSignal, "OutputModeNimSS.PROC", kind=Kind.config, auto_monitor=True)
    polarity = Component(
        EpicsSignal,
        "OutputPolarityBI",
        write_pv="OutputPolarityBO",
        name="polarity",
        kind=Kind.config,
        auto_monitor=True,
    )

    amplitude = Component(
        EpicsSignal,
        "OutputAmpAI",
        write_pv="OutputAmpAO",
        name="amplitude",
        kind=Kind.config,
        auto_monitor=True,
    )

    offset = Component(
        EpicsSignal,
        "OutputOffsetAI",
        write_pv="OutputOffsetAO",
        name="offset",
        kind=Kind.config,
        auto_monitor=True,
    )


class DummyPositioner(PVPositioner):
    """Dummy Positioner to set AO, AI and ReferenceMO."""

    setpoint = Component(
        EpicsSignal, "DelayAO", put_complete=True, kind=Kind.config, auto_monitor=True
    )
    readback = Component(EpicsSignalRO, "DelayAI", kind=Kind.config, auto_monitor=True)
    # TODO This currently means that a "move" is done immediately. Given that these are PVs, this may be the appropriate solution
    done = Component(Signal, value=1)
    reference = Component(
        EpicsSignal, "ReferenceMO", put_complete=True, kind=Kind.config, auto_monitor=True
    )


class DelayPair(PseudoPositioner):
    """
    Delay pair interface

    Virtual motor interface to a pair of signals (on the frontpanel - AB/CD/EF/GH).
    It offers a simple delay and pulse width interface.
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


class DelayGenerator(Device):
    """Delay Generator Stanford Research DG645. This implements an interface for the DG645 delay generator.

    The DG645 has 8 channels, each with a delay and pulse width. The channels are implemented as DelayPair objects (AB etc.).

    Signal pairs, e.g. AB, CD, EF, GH, are implemented as DelayPair objects. They
    have a TTL pulse width, delay and a reference signal to which they are being triggered.
    In addition, the io layer allows setting amplitude, offset and polarity for each pair.

    Detailed information can be found in the manual:
    https://www.thinksrs.com/downloads/pdfs/manuals/DG645m.pdf
    """

    USER_ACCESS = [
        "set_channels",
        "burst_enable",
        "burst_disable",
        "set_trigger",
        "check_if_ddg_okay",
    ]

    # PVs
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
    burstMode = Component(
        EpicsSignal, "BurstModeBI", write_pv="BurstModeBO", name="burstmode", kind=Kind.config
    )
    burstConfig = Component(
        EpicsSignal, "BurstConfigBI", write_pv="BurstConfigBO", name="burstconfig", kind=Kind.config
    )
    burstCount = Component(
        EpicsSignal, "BurstCountLI", write_pv="BurstCountLO", name="burstcount", kind=Kind.config
    )
    burstDelay = Component(
        EpicsSignal, "BurstDelayAI", write_pv="BurstDelayAO", name="burstdelay", kind=Kind.config
    )
    burstPeriod = Component(
        EpicsSignal, "BurstPeriodAI", write_pv="BurstPeriodAO", name="burstperiod", kind=Kind.config
    )

    def __init__(self, name: str, prefix: str = "", kind: Kind = None, parent=None, **kwargs):
        """Initialize the DG645 device

        Args:
            name (str):     Name of the device
            prefix (str):   PV prefix
            kind (Kind):    Kind of the device
            parent:         Parent device
        """
        super().__init__(prefix=prefix, name=name, kind=kind, parent=parent, **kwargs)

        self.all_channels = ["channelT0", "channelAB", "channelCD", "channelEF", "channelGH"]
        self.all_delay_pairs = ["AB", "CD", "EF", "GH"]

    def set_trigger(self, source: TriggerSource | int) -> None:
        """Set the trigger source of the DG645

        Args:
            source (TriggerSource | int):   The trigger source
                                            INTERNAL = 0
                                            EXT_RISING_EDGE = 1
                                            EXT_FALLING_EDGE = 2
                                            SS_EXT_RISING_EDGE = 3
                                            SS_EXT_FALLING_EDGE = 4
                                            SINGLE_SHOT = 5
                                            LINE = 6
        """
        value = int(source)
        self.source.set(value).wait()

    @typechecked
    def burst_enable(
        self, count: int, delay: float, period: float, config: Literal["all", "first"] = "all"
    ) -> None:
        """Enable burst mode with valid parameters.

        Args:
            count (int):    Number of bursts >0
            delay (float):  Delay before bursts start in seconds >=0
            period (float): Period of the bursts in seconds >0
            config (str):   Configuration of T0 duiring burst.
                            In addition, to simplify triggering of other instruments synchronously with the burst,
                            the T0 output may be configured to fire on the first delay cycle of the burst,
                            rather than for all delay cycles as is normally the case.
        """

        # Check inputs first
        if count <= 0:
            raise DelayGeneratorError(f"Count must be >0, provided: {count}")
        if delay < 0:
            raise DelayGeneratorError(f"Delay must be >=0, provided: {delay}")
        if period <= 0:
            raise DelayGeneratorError(f"Period must be >0, provided: {period}")

        self.burstMode.put(1)
        self.burstCount.put(count)
        self.burstDelay.put(delay)
        self.burstPeriod.put(period)

        if config == "all":
            self.burstConfig.put(0)
        elif config == "first":
            self.burstConfig.put(1)

    def burst_disable(self) -> None:
        """Disable burst mode"""
        self.burstMode.put(0)

    def set_channels(self, signal: str, value: Any, channels: list = None) -> None:
        """
        Utility method to set signals (width, delay, amplitude, offset, polarity)
        on single of multiple channels T0, AB, CD, EF, GH.


        Args:
            signal (str)                : signal to set (width, delay, amplitude, offset, polarity)
            value (Any)                 : value to set
            channels (list, optional)   : list of channels to set. Defaults to self.all_channels
                                          ["channelT0", "channelAB", "channelCD", "channelEF", "channelGH"]
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

    def check_if_ddg_okay(self, raise_on_error: bool = False) -> None:
        """
        Utility method to check if the DDG is okay.

        If raise_on_error is False, the method will:
        (1) check the status of the DDG,
        (2) if the status is not okay, it will try to clear the error and wait 0.5s before checking again.

        Args:
            raise_on_error (bool, optional): raise exception if DDG is not okay. Defaults to False.
        """
        sleep_time = 0.5
        status = self.status.read()[self.status.name]["value"]
        if status != "STATUS OK" and not raise_on_error:
            logger.warning(f"DDG returns {status}, trying to clear ERROR")
            # TODO check if clear_error is working
            self.clear_error.put(1)
            time.sleep(sleep_time)
            self.check_if_ddg_okay(raise_on_error=True)
        elif status != "STATUS OK":
            raise DelayGeneratorError(f"DDG failed to start with status: {status}")
