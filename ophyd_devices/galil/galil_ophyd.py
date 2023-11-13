import functools
import threading
import time
from typing import List

import numpy as np
from bec_lib import bec_logger
from ophyd import Component as Cpt
from ophyd import Device, PositionerBase, Signal
from ophyd.status import wait as status_wait
from ophyd.utils import LimitError, ReadOnlyError
from prettytable import PrettyTable

from ophyd_devices.utils.controller import Controller, threadlocked
from ophyd_devices.utils.socket import SocketIO, SocketSignal, raise_if_disconnected

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
    _axes_per_controller = 8
    USER_ACCESS = [
        "describe",
        "show_running_threads",
        "galil_show_all",
        "socket_put_and_receive",
        "socket_put_confirmed",
        "lgalil_is_air_off_and_orchestra_enabled",
    ]

    @threadlocked
    def socket_put(self, val: str) -> None:
        self.sock.put(f"{val}\r".encode())

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
        if axis_Id is None and axis_Id_numeric is not None:
            axis_Id = self.axis_Id_numeric_to_alpha(axis_Id_numeric)
        is_moving = bool(float(self.socket_put_and_receive(f"MG_BG{axis_Id}")) != 0)
        backlash_is_active = bool(float(self.socket_put_and_receive(f"MGbcklact[axis]")) != 0)
        return bool(
            is_moving or backlash_is_active or self.is_thread_active(0) or self.is_thread_active(2)
        )

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
        return self.socket_put_and_receive(f"XQ#STOP,1")

    def lgalil_is_air_off_and_orchestra_enabled(self) -> bool:
        # TODO: move this to the LamNI-specific controller
        rt_not_blocked_by_galil = bool(self.socket_put_and_receive(f"MG@OUT[9]"))
        air_off = bool(self.socket_put_and_receive(f"MG@OUT[13]"))
        return rt_not_blocked_by_galil and air_off

    def axis_is_referenced(self, axis_Id_numeric) -> bool:
        return bool(float(self.socket_put_and_receive(f"MG axisref[{axis_Id_numeric}]").strip()))

    def all_axes_referenced(self) -> bool:
        """
        Check if all axes are referenced.
        """
        return bool(float(self.socket_put_and_receive("MG allaxref").strip()))

    def drive_axis_to_limit(self, axis_Id_numeric: int, direction: str) -> None:
        """
        Drive an axis to the limit in a specified direction.

        Args:
            axis_Id_numeric (int): Axis number
            direction (str): Direction in which the axis should be driven to the limit. Either 'forward' or 'reverse'.
        """
        if direction == "forward":
            direction_flag = 1
        elif direction == "reverse":
            direction_flag = -1
        else:
            raise ValueError(f"Invalid direction {direction}")

        self.socket_put_confirmed(f"naxis={axis_Id_numeric}")
        self.socket_put_confirmed(f"ndir={direction_flag}")
        self.socket_put_confirmed("XQ#NEWPAR")
        self.socket_put_confirmed("XQ#FES")
        time.sleep(0.1)
        while self.is_axis_moving(None, axis_Id_numeric):
            time.sleep(0.1)

        axis_Id = self.axis_Id_numeric_to_alpha(axis_Id_numeric)
        # check if we actually hit the limit
        if direction == "forward":
            limit = self.get_motor_limit_switch(axis_Id)[1]
        elif direction == "reverse":
            limit = self.get_motor_limit_switch(axis_Id)[0]

        if not limit:
            raise GalilError(f"Failed to drive axis {axis_Id}/{axis_Id_numeric} to limit.")

    def find_reference(self, axis_Id_numeric: int) -> None:
        """
        Find the reference of an axis.

        Args:
            axis_Id_numeric (int): Axis number
        """
        self.socket_put_confirmed(f"naxis={axis_Id_numeric}")
        self.socket_put_and_receive("XQ#NEWPAR")
        self.socket_put_confirmed("XQ#FRM")
        time.sleep(0.1)
        while self.is_axis_moving(None, axis_Id_numeric):
            time.sleep(0.1)

        if not self.axis_is_referenced(axis_Id_numeric):
            raise GalilError(f"Failed to find reference of axis {axis_Id_numeric}.")

        logger.info(f"Successfully found reference of axis {axis_Id_numeric}.")

    def show_running_threads(self) -> None:
        t = PrettyTable()
        t.title = f"Threads on {self.sock.host}:{self.sock.port}"
        t.field_names = [str(ax) for ax in range(self._axes_per_controller)]
        t.add_row(
            [
                "active" if self.is_thread_active(t) else "inactive"
                for t in range(self._axes_per_controller)
            ]
        )
        print(t)

    def is_motor_on(self, axis_Id) -> bool:
        return not bool(float(self.socket_put_and_receive(f"MG _MO{axis_Id}").strip()))

    def get_motor_limit_switch(self, axis_Id) -> list:
        """
        Get the status of the motor limit switches.

        Args:
            axis_Id (str): Axis identifier (e.g. 'A', 'B', 'C', ...)

        Returns:
            list: List of two booleans indicating if the low and high limit switch is active, respectively.
        """
        ret = self.socket_put_and_receive(f"MG _LR{axis_Id}, _LF{axis_Id}")
        low, high = ret.strip().split(" ")
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
        for ax in range(self._axes_per_controller):
            axis = self._axis[ax]
            if axis is not None:
                t.add_row(
                    [
                        f"{axis.axis_Id_numeric}/{axis.axis_Id}",
                        axis.name,
                        axis.connected,
                        self.axis_is_referenced(axis.axis_Id_numeric),
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

    @staticmethod
    def axis_Id_to_numeric(axis_Id: str) -> int:
        return ord(axis_Id.lower()) - 97

    @staticmethod
    def axis_Id_numeric_to_alpha(axis_Id_numeric: int) -> str:
        return (chr(axis_Id_numeric + 97)).capitalize()


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

        current_pos = float(self.controller.socket_put_and_receive(f"TD{self.parent.axis_Id}"))
        current_pos *= self.parent.sign
        step_mm = self.parent.motor_resolution.get()
        return current_pos / step_mm

    def read(self):
        self._metadata["timestamp"] = time.time()
        val = super().read()
        if self.parent.axis_Id_numeric == 2:
            try:
                rt = self.parent.device_manager.devices[self.parent.rt]
                if rt.enabled:
                    rt.obj.controller.set_rotation_angle(val[self.parent.name]["value"])
            except KeyError:
                logger.warning("Failed to set RT value during readback.")
        return val


class GalilSetpointSignal(GalilSignalBase):
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
            GalilError: Raised if not all axes are referenced.

        """
        target_val = val * self.parent.sign
        self.setpoint = target_val
        axes_referenced = self.controller.all_axes_referenced()
        if axes_referenced:
            while self.controller.is_thread_active(0):
                time.sleep(0.1)

            if self.parent.axis_Id_numeric == 2:
                angle_status = self.parent.device_manager.devices[
                    self.parent.rt
                ].obj.controller.feedback_status_angle_lamni()

                if angle_status:
                    self.controller.socket_put_confirmed("angintf=1")

            self.controller.socket_put_confirmed(f"naxis={self.parent.axis_Id_numeric}")
            self.controller.socket_put_confirmed(f"ntarget={target_val:.3f}")
            self.controller.socket_put_confirmed("movereq=1")
            self.controller.socket_put_confirmed("XQ#NEWPAR")
            while self.controller.is_thread_active(0):
                time.sleep(0.005)
        else:
            raise GalilError("Not all axes are referenced.")


class GalilMotorResolution(GalilSignalRO):
    @retry_once
    @threadlocked
    def _socket_get(self):
        return float(
            self.controller.socket_put_and_receive(f"MG stppermm[{self.parent.axis_Id_numeric}]")
        )


class GalilMotorIsMoving(GalilSignalRO):
    @threadlocked
    def _socket_get(self):
        return self.controller.is_axis_moving(self.parent.axis_Id, self.parent.axis_Id_numeric)

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
        return self.controller.all_axes_referenced()


class GalilMotor(Device, PositionerBase):
    USER_ACCESS = ["controller"]
    readback = Cpt(
        GalilReadbackSignal,
        signal_name="readback",
        kind="hinted",
    )
    user_setpoint = Cpt(GalilSetpointSignal, signal_name="setpoint")
    motor_resolution = Cpt(GalilMotorResolution, signal_name="resolution", kind="config")
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
        host="mpc2680.psi.ch",
        port=8081,
        limits=None,
        sign=1,
        socket_cls=SocketIO,
        device_manager=None,
        **kwargs,
    ):
        self.controller = GalilController(socket_cls=socket_cls, socket_host=host, socket_port=port)
        self.axis_Id = axis_Id
        self.controller.set_axis(axis=self, axis_nr=self.axis_Id_numeric)
        self.sign = sign
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
                time.sleep(0.1)
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
            self._axis_Id_alpha = val
            self._axis_Id_numeric = self.controller.axis_Id_to_numeric(val)
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
            self._axis_Id_alpha = self.controller.axis_Id_numeric_to_alpha(val)
            self._axis_Id_numeric = val
        else:
            raise TypeError(f"Expected value of type int but received {type(val)}")

    @property
    def egu(self):
        """The engineering units (EGU) for positions"""
        return "mm"

    def stage(self) -> List[object]:
        return super().stage()

    def unstage(self) -> List[object]:
        return super().unstage()

    def stop(self, *, success=False):
        self.controller.stop_all_axes()
        return super().stop(success=success)


if __name__ == "__main__":
    mock = False
    if not mock:
        leyey = GalilMotor("H", name="leyey", host="mpc2680.psi.ch", port=8081, sign=-1)
        leyey.stage()
        status = leyey.move(0, wait=True)
        status = leyey.move(10, wait=True)
        leyey.read()

        leyey.get()
        leyey.describe()

        leyey.unstage()
    else:
        from ophyd_devices.utils.socket import SocketMock

        leyex = GalilMotor(
            "G", name="leyex", host="mpc2680.psi.ch", port=8081, socket_cls=SocketMock
        )
        leyey = GalilMotor(
            "H", name="leyey", host="mpc2680.psi.ch", port=8081, socket_cls=SocketMock
        )
        leyex.stage()
        # leyey.stage()

        leyex.controller.galil_show_all()
