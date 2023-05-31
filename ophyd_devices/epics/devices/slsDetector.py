from ophyd import EpicsSignal, EpicsSignalRO, EpicsSignalWithRBV
from ophyd import CamBase, DetectorBase
from ophyd import ADComponent as ADCpt
from ophyd.areadetector.plugins import FileBase


class slsDetectorCam(CamBase, FileBase):
    detector_type = ADCpt(EpicsSignalRO, "DetectorType_RBV")
    setting = ADCpt(EpicsSignalWithRBV, "Setting")
    delay_time = ADCpt(EpicsSignalWithRBV, "DelayTime")
    threshold_energy = ADCpt(EpicsSignalWithRBV, "ThresholdEnergy")
    enable_trimbits = ADCpt(EpicsSignalWithRBV, "Trimbits")
    bit_depth = ADCpt(EpicsSignalWithRBV, "BitDepth")
    num_gates = ADCpt(EpicsSignalWithRBV, "NumGates")
    num_cycles = ADCpt(EpicsSignalWithRBV, "NumCycles")
    num_frames = ADCpt(EpicsSignalWithRBV, "NumFrames")
    timing_mode = ADCpt(EpicsSignalWithRBV, "TimingMode")
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


class slsDetector(DetectorBase):
    cam = ADCpt(slsDetectorCam, "cam1:")
