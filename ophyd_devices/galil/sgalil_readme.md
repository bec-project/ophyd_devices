# Documentation SGalil ophyd wrapper 
Ophyd wrapper for the SGalil controller and stages.
## TODO tests and evaluate whether its good to combine common functionaltiy with galil lamni/omny/flomni controller
## Integration of the device in IPython kernel
BEC needs to be able to reach the host TCP to initiate a connection to the device.
```Python
from ophyd_devices.galil.sgalil_ophyd import SGalilMotor
samx = SGalilMotor("E", name="samx", host="129.129.122.26", port=23, sign=-1)
samy = SGalilMotor("C", name="samy", host="129.129.122.26", port=23, sign=-1)
# connect to the controller
samx.controller.on()
samx.read()
samx.move(5)
dir(samx)# for full printout of commands
# useful for development, check below socket communication with sgalil controller
samx.controller.socket_put_and_receive('#string: message_to_controller')
```
## TODO Integration of device in BEC device config!
to be tested too

## Fly scans
2D grid fly scan as implemented on the controller. 
TTL triggers are sent for the start of each line. 
The scan on the controller needs to be matched with an appropriate triggering scheme, as for instance shown in the attached scheme together with the Stanford Research DG645 device at cSAXS.
![image info](./csaxs_sgalil_triggering.png)
```Python
samx.controller.(start_y, end_y, interval_y, start_x, end_x, interval_x, exp_time, readtime)
# for example 
samx.controller.fly_grid_scan(start_y= 16, end_y= 24, interval_y= 100, start_x= 18, end_x= 17.6, interval_x= 2, exp_time= 0.08, readtime= 0.005)
```

## TODO implement line scan
Check SPEC implementation for line scans with sgalil controller, and complement it with a suitable triggering scheme of the DG645.

## TODO readout of positions in encoder
Should this be integrated in the flyscan or not. 
To be explored where this is most suitable. 

## Socket communication with sgalil controller
### vertical axis (samy)
- initiate with axis 2, C
- in motion: "MG _BG{axis_char}", e.g. "MG _BGC" , 0 or 1
- limit switch not pressed: "MG _LR{axis_char}, _LF{axis_char}" , 0 or 1
- position: "MG _TP{axis_char}/mm" , position in mm
- Axis referenced: "MG allaxref", 0 or 1
- stop all axis: "XQ#STOP,1"
- is motor on: "MG _MO{axis_char}", 0 or 1
- is thread active: "MG _XQ{thread_id}", 0 or 1
**Specific for sgalil_y**
- set_motion_speed: "SP{axis_char}=2*mm", 2mm/s is max speed
- set_final_pos: "PA{axis_char}={val:04f}*mm", target pos in mm
- start motion: "BG{axis_char}", start motion
### horizontal axis (samx) 
note: some hardware modifications were done that require access to different channels in the encoder. Encoder, motor and limit switches are not controlled by the same endpoint/axis of the controller... see below
- initiate with axis 4, E
**Specific for sgalil_x**
- set_final_pos: "targ{axis_char}={val:04f}", e.g. "targE=2.0000"
- start motion: "XQ#POSE,{axis_char}"
- For *in motion* and *limit switch not pressed* commands, 
the key changes to AXIS 5 || F, e.g. "MG _BGF"
- For *position* switch to Axis 0 || A, e.g. "MG _TPA/mm"

### flyscan 2D grid commanes:
Last command  ('XQ#SCANG') has to come with sufficient delay, important for setting up dedicated scans 
f***ast axis***
- self.socket_put_and_receive(f'a_start={start_y:.04f};a_end={end_y:.04f};speed={speed:.04f}')
***slow axis***
- self.socket_put_and_receive(f'b_start={start_x:.04f};gridmax={gridmax:d};b_step={step_grid:.04f}')
- self.socket_put_and_receive(f'nums={n_samples}') # Declare number of triggers for encoder
- self.socket_put_and_receive('XQ#SAMPLE') # Reset encoder counting --> sampling starts with 0
Start scan (be aware, needs some waiting from before)
- self.socket_put_and_receive('XQ#SCANG')
for continuous readout of encoder:
- self.socket_put_and_receive('MGsposct') # get current position counter
- self.socket_put_and_receive('MGaposavg[{ii%2000}]*10, cposavg[{ii%2000}]*10,')
