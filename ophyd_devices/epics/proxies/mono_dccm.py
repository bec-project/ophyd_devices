# -*- coding: utf-8 -*-
"""
Created on Wed Oct 13 18:06:15 2021

@author: mohacsi_i

IMPORTANT: Virtual monochromator axes should be implemented already in EPICS!!!
"""

import numpy as np
from math import isclose
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
from ophyd.sim import SynAxis, Syn2DGauss

LN_CORR = 2e-4


def a2e(angle, hkl=[1, 1, 1], lnc=False, bent=False, deg=False):
    """Convert between angle and energy for Si monchromators
    ATTENTION: 'angle' must be in radians, not degrees!
    """
    lncorr = LN_CORR if lnc else 0.0
    angle = angle * np.pi / 180 if deg else angle

    # Lattice constant along direction
    d0 = 5.43102 * (1.0 - lncorr) / np.linalg.norm(hkl)
    energy = 12.39842 / (2.0 * d0 * np.sin(angle))
    return energy


def e2w(energy):
    """Convert between energy and wavelength"""
    return 0.1 * 12398.42 / energy


def w2e(wwl):
    """Convert between wavelength and energy"""
    return 12398.42 * 0.1 / wwl


def e2a(energy, hkl=[1, 1, 1], lnc=False, bent=False):
    """Convert between energy and angle for Si monchromators
    ATTENTION: 'angle' must be in radians, not degrees!
    """
    lncorr = LN_CORR if lnc else 0.0

    # Lattice constant along direction
    d0 = 2 * 5.43102 * (1.0 - lncorr) / np.linalg.norm(hkl)
    angle = np.arcsin(12.39842 / d0 / energy)

    # Rfine for bent mirror
    if bent:
        rho = 2 * 19.65 * 8.35 / 28 * np.sin(angle)
        dt = 0.2e-3 / rho * 0.279
        d0 = 2 * 5.43102 * (1.0 + dt) / np.linalg.norm(hkl)
        angle = np.arcsin(12.39842 / d0 / energy)

    return angle


class MonoMotor(PseudoPositioner):
    """Monochromator axis

    Small wrapper to combine a real angular axis with the corresponding energy.
    ATTENTION: 'angle' is in degrees, at least for PXIII
    """

    # Real axis (in degrees)
    angle = Component(EpicsMotor, "", name="angle")
    # Virtual axis
    energy = Component(PseudoSingle, name="energy")

    _real = ["angle"]

    @pseudo_position_argument
    def forward(self, pseudo_pos):
        return self.RealPosition(angle=180.0 * e2a(pseudo_pos.energy) / 3.141592)

    @real_position_argument
    def inverse(self, real_pos):
        return self.PseudoPosition(energy=a2e(3.141592 * real_pos.angle / 180.0))


class MonoDccm(PseudoPositioner):
    """Combined DCCM monochromator

    The first crystal selects the energy, the second one is only following.
    DCCMs are quite simple in terms that they can't crash and we don't
    have a beam offset.
    ATTENTION: 'angle' is in degrees, at least for PXIII
    """

    # Real axis (in degrees)
    th1 = Component(EpicsMotor, "ROX1", name="theta1")
    th2 = Component(EpicsMotor, "ROX2", name="theta2")

    # Virtual axes
    en1 = Component(PseudoSingle, name="en1")
    en2 = Component(PseudoSingle, name="en2")
    energy = Component(PseudoSingle, name="energy", kind=Kind.hinted)

    # Other parameters
    # feedback = Component(EpicsSignal, "MONOBEAM", name="feedback")
    # enc1 = Component(EpicsSignalRO, "1:EXC1", name="enc1")
    # enc2 = Component(EpicsSignalRO, "1:EXC2", name="enc2")

    @pseudo_position_argument
    def forward(self, pseudo_pos):
        """WARNING: We have an overdefined system! Not sure if common crystal movement is reliable without retuning"""
        if (
            abs(pseudo_pos.energy - self.energy.position) > 0.0001
            and abs(pseudo_pos.en1 - self.en1.position) < 0.0001
            and abs(pseudo_pos.en2 - self.en2.position) < 0.0001
        ):
            # Probably the common energy was changed
            return self.RealPosition(
                th1=-180.0 * e2a(pseudo_pos.energy) / 3.141592,
                th2=180.0 * e2a(pseudo_pos.energy) / 3.141592,
            )
        else:
            # Probably the individual axes was changes
            return self.RealPosition(
                th1=-180.0 * e2a(pseudo_pos.en1) / 3.141592,
                th2=180.0 * e2a(pseudo_pos.en2) / 3.141592,
            )

    @real_position_argument
    def inverse(self, real_pos):
        return self.PseudoPosition(
            en1=-a2e(3.141592 * real_pos.th1 / 180.0),
            en2=a2e(3.141592 * real_pos.th2 / 180.0),
            energy=-a2e(3.141592 * real_pos.th1 / 180.0),
        )
