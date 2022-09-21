# -*- coding: utf-8 -*-
"""
Created on Tue Nov  9 16:12:47 2021

@author: mohacsi_i
"""

from ophyd import Device, Component, EpicsSignal, EpicsSignalRO, Kind
from ophyd import PositionerBase
from ophyd.pseudopos import pseudo_position_argument, real_position_argument, PseudoSingle, PseudoPositioner


class DelayStatic(Device):
    """ Static axis for the T0 output channel
        It allows setting the logic levels, but the timing is fixed.
        The signal is high after receiving the trigger until the end 
        of the holdoff period.
    """
    # Other channel stuff
    ttl_mode = Component(EpicsSignal, "OutputModeTtlSS.PROC", kind=Kind.config)
    nim_mode = Component(EpicsSignal, "OutputModeNimSS.PROC", kind=Kind.config)
    polarity = Component(EpicsSignal, "OutputPolarityBI", write_pv="OutputPolarityBO", name='polarity', kind=Kind.config)
    amplitude = Component(EpicsSignal, "OutputAmpAI", write_pv="OutputAmpAO", name='amplitude', kind=Kind.config)
    polarity = Component(EpicsSignal, "OutputOffsetAI", write_pv="OutputOffsetAO", name='offset', kind=Kind.config)        

    
class DummyPositioner(Device, PositionerBase):
    setpoint = Component(EpicsSignal, "DelayAO", kind=Kind.config)
    readback = Component(EpicsSignalRO, "DelayAI", kind=Kind.config)
    

class DelayPair(PseudoPositioner):
    """ Delay pair interface for DG645
    
        Virtual motor interface to a pair of signals (on the frontpanel). 
        It offers a simple delay and pulse width interface for scanning. 
    """
    # The pseudo positioner axes
    delay = Component(PseudoSingle, limits=(0, 2000.0), name='delay')
    width = Component(PseudoSingle, limits=(0, 2000.0), name='pulsewidth')         
    # The real delay axes
    ch1 = Component(DummyPositioner, name='ch1')
    ch2 = Component(DummyPositioner, name='ch2')   
    
    def __init__(self, *args, **kwargs):
        # Change suffix names before connecting (a bit of dynamic connections)
        self.__class__.__dict__['ch1'].suffix = kwargs['channel'][0]
        self.__class__.__dict__['ch2'].suffix = kwargs['channel'][1]
        del kwargs['channel']          
        # Call parent to start the connections
        super().__init__(*args, **kwargs)
        
    @pseudo_position_argument
    def forward(self, pseudo_pos):
        '''Run a forward (pseudo -> real) calculation'''
        return self.RealPosition(ch1=pseudo_pos.delay, ch2=pseudo_pos.delay+pseudo_pos.width)

    @real_position_argument
    def inverse(self, real_pos):
        '''Run an inverse (real -> pseudo) calculation'''
        return self.PseudoPosition(delay=real_pos.ch1, width=real_pos.ch2 - real_pos.ch1)    
    
    
class DelayGeneratorDG645(Device):
    """ DG645 delay generator
    
        This class implements a thin Ophyd wrapper around the Stanford Research DG645 
        digital delay generator. 
        
        Internally, the DG645 generates 8+1 signals:  A, B, C, D, E, F, G, H and T0
        Front panel outputs T0, AB, CD, EF and GH are a combination of these signals.
        Back panel outputs are directly routed signals. So signals are NOT INDEPENDENT.
        
        
        Front panel signals:
        All signals go high after their defined delays and go low after the trigger 
        holdoff period, i.e. this is the trigger window. Front panel outputs provide
        a combination of these events.
        Option 1 back panel 5V signals:
        All signals go high after their defined delays and go low after the trigger 
        holdoff period, i.e. this is the trigger window. The signals will stay high
        until the end of the window.
        Option 2 back panel 30V signals:
        All signals go high after their defined delays for ~100ns. This is fixed by 
        electronics (30V needs quite some power). This is not implemented in the 
        current device
    """
    state = Component(EpicsSignalRO, "EventStatusLI", name='status_register')
    status = Component(EpicsSignalRO, "StatusSI", name='status')

    # Front Panel
    channelT0 = Component(DelayStatic, "T0", name='T0')
    channelAB = Component(DelayPair, "", name='AB', channel="AB")
    channelCD = Component(DelayPair, "", name='CD', channel="CD")
    channelEF = Component(DelayPair, "", name='EF', channel="EF")
    channelGH = Component(DelayPair, "", name='GH', channel="GH")
        
    # Minimum time between triggers
    holdoff = Component(EpicsSignal, "TriggerHoldoffAI", write_pv="TriggerHoldoffAO", name='trigger_holdoff', kind=Kind.config)
    inhibit = Component(EpicsSignal, "TriggerInhibitMI", write_pv="TriggerInhibitMO", name='trigger_inhibit', kind=Kind.config)
    source = Component(EpicsSignal, "TriggerSourceMI", write_pv="TriggerSourceMO", name='trigger_source', kind=Kind.config)
    level = Component(EpicsSignal, "TriggerLevelAI", write_pv="TriggerLevelAO", name='trigger_level', kind=Kind.config)
    rate = Component(EpicsSignal, "TriggerRateAI", write_pv="TriggerRateAO", name='trigger_rate', kind=Kind.config)

    # Command PVs
    arm = Component(EpicsSignal, "TriggerDelayBI", write_pv="TriggerDelayBO", name='arm', kind=Kind.omitted)

    # Burst mode
    burstMode = Component(EpicsSignal, "BurstModeBI", write_pv="BurstModeBO", name='burstmode', kind=Kind.config)
    burstConfig = Component(EpicsSignal, "BurstConfigBI", write_pv="BurstConfigBO", name='burstconfig', kind=Kind.config)
    burstCount = Component(EpicsSignal, "BurstCountLI", write_pv="BurstCountLO", name='burstcount', kind=Kind.config)
    burstDelay = Component(EpicsSignal, "BurstDelayAI", write_pv="BurstDelayAO", name='burstdelay', kind=Kind.config)
    burstPeriod = Component(EpicsSignal, "BurstPeriodAI", write_pv="BurstPeriodAO", name='burstperiod', kind=Kind.config)


    def stage(self):
        """Trigger the generator by arming to accept triggers"""
        self.arm.write(1).wait()
        
    def unstage(self):
        """Stop the trigger generator from accepting triggers"""
        self.arm.write(0).wait()
    
    def burstEnable(self, count, delay, period, config="all"):
        """Enable the burst mode"""
        # Validate inputs
        count = int(count)
        assert count > 0, "Number of bursts must be positive"
        assert delay > 0, "Burst delay must be positive"
        assert period > 0, "Burst period must be positive"
        assert config in ['all', 'first'], "Supported bust configs are 'all' and 'first'"

        self.burstMode.set(1).wait()
        self.burstCount.set(count).wait()
        self.burstDelay.set(delay).wait()
        self.burstPeriod.set(period).wait()

        if config=="all":
            self.burstConfig.set(0).wait()
        elif config=="first":
            self.burstConfig.set(1).wait()
        
    def busrtDisable(self):
        """Disable the burst mode"""
        self.burstMode.set(0).wait()
    
    
    
# pair = DelayPair("DGEN01:", name="delayer", channel="CD")
dgen = DelayGeneratorDG645("X01DA-PC-DGEN:", name="delayer")
    
    
    
    
