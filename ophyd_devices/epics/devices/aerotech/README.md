







## Integration log for the Ophyd integration for the Aerotech Automation1 EPICS IOC


## Avoid the safespace API!!!

The properly documented beamline scripting interface was meant for exernal users. Hence, it is idiotproof and only offers a very limited functionality, making it completely unsuitable for serious development. Anyhing more complicated should go through the undocumented scan API under 'bec/scan_server/scan_plugins'. The interface is a bit inconcvenient and there's no documentation, but there are sufficient code examples to get going, but it's quite picky about some small details (that are not documented). Note that the scan plugins will probably migrate to beamline repositories in the future.

## Differences to vanilla Bluesky

Unfortunately the BEC is not 100% compatible with Bluesky, thus some changes are also required from the ophyd layer.

### Event model

The BEC has it's own event model, that's different from vanilla Bluesky. Particularly every standard scan is framed between **stage --> ... --> complete --> unstage**. So:

  - **Bluesky stepper**: configure --> stage --> Nx(trigger+read) --> unstage
  - **Bluesky flyer**: configure --> kickoff --> complete --> collect
  - **BEC stepper**: stage --> configure --> Nx(trigger+ read) --> complete --> unstage
  - **BEC flyer**: stage --> configure --> kickoff --> complete --> complete --> unstage

What's more is that unless it's explicitly specified in the scan, **ALL** ophyd devices (even listeners) get staged and unstaged for every scan. This either makes device management mandatory or raises the need to explicitly prevent this in custom scans.

### Scan server hangs

Unfortunately a common behavior.

### Class 

The DeviceServer's instantiates the ophyd devices from a dictionary. Therefore all arguments of '__init__(self, ...)' must be explicity named, you can't use the shorthand '__init__(self, *args, **kwargs)'.

'''python
# Wrong example
#class aa1Controller(Device):
#    def __init__(self, *args, **kwargs):
#        super().__init__(*args, **kwargs)
#        self._foo = "bar"

# Right example
class aa1Controller(Device):
    def __init__(self, prefix="", *, name, kind=None, read_attrs=None, configuration_attrs=None, parent=None, **kwargs):
        super().__init__(prefix=prefix, name=name, kind=kind, read_attrs=read_attrs, configuration_attrs=configuration_attrs, parent=parent, **kwargs)
        self._foo = "bar"
'''

### Status objects (futures)

This is a major time sink. Bluesky usually just calls 'StatusBase.wait()', and it doesn't even check the type, i.e. it works with anything that resembles an ophyd future. However the BEC adds it's own subscription that has some inconveniences...

#### DeviceStatus must have a device
Since the BEC wants to subscribe to it, it needs a device to subscribe.
'''python
# Wrong example
#    def complete(self):
#        status = Status()
#        return status

# Right example 
    def complete(self):
        status = Status(self)
        return status
'''

#### The device of the status shouldn't be a dynamically created object
For some reason it can't be a dynamically created ophyd object.
'''python
# Wrong example
#    def complete(self):
#        self.mon = EpicsSignal("PV-TO-MONITOR")
#        status = SubscriptionStatus(self.mon, self._mon_cb, ...)
#        return status

# Right example 
    def complete(self):
        status = SubscriptionStatus(self.mon, self._mon_cb, ...)
        return status        
'''


### Scans

Important to know that 'ScanBase.num_pos' must be set to 1 at the end of the scan. Otherwise the bec_client will just hang.




'''python
class AeroScriptedSequence(FlyScanBase):
    def __init__(self, *args, parameter: dict = None, **kwargs):
        super().__init__(parameter=parameter, **kwargs)
        self.num_pos = 0

    def cleanup(self):
        self.num_pos = 1
        return super().cleanup()
'''

Note that is often set from a  device progress that requires additional capability from the Ophyd device to report it's current progress. 
'''
class ProggressMotor(EpicsMotor):
    SUB_PROGRESS = "progress"

    def __init__(self, prefix="", *, name, kind=None, read_attrs=None, configuration_attrs=None, parent=None, **kwargs):
        super().__init__(prefix=prefix, name=name, kind=kind, read_attrs=read_attrs, configuration_attrs=configuration_attrs, parent=parent, **kwargs)
        self.subscribe(self._progress_update, run=False)

    def _progress_update(self, value, **kwargs) -> None:
        """Progress update on the scan"""
        if not self.moving:
            self._run_subs( sub_type="progress", value=1, max_value=1, done=1, )
        else:
            progress = np.abs( (value-self._startPosition)/(self._targetPosition-self._startPosition) )
            self._run_subs(sub_type="progress", value=progress, max_value=1, done=np.isclose(1, progress, 1e-3) )
'''

calculated 

Otherwise 










































