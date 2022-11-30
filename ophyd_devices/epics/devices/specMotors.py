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
    Device,
    Signal,
    Component,
    Kind,
)
from ophyd.pseudopos import pseudo_position_argument, real_position_argument


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
        self._run_subs(sub_type="value", timestamp=timestamp, obj=self)

    def get(self, *args, **kwargs):
        # self.parent._cnt.set(1).wait()
        self._metadata["timestamp"] = time.time()
        total = (
            self.parent.ch1.get()
            + self.parent.ch2.get()
            + self.parent.ch3.get()
            + self.parent.ch4.get()
        )
        return total


class Bpm4i(Device):
    SUB_VALUE = "value"
    _default_sub = SUB_VALUE
    _cont = Component(EpicsSignal, "CONT", put_complete=True, kind=Kind.omitted)
    _cnt = Component(EpicsSignal, "CNT", put_complete=True, kind=Kind.omitted)
    ch1 = Component(EpicsSignalRO, "S2", auto_monitor=True, kind=Kind.omitted, name="ch1")
    ch2 = Component(EpicsSignalRO, "S3", auto_monitor=True, kind=Kind.omitted, name="ch2")
    ch3 = Component(EpicsSignalRO, "S4", auto_monitor=True, kind=Kind.omitted, name="ch3")
    ch4 = Component(EpicsSignalRO, "S5", auto_monitor=True, kind=Kind.omitted, name="ch4")
    sum = Component(
        CurrentSum,
        kind=Kind.hinted,
        name="sum",
    )

    def __init__(
        self,
        prefix="",
        *,
        name,
        kind=None,
        read_attrs=None,
        configuration_attrs=None,
        parent=None,
        **kwargs
    ):
        super().__init__(
            prefix,
            name=name,
            kind=kind,
            read_attrs=read_attrs,
            configuration_attrs=configuration_attrs,
            parent=parent,
            **kwargs
        )
        self.sum.name = self.name
        # Ensure the scaler counts automatically
        self._cont.wait_for_connection()
        self._cont.set(1).wait()
        self.ch1.subscribe(self._emit_value)

    def _emit_value(self, **kwargs):
        timestamp = kwargs.pop("timestamp", time.time())
        self.wait_for_connection()
        self._run_subs(sub_type=self.SUB_VALUE, timestamp=timestamp, obj=self)


SPEC_DATA_PATH = "/import/work/sls/spec/local/X12SA/macros/spec_data"

class FilterWheel(PseudoPositioner):
    """Filter wheel in the cSAXS optics hutch

    The OP filters consist of 3 wheels, each containing 5 filter slots (one is empty).
    This gives 5**3=125 possible filter combinations.

    """
    # Real axis (in degrees)
    fi1try = Component(EpicsMotor, "X12SA-OP-FI1:TRY1", name="fi1try")
    fi2try = Component(EpicsMotor, "X12SA-OP-FI2:TRY1", name="fi2try")
    fi3try = Component(EpicsMotor, "X12SA-OP-FI3:TRY1", name="fi3try")
    energy = Component(EnergyKev, "X12SA-OP-MO:ROX2", name="energy")
    # Virtual axis
    trans = Component(PseudoSingle, name="trans")

    _real = ["fi1try", "fi2try", "fi3try"]

    _materials = (['None', 'Ge', 'Si', 'Si', 'Si'], 
                  ['None', 'Ge', 'Ge', 'Si', 'Si'],
                  ['None', 'Si', 'Ge', 'Si', 'Si'])
    _thickness = ([0.0, 400.0, 6400.0, 800.0, 100.0], 
                  [0.0, 800.0, 100.0, 1600.0, 200.0],
                  [0.0, 200.0, 200.0, 3200.0, 400.0])
    _enabled = ([True, True, True, True, True], 
                [True, True, True, True, True],
                [True, False, True, True, True])
    _positions = ([0.0, -20, -40, -60, -80], 
                  [0.0, -20, -40, -60, -80],
                  [0.0, -20, -40, -60, -80])
    _tolerance = 2

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._constants = {}

        self._constants['Block'] = np.array([[1000, 1e-9], [10000, 1e-9], [100000, 1e-9]])
        self._constants['None'] = np.array([[1000, 1e42], [10000, 1e42], [100000, 1e42]])
        self._constants['Si'] = np.loadtxt(f"{SPEC_DATA_PATH}/filter_attenuation-length_si.txt")
        self._constants['Ge'] = np.loadtxt(f"{SPEC_DATA_PATH}/filter_attenuation-length_ge.txt")

    def getSelection(self, wheel: int, pos: float) -> str:
        dst = np.array(self._positions[int(wheel)])-pos
        loc = np.where(np.abs(dst)<self._tolerance)
        if len(loc)==0:
            return 0
        elif len(loc)==1:
            return int(loc[0])
        else:
            # ToDo: Additional possibilities like filter out
            raise Exception(f"The OP filter location is ambiguous, candidates are: {loc}")
        
    def getAttenuationLength(self, mat: str, energy: float) -> float:
        return np.interp(energy, self._constants[mat][:,0], self._constants[mat][:,1])

    def getTransmission(self, wheel: int, slot: int, energy=None) -> float:
        if energy is None:
            energy = 1000 * self.energy.get()
        wheel = int(wheel)
        slot = int(slot)
        thickness = self._thickness[wheel][slot]
        material = self._materials[wheel][slot]
        attlength = self.getAttenuationLength(material, energy)
        return np.exp(-thickness/attlength)

    def transmissionTensor(self, energy=None) -> np.ndarray:
        if energy is None:
            energy = 1000 * self.energy.get()
        trans0 = [self.getTransmission(0, ii, energy) for ii in range(5)]
        trans1 = [self.getTransmission(1, ii, energy) for ii in range(5)]
        trans2 = [self.getTransmission(2, ii, energy) for ii in range(5)]
        trans012 = np.outer(np.outer(trans0, trans1), trans2).reshape([5,5,5])
        return trans012

    @pseudo_position_argument
    def forward(self, pseudo_pos):
        trans = pseudo_pos.trans
        trans = 1 if trans > 1 else trans
        trans = 0 if trans < 0 else trans

        tens = self.transmissionTensor()
        # Logarithmic minimum
        amin = np.argmin(np.abs(np.log(tens/trans)))
        print(np.log(tens/trans))
        print(amin)
        return self.RealPosition(
            fi1try=self._positions[0][amin[0]],
            fi2try=self._positions[1][amin[1]],
            fi3try=self._positions[2][amin[2]],
        )

    @real_position_argument
    def inverse(self, real_pos):
        sel = [self.getSelection(0,real_pos.fi1try), 
               self.getSelection(1,real_pos.fi2try),
               self.getSelection(2,real_pos.fi3try)]
        trans = [self.getTransmission(0, sel[0]), self.getTransmission(1, sel[1]), self.getTransmission(2, sel[2]), ]
        print(trans)

        return self.PseudoPosition(trans = np.prod(trans))








if __name__ == "__main__":
    dut = FilterWheel("", name="fil_op")
    dut.wait_for_connection()
    print(dut.read())
    print(dut.describe())
