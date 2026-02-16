"""
Module to interface with a PandaBox device. It requires the 'host' of the PandaBox to
be able to connect to it via the BlockingClient from the pandablocks library.

This module contains a base integration of the PandaBox hardware as a PSIDeviceBase device.
It wraps a couple of the methods from the scan interface (stage, unstage, pre_scan, stop, destroy)
with PandaBox specific logic to manage the data acquisition and communication with the hardware.

Any beamline integration should inherit from this base class and integrate their specific logic
into the on_connected, on_stage, on_unstage, on_pre_scan, on_complete methods as needed.

Please note that the super().on_.. methods should be called to ensure proper initialization
and cleanup. You should only avoid calling the super() methods if you are certain that this
does not jeopardize the proper setup of the PandaBox and PCAP module for data acquisition.

Example:

def on_pre_scan(self):
    # Custom logic before staging, e.g. checking some conditions or setting up some parameters
    return super().on_pre_scan()  # Make sure to call return super().on_pre_scan() and return this
                                    status object

The base integration also includes a data signal with all available PCAP block signals. We allow
children classes to provide signal_aliases during the initialization to rename signals from the
PandaBox to better suited names for the beamline. We recommend to keep these names consistent
to allow for long-term maintainability and their storage in the data files/base.

Besides the integration, we also provide certain utility methods to directly load/save layouts
from/to the PandaBox hardware or from/to local files. This allows to easily manage the layouts
required for beamline operation.
"""

from __future__ import annotations

import os
import threading
import time
import uuid
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Callable, TypeAlias, TypedDict

import pandablocks.commands as pbc
from bec_lib import bec_logger
from ophyd import Component as Cpt
from ophyd.status import WaitTimeoutError
from pandablocks.blocking import BlockingClient
from pandablocks.responses import Data, EndData, FrameData, ReadyData, StartData

from ophyd_devices import DynamicSignal, PSIDeviceBase, StatusBase
from ophyd_devices.devices.panda_box.utils import get_pcap_capture_fields

if TYPE_CHECKING:  # pragma: no cover
    from bec_lib.devicemanager import ScanInfo
    from bec_server.device_server.devices.devicemanager import DeviceManagerDS
    from ophyd import StatusBase as OphydStatusBase

logger = bec_logger.logger


##########################
### Utility functions ###
##########################


def load_layout_from_panda(host: str) -> list[str]:
    """Load the current layout from the PandaBox.

    Args:
        host (str): The hostname of the PandaBox.

    Returns:
        list[str]: The current layout of the PandaBox device. Please check module dockstring for more info


    """
    with BlockingClient(host) as client:
        state = client.send(pbc.GetState())
    return state


def load_layout_to_panda(host: str, layout: list[str]) -> None:
    """Load a layout to the PandaBox.

    Args:
        host (str): The hostname of the PandaBox.
        layout (list[str]): The layout to load to the PandaBox. See module docstring for more info.
    """
    with BlockingClient(host) as client:
        client.send(pbc.SetState(layout))


def save_panda_layout_to_file(host: str, file_path: str) -> None:
    """
    Save the currently loaded layout from the PandaBox to a local file.

    Args:
        host (str): The hostname of the PandaBox.
        file_path (str): The path to the file where the layout will be saved.
    """
    layout = "\n".join(load_layout_from_panda(host))
    with open(file_path, "w") as file:
        file.write(layout)


def load_layout_from_file_to_panda(host: str, file_path: str) -> None:
    """
    Load a layout from a local file to the PandaBox.

    Args:
        host (str): The hostname of the PandaBox.
        file_path (str): The path to the file from which the layout will be loaded.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Could not find layout for file path: {file_path}.")
    with open(file_path, "r") as f:
        layout = f.read().splitlines()
    load_layout_to_panda(host, layout)


########################
### PandaBox Device  ###
########################


class PandaState(StrEnum):
    """
    States from the PandaBox data stream. The state READY, START, FRAME, END correspond to
    actual data frames received from the PandaBox. DISARMED indicates that the PandaBox
    has been disarmed and is no longer acquiring data.
    """

    READY = "ready"
    START = "start"
    FRAME = "frame"
    END = "end"
    DISARMED = "disarmed"

    def describe(self) -> str:
        """Return a human-readable description of the event."""
        descriptions = {
            PandaState.READY: "PandaBox is ready for data acquisition.",
            PandaState.START: "PandaBox has started data acquisition.",
            PandaState.FRAME: "PandaBox has sent a frame of data.",
            PandaState.END: "PandaBox has ended data acquisition.",
            PandaState.DISARMED: "PandaBox is disarmed and not acquiring data. This event is not triggered by a data frame from the PandaBox.",
        }
        return descriptions.get(self, "Unknown PandaBox data event.")


# pylint: disable=invalid-name
LITERAL_PANDA_COMMANDS: TypeAlias = (
    pbc.Raw
    | pbc.Arm
    | pbc.Disarm
    | pbc.GetChanges
    | pbc.GetBlockInfo
    | pbc.GetFieldInfo
    | pbc.GetPcapBitsLabels
)
LITERAL_PANDA_DATA: TypeAlias = ReadyData | StartData | FrameData | EndData | Data


class DataCallback(TypedDict):
    callback: Callable[[LITERAL_PANDA_DATA], None]
    data_type: PandaState


class PandaBox(PSIDeviceBase):
    """
    Base class for PandaBox devices. Beamline integrations should inherit from this base class,
    to integrate pre-defined PandaBox layout directly into the BEC scan interface, stage/unstage,
    trigger/complete, pre_scan or kickoff methods.

    A signal_alias can be provided during initialization to specify the mapping from PandaBox signal names to
    beamline specific signal names. Any signal that is found in the data frames will be automatically
    mapped to the provided signal names. If data is received for a signal that is not included in the signal_alias,
    the original name from the PandaBox will be used as the signal name. Signal config should be provided as a
    dict with keys corresponding to the signal names from the PandaBox, and values corresponding to the desired
    signal names to be used in the data frames.
    """

    data = Cpt(
        DynamicSignal,
        name="data",
        ndim=0,
        max_size=1000,
        signals=get_pcap_capture_fields(),
        async_update={"type": "add", "max_shape": [None]},
    )

    USER_ACCESS = ["send_raw", "add_status_callback", "remove_status_callback", "get_panda_state"]

    def __init__(
        self,
        *,
        name: str,
        host: str,
        signal_alias: dict[str, str] | None = None,
        scan_info: ScanInfo | None = None,
        device_manager: DeviceManagerDS | None = None,
        **kwargs,
    ) -> None:
        self.signal_alias = signal_alias if signal_alias is not None else {}
        kwargs.pop(
            "signal_alias", None
        )  # Remove signal_alias from kwargs to avoid issues with super().__init__()
        super().__init__(name=name, scan_info=scan_info, device_manager=device_manager, **kwargs)
        self.host = host

        # Lock
        self._lock = threading.RLock()
        self._panda_state: PandaState | str = PandaState.DISARMED.value

        # Status callback management
        self._status_callbacks: dict[str, dict[str, Any]] = {}

        # Data callbacks management
        self._data_callbacks: dict[str, DataCallback] = {}

        # Thread to receive data from the PandaBox
        self.data_thread: threading.Thread = threading.Thread(
            target=self._data_thread_loop, daemon=True, name=f"{self.name}_data_thread"
        )
        self.data_thread_kill_event = threading.Event()
        self.data_thread_run_event = threading.Event()

        # Acquisition group of the PandaBox data.
        self._acquisition_group = "panda"

        # Timeouts for wait operations in seconds
        self._stage_timeout_in_s = 3

    def on_init(self):
        """Initialize the PandaBox device. This method can be used to perform any additional initialization logic."""
        super().on_init()
        new_names = [
            self.signal_alias.get(original_name, original_name)
            for original_name, _ in self.data.signals
        ]
        # Unify names for data
        self.data.signals = self.data._unify_signals(new_names)

    ##########################
    ### Public API methods ###
    ##########################

    def send_raw(self, raw_command: str | list[str]) -> Any:
        """
        Send a raw command to the PandaBox. This can be used to set for example
        values on PandaBox block fields directly, e.g. 'BITS.B=1' to set the BITS.B field to 1.
        Please note, list of raw commands are not allowed as they have to sent sequentially.
        The list[str] input is needed to certain commands that require this syntax, e.g.
        ["SEQ1.TABLE>", "1", "1", "0", "0", ""]

        Args:
            raw_command (str | list[str]): The raw command to send to the PandaBox. We can also send
                                           a list of raw commands at once. This will be executed sequentially by
                                           the PandaBox client.

        Returns:
            Any: The response from the PandaBox client.

        Notes:
            Other useful raw commands:
            - 'BITS.B=1' or similar once to set bit fields
            - '*CAPTURE?' to inspect which signals have been configured for capture (PCAP?) TODO to check

        """
        if isinstance(raw_command, str):
            raw_command = [raw_command]
        return self._send_command(pbc.Raw(raw_command))

    def add_status_callback(
        self,
        status: StatusBase,
        success: list[PandaState],
        failure: list[PandaState],
        check_directly: bool = True,
    ) -> str:
        """
        This methods registers a status callback to the data receiving loop that will resolve
        if the PandaBox receives specific data events. It is used to allow asynchronous resolution
        of status objects based on PandaBox events. Per default, the callback checks the current
        panda_state directly to see if the status can be resolved immediately. This is useful
        when the status is created after the PandaBox has already sent some data events. However, this
        can also be disabled by setting check_directly to False.

        Args:
            status (StatusBase): The status object to register the callback for.
            success (list[PandaState]): The list of PandaBox data events that will resolve
                                            the status as successful.
            failure (list[PandaState]): The list of PandaBox data events that will resolve
                                            the status as failed.
            check_directly (bool): Whether to check the current panda_state directly
                                   to resolve the status immediately. Defaults to True.

        Returns:
            str: The unique ID of the registered callback. This can be used to remove the callback. If the
                status is resolved directly, an empty string is returned.
        """
        with self._lock:
            if check_directly:
                current_state = self.panda_state
                if current_state in success and not status.done:
                    status.set_finished()
                    return ""
                elif current_state in failure and not status.done:
                    status.set_exception(
                        RuntimeError(
                            f"Status with success conditions {success} and failure conditions {failure} "
                            f"due to PandaBox already being in failure state: {current_state}"
                        )
                    )
                    return ""
            cb_id = str(uuid.uuid4())
            self._status_callbacks[cb_id] = {
                "status": status,
                "success": success,
                "failure": failure,
            }
            return cb_id

    def remove_status_callback(self, cb_id: str) -> None:
        """
        Remove a previously registered status callback.

        Args:
            cb_id (str): The unique ID of the callback to remove.
        """
        with self._lock:
            self._status_callbacks.pop(cb_id, None)

    def add_data_callback(
        self,
        callback: Callable[[LITERAL_PANDA_DATA], None],
        data_type: PandaState = PandaState.FRAME,
    ) -> str:
        """
        Register a data callback to be called whenever new data is received from the PandaBox.

        Args:
            callback (Callable[[LITERAL_PANDA_DATA], None]): The callback function to register. It should accept
                                                             a single argument of type LITERAL_PANDA_DATA (see notes).
            data_type ("ready", "start", "frame", "end"): The type of data to register the callback for.
                                                            Defaults to "frame".

        Returns:
            str: The unique ID of the registered callback. This can be used to remove the callback.
        """
        with self._lock:
            cb_id = str(uuid.uuid4())
            self._data_callbacks[cb_id] = {"callback": callback, "data_type": data_type}
            return cb_id

    def remove_data_callback(self, cb_id: str) -> None:
        """
        Remove a previously registered data callback.

        Args:
            cb_id (str): The unique ID of the callback to remove.
        """
        with self._lock:
            self._data_callbacks.pop(cb_id, None)

    def get_panda_state(self) -> str:
        """Get current panda data state."""
        return self.panda_state

    #########################
    ### State management  ###
    #########################

    @property
    def panda_state(self) -> str:
        """Get the current state of the data acquisition on the PandaBox."""
        return (
            self._panda_state.value
            if isinstance(self._panda_state, PandaState)
            else self._panda_state
        )

    @panda_state.setter
    def panda_state(self, value: PandaState | str) -> None:
        """Set the current state of the data acquisition on the PandaBox."""
        with self._lock:
            self._panda_state = value

    ################################
    ### Data readout management  ###
    ################################

    def _data_thread_loop(self) -> None:
        """
        This method runs a loop in the data_thread and handle data readouts from the PandaBox.
        The loop will be activated when the data_thread_run_event is set, and will exit when the
        data_thread_kill_event is set. Please make sure to first set the kill event, and also the
        run_event to unblock the thread such that it can exit cleanly.
        """
        while not self.data_thread_kill_event.is_set():
            self.data_thread_run_event.wait()  # Block until started
            if self.data_thread_kill_event.is_set():
                break  # Break loop if kill event is set after waiting is unblocked
            self._run_data_readout()

    def _run_data_readout(self) -> None:
        """
        Data readoud loop. This method connects to the PandaBox with a BlockingClient,
        receiving data messages. There are 4 types of data messages:
         - ReadyData: Indicates that the PandaBox is ready for data acquisition.
         - StartData: Indicates the start of a data acquisition.
         - FrameData: Contains a frame of data acquired from the PandaBox.
         - EndData: Indicates the end of a data acquisition.

        Upon receiving each type of data message, the panda_state is updated accordingly,
        and any registered callbacks for that event are executed. This allows to handle callbacks
        for each stage of the data acquisition process. For example, a child class could add a
        status callback to resolve during a specific stage of the data acquisition based on an
        event received here.

        # NOTE: The receiving loop has to be started before the ARM() command is sent to the PandaBox.
        # The required sequence is to (1) start the data readout loop and receive ReadyData,
        # (2) send the ARM() command to the PandaBox to start acquisition, (3) receive StartData and FrameData,
        # (4) receive EndData when acquisition is complete. When an acquisition is interrupted prematurely, we have
        # to ensure that we send the DISARM() command to the PandaBox to stop the acquisition cleanly. Multiple disarm
        # commands are safe to send, so we can always ensure that we disarm at the end of the readout loop. (TODO to check).
        """
        try:
            with BlockingClient(self.host) as client:
                for data in client.data(scaled=False):
                    if isinstance(data, ReadyData):
                        self._run_status_callbacks(PandaState.READY)
                        self._run_data_callbacks(data, PandaState.READY)

                    elif isinstance(data, StartData):
                        self._run_status_callbacks(PandaState.START)
                        self._run_data_callbacks(data, PandaState.START)

                    elif isinstance(data, FrameData):
                        self._run_status_callbacks(PandaState.FRAME)
                        self._run_data_callbacks(data, PandaState.FRAME)

                    elif isinstance(data, EndData):
                        self._run_status_callbacks(PandaState.END)
                        self._run_data_callbacks(data, PandaState.END)
                        break  # Exit data readout loop

        finally:
            # NOTE: This block ensures that we properly cleanup after a data acquisition,
            # whether it completed successfully or was interrupted. This includes sending
            # the DISARM() command to the PandaBox to stop any ongoing acquisition in case
            # we exited the loop prematurely. It also clears the data_thread_run_event to block
            # the data readout loop again, and runs the DISARMED status callbacks to notify
            # any registered status objects that the PandaBox is now disarmed. DISARMED is the
            # expected safe state of the data receiving loop from the PandaBox and was added
            # in addition to the existing READY, START, FRAME, END events created from the existing
            # PandaBox data messages.

            self._disarm()  # Ensure we disarm at the end

            self.data_thread_run_event.clear()  # Stop data readout loop

            self._run_status_callbacks(PandaState.DISARMED)  # Run DISARMED status callbacks

            # As DISARMED is not triggered by a data message, we manually run data callbacks for it here
            # and run it with an empty Data() object following the base class for data message responses
            # of the pandablocks library.
            self._run_data_callbacks(Data(), PandaState.DISARMED)

    def _run_status_callbacks(self, event: PandaState) -> None:
        """
        Run registered status callbacks for a given PandaBox data event.
        These callbacks are used to resolve status objects that are registered
        to resolve in success/failure based on PandaBox data events. They are
        commonly used in the scan interface methods (pre_scan, kickoff, trigger or complete).
        and allow to for asynchronous resolution of these methods based on PandaBox data events.

        NOTE : Status callbacks are removed once they are resolved (either success or failure).

        Args:
            event (PandaState): The PandaBox data event that occurred.
            data (LITERAL_PANDA_DATA): The data associated with the event.
        """
        self.panda_state = event
        with self._lock:
            callbacks_to_remove = []
            for cb_id, cb_info in self._status_callbacks.items():
                status: StatusBase = cb_info["status"]
                success_events: list[PandaState] = cb_info["success"]
                failure_events: list[PandaState] = cb_info["failure"]

                if event in success_events and not status.done:
                    status.set_finished()
                    callbacks_to_remove.append(cb_id)
                elif event in failure_events and not status.done:
                    status.set_exception(
                        RuntimeError(
                            f"Status with success conditions {success_events} and failure conditions {failure_events} "
                            f"due to PandaBox receiving failure event: {event}"
                        )
                    )
                    callbacks_to_remove.append(cb_id)
            for cb_id in callbacks_to_remove:
                self._status_callbacks.pop(cb_id, None)

    def _run_data_callbacks(self, data: LITERAL_PANDA_DATA, event_type: PandaState) -> None:
        """
        Placeholder method to run data callbacks for received PandaBox data.
        Child classes can override this method to implement custom behavior
        upon receiving different types of PandaBox data.
        NOTE: Data callbacks are not removed after being called, as they may be
        intended to be called multiple times during a data acquisition.

        Args:
            data (LITERAL_PANDA_DATA): The data received from the PandaBox.
            event_type (PandaState): The type of data received. This can be
                                                     "ready", "start", "frame", or "end".
        """
        with self._lock:
            for cb_info in self._data_callbacks.values():
                callback: Callable[[LITERAL_PANDA_DATA], None] = cb_info["callback"]
                cb_data_type: PandaState = cb_info["data_type"]
                if cb_data_type == event_type:
                    callback(data)

    #############################
    ### PSIDeviceBase methods ###
    #############################

    # NOTE These are beamline hooks for the scan interface within BEC.
    # If overwritten by child classes, please make sure to either call super()
    # or re-evaluate the implemented logic as these methods attempt to partially
    # setup the PandaBox for data acquisition.

    def wait_for_connection(self, timeout: float | None = None) -> bool:
        ret = self.send_raw("*IDN?")
        return True

    def on_connected(self):
        """
        Here we start the data readout thread upon connection to the PandaBox device.
        We do this after the super().on_connected() call to ensure that any additional
        connection logic from child classes is executed first.
        """
        # Test connection by sending WHO command which should respond with PandaBox ID
        super().on_connected()
        self.data_thread.start()
        self.add_data_callback(data_type=PandaState.FRAME, callback=self._receive_frame_data)

    def _receive_frame_data(self, data: FrameData) -> None:
        logger.info(f"Received frame data with signals {data}")
        out = self.convert_frame_data(frame_data=data)
        logger.info(f"Compiled data {out}")
        self.data.put(out, acquisition_group=self._acquisition_group)

    def stop(self, *, success=False):
        """
        Stopping the PandaBox device should ensure that the PandaBox is disarmed.
        We call this prior to the super().stop() call to ensure that the PandaBox
        is disarmed before any additional stopping logic from child classes is executed.
        """
        self._disarm()
        self.on_stop()
        super().stop(success=success)

    def destroy(self):
        """
        We append the cleanup of the data readout thread to the destroy method,
        and call it prior to the super().destroy() call.
        This ensures that the data readout thread is properly cleaned up
        when the PandaBox device is destroyed.
        """
        self.data_thread_kill_event.set()  # Signal thread to exit
        self.data_thread_run_event.set()  # Unblock thread if waiting
        self.on_destroy()
        super().destroy()

    def on_stage(self) -> StatusBase | OphydStatusBase | None:
        """On stage hook for the PandaBox. Here we make sure that the PandaBox is disarmed before staging."""
        status = StatusBase(obj=self)
        self.add_status_callback(status=status, success=[PandaState.DISARMED], failure=[])
        try:
            status.wait(timeout=self._stage_timeout_in_s)
        except WaitTimeoutError:
            logger.error(f"PandaBox {self.name} did not disarm before staging.")
            # pylint: disable=raise-from-missing
            raise RuntimeError(
                f"PandaBox {self.name} did not disarm properly. Please check the connection and the device integration."
            )
        self.data_thread_run_event.set()  # Start data readout loop
        return super().on_stage()

    def on_pre_scan(self) -> StatusBase | OphydStatusBase | None:
        """
        On pre_scan hook for the PandaBox. We use this hook to arm the PCAP module for data acquisition.
        This logic makes sure that the data readout loop is started and that we received the READY event
        from the device. Only then can the PCAP module aquire data.
        """
        status = StatusBase(obj=self)
        status.add_callback(self._pre_scan_status_callback)
        self.add_status_callback(
            status=status, success=[PandaState.READY], failure=[PandaState.FRAME, PandaState.END]
        )
        self.cancel_on_stop(status)  # Make sure status is cancelled if externally stopped
        return status

    def on_unstage(self) -> list[object] | StatusBase | OphydStatusBase:
        """
        Any unstaging of the PandaBox device should ensure that"""
        self.data_thread_run_event.clear()  # Make sure that the data readout loop is stopped
        self._disarm()  # Disarm the PandaBox, should be idempotent
        return super().on_unstage()

    #######################
    ### Utility Methods ###
    #######################

    def _get_signal_names_allowed_for_capture(self) -> list[str]:
        """Utility method to get a list of all signal keys that CAN BE CONFIGURED for capture on the PandaBox."""
        ret = self.send_raw("*CAPTURE.*?")
        return [key.split(" ")[0].strip("!") for key in ret if key.strip(".")]

    def _get_signal_names_configured_for_capture(self) -> list[str]:
        """Utility method to get a list of all signal keys thar ARE CURRENTLY CONFIGURED for capture on the PandaBox."""
        ret = self.send_raw("*CAPTURE?")
        signal_names = []
        for value in ret:
            if value.strip("."):  # Ignore empty values "."
                string_parts = value.strip("!").split(" ")
                base_name = string_parts[0]  # Get base name without capture config
                _ = [signal_names.append(f"{base_name}.{key}") for key in string_parts[1:]]
        return signal_names

    def convert_frame_data(self, frame_data: FrameData) -> dict[str, Any]:
        """
        Convert the data from a FrameData object into a dictionary with expected OPHYD
        read format, e.g. signal {signal_name: {"value": [...]}}.

        Args:
            frame_data (FrameData): The FrameData object received from the PandaBox.

        Returns:
            dict[str, Any]: The converted data in OPHYD read format.
        """
        # Create output dict
        out = {}
        data = frame_data.data
        keys = data.dtype.names
        # Map keys if mapping is provided
        mapped_key = [self.signal_alias.get(key, key) for key in keys]
        # Initialize lists for each key, consider adjusting names to match
        for k in mapped_key:
            out[k] = {"value": [], "timestamp": time.time()}
        for entry in data:
            for i, k in enumerate(mapped_key):
                out[k]["value"].append(entry[i])  # Fill values from data
        return out

    def _pre_scan_status_callback(self, status: StatusBase):
        """
        Callback for arming the PCAP module during pre_scan.

        Args:
            status (StatusBase): The status object to resolve when arming is complete.
        """
        if status.done and status.success:
            self._arm()

    def _send_command(self, command: LITERAL_PANDA_COMMANDS) -> Any:
        """Send a command to the PandaBox via the BlockingClient."""
        with BlockingClient(self.host) as client:
            response = client.send(command)
        return response

    def _arm(self) -> None:
        """Arm the PandaBox device."""
        self._send_command(pbc.Arm())

    def _disarm(self) -> None:
        """Disarm the PandaBox device."""
        self._send_command(pbc.Disarm())


if __name__ == "__main__":
    # Example usage of the PandaBox class
    panda_box = PandaBox(
        name="PandaBox1", host="localhost", signal_alias={"long_list": "mapped_signal_name"}
    )
