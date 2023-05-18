# Summary on communication commands for SGalilMotor
## sgalil_y - vertical axis (samy)
- Axis 2 || C
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
## sgalil_y - horizontal axis (samx) - due to hardware modifications a bit more complicated
- initiate with Axis 4 || E
**Specific for sgalil_x**
- set_final_pos: "targ{axis_char}={val:04f}", e.g. "targE=2.0000"
- start motion: "XQ#POSE,{axis_char}"
- For *in motion* and *limit switch not pressed* commands, 
the key changes to AXIS 5 || F, e.g. "MG _BGF"
- For *position* switch to Axis 0 || A, e.g. "MG _TPA/mm"
