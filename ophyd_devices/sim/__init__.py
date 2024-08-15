from .sim_camera import SimCamera
from .sim_flyer import SimFlyer

SynFlyer = SimFlyer
from .sim_frameworks import SlitProxy
from .sim_monitor import SimMonitor
from .sim_positioner import SimPositioner
from .sim_signals import ReadOnlySignal, SetableSignal
from .sim_test_devices import SimPositionerWithCommFailure, SimPositionerWithController
from .sim_waveform import SimWaveform
from .sim_xtreme import SynXtremeOtf
