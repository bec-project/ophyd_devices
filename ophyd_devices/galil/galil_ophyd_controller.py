import threading
import time
from typing import List

from ophyd import Component as Cpt
from ophyd import Device, PositionerBase, Signal
from ophyd.status import wait as status_wait
from ophyd.utils import ReadOnlyError
from ophyd_devices.utils.controller import Controller
from ophyd_devices.utils.socket import SocketIO, SocketSignal, raise_if_disconnected
from prettytable import PrettyTable
from bec_utils import bec_logger

logger = bec_logger.logger


class GalilCommunicationError(Exception):
    pass


class GalilError(Exception):
    pass


class GalilController(Controller):
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

    def socket_put(self, val: str) -> None:
        self.sock.put(f"{val}\r".encode())

    def socket_get(self) -> str:
        return self.sock.receive().decode()

    def socket_put_and_receive(self, val: str, remove_trailing_chars=True) -> str:
        self.socket_put(val)
        if remove_trailing_chars:
            return self._remove_trailing_characters(self.sock.receive().decode())
        return self.socket_get()

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

    def is_axis_moving(self, axis_Id) -> bool:
        return bool(float(self.socket_put_and_receive(f"MG _BG{axis_Id}")))

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

    def describe(self) -> None:
        t = PrettyTable()
        t.title = f"{self.__class__.__name__} on {self.sock.host}:{self.sock.port}"
        t.field_names = [
            "Axis",
            "Name",
            "Connected",
            "Referenced",
            "Motor",
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
                        "NA",
                        "off",
                        "",
                        axis.user_readback.read().get("value"),
                    ]
                )
            else:
                t.add_row([None for t in t.field_names])
        print(t)

        self.show_running_threads()

    def galil_show_all(self) -> None:
        for controller in self._controller_instances.values():
            controller.describe()


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
    def _socket_get(self) -> float:
        """Get command for the readback signal

        Returns:
            float: Readback value after adjusting for sign and motor resolution.
        """

        current_pos = float(self.controller.socket_put_and_receive(f"TD{self.parent.axis_Id}\n"))
        current_pos *= self.parent.sign
        step_mm = self.parent.motor_resolution.get()
        return current_pos / step_mm


class GalilSetpointSignal(GalilSignalBase):
    setpoint = 0

    def _socket_get(self) -> float:
        """Get command for receiving the setpoint / target value.
        The value is not pulled from the controller but instead just the last setpoint used.

        Returns:
            float: setpoint / target value
        """
        return self.setpoint

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
        axes_referenced = float(self.controller.socket_put_and_receive("MG allaxref"))
        if axes_referenced:
            self.controller.socket_put_confirmed(f"naxis={self.parent.axis_Id_numeric}")
            self.controller.socket_put_confirmed(f"ntarget={target_val:.3f}")
            self.controller.socket_put_confirmed("movereq=1")
            self.controller.socket_put_confirmed("XQ#NEWPAR")
        else:
            raise GalilError("Not all axes are referenced.")


class GalilMotorResolution(GalilSignalRO):
    def _socket_get(self):
        return float(
            self.controller.socket_put_and_receive(f"MG stppermm[{self.parent.axis_Id_numeric}]\n")
        )


class GalilMotorIsMoving(GalilSignalRO):
    def _socket_get(self):
        return (
            self.controller.is_axis_moving(self.parent.axis_Id)
            or self.controller.is_thread_active(0)
            or self.controller.is_thread_active(2)
        )


class GalilAxesReferenced(GalilSignalRO):
    def _socket_get(self):
        return self.controller.socket_put_and_receive("MG allaxref")


class GalilControllerSignal(Signal):
    def _socket_get(self):
        return self.controller.socket_put_and_receive("MG allaxref")


class GalilControllerDevice(Device):
    motor_is_moving = Cpt(GalilMotorIsMoving, signal_name="motor_is_moving", kind="omitted")

    SUB_READBACK = "motor_is_moving"
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
        sign=1,
        socket_cls=SocketIO,
        **kwargs,
    ):
        self.axis_Id = axis_Id
        self.sign = sign
        self.controller = GalilController(socket=socket_cls(host=host, port=port))
        self.controller.set_axis(axis=self, axis_nr=0)
        super().__init__(
            prefix,
            name=name,
            kind=kind,
            read_attrs=read_attrs,
            configuration_attrs=configuration_attrs,
            parent=parent,
            **kwargs,
        )
        print(self.prefix)


class GalilMotor(Device, PositionerBase):

    user_readback = Cpt(
        GalilReadbackSignal,
        signal_name="readback",
        kind="hinted",
    )
    user_setpoint = Cpt(GalilSetpointSignal, signal_name="setpoint")
    motor_resolution = Cpt(GalilMotorResolution, signal_name="resolution", kind="config")
    motor_is_moving = Cpt(GalilMotorIsMoving, signal_name="motor_is_moving", kind="omitted")
    all_axes_referenced = Cpt(GalilAxesReferenced, signal_name="all_axes_referenced", kind="config")
    from ophyd_devices.utils.socket import SocketMock

    controller_device = Cpt(
        GalilControllerDevice,
        "C",
        name="controller_device",
        host="mpc2680.psi.ch",
        port=8081,
        socket_cls=SocketMock,
    )

    SUB_READBACK = "user_readback"
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
        sign=1,
        socket_cls=SocketIO,
        **kwargs,
    ):
        self.axis_Id = axis_Id
        self.sign = sign
        self.controller = GalilController(socket=socket_cls(host=host, port=port))
        self.controller.set_axis(axis=self, axis_nr=self.axis_Id_numeric)

        super().__init__(
            prefix,
            name=name,
            kind=kind,
            read_attrs=read_attrs,
            configuration_attrs=configuration_attrs,
            parent=parent,
            **kwargs,
        )
        self.controller.subscribe(
            self._update_connection_state, event_type=self.SUB_CONNECTION_CHANGE
        )
        self._update_connection_state()

    def _update_connection_state(self, **kwargs):
        for walk in self.walk_signals():
            walk.item._metadata["connected"] = self.controller.connected

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

        status = super().move(position, timeout=4, **kwargs)
        self.user_setpoint.put(position, wait=False)

        def move_and_finish():
            while self.motor_is_moving.get():
                self.user_readback.read()
                time.sleep(0.2)
            logger.info("Move finished")
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

    @property
    def egu(self):
        """The engineering units (EGU) for positions"""
        return "mm"

    def stage(self) -> List[object]:
        self.controller.on()
        return super().stage()

    def unstage(self) -> List[object]:
        self.controller.off()
        return super().unstage()

    def stop(self, *, success=False):
        self.controller.stop_all_axes()
        return super().stop(success=success)


if __name__ == "__main__":

    mock = True
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
        controller_device = GalilControllerDevice(
            "C",
            name="controller_device",
            host="mpc2680.psi.ch",
            port=8081,
            socket_cls=SocketMock,
        )
        leyex.stage()
        leyex.controller.galil_show_all()
