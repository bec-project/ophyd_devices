import functools
import threading
import time

import numpy as np
from bec_lib import bec_logger
from ophyd import Component as Cpt, DeviceStatus
from ophyd import Device, PositionerBase, Signal
from ophyd.status import wait as status_wait
from ophyd.utils import LimitError, ReadOnlyError
from ophyd_devices.utils.controller import Controller, threadlocked
from ophyd_devices.utils.socket import SocketIO, SocketSignal, raise_if_disconnected
from prettytable import PrettyTable

logger = bec_logger.logger


class GalilCommunicationError(Exception):
    pass


class GalilError(Exception):
    pass


class BECConfigError(Exception):
    pass


def retry_once(fcn):
    """Decorator to rerun a function in case a Galil communication error was raised. This may happen if the buffer was not empty."""

    @functools.wraps(fcn)
    def wrapper(self, *args, **kwargs):
        try:
            val = fcn(self, *args, **kwargs)
        except (GalilCommunicationError, GalilError):
            val = fcn(self, *args, **kwargs)
        return val

    return wrapper


class GalilController(Controller):
    USER_ACCESS = [
        "describe",
        "show_running_threads",
        "galil_show_all",
        "socket_put_and_receive",
        "socket_put_confirmed",
        "sgalil_reference",
        "fly_grid_scan",
        "read_encoder_position",
    ]

    def __init__(
        self,
        *,
        name="GalilController",
        kind=None,
        parent=None,
        socket=None,
        attr_name="",
        labels=None,
    ):
        if not hasattr(self, "_initialized") or not self._initialized:
            self._galil_axis_per_controller = 8
            self._axis = [None for axis_num in range(self._galil_axis_per_controller)]
            super().__init__(
                name=name,
                socket=socket,
                attr_name=attr_name,
                parent=parent,
                labels=labels,
                kind=kind,
            )

    def on(self, controller_num=0) -> None:
        """Open a new socket connection to the controller"""
        if not self.connected:
            self.sock.open()
            self.connected = True
        else:
            logger.info("The connection has already been established.")
            # warnings.warn(f"The connection has already been established.", stacklevel=2)

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
        time.sleep(0.01)
        self.sock.put(f"{val}\r".encode())

    @threadlocked
    def socket_get(self) -> str:
        time.sleep(0.01)
        return self.sock.receive().decode()

    @retry_once
    @threadlocked
    def socket_put_and_receive(self, val: str, remove_trailing_chars=True) -> str:
        self.socket_put(val)
        if remove_trailing_chars:
            return self._remove_trailing_characters(self.sock.receive().decode())
        return self.socket_get()

    @retry_once
    def socket_put_confirmed(self, val: str) -> None:
        """Send message to controller and ensure that it is received by checking that the socket receives a colon.

        Args:
            val (str): Message that should be sent to the socket

        Raises:
            GalilCommunicationError: Raised if the return value is not a colon.

        """
        return_val = self.socket_put_and_receive(val)
        if return_val != ":":
            raise GalilCommunicationError(
                f"Expected return value of ':' but instead received {return_val}"
            )

    def is_axis_moving(self, axis_Id, axis_Id_numeric) -> bool:
        is_moving = bool(float(self.socket_put_and_receive(f"MG_BG{axis_Id}")) != 0)
        # backlash_is_active = bool(float(self.socket_put_and_receive(f"MGbcklact[axis]")) != 0)
        return bool(is_moving)  # bool(is_moving or backlash_is_active)

    def is_thread_active(self, thread_id: int) -> bool:
        val = float(self.socket_put_and_receive(f"MG_XQ{thread_id}"))
        if val == -1:
            return False
        return True

    def _remove_trailing_characters(self, var) -> str:
        if len(var) > 1:
            return var.split("\r\n")[0]
        return var

    def stop_all_axes(self) -> str:
        # return self.socket_put_and_receive(f"XQ#STOP,1")
        # Command stops all threads and motors!
        self.socket_put_and_receive(f"CB8")
        return self.socket_put_and_receive(f"ST")

    def axis_is_referenced(self) -> bool:
        return bool(float(self.socket_put_and_receive(f"MG allaxref").strip()))

    def show_running_threads(self) -> None:
        t = PrettyTable()
        t.title = f"Threads on {self.sock.host}:{self.sock.port}"
        t.field_names = [str(ax) for ax in range(self._galil_axis_per_controller)]
        t.add_row(
            [
                "active" if self.is_thread_active(t) else "inactive"
                for t in range(self._galil_axis_per_controller)
            ]
        )
        print(t)

    def is_motor_on(self, axis_Id) -> bool:
        return not bool(float(self.socket_put_and_receive(f"MG _MO{axis_Id}").strip()))

    def get_motor_limit_switch(self, axis_Id) -> list:
        # SGalil specific
        if axis_Id == "C":
            ret = self.socket_put_and_receive(f"MG _LF{axis_Id}, _LR{axis_Id}")
            high, low = ret.strip().split(" ")
        elif axis_Id == "E":
            ret = self.socket_put_and_receive(f"MG _LF{'F'}, _LR{'F'}")
            high, low = ret.strip().split(" ")
        return [not bool(float(low)), not bool(float(high))]

    def describe(self) -> None:
        t = PrettyTable()
        t.title = f"{self.__class__.__name__} on {self.sock.host}:{self.sock.port}"
        t.field_names = [
            "Axis",
            "Name",
            "Connected",
            "Referenced",
            "Motor On",
            "Limits",
            "Position",
        ]
        for ax in range(self._galil_axis_per_controller):
            axis = self._axis[ax]
            if axis is not None:
                t.add_row(
                    [
                        f"{axis.axis_Id_numeric}/{axis.axis_Id}",
                        axis.name,
                        axis.connected,
                        self.axis_is_referenced(),
                        self.is_motor_on(axis.axis_Id),
                        self.get_motor_limit_switch(axis.axis_Id),
                        axis.readback.read().get(axis.name).get("value"),
                    ]
                )
            else:
                t.add_row([None for t in t.field_names])
        print(t)

        self.show_running_threads()

    def galil_show_all(self) -> None:
        for controller in self._controller_instances.values():
            if isinstance(controller, GalilController):
                controller.describe()

    def sgalil_reference(self) -> None:
        """Reference all axes of the controller"""
        if self.axis_is_referenced():
            print("All axes are already referenced.\n")
            return
        # Make sure no axes are moving, is this necessary?
        self.stop_all_axes()
        self.socket_put_and_receive(f"XQ#FINDREF")
        print("Referencing. Please wait, timeout after 100s...\n")

        timeout = time.time() + 100
        while not self.axis_is_referenced():
            if time.time() > timeout:
                print("Abort reference sequence, timeout reached\n")
                break
            time.sleep(0.5)

    # @threadlocked
    def fly_grid_scan(
        self,
        status: DeviceStatus,
        start_y: float,
        end_y: float,
        interval_y: int,
        start_x: float,
        end_x: float,
        interval_x: int,
        exp_time: float,
        readout_time: float,
        **kwargs,
    ) -> tuple:
        """_summary_

        Args:
            start_y (float): start position of y axis (fast axis)
            end_y (float): end position of y axis (fast axis)
            interval_y (int): number of points in y axis
            start_x (float): start position of x axis (slow axis)
            end_x (float): end position of x axis (slow axis)
            interval_x (int): number of points in x axis
            exp_time (float): exposure time in seconds
            readout_time (float): readout time in seconds, minimum of .5e-3s (0.5ms)

        Raises:

            LimitError: Raised if any position of motion is outside of the limits
            LimitError: Raised if the speed is above 2mm/s or below 0.02mm/s

        """
        #
        if not self.axis_is_referenced():
            raise GalilError("Axis are not referenced")
        sign_y = self._axis[ord("c") - 97].sign
        sign_x = self._axis[ord("e") - 97].sign
        # Check limits
        # TODO check sign of stage, or not necessary
        check_values = [start_y, end_y, start_x, end_x]
        for val in check_values:
            self.check_value(val)

        start_x *= sign_x
        end_x *= sign_x
        start_y *= sign_y
        end_y *= sign_y

        speed = np.abs(end_y - start_y) / (
            (interval_y) * exp_time + (interval_y - 1) * readout_time
        )
        if speed > 2.00 or speed < 0.02:
            raise LimitError(
                f"Speed of {speed:.03f}mm/s is outside of acceptable range of 0.02 to 2 mm/s"
            )

        gridmax = int(interval_x - 1)
        step_grid = (end_x - start_x) / interval_x
        n_samples = int(interval_y * interval_x)

        # Hard coded to maximum offset of 0.1mm to avoid long motions.
        self.socket_put_and_receive(f"off={(0):f}")
        self.socket_put_and_receive(f"a_start={start_y:.04f};a_end={end_y:.04f};speed={speed:.04f}")
        self.socket_put_and_receive(
            f"b_start={start_x:.04f};gridmax={gridmax:d};b_step={step_grid:.04f}"
        )
        self.socket_put_and_receive(f"nums={n_samples}")
        self.socket_put_and_receive("XQ#SAMPLE")
        # sleep 50ms to avoid controller running into
        time.sleep(0.1)
        self.socket_put_and_receive("XQ#SCANG")
        # self._block_while_active(3)
        # time.sleep(0.1)
        threading.Thread(target=self._block_while_active, args=(3, status), daemon=True).start()
        # self._while_in_motion(3, n_samples)

    def _block_while_active(self, thread_id: int, status) -> None:
        while self.is_thread_active(thread_id):
            time.sleep(1)
        time.sleep(1)
        while self.is_thread_active(thread_id):
            time.sleep(1)
        status.set_finished()

    # TODO this is for reading out positions, readout is limited by stage triggering
    def _while_in_motion(self, thread_id: int, n_samples: int) -> tuple:
        last_readout = 0
        val_axis2 = []  # y axis
        val_axis4 = []  # x axis
        while self.is_thread_active(thread_id):
            posct = int(self.socket_put_and_receive(f"MGposct").strip().split(".")[0])
            logger.info(f"SGalil is scanning - latest enconder position {posct+1} from {n_samples}")
            time.sleep(1)
            if posct > last_readout:
                positions = self.read_encoder_position(last_readout, posct)
                val_axis4.extend(positions[0])
                val_axis2.extend(positions[1])
                last_readout = posct + 1
            logger.info(len(val_axis2))
            time.sleep(1)
        # Readout of last positions after scan finished
        posct = int(self.socket_put_and_receive(f"MGposct").strip().split(".")[0])
        logger.info(f"SGalil is scanning - latest enconder position {posct} from {n_samples}")
        if posct > last_readout:
            positions = self.read_encoder_position(last_readout, posct)
            val_axis4.extend(positions[0])
            val_axis2.extend(positions[1])

        return val_axis4, val_axis2

    def read_encoder_position(self, fromval: int, toval: int) -> tuple:
        val_axis2 = []  # y axis
        val_axis4 = []  # x axis
        for ii in range(fromval, toval + 1):
            rts = self.socket_put_and_receive(f"MGaposavg[{ii%2000}]*10,cposavg[{ii%2000}]*10")
            if rts == ":":
                val_axis4.append(rts)
                val_axis2.append(rts)
                continue

            val_axis4.append(float(rts.strip().split(" ")[0]) / 100000)
            val_axis2.append(float(rts.strip().split(" ")[1]) / 100000)
        return val_axis4, val_axis2


class GalilSignalBase(SocketSignal):
    def __init__(self, signal_name, **kwargs):
        self.signal_name = signal_name
        super().__init__(**kwargs)
        self.controller = self.parent.controller
        self.sock = self.parent.controller.sock


class GalilSignalRO(GalilSignalBase):
    def __init__(self, signal_name, **kwargs):
        super().__init__(signal_name, **kwargs)
        self._metadata["write_access"] = False

    def _socket_set(self, val):
        raise ReadOnlyError("Read-only signals cannot be set")


class GalilReadbackSignal(GalilSignalRO):
    @retry_once
    @threadlocked
    def _socket_get(self) -> float:
        """Get command for the readback signal

        Returns:
            float: Readback value after adjusting for sign and motor resolution.
        """
        if self.parent.axis_Id_numeric == 2:
            current_pos = float(
                self.controller.socket_put_and_receive(f"MG _TP{self.parent.axis_Id}/mm")
            )
        elif self.parent.axis_Id_numeric == 4:
            # hardware controller readback from axis 4 is on axis 0, A instead of E
            current_pos = float(self.controller.socket_put_and_receive(f"MG _TP{'A'}/mm"))
        current_pos *= self.parent.sign
        return current_pos

    def read(self):
        self._metadata["timestamp"] = time.time()
        val = super().read()
        return val


class GalilSetpointSignal(GalilSignalBase):
    setpoint = 0

    def _socket_get(self) -> float:
        """Get command for receiving the setpoint / target value.
        The value is not pulled from the controller but instead just the last setpoint used.

        Returns:
            float: setpoint / target value
        """
        return self.setpoint * self.parent.sign

    @retry_once
    @threadlocked
    def _socket_set(self, val: float) -> None:
        """Set a new target value / setpoint value. Before submission, the target value is adjusted for the axis' sign.
        Furthermore, it is ensured that all axes are referenced before a new setpoint is submitted.

        Args:
            val (float): Target value / setpoint value

        Raises:
            GalilError: Raised if not all axes are referenced.

        """
        target_val = val * self.parent.sign
        self.setpoint = target_val
        axes_referenced = self.controller.axis_is_referenced()
        if not axes_referenced:
            raise GalilError(
                "Not all axes are referenced. Please use controller.sgalil_reference(). BE AWARE that axes start moving, potentially beyond limits, make sure full range of motion is safe"
            )
        while self.controller.is_thread_active(0):
            time.sleep(0.1)

        if self.parent.axis_Id_numeric == 2:
            self.controller.socket_put_confirmed(f"PA{self.parent.axis_Id}={target_val:.4f}*mm")
            self.controller.socket_put_and_receive(f"BG{self.parent.axis_Id}")
        elif self.parent.axis_Id_numeric == 4:
            self.controller.socket_put_confirmed(f"targ{self.parent.axis_Id}={target_val:.4f}")
            self.controller.socket_put_and_receive(f"XQ#POSE,{self.parent.axis_Id_numeric}")
        while self.controller.is_thread_active(0):
            time.sleep(0.005)


class GalilMotorIsMoving(GalilSignalRO):
    @threadlocked
    def _socket_get(self):
        if self.parent.axis_Id_numeric == 2:
            ret = self.controller.is_axis_moving(self.parent.axis_Id, self.parent.axis_Id_numeric)
            return ret
        if self.parent.axis_Id_numeric == 4:
            # Motion signal from axis 4 is mapped to axis 5
            ret = self.controller.is_axis_moving("F", 5)
            return ret or self.controller.is_thread_active(4)

    def get(self):
        val = super().get()
        if val is not None:
            self._run_subs(
                sub_type=self.SUB_VALUE,
                value=val,
                timestamp=time.time(),
            )
        return val


class GalilAxesReferenced(GalilSignalRO):
    @threadlocked
    def _socket_get(self):
        return self.controller.socket_put_and_receive("MG allaxref")


class SGalilMotor(Device, PositionerBase):
    """ "SGalil Motors at cSAXS have a
    DC motor (y axis - vertical) - implemented as C
    and a step motor (x-axis horizontal) - implemented as E
    that require different communication for control
    """

    USER_ACCESS = ["controller"]
    readback = Cpt(
        GalilReadbackSignal,
        signal_name="readback",
        kind="hinted",
    )
    user_setpoint = Cpt(GalilSetpointSignal, signal_name="setpoint")
    motor_is_moving = Cpt(GalilMotorIsMoving, signal_name="motor_is_moving", kind="normal")
    all_axes_referenced = Cpt(GalilAxesReferenced, signal_name="all_axes_referenced", kind="config")
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
        host="129.129.122.26",
        port=23,
        limits=None,
        sign=1,
        socket_cls=SocketIO,
        device_manager=None,
        **kwargs,
    ):
        self.axis_Id = axis_Id
        self.sign = sign
        self.controller = GalilController(socket=socket_cls(host=host, port=port))
        self.controller.set_axis(axis=self, axis_nr=self.axis_Id_numeric)
        self.tolerance = kwargs.pop("tolerance", 0.5)
        self.device_mapping = kwargs.pop("device_mapping", {})
        self.device_manager = device_manager

        if len(self.device_mapping) > 0 and self.device_manager is None:
            raise BECConfigError(
                "device_mapping has been specified but the device_manager cannot be accessed."
            )
        self.rt = self.device_mapping.get("rt")

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
                logger.info("motor is moving")
                val = self.readback.read()
                self._run_subs(
                    sub_type=self.SUB_READBACK,
                    value=val,
                    timestamp=time.time(),
                )
                time.sleep(1.5)
            val = self.readback.read()
            success = np.isclose(
                val[self.name]["value"],
                position,
                atol=self.tolerance,
            )

            if not success:
                print(" stop")
            self._done_moving(success=success)
            logger.info("Move finished")

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
            if val not in ["C", "E"]:
                raise ValueError(
                    f"axis_id {val} is currently not supported, please use either 'C' or 'E'."
                )
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
            if val not in [2, 4]:
                raise ValueError(f"Numeric value {val} is not supported, it must be either 2 or 4.")
            self._axis_Id_alpha = val
            self._axis_Id_numeric = (chr(val + 97)).capitalize()
        else:
            raise TypeError(f"Expected value of type int but received {type(val)}.")

    @property
    def egu(self):
        """The engineering units (EGU) for positions"""
        return "mm"

    def stop(self, *, success=False):
        self.controller.stop_all_axes()
        # last_speed = self.controller.socket_put_and_receive("MG")
        rtr = self.controller.socket_put_and_receive(f"SPC={2*10000}")
        logger.info(f"{rtr}")
        # logger.info(f'Motor stopped, restored speed for samy from {last_speed}mm/s to 2mm/s')
        return super().stop(success=success)

    def kickoff(self) -> DeviceStatus:
        status = DeviceStatus(self)
        self.controller.fly_grid_scan(
            status,
            self._kickoff_params.get("start_y"),
            self._kickoff_params.get("end_y"),
            self._kickoff_params.get("interval_y"),
            self._kickoff_params.get("start_x"),
            self._kickoff_params.get("end_x"),
            self._kickoff_params.get("interval_x"),
            self._kickoff_params.get("exp_time"),
            self._kickoff_params.get("readout_time"),
        )
        return status

    def configure(
        self,
        parameter: dict,
        **kwargs,
    ) -> None:
        self._kickoff_params = parameter


if __name__ == "__main__":
    mock = False
    if not mock:
        samy = SGalilMotor("C", name="samy", host="129.129.122.26", port=23, sign=-1)
        samx = SGalilMotor("E", name="samx", host="129.129.122.26", port=23, sign=-1)
    else:
        from ophyd_devices.utils.socket import SocketMock

        samx = SGalilMotor("E", name="samx", host="129.129.122.26", port=23, socket_cls=SocketMock)
        samy = SGalilMotor("C", name="samy", host="129.129.122.26", port=23, socket_cls=SocketMock)

        samx.controller.galil_show_all()
