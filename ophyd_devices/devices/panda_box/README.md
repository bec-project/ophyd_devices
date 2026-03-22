# PandaBox Integration
Short Documentation of the PandaBox Device Integration in Ophyd Devices

## Overview

The PandaBox integration provides a base class for interfacing with PandaBox hardware from Diamond Light Source. This implementation wraps the PandaBox hardware as a `PSIDeviceBase` device, integrating it into the BEC scan interface. It uses the `pandablocks` library for communication and data acquisition. Beamline-specific implementations should use the *on_hook* methods from PSIDeviceBase to implement custom logic.

**IMPORTANT** : If the `on_connected()` method is overridden by a child class, it must always call `super().on_connected()` first to ensure proper initialization of the PandaBox device. This is implemented in the [PandaBox class](./panda_box.py). The same is true for all the other *on_hook* methods, which may contain important logic for the proper setup for the scan. Only skip them if you are sure this logic is not required.

### PandaState

The PandaBox has a PCAP module that can be used to record block values. The base integration implements logic that automatically arms/disarms the PCAP module for the BEC scan interface. Callbacks can be attached for handling status updates *add_status_callback* and data handling *add_data_callback* respectively. Below is the enum defining the various PandaBox states:

```python
class PandaState(StrEnum):
    READY = "ready"      # Ready for data acquisition
    START = "start"      # Data acquisition started
    FRAME = "frame"      # Frame data received
    END = "end"          # Data acquisition ended
    DISARMED = "disarmed"  # Device is disarmed
```

### Public API (USER ACCESS)

There are a couple of methods which are tagged as USER_ACCESS methods, and thereby also available on the proxy devices. 
These methods include:
 - `send_raw(cmd: Union[str, list[str]]) -> Any` : Send raw commands or lists of commands to the PandaBox hardware.
 - `add_status_callback(status: StatusBase, success: list[PandaState], failure: list[PandaState], check_directly: bool = True) -> str` : Register a callback to resolve status objects based on PandaBox events. PandaBox events are defined in the `PandaState` enum, which includes states like READY, START, FRAME, END, and DISARMED. These states correspond to different stages of the data acquisition of the PCAP module of the PandaBox. 
- `remove_status_callback(cb_id: str) -> None` : Remove a registered status callback using its unique callback ID (str) which is returned by *add_status_callback*.
- `add_data_callback(callback: Callable[[LITERAL_PANDA_DATA], None], data_type: PandaState = PandaState.FRAME.value) -> str` : Register a callback for processing PandaBox data. The callback function is called when data of the specified type (READY, START, FRAME, END, DATA) is received from the PandaBox. The default data type is FRAME, which corresponds to actual frame data from the PCAP module. These data frames can be inspected in pandablocks.response module.
- `remove_data_callback(cb_id: str) -> None` : Remove a registered data callback using its unique callback ID (str) which is returned by *add_data_callback*.
- `get_panda_state() -> str` : Get the current PandaBox data acquisition state as a string (ready, start, frame, end, data ).

### Other useful methods

- `convert_frame_data(frame_data: FrameData) -> dict[str, Any]` : Convert FrameData from PandaBox into a dictionary format compatible with Ophyd signals, using the device's configured signal aliases.
- `_get_signal_names_allowed_for_capture() -> list[str]` : Get a list of all signal keys that can be configured for capture on the PandaBox.
- `_get_signal_names_configured_for_capture() -> list[str]` : Get a list of all signal keys that are currently configured for capture on the PandaBox.


### Utility Scripts

The module [utility_scripts.py](./utility_scripts.py) provides command-line tools for saving and loading PandaBox layouts to/from files. This is useful to save layouts configured via the PandaBox web interface, and store them alongside beamline-specific integrations of the PandaBox in the beamline plugin repository. Multiple layouts can be created and also loaded dynamically depending on the scan type. We recommend using this operation mode for beamline-specific use cases of the PandaBox.

#### Save Layout from PandaBox to File
``` bash
python ./utility_scripts.py --host panda-box-host.psi.ch --save-layout ./my_layout.ini
```
Saves the current layout from the PandaBox at the specified host to a local file named `my_layout.ini`.

#### Load Layout from File to PandaBox
``` bash
python ./utility_scripts.py --host panda-box-host.psi.ch --load-layout ./my_layout.ini
```
**IMPORTANT**: Loads the layout from the local file `my_layout.ini` to the PandaBox at the specified host. Please note that loading a layout will overwrite the current configuration on the PandaBox. The UI will partly update, but the WEB server needs to be restarted manually to reflect these changes properly. We expect beamlines to prepare and test layouts beforehand and not use the PandaBox web interface in operation. All dynamic configuration should be done through the ophyd device hooks either directly in the device integration or temporarily through custom scan implementations.