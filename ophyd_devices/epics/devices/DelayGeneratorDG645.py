# -*- coding: utf-8 -*-
"""
Created on Tue Nov  9 16:12:47 2021

@author: mohacsi_i
"""

import enum
import time
from ophyd import Device, Component, EpicsSignal, EpicsSignalRO, Kind
from ophyd import PVPositioner, Signal
from ophyd.pseudopos import (
    pseudo_position_argument,
    real_position_argument,
    PseudoSingle,
    PseudoPositioner,
)

from bec_lib.core import BECMessage, MessageEndpoints, RedisConnector
from bec_lib.core.file_utils import FileWriterMixin
from bec_lib.core import bec_logger

from ophyd_devices.utils.socket import data_shape, data_type


logger = bec_logger.logger
DEFAULT_EPICSSIGNAL_VALUE = object()


class DDGError(Exception):
    pass


class DDGConfigSignal(Signal):
    def get(self):
        self._readback = self.parent.ddg_configs[self.name]
        return self._readback

    def put(
        self,
        value,
        connection_timeout=1,
        callback=None,
        timeout=1,
        **kwargs,
    ):
        """Using channel access, set the write PV to `value`.

        Keyword arguments are passed on to callbacks

        Parameters
        ----------
        value : any
            The value to set
        connection_timeout : float, optional
            If not already connected, allow up to `connection_timeout` seconds
            for the connection to complete.
        use_complete : bool, optional
            Override put completion settings
        callback : callable
            Callback for when the put has completed
        timeout : float, optional
            Timeout before assuming that put has failed. (Only relevant if
            put completion is used.)
        """

        old_value = self.get()
        timestamp = time.time()
        self.parent.ddg_configs[self.name] = value
        super().put(value, timestamp=timestamp, force=True)
        self._run_subs(
            sub_type=self.SUB_VALUE,
            old_value=old_value,
            value=value,
            timestamp=timestamp,
        )

    def describe(self):
        """Provide schema and meta-data for :meth:`~BlueskyInterface.read`

        This keys in the `OrderedDict` this method returns must match the
        keys in the `OrderedDict` return by :meth:`~BlueskyInterface.read`.

        This provides schema related information, (ex shape, dtype), the
        source (ex PV name), and if available, units, limits, precision etc.

        Returns
        -------
        data_keys : OrderedDict
            The keys must be strings and the values must be dict-like
            with the ``event_model.event_descriptor.data_key`` schema.
        """
        if self._readback is DEFAULT_EPICSSIGNAL_VALUE:
            val = self.get()
        else:
            val = self._readback
        return {
            self.name: {
                "source": f"{self.parent.prefix}:{self.name}",
                "dtype": data_type(val),
                "shape": data_shape(val),
            }
        }


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
        EpicsSignal, "OutputAmpAI", write_pv="OutputAmpAO", name="amplitude", kind=Kind.config
    )
    offset = Component(
        EpicsSignal, "OutputOffsetAI", write_pv="OutputOffsetAO", name="offset", kind=Kind.config
    )


class DummyPositioner(PVPositioner):
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
    # The real delay axes
    # ch1 = Component(EpicsSignal, "DelayAI", write_pv="DelayAO", name="ch1", put_complete=True, kind=Kind.config)
    # ch2 = Component(EpicsSignal, "DelayAI", write_pv="DelayAO", name="ch2", put_complete=True, kind=Kind.config)
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


class TriggerSource(int, enum.Enum):
    INTERNAL = 0
    EXT_RISING_EDGE = 1
    EXT_FALLING_EDGE = 2
    SS_EXT_RISING_EDGE = 3
    SS_EXT_FALLING_EDGE = 4
    SINGLE_SHOT = 5
    LINE = 6


class DelayGeneratorDG645(Device):
    """DG645 delay generator

    This class implements a thin Ophyd wrapper around the Stanford Research DG645
    digital delay generator.

    Internally, the DG645 generates 8+1 signals:  A, B, C, D, E, F, G, H and T0
    Front panel outputs T0, AB, CD, EF and GH are a combination of these signals.
    Back panel outputs are directly routed signals. So signals are NOT INDEPENDENT.

    Front panel signals:
    All signals go high after their defined delays and go low after the trigger
    holdoff period, i.e. this is the trigger window. Front panel outputs provide
    a combination of these events.
    Option 1 back panel 5V signals:
    All signals go high after their defined delays and go low after the trigger
    holdoff period, i.e. this is the trigger window. The signals will stay high
    until the end of the window.
    Option 2 back panel 30V signals:
    All signals go high after their defined delays for ~100ns. This is fixed by
    electronics (30V needs quite some power). This is not implemented in the
    current device
    """

    state = Component(EpicsSignalRO, "EventStatusLI", name="status_register")
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
    # Burst mode
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

    delta_delay = Component(DDGConfigSignal, name="delta_delay", kind="config")
    delta_width = Component(DDGConfigSignal, name="delta_width", kind="config")
    delta_triggers = Component(DDGConfigSignal, name="delta_triggers", kind="config")
    polarity = Component(DDGConfigSignal, name="polarity", kind="config")
    amplitude = Component(DDGConfigSignal, name="amplitude", kind="config")
    offset = Component(DDGConfigSignal, name="offset", kind="config")
    thres_trig_level = Component(DDGConfigSignal, name="thres_trig_level", kind="config")

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
        **kwargs,
    ):
        """_summary_

        Args:
            name (_type_): _description_
            prefix (str, optional): _description_. Defaults to "".
            kind (_type_, optional): _description_. Defaults to None.
            read_attrs (_type_, optional): _description_. Defaults to None.
            configuration_attrs (_type_, optional): _description_. Defaults to None.
            parent (_type_, optional): _description_. Defaults to None.
            device_manager (_type_, optional): _description_. Defaults to None.
            polarity (_type_, optional): _description_. Defaults to None.
            amplitude (_type_, optional): _description_. Defaults to None.
            offset (_type_, optional): _description_. Defaults to None.
            thres_trig_level (_type_, optional): _description_. Defaults to None.
            delta_delay (_type_, float): Add delay for triggering in software trigger mode to allow fast shutter to open. Defaults to 0.
            delta_width (_type_, float): Add width to fast shutter signal to make sure its open during acquisition. Defaults to 0.
            delta_triggers (_type_, int): Add additional triggers to burst mode (mcs card needs +1 triggers per line). Defaults to 0.
        """
        self.ddg_configs = {
            f"{name}_delta_delay": 0,
            f"{name}_delta_width": 0,
            f"{name}_delta_triggers": 0,
            f"{name}_polarity": 1,
            f"{name}_amplitude": 2.5,  # half amplitude -> 5V peak signal
            f"{name}_offset": 0,
            f"{name}_thres_trig_level": 1.75,  # -> 3.5V
        }
        super().__init__(
            prefix=prefix,
            name=name,
            kind=kind,
            read_attrs=read_attrs,
            configuration_attrs=configuration_attrs,
            parent=parent,
            **kwargs,
        )
        self.device_manager = device_manager
        self._producer = self.device_manager.producer
        self.wait_for_connection()
        self._init_ddg()
        self._ddg_is_okay()

    def _set_trigger(self, trigger_source: TriggerSource) -> None:
        """Set trigger source to value of list below, or string
        Accepts integer 0-6 or TriggerSource.* with *
        INTERNAL = 0
        EXT_RISING_EDGE = 1
        EXT_FALLING_EDGE = 2
        SS_EXT_RISING_EDGE = 3
        SS_EXT_FALLING_EDGE = 4
        SINGLE_SHOT = 5
        LINE = 6
        """
        value = int(trigger_source)
        self.source.set(value)

    def _ddg_is_okay(self, raise_on_error=False) -> None:
        status = self.status.read()[self.status.name]["value"]
        if status != "STATUS OK" and not raise_on_error:
            logger.warning(f"DDG returns {status}, trying to clear ERROR")
            self.clear_error()
            time.sleep(1)
            self._ddg_is_okay(rais_on_error=True)
        elif status != "STATUS OK":
            raise DDGError(f"DDG failed to start with status: {status}")

    def _init_ddg_pol_allchannels(self, polarity: int = 1) -> None:
        """Set Polarity for all channels (including T0) upon init
        Args:
            polarity: int | 0 negative, 1 positive defaults to 1
        """
        self.channelT0.polarity.set(polarity)
        self.channelAB.io.polarity.set(polarity)
        self.channelCD.io.polarity.set(polarity)
        self.channelEF.io.polarity.set(polarity)
        self.channelGH.io.polarity.set(polarity)

    def _init_ddg_amp_allchannels(self, amplitude: float = 2.5) -> None:
        """Set amplitude for all channels (including T0) upon init
        Args:
            amplitude: float | defaults to 2.5 (value is equivalent to half amplitude -> 5V difference between low and high)
        """
        # TODO add check for range!!
        self.channelT0.amplitude.set(amplitude)
        self.channelAB.io.amplitude.set(amplitude)
        self.channelCD.io.amplitude.set(amplitude)
        self.channelEF.io.amplitude.set(amplitude)
        self.channelGH.io.amplitude.set(amplitude)

    def _init_ddg_offset_allchannels(self, offset: float = 0) -> None:
        """Set offset for all channels (including T0) upon init
        Args:
            offset: float | defaults to 0
        """
        # TODO add check for range!!
        self.channelT0.offset.set(offset)
        self.channelAB.io.offset.set(offset)
        self.channelCD.io.offset.set(offset)
        self.channelEF.io.offset.set(offset)
        self.channelGH.io.offset.set(offset)

    def _cleanup_ddg(self) -> None:
        self._set_trigger(TriggerSource.SINGLE_SHOT)

    def _init_ddg(self) -> None:
        self._init_ddg_pol_allchannels(self.polarity.get())
        self._init_ddg_amp_allchannels(self.amplitude.get())
        self._init_ddg_offset_allchannels(self.offset.get())
        self._set_trigger(TriggerSource.SINGLE_SHOT)
        self.level.set(self.thres_trig_level.get())

    # TODO add delta_delay, delta_width, delta triggers!

    def stage(self):
        """Trigger the generator by arming to accept triggers"""
        # TODO check PV TriggerDelayBO, seems to be a bug in the IOC

        super().stage()

    def unstage(self):
        """Stop the trigger generator from accepting triggers"""
        self._set_trigger(TriggerSource.SINGLE_SHOT)
        super().stage()

    def burstEnable(self, count, delay, period, config="all"):
        """Enable the burst mode"""
        # Validate inputs
        count = int(count)
        assert count > 0, "Number of bursts must be positive"
        assert delay >= 0, "Burst delay must be larger than 0"
        assert period > 0, "Burst period must be positive"
        assert config in ["all", "first"], "Supported bust configs are 'all' and 'first'"

        self.burstMode.set(1).wait()
        self.burstCount.set(count).wait()
        self.burstDelay.set(delay).wait()
        self.burstPeriod.set(period).wait()

        if config == "all":
            self.burstConfig.set(0).wait()
        elif config == "first":
            self.burstConfig.set(1).wait()

    def burstDisable(self):
        """Disable the burst mode"""
        self.burstMode.set(0).wait()


# Automatically connect to test environmenr if directly invoked
if __name__ == "__main__":
    dgen = DelayGeneratorDG645("X01DA-PC-DGEN:", name="delayer")
