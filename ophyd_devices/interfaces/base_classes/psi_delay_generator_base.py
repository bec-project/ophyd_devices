import time
from typing import Any

from bec_lib import bec_logger
from ophyd import (
    Component,
    Device,
    DeviceStatus,
    EpicsSignal,
    EpicsSignalRO,
    Kind,
    PVPositioner,
    Signal,
)
from ophyd.device import Staged

from ophyd_devices.devices.delay_generator_645 import DelayGenerator
from ophyd_devices.interfaces.base_classes.psi_device_base import CustomPrepare, PSIDeviceBase
from ophyd_devices.utils import bec_utils
from ophyd_devices.utils.bec_scaninfo_mixin import BecScaninfoMixin

logger = bec_logger.logger


class DelayGeneratorNotOkay(Exception):
    """Custom exception class for DelayGenerator errors"""


# class DDGCustomMixin:
#     """
#     Mixin class for custom DelayGenerator logic within PSIDelayGeneratorBase.

#     This class provides a parent class for implementation of BL specific logic of the device.
#     It is also possible to pass implementing certain methods, e.g. finished or on_trigger,
#     based on the setup and desired operation mode at the beamline.

#     Args:
#         parent (object): instance of PSIDelayGeneratorBase
#         **kwargs: keyword arguments
#     """

#     def __init__(self, *_args, parent: Device = None, **_kwargs) -> None:
#         self.parent = parent

#     def initialize_default_parameter(self) -> None:
#         """
#         Method to initialize default parameters for DDG.

#         Called upon initiating the base class.
#         It should be used to set the DDG default parameters.
#         These may include: amplitude, offsets, delays, etc.
#         """

#     def prepare_ddg(self) -> None:
#         """
#         Method to prepare the DDG for the upcoming scan.

#         Called by the stage method of the base class.
#         It should be used to set the DDG parameters for the upcoming scan.
#         """

#     def on_trigger(self) -> None:
#         """Method executed upon trigger call in parent class"""

#     def finished(self) -> None:
#         """Method to check if DDG is finished with the scan"""

#     def on_pre_scan(self) -> None:
#         """
#         Method executed upon pre_scan call in parent class.

#         Covenient to implement time sensitive actions to be executed right before start of the scan.
#         Example could be to open the shutter by triggering a pulse via pre_scan.
#         """

#     def check_scan_id(self) -> None:
#         """Method to check if there is a new scan_id, called by stage."""

#     def is_ddg_okay(self, raise_on_error=False) -> None:
#         """
#         Method to check if DDG is okay

#         It checks the status PV of the DDG and tries to clear the error if it is not okay.
#         It will rerun itself and raise DelayGeneratorNotOkay if DDG is still not okay.

#         Args:
#             raise_on_error (bool, optional): raise exception if DDG is not okay. Defaults to False.
#         """
#         status = self.parent.status.read()[self.parent.status.name]["value"]
#         if status != "STATUS OK" and not raise_on_error:
#             logger.warning(f"DDG returns {status}, trying to clear ERROR")
#             self.parent.clear_error()
#             time.sleep(1)
#             self.is_ddg_okay(raise_on_error=True)
#         elif status != "STATUS OK":
#             raise DelayGeneratorNotOkay(f"DDG failed to start with status: {status}")


class PSIDelayGeneratorBase(PSIDeviceBase, DelayGenerator):
    """
    Abstract base class for DelayGenerator DG645

    This class implements a thin Ophyd wrapper around the Stanford Research DG645
    digital delay generator.

    The DG645 generates 8+1 signals: A, B, C, D, E, F, G, H and T0. Front panel outputs
    T0, AB, CD, EF and GH are combinations of these signals. Back panel outputs are
    directly routed signals. Signals are not independent.

    Signal pairs, e.g. AB, CD, EF, GH, are implemented as DelayPair objects. They
    have a TTL pulse width, delay and a reference signal to which they are being triggered.
    In addition, the io layer allows setting amplitude, offset and polarity for each pair.

    Detailed information can be found in the manual:
    https://www.thinksrs.com/downloads/pdfs/manuals/DG645m.pdf

    Class attributes:
        custom_prepare_cls (object): class for custom prepare logic (BL specific)

    Args:
        prefix (str)                : EPICS PV prefix for component (optional)
        name (str)                  : name of the device, as will be reported via read()
        kind (str)                  : member of class 'ophydobj.Kind', defaults to Kind.normal
                                        omitted -> readout ignored for read 'ophydobj.read()'
                                        normal -> readout for read
                                        config -> config parameter for 'ophydobj.read_configuration()'
                                        hinted -> which attribute is readout for read
        read_attrs (list)           : sequence of attribute names to read
        configuration_attrs (list)  : sequence of attribute names via config_parameters
        parent (object)             : instance of the parent device
        device_manager (object)     : bec device manager
        sim_mode (bool)             : simulation mode, if True, no device manager is required
        **kwargs                    : keyword arguments
        attributes                  : lazy_wait_for_connection : bool
    """

    # Custom_prepare_cls
    # custom_prepare_cls = DDGCustomMixin

    # SUB_PROGRESS = "progress"
    # SUB_VALUE = "value"
    # _default_sub = SUB_VALUE

    # def __init__(
    #     self,
    #     prefix="",
    #     *,
    #     name,
    #     kind=None,
    #     read_attrs=None,
    #     configuration_attrs=None,
    #     parent=None,
    #     device_manager=None,
    #     sim_mode=False,
    #     **kwargs,
    # ):
    #     super().__init__(
    #         prefix=prefix,
    #         name=name,
    #         kind=kind,
    #         read_attrs=read_attrs,
    #         configuration_attrs=configuration_attrs,
    #         parent=parent,
    #         **kwargs,
    #     )
    #     if device_manager is None and not sim_mode:
    #         raise DeviceInitError(
    #             f"No device manager for device: {name}, and not started sim_mode: {sim_mode}. Add"
    #             " DeviceManager to initialization or init with sim_mode=True"
    #         )
    #     # Init variables
    #     self.sim_mode = sim_mode
    #     self.stopped = False
    #     self.name = name
    #     self.scaninfo = None
    #     self.timeout = 5
    #     self.all_channels = ["channelT0", "channelAB", "channelCD", "channelEF", "channelGH"]
    #     self.all_delay_pairs = ["AB", "CD", "EF", "GH"]
    #     self.wait_for_connection(all_signals=True)

    #     # Init custom prepare class with BL specific logic
    #     self.custom_prepare = self.custom_prepare_cls(parent=self, **kwargs)
    #     if not sim_mode:
    #         self.device_manager = device_manager
    #     else:
    #         self.device_manager = bec_utils.DMMock()
    #     self.connector = self.device_manager.connector
    #     self._update_scaninfo()
    #     self._init()

    # def _update_scaninfo(self) -> None:
    #     """
    #     Method to updated scaninfo from BEC.

    #     In sim_mode, scaninfo output is mocked - see bec_scaninfo_mixin.py
    #     """
    #     self.scaninfo = BecScaninfoMixin(self.device_manager, self.sim_mode)
    #     self.scaninfo.load_scan_metadata()

    # def _init(self) -> None:
    #     """Method to initialize custom parameters of the DDG."""
    #     self.custom_prepare.initialize_default_parameter()
    #     self.custom_prepare.is_ddg_okay()

    # def set_channels(self, signal: str, value: Any, channels: list = None) -> None:
    #     """
    #     Method to set signals on DelayPair and DelayStatic channels.

    #     Signals can be set on the DelayPair and DelayStatic channels. The method checks
    #     if the signal is available on the channel and sets it. It works for both, DelayPair
    #     and Delay Static although signals are hosted in different layers.

    #     Args:
    #         signal (str)                : signal to set (width, delay, amplitude, offset, polarity)
    #         value (Any)                 : value to set
    #         channels (list, optional)   : list of channels to set. Defaults to self.all_channels (T0,AB,CD,EF,GH)
    #     """
    #     if not channels:
    #         channels = self.all_channels
    #     for chname in channels:
    #         channel = getattr(self, chname, None)
    #         if not channel:
    #             continue
    #         if signal in channel.component_names:
    #             getattr(channel, signal).set(value)
    #             continue
    #         if "io" in channel.component_names and signal in channel.io.component_names:
    #             getattr(channel.io, signal).set(value)

    # def set_trigger(self, trigger_source: TriggerSource) -> None:
    #     """Set trigger source on DDG - possible values defined in TriggerSource enum"""
    #     value = int(trigger_source)
    #     self.source.put(value)

    # def burst_enable(self, count, delay, period, config="all"):
    #     """Enable the burst mode"""
    #     # Validate inputs
    #     count = int(count)
    #     assert count > 0, "Number of bursts must be positive"
    #     assert delay >= 0, "Burst delay must be larger than 0"
    #     assert period > 0, "Burst period must be positive"
    #     assert config in ["all", "first"], "Supported burst configs are 'all' and 'first'"

    #     self.burstMode.put(1)
    #     self.burstCount.put(count)
    #     self.burstDelay.put(delay)
    #     self.burstPeriod.put(period)

    #     if config == "all":
    #         self.burstConfig.put(0)
    #     elif config == "first":
    #         self.burstConfig.put(1)

    # def burst_disable(self):
    #     """Disable burst mode"""
    #     self.burstMode.put(0)

    # def stage(self) -> list[object]:
    #     """
    #     Method to stage the device.

    #     Called in preparation for a scan.

    #     Internal Calls:
    #     - scaninfo.load_scan_metadata        : load scan metadata
    #     - custom_prepare.prepare_ddg         : prepare DDG for measurement
    #     - is_ddg_okay                        : check if DDG is okay

    #     Returns:
    #         list(object): list of objects that were staged
    #     """
    #     if self._staged != Staged.no:
    #         return super().stage()
    #     self.stopped = False
    #     self.scaninfo.load_scan_metadata()
    #     self.custom_prepare.prepare_ddg()
    #     self.custom_prepare.is_ddg_okay()
    #     # At the moment needed bc signal might not be reliable, BEC too fast.
    #     # Consider removing this overhead in future!
    #     time.sleep(0.05)
    #     return super().stage()

    # def trigger(self) -> DeviceStatus:
    #     """
    #     Method to trigger the acquisition.

    #     Internal Call:
    #     - custom_prepare.on_trigger  : execute BL specific action
    #     """
    #     self.custom_prepare.on_trigger()
    #     return super().trigger()

    # def pre_scan(self) -> None:
    #     """
    #     Method pre_scan gets executed directly before the scan

    #     Internal Call:
    #     - custom_prepare.on_pre_scan  : execute BL specific action
    #     """
    #     self.custom_prepare.on_pre_scan()

    # def unstage(self) -> list[object]:
    #     """
    #     Method unstage gets called at the end of a scan.

    #     If scan (self.stopped is True) is stopped, returns directly.
    #     Otherwise, checks if the DDG finished acquisition

    #     Internal Calls:
    #     - custom_prepare.check_scan_id          : check if scan_id changed or detector stopped
    #     - custom_prepare.finished              : check if device finished acquisition (succesfully)
    #     - is_ddg_okay                          : check if DDG is okay

    #     Returns:
    #         list(object): list of objects that were unstaged
    #     """
    #     self.custom_prepare.check_scan_id()
    #     if self.stopped is True:
    #         return super().unstage()
    #     self.custom_prepare.finished()
    #     self.custom_prepare.is_ddg_okay()
    #     self.stopped = False
    #     return super().unstage()

    # def stop(self, *, success=False) -> None:
    #     """
    #     Method to stop the DDG

    #     #TODO Check if the pulse generation can be interruppted

    #     Internal Call:
    #     - custom_prepare.is_ddg_okay          : check if DDG is okay
    #     """
    #     self.custom_prepare.is_ddg_okay()
    #     super().stop(success=success)
    #     self.stopped = True
