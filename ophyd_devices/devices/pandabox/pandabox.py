"""
Module to interface with a PandaBox device. It requires the 'host' of the PandaBox to
be able to connect to it via the BlockingClient from the pandablocks library.

This module contains a base integration of the PandaBox hardware as a PSIDeviceBase device.
It wraps a couple of the methods from the scan interface (stage, unstage, pre_scan, stop, destroy)
with PandaBox specific logic to manage the data acquisition and communication with the hardware.

Any beamline integration should inherit from this base class and integrate their specific logic
into the on_connected, stage, unstage, pre_scan, kickoff, complete methods as needed. Please
be aware that the on_connected method is wrapped in here and should therefore always call
super().on_connected(). Child integrations should register data callbacks to handle incoming
data from the PandaBox during acquisition, and set the respective data on their ophyd signals.
The utility method _compile_frame_data_to_dict can be used to convert FrameData objects received
to the expected signal dict format. Please be aware that naming conventions here map to the
names of the blocks, and should be mapped to the beamline specific signal names in the child class.

More generally, a beamline specific integration needs to imlement logic attached to specific
layouts that change dynamically during scans. More importantly, it also needs to make sure that
the correct layout is loaded. Utility methods to load/save layouts to/from files or directly
from/to the PandaBox hardware are provided in this class too.
"""

import os
import threading
import uuid
from collections import defaultdict
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Callable, TypeAlias, Union

import pandablocks.commands as pbc
from bec_lib import bec_logger
from ophyd.status import WaitTimeoutError
from pandablocks.blocking import BlockingClient
from pandablocks.responses import EndData, FrameData, ReadyData, StartData

from ophyd_devices import PSIDeviceBase, StatusBase

if TYPE_CHECKING:  # pragma: no cover
    from bec_lib.devicemanager import ScanInfo
    from bec_server.device_server.devices.devicemanager import DeviceManagerDS

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


class PandaDataEvents(StrEnum):
    """
    Events from the PandaBox data stream. The events READY, START, FRAME, END correspond to
    actual data frames received from the PandaBox. The DISARMED event is used to indicate
    that the PandaBox has been disarmed, either after a complete data acquisition or after
    an interrupted acquisition.
    """

    READY = "ready"
    START = "start"
    FRAME = "frame"
    END = "end"
    DISARMED = "disarmed"


LITERAL_PANDA_DATA_EVENTS: TypeAlias = Union[
    PandaDataEvents.READY.value,
    PandaDataEvents.START.value,
    PandaDataEvents.FRAME.value,
    PandaDataEvents.END.value,
]

LITERAL_PANDA_COMMANDS: TypeAlias = Union[
    pbc.Raw,
    pbc.Arm,
    pbc.Disarm,
    pbc.GetChanges,
    pbc.GetBlockInfo,
    pbc.GetFieldInfo,
    pbc.GetPcapBitsLabels,
]

LITERAL_PANDA_DATA: TypeAlias = Union[ReadyData, StartData, FrameData, EndData]


class PandaBox(PSIDeviceBase):
    """
    Base class for PandaBox devices. Beamline integrations should inherit from this base class,
    to integrate pre-defined PandaBox layout directly into the BEC scan interface, stage/unstage,
    trigger/complete, pre_scan or kickoff methods.

    """

    USER_ACCESS = [
        "send_raw",
        "add_status_callback",
        "remove_status_callback",
        "get_panda_data_state",
    ]

    def __init__(
        self,
        *,
        name: str,
        host: str,
        scan_info: "ScanInfo" | None = None,
        device_manager: "DeviceManagerDS" | None = None,
        kwargs,
    ) -> None:
        super().__init__(name=name, scan_info=scan_info, device_manager=device_manager, **kwargs)
        self.host = host

        # Lock
        self._lock = threading.RLock()
        self._panda_data_state: PandaDataEvents | str = PandaDataEvents.DISARMED.value

        # Status callback management
        self._status_callbacks: dict[uuid.UUID, dict[str, Any]] = {}

        # Data callbacks management
        self._data_callbacks: dict[uuid.UUID, Callable[[LITERAL_PANDA_DATA], None]] = {}

        # Thread to receive data from the PandaBox
        self.data_thread: threading.Thread = threading.Thread(
            target=self._data_thread_loop, daemon=True
        )
        self.data_thread_kill_event = threading.Event()
        self.data_thread_run_event = threading.Event()

    ##########################
    ### Public API methods ###
    ##########################

    def send_raw(self, raw_command: Union[str, list[str]]) -> Any:
        """
        Send a raw command to the PandaBox. This can be used to set for example
        values on PandaBox block fields directly, e.g. 'BITS.B=1' to set the BITS.B field to 1.

        Args:
            raw_command (str | list[str]): The raw command to send to the PandaBox. We can also send
                                           a list of raw commands at once. This will be executed sequentially by
                                           the PandaBox client.

        Returns:
            Any: The response from the PandaBox client.

        Notes:
            Other useful raw commands:
            - 'BITS.B=1' or similar once to set bit fields
            - ['PULSE1.DELAY.UNITS=s', PULSE1.DELAY=0, PULSE1.WIDTH.UNITS=s, PULSE1.WIDTH=0.001] to set multiple fields at once
            - '*CAPTURE?' to inspect which signals have been configured for capture (PCAP?) TODO to check
        """
        return self._send_command(pbc.Raw(raw_command))

    def add_status_callback(
        self,
        status: StatusBase,
        success: list[PandaDataEvents],
        failure: list[PandaDataEvents],
        check_directly: bool = True,
    ) -> str:
        """
        This methods registers a status callback to the data receiving loop that will resolve
        if the PandaBox receives specific data events. It is used to allow asynchronous resolution
        of status objects based on PandaBox events. Per default, the callback checks the current
        panda_data_state directly to see if the status can be resolved immediately. This is useful
        when the status is created after the PandaBox has already sent some data events. However, this
        can also be disabled by setting check_directly to False.

        Args:
            status (StatusBase): The status object to register the callback for.
            success (list[PandaDataEvents]): The list of PandaBox data events that will resolve
                                            the status as successful.
            failure (list[PandaDataEvents]): The list of PandaBox data events that will resolve
                                            the status as failed.
            check_directly (bool): Whether to check the current panda_data_state directly
                                   to resolve the status immediately. Defaults to True.

        Returns:
            str: The unique ID of the registered callback. This can be used to remove the callback. If the
                status is resolved directly, an empty string is returned.
        """
        with self._lock:
            if check_directly:
                current_state = self.panda_data_state
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
        data_type: LITERAL_PANDA_DATA_EVENTS = PandaDataEvents.FRAME.value,
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

    def get_panda_data_state(self) -> str:
        """Get current panda data state."""
        return self.panda_data_state

    #########################
    ### State management  ###
    #########################

    @property
    def panda_data_state(self) -> str:
        """Get the current state of the data acquisition on the PandaBox."""
        return (
            self._panda_data_state.value
            if isinstance(self._panda_data_state, PandaDataEvents)
            else self._panda_data_state
        )

    @panda_data_state.setter
    def panda_data_state(self, value: PandaDataEvents | str) -> None:
        """Set the current state of the data acquisition on the PandaBox."""
        with self._lock:
            self._panda_data_state = value

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

        Upon receiving each type of data message, the panda_data_state is updated accordingly,
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
        with BlockingClient(self.host) as client:
            try:
                for data in client.data(scaled=False):
                    if isinstance(data, ReadyData):
                        self._run_status_callbacks(PandaDataEvents.READY)
                        self._run_data_callbacks(data, PandaDataEvents.READY.value)

                    elif isinstance(data, StartData):
                        self._run_status_callbacks(PandaDataEvents.START)
                        self._run_data_callbacks(data, PandaDataEvents.START.value)

                    elif isinstance(data, FrameData):
                        self._run_status_callbacks(PandaDataEvents.FRAME)
                        self._run_data_callbacks(data, PandaDataEvents.FRAME.value)

                    elif isinstance(data, EndData):
                        self._run_status_callbacks(PandaDataEvents.END)
                        self._run_data_callbacks(data, PandaDataEvents.END.value)
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
                client.send(self._disarm())  # Ensure we disarm at the end
                self.data_thread_run_event.clear()
                self._run_status_callbacks(PandaDataEvents.DISARMED)

    def _run_status_callbacks(self, event: PandaDataEvents) -> None:
        """
        Run registered status callbacks for a given PandaBox data event.
        These callbacks are used to resolve status objects that are registered
        to resolve in success/failure based on PandaBox data events. They are
        commonly used in the scan interface methods (pre_scan, kickoff, trigger or complete).
        and allow to for asynchronous resolution of these methods based on PandaBox data events.

        NOTE : Status callbacks are removed once they are resolved (either success or failure).

        Args:
            event (PandaDataEvents): The PandaBox data event that occurred.
            data (LITERAL_PANDA_DATA): The data associated with the event.
        """
        self.panda_data_state = event
        with self._lock:
            callbacks_to_remove = []
            for cb_id, cb_info in self._status_callbacks.items():
                status: StatusBase = cb_info["status"]
                success_events: list[PandaDataEvents] = cb_info["success"]
                failure_events: list[PandaDataEvents] = cb_info["failure"]

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

    def _run_data_callbacks(
        self, data: LITERAL_PANDA_DATA, event_type: LITERAL_PANDA_DATA_EVENTS
    ) -> None:
        """
        Placeholder method to run data callbacks for received PandaBox data.
        Child classes can override this method to implement custom behavior
        upon receiving different types of PandaBox data.
        NOTE: Data callbacks are not removed after being called, as they may be
        intended to be called multiple times during a data acquisition.

        Args:
            data (LITERAL_PANDA_DATA): The data received from the PandaBox.
            event_type (LITERAL_PANDA_DATA_EVENTS): The type of data received. This can be
                                                     "ready", "start", "frame", or "end".
        """
        with self._lock:
            for cb_info in self._data_callbacks.values():
                callback: Callable[[LITERAL_PANDA_DATA], None] = cb_info["callback"]
                cb_data_type: LITERAL_PANDA_DATA_EVENTS = cb_info["data_type"]
                if cb_data_type == event_type:
                    callback(data)

    #############################
    ### PSIDeviceBase methods ###
    #############################

    # NOTE These are beamline hooks for the scan interface within BEC.
    # If overwritten by child classes, please make sure to either call super()
    # or re-evaluate the implemented logic as these methods attempt to partially
    # setup the PandaBox for data acquisition.

    def on_connected(self):
        """
        Here we start the data readout thread upon connection to the PandaBox device.
        We do this after the super().on_connected() call to ensure that any additional
        connection logic from child classes is executed first.
        """
        # Test connection by sending WHO command which should respond with PandaBox ID
        try:
            ret = self.send_raw("*IDN?")
        except Exception as e:
            logger.error(f"Could not connect to PandaBox {self.name} at host {self.host}: {e}")
            raise e from e
        super().on_connected()
        self.data_thread.start()

    def stop(self, *, success=False):
        """
        Stopping the PandaBox device should ensure that the PandaBox is disarmed.
        We call this prior to the super().stop() call to ensure that the PandaBox
        is disarmed before any additional stopping logic from child classes is executed.
        """
        super().stop(success=success)
        self._disarm()

    def destroy(self):
        """
        We append the cleanup of the data readout thread to the destroy method,
        and call it prior to the super().destroy() call.
        This ensures that the data readout thread is properly cleaned up
        when the PandaBox device is destroyed.
        """
        self.data_thread_kill_event.set()  # Signal thread to exit
        self.data_thread_run_event.set()  # Unblock thread if waiting
        super().destroy()

    def stage(self) -> list[object] | StatusBase:
        """
        Stage the PandaBox device for acquisition.
        We make sure that the PandaBox data state is DISARMED before staging,
        to ensure that we do not start an acquisition while the PandaBox is still running an acquisition.
        This should never hapen in a well-integrated scan interface, but we add this check
        to be safe.

        Then we call super().stage() to perform any additional staging logic from child classes.
        Finally, we start the data readout loop by setting the data_thread_run_event.

        Returns:
            list[object] | StatusBase: The result of the super().stage() call.
        """
        # First make sure that the data readout loop is not running
        status = StatusBase(obj=self)
        self.add_status_callback(status=status, success=[PandaDataEvents.DISARMED], failure=[])
        try:
            status.wait(timeout=3)
        except WaitTimeoutError:
            logger.error(f"PandaBox {self.name} did not disarm before staging.")
            # pylint: disable=raise-from-missing
            raise RuntimeError(
                f"PandaBox {self.name} did not disarm properly. Please connection and the device integration."
            )

        ret = super().stage()
        self.data_thread_run_event.set()  # Start data readout loop
        return ret

    def pre_scan(self) -> StatusBase:
        """
        Prepare the PandaBox device for scan acquisition. It is important here that
        the PCAP module is armed for acquisition only after the data readout loop is started.
        We therefore add the logic here after any additional pre_scan logic from child classes.
        """
        status = super().pre_scan()
        status_ready_data_received = StatusBase(obj=self)
        self.add_status_callback(
            status=status_ready_data_received,
            success=[PandaDataEvents.READY],
            failure=[PandaDataEvents.FRAME, PandaDataEvents.END],
        )
        status_ready_data_received.add_callback(self._pre_scan_status_callback)
        if status:
            ret_status = status_ready_data_received & status
        else:
            ret_status = status_ready_data_received
        self.cancel_on_stop(ret_status)
        return ret_status

    def unstage(self) -> list[object] | StatusBase:
        """
        Any unstaging of the PandaBox device should ensure that"""
        ret = super().unstage()
        self.data_thread_run_event.clear()  # Make sure that the data readout loop is stopped
        self._disarm()  # Disarm the PandaBox, should be idempotent (TODO to check)
        return ret

    #######################
    ### Utility Methods ###
    #######################

    def _get_signal_names_allowed_for_capture(self) -> list[str]:
        """Utility method to get a list of all signal keys that CAN BE CONFIGURED for capture on the PandaBox."""
        ret = self.send_command(self.send_raw("*CAPTURE.*?"))
        # TODO check proper unpacking of returned keys
        return [key.split(" ")[0].strip("!") for key in ret if key.strip(".")]

    def _get_signal_names_configured_for_capture(self) -> list[str]:
        """Utility method to get a list of all signal keys thar ARE CURRENTLY CONFIGURED for capture on the PandaBox."""
        ret = self.send_command(self.send_raw("*CAPTURE?"))
        return [key.split(" ")[0].strip("!") for key in ret if key.strip(".")]

    def _compile_frame_data_to_dict(self, frame_data: FrameData) -> dict[str, Any]:
        """
        Compile the data from a FrameData object into a dictionary with expected OPHYD
        read format, e.g. signal {signal_name: {"value": [...]}}.

        Args:
            frame_data (FrameData): The FrameData object received from the PandaBox.

        Returns:
            dict[str, Any]: The compiled data in OPHYD read format.
        """
        out = defaultdict(list)
        data = frame_data.data
        keys = data.dtype.names
        for entry in data:
            for i, key in enumerate(keys):
                out[key]["value"].append(entry[i])

    def _pre_scan_status_callback(self, status: StatusBase):
        """
        Callback for arming the PCAP module during pre_scan.

        Args:
            status (StatusBase): The status object to resolve when arming is complete.
        """
        if not status.done:
            self._arm()
            status.set_finished()

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
