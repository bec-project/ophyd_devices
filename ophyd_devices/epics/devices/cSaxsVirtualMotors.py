import numpy as np
from ophyd import Component, EpicsMotor

TABLES_DT_PUSH_DIST_MM = 890


SPEC_DATA_PATH = "/import/work/sls/spec/local/X12SA/macros/spec_data"


class DetectorTableTheta(PseudoPositioner):
    """Detector table tilt motor

    Small wrapper to adjust the detector table tilt as angle.
    The table is pushed from one side by a single vertical motor.

    Note: Rarely used!
    """

    # Real axis (in degrees)
    pusher = Component(EpicsMotor, "", name="pusher")
    # Virtual axis
    theta = Component(PseudoSingle, name="theta")

    _real = ["pusher"]

    @pseudo_position_argument
    def forward(self, pseudo_pos):
        return self.RealPosition(
            pusher=tan(pseudo_pos.theta * 3.141592 / 180.0) * TABLES_DT_PUSH_DIST_MM
        )

    @real_position_argument
    def inverse(self, real_pos):
        return self.PseudoPosition(
            theta=-180 * atan(real_pos.pusher / TABLES_DT_PUSH_DIST_MM) / 3.141592
        )

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
    _tolarance = 2

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._constants = {}

	self._constants['Block'] = np.array([[1000, 1e-9], [10000, 1e-9], [100000, 1e-9]])
	self._constants['None'] = np.array([[1000, 1e42], [10000, 1e42], [100000, 1e42]])
        self._constants['Si'] = np.loadtxt(f"{SPEC_DATA_PATH}/filter_attenuation-length_si.txt")
        self._constants['Ge'] = np.loadtxt(f"{SPEC_DATA_PATH}/filter_attenuation-length_ge.txt")



    def getSelection(self, wheel: int, pos: float) -> str:
        dst = np.ndarray(self._positions[wheel])-pos
        loc = np.where(np.abs(dst)<self._tolerance)
        if len(loc)==0:
            return "Block"
        elif len(loc)==1:
            return self._materials[wheel][loc[0]]
        else:
            # ToDo: Additional possibilities like filter out
            raise Exception(f"The OP filter location is ambiguous, candidates are: {loc}")
        
    def getAttenuationLength(self, mat: str, energy: float)
        return np.interp(energy, self._constants[mat][:,0], self._constants[mat][:,1])

    def getTransmission(self, wheel: int, sel: float, energy=None) -> float:
        if energy is None:
            energy = 1000 * self.energy.get()
        thickness = self._thickness[wheel][sel]
        material = self._materials[wheel][sel]
        attlength = self._thickness[wheel][sel]
        return np.exp(-thickness/attlength)

    def transmissionTensor(self, energy=None) -> np.ndarray:
        if energy is None:
            energy = 1000 * self.energy.get()
        trans0 = [self.getTransmission(0, ii, energy) for ii in range(5)]
        trans1 = [self.getTransmission(0, ii, energy) for ii in range(5)]
        trans2 = [self.getTransmission(0, ii, energy) for ii in range(5)]
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







