import functools
import threading
import time
import numpy as np
from typing import List
from ophyd import PositionerBase, Device, Component as Cpt
from prettytable import PrettyTable
from ophyd_devices.utils.controller import Controller
from ophyd_devices.utils.socket import (
    SocketIO,
    raise_if_disconnected,
    SocketSignal,
)
import logging
from ophyd.utils import ReadOnlyError
from ophyd.status import wait as status_wait

logger = logging.getLogger("rtlamni")

def threadlocked(fcn):
    """Ensure that thread acquires and releases the lock."""

    @functools.wraps(fcn)
    def wrapper(self, *args, **kwargs):
        with self._lock:
            return fcn(self, *args, **kwargs)

    return wrapper

class RtLamniCommunicationError(Exception):
    pass


class RtLamniError(Exception):
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
        "feedback_enable_without_reset"
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
            #discuss - after disconnect takes a while for the server to be ready again
            welcome_message = self.sock.receive()
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
        self.sock.put(f"{val}\n".encode())

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
        #this checks that axis is on target
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

    def set_rotation_angle(self, val:float):
        self.socket_put(f"a{(val-300+30.538)/180*np.pi}")

    def stop_all_axes(self) -> str:
        return 0 #self.socket_put_and_receive(f"XQ#STOP,1")

    def feedback_disable(self):
        self.socket_put("J0")
        logger.info("LamNI Feedback disabled.")
        #motor_par("lsamx","disable",0)
        #motor_par("lsamy","disable",0)
        #motor_par("loptx","disable",0)
        #motor_par("lopty","disable",0)
        #motor_par("loptz","disable",0)

    def feedback_enable_without_reset(self):
        #read current interferometer position
        return_table = (self.socket_put_and_receive(f"J4")).split(",")
        x_curr=float(return_table[2])
        y_curr=float(return_table[1])
        #set these as closed loop target position
        self.socket_put(f"pa0,{x_curr:.4f}")
        self.socket_put(f"pa1,{y_curr:.4f}")
        self.socket_put("J5")
        logger.info("LamNI Feedback enabled (without reset).")
        #motor_par("lsamx","disable",1)
        #motor_par("lsamy","disable",1)
        #motor_par("loptx","disable",1)
        #motor_par("lopty","disable",1)
        #motor_par("loptz","disable",1)

    def feedback_disable_and_even_reset_lamni_angle_interferometer(self):
        self.socket_put("J6")
        logger.info("LamNI Feedback disabled including the angular interferometer.")
        #motor_par("lsamx","disable",0)
        #motor_par("lsamy","disable",0)
        #motor_par("loptx","disable",0)
        #motor_par("lopty","disable",0)
        #motor_par("loptz","disable",0)

    def clear_trajectory_generator(self):
        self.socket_put("sc")
        logger.info("LamNI scan stopped and deleted, moving to start position")

    def feedback_status_angle_lamni(self) -> bool:
        return_table = (self.socket_put_and_receive(f"J7")).split(",")
        logger.debug(f"LamNI angle interferomter status {bool(return_table[0])}, position {float(return_table[1])}, signal {float(return_table[2])}")
        return bool(return_table[0])

    def feedback_enable_with_reset(self):
        if not self.feedback_status_angle_lamni(self):
            self.rt_feedback_disable_and_even_reset_lamni_angle_interferometer(self)
            logger.info(f"LamNI resetting interferometer inclusive angular interferomter.")
        else:
            self.feedback_disable(self)
            logger.info(f"LamNI resetting interferomter except angular interferometer which is already running.")

        #set these as closed loop target position
        #discuss: after this the current target position in lamni is 0, while the latest target position in ophyd might be different
        #the same is after moving to a different scan region with the coarse stages. maybe issue a move command later to have them match?
        #that is only possible with runnign feedback. or change user setpoint in a different way?
        self.socket_put(f"pa0,0")
        self.socket_put(f"pa1,0")
        self.socket_put(f"pa2,0") #we set all three outputs of the traj. gen. although in LamNI case only 0,1 are used
        self.clear_trajectory_generator(self)

        ####
        #here umv lsamrot 0
        ####
        #!lgalil_is_air_off_and_orchestra_enabled:
        #Cannot enable feedback. The small rotation air is on and/or orchestra disabled by the motor controller.
        #exit with failure

        time.sleep(0.03)
        #global _lsamx_center
        #global _lsamy_center
        #umv lsamx _lsamx_center
        #umv lsamy _lsamy_center

        self.socket_put("J1")
        #set_lm rtx -50 50
        #set_lm rty -50 50
        _waitforfeedbackctr=0

        #this is implemented as class and not function. why? RtLamniFeedbackRunning

#        while self.RtLamniFeedbackRunning _rt_status_feedback(self) == 1 && _waitforfeedbackctr<100)
# {
#   sleep(0.01)
#   _waitforfeedbackctr++
#   #p _waitforfeedbackctr
# }
# motor_par("lsamx","disable",1)
# motor_par("lsamy","disable",1)
# motor_par("loptx","disable",1)
# motor_par("lopty","disable",1)
# motor_par("loptz","disable",1)
# rt_feedback_status

#}

global ptychography_alignment_done
ptychography_alignment_done = 0



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
    def _socket_set(self, val: float) -> None:
        """Set a new target value / setpoint value. Before submission, the target value is adjusted for the axis' sign.
        Furthermore, it is ensured that all axes are referenced before a new setpoint is submitted.

        Args:
            val (float): Target value / setpoint value

        Raises:
            RtLamniError: Raised if interferometer feedback is disabled.

        """
        target_val = val * self.parent.sign
        self.setpoint = target_val
        interferometer_feedback_not_running = int((self.controller.socket_put_and_receive("J2")).split(",")[0])
        if interferometer_feedback_not_running == 0:
            self.controller.socket_put(f"pa{self.parent.axis_Id_numeric},{target_val:.4f}")
        else:
           raise RtLamniError("The interferometer feedback is not running. Either it is turned off or and interferometer error occured.")


class RtLamniMotorIsMoving(RtLamniSignalRO):
    def _socket_get(self):
        return self.controller.is_axis_moving(self.parent.axis_Id_numeric)

    def get(self):
        val = super().get()
        if val is not None:
            self._run_subs(sub_type=self.SUB_VALUE,
                value=val,
                timestamp=time.time(),
            )
        return val


class RtLamniFeedbackRunning(RtLamniSignalRO):
    def _socket_get(self):
        if int((self.controller.socket_put_and_receive("J2")).split(",")[0]) == 0:
            return 1
        else:
	        return 0

class RtLamniMotor(Device, PositionerBase):
    USER_ACCESS = [
        "controller"
    ]
    readback = Cpt(
        RtLamniReadbackSignal,
        signal_name="readback",
        kind="hinted",
    )
    user_setpoint = Cpt(RtLamniSetpointSignal, signal_name="setpoint")
   
    motor_is_moving = Cpt(
        RtLamniMotorIsMoving, signal_name="motor_is_moving", kind="normal"
    )

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
        **kwargs,
    ):
        self.axis_Id = axis_Id
        self.sign = sign
        self.controller = RtLamniController(socket=socket_cls(host=host, port=port))
        self.controller.set_axis(axis=self, axis_nr=self.axis_Id_numeric)
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
        timeout = kwargs.pop("timeout", 4)
        status = super().move(position, timeout=timeout, **kwargs)
        self.user_setpoint.put(position, wait=False)

        def move_and_finish():
            while self.motor_is_moving.get():
                print("motor is moving")
                val = self.readback.read()
                self._run_subs(sub_type=self.SUB_READBACK,
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

    @property
    def egu(self):
        """The engineering units (EGU) for positions"""
        return "um"

	# how is this used later?

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

        rtx = RtLamniMotor(
            "A", name="rtx", host="mpc2680.psi.ch", port=3333, socket_cls=SocketMock
        )
        rty = RtLamniMotor(
            "B", name="rty", host="mpc2680.psi.ch", port=3333, socket_cls=SocketMock
        )
        rtx.stage()
        # rty.stage()

