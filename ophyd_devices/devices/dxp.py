"""
Base classes for XIA xMAP and FalconX dxp system.
Falcon interfaces with the dxpSITORO epics driver, https://github.com/epics-modules/dxpSITORO.
xMAP interfaces with the dxp epics driver, https://github.com/epics-modules/dxp.

An example usage for a 4-element FalconX system. ::

    from ophyd import Component as Cpt
    from ophyd_devices.devices.dxp import Falcon, EpicsMCARecord, EpicsDXPFalcon
    from ophyd_devices.devices.areadetector.plugins import HDF5Plugin_V35 as HDF5Plugin

    class FalconX4(Falcon):

        # Attributes needed to be set for the ADBase class
        # Otherwise, ADBase will overwrite read_attrs and configuration_attrs
        # and as a result a .read() will return an empty dictionary
        # This is a shortcoming of the ADBase class and has to be fixed
        # on the highest level of the class hierarchy, one may also include specific signals of the Falcon
        # in the read_attrs and configuration_attrs, i.e. elapsed_real_time, elapsed_live_time, etc.
        _default_read_attrs = ("dxp1", "dxp2", "dxp3", "dxp4", "mca1", "mca2", "mca3", "mca4", "hdf")
        _default_configuration_attrs = ("dxp1", "dxp2", "dxp3", "dxp4", "mca1", "mca2", "mca3", "mca4", "hdf")

        # DXP parameters
        dxp1 = Cpt(EpicsDXPFalcon, "dxp1:")
        dxp2 = Cpt(EpicsDXPFalcon, "dxp2:")
        dxp3 = Cpt(EpicsDXPFalcon, "dxp3:")
        dxp4 = Cpt(EpicsDXPFalcon, "dxp4:")

        # MCA record with spectrum data
        mca1 = Cpt(EpicsMCARecord, "mca1")
        mca2 = Cpt(EpicsMCARecord, "mca2")
        mca3 = Cpt(EpicsMCARecord, "mca3")
        mca4 = Cpt(EpicsMCARecord, "mca4")

        # optionally with a HDF5 writer plugin
        hdf = Cpt(HDF5Plugin, "HDF1:")

    falcon = FalconX4("X07MB-SITORO:", name="falcon")
    falcon.collect_mode.put(0) # 0: MCA spectra, 1: MCA mapping
    falcon.preset_mode.put("Real time")
    falcon.preset_real_time.put(1)
    status = falcon.erase_start.set(1)
    status.wait()
    falcon.mca1.spectrum.get()

"""

from collections import OrderedDict

from ophyd import Component as Cpt
from ophyd import Device, EpicsSignal, EpicsSignalRO, Kind
from ophyd.areadetector import ADBase
from ophyd.areadetector import ADComponent as ADCpt
from ophyd.areadetector import EpicsSignalWithRBV
from ophyd.device import DynamicDeviceComponent as DCpt
from ophyd.mca import ROI as _ROI
from ophyd.mca import EpicsDXP, EpicsDXPBaseSystem, EpicsDXPMapping
from ophyd.mca import EpicsDXPMultiElementSystem as _EpicsDXPMultiElementSystem
from ophyd.mca import EpicsMCARecord as _EpicsMCARecord

__all__ = ("EpicsMCARecord", "EpicsDXP", "EpicsDXPFalcon", "Falcon", "Mercury", "xMAP")

# pylint: disable=protected-access


class ROI(_ROI):
    """ROI for DXP system with proper Kind settings."""

    # normal Components
    count = Cpt(EpicsSignalRO, "", lazy=True, kind=Kind.normal)
    net_count = Cpt(EpicsSignalRO, "N", lazy=True, kind=Kind.normal)

    # Config components
    preset_count = Cpt(EpicsSignal, "P", lazy=True, kind=Kind.config)
    bkgnd_chans = Cpt(EpicsSignal, "BG", lazy=True, kind=Kind.config)
    label = Cpt(EpicsSignal, "NM", lazy=True, kind=Kind.config)
    is_preset = Cpt(EpicsSignal, "IP", lazy=True, kind=Kind.config)
    hi_chan = Cpt(EpicsSignal, "HI", lazy=True, kind=Kind.config)
    lo_chan = Cpt(EpicsSignal, "LO", lazy=True, kind=Kind.config)


def add_rois(range_, **kwargs):
    """Add ROIs to the EpicsMCARecord."""
    defn = OrderedDict()

    for roi in range_:
        if not (0 <= roi < 32):
            raise ValueError("roi must be in the set [0,31]")

        attr = f"roi{roi}"
        defn[attr] = (ROI, f".R{roi}", kwargs)

    return defn


# predefined nunmber of ROIs per EpicsMCARecord
ROI_RANGE = range(0, 8)


class EpicsMCARecord(_EpicsMCARecord):
    """EpicsMCARecord with addtional fields"""

    # Calibration values
    calo = Cpt(EpicsSignal, ".CALO", kind=Kind.config)
    cals = Cpt(EpicsSignal, ".CALS", kind=Kind.config)
    calq = Cpt(EpicsSignal, ".CALQ", kind=Kind.config)
    tth = Cpt(EpicsSignal, ".TTH", kind=Kind.config)

    elapsed_real_time = Cpt(EpicsSignalRO, ".ERTM", kind=Kind.normal, auto_monitor=True)
    rois = DCpt(add_rois(ROI_RANGE, kind=Kind.normal), kind=Kind.normal)


class EpicsDXPFalcon(Device):
    """All high-level DXP parameters for each channel"""

    # Detection
    detection_filter = Cpt(EpicsSignalWithRBV, "DetectionFilter")
    detection_threshold = Cpt(EpicsSignalWithRBV, "DetectionThreshold")
    min_pulse_pair_separation = Cpt(EpicsSignalWithRBV, "MinPulsePairSeparation")

    # Pre-amp and energe range
    detector_polarity = Cpt(EpicsSignalWithRBV, "DetectorPolarity")
    decay_time = Cpt(EpicsSignalWithRBV, "DecayTime")
    risetime_optimization = Cpt(EpicsSignalWithRBV, "RisetimeOptimization")
    scale_factor = Cpt(EpicsSignalWithRBV, "ScaleFactor")

    # Presets
    preset_events = Cpt(EpicsSignalWithRBV, "PresetEvents")
    preset_mode = Cpt(EpicsSignalWithRBV, "PresetMode", string=True)
    preset_triggers = Cpt(EpicsSignalWithRBV, "PresetTriggers")
    preset_real_time = Cpt(EpicsSignalWithRBV, "PresetReal")

    # Couting statistics
    elapsed_live_time = Cpt(EpicsSignalRO, "ElapsedLiveTime", lazy=True)
    elapsed_real_time = Cpt(EpicsSignalRO, "ElapsedRealTime", lazy=True)
    elapsed_trigger_live = Cpt(EpicsSignalRO, "ElapsedTriggerLiveTime", lazy=True)
    triggers = Cpt(EpicsSignalRO, "Triggers", lazy=True)
    events = Cpt(EpicsSignalRO, "Events", lazy=True)
    input_count_rate = Cpt(EpicsSignalRO, "InputCountRate", kind=Kind.normal, auto_monitor=True)
    output_count_rate = Cpt(EpicsSignalRO, "OutputCountRate", kind=Kind.normal, auto_monitor=True)

    # Mapping
    current_pixel = Cpt(EpicsSignal, "CurrentPixel")

    # Diagnostic trace
    trace_data = Cpt(EpicsSignal, "TraceData")


class EpicsDXPFalconMultiElementSystem(EpicsDXPBaseSystem):
    """System-wide parameters as defined in dxpMED.template"""

    # Preset control
    preset_events = Cpt(EpicsSignal, "PresetEvents")
    preset_real_time = Cpt(EpicsSignal, "PresetReal")
    preset_mode = Cpt(EpicsSignal, "PresetMode", string=True)
    preset_triggers = Cpt(EpicsSignal, "PresetTriggers")

    # Acquisition control
    erase_all = Cpt(EpicsSignal, "EraseAll")
    erase_start = Cpt(EpicsSignal, "EraseStart", put_complete=True, trigger_value=1)
    start_all = Cpt(EpicsSignal, "StartAll", put_complete=True, trigger_value=1)
    stop_all = Cpt(EpicsSignal, "StopAll")

    # Status
    set_acquire_busy = Cpt(EpicsSignal, "SetAcquireBusy")
    acquire_busy = Cpt(EpicsSignal, "AcquireBusy")
    status_all = Cpt(EpicsSignal, "StatusAll")
    status_all_once = Cpt(EpicsSignal, "StatusAllOnce")
    acquiring = Cpt(EpicsSignal, "Acquiring")

    # Reading
    read_all = Cpt(EpicsSignal, "ReadAll", kind=Kind.omitted)
    read_all_once = Cpt(EpicsSignal, "ReadAllOnce", kind=Kind.omitted)

    # As a debugging note, if snl_connected is not '1', your IOC is
    # misconfigured:
    snl_connected = Cpt(EpicsSignal, "SNL_Connected")

    # High-level parameters
    copy_decay_time = Cpt(EpicsSignal, "CopyDecayTime", kind=Kind.omitted)
    copy_detection_filter = Cpt(EpicsSignal, "CopyDetectionFilter", kind=Kind.omitted)
    copy_detection_threshold = Cpt(EpicsSignal, "CopyDetectionThreshold", kind=Kind.omitted)
    copy_detector_polarity = Cpt(EpicsSignal, "CopyDetectorPolarity", kind=Kind.omitted)
    copy_min_pulse_pair_separation = Cpt(
        EpicsSignal, "CopyMinPulsePairSeparation", kind=Kind.omitted
    )
    copt_risetime_optimization = Cpt(EpicsSignal, "CopyRisetimeOptimization", kind=Kind.omitted)
    copy_scale_factor = Cpt(EpicsSignal, "CopyScaleFactor", kind=Kind.omitted)
    read_traces = Cpt(EpicsSignal, "ReadTraces", kind=Kind.omitted)

    # ROI and SCA
    copy_roi_channel = Cpt(EpicsSignal, "CopyROIChannel", kind=Kind.omitted)
    copy_roi_energy = Cpt(EpicsSignal, "CopyROIEnergy", kind=Kind.omitted)
    copy_roi_sca = Cpt(EpicsSignal, "CopyROI_SCA", kind=Kind.omitted)

    # do_* executes the process:
    do_read_all = Cpt(EpicsSignal, "DoReadAll", kind=Kind.omitted)
    do_status_all = Cpt(EpicsSignal, "DoStatusAll", kind=Kind.omitted)
    do_read_traces = Cpt(EpicsSignal, "DoReadTraces", kind=Kind.omitted)

    # Statistics
    dead_time = Cpt(EpicsSignal, "DeadTime")
    idead_time = Cpt(EpicsSignal, "IDeadTime")
    max_elapsed_live = Cpt(EpicsSignal, "MaxElapsedLive")
    max_elapsed_real = Cpt(EpicsSignal, "MaxElapsedReal")
    max_elapsed_trigger_live = Cpt(EpicsSignal, "MaxElapsedTriggerLive")
    max_triggers = Cpt(EpicsSignal, "MaxTriggers")
    max_events = Cpt(EpicsSignal, "MaxEvents")
    max_input_count_rate = Cpt(EpicsSignal, "MaxInputCountRate")
    max_output_count_rate = Cpt(EpicsSignal, "MaxOutputCountRate")


class EpicsDxpFalconMapping(EpicsDXPMapping):
    """Mapping mode parameters as defined in dxpMapping.template"""

    auto_apply = None
    apply = None
    nd_array_mode = Cpt(EpicsSignalWithRBV, "NDArrayMode")


class Falcon(EpicsDXPFalconMultiElementSystem, EpicsDxpFalconMapping, ADBase):
    """Falcon base device"""

    # attribute required by ADBase
    port_name = ADCpt(EpicsSignalRO, "Asyn.PORT", string=True)


class EpicsDXPMultiElementSystem(_EpicsDXPMultiElementSystem):
    """System-wide parameters as defined in dxpMED.template"""

    # Override some action signals, so calling `set`` method
    # returns a waitable Status object. Otherwise the Status object is immediately done.
    erase_start = Cpt(EpicsSignal, "EraseStart", put_complete=True, trigger_value=1)
    start_all = Cpt(EpicsSignal, "StartAll", put_complete=True, trigger_value=1)

    # mca.EpicsDXPMultiElementSystem maps the EPICS records under wrong names, i.e.
    # copy_adcp_ercent_rule, copy_roic_hannel and copy_roie_nergy
    copy_adc_percent_rule = Cpt(EpicsSignal, "CopyADCPercentRule")
    copy_roi_channel = Cpt(EpicsSignal, "CopyROIChannel")
    copy_roi_energy = Cpt(EpicsSignal, "CopyROIEnergy")


class Mercury(EpicsDXPMultiElementSystem, ADBase):
    """Mercury base device"""

    # attribute required by ADBase
    port_name = ADCpt(EpicsSignalRO, "Asyn.PORT", string=True)


class xMAP(EpicsDXPMultiElementSystem, EpicsDXPMapping, ADBase):
    """xMAP base device"""

    # attribute required by ADBase
    port_name = ADCpt(EpicsSignalRO, "Asyn.PORT", string=True)
