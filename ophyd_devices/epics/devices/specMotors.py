# -*- coding: utf-8 -*-
"""
Created on Wed Oct 13 18:06:15 2021

@author: mohacsi_i

IMPORTANT: Virtual monochromator axes should be implemented already in EPICS!!!
"""

import numpy as np
from math import isclose, tan, atan
from ophyd import (
    EpicsSignal,
    EpicsSignalRO,
    EpicsMotor,
    PseudoPositioner,
    PseudoSingle,
    Device,
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
