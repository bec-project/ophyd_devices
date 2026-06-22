from __future__ import annotations

from ophyd import Component as Cpt
from ophyd import Device

from ophyd_devices.devices.areadetector.plugins import ROIPlugin, StatsPlugin
from ophyd_devices.utils.bec_roi_signals.roi_processing import (
    LITERAL_ROI_PROCESSING_CONFIG,
    ROIProcessing,
)

NDPLUGIN_STATS_CONFIG: LITERAL_ROI_PROCESSING_CONFIG = {
    "basic_statistics": {
        "scalar_outputs": ["sum", "mean", "min", "max", "sigma"],
        "waveform_outputs": [],
    }
}


class ADROIProcessing(ROIProcessing):
    """ROI processing signal for AD detector setups at PSI."""

    roi1 = Cpt(ROIPlugin, prefix="ROI1:", kind="normal")
    stats1 = Cpt(StatsPlugin, prefix="STATS1:", kind="normal")

    def get_scalar_outputs(self) -> list[str]:
        scalar_outpus = []
        for v in NDPLUGIN_STATS_CONFIG.values():
            scalar_outpus.extend(v["scalar_outputs"])
        return scalar_outpus

    def get_waveform_outputs(self) -> list[str]:
        waveform_outputs = []
        for v in NDPLUGIN_STATS_CONFIG.values():
            waveform_outputs.extend(v["waveform_outputs"])
        return waveform_outputs

    def get_available_analysis_operations(self) -> list[str]:
        return list(NDPLUGIN_STATS_CONFIG.keys())


class MyDevice(Device):
    """Example device with ROI processing."""

    roi_processing = Cpt(ADROIProcessing, prefix="ROI1:", kind="normal")
