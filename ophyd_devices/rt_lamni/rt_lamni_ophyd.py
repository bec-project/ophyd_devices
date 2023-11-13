import functools
import threading
import time
from typing import List

import numpy as np
from bec_lib import messages, MessageEndpoints, bec_logger
from ophyd import Component as Cpt
from ophyd import Device, PositionerBase, Signal
from ophyd.status import wait as status_wait
from ophyd.utils import LimitError, ReadOnlyError

from ophyd_devices.utils.controller import Controller, threadlocked
from ophyd_devices.utils.socket import SocketIO, SocketSignal, raise_if_disconnected

logger = bec_logger.logger


class RtLamniCommunicationError(Exception):
    pass


class RtLamniError(Exception):
    pass


class BECConfigError(Exception):
    pass


def retry_once(fcn):
    """Decorator to rerun a function in case a CommunicationError was raised. This may happen if the buffer was not empty."""

    @functools.wraps(fcn)
    def wrapper(self, *args, **kwargs):
        try:
            val = fcn(self, *args, **kwargs)
        except (RtLamniCommunicationError, RtLamniError):
            val = fcn(self, *args, **kwargs)
        return val

    return wrapper


class RtLamniController(Controller):
    USER_ACCESS = [
        "socket_put_and_receive",
        "set_rotation_angle",
        "feedback_disable",
        "feedback_enable_without_reset",
        "feedback_disable_and_even_reset_lamni_angle_interferometer",
        "feedback_enable_with_reset",
        "add_pos_to_scan",
        "clear_trajectory_generator",
        "_set_axis_velocity",
        "_set_axis_velocity_maximum_speed",
        "_position_sampling_single_read",
        "_position_sampling_single_reset_and_start_sampling",
    ]

    def __init__(
        self,
        *,
        name="RtLamniController",
        kind=None,
        parent=None,
        socket=None,
        attr_name="",
        labels=None,
    ):
        if not hasattr(self, "_initialized") or not self._initialized:
            self._rtlamni_axis_per_controller = 3
            self._axis = [None for axis_num in range(self._rtlamni_axis_per_controller)]
            self._min_scan_buffer_reached = False
            super().__init__(
                name=name,
                socket=socket,
                attr_name=attr_name,
                parent=parent,
                labels=labels,
                kind=kind,
            )
        self.readout_metadata = {}

    def on(self, controller_num=0) -> None:
        """Open a new socket connection to the controller"""
        if not self.connected:
            try:
                self.sock.open()
                # discuss - after disconnect takes a while for the server to be ready again
                max_retries = 10
                tries = 0
                while not self.connected:
                    try:
                        welcome_message = self.sock.receive()
                        self.connected = True
                    except ConnectionResetError as conn_reset:
                        if tries > max_retries:
                            raise conn_reset
                        tries += 1
                        time.sleep(2)
            except ConnectionRefusedError as conn_error:
                logger.error("Failed to open a connection to RTLamNI.")
                raise RtLamniCommunicationError from conn_error

        else:
            logger.info("The connection has already been established.")
            # warnings.warn(f"The connection has already been established.", stacklevel=2)

        self._update_flyer_device_info()

    def off(self) -> None:
        """Close the socket connection to the controller"""
        if self.connected:
            self.sock.close()
            self.connected = False
        else:
            logger.info("The connection is already closed.")

    def set_axis(self, axis: Device, axis_nr: int) -> None:
        """Assign an axis to a device instance.

        Args:
            axis (Device): Device instance (e.g. GalilMotor)
            axis_nr (int): Controller axis number

        """
        self._axis[axis_nr] = axis

    @threadlocked
    def socket_put(self, val: str) -> None:
        self.sock.put(f"{val}\n".encode())

    @threadlocked
    def socket_get(self) -> str:
        return self.sock.receive().decode()

    @retry_once
    @threadlocked
    def socket_put_and_receive(self, val: str, remove_trailing_chars=True) -> str:
        self.socket_put(val)
        if remove_trailing_chars:
            return self._remove_trailing_characters(self.sock.receive().decode())
        return self.socket_get()

    def is_axis_moving(self, axis_Id) -> bool:
        # this checks that axis is on target
        axis_is_on_target = bool(float(self.socket_put_and_receive(f"o")))
        return not axis_is_on_target

    #    def is_thread_active(self, thread_id: int) -> bool:
    #        val = float(self.socket_put_and_receive(f"MG_XQ{thread_id}"))
    #        if val == -1:
    #            return False
    #        return True

    def _remove_trailing_characters(self, var) -> str:
        if len(var) > 1:
            return var.split("\r\n")[0]
        return var

    @threadlocked
    def set_rotation_angle(self, val: float):
        self.socket_put(f"a{(val-300+30.538)/180*np.pi}")

    @threadlocked
    def stop_all_axes(self):
        self.socket_put("sc")

    @threadlocked
    def feedback_disable(self):
        self.socket_put("J0")
        logger.info("LamNI Feedback disabled.")
        self.set_device_enabled("lsamx", True)
        self.set_device_enabled("lsamy", True)
        self.set_device_enabled("loptx", True)
        self.set_device_enabled("lopty", True)
        self.set_device_enabled("loptz", True)

    @threadlocked
    def _set_axis_velocity(self, um_per_s):
        self.socket_put(f"V{um_per_s}")

    @threadlocked
    def _set_axis_velocity_maximum_speed(self):
        self.socket_put(f"V0")

    # for developement of soft continuous scanning
    @threadlocked
    def _position_sampling_single_reset_and_start_sampling(self):
        self.socket_put(f"Ss")

    @threadlocked
    def _position_sampling_single_read(self):
        (number_of_samples, sum0, sum0_2, sum1, sum1_2, sum2, sum2_2) = self.socket_put_and_receive(
            f"Sr"
        ).split(",")
        avg_x = float(sum1) / int(number_of_samples)
        avg_y = float(sum0) / int(number_of_samples)
        stdev_x = np.sqrt(
            float(sum1_2) / int(number_of_samples)
            - np.power(float(sum1) / int(number_of_samples), 2)
        )
        stdev_y = np.sqrt(
            float(sum0_2) / int(number_of_samples)
            - np.power(float(sum0) / int(number_of_samples), 2)
        )
        return (avg_x, avg_y, stdev_x, stdev_y)

    @threadlocked
    def feedback_enable_without_reset(self):
        # read current interferometer position
        return_table = (self.socket_put_and_receive(f"J4")).split(",")
        x_curr = float(return_table[2])
        y_curr = float(return_table[1])
        # set these as closed loop target position
        self.socket_put(f"pa0,{x_curr:.4f}")
        self.socket_put(f"pa1,{y_curr:.4f}")
        self.get_device_manager().devices.rtx.obj.user_setpoint.set_with_feedback_disabled(x_curr)
        self.get_device_manager().devices.rty.obj.user_setpoint.set_with_feedback_disabled(y_curr)
        self.socket_put("J5")
        logger.info("LamNI Feedback enabled (without reset).")
        self.set_device_enabled("lsamx", False)
        self.set_device_enabled("lsamy", False)
        self.set_device_enabled("loptx", False)
        self.set_device_enabled("lopty", False)
        self.set_device_enabled("loptz", False)

    @threadlocked
    def feedback_disable_and_even_reset_lamni_angle_interferometer(self):
        self.socket_put("J6")
        logger.info("LamNI Feedback disabled including the angular interferometer.")
        self.set_device_enabled("lsamx", True)
        self.set_device_enabled("lsamy", True)
        self.set_device_enabled("loptx", True)
        self.set_device_enabled("lopty", True)
        self.set_device_enabled("loptz", True)

    def get_device_manager(self):
        for axis in self._axis:
            if hasattr(axis, "device_manager") and axis.device_manager:
                return axis.device_manager
        raise BECConfigError("Could not access the device_manager")

    def get_axis_by_name(self, name):
        for axis in self._axis:
            if axis:
                if axis.name == name:
                    return axis
        raise RuntimeError(f"Could not find an axis with name {name}")

    @threadlocked
    def clear_trajectory_generator(self):
        self.socket_put("sc")
        logger.info("LamNI scan stopped and deleted, moving to start position")

    def add_pos_to_scan(self, positions) -> None:
        def send_positions(parent, positions):
            parent._min_scan_buffer_reached = False
            for pos_index, pos in enumerate(positions):
                parent.socket_put_and_receive(f"s{pos[0]},{pos[1]},0")
                if pos_index > 100:
                    parent._min_scan_buffer_reached = True
            parent._min_scan_buffer_reached = True

        threading.Thread(target=send_positions, args=(self, positions), daemon=True).start()

    @retry_once
    @threadlocked
    def get_scan_status(self):
        return_table = (self.socket_put_and_receive(f"sr")).split(",")
        if len(return_table) != 3:
            raise RtLamniCommunicationError(
                f"Expected to receive 3 return values. Instead received {return_table}"
            )
        mode = int(return_table[0])
        # mode 0: direct positioning
        # mode 1: running internal timer (not tested/used anymore)
        # mode 2: rt point scan running
        # mode 3: rt point scan starting
        # mode 5/6: rt continuous scanning (not available in LamNI)
        number_of_positions_planned = int(return_table[1])
        current_position_in_scan = int(return_table[2])
        return (mode, number_of_positions_planned, current_position_in_scan)

    @threadlocked
    def start_scan(self):
        interferometer_feedback_not_running = int((self.socket_put_and_receive("J2")).split(",")[0])
        if interferometer_feedback_not_running == 1:
            logger.error(
                "Cannot start scan because feedback loop is not running or there is an interferometer error."
            )
            raise RtLamniError(
                "Cannot start scan because feedback loop is not running or there is an interferometer error."
            )
            # here exception
        (mode, number_of_positions_planned, current_position_in_scan) = self.get_scan_status()

        if number_of_positions_planned == 0:
            logger.error("Cannot start scan because no target positions are planned.")
            raise RtLamniError("Cannot start scan because no target positions are planned.")
            # hier exception
        # start a point-by-point scan (for cont scan in flomni it would be "sa")
        self.socket_put_and_receive("sd")

    def start_readout(self):
        readout = threading.Thread(target=self.read_positions_from_sampler)
        readout.start()

    def _update_flyer_device_info(self):
        flyer_info = self._get_flyer_device_info()
        self.get_device_manager().producer.set(
            MessageEndpoints.device_info("rt_scan"),
            messages.DeviceInfoMessage(device="rt_scan", info=flyer_info).dumps(),
        )

    def _get_flyer_device_info(self) -> dict:
        return {
            "device_name": self.name,
            "device_attr_name": getattr(self, "attr_name", ""),
            "device_dotted_name": getattr(self, "dotted_name", ""),
            "device_info": {
                "device_base_class": "ophydobject",
                "signals": [],
                "hints": {"fields": ["average_x_st_fzp", "average_y_st_fzp"]},
                "describe": {},
                "describe_configuration": {},
                "sub_devices": [],
                "custom_user_access": [],
            },
        }

    def kickoff(self, metadata):
        self.readout_metadata = metadata
        while not self._min_scan_buffer_reached:
            time.sleep(0.001)
        self.start_scan()
        time.sleep(0.1)
        self.start_readout()

    def _get_signals_from_table(self, return_table) -> dict:
        self.average_stdeviations_x_st_fzp += float(return_table[5])
        self.average_stdeviations_y_st_fzp += float(return_table[8])
        self.average_lamni_angle += float(return_table[19])
        signals = {
            "target_x": {"value": float(return_table[3])},
            "average_x_st_fzp": {"value": float(return_table[4])},
            "stdev_x_st_fzp": {"value": float(return_table[5])},
            "target_y": {"value": float(return_table[6])},
            "average_y_st_fzp": {"value": float(return_table[7])},
            "stdev_y_st_fzp": {"value": float(return_table[8])},
            "average_cap1": {"value": float(return_table[9])},
            "stdev_cap1": {"value": float(return_table[10])},
            "average_cap2": {"value": float(return_table[11])},
            "stdev_cap2": {"value": float(return_table[12])},
            "average_cap3": {"value": float(return_table[13])},
            "stdev_cap3": {"value": float(return_table[14])},
            "average_cap4": {"value": float(return_table[15])},
            "stdev_cap4": {"value": float(return_table[16])},
            "average_cap5": {"value": float(return_table[17])},
            "stdev_cap5": {"value": float(return_table[18])},
            "average_angle_interf_ST": {"value": float(return_table[19])},
            "stdev_angle_interf_ST": {"value": float(return_table[20])},
            "average_stdeviations_x_st_fzp": {
                "value": self.average_stdeviations_x_st_fzp / (int(return_table[0]) + 1)
            },
            "average_stdeviations_y_st_fzp": {
                "value": self.average_stdeviations_y_st_fzp / (int(return_table[0]) + 1)
            },
            "average_lamni_angle": {"value": self.average_lamni_angle / (int(return_table[0]) + 1)},
        }
        return signals

    def read_positions_from_sampler(self):
        # this was for reading after the scan completed
        number_of_samples_to_read = 1  # self.get_scan_status()[1]  #number of valid samples, will be updated upon first data read

        read_counter = 0
        previous_point_in_scan = 0

        self.average_stdeviations_x_st_fzp = 0
        self.average_stdeviations_y_st_fzp = 0
        self.average_lamni_angle = 0

        mode, number_of_positions_planned, current_position_in_scan = self.get_scan_status()

        # if not (mode==2 or mode==3):
        #    error
        self.get_device_manager().producer.set_and_publish(
            MessageEndpoints.device_status("rt_scan"),
            messages.DeviceStatusMessage(
                device="rt_scan", status=1, metadata=self.readout_metadata
            ).dumps(),
        )
        # while scan is running
        while mode > 0:
            # logger.info(f"Current scan position {current_position_in_scan} out of {number_of_positions_planned}")
            mode, number_of_positions_planned, current_position_in_scan = self.get_scan_status()
            time.sleep(0.01)
            if current_position_in_scan > 5:
                while current_position_in_scan > read_counter + 1:
                    return_table = (self.socket_put_and_receive(f"r{read_counter}")).split(",")
                    # logger.info(f"{return_table}")
                    logger.info(f"Read {read_counter} out of {number_of_positions_planned}")

                    read_counter = read_counter + 1

                    signals = self._get_signals_from_table(return_table)

                    self.publish_device_data(signals=signals, pointID=int(return_table[0]))

        time.sleep(0.05)

        # read the last samples even though scan is finished already
        while number_of_positions_planned > read_counter:
            return_table = (self.socket_put_and_receive(f"r{read_counter}")).split(",")
            logger.info(f"Read {read_counter} out of {number_of_positions_planned}")
            # logger.info(f"{return_table}")
            read_counter = read_counter + 1

            signals = self._get_signals_from_table(return_table)
            self.publish_device_data(signals=signals, pointID=int(return_table[0]))

        self.get_device_manager().producer.set_and_publish(
            MessageEndpoints.device_status("rt_scan"),
            messages.DeviceStatusMessage(
                device="rt_scan", status=0, metadata=self.readout_metadata
            ).dumps(),
        )

        logger.info(
            f"LamNI statistics: Average of all standard deviations: x {self.average_stdeviations_x_st_fzp/number_of_samples_to_read}, y {self.average_stdeviations_y_st_fzp/number_of_samples_to_read}, angle {self.average_lamni_angle/number_of_samples_to_read}."
        )

    def publish_device_data(self, signals, pointID):
        self.get_device_manager().producer.send(
            MessageEndpoints.device_read("rt_lamni"),
            messages.DeviceMessage(
                signals=signals,
                metadata={"pointID": pointID, **self.readout_metadata},
            ).dumps(),
        )

    def feedback_status_angle_lamni(self) -> bool:
        return_table = (self.socket_put_and_receive(f"J7")).split(",")
        logger.debug(
            f"LamNI angle interferomter status {bool(return_table[0])}, position {float(return_table[1])}, signal {float(return_table[2])}"
        )
        return bool(return_table[0])

    def feedback_enable_with_reset(self):
        if not self.feedback_status_angle_lamni():
            self.feedback_disable_and_even_reset_lamni_angle_interferometer()
            logger.info(f"LamNI resetting interferometer inclusive angular interferomter.")
        else:
            self.feedback_disable()
            logger.info(
                f"LamNI resetting interferomter except angular interferometer which is already running."
            )

        # set these as closed loop target position

        self.socket_put(f"pa0,0")
        self.get_axis_by_name("rtx").user_setpoint.setpoint = 0
        self.socket_put(f"pa1,0")
        self.get_axis_by_name("rty").user_setpoint.setpoint = 0
        self.socket_put(
            f"pa2,0"
        )  # we set all three outputs of the traj. gen. although in LamNI case only 0,1 are used
        self.clear_trajectory_generator()

        self.get_device_manager().devices.lsamrot.obj.move(0, wait=True)

        galil_controller_rt_status = (
            self.get_device_manager().devices.lsamx.obj.controller.lgalil_is_air_off_and_orchestra_enabled()
        )

        if galil_controller_rt_status == 0:
            logger.error(
                "Cannot enable feedback. The small rotation air is on and/or orchestra disabled by the motor controller."
            )
            raise RtLamniError(
                "Cannot enable feedback. The small rotation air is on and/or orchestra disabled by the motor controller."
            )

        time.sleep(0.03)

        lsamx_user_params = self.get_device_manager().devices.lsamx.user_parameter
        if lsamx_user_params is None or lsamx_user_params.get("center") is None:
            raise RuntimeError("lsamx center is not defined")
        lsamy_user_params = self.get_device_manager().devices.lsamy.user_parameter
        if lsamy_user_params is None or lsamy_user_params.get("center") is None:
            raise RuntimeError("lsamy center is not defined")
        lsamx_center = lsamx_user_params.get("center")
        lsamy_center = lsamy_user_params.get("center")
        self.get_device_manager().devices.lsamx.obj.move(lsamx_center, wait=True)
        self.get_device_manager().devices.lsamy.obj.move(lsamy_center, wait=True)
        self.socket_put("J1")

        _waitforfeedbackctr = 0

        interferometer_feedback_not_running = int((self.socket_put_and_receive("J2")).split(",")[0])

        while interferometer_feedback_not_running == 1 and _waitforfeedbackctr < 100:
            time.sleep(0.01)
            _waitforfeedbackctr = _waitforfeedbackctr + 1
            interferometer_feedback_not_running = int(
                (self.socket_put_and_receive("J2")).split(",")[0]
            )

        self.set_device_enabled("lsamx", False)
        self.set_device_enabled("lsamy", False)
        self.set_device_enabled("loptx", False)
        self.set_device_enabled("lopty", False)
        self.set_device_enabled("loptz", False)

        if interferometer_feedback_not_running == 1:
            logger.error(
                "Cannot start scan because feedback loop is not running or there is an interferometer error."
            )
            raise RtLamniError(
                "Cannot start scan because feedback loop is not running or there is an interferometer error."
            )

        time.sleep(0.01)

        # ptychography_alignment_done = 0

    def set_device_enabled(self, device_name: str, enabled: bool) -> None:
        """enable / disable a device"""
        if device_name not in self.get_device_manager().devices:
            logger.warning(
                f"Device {device_name} is not configured and cannot be enabled/disabled."
            )
            return
        self.get_device_manager().devices[device_name].enabled_set = enabled


class RtLamniSignalBase(SocketSignal):
    def __init__(self, signal_name, **kwargs):
        self.signal_name = signal_name
        super().__init__(**kwargs)
        self.controller = self.parent.controller
        self.sock = self.parent.controller.sock


class RtLamniSignalRO(RtLamniSignalBase):
    def __init__(self, signal_name, **kwargs):
        super().__init__(signal_name, **kwargs)
        self._metadata["write_access"] = False

    def _socket_set(self, val):
        raise ReadOnlyError("Read-only signals cannot be set")


class RtLamniReadbackSignal(RtLamniSignalRO):
    @retry_once
    @threadlocked
    def _socket_get(self) -> float:
        """Get command for the readback signal

        Returns:
        float: Readback value after adjusting for sign and motor resolution.
        """
        return_table = (self.controller.socket_put_and_receive(f"J4")).split(",")
        print(return_table)
        if self.parent.axis_Id_numeric == 0:
            readback_index = 2
        elif self.parent.axis_Id_numeric == 1:
            readback_index = 1
        else:
            raise RtLamniError("Currently, only two axes are supported.")

        current_pos = float(return_table[readback_index])

        current_pos *= self.parent.sign
        return current_pos


class RtLamniSetpointSignal(RtLamniSignalBase):
    setpoint = 0

    def _socket_get(self) -> float:
        """Get command for receiving the setpoint / target value.
        The value is not pulled from the controller but instead just the last setpoint used.

        Returns:
            float: setpoint / target value
        """
        return self.setpoint

    @retry_once
    @threadlocked
    def _socket_set(self, val: float) -> None:
        """Set a new target value / setpoint value. Before submission, the target value is adjusted for the axis' sign.
        Furthermore, it is ensured that all axes are referenced before a new setpoint is submitted.

        Args:
            val (float): Target value / setpoint value

        Raises:
            RtLamniError: Raised if interferometer feedback is disabled.

        """
        interferometer_feedback_not_running = int(
            (self.controller.socket_put_and_receive("J2")).split(",")[0]
        )
        if interferometer_feedback_not_running != 0:
            raise RtLamniError(
                "The interferometer feedback is not running. Either it is turned off or and interferometer error occured."
            )
        self.set_with_feedback_disabled(val)

    def set_with_feedback_disabled(self, val):
        target_val = val * self.parent.sign
        self.setpoint = target_val
        self.controller.socket_put(f"pa{self.parent.axis_Id_numeric},{target_val:.4f}")


class RtLamniMotorIsMoving(RtLamniSignalRO):
    def _socket_get(self):
        return self.controller.is_axis_moving(self.parent.axis_Id_numeric)

    def get(self):
        val = super().get()
        if val is not None:
            self._run_subs(
                sub_type=self.SUB_VALUE,
                value=val,
                timestamp=time.time(),
            )
        return val


class RtLamniFeedbackRunning(RtLamniSignalRO):
    @threadlocked
    def _socket_get(self):
        if int((self.controller.socket_put_and_receive("J2")).split(",")[0]) == 0:
            return 1
        else:
            return 0


class RtLamniMotor(Device, PositionerBase):
    USER_ACCESS = ["controller"]
    readback = Cpt(
        RtLamniReadbackSignal,
        signal_name="readback",
        kind="hinted",
    )
    user_setpoint = Cpt(RtLamniSetpointSignal, signal_name="setpoint")

    motor_is_moving = Cpt(RtLamniMotorIsMoving, signal_name="motor_is_moving", kind="normal")
    high_limit_travel = Cpt(Signal, value=0, kind="omitted")
    low_limit_travel = Cpt(Signal, value=0, kind="omitted")

    SUB_READBACK = "readback"
    SUB_CONNECTION_CHANGE = "connection_change"
    _default_sub = SUB_READBACK

    def __init__(
        self,
        axis_Id,
        prefix="",
        *,
        name,
        kind=None,
        read_attrs=None,
        configuration_attrs=None,
        parent=None,
        host="mpc2680.psi.ch",
        port=3333,
        sign=1,
        socket_cls=SocketIO,
        device_manager=None,
        limits=None,
        **kwargs,
    ):
        self.axis_Id = axis_Id
        self.sign = sign
        self.controller = RtLamniController(socket=socket_cls(host=host, port=port))
        self.controller.set_axis(axis=self, axis_nr=self.axis_Id_numeric)
        self.device_manager = device_manager
        self.tolerance = kwargs.pop("tolerance", 0.5)

        super().__init__(
            prefix,
            name=name,
            kind=kind,
            read_attrs=read_attrs,
            configuration_attrs=configuration_attrs,
            parent=parent,
            **kwargs,
        )
        self.readback.name = self.name
        self.controller.subscribe(
            self._update_connection_state, event_type=self.SUB_CONNECTION_CHANGE
        )
        self._update_connection_state()

        # self.readback.subscribe(self._forward_readback, event_type=self.readback.SUB_VALUE)
        if limits is not None:
            assert len(limits) == 2
            self.low_limit_travel.put(limits[0])
            self.high_limit_travel.put(limits[1])

    @property
    def limits(self):
        return (self.low_limit_travel.get(), self.high_limit_travel.get())

    @property
    def low_limit(self):
        return self.limits[0]

    @property
    def high_limit(self):
        return self.limits[1]

    def check_value(self, pos):
        """Check that the position is within the soft limits"""
        low_limit, high_limit = self.limits

        if low_limit < high_limit and not (low_limit <= pos <= high_limit):
            raise LimitError(f"position={pos} not within limits {self.limits}")

    def _update_connection_state(self, **kwargs):
        for walk in self.walk_signals():
            walk.item._metadata["connected"] = self.controller.connected

    def _forward_readback(self, **kwargs):
        kwargs.pop("sub_type")
        self._run_subs(sub_type="readback", **kwargs)

    @raise_if_disconnected
    def move(self, position, wait=True, **kwargs):
        """Move to a specified position, optionally waiting for motion to
        complete.

        Parameters
        ----------
        position
            Position to move to
        moved_cb : callable
            Call this callback when movement has finished. This callback must
            accept one keyword argument: 'obj' which will be set to this
            positioner instance.
        timeout : float, optional
            Maximum time to wait for the motion. If None, the default timeout
            for this positioner is used.

        Returns
        -------
        status : MoveStatus

        Raises
        ------
        TimeoutError
            When motion takes longer than `timeout`
        ValueError
            On invalid positions
        RuntimeError
            If motion fails other than timing out
        """
        self._started_moving = False
        timeout = kwargs.pop("timeout", 100)
        status = super().move(position, timeout=timeout, **kwargs)
        self.user_setpoint.put(position, wait=False)

        def move_and_finish():
            while self.motor_is_moving.get():
                print("motor is moving")
                val = self.readback.read()
                self._run_subs(
                    sub_type=self.SUB_READBACK,
                    value=val,
                    timestamp=time.time(),
                )
                time.sleep(0.01)
            print("Move finished")
            self._done_moving()

        threading.Thread(target=move_and_finish, daemon=True).start()
        try:
            if wait:
                status_wait(status)
        except KeyboardInterrupt:
            self.stop()
            raise

        return status

    @property
    def axis_Id(self):
        return self._axis_Id_alpha

    @axis_Id.setter
    def axis_Id(self, val):
        if isinstance(val, str):
            if len(val) != 1:
                raise ValueError(f"Only single-character axis_Ids are supported.")
            self._axis_Id_alpha = val
            self._axis_Id_numeric = ord(val.lower()) - 97
        else:
            raise TypeError(f"Expected value of type str but received {type(val)}")

    @property
    def axis_Id_numeric(self):
        return self._axis_Id_numeric

    @axis_Id_numeric.setter
    def axis_Id_numeric(self, val):
        if isinstance(val, int):
            if val > 26:
                raise ValueError(f"Numeric value exceeds supported range.")
            self._axis_Id_alpha = val
            self._axis_Id_numeric = (chr(val + 97)).capitalize()
        else:
            raise TypeError(f"Expected value of type int but received {type(val)}")

    def kickoff(self, metadata, **kwargs) -> None:
        self.controller.kickoff(metadata)

    @property
    def egu(self):
        """The engineering units (EGU) for positions"""
        return "um"

    # how is this used later?

    def stage(self) -> List[object]:
        return super().stage()

    def unstage(self) -> List[object]:
        return super().unstage()

    def stop(self, *, success=False):
        self.controller.stop_all_axes()
        return super().stop(success=success)


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    mock = False
    if not mock:
        rty = RtLamniMotor("B", name="rty", host="mpc2680.psi.ch", port=3333, sign=1)
        rty.stage()
        status = rty.move(0, wait=True)
        status = rty.move(10, wait=True)
        rty.read()

        rty.get()
        rty.describe()

        rty.unstage()
    else:
        from ophyd_devices.utils.socket import SocketMock

        rtx = RtLamniMotor("A", name="rtx", host="mpc2680.psi.ch", port=3333, socket_cls=SocketMock)
        rty = RtLamniMotor("B", name="rty", host="mpc2680.psi.ch", port=3333, socket_cls=SocketMock)
        rtx.stage()
        # rty.stage()
