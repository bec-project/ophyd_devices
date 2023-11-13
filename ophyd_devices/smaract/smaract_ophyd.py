import logging
import threading
import time
from typing import List

import numpy as np
from bec_lib import bec_logger
from ophyd import Component as Cpt
from ophyd import Device, PositionerBase, Signal
from ophyd.status import wait as status_wait
from ophyd.utils import LimitError, ReadOnlyError

from ophyd_devices.smaract.smaract_controller import SmaractController
from ophyd_devices.smaract.smaract_errors import SmaractCommunicationError, SmaractError
from ophyd_devices.utils.controller import threadlocked
from ophyd_devices.utils.socket import SocketIO, SocketSignal, raise_if_disconnected

logger = bec_logger.logger


class SmaractSignalBase(SocketSignal):
    def __init__(self, signal_name, **kwargs):
        self.signal_name = signal_name
        super().__init__(**kwargs)
        self.controller = self.parent.controller
        self.sock = self.parent.controller.sock


class SmaractSignalRO(SmaractSignalBase):
    def __init__(self, signal_name, **kwargs):
        super().__init__(signal_name, **kwargs)
        self._metadata["write_access"] = False

    @threadlocked
    def _socket_set(self, val):
        raise ReadOnlyError("Read-only signals cannot be set")


class SmaractReadbackSignal(SmaractSignalRO):
    @threadlocked
    def _socket_get(self):
        return self.controller.get_position(self.parent.axis_Id_numeric) * self.parent.sign


class SmaractSetpointSignal(SmaractSignalBase):
    setpoint = 0

    @threadlocked
    def _socket_get(self):
        return self.setpoint

    @threadlocked
    def _socket_set(self, val):
        target_val = val * self.parent.sign
        self.setpoint = target_val

        if self.controller.axis_is_referenced(self.parent.axis_Id_numeric):
            self.controller.move_axis_to_absolute_position(self.parent.axis_Id_numeric, target_val)
            # parameters are axis_no,pos_mm*1e6, hold_time_sec*1e3
        else:
            raise SmaractError(f"Axis {self.parent.axis_Id_numeric} is not referenced.")


class SmaractMotorIsMoving(SmaractSignalRO):
    @threadlocked
    def _socket_get(self):
        return self.controller.is_axis_moving(self.parent.axis_Id_numeric)


class SmaractAxisReferenced(SmaractSignalRO):
    @threadlocked
    def _socket_get(self):
        return self.parent.controller.axis_is_referenced(self.parent.axis_Id_numeric)


class SmaractAxisLimits(SmaractSignalBase):
    @threadlocked
    def _socket_get(self):
        limits_msg = self.controller.socket_put_and_receive(f"GPL{self.parent.axis_Id_numeric}")
        if limits_msg.startswith(":PL"):
            limits = [
                float(limit)
                for limit in limits_msg.strip(f":PL{self.parent.axis_Id_numeric},").split(",")
            ]
        else:
            raise SmaractCommunicationError("Expected to receive message starting with :PL.")
        return limits

    # def _socket_set(self, val):


class SmaractMotor(Device, PositionerBase):
    USER_ACCESS = ["controller"]
    readback = Cpt(
        SmaractReadbackSignal,
        signal_name="readback",
        kind="hinted",
    )
    user_setpoint = Cpt(SmaractSetpointSignal, signal_name="setpoint")

    # motor_resolution = Cpt(
    #    SmaractMotorResolution, signal_name="resolution", kind="config"
    # )

    motor_is_moving = Cpt(SmaractMotorIsMoving, signal_name="motor_is_moving", kind="normal")
    high_limit_travel = Cpt(Signal, value=0, kind="omitted")
    low_limit_travel = Cpt(Signal, value=0, kind="omitted")
    # all_axes_referenced = Cpt(
    #    SmaractAxesReferenced, signal_name="all_axes_referenced", kind="config"
    # )

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
        port=8085,
        limits=None,
        sign=1,
        socket_cls=SocketIO,
        **kwargs,
    ):
        self.controller = SmaractController(
            socket_cls=socket_cls, socket_host=host, socket_port=port
        )
        self.axis_Id = axis_Id
        self.sign = sign
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
            self._done_moving(success=success)

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
        lsmarA = SmaractMotor("A", name="lsmarA", host="mpc2680.psi.ch", port=8085, sign=1)
        lsmarB = SmaractMotor("B", name="lsmarB", host="mpc2680.psi.ch", port=8085, sign=1)

        lsmarA.stage()
        lsmarB.stage()
        # status = leyey.move(2, wait=True)
        # status = leyey.move(2, wait=True)
        lsmarA.read()
        lsmarB.read()

        lsmarA.get()
        lsmarB.get()
        lsmarA.describe()

        lsmarA.unstage()
        lsmarA.controller.off()
        # status = leyey.move(10, wait=False)
        # print(lSmaract_controller)
    else:
        from ophyd_devices.utils.socket import SocketMock

        lsmarA = SmaractMotor(
            "A",
            name="lsmarA",
            host="mpc2680.psi.ch",
            port=8085,
            sign=1,
            socket_cls=SocketMock,
        )
        lsmarB = SmaractMotor(
            "B",
            name="lsmarB",
            host="mpc2680.psi.ch",
            port=8085,
            sign=1,
            socket_cls=SocketMock,
        )
        lsmarA.stage()
        lsmarB.stage()

        lsmarA.read()
        lsmarB.read()

        lsmarA.get()
        lsmarB.get()
        lsmarA.describe()

        lsmarA.unstage()
        lsmarA.controller.off()
        # status = leyey.move(10, wait=False)
        # print(lSmaract_controller)
