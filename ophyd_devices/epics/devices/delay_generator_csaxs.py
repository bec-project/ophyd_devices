import enum
from ophyd import Component

from ophyd_devices.utils import bec_utils
from ophyd_devices.epics.devices.psi_delay_generator_base import (
    PSIDelayGeneratorBase,
    DDGCustomMixin,
)

from bec_lib import bec_logger


logger = bec_logger.logger


class DelayGeneratorError(Exception):
    """Exception raised for errors in the Delay Generator."""


class TriggerSource(enum.IntEnum):
    """Trigger source options for DG645"""

    INTERNAL = 0
    EXT_RISING_EDGE = 1
    EXT_FALLING_EDGE = 2
    SS_EXT_RISING_EDGE = 3
    SS_EXT_FALLING_EDGE = 4
    SINGLE_SHOT = 5
    LINE = 6


class DDGSetup(DDGCustomMixin):
    """
    Mixin class for custom DelayGenerator logic

    This class is used to implement BL specific logic for the DDG.
    It is used in the PSIDelayGeneratorBase class.
    """

    def initialize_default_parameter(self) -> None:
        """Initialize default parameters for DDG"""
        for ii, channel in enumerate(self.parent.all_channels):
            self.parent.set_channels("polarity", self.parent.polarity.get()[ii], channels=[channel])

        self.parent.set_channels("amplitude", self.parent.amplitude.get())
        self.parent.set_channels("offset", self.parent.offset.get())
        # Setup reference
        self.parent.set_channels(
            "reference",
            0,
            [
                f"channel{self.parent.all_delay_pairs[ii]}.ch1"
                for ii in range(len(self.parent.all_delay_pairs))
            ],
        )
        for ii, pair in enumerate(self.parent.all_delay_pairs):
            self.parent.set_channels(
                "reference",
                0,
                [f"channel{pair}.ch2"],
            )
        self.parent.set_trigger(getattr(TriggerSource, self.parent.set_trigger_source.get()))
        # Set threshold level for ext. pulses
        self.parent.level.put(self.parent.thres_trig_level.get())

    def prepare_ddg(self) -> None:
        """Prepare DDG for scan"""
        # scantype "step"
        if self.parent.scaninfo.scan_type == "step":
            # define parameters
            if self.parent.set_high_on_exposure.get():
                self.parent.set_trigger(
                    getattr(TriggerSource, self.parent.set_trigger_source.get())
                )
                num_burst_cycle = 1 + self.parent.additional_triggers.get()

                exp_time = (
                    self.parent.delta_width.get()
                    + self.parent.scaninfo.frames_per_trigger
                    * (self.parent.scaninfo.exp_time + self.parent.scaninfo.readout_time)
                )
                total_exposure = exp_time
                delay_burst = self.parent.delay_burst.get()
                self.parent.burst_enable(
                    num_burst_cycle, delay_burst, total_exposure, config="first"
                )
                self.parent.set_channels("delay", 0)
                # Set burst length to half of the experimental time!
                if not self.parent.trigger_width.get():
                    self.parent.set_channels("width", exp_time)
                else:
                    self.parent.set_channels("width", self.parent.trigger_width.get())
                for value, channel in zip(
                    self.parent.fixed_ttl_width.get(), self.parent.all_channels
                ):
                    logger.debug(f"Trying to set DDG {channel} to {value}")
                    if value != 0:
                        self.parent.set_channels("width", value, channels=[channel])
            else:
                self.parent.set_trigger(
                    getattr(TriggerSource, self.parent.set_trigger_source.get())
                )
                exp_time = self.parent.delta_width.get() + self.parent.scaninfo.exp_time
                total_exposure = exp_time + self.parent.scaninfo.readout_time
                delay_burst = self.parent.delay_burst.get()
                num_burst_cycle = (
                    self.parent.scaninfo.frames_per_trigger + self.parent.additional_triggers.get()
                )
                # set parameters in DDG
                self.parent.burst_enable(
                    num_burst_cycle, delay_burst, total_exposure, config="first"
                )
                self.parent.set_channels("delay", 0)
                # Set burst length to half of the experimental time!
                if not self.parent.trigger_width.get():
                    self.parent.set_channels("width", exp_time)
                else:
                    self.parent.set_channels("width", self.parent.trigger_width.get())
        # scantype "fly"
        elif self.parent.scaninfo.scan_type == "fly":
            if self.parent.set_high_on_exposure.get():
                # define parameters
                self.parent.set_trigger(
                    getattr(TriggerSource, self.parent.set_trigger_source.get())
                )
                exp_time = (
                    self.parent.delta_width.get()
                    + self.parent.scaninfo.exp_time * self.parent.scaninfo.num_points
                    + self.parent.scaninfo.readout_time * (self.parent.scaninfo.num_points - 1)
                )
                total_exposure = exp_time
                delay_burst = self.parent.delay_burst.get()
                # self.additional_triggers should be 0 for self.set_high_on_exposure or remove here fully..
                num_burst_cycle = 1 + self.parent.additional_triggers.get()
                # set parameters in DDG
                self.parent.burst_enable(
                    num_burst_cycle, delay_burst, total_exposure, config="first"
                )
                self.parent.set_channels("delay", 0.0)
                # Set burst length to half of the experimental time!
                if not self.parent.trigger_width.get():
                    self.parent.set_channels("width", exp_time)
                else:
                    self.parent.set_channels("width", self.parent.trigger_width.get())
                for value, channel in zip(
                    self.parent.fixed_ttl_width.get(), self.parent.all_channels
                ):
                    logger.info(f"{value}")
                    if value != 0:
                        logger.info(f"Setting {value}")
                        self.parent.set_channels("width", value, channels=[channel])
            else:
                # define parameters
                self.parent.set_trigger(
                    getattr(TriggerSource, self.parent.set_trigger_source.get())
                )
                exp_time = self.parent.delta_width.get() + self.parent.scaninfo.exp_time
                total_exposure = exp_time + self.parent.scaninfo.readout_time
                delay_burst = self.parent.delay_burst.get()
                num_burst_cycle = (
                    self.parent.scaninfo.num_points + self.parent.additional_triggers.get()
                )
                # set parameters in DDG
                self.parent.burst_enable(
                    num_burst_cycle, delay_burst, total_exposure, config="first"
                )
                self.parent.set_channels("delay", 0.0)
                # Set burst length to half of the experimental time!
                if not self.parent.trigger_width.get():
                    self.parent.set_channels("width", exp_time)
                else:
                    self.parent.set_channels("width", self.parent.trigger_width.get())

        else:
            raise Exception(f"Unknown scan type {self.parent.scaninfo.scan_type}")

    def on_trigger(self) -> None:
        """Trigger DDG"""
        if self.parent.source.read()[self.parent.source.name]["value"] == TriggerSource.SINGLE_SHOT:
            self.parent.trigger_shot.put(1)

    def check_scanID(self) -> None:
        """Checks if scanID has changed and stops the scan if it has"""
        old_scanID = self.parent.scaninfo.scanID
        self.parent.scaninfo.load_scan_metadata()
        if self.parent.scaninfo.scanID != old_scanID:
            self.parent.stopped = True

    def finished(self) -> None:
        """Checks if DDG finished acquisition"""

    def on_pre_scan(self) -> None:
        """Call by pre scan hook, action executed before scan starts"""
        if self.parent.premove_trigger.get() is True:
            self.parent.trigger_shot.put(1)


class DelayGeneratorcSAXS(PSIDelayGeneratorBase):
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

    custom_prepare_cls = DDGSetup

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
        """Signals for the DG645 configured via Device config

        Args:
            name (_type_): _description_
            prefix (str, optional): _description_. Defaults to "".
            kind (_type_, optional): _description_. Defaults to None.
            read_attrs (_type_, optional): _description_. Defaults to None.
            configuration_attrs (_type_, optional): _description_. Defaults to None.
            parent (_type_, optional): _description_. Defaults to None.
            device_manager (_type_, optional): _description_. Defaults to None.
        Signals from ddg_config (device coinfig):
            polarity (_list_, optional): Polarity for different channels
            fixed_ttl_width (_list_, optional): If TTL pulse should get fixed width
            amplitude (_type_, optional): Amplitude of trigger signal
            offset (_type_, optional): _description_. Defaults to None.
            thres_trig_level (_type_, optional): Threshold of trigger amplitude
            delay_burst (_type_, float): Add delay for triggering in software trigger mode to allow fast shutter to open. Defaults to 0.
            delta_width (_type_, float): Add width to fast shutter signal to make sure its open during acquisition. Defaults to 0.
            delta_triggers (_type_, int): Add additional triggers to burst mode (mcs card needs +1 triggers per line). Defaults to 0.
            set_high_on_exposure : Set signal high on exposure
            set_high_on_stage : Set high on stage
            set_trigger_source : Specify default trigger source
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
            # pylint: disable=expression-not-assigned
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

    def set_trigger(self, trigger_source: TriggerSource) -> None:
        """Set trigger source on DDG - possible values defined in TriggerSource enum"""
        value = int(trigger_source)
        self.source.put(value)

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
        ], "Supported burst configs are 'all' and 'first'"

        self.burstMode.put(1)
        self.burstCount.put(count)
        self.burstDelay.put(delay)
        self.burstPeriod.put(period)

        if config == "all":
            self.burstConfig.put(0)
        elif config == "first":
            self.burstConfig.put(1)

    def burst_disable(self):
        """Disable burst mode"""
        self.burstMode.put(0)

    def stage(self):
        """Customized stage function"""


# Automatically connect to test environmenr if directly invoked
if __name__ == "__main__":
    dgen = DelayGeneratorcSAXS("delaygen:DG1:", name="dgen", sim_mode=True)
