from ophyd import Component

from ophyd_devices.utils import bec_utils
from ophyd_devices.epics.devices.psi_delay_generator_base import (
    PSIDelayGeneratorBase,
    DDGCustomMixin,
    TriggerSource,
)

from bec_lib import bec_logger


logger = bec_logger.logger


class DelayGeneratorError(Exception):
    """Exception raised for errors."""


class DDGSetup(DDGCustomMixin):
    """
    Mixin class for DelayGenerator logic at cSAXS.

    At cSAXS, multiple DDGs were operated at the same time. There different behaviour is
        implemented in the ddg_config signals that are passed via the device config.
    """

    def initialize_default_parameter(self) -> None:
        """Method to initialize default parameters."""
        for ii, channel in enumerate(self.parent.all_channels):
            self.parent.set_channels("polarity", self.parent.polarity.get()[ii], [channel])

        self.parent.set_channels("amplitude", self.parent.amplitude.get())
        self.parent.set_channels("offset", self.parent.offset.get())
        # Setup reference
        self.parent.set_channels(
            "reference",
            0,
            [f"channel{pair}.ch1" for pair in self.parent.all_delay_pairs],
        )
        self.parent.set_channels(
            "reference",
            0,
            [f"channel{pair}.ch2" for pair in self.parent.all_delay_pairs],
        )
        self.parent.set_trigger(getattr(TriggerSource, self.parent.set_trigger_source.get()))
        # Set threshold level for ext. pulses
        self.parent.level.put(self.parent.thres_trig_level.get())

    def prepare_ddg(self) -> None:
        """
        Method to prepare scan logic of cSAXS

        Two scantypes are supported: "step" and "fly":
        - step: Scan is performed by stepping the motor and acquiring data at each step
        - fly: Scan is performed by moving the motor with a constant velocity and acquiring data

        Custom logic for different DDG behaviour during scans.

        - set_high_on_exposure      : If True, then TTL signal is high during
                                    the full exposure time of the scan (all frames).
                                    E.g. Keep shutter open for the full scan.
        - fixed_ttl_width           : fixed_ttl_width is a list of 5 values, one for each channel.
                                    If the value is 0, then the width of the TTL pulse is determined,
                                    no matter which parameters are passed from the scaninfo for exposure time
        - set_trigger_source        : Specifies the default trigger source for the DDG. For cSAXS, relevant ones
                                    were: SINGLE_SHOT, EXT_RISING_EDGE
        """
        self.parent.set_trigger(getattr(TriggerSource, self.parent.set_trigger_source.get()))
        # scantype "step"
        if self.parent.scaninfo.scan_type == "step":
            # High on exposure means that the signal
            if self.parent.set_high_on_exposure.get():
                # caluculate parameters
                num_burst_cycle = 1 + self.parent.additional_triggers.get()

                exp_time = (
                    self.parent.delta_width.get()
                    + self.parent.scaninfo.frames_per_trigger
                    * (self.parent.scaninfo.exp_time + self.parent.scaninfo.readout_time)
                )
                total_exposure = exp_time
                delay_burst = self.parent.delay_burst.get()

                # Set individual channel widths, if fixed_ttl_width and trigger_width are combined, this can be a common call too
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
                # caluculate parameters
                exp_time = self.parent.delta_width.get() + self.parent.scaninfo.exp_time
                total_exposure = exp_time + self.parent.scaninfo.readout_time
                delay_burst = self.parent.delay_burst.get()
                num_burst_cycle = (
                    self.parent.scaninfo.frames_per_trigger + self.parent.additional_triggers.get()
                )

                # Set individual channel widths, if fixed_ttl_width and trigger_width are combined, this can be a common call too
                if not self.parent.trigger_width.get():
                    self.parent.set_channels("width", exp_time)
                else:
                    self.parent.set_channels("width", self.parent.trigger_width.get())
        # scantype "fly"
        elif self.parent.scaninfo.scan_type == "fly":
            if self.parent.set_high_on_exposure.get():
                # caluculate parameters
                exp_time = (
                    self.parent.delta_width.get()
                    + self.parent.scaninfo.exp_time * self.parent.scaninfo.num_points
                    + self.parent.scaninfo.readout_time * (self.parent.scaninfo.num_points - 1)
                )
                total_exposure = exp_time
                delay_burst = self.parent.delay_burst.get()
                num_burst_cycle = 1 + self.parent.additional_triggers.get()

                # Set individual channel widths, if fixed_ttl_width and trigger_width are combined, this can be a common call too
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
                # caluculate parameters
                exp_time = self.parent.delta_width.get() + self.parent.scaninfo.exp_time
                total_exposure = exp_time + self.parent.scaninfo.readout_time
                delay_burst = self.parent.delay_burst.get()
                num_burst_cycle = (
                    self.parent.scaninfo.num_points + self.parent.additional_triggers.get()
                )

                # Set individual channel widths, if fixed_ttl_width and trigger_width are combined, this can be a common call too
                if not self.parent.trigger_width.get():
                    self.parent.set_channels("width", exp_time)
                else:
                    self.parent.set_channels("width", self.parent.trigger_width.get())

        else:
            raise Exception(f"Unknown scan type {self.parent.scaninfo.scan_type}")
        # Set common DDG parameters
        self.parent.burst_enable(num_burst_cycle, delay_burst, total_exposure, config="first")
        self.parent.set_channels("delay", 0.0)

    def on_trigger(self) -> None:
        """Method to be executed upon trigger"""
        if self.parent.source.read()[self.parent.source.name]["value"] == TriggerSource.SINGLE_SHOT:
            self.parent.trigger_shot.put(1)

    def check_scanID(self) -> None:
        """
        Method to check if scanID has changed.

        If yes, then it changes parent.stopped to True, which will stop further actions.
        """
        old_scanID = self.parent.scaninfo.scanID
        self.parent.scaninfo.load_scan_metadata()
        if self.parent.scaninfo.scanID != old_scanID:
            self.parent.stopped = True

    def finished(self) -> None:
        """Method checks if DDG finished acquisition"""

    def on_pre_scan(self) -> None:
        """
        Method called by pre_scan hook in parent class.

        Executes trigger if premove_trigger is Trus.
        """
        if self.parent.premove_trigger.get() is True:
            self.parent.trigger_shot.put(1)


class DelayGeneratorcSAXS(PSIDelayGeneratorBase):
    """
    DG645 delay generator at cSAXS (multiple can be in use depending on the setup)

    Default values for setting up DDG.
    Note: checks of set calues are not (only partially) included, check manual for details on possible settings.
    https://www.thinksrs.com/downloads/pdfs/manuals/DG645m.pdf

    - delay_burst               : (float >=0) Delay between trigger and first pulse in burst mode
    - delta_width               : (float >= 0) Add width to fast shutter signal to make sure its open during acquisition
    - additional_triggers       : (int) add additional triggers to burst mode (mcs card needs +1 triggers per line)
    - polarity                  : (list of 0/1) polarity for different channels
    - amplitude                 : (float) amplitude voltage of TTLs
    - offset                    : (float) offset for ampltitude
    - thres_trig_level          : (float) threshold of trigger amplitude

    Custom signals for logic in different DDGs during scans (for custom_prepare.prepare_ddg):

    - set_high_on_exposure      : (bool): if True, then TTL signal should go high during the full acquisition time of a scan.
    # TODO trigger_width and fixed_ttl could be combined into single list.
    - fixed_ttl_width           : (list of either 1 or 0), one for each channel.
    - trigger_width             : (float) if fixed_ttl_width is True, then the width of the TTL pulse is set to this value.
    - set_trigger_source        : (TriggerSource) specifies the default trigger source for the DDG.
    - premove_trigger           : (bool) if True, then a trigger should be executed before the scan starts (to be implemented in on_pre_scan).
    - set_high_on_stage         : (bool) if True, then TTL signal should go high already on stage.
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
        """
        Args:
            prefix (str, optional): Prefix of the device. Defaults to "".
            name (str): Name of the device.
            kind (str, optional): Kind of the device. Defaults to None.
            read_attrs (list, optional): List of attributes to read. Defaults to None.
            configuration_attrs (list, optional): List of attributes to configure. Defaults to None.
            parent (Device, optional): Parent device. Defaults to None.
            device_manager (DeviceManagerBase, optional): DeviceManagerBase object. Defaults to None.
            sim_mode (bool, optional): Simulation mode flag. Defaults to False.
            ddg_config (dict, optional): Dictionary of ddg_config signals. Defaults to None.

        """
        # Default values for ddg_config signals
        self.ddg_config = {
            # Setup default values
            f"{name}_delay_burst": 0,
            f"{name}_delta_width": 0,
            f"{name}_additional_triggers": 0,
            f"{name}_polarity": [1, 1, 1, 1, 1],
            f"{name}_amplitude": 4.5,
            f"{name}_offset": 0,
            f"{name}_thres_trig_level": 2.5,
            # Values for different behaviour during scans
            f"{name}_fixed_ttl_width": [0, 0, 0, 0, 0],
            f"{name}_trigger_width": None,
            f"{name}_set_high_on_exposure": False,
            f"{name}_set_high_on_stage": False,
            f"{name}_set_trigger_source": "SINGLE_SHOT",
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
            device_manager=device_manager,
            sim_mode=sim_mode,
            **kwargs,
        )


if __name__ == "__main__":
    # Start delay generator in simulation mode.
    # Note: To run, access to Epics must be available.
    dgen = DelayGeneratorcSAXS("delaygen:DG1:", name="dgen", sim_mode=True)
