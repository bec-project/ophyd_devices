"""AreaDetector Devices
"""

# isort: skip_file
from ophyd import EpicsSignal, EpicsSignalRO, EpicsSignalWithRBV
from ophyd.areadetector import ADComponent as ADCpt
from ophyd.areadetector.cam import (
    CamBase as _CamBase,
    FileBase as _FileBase,
    Andor3DetectorCam as _Andor3DetectorCam,
    PilatusDetectorCam as _PilatusDetectorCam,
    EigerDetectorCam as _EigerDetectorCam,
    ProsilicaDetectorCam as _ProsilicaDetectorCam,
    SimDetectorCam as _SimDetectorCam,
    URLDetectorCam as _URLDetectorCam,
)

__all__ = [
    "CamBase",
    "FileBase",
    "Andor3DetectorCam",
    "EigerDetectorCam",
    "PilatusDetectorCam",
    "ProsilicaDetectorCam",
    "URLDetectorCam",
    "AravisDetectorCam",
    "PylonDetectorCam",
    "VimbaDetectorCam",
]


class CamBase(_CamBase):
    pool_max_buffers = None


class FileBase(_FileBase):
    file_number_sync = None
    file_number_write = None


class Andor3DetectorCam(CamBase, _Andor3DetectorCam):
    gate_mode = ADCpt(EpicsSignalWithRBV, "GateMode")
    insertion_delay = ADCpt(EpicsSignalWithRBV, "InsertionDelay")
    mcp_gain = ADCpt(EpicsSignalWithRBV, "MCPGain")
    mcp_intelligate = ADCpt(EpicsSignalWithRBV, "MCPIntelligate")


class EigerDetectorCam(CamBase, _EigerDetectorCam): ...


class PilatusDetectorCam(CamBase, _PilatusDetectorCam): ...


class ProsilicaDetectorCam(CamBase, _ProsilicaDetectorCam): ...


class SimDetectorCam(CamBase, _SimDetectorCam): ...


class URLDetectorCam(CamBase, _URLDetectorCam): ...


class GenICam(CamBase):
    frame_rate = ADCpt(EpicsSignalWithRBV, "FrameRate")
    frame_rate_enable = ADCpt(EpicsSignalWithRBV, "FrameRateEnable")
    trigger_source = ADCpt(EpicsSignalWithRBV, "TriggerSource")
    trigger_overlay = ADCpt(EpicsSignalWithRBV, "TriggerOverlay")
    trigger_software = ADCpt(EpicsSignal, "TriggerSoftware")
    exposure_mode = ADCpt(EpicsSignalWithRBV, "ExposureMode")
    exposure_auto = ADCpt(EpicsSignalWithRBV, "ExposureAuto")
    gain_auto = ADCpt(EpicsSignalWithRBV, "GainAuto")
    pixel_format = ADCpt(EpicsSignalWithRBV, "PixelFormat")


class AravisDetectorCam(GenICam):
    ar_convert_pixel_format = ADCpt(EpicsSignalWithRBV, "ARConvertPixelFormat")
    ar_shift_dir = ADCpt(EpicsSignalWithRBV, "ARShiftDir")
    ar_shift_bits = ADCpt(EpicsSignalWithRBV, "ARShiftBits")


class VimbaDetectorCam(GenICam):
    time_stamp_mode = ADCpt(EpicsSignalWithRBV, "TimeStampMode")
    unique_id_mode = ADCpt(EpicsSignalWithRBV, "UniqueIdMode")
    convert_pixel_format = ADCpt(EpicsSignalWithRBV, "ConvertPixelFormat")


class PylonDetectorCam(GenICam):
    time_stamp_mode = ADCpt(EpicsSignalWithRBV, "TimeStampMode")
    unique_id_mode = ADCpt(EpicsSignalWithRBV, "UniqueIdMode")
    convert_pixel_format = ADCpt(EpicsSignalWithRBV, "ConvertPixelFormat")
    convert_bit_align = ADCpt(EpicsSignalWithRBV, "ConvertBitAlign")
    convert_shift_bits = ADCpt(EpicsSignalWithRBV, "ConvertShiftBits")


class SLSDetectorCam(CamBase, FileBase):
    detector_type = ADCpt(EpicsSignalRO, "DetectorType_RBV")
    setting = ADCpt(EpicsSignalWithRBV, "Setting")
    delay_time = ADCpt(EpicsSignalWithRBV, "DelayTime")
    threshold_energy = ADCpt(EpicsSignalWithRBV, "ThresholdEnergy")
    enable_trimbits = ADCpt(EpicsSignalWithRBV, "Trimbits")
    bit_depth = ADCpt(EpicsSignalWithRBV, "BitDepth")
    num_gates = ADCpt(EpicsSignalWithRBV, "NumGates")
    num_cycles = num_images = ADCpt(EpicsSignalWithRBV, "NumCycles")
    num_frames = ADCpt(EpicsSignalWithRBV, "NumFrames")
    trigger_mode = timing_mode = ADCpt(EpicsSignalWithRBV, "TimingMode")
    trigger_software = ADCpt(EpicsSignal, "TriggerSoftware")
    high_voltage = ADCpt(EpicsSignalWithRBV, "HighVoltage")
    # Receiver and data callback
    receiver_mode = ADCpt(EpicsSignalWithRBV, "ReceiverMode")
    receiver_stream = ADCpt(EpicsSignalWithRBV, "ReceiverStream")
    enable_data = ADCpt(EpicsSignalWithRBV, "UseDataCallback")
    missed_packets = ADCpt(EpicsSignalRO, "ReceiverMissedPackets_RBV")
    # Direct settings access
    setup_file = ADCpt(EpicsSignal, "SetupFile")
    load_setup = ADCpt(EpicsSignal, "LoadSetup")
    command = ADCpt(EpicsSignal, "Command")
    # Mythen 3
    counter_mask = ADCpt(EpicsSignalWithRBV, "CounterMask")
    counter1_threshold = ADCpt(EpicsSignalWithRBV, "Counter1Threshold")
    counter2_threshold = ADCpt(EpicsSignalWithRBV, "Counter2Threshold")
    counter3_threshold = ADCpt(EpicsSignalWithRBV, "Counter3Threshold")
    gate1_delay = ADCpt(EpicsSignalWithRBV, "Gate1Delay")
    gate1_width = ADCpt(EpicsSignalWithRBV, "Gate1Width")
    gate2_delay = ADCpt(EpicsSignalWithRBV, "Gate2Delay")
    gate2_width = ADCpt(EpicsSignalWithRBV, "Gate2Width")
    gate3_delay = ADCpt(EpicsSignalWithRBV, "Gate3Delay")
    gate3_width = ADCpt(EpicsSignalWithRBV, "Gate3Width")
    # Moench
    json_frame_mode = ADCpt(EpicsSignalWithRBV, "JsonFrameMode")
    json_detector_mode = ADCpt(EpicsSignalWithRBV, "JsonDetectorMode")
