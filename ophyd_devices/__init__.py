from .devices.sls_devices import SLSInfo, SLSOperatorMessages
from .sim.sim_camera import SimCamera
from .sim.sim_monitor import SimMonitor, SimMonitorAsync

SynAxisMonitor = SimMonitor
SynGaussBEC = SimMonitor
from .sim.sim_positioner import SimLinearTrajectoryPositioner, SimPositioner

SynAxisOPAAS = SimPositioner
from .sim.sim_flyer import SimFlyer

SynFlyer = SimFlyer
from .sim.sim import SynDeviceOPAAS, SynDynamicComponents
from .sim.sim_frameworks import DeviceProxy, H5ImageReplayProxy, SlitProxy
from .sim.sim_signals import ReadOnlySignal
from .sim.sim_waveform import SimWaveform

SynSignalRO = ReadOnlySignal
from .devices.softpositioner import SoftPositioner
from .utils.bec_device_base import BECDeviceBase
from .utils.dynamic_pseudo import ComputedSignal
from .utils.static_device_test import launch
