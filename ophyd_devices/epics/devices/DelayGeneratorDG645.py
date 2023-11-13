import enum
import threading
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
from ophyd_devices.utils.socket import data_shape, data_type
from ophyd_devices.utils import bec_utils as bec_utils

from bec_lib import bec_logger

from ophyd_devices.epics.devices.bec_scaninfo_mixin import BecScaninfoMixin


logger = bec_logger.logger


class DDGError(Exception):
    pass


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

    delay_burst = Component(
        bec_utils.ConfigSignal,
        name="delay_burst",
        kind="config",
        config_storage_name="ddg_config",
    )

    delta_width = Component(
        bec_utils.ConfigSignal,
        name="delta_width",
        kind="config",
        config_storage_name="ddg_config",
    )

    additional_triggers = Component(
        bec_utils.ConfigSignal,
        name="additional_triggers",
        kind="config",
        config_storage_name="ddg_config",
    )

    polarity = Component(
        bec_utils.ConfigSignal,
        name="polarity",
        kind="config",
        config_storage_name="ddg_config",
    )

    fixed_ttl_width = Component(
        bec_utils.ConfigSignal,
        name="fixed_ttl_width",
        kind="config",
        config_storage_name="ddg_config",
    )

    amplitude = Component(
        bec_utils.ConfigSignal,
        name="amplitude",
        kind="config",
        config_storage_name="ddg_config",
    )

    offset = Component(
        bec_utils.ConfigSignal,
        name="offset",
        kind="config",
        config_storage_name="ddg_config",
    )

    thres_trig_level = Component(
        bec_utils.ConfigSignal,
        name="thres_trig_level",
        kind="config",
        config_storage_name="ddg_config",
    )

    set_high_on_exposure = Component(
        bec_utils.ConfigSignal,
        name="set_high_on_exposure",
        kind="config",
        config_storage_name="ddg_config",
    )

    set_high_on_stage = Component(
        bec_utils.ConfigSignal,
        name="set_high_on_stage",
        kind="config",
        config_storage_name="ddg_config",
    )

    set_trigger_source = Component(
        bec_utils.ConfigSignal,
        name="set_trigger_source",
        kind="config",
        config_storage_name="ddg_config",
    )

    trigger_width = Component(
        bec_utils.ConfigSignal,
        name="trigger_width",
        kind="config",
        config_storage_name="ddg_config",
    )
    premove_trigger = Component(
        bec_utils.ConfigSignal,
        name="premove_trigger",
        kind="config",
        config_storage_name="ddg_config",
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
        ddg_config=None,
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
        Signals:
            polarity (_list_, optional): _description_. Defaults to None.
            fixed_ttl_width (_list_, optional): _description_. Defaults to None.
            amplitude (_type_, optional): _description_. Defaults to None.
            offset (_type_, optional): _description_. Defaults to None.
            thres_trig_level (_type_, optional): _description_. Defaults to None.
            delay_burst (_type_, float): Add delay for triggering in software trigger mode to allow fast shutter to open. Defaults to 0.
            delta_width (_type_, float): Add width to fast shutter signal to make sure its open during acquisition. Defaults to 0.
            delta_triggers (_type_, int): Add additional triggers to burst mode (mcs card needs +1 triggers per line). Defaults to 0.
            set_high_on_exposure
            set_high_on_stage
            set_trigger_source

        """
        self.ddg_config = {
            f"{name}_delay_burst": 0,
            f"{name}_delta_width": 0,
            f"{name}_additional_triggers": 0,
            f"{name}_polarity": [1, 1, 1, 1, 1],
            f"{name}_fixed_ttl_width": [0, 0, 0, 0, 0],
            f"{name}_amplitude": 4.5,
            f"{name}_offset": 0,
            f"{name}_thres_trig_level": 2.5,
            f"{name}_set_high_on_exposure": False,
            f"{name}_set_high_on_stage": False,
            f"{name}_set_trigger_source": "SINGLE_SHOT",
            f"{name}_trigger_width": None,  # This somehow duplicates the logic of fixed_ttl_width
            f"{name}_premove_trigger": False,
        }
        if ddg_config is not None:
            [self.ddg_config.update({f"{name}_{key}": value}) for key, value in ddg_config.items()]
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
            raise DDGError("Add DeviceManager to initialization or init with sim_mode=True")
        self.device_manager = device_manager
        if not sim_mode:
            self._producer = self.device_manager.producer
        else:
            self._producer = bec_utils.MockProducer()
            self.device_manager = bec_utils.MockDeviceManager()
        self.scaninfo = BecScaninfoMixin(device_manager, sim_mode)
        self._all_channels = [
            "channelT0",
            "channelAB",
            "channelCD",
            "channelEF",
            "channelGH",
        ]
        self._all_delay_pairs = ["AB", "CD", "EF", "GH"]
        self.wait_for_connection()  # Make sure to be connected before talking to PVs
        logger.info(f"Current polarity values {self.polarity.get()}")
        self.reload_config()
        self._ddg_is_okay()
        self._stopped = False

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
        self.source.put(value)

    def _ddg_is_okay(self, raise_on_error=False) -> None:
        status = self.status.read()[self.status.name]["value"]
        if status != "STATUS OK" and not raise_on_error:
            logger.warning(f"DDG returns {status}, trying to clear ERROR")
            self.clear_error()
            time.sleep(1)
            self._ddg_is_okay(rais_on_error=True)
        elif status != "STATUS OK":
            raise DDGError(f"DDG failed to start with status: {status}")

    def set_channels(self, signal: str, value: Any, channels: List = None) -> None:
        if not channels:
            channels = self._all_channels
        for chname in channels:
            channel = getattr(self, chname, None)
            if not channel:
                continue
            if signal in channel.component_names:
                getattr(channel, signal).set(value)
                continue
            if "io" in channel.component_names and signal in channel.io.component_names:
                getattr(channel.io, signal).set(value)

    def _cleanup_ddg(self) -> None:
        self._set_trigger(getattr(TriggerSource, self.set_trigger_source.get()))

    def reload_config(self) -> None:
        for ii, channel in enumerate(self._all_channels):
            self.set_channels("polarity", self.polarity.get()[ii], channels=[channel])
        # Set polarity for eiger inverted!
        # self.set_channels("polarity", 0, channels=["channelAB"])
        self.set_channels("amplitude", self.amplitude.get())
        self.set_channels("offset", self.offset.get())
        # Setup reference
        self.set_channels(
            "reference",
            0,
            [f"channel{self._all_delay_pairs[ii]}.ch1" for ii in range(len(self._all_delay_pairs))],
        )
        for ii in range(len(self._all_delay_pairs)):
            self.set_channels(
                "reference",
                0,
                [f"channel{self._all_delay_pairs[ii]}.ch2"],
            )
        self._set_trigger(getattr(TriggerSource, self.set_trigger_source.get()))
        # Set threshold level for ext. pulses
        self.level.put(self.thres_trig_level.get())

    def _check_burst_cycle(self, status) -> None:
        """Checks burst cycle of delay generator
        Force readout, return value from end of burst cycle
        """
        return status.set_finished()
        while True:
            self.trigger_burst_readout.put(1, use_complete=True)
            if self.burst_cycle_finished.read()[self.burst_cycle_finished.name]["value"] == 1:
                self._acquisition_done = True
                status.set_finished()
                return
            if self._stopped == True:
                status.set_finished()
                break

            time.sleep(0.01)

    def stop(self, success=False):
        """Stops the DDG"""
        self._stopped = True
        self._acquisition_done = True
        super().stop(success=success)

    def stage(self):
        """Trigger the generator by arming to accept triggers"""
        self.scaninfo.load_scan_metadata()
        if self.scaninfo.scan_type == "step":
            # define parameters
            if self.set_high_on_exposure.get():
                self._set_trigger(getattr(TriggerSource, self.set_trigger_source.get()))
                num_burst_cycle = 1 + self.additional_triggers.get()

                exp_time = self.delta_width.get() + self.scaninfo.frames_per_trigger * (
                    self.scaninfo.exp_time + self.scaninfo.readout_time
                )
                total_exposure = exp_time
                delay_burst = self.delay_burst.get()
                self.burst_enable(num_burst_cycle, delay_burst, total_exposure, config="first")
                self.set_channels("delay", 0)
                # Set burst length to half of the experimental time!
                if not self.trigger_width.get():
                    self.set_channels("width", exp_time)
                else:
                    self.set_channels("width", self.trigger_width.get())
                for value, channel in zip(self.fixed_ttl_width.get(), self._all_channels):
                    logger.info(f"{value}")
                    if value != 0:
                        logger.info(f"Setting {value}")
                        self.set_channels("width", value, channels=[channel])
            else:
                self._set_trigger(getattr(TriggerSource, self.set_trigger_source.get()))
                exp_time = self.delta_width.get() + self.scaninfo.exp_time
                total_exposure = exp_time + self.scaninfo.readout_time
                delay_burst = self.delay_burst.get()
                num_burst_cycle = self.scaninfo.frames_per_trigger + self.additional_triggers.get()
                # set parameters in DDG
                self.burst_enable(num_burst_cycle, delay_burst, total_exposure, config="first")
                self.set_channels("delay", 0)
                # Set burst length to half of the experimental time!
                if not self.trigger_width.get():
                    self.set_channels("width", exp_time)
                else:
                    self.set_channels("width", self.trigger_width.get())
        elif self.scaninfo.scan_type == "fly":
            if self.set_high_on_exposure.get():
                # define parameters
                self._set_trigger(getattr(TriggerSource, self.set_trigger_source.get()))
                exp_time = (
                    self.delta_width.get()
                    + self.scaninfo.exp_time * self.scaninfo.num_points
                    + self.scaninfo.readout_time * (self.scaninfo.num_points - 1)
                )
                total_exposure = exp_time
                delay_burst = self.delay_burst.get()
                # self.additional_triggers should be 0 for self.set_high_on_exposure or remove here fully..
                num_burst_cycle = 1 + self.additional_triggers.get()
                # set parameters in DDG
                self.burst_enable(num_burst_cycle, delay_burst, total_exposure, config="first")
                self.set_channels("delay", 0.0)
                # Set burst length to half of the experimental time!
                if not self.trigger_width.get():
                    self.set_channels("width", exp_time)
                else:
                    self.set_channels("width", self.trigger_width.get())
                for value, channel in zip(self.fixed_ttl_width.get(), self._all_channels):
                    logger.info(f"{value}")
                    if value != 0:
                        logger.info(f"Setting {value}")
                        self.set_channels("width", value, channels=[channel])
            else:
                # define parameters
                self._set_trigger(getattr(TriggerSource, self.set_trigger_source.get()))
                exp_time = self.delta_width.get() + self.scaninfo.exp_time
                total_exposure = exp_time + self.scaninfo.readout_time
                delay_burst = self.delay_burst.get()
                num_burst_cycle = self.scaninfo.num_points + self.additional_triggers.get()
                # set parameters in DDG
                self.burst_enable(num_burst_cycle, delay_burst, total_exposure, config="first")
                self.set_channels("delay", 0.0)
                # Set burst length to half of the experimental time!
                if not self.trigger_width.get():
                    self.set_channels("width", exp_time)
                else:
                    self.set_channels("width", self.trigger_width.get())

        else:
            raise DDGError(f"Unknown scan type {self.scaninfo.scan_type}")

        # Check status
        self._ddg_is_okay()
        logger.info("DDG staged")
        super().stage()

    def unstage(self):
        """Stop the trigger generator from accepting triggers"""
        # self._set_trigger(getattr(TriggerSource, self.set_trigger_source.get()))
        # Check status
        self._ddg_is_okay()
        self._stopped = False
        self._acquisition_done = False
        logger.info("DDG unstaged")
        super().unstage()

    def pre_scan(self) -> None:
        if self.premove_trigger.get() == True:
            self.trigger_shot.put(1)

    def trigger(self) -> DeviceStatus:
        status = DeviceStatus(self)
        if self.premove_trigger.get() == True:
            status.set_finished()
            return status
        if self.source.read()[self.source.name]["value"] == int(TriggerSource.SINGLE_SHOT):
            self.trigger_shot.put(1)
        burst_state = threading.Thread(target=self._check_burst_cycle, args=(status,), daemon=True)
        burst_state.start()
        return status

    def burst_enable(self, count, delay, period, config="all"):
        """Enable the burst mode"""
        # Validate inputs
        count = int(count)
        assert count > 0, "Number of bursts must be positive"
        assert delay >= 0, "Burst delay must be larger than 0"
        assert period > 0, "Burst period must be positive"
        assert config in [
            "all",
            "first",
        ], "Supported bust configs are 'all' and 'first'"

        self.burstMode.put(1)
        self.burstCount.put(count)
        self.burstDelay.put(delay)
        self.burstPeriod.put(period)

        if config == "all":
            self.burstConfig.put(0)
        elif config == "first":
            self.burstConfig.put(1)

    def burst_disable(self):
        """Disable the burst mode"""
        self.burstMode.put(0)


# Automatically connect to test environmenr if directly invoked
if __name__ == "__main__":
    dgen = DelayGeneratorDG645("delaygen:DG1:", name="dgen", sim_mode=True)

    # start = time.time()
    # dgen.stage()
    # dgen.trigger()
    # print(f"Time passed for stage and trigger {time.time()-start}s")
