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
        register_plugin,
        PluginBase, PluginBase_V34,
        FilePlugin, FilePlugin_V34,
        AttributePlugin, AttributePlugin_V34,
        AttrPlotPlugin, AttrPlotPlugin_V34,
        CircularBuffPlugin, CircularBuffPlugin_V34,
        CodecPlugin, CodecPlugin_V34,
        ColorConvPlugin, ColorConvPlugin_V34,
        FFTPlugin, FFTPlugin_V34,
        GatherPlugin,
        GatherNPlugin, GatherNPlugin_V31,
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
    """
    Base class for all plugins.
    """

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
    """
    Base class for all file plugins.
    """


class ColorConvPlugin_V35(
    PluginBase_V35, ColorConvPlugin_V34, version=(3, 5), version_of=ColorConvPlugin
):
    """
    Plugin to convert the color mode of NDArray data,
    https://areadetector.github.io/areaDetector/ADCore/NDPluginColorConvert.html.

    ::

        class MyDetector(ADBase):
            cc = Cpt(ColorConvPlugin_V35, 'CC1:')
    """


class HDF5Plugin_V35(
    FilePlugin_V35, HDF5Plugin_V34, version=(3, 5), version_of=HDF5Plugin
):
    """
    Plugin to save data in HDF5 format,
    https://areadetector.github.io/areaDetector/ADCore/NDFileHDF5.html.

    ::
        class MyDetector(ADBase):
            hdf = Cpt(HDF5Plugin_V35, 'HDF1:')
    """
    flush_now = Cpt(
        EpicsSignal,
        "FlushNow",
        string=True,
        doc="0=Done 1=Flush")


class ImagePlugin_V35(
    PluginBase_V35, ImagePlugin_V34, version=(3, 5), version_of=ImagePlugin
):
    """
    Plugin to convert the NDArray data into a form accessible by EPICS Channel Access clients,
    https://areadetector.github.io/areaDetector/ADCore/NDPluginStdArrays.html.

    ::

        class MyDetector(ADBase):
            image = Cpt(ImagePlugin_V35, 'image1:')
    """


class JPEGPlugin_V35(
    FilePlugin_V35, JPEGPlugin_V34, version=(3, 5), version_of=JPEGPlugin
):
    """
    Plugin to save data in JPEG format,
    https://areadetector.github.io/areaDetector/ADCore/NDFileJPEG.html.

    ::

        class MyDetector(ADBase):
            jpeg = Cpt(JPEGPlugin_V35, 'JPEG1:')
    """


class MagickPlugin_V35(
    FilePlugin_V35, MagickPlugin_V34, version=(3, 5), version_of=MagickPlugin
):
    """
    Plugin to save data in any format supported by ImageMagick/GraphicsMagick,
    https://areadetector.github.io/areaDetector/ADCore/NDFileMagick.html.

    ::

        class MyDetector(ADBase):
            magick = Cpt(MagickPlugin_V35, 'Magick1:')
    """


class NetCDFPlugin_V35(
    FilePlugin_V35, NetCDFPlugin_V34, version=(3, 5), version_of=NetCDFPlugin
):
    """
    Plugin to save data in netCDF format,
    https://areadetector.github.io/areaDetector/ADCore/NDFileNetCDF.html.

    ::

        class MyDetector(ADBase):
            netcdf = Cpt(NetCDFPlugin_V35, 'netCDF1:')
    """

class NexusPlugin_V35(
    FilePlugin_V35, NexusPlugin_V34, version=(3, 5), version_of=NexusPlugin
):
    """
    Plugin to save data in NeXus format,
    https://areadetector.github.io/areaDetector/ADCore/NDFileNexus.html.

    ::

        class MyDetector(ADBase):
            nexus = Cpt(NexusPlugin_V35, 'Nexus1:')
    """


class OverlayPlugin_V35(
    PluginBase_V35, OverlayPlugin_V34, version=(3, 5), version_of=OverlayPlugin
):
    """
    Plugin to add graphics overlay to image data,
    https://areadetector.github.io/areaDetector/ADCore/NDPluginOverlay.html.

    ::

        class MyDetector(ADBase):
            overlay = Cpt(OverlayPlugin_V35, 'Over1:')
    """


class ProcessPlugin_V313(
    PluginBase_V35, ProcessPlugin_V34, version=(3, 13), version_of=ProcessPlugin
):
    """
    Plugin to perform arithmetic processing on NDArray data,
    https://areadetector.github.io/areaDetector/ADCore/NDPluginProcess.html.

    ::

        class MyDetector(ADBase):
            process = Cpt(ProcessPlugin_V35, 'Proc1:')
    """
    low_clip = None
    high_clip = None

    low_clip_thresh = Cpt(EpicsSignalWithRBV, "LowClipThresh", kind='config')
    low_clip_value = Cpt(EpicsSignalWithRBV, "LowClipValue", kind='config')

    high_clip_thresh = Cpt(EpicsSignalWithRBV, "HighClipThresh", kind='config')
    high_clip_value = Cpt(EpicsSignalWithRBV, "HighClipValue", kind='config')


class ROIPlugin_V35(
    PluginBase_V35, ROIPlugin_V34, version=(3, 5), version_of=ROIPlugin
):
    """
    Plugin to select a ROI from NDArray data,
    https://areadetector.github.io/areaDetector/ADCore/NDPluginROI.html.

    ::

        class MyDetector(ADBase):
            roi1 = Cpt(ROIPlugin_V35, 'ROI1:')
            roi2 = Cpt(ROIPlugin_V35, 'ROI2:')
    """


class ROIStatPlugin_V35(
    PluginBase_V35, ROIStatPlugin_V34, version=(3, 5), version_of=ROIStatPlugin
):
    """
    Plugin to calculate statistics for multiple ROIs,
    https://areadetector.github.io/areaDetector/ADCore/NDPluginROIStat.html.

    ::

        class MyROIStatPlugin(ROIStatPlugin_V35):
            roi1 = Cpt(ROIStatNPlugin_V35, '1:')
            roi2 = Cpt(ROIStatNPlugin_V35, '2:')

        class MyDetector(ADBase):
            roistat = Cpt(MyROIStatPlugin, 'ROIStat1:')
    """


class ROIStatNPlugin_V35(ROIStatNPlugin_V25, version=(3, 5), version_of=ROIStatNPlugin):
    """
    Part of ROIStatPlugin
    """


class StatsPlugin_V35(
    PluginBase_V35, StatsPlugin_V34, version=(3, 5), version_of=StatsPlugin
):
    """
    Plugin to calculate statistics on NDArray data,
    https://areadetector.github.io/areaDetector/ADCore/NDPluginStats.html.

    ::

        class MyDetector(ADBase):
            stats = Cpt(StatsPlugin_V35, 'Stats1:')
    """


class TIFFPlugin_V35(
    FilePlugin_V35, TIFFPlugin_V34, version=(3, 5), version_of=TIFFPlugin
):
    """
    Plugin to save data in TIFF format,
    https://areadetector.github.io/areaDetector/ADCore/NDFileTIFF.html.

    ::

        class MyDetector(ADBase):
            tiff = Cpt(TIFFPlugin_V35, 'TIFF1:')
    """


class TransformPlugin_V35(
    PluginBase_V35, TransformPlugin_V34, version=(3, 5), version_of=TransformPlugin
):
    """
    Plugin to rotate/flip the image,
    https://areadetector.github.io/areaDetector/ADCore/NDPluginTransform.html.

    ::
        class MyDetector(ADBase):
            transform = Cpt(TransformPlugin_V35, 'Trans1:')
    """


class PvaPlugin_V35(
    PluginBase_V35, PvaPlugin_V34, version=(3, 5), version_of=PvaPlugin
):
    """
    Plugin to convert NDArray into NTNDArray accessible by PVAccess clients,
    https://areadetector.github.io/areaDetector/ADCore/NDPluginPva.html.

    ::
        class MyDetector(ADBase):
            pva = Cpt(PvaPlugin_V35, 'Pva1:')
    """


class FFTPlugin_V35(
    PluginBase_V35, FFTPlugin_V34, version=(3, 5), version_of=FFTPlugin
):
    """
    Plugin to compute 1-D or 2-D Fast Fourier Transforms,
    https://areadetector.github.io/areaDetector/ADCore/NDPluginFFT.html.

    ::
        class MyDetector(ADBase):
            fft = Cpt(FFTPlugin_V35, 'FFT1:')
    """


class ScatterPlugin_V35(
    PluginBase_V35, ScatterPlugin_V34, version=(3, 5), version_of=ScatterPlugin
):
    """
    Plugin to distribute the processing of NDArrays to multiple downstream plugins,
    https://areadetector.github.io/areaDetector/ADCore/NDPluginScatter.html.

    ::
        class MyDetector(ADBase):
            scatter = Cpt(ScatterPlugin_V35, 'Scatter1:')
    """

class GatherPlugin_V35(
    PluginBase_V35, GatherPlugin, version=(3, 5), version_of=GatherPlugin
):
    """
    Plugin to to gather NDArrays from multiple upstream plugins and merge them into a single stream,
    https://areadetector.github.io/areaDetector/ADCore/NDPluginGather.html.

    ::
        class MyGatherPlugin(GatherPlugin_V35):
            gather1 = Cpt(GatherNPlugin_V35, '', index=1)
            gather2 = Cpt(GatherNPlugin_V35, '', index=2)

        class MyDetector(ADBase):
            gather = Cpt(MyGatherPlugin, 'Gather1:')
    """


class GatherNPlugin_V35(GatherNPlugin_V31, version=(3, 5), version_of=GatherNPlugin):
    """
    Part of GatherPlugin.
    """


class PosPluginPlugin_V35(
    PluginBase_V35, PosPluginPlugin_V34, version=(3, 5), version_of=PosPlugin
):
    """
    Plugin to attach positional information to NDArrays in the form of NDAttributes,
    https://areadetector.github.io/areaDetector/ADCore/NDPluginPos.html.

    ::
        class MyDetector(ADBase):
            pos = Cpt(PosPluginPlugin_V35, 'Pos1:')
    """


class CircularBuffPlugin_V35(
    PluginBase_V35,
    CircularBuffPlugin_V34,
    version=(3, 5),
    version_of=CircularBuffPlugin
):
    """
    Plugin to check a user-defined trigger condition has been met and output triggering NDArray,
    https://areadetector.github.io/areaDetector/ADCore/NDPluginCircularBuff.html.

    ::
        class MyDetector(ADBase):
            cb = Cpt(CircularBuffPlugin_V35, 'CB1:')
    """


class AttrPlotPlugin_V35(
    PluginBase_V35, AttrPlotPlugin_V34, version=(3, 5), version_of=AttrPlotPlugin
):
    """
    Plugin to retrieve NDAttribute values, cache them and expose them as a waveform,
    https://areadetector.github.io/areaDetector/ADCore/NDPluginAttrPlot.html.

    ::
        class MyDetector(ADBase):
            attrplot = Cpt(AttrPlotPlugin_V35, 'AttrPlot1:')
    """


class TimeSeriesPlugin_V35(
    PluginBase_V35, TimeSeriesPlugin_V34, version=(3, 5), version_of=TimeSeriesPlugin
):
    """
    Plugin to create time-series data of input signals,
    https://areadetector.github.io/areaDetector/ADCore/NDPluginTimeSeries.html.

    ::
        class MyDetector(ADBase):
            ts = Cpt(TimeSeriesPlugin_V35, 'TS:')
    """


class CodecPlugin_V35(
    PluginBase_V35, CodecPlugin_V34, version=(3, 5), version_of=CodecPlugin
):
    """
    Plugin to compress and decompress NDArray data,
    https://areadetector.github.io/areaDetector/ADCore/NDPluginCodec.html.

    ::
        class MyDetector(ADBase):
            codec = Cpt(CodecPlugin_V35, 'Codec1:')
    """

    blosc_shuffle = Cpt(
        EpicsSignalWithRBV, "BloscShuffle", string=True, doc="0=None 1=Byte 2=Bit"
    )


class AttributePlugin_V35(
    PluginBase_V35, AttributePlugin_V34, version=(3, 5), version_of=AttributePlugin
):
    """
    Plugin to extract NDArray attributes and publish their values over channel access,
    https://areadetector.github.io/areaDetector/ADCore/NDPluginAttribute.html.

    ::
        class MyDetector(ADBase):
            attr = Cpt(AttributePlugin_V35, 'Attr1:')
    """

    ts_acquiring = None
    ts_control = None
    ts_current_point = None
    ts_num_points = None
    ts_read = None


@register_plugin
class BadPixelPlugin(PluginBase_V35, version=(3, 11), version_type="ADCore"):
    """
    Plugin to replace bad pixels in an NDArray,
    https://areadetector.github.io/areaDetector/ADCore/NDPluginBadPixel.html.

    ::
        class MyDetector(ADBase):
            baxpixel = Cpt(BadPixelPlugin, 'BadPix1:')
    """
    _default_suffix = "BadPix:"
    _suffix_re = r"BadPix\d:"
    _plugin_type = "NDPluginBadPixel"
