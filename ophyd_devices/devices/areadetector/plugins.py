# vi: ts=4 sw=4
"""AreaDetector up-to-date plugins.

.. _areaDetector: http://cars.uchicago.edu/software/epics/areaDetector.html
"""
# This module contains:
# - Classes like `StatsPlugin_V{X}{Y}` that are design to be counterparts to
#   AreaDetector verion X.Y.
#
# isort: skip_file

from ophyd import Component as Cpt, Device, EpicsSignal, EpicsSignalRO, EpicsSignalWithRBV

# fmt: off
from ophyd.areadetector.plugins import (
        PluginBase, PluginBase_V34,
        FilePlugin, FilePlugin_V34,
        AttributePlugin, AttributePlugin_V34,
        AttrPlotPlugin, AttrPlotPlugin_V34,
        CircularBuffPlugin, CircularBuffPlugin_V34,
        CodecPlugin, CodecPlugin_V34,
        ColorConvPlugin, ColorConvPlugin_V34,
        FFTPlugin, FFTPlugin_V34,
        HDF5Plugin, HDF5Plugin_V34,
        ImagePlugin, ImagePlugin_V34,
        JPEGPlugin, JPEGPlugin_V34,
        MagickPlugin, MagickPlugin_V34,
        NetCDFPlugin, NetCDFPlugin_V34,
        NexusPlugin, NexusPlugin_V34,
        OverlayPlugin, OverlayPlugin_V34,
        PosPlugin, PosPluginPlugin_V34,
        PvaPlugin, PvaPlugin_V34,
        ProcessPlugin, ProcessPlugin_V34,
        ROIPlugin, ROIPlugin_V34,
        ROIStatPlugin, ROIStatPlugin_V34,
        ROIStatNPlugin, ROIStatNPlugin_V25,
        ScatterPlugin, ScatterPlugin_V34,
        StatsPlugin, StatsPlugin_V34,
        TIFFPlugin, TIFFPlugin_V34,
        TimeSeriesPlugin, TimeSeriesPlugin_V34,
        TransformPlugin, TransformPlugin_V34,
)

class PluginBase_V35(PluginBase_V34, version=(3, 5), version_of=PluginBase):
    codec = Cpt(EpicsSignalRO, "Codec_RBV", string=True)
    compressed_size = Cpt(EpicsSignalRO, "CompressedSize_RBV")

    def read_configuration(self):
        ret = Device.read_configuration(self)
        source_plugin = self.source_plugin
        if source_plugin:
            ret.update(source_plugin.read_configuration())

        return ret

    def describe_configuration(self):
        ret = Device.describe_configuration(self)

        source_plugin = self.source_plugin
        if source_plugin:
            ret.update(source_plugin.describe_configuration())

        return ret


class FilePlugin_V35(
    PluginBase_V35, FilePlugin_V34, version=(3, 5), version_of=FilePlugin
):
    ...


class ColorConvPlugin_V35(
    PluginBase_V35, ColorConvPlugin_V34, version=(3, 5), version_of=ColorConvPlugin
):
    ...


class HDF5Plugin_V35(
    FilePlugin_V35, HDF5Plugin_V34, version=(3, 5), version_of=HDF5Plugin
):
    flush_now = Cpt(
        EpicsSignal,
        "FlushNow",
        string=True,
        doc="0=Done 1=Flush")


class ImagePlugin_V35(
    PluginBase_V35, ImagePlugin_V34, version=(3, 5), version_of=ImagePlugin
):
    ...


class JPEGPlugin_V35(
    FilePlugin_V35, JPEGPlugin_V34, version=(3, 5), version_of=JPEGPlugin
):
    ...


class MagickPlugin_V35(
    FilePlugin_V35, MagickPlugin_V34, version=(3, 5), version_of=MagickPlugin
):
    ...


class NetCDFPlugin_V35(
    FilePlugin_V35, NetCDFPlugin_V34, version=(3, 5), version_of=NetCDFPlugin
):
    ...


class NexusPlugin_V35(
    FilePlugin_V35, NexusPlugin_V34, version=(3, 5), version_of=NexusPlugin
):
    ...


class OverlayPlugin_V35(
    PluginBase_V35, OverlayPlugin_V34, version=(3, 5), version_of=OverlayPlugin
):
    ...


class ProcessPlugin_V35(
    PluginBase_V35, ProcessPlugin_V34, version=(3, 5), version_of=ProcessPlugin
):
    ...


class ROIPlugin_V35(
    PluginBase_V35, ROIPlugin_V34, version=(3, 5), version_of=ROIPlugin
):
    ...


class ROIStatPlugin_V35(
    PluginBase_V35, ROIStatPlugin_V34, version=(3, 5), version_of=ROIStatPlugin
):
    ...

class ROIStatNPlugin_V35(ROIStatNPlugin_V25, version=(3, 5), version_of=ROIStatNPlugin):
    ...

class StatsPlugin_V35(
    PluginBase_V35, StatsPlugin_V34, version=(3, 5), version_of=StatsPlugin
):
    ...


class TIFFPlugin_V35(
    FilePlugin_V35, TIFFPlugin_V34, version=(3, 5), version_of=TIFFPlugin
):
    ...


class TransformPlugin_V35(
    PluginBase_V35, TransformPlugin_V34, version=(3, 5), version_of=TransformPlugin
):
    ...


class PvaPlugin_V35(
    PluginBase_V35, PvaPlugin_V34, version=(3, 5), version_of=PvaPlugin
):
    ...


class FFTPlugin_V35(
    PluginBase_V35, FFTPlugin_V34, version=(3, 5), version_of=FFTPlugin
):
    ...


class ScatterPlugin_V35(
    PluginBase_V35, ScatterPlugin_V34, version=(3, 5), version_of=ScatterPlugin
):
    ...


class PosPluginPlugin_V35(
    PluginBase_V35, PosPluginPlugin_V34, version=(3, 5), version_of=PosPlugin
):
    ...


class CircularBuffPlugin_V35(
    PluginBase_V35,
    CircularBuffPlugin_V34,
    version=(3, 5),
    version_of=CircularBuffPlugin
):
    ...


class AttrPlotPlugin_V35(
    PluginBase_V35, AttrPlotPlugin_V34, version=(3, 5), version_of=AttrPlotPlugin
):
    ...


class TimeSeriesPlugin_V35(
    PluginBase_V35, TimeSeriesPlugin_V34, version=(3, 5), version_of=TimeSeriesPlugin
):
    ...


class CodecPlugin_V35(
    PluginBase_V35, CodecPlugin_V34, version=(3, 5), version_of=CodecPlugin
):
    blosc_shuffle = Cpt(
        EpicsSignalWithRBV, "BloscShuffle", string=True, doc="0=None 1=Byte 2=Bit"
    )


class AttributePlugin_V35(
    PluginBase_V35, AttributePlugin_V34, version=(3, 5), version_of=AttributePlugin
):
    ts_acquiring = None
    ts_control = None
    ts_current_point = None
    ts_num_points = None
    ts_read = None
