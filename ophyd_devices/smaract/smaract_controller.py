import enum
import functools
import json
import logging
import os
import time

import numpy as np
from prettytable import PrettyTable
from typeguard import typechecked

from ophyd_devices.smaract.smaract_errors import SmaractCommunicationError, SmaractErrorCode
from ophyd_devices.utils.controller import Controller, axis_checked, threadlocked

logger = logging.getLogger("smaract_controller")


class SmaractCommunicationMode(enum.Enum):
    SYNC = 0
    ASYNC = 1


def retry_once(fcn):
    """Decorator to rerun a function in case a SmaractCommunicationError was raised. This may happen if the buffer was not empty."""

    @functools.wraps(fcn)
    def wrapper(self, *args, **kwargs):
        try:
            val = fcn(self, *args, **kwargs)
        except (SmaractCommunicationError, SmaractErrorCode):
            val = fcn(self, *args, **kwargs)
        return val

    return wrapper


class SmaractChannelStatus(enum.Enum):
    STOPPED = 0
    STEPPING = 1
    SCANNING = 2
    HOLDING = 3
    TARGETING = 4
    MOVE_DELAY = 5
    CALIBRATING = 6
    FINDING_REFERENCE_MARK = 7
    LOCKED = 9


class SmaractSensorDefinition:
    def __init__(self, symbol, type_code, positioner_series, comment, reference_type) -> None:
        self.symbol = symbol
        self.type_code = type_code
        self.comment = comment
        self.positioner_series = positioner_series
        self.reference_type = reference_type


class SmaractSensors:
    smaract_sensor_definition_file = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "smaract_sensors.json"
    )

    def __init__(self) -> None:
        self.avail_sensors = {}

        with open(self.smaract_sensor_definition_file) as json_file:
            sensor_list = json.load(json_file)
        for sensor in sensor_list:
            self.avail_sensors[sensor["type_code"]] = SmaractSensorDefinition(**sensor)


class SmaractController(Controller):
    _axes_per_controller = 6
    _initialized = False
    USER_ACCESS = [
        "socket_put_and_receive",
        "smaract_show_all",
        "move_open_loop_steps",
        "find_reference_mark",
        "describe",
        "axis_is_referenced",
        "all_axes_referenced",
    ]

    def __init__(
        self,
        *,
        name="SmaractController",
        kind=None,
        parent=None,
        socket_cls=None,
        socket_host=None,
        socket_port=None,
        attr_name="",
        labels=None,
    ):
        if not self._initialized:
            super().__init__(
                name=name,
                socket_cls=socket_cls,
                socket_host=socket_host,
                socket_port=socket_port,
                attr_name=attr_name,
                parent=parent,
                labels=labels,
                kind=kind,
            )
            self._sensors = SmaractSensors()

    @threadlocked
    def socket_put(self, val: str):
        self.sock.put(f":{val}\n".encode())

    @threadlocked
    def socket_get(self):
        return self.sock.receive().decode()

    @threadlocked
    def socket_put_and_receive(
        self, val: str, remove_trailing_chars=True, check_for_errors=True, raise_if_not_status=False
    ) -> str:
        self.socket_put(val)
        return_val = ""
        max_wait_time = 1
        elapsed_time = 0
        sleep_time = 0.01
        while True:
            ret = self.socket_get()
            return_val += ret
            if ret.endswith("\n"):
                break
            time.sleep(sleep_time)
            elapsed_time += sleep_time
            if elapsed_time > max_wait_time:
                break
        if remove_trailing_chars:
            return_val = self._remove_trailing_characters(return_val)
            logger.debug(f"Sending {val}; Returned {return_val}")
        if check_for_errors:
            self._check_for_error(return_val, raise_if_not_status=raise_if_not_status)
        return return_val

    @retry_once
    @axis_checked
    def get_status(self, axis_Id_numeric: int) -> SmaractChannelStatus:
        """Returns the current movement status code of a positioner or end effector.This command can be used to check whether a previously issued movement command has been completed.

        Args:
            axis_Id_numeric (int): Axis number

        Returns:
            SmaractChannelStatus: Channel status
        """
        return_val = self.socket_put_and_receive(f"GS{axis_Id_numeric}")
        if self._message_starts_with(return_val, f":S{axis_Id_numeric}"):
            return SmaractChannelStatus(int(return_val.split(",")[1]))

    @retry_once
    @axis_checked
    def is_axis_moving(self, axis_Id_numeric: int) -> bool:
        """Check if axis is moving. Returns true upon open loop move, scanning, closed loop move or reference mark search.

        Args:
            axis_Id_numeric (int): Axis number.

        Returns:
            bool: True if axis is moving.
        """
        axis_status = self.get_status(axis_Id_numeric)
        return axis_status in [
            SmaractChannelStatus.STEPPING,
            SmaractChannelStatus.SCANNING,
            SmaractChannelStatus.TARGETING,
            SmaractChannelStatus.FINDING_REFERENCE_MARK,
        ]

    @retry_once
    def stop_all_axes(self):
        return [
            self.socket_put_and_receive(f"S{ax.axis_Id_numeric}", raise_if_not_status=True)
            for ax in self._axis
            if ax is not None
        ]

    @retry_once
    @axis_checked
    def axis_is_referenced(self, axis_Id_numeric: int) -> bool:
        return_val = self.socket_put_and_receive(f"GPPK{axis_Id_numeric}")
        if self._message_starts_with(return_val, f":PPK{axis_Id_numeric}"):
            return bool(int(return_val.split(",")[1]))

    def all_axes_referenced(self) -> bool:
        return all(
            self.axis_is_referenced(ax.axis_Id_numeric) for ax in self._axis if ax is not None
        )

    @retry_once
    @axis_checked
    def get_position(self, axis_Id_numeric: int) -> float:
        """Returns the current position of a positioner.

        Args:
            axis_Id_numeric (int): Axis number.

        Returns:
            float: Position in mm
        """
        return_val = self.socket_put_and_receive(f"GP{axis_Id_numeric}")
        if self._message_starts_with(return_val, f":P{axis_Id_numeric}"):
            return float(return_val.split(",")[1]) / 1e6

    @retry_once
    @axis_checked
    @typechecked
    def move_axis_to_absolute_position(
        self, axis_Id_numeric: int, target_val: float, hold_time: int = 1000
    ) -> None:
        """Instructs a positioner to move to a specific position.

        Args:
            axis_Id_numeric (int): Axis number.
            target_val (float): Target position in mm.
            hold_time (int, optional): Specifies how long (in milliseconds) the position is actively held after reaching the target. The valid range is 0..60,000. A 0 deactivates this feature, a value of 60,000 is infinite (until manually stopped, see S command). Defaults to 1000.

        """
        self.socket_put_and_receive(
            f"MPA{axis_Id_numeric},{int(np.round(target_val*1e6))},{hold_time}",
            raise_if_not_status=True,
        )

    @retry_once
    @axis_checked
    @typechecked
    def move_axis_to_relative_position(
        self, axis_Id_numeric: int, target_val: float, hold_time: int = 1000
    ) -> None:
        """Instructs a positioner to move to a position relative to its current position.

        Args:
            axis_Id_numeric (int): Axis number.
            target_val (float): Relative position to move to in mm.
            hold_time (int, optional): Specifies how long (in milliseconds) the position is actively held after reaching the target. The valid range is 0..60,000. A 0 deactivates this feature, a value of 60,000 is infinite (until manually stopped, see S command). Defaults to 1000.

        """
        self.socket_put_and_receive(
            f"MPR{axis_Id_numeric},{int(np.round(target_val*1e6))},{hold_time}",
            raise_if_not_status=True,
        )

    @retry_once
    @axis_checked
    @typechecked
    def move_open_loop_steps(
        self, axis_Id_numeric: int, steps: int, amplitude: int = 4000, frequency: int = 2000
    ) -> None:
        """Move open loop steps. It performs a burst of steps with the given parameters.

        Args:
            axis_Id_numeric (int): Axis number.
            steps (int): Number and direction of steps to perform. The valid range is -30,000..30,000. A value of 0 stops the positioner, but see S command. A value of 30,000 or -30,000 performs an unbounded move. This should be used with caution since the positioner will only stop on an S command.
            amplitude (int): Amplitude that the steps are performed with. Lower amplitude values result in a smaller step width. The parameter must be given as a 12bit value (range 0..4,095). 0 corresponds to 0V, 4,095 to 100V. Default: 4000
            frequency (int): Frequency in Hz that the steps are performed with. The valid range is 1..18,500. Default: 2000.
        """
        self.socket_put_and_receive(
            f"MST{axis_Id_numeric},{steps},{amplitude},{frequency}", raise_if_not_status=True
        )

    @retry_once
    def get_communication_mode(self) -> SmaractCommunicationMode:
        return_val = self.socket_put_and_receive("GCM")
        if self._message_starts_with(return_val, f":CM"):
            return SmaractCommunicationMode(int(return_val.strip(":CM")))

    @retry_once
    @axis_checked
    def get_channel_type(self, axis_Id_numeric) -> str:
        return_val = self.socket_put_and_receive(f"GCT{axis_Id_numeric}")
        if self._message_starts_with(return_val, f":CT{axis_Id_numeric}"):
            return return_val.split(",")[1]

    @retry_once
    def get_interface_version(self) -> str:
        """This command may be used to retrieve the interface version of the system. It is useful to check if changes
        have been made to the software interface. An application may check the version in order to ensure that the
        system behaves as the application expects it to do.

        Returns:
            str: interface version
        """
        return_val = self.socket_put_and_receive("GIV")
        if self._message_starts_with(return_val, f":IV"):
            return return_val.strip(":IV")

    @retry_once
    def get_number_of_channels(self) -> int:
        """This command may be used to determine how many control channels are available on a system. This
        includes positioner channels and end effector channels. Each channel is of a specific type. Use the GCT
        command to determine the types of the channels.
        Note that the number of channels does not represent the number positioners and/or end effectors that are
        currently connected to the system.
        The channel indexes throughout the interface are zero based. If your system has N channels then the valid
        range for a channel index is 0.. N-1.

        Returns:
            int: number of channels
        """
        return_val = self.socket_put_and_receive("GNC")
        if self._message_starts_with(return_val, f":N"):
            return int(return_val.strip(":N"))

    @retry_once
    def get_system_id(self) -> str:
        """This command may be used to physically identify a system connected to the PC. Each system has a unique
        ID which makes it possible to distinguish one from another.
        The ID returned is a generic decimal number that uniquely identifies the system.

        """
        return_val = self.socket_put_and_receive("GSI")
        if self._message_starts_with(return_val, f":ID"):
            return return_val.strip(":ID")

    @retry_once
    def reset(self) -> None:
        """When this command is sent the system will perform a reset. It has the same effect as a power down/power
        up cycle. The system replies with an acknowledge string before resetting itself.
        """
        self.socket_put_and_receive("R", raise_if_not_status=True)

    @retry_once
    def set_hcm_mode(self, mode: int):
        """If a Hand Control Module (HCM) is connected to the system, this command may be used to enable or
        disable it in order to avoid interference while the software is in control of the system. There are three possible
        modes to set:
        0: In this mode the Hand Control Module is disabled. It may not be used to control positioners.
        1: This is the default setting where the Hand Control Module may be used to control the positioners.
        2: In this mode the Hand Control Module cannot be used to control the positioners. However, if there
        are positioners with sensors attached, their position data will still be displayed.

        Args:
            mode (int): HCM mode

        """
        if mode not in range(3):
            raise ValueError(f"HCM mode must be 0, 1 or 2. Received: {mode}.")
        self.socket_put_and_receive(f"SHE{mode}", raise_if_not_status=True)

    @retry_once
    @axis_checked
    def get_position_limits(self, axis_Id_numeric: int) -> list:
        """May be used to read out the travel range limit that is currently
        configured for a linear channel.

                Args:
                    axis_Id_numeric (int): Axis

                Returns:
                    list: [low_limit, high_limit] in mm
        """
        return_val = self.socket_put_and_receive(f"GPL{axis_Id_numeric}")
        if self._message_starts_with(return_val, f":GPL{axis_Id_numeric}"):
            return [
                float(limit) / 1e6
                for limit in return_val.strip(f":GPL{axis_Id_numeric},").split(",")
            ]

    @retry_once
    @axis_checked
    def set_position_limits(
        self, axis_Id_numeric: int, low_limit: float, high_limit: float
    ) -> None:
        """For positioners with integrated sensors this command may be used to limit the travel range of a linear
        positioner by software. By default there is no limit set. If defined the
        positioner will not move beyond the limit. This affects open-loop as well as closed-loop movements.

                Args:
                    axis_Id_numeric (int): Axis
                    low_limit (float): low limit in mm
                    high_limit (float): high limit in mm

        """
        self.socket_put_and_receive(
            f"SPL{axis_Id_numeric},{np.round(low_limit*1e6)},{np.round(high_limit*1e6)}",
            raise_if_not_status=True,
        )

    @retry_once
    @axis_checked
    def get_sensor_type(self, axis_Id_numeric: int) -> SmaractSensorDefinition:
        return_val = self.socket_put_and_receive(f"GST{axis_Id_numeric}")
        if self._message_starts_with(return_val, f":ST{axis_Id_numeric}"):
            return self._sensors.avail_sensors.get(int(return_val.strip(f":ST{axis_Id_numeric},")))

    @retry_once
    @axis_checked
    def find_reference_mark(
        self, axis_Id_numeric: int, direction: int, holdTime: int, autoZero: int
    ) -> None:
        return_val = self.socket_put_and_receive(
            f"FRM{axis_Id_numeric},{direction},{holdTime},{autoZero}"
        )

    @retry_once
    @axis_checked
    def set_closed_loop_move_speed(self, axis_Id_numeric: int, move_speed: float) -> None:
        """This command configures the speed control feature of a channel for closed-loop commands move_axis_to_absolute_position. By default the speed control is inactive. In this state the behavior of closed-loop commands is influenced by the maximum driving frequency. If a movement speed is configured, all following closed-loop commands will be executed with the new speed.

        Args:
            axis_Id_numeric (int): Axis number.
            move_speed (float): Movement speed given in mm/s for linear positioners. The valid range is 0 .. 100. A value of 0 (default) deactivates the speed control feature.
        """
        move_speed_in_nm_per_s = int(round(move_speed * 1e6))

        if move_speed_in_nm_per_s > 100e6 or move_speed_in_nm_per_s < 0:
            raise ValueError("Move speed must be within 0 to 100 mm/s.")

        self.socket_put_and_receive(
            f"SCLS{axis_Id_numeric},{move_speed_in_nm_per_s}", raise_if_not_status=True
        )

    @retry_once
    @axis_checked
    def get_closed_loop_move_speed(self, axis_Id_numeric: int) -> float:
        """Returns the currently configured movement speed that is used for closed-loop commands for a channel.

        Args:
            axis_Id_numeric (int): Axis number.

        Returns:
            float: move speed in mm/s. A return value of 0 means that the speed control feature is disabled.
        """

        return_val = self.socket_put_and_receive(f"GCLS{axis_Id_numeric}")
        if self._message_starts_with(return_val, f":CLS{axis_Id_numeric}"):
            return float(return_val.strip(f":CLS{axis_Id_numeric},")) * 1e6

    def describe(self) -> None:
        t = PrettyTable()
        t.title = f"{self.__class__.__name__} on {self.sock.host}:{self.sock.port}"
        t.field_names = ["Axis", "Name", "Connected", "Referenced", "Closed Loop Speed", "Position"]
        for ax in range(self._axes_per_controller):
            axis = self._axis[ax]
            if axis is not None:
                t.add_row(
                    [
                        f"{axis.axis_Id_numeric}/{axis.axis_Id}",
                        axis.name,
                        axis.connected,
                        self.axis_is_referenced(axis.axis_Id_numeric),
                        self.get_closed_loop_move_speed(axis.axis_Id_numeric),
                        axis.readback.read().get(axis.name).get("value"),
                    ]
                )
            else:
                t.add_row([None for t in t.field_names])
        print(t)

    @axis_checked
    def _error_str(self, axis_Id_numeric: int, error_number: int):
        return f":E{axis_Id_numeric},{error_number}"

    def _get_error_code_from_msg(self, msg: str) -> int:
        if msg.startswith(":E"):
            return int(msg.split(",")[-1])
        else:
            return -1

    def _get_axis_from_error_code(self, msg: str) -> int:
        if msg.startswith(":E"):
            try:
                return int(msg.strip(":E").split(",")[0])
            except ValueError:
                return None
        else:
            return None

    def _check_for_error(self, msg: str, axis_Id_numeric: int = None, raise_if_not_status=False):
        if msg.startswith(":E"):
            if axis_Id_numeric is None:
                axis_Id_numeric = self._get_axis_from_error_code(msg)

            if axis_Id_numeric is None:
                raise SmaractCommunicationError(
                    "Could not retrieve axis number from error message."
                )

            if msg != self._error_str(axis_Id_numeric, 0):
                error_code = self._get_error_code_from_msg(msg)
                if error_code != 0:
                    raise SmaractErrorCode(error_code)
        else:
            if raise_if_not_status:
                raise SmaractCommunicationError(
                    "Expected error / status message but failed to parse it."
                )

    def _remove_trailing_characters(self, var: str) -> str:
        if len(var) > 1:
            return var.split("\n")[0]
        return var

    def _message_starts_with(self, msg: str, leading_chars: str) -> bool:
        if msg.startswith(leading_chars):
            return True
        raise SmaractCommunicationError(
            f"Expected to receive a return message starting with {leading_chars} but instead"
            f" received '{msg}'"
        )
