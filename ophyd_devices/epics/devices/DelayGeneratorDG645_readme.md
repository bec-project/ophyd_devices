# Documentation for Stanford Research DG645 device and ophyd class
This device allows to create TTL pulse for hardware trigger control of stages, detectors and more.
It can be operate on external and/or internal triggering with up to 5 signals (T0, AB, CD, EF, GH) that can be generated for single or burst triggers.
A detailed description of all functionality can be found in the [manual](https://www.thinksrs.com/downloads/pdfs/manuals/DG645m.pdf) of the device online. 
The DG645 is for instance used for hardware triggering for fly scans at cSAXS.
As for all EPIC devices, you need to ensure that the EPICS IOC is running to be able to control the device.
This readme relates to the implementation of the devices as an ophyd class done in DelayGeneratorDG645.py. 
## Integration of device in IPython kernel
To add the device within IPython, proceed with the following steps:
```Python
from ophyd_devices.epics.devices.DelayGeneratorDG645 import DelayGeneratorDG645
ddg4 = DelayGeneratorDG645(prefix='delaygen:DG1:',name='DDG4')
```
with prefix and name matching the settings within the EPIC's IOC.
## TODO Integration of device in BEC device config!
to be tested too
## DDG645 ophyd class wrapper
***Control trigger source***
```Python
ddg4.source.set(value:int)
# int between 0 and 6
```
with *int* 
- 0: internal, 1: ext rising edge, 2: ext falling edge, 3: SS ext rise edge, 4: SS ext falling edge, 5: Single shot, 6: line
See manual for more details, most commonly used 0,1,2. 
***Control width and delay of for instance channel AB***
```Python
ddg4.channelAB.width.set(1e-3) # setpoint in s
ddg4.channelAB.width.read()
ddg4.channelAB.delay.set(1e-3) # setpoint in s
```
***Burst mode***
 Check page 26 of manual for details.
```Python
ddg4.burstEnable(count:int, delay:float, period:float, config="first")
# with
# count: number of burst triggers on all channels: integer>0
# delay: initial delay before first trigger in s:>0
# period: repetition rate for triggers in s:>0, e.g. exposure time + readout time 
# config Whether T0 fires off for all or only first trigger in burst sequence: "all" or "first"
# for example
ddg4.burstEnable(50, 0.015, 0.05, config="first")
```