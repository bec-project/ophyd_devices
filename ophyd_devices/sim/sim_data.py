from abc import ABC, abstractmethod
from collections import defaultdict
import enum
import time as ttime
import numpy as np

from bec_lib import bec_logger

logger = bec_logger.logger


class SimulatedDataException(Exception):
    """Exception raised when there is an issue with the simulated data."""


class SimulationType(str, enum.Enum):
    """Type of simulation to steer simulated data."""

    CONSTANT = "constant"
    GAUSSIAN = "gauss"


class NoiseType(str, enum.Enum):
    """Type of noise to add to simulated data."""

    NONE = "none"
    UNIFORM = "uniform"
    POISSON = "poisson"


class SimulatedDataBase:
    USER_ACCESS = [
        "get_sim_params",
        "set_sim_params",
        "get_sim_type",
        "set_sim_type",
    ]

    def __init__(self, *args, parent=None, device_manager=None, **kwargs) -> None:
        self.parent = parent
        self.sim_state = defaultdict(lambda: {})
        self._all_params = defaultdict(lambda: {})
        self.device_manager = device_manager
        self._simulation_type = None
        self.init_paramaters(**kwargs)
        self._active_params = self._all_params.get(self._simulation_type, None)

    def init_paramaters(self, **kwargs):
        """Initialize the parameters for the Simulated Data

        This methods should be implemented by the subclass.

        It should set the default parameters for:
        - self._params (dict used for e.g. computation of gaussian)
        - self._simulation_type (SimulationType, e.g. 'constant', 'gauss').
        - self._noise (NoiseType, e.g. 'none', 'uniform', 'poisson')

        It sets the default parameters for the simulated data,
        in self._params that are required for the simulation of for instance
        the siumulation type gaussian.
        """

    def get_sim_params(self) -> dict:
        """Return the parameters self._params of the simulation."""
        return self._active_params

    def set_sim_params(self, params: dict) -> None:
        """Set the parameters self._params of the simulation."""
        for k, v in params.items():
            try:
                self._active_params[k] = v
            except KeyError:
                # TODO propagate msg to client!
                logger.warning(
                    f"Could not set {k} to {v} in {self._active_params}.KeyError raised. Ignoring."
                )

    def get_sim_type(self) -> SimulationType:
        """Return the simulation type of the simulation.

        Returns:
            SimulationType: Type of simulation (e.g. "constant" or "gauss).
        """
        return self._simulation_type

    def set_sim_type(self, simulation_type: SimulationType) -> None:
        """Set the simulation type of the simulation."""
        try:
            self._simulation_type = SimulationType(simulation_type)
        except ValueError:
            raise SimulatedDataException(
                f"Could not set simulation type to {simulation_type}. Valid options are 'constant'"
                " and 'gauss'"
            )
        self._active_params = self._all_params.get(self._simulation_type, None)

    def _compute_sim_state(self, signal_name: str) -> None:
        """Update the simulated state of the device.

        If no computation is relevant, ignore this method.
        Otherwise implement it in the subclass.
        """

    def update_sim_state(self, signal_name: str, value: any) -> None:
        """Update the simulated state of the device.

        Args:
            signal_name (str): Name of the signal to update.
        """
        self.sim_state[signal_name]["value"] = value
        self.sim_state[signal_name]["timestamp"] = ttime.time()


class SimulatedDataMonitor(SimulatedDataBase):
    """Simulated data for a monitor."""

    def init_paramaters(self, **kwargs):
        """Initialize the parameters for the Simulated Data

        Ref_motor is the motor that is used to compute the gaussian.
        Amp is the amplitude of the gaussian.
        Cen is the center of the gaussian.
        Sig is the sigma of the gaussian.
        Noise is the type of noise to add to the signal. Be aware that poisson noise will round the value to an integer-like values.
        Noise multiplier is the multiplier of the noise, only relevant for uniform noise.
        """
        self._all_params = {
            SimulationType.CONSTANT: {
                "amp": 100,
                "noise": NoiseType.POISSON,
                "noise_multiplier": 0.1,
            },
            SimulationType.GAUSSIAN: {
                "ref_motor": "samx",
                "amp": 100,
                "cen": 0,
                "sig": 1,
                "noise": NoiseType.NONE,
                "noise_multiplier": 0.1,
            },
        }

        if self.parent.init_sim_params:
            sim_type = self.parent.init_sim_params.pop("sym_type", SimulationType.CONSTANT)
            for v in self._all_params.values():
                for k in v.keys():
                    if k in self.parent.init_sim_params:
                        v[k] = self.parent.init_sim_params[k]
        else:
            sim_type = SimulationType.CONSTANT
        self.set_sim_type(sim_type)

    def _compute_sim_state(self, signal_name: str) -> None:
        """Update the simulated state of the device.

        Args:
            signal_name (str): Name of the signal to update.
            sim_type (SimulationType, optional): Type of simulation to steer simulated data. Defaults to SimulationType.CONSTANT.
        """
        if self.get_sim_type() == SimulationType.CONSTANT:
            value = self._compute_constant()
        elif self.get_sim_type() == SimulationType.GAUSSIAN:
            value = self._compute_gaussian()

        self.update_sim_state(signal_name, value)

    def _compute_constant(self) -> float:
        """Compute a random value."""
        v = self._active_params["amp"]
        if self._active_params["noise"] == NoiseType.POISSON:
            v = np.random.poisson(np.round(v), 1)[0]
        elif self._active_params["noise"] == NoiseType.UNIFORM:
            v += np.random.uniform(-1, 1) * self._active_params["noise_multiplier"]
        elif self._active_params["noise"] == NoiseType.NONE:
            v = self._active_params["amp"]
        else:
            # TODO Propagate msg to client!
            logger.warning(
                f"Unknown noise type {self._active_params['noise']}. Please choose from 'poisson',"
                " 'uniform' or 'none'. Returning 0."
            )
            return 0
        return v

    def _compute_gaussian(self) -> float:
        """Compute a gaussian value.

        Based on the parameters in self._params, a value of a gaussian distributed
        is computed with respected to the motor position of ref_motor.

        If computation fails, it returns 0.
        """

        params = self._active_params
        try:
            motor_pos = self.device_manager.devices[params["ref_motor"]].obj.read()[
                params["ref_motor"]
            ]["value"]
            v = params["amp"] * np.exp(
                -((motor_pos - params["cen"]) ** 2) / (2 * params["sig"] ** 2)
            )
            if params["noise"] == NoiseType.POISSON:
                v = np.random.poisson(np.round(v), 1)[0]
            elif params["noise"] == NoiseType.UNIFORM:
                v += np.random.uniform(-1, 1) * params["noise_multiplier"]
            return v
        except SimulatedDataException as exc:
            # TODO Propagate msg to client!
            logger.warning(
                f"Could not compute gaussian for {params['ref_motor']} with {exc} raised."
                "Returning 0 instead."
            )
            return 0


class SimulatedDataCamera(SimulatedDataBase):
    """Simulated data for a 2D camera."""

    def init_paramaters(self, **kwargs):
        """Initialize the parameters for the simulated camera data"""
        self._all_params = {
            SimulationType.CONSTANT: {
                "amp": 100,
                "noise": NoiseType.POISSON,
                "noise_multiplier": 0.1,
            },
            SimulationType.GAUSSIAN: {
                "amp": 100,
                "cen": np.array([50, 50]),
                "cov": np.array([[10, 0], [0, 10]]),
                "noise": NoiseType.NONE,
                "noise_multiplier": 0.1,
            },
        }

        if self.parent.init_sim_params:
            sim_type = self.parent.init_sim_params.pop("sym_type", SimulationType.CONSTANT)
            for v in self._all_params.values():
                for k in v.keys():
                    if k in self.parent.init_sim_params:
                        v[k] = self.parent.init_sim_params[k]
        else:
            sim_type = SimulationType.CONSTANT
        self.set_sim_type(sim_type)

    def _compute_sim_state(self, signal_name: str) -> None:
        """Update the simulated state of the device.

        Args:
            signal_name (str): Name of the signal to update.
            sim_type (SimulationType, optional): Type of simulation to steer simulated data. Defaults to SimulationType.CONSTANT.
        """
        if self.get_sim_type() == SimulationType.CONSTANT:
            value = self._compute_constant()
        elif self.get_sim_type() == SimulationType.GAUSSIAN:
            value = self._compute_gaussian()

        self.update_sim_state(signal_name, value)

    def _compute_constant(self) -> float:
        """Compute a random value."""
        # tuple with shape
        shape = self.sim_state[self.parent.image_shape.name]["value"]
        v = self._active_params["amp"] * np.ones(shape, dtype=np.uint16)
        if self._active_params["noise"] == NoiseType.POISSON:
            v = np.random.poisson(np.round(v), v.shape)
            return v
        elif self._active_params["noise"] == NoiseType.UNIFORM:
            multiplier = self._active_params["noise_multiplier"]
            v += np.random.randint(-multiplier, multiplier, v.shape)
            return v
        elif self._active_params["noise"] == NoiseType.NONE:
            return v
        else:
            # TODO Propagate msg to client!
            logger.warning(
                f"Unknown noise type {self._active_params['noise']}. Please choose from 'poisson',"
                " 'uniform' or 'none'. Returning 0."
            )
            return 0

    def _compute_multivariate_gaussian(self, pos: np.ndarray, cen: np.ndarray, cov: np.ndarray):
        """Return the multivariate Gaussian distribution on array pos."""

        dim = cen.shape[0]
        cov_det = np.linalg.det(cov)
        cov_inv = np.linalg.inv(cov)
        N = np.sqrt((2 * np.pi) ** dim * cov_det)
        # This einsum call calculates (x-mu)T.Sigma-1.(x-mu) in a vectorized
        # way across all the input variables.
        fac = np.einsum("...k,kl,...l->...", pos - cen, cov_inv, pos - cen)

        return np.exp(-fac / 2) / N

    def _compute_gaussian(self) -> float:
        """Compute a gaussian value.

        Based on the parameters in self._params, a value of a gaussian distributed
        is computed with respected to the motor position of ref_motor.

        If computation fails, it returns 0.
        """

        params = self._active_params
        shape = self.sim_state[self.parent.image_shape.name]["value"]
        try:
            X, Y = np.meshgrid(
                np.linspace(0, shape[0] - 1, shape[0]),
                np.linspace(0, shape[1] - 1, shape[1]),
            )
            pos = np.empty((*X.shape, 2))
            pos[:, :, 0] = X
            pos[:, :, 1] = Y

            v = self._compute_multivariate_gaussian(pos=pos, cen=params["cen"], cov=params["cov"])
            # divide by max(v) to ensure that maximum is params["amp"]
            v *= params["amp"] / np.max(v)

            # TODO add dependency from motor position -> #transmission factor, sigmoidal form from 0 to 1 as a function of motor pos
            # motor_pos = self.device_manager.devices[params["ref_motor"]].obj.read()[
            #     params["ref_motor"]
            # ]["value"]

            if params["noise"] == NoiseType.POISSON:
                v = np.random.poisson(np.round(v), v.shape)
                return v
            elif params["noise"] == NoiseType.UNIFORM:
                multiplier = params["noise_multiplier"]
                v += np.random.uniform(-multiplier, multiplier, v.shape)
                return v
        except SimulatedDataException as exc:
            # TODO Propagate msg to client!
            logger.warning(
                f"Could not compute gaussian for {params['ref_motor']} with {exc} raised."
                "Returning 0 instead."
            )
            return 0
