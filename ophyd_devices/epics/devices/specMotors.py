# -*- coding: utf-8 -*-
"""
Created on Wed Oct 13 18:06:15 2021

@author: mohacsi_i

IMPORTANT: Virtual monochromator axes should be implemented already in EPICS!!!
"""

import numpy as np
import time
from math import isclose, tan, atan, sqrt, sin, asin
from ophyd import (
    EpicsSignal,
    EpicsSignalRO,
    EpicsMotor,
    PseudoPositioner,
    PseudoSingle,
    PVPositioner,
    Device, Signal,
    Component,
    DynamicDeviceComponent,
    Kind,
)
from ophyd.pseudopos import pseudo_position_argument, real_position_argument
from ophyd.utils.epics_pvs import data_type


class PmMonoBender(PseudoPositioner):
    """Monochromator bender

    Small wrapper to combine the four monochromator bender motors.
    """

    # Real axes
    ai = Component(EpicsMotor, "TRYA", name="ai")
    bo = Component(EpicsMotor, "TRYB", name="bo")
    co = Component(EpicsMotor, "TRYC", name="co")
    di = Component(EpicsMotor, "TRYD", name="di")

    # Virtual axis
    bend = Component(PseudoSingle, name="bend")

    _real = ["ai", "bo", "co", "di"]

    @pseudo_position_argument
    def forward(self, pseudo_pos):
        delta = pseudo_pos.bend - 0.25 * (
            self.ai.position + self.bo.position + self.co.position + self.di.position
        )
        return self.RealPosition(
            ai=self.ai.position + delta,
            bo=self.bo.position + delta,
            co=self.co.position + delta,
            di=self.di.position + delta,
        )

    @real_position_argument
    def inverse(self, real_pos):
        return self.PseudoPosition(
            bend=0.25 * (real_pos.ai + real_pos.bo + real_pos.co + real_pos.di)
        )


def r2d(radians):
    return radians * 180 / 3.141592


def d2r(degrees):
    return degrees * 3.141592 / 180.0


class PmDetectorRotation(PseudoPositioner):
    """Detector rotation pseudo motor

    Small wrapper to convert detector pusher position to rotation angle.
    """

    _tables_dt_push_dist_mm = 890
    # Real axes
    dtpush = Component(EpicsMotor, "", name="dtpush")

    # Virtual axis
    dtth = Component(PseudoSingle, name="dtth")

    _real = ["dtpush"]

    @pseudo_position_argument
    def forward(self, pseudo_pos):
        return self.RealPosition(
            dtpush=d2r(tan(-3.14 / 180 * pseudo_pos.dtth)) * self._tables_dt_push_dist_mm
        )

    @real_position_argument
    def inverse(self, real_pos):
        return self.PseudoPosition(dtth=r2d(-atan(real_pos.dtpush / self._tables_dt_push_dist_mm)))


class GirderMotorX1(PVPositioner):
    """Girder X translation pseudo motor"""

    setpoint = Component(EpicsSignal, ":X_SET", name="sp")
    readback = Component(EpicsSignalRO, ":X1", name="rbv")
    done = Component(EpicsSignal, ":M-DMOV", name="dmov")


class GirderMotorY1(PVPositioner):
    """Girder Y translation pseudo motor"""

    setpoint = Component(EpicsSignal, ":Y_SET", name="sp")
    readback = Component(EpicsSignalRO, ":Y1", name="rbv")
    done = Component(EpicsSignal, ":M-DMOV", name="dmov")


class GirderMotorYAW(PVPositioner):
    """Girder YAW pseudo motor"""

    setpoint = Component(EpicsSignal, ":YAW_SET", name="sp")
    readback = Component(EpicsSignalRO, ":YAW1", name="rbv")
    done = Component(EpicsSignal, ":M-DMOV", name="dmov")


class GirderMotorROLL(PVPositioner):
    """Girder ROLL pseudo motor"""

    setpoint = Component(EpicsSignal, ":ROLL_SET", name="sp")
    readback = Component(EpicsSignalRO, ":ROLL1", name="rbv")
    done = Component(EpicsSignal, ":M-DMOV", name="dmov")


class GirderMotorPITCH(PVPositioner):
    """Girder YAW pseudo motor"""

    setpoint = Component(EpicsSignal, ":PITCH_SET", name="sp")
    readback = Component(EpicsSignalRO, ":PITCH1", name="rbv")
    done = Component(EpicsSignal, ":M-DMOV", name="dmov")


class VirtualEpicsSignalRO(EpicsSignalRO):
    """This is a test class to create derives signals from one or
    multiple original signals...
    """

    def calc(self, val):
        return val

    def get(self, *args, **kwargs):
        raw = super().get(*args, **kwargs)
        return self.calc(raw)

    # def describe(self):
    #    val = self.get()
    #    d = super().describe()
    #    d[self.name]["dtype"] = data_type(val)
    #    return d


class MonoTheta1(VirtualEpicsSignalRO):
    """Converts the pusher motor position to theta angle"""

    _mono_a0_enc_scale1 = -1.0
    _mono_a1_lever_length1 = 206.706
    _mono_a2_pusher_offs1 = 6.85858
    _mono_a3_enc_offs1 = -16.9731

    def calc(self, val):
        asin_arg = (val - self._mono_a2_pusher_offs1) / self._mono_a1_lever_length1
        theta1 = (
            self._mono_a0_enc_scale1 * asin(asin_arg) / 3.141592 * 180.0 + self._mono_a3_enc_offs1
        )
        return theta1


class MonoTheta2(VirtualEpicsSignalRO):
    """Converts the pusher motor position to theta angle"""

    _mono_a3_enc_offs2 = -19.7072
    _mono_a2_pusher_offs2 = 5.93905
    _mono_a1_lever_length2 = 206.572
    _mono_a0_enc_scale2 = -1.0

    def calc(self, val):
        asin_arg = (val - self._mono_a2_pusher_offs2) / self._mono_a1_lever_length2
        theta2 = (
            self._mono_a0_enc_scale2 * asin(asin_arg) / 3.141592 * 180.0 + self._mono_a3_enc_offs2
        )
        return theta2


class EnergyKev(VirtualEpicsSignalRO):
    """Converts the pusher motor position to energy in keV"""

    _mono_a3_enc_offs2 = -19.7072
    _mono_a2_pusher_offs2 = 5.93905
    _mono_a1_lever_length2 = 206.572
    _mono_a0_enc_scale2 = -1.0
    _mono_hce = 12.39852066
    _mono_2d2 = 2 * 5.43102 / sqrt(3)

    def calc(self, val):
        asin_arg = (val - self._mono_a2_pusher_offs2) / self._mono_a1_lever_length2
        theta2_deg = (
            self._mono_a0_enc_scale2 * asin(asin_arg) / 3.141592 * 180.0 + self._mono_a3_enc_offs2
        )
        E_keV = -self._mono_hce / self._mono_2d2 / sin(theta2_deg / 180.0 * 3.14152)
        return E_keV


class CurrentSum(Signal):
    """Adds up four current signals from the parent"""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.parent.ch1.subscribe(self._emit_value)

    def _emit_value(self, **kwargs):
        timestamp = kwargs.pop("timestamp", time.time())
        self.wait_for_connection()
        self._run_subs(sub_type='value', timestamp=timestamp, obj=self)

    def get(self, *args, **kwargs):
        total = self.parent.ch1.get() + self.parent.ch2.get() + self.parent.ch3.get() + self.parent.ch4.get() 
        return total


class Bpm4i(Device):
    SUB_VALUE = "value"
    _default_sub = SUB_VALUE

    ch1 = Component(EpicsSignalRO, "S2", auto_monitor=True, kind=Kind.omitted, name="ch1")
    ch2 = Component(EpicsSignalRO, "S3", auto_monitor=True, kind=Kind.omitted, name="ch2")
    ch3 = Component(EpicsSignalRO, "S4", auto_monitor=True, kind=Kind.omitted, name="ch3")
    ch4 = Component(EpicsSignalRO, "S5", auto_monitor=True, kind=Kind.omitted, name="ch4")
    sum = Component(CurrentSum, kind=Kind.hinted, name="sum", )




if __name__ == "__main__":
    dut = Bpm4i("X12SA-OP1-SCALER.", name="bpm4")
    dut.wait_for_connection()
    print(dut.read())
    print(dut.describe())

