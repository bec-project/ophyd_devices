import threading
import time
from typing import List

import numpy as np
from bec_lib import MessageEndpoints, bec_logger, messages
from ophyd import Component as Cpt
from ophyd import Device, PositionerBase, Signal
from ophyd.status import wait as status_wait
from ophyd.utils import LimitError
from prettytable import PrettyTable

from ophyd_devices.rt_lamni.rt_ophyd import (
    BECConfigError,
    RtCommunicationError,
    RtController,
    RtError,
    RtReadbackSignal,
    RtSetpointSignal,
    RtSignalRO,
    retry_once,
)
from ophyd_devices.utils.controller import threadlocked
from ophyd_devices.utils.socket import SocketIO, raise_if_disconnected

logger = bec_logger.logger


class RtFlomniController(RtController):
    USER_ACCESS = [
        "socket_put_and_receive",
        "set_rotation_angle",
        "feedback_disable",
        "feedback_enable_without_reset",
        "feedback_enable_with_reset",
        "feedback_is_running",
        "add_pos_to_scan",
        "clear_trajectory_generator",
        "show_cyclic_error_compensation",
        "laser_tracker_on",
        "laser_tracker_off",
        "laser_tracker_show_all",
        "show_signal_strength_interferometer",
    ]

    def __init__(
        self,
        *,
        name=None,
        socket_cls=None,
        socket_host=None,
        socket_port=None,
        attr_name="",
        parent=None,
        labels=None,
        kind=None,
    ):
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
        self.tracker_info = {}
        self._min_scan_buffer_reached = False
        self.rt_pid_voltage = None

    def add_pos_to_scan(self, positions) -> None:
        def send_positions(parent, positions):
            parent._min_scan_buffer_reached = False
            start_time = time.time()
            for pos_index, pos in enumerate(positions):
                parent.socket_put_and_receive(f"s{pos[0]},{pos[1]},{pos[2]}")
                if pos_index > 100:
                    parent._min_scan_buffer_reached = True
            parent._min_scan_buffer_reached = True
            logger.info(
                f"Sending {len(positions)} positions took {time.time()-start_time} seconds."
            )

        threading.Thread(target=send_positions, args=(self, positions), daemon=True).start()

    def move_to_zero(self):
        self.socket_put("pa0,0")
        self.get_axis_by_name("rtx").user_setpoint.setpoint = 0
        self.socket_put("pa1,0")
        self.get_axis_by_name("rty").user_setpoint.setpoint = 0
        self.socket_put("pa2,0")
        self.get_axis_by_name("rtz").user_setpoint.setpoint = 0
        time.sleep(0.05)

    def feedback_is_running(self) -> bool:
        status = int(float(self.socket_put_and_receive("l2").strip()))
        if status == 1:
            return False
        return True

    def feedback_enable_with_reset(self):
        self.socket_put("l0")  # disable feedback

        self.move_to_zero()

        if not self.slew_rate_limiters_on_target() or np.abs(self.pid_y()) > 0.1:
            print("Please wait, slew rate limiters not on target.")
            logger.info("Please wait, slew rate limiters not on target.")
        while not self.slew_rate_limiters_on_target() or np.abs(self.pid_y()) > 0.1:
            time.sleep(0.05)

        self.get_device_manager().devices.rty.update_user_parameter({"tomo_additional_offsety": 0})
        self.clear_trajectory_generator()

        self.laser_tracker_on()

        # move to 0. FUPR will set the rotation angle during readout
        self.get_device_manager().devices.fsamroy.obj.move(0, wait=True)

        fsamx = self.get_device_manager().devices.fsamx

        fsamx.obj.pid_x_correction = 0
        fsamx.obj.controller.socket_put_confirmed("axspeed[4]=0.1*stppermm[4]")
        fsamx_in = fsamx.user_parameter.get("in")
        if not np.isclose(fsamx.obj.readback.get(), fsamx_in, atol=0.3):
            print(
                "Something is wrong. fsamx is very far from the samx_in position. Don't dare correct automatically."
            )
            raise RtError(
                "Something is wrong. fsamx is very far from the samx_in position. Don't dare correct automatically."
            )

        if not np.isclose(fsamx.obj.readback.get(), fsamx_in, atol=0.01):
            fsamx.read_only = False
            fsamx.obj.move(fsamx_in, wait=True)
            fsamx.read_only = True
            time.sleep(1)

        self.socket_put("l1")
        time.sleep(0.4)

        if not self.feedback_is_running():
            print("Feedback is not running; likely an error in the interferometer.")
            raise RtError("Feedback is not running; likely an error in the interferometer.")

        time.sleep(1.5)
        self.show_cyclic_error_compensation()

        self.rt_pid_voltage = self.get_pid_x()
        rtx = self.get_device_manager().devices.rtx
        rtx.update_user_parameter({"rt_pid_voltage": self.rt_pid_voltage})

        self.set_device_enabled("fsamx", False)
        self.set_device_enabled("fsamy", False)
        self.set_device_enabled("foptx", False)
        self.set_device_enabled("fopty", False)
        print("rt feedback is now enabled.")

    def move_samx_to_scan_region(self, fovx: float, cenx: float):
        if self.rt_pid_voltage is None:
            rtx = self.get_device_manager().devices.rtx
            self.rt_pid_voltage = rtx.user_parameter.get("rt_pid_voltage")
            if self.rt_pid_voltage is None:
                raise RtError(
                    "rt_pid_voltage not set in rtx user parameters. Please run feedback_enable_with_reset first."
                )
            logger.info(f"Using PID voltage from rtx user parameter: {self.rt_pid_voltage}")
        expected_voltage = self.rt_pid_voltage + fovx / 2 * 7 / 100
        logger.info(f"Expected PID voltage: {expected_voltage}")
        logger.info(f"Current PID voltage: {self.get_pid_x()}")

        wait_on_exit = False
        while True:
            if np.abs(self.get_pid_x() - expected_voltage) < 1:
                break
            wait_on_exit = True
            self.socket_put("v0")
            fsamx = self.get_device_manager().devices.fsamx
            fsamx.read_only = False
            fsamx.obj.controller.socket_put_confirmed("axspeed[4]=0.1*stppermm[4]")
            fsamx.obj.pid_x_correction -= (self.get_pid_x() - expected_voltage) * 0.007
            logger.info(f"Correcting fsamx by {fsamx.obj.pid_x_correction}")
            fsamx_in = fsamx.user_parameter.get("in")
            fsamx.obj.move(fsamx_in + cenx / 1000 + fsamx.obj.pid_x_correction, wait=True)
            fsamx.read_only = True
            time.sleep(0.1)
            self.laser_tracker_on()
            time.sleep(0.01)

        if wait_on_exit:
            time.sleep(1)

        self.socket_put("v1")

    @threadlocked
    def clear_trajectory_generator(self):
        self.socket_put("sc")
        logger.info("flomni scan stopped and deleted, moving to start position")

    def feedback_enable_without_reset(self):
        self.laser_tracker_on()
        self.socket_put("l3")
        time.sleep(0.01)

        if not self.feedback_is_running():
            print("Feedback is not running; likely an error in the interferometer.")
            raise RtError("Feedback is not running; likely an error in the interferometer.")

        self.set_device_enabled("fsamx", False)
        self.set_device_enabled("fsamy", False)
        self.set_device_enabled("foptx", False)
        self.set_device_enabled("fopty", False)

    def feedback_disable(self):
        self.clear_trajectory_generator()
        self.move_to_zero()
        self.socket_put("l0")

        self.set_device_enabled("fsamx", True)
        self.set_device_enabled("fsamy", True)
        self.set_device_enabled("foptx", True)
        self.set_device_enabled("fopty", True)

        fsamx = self.get_device_manager().devices.fsamx
        fsamx.obj.controller.socket_put_confirmed("axspeed[4]=025*stppermm[4]")
        print("rt feedback is now disalbed.")

    def get_pid_x(self) -> float:
        voltage = float(self.socket_put_and_receive("g").strip())
        return voltage

    def show_cyclic_error_compensation(self):
        cec0 = int(float(self.socket_put_and_receive("w0").strip()))
        cec1 = int(float(self.socket_put_and_receive("w0").strip()))

        if cec0 == 32:
            logger.info("Cyclic Error Compensation: y-axis is initialized")
        else:
            logger.info("Cyclic Error Compensation: y-axis is NOT initialized")
            print("Cyclic Error Compensation: y-axis is NOT initialized")
        if cec1 == 32:
            logger.info("Cyclic Error Compensation: x-axis is initialized")
        else:
            logger.info("Cyclic Error Compensation: x-axis is NOT initialized")
            print("Cyclic Error Compensation: x-axis is NOT initialized")

    def set_rotation_angle(self, val: float) -> None:
        self.socket_put(f"a{val/180*np.pi}")

    def laser_tracker_on(self):
        self.laser_update_tracker_info()

        if not self.tracker_info["enabled_z"] or not self.tracker_info["enabled_y"]:
            logger.info("Enabling the laser tracker. Please wait...")
            print("Enabling the laser tracker. Please wait...")

            tracker_intensity = self.tracker_info["tracker_intensity"]
            if (
                tracker_intensity < self.tracker_info["threshold_intensity_y"]
                or tracker_intensity < self.tracker_info["threshold_intensity_z"]
            ):
                logger.info(self.tracker_info)
                print("The tracker cannot be enabled because the beam intensity it low.")
                raise RtError("The tracker cannot be enabled because the beam intensity it low.")

            self.move_to_zero()
            self.socket_put("T1")
            time.sleep(0.5)

            self.get_device_manager().devices.ftrackz.obj.controller.socket_put_confirmed(
                "trackyct=0"
            )
            self.get_device_manager().devices.ftrackz.obj.controller.socket_put_confirmed(
                "trackzct=0"
            )

        self.laser_tracker_wait_on_target()
        logger.info("Laser tracker running!")
        print("Laser tracker running!")

    def laser_tracker_off(self):
        self.socket_put("T0")
        logger.info("Disabled the laser tracker")
        print("Disabled the laser tracker")

    def laser_tracker_show_all(self):
        self.laser_update_tracker_info()
        t = PrettyTable()
        t.title = f"Laser Tracker Info"
        t.field_names = ["Name", "Value"]
        for key, val in self.tracker_info.items():
            t.add_row([key, val])
        print(t)

    def laser_update_tracker_info(self):
        ret = self.socket_put_and_receive("Ts")

        # remove trailing \n
        ret = ret.split("\n")[0]

        tracker_values = [float(val) for val in ret.split(",")]
        self.tracker_info = {
            "tracker_intensity": tracker_values[2],
            "threshold_intensity_y": tracker_values[8],
            "enabled_y": bool(tracker_values[10]),
            "beampos_y": tracker_values[5],
            "target_y": tracker_values[6],
            "piezo_voltage_y": tracker_values[9],
            "threshold_intensity_z": tracker_values[3],
            "enabled_z": bool(tracker_values[10]),
            "beampos_z": tracker_values[0],
            "target_z": tracker_values[1],
            "piezo_voltage_z": tracker_values[4],
        }

    def laser_tracker_galil_enable(self):
        ftrackz_con = self.get_device_manager().devices.ftrackz.obj.controller
        ftrackz_con.socket_put_confirmed("tracken=1")
        ftrackz_con.socket_put_confirmed("trackyct=0")
        ftrackz_con.socket_put_confirmed("trackzct=0")
        ftrackz_con.socket_put_confirmed("XQ#Tracker")

    def laser_tracker_on_target(self) -> bool:
        self.laser_update_tracker_info()
        if np.isclose(
            self.tracker_info["beampos_y"], self.tracker_info["target_y"], atol=0.02
        ) and np.isclose(self.tracker_info["beampos_z"], self.tracker_info["target_z"], atol=0.02):
            return True
        return False

    def laser_tracker_wait_on_target(self):
        max_repeat = 25
        count = 0
        while not self.laser_tracker_on_target():
            self.laser_tracker_galil_enable()
            logger.info("Waiting for laser tracker to reach target.")
            time.sleep(0.5)
            count += 1
            if count > max_repeat:
                print("Failed to reach laser target position.")
                raise RtError("Failed to reach laser target position.")

    def slew_rate_limiters_on_target(self) -> bool:
        ret = int(float(self.socket_put_and_receive("y").strip()))
        if ret == 3:
            return True
        return False

    def pid_y(self) -> float:
        ret = float(self.socket_put_and_receive("G").strip())
        return ret

    def read_ssi_interferometer(self, axis_number):
        val = float(self.socket_put_and_receive(f"j{axis_number}").strip())
        return val

    def show_signal_strength_interferometer(self):
        t = PrettyTable()
        t.title = f"Interferometer signal strength"
        t.field_names = ["Axis", "Value"]
        for i in range(3):
            t.add_row([i, self.read_ssi_interferometer(i)])
        print(t)

    def _get_signals_from_table(self, return_table) -> dict:
        self.average_stdeviations_x_st_fzp += float(return_table[4])
        self.average_stdeviations_y_st_fzp += float(return_table[7])
        signals = {
            "target_x": {"value": float(return_table[2])},
            "average_x_st_fzp": {"value": float(return_table[3])},
            "stdev_x_st_fzp": {"value": float(return_table[4])},
            "target_y": {"value": float(return_table[5])},
            "average_y_st_fzp": {"value": float(return_table[6])},
            "stdev_y_st_fzp": {"value": float(return_table[7])},
            "average_rotz": {"value": float(return_table[8])},
            "stdev_rotz": {"value": float(return_table[9])},
            "average_stdeviations_x_st_fzp": {
                "value": self.average_stdeviations_x_st_fzp / (int(return_table[0]) + 1)
            },
            "average_stdeviations_y_st_fzp": {
                "value": self.average_stdeviations_y_st_fzp / (int(return_table[0]) + 1)
            },
        }
        return signals

    @threadlocked
    def start_scan(self):
        if not self.feedback_is_running():
            logger.error(
                "Cannot start scan because feedback loop is not running or there is an"
                " interferometer error."
            )
            raise RtError(
                "Cannot start scan because feedback loop is not running or there is an"
                " interferometer error."
            )
            # here exception
        (mode, number_of_positions_planned, current_position_in_scan) = self.get_scan_status()

        if number_of_positions_planned == 0:
            logger.error("Cannot start scan because no target positions are planned.")
            raise RtError("Cannot start scan because no target positions are planned.")
            # hier exception
        # start a point-by-point scan (for cont scan in flomni it would be "sa")
        self.socket_put_and_receive("sd")

    @retry_once
    @threadlocked
    def get_scan_status(self):
        return_table = (self.socket_put_and_receive("sr")).split(",")
        if len(return_table) != 3:
            raise RtCommunicationError(
                f"Expected to receive 3 return values. Instead received {return_table}"
            )
        mode = int(float(return_table[0]))
        # mode 0: direct positioning
        # mode 1: running internal timer (not tested/used anymore)
        # mode 2: rt point scan running
        # mode 3: rt point scan starting
        # mode 5/6: rt continuous scanning (not available in LamNI)
        number_of_positions_planned = int(float(return_table[1]))
        current_position_in_scan = int(float(return_table[2]))
        return (mode, number_of_positions_planned, current_position_in_scan)

    def get_device_manager(self):
        for axis in self._axis:
            if hasattr(axis, "device_manager") and axis.device_manager:
                return axis.device_manager
        raise BECConfigError("Could not access the device_manager")

    def read_positions_from_sampler(self):
        # this was for reading after the scan completed
        number_of_samples_to_read = 1  # self.get_scan_status()[1]  #number of valid samples, will be updated upon first data read

        read_counter = 0

        self.average_stdeviations_x_st_fzp = 0
        self.average_stdeviations_y_st_fzp = 0
        self.average_lamni_angle = 0

        mode, number_of_positions_planned, current_position_in_scan = self.get_scan_status()

        # if not (mode==2 or mode==3):
        #    error
        self.get_device_manager().connector.set(
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

        self.get_device_manager().connector.set(
            MessageEndpoints.device_status("rt_scan"),
            messages.DeviceStatusMessage(
                device="rt_scan", status=0, metadata=self.readout_metadata
            ).dumps(),
        )

        logger.info(
            "Flomni statistics: Average of all standard deviations: x"
            f" {self.average_stdeviations_x_st_fzp/number_of_samples_to_read}, y"
            f" {self.average_stdeviations_y_st_fzp/number_of_samples_to_read}."
        )

    def publish_device_data(self, signals, pointID):
        self.get_device_manager().connector.set_and_publish(
            MessageEndpoints.device_read("rt_flomni"),
            messages.DeviceMessage(
                signals=signals, metadata={"pointID": pointID, **self.readout_metadata}
            ).dumps(),
        )

    def start_readout(self):
        readout = threading.Thread(target=self.read_positions_from_sampler)
        readout.start()

    def kickoff(self, metadata):
        self.readout_metadata = metadata
        while not self._min_scan_buffer_reached:
            time.sleep(0.001)
        self.start_scan()
        time.sleep(0.1)
        self.start_readout()


class RtFlomniReadbackSignal(RtReadbackSignal):
    @retry_once
    @threadlocked
    def _socket_get(self) -> float:
        """Get command for the readback signal

        Returns:
        float: Readback value after adjusting for sign and motor resolution.
        """
        time.sleep(0.1)
        return_table = (self.controller.socket_put_and_receive(f"pr")).split(",")

        current_pos = float(return_table[self.parent.axis_Id_numeric])

        current_pos *= self.parent.sign
        self.parent.user_setpoint.setpoint = current_pos
        return current_pos


class RtFlomniSetpointSignal(RtSetpointSignal):
    setpoint = 0

    @retry_once
    @threadlocked
    def _socket_set(self, val: float) -> None:
        """Set a new target value / setpoint value. Before submission, the target value is adjusted for the axis' sign.
        Furthermore, it is ensured that all axes are referenced before a new setpoint is submitted.

        Args:
            val (float): Target value / setpoint value

        Raises:
            RtError: Raised if interferometer feedback is disabled.

        """
        if not self.parent.controller.feedback_is_running():
            print(
                "The interferometer feedback is not running. Either it is turned off or and"
                " interferometer error occured."
            )
            raise RtError(
                "The interferometer feedback is not running. Either it is turned off or and"
                " interferometer error occured."
            )
        self.set_with_feedback_disabled(val)

    def set_with_feedback_disabled(self, val):
        target_val = val * self.parent.sign
        self.setpoint = target_val
        self.controller.socket_put(f"pa{self.parent.axis_Id_numeric},{target_val:.4f}")


class RtFlomniFeedbackRunning(RtSignalRO):
    @threadlocked
    def _socket_get(self):
        return int(self.parent.controller.feedback_is_running())


class RtFlomniMotor(Device, PositionerBase):
    USER_ACCESS = ["controller"]
    readback = Cpt(RtFlomniReadbackSignal, signal_name="readback", kind="hinted")
    user_setpoint = Cpt(RtFlomniSetpointSignal, signal_name="setpoint")

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
        host="mpc2844.psi.ch",
        port=2222,
        sign=1,
        socket_cls=SocketIO,
        device_manager=None,
        limits=None,
        **kwargs,
    ):
        self.axis_Id = axis_Id
        self.sign = sign
        self.controller = RtFlomniController(
            socket_cls=socket_cls, socket_host=host, socket_port=port
        )
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
            while not self.controller.slew_rate_limiters_on_target():
                print("motor is moving")
                val = self.readback.read()
                self._run_subs(sub_type=self.SUB_READBACK, value=val, timestamp=time.time())
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
    rtcontroller = RtFlomniController(
        socket_cls=SocketIO, socket_host="mpc2844.psi.ch", socket_port=2222
    )
    rtcontroller.on()
    rtcontroller.laser_tracker_on()
