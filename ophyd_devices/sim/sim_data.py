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

        It sets the default parameters for the simulated data in
        self._params and calls self._update_init_params()
        """

    def get_sim_params(self) -> dict:
        """Return the currently parameters for the active simulation type in sim_type.

        These parameters can be changed with set_sim_params.

        Returns:
            dict: Parameters of the currently active simulation in sim_type.
        """
        return self._active_params

    def set_sim_params(self, params: dict) -> None:
        """Change the current set of parameters for the active simulation type.

        Args:
            params (dict): New parameters for the active simulation type.

        Raises:
            SimulatedDataException: If the new parameters can not be set or is not part of the parameters initiated.
        """
        for k, v in params.items():
            try:
                if k == "noise":
                    self._active_params[k] = NoiseType(v)
                else:
                    self._active_params[k] = v
            except Exception as exc:
                raise SimulatedDataException(
                    f"Could not set {k} to {v} in {self._active_params} with exception {exc}"
                ) from exc

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
        except ValueError as exc:
            raise SimulatedDataException(
                f"Could not set simulation type to {simulation_type}. Valid options are 'constant'"
                " and 'gauss'"
            ) from exc
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

    def _update_init_params(self, sim_type_default: SimulationType) -> None:
        """Update the initial parameters of the simulated data with input from deviceConfig.

        Args:
            sim_type_default (SimulationType): Default simulation type to use if not specified in deviceConfig.
        """
        init_params = self.parent.init_sim_params
        for sim_type in self._all_params.values():
            for sim_type_config_element in sim_type:
                if init_params:
                    if sim_type_config_element in init_params:
                        sim_type[sim_type_config_element] = init_params[sim_type_config_element]
        # Set simulation type to default if not specified in deviceConfig
        sim_type_select = (
            init_params.get("sim_type", sim_type_default) if init_params else sim_type_default
        )
        self.set_sim_type(sim_type_select)


class SimulatedDataMonitor(SimulatedDataBase):
    """Simulated data for a monitor."""

    def init_paramaters(self, **kwargs):
        """Initialize the parameters for the simulated data

        This method will fill self._all_params with the default parameters for
        SimulationType.CONSTANT and SimulationType.GAUSSIAN.
        New simulation types can be added by adding a new key to self._all_params,
        together with the required parameters for that simulation type. Please
        also complement the docstring of this method with the new simulation type.

        For SimulationType.CONSTANT:
            Amp is the amplitude of the constant value.
            Noise is the type of noise to add to the signal. Available options are 'poisson', 'uniform' or 'none'.
            Noise multiplier is the multiplier of the noise, only relevant for uniform noise.

        For SimulationType.GAUSSIAN:
            ref_motor is the motor that is used as reference to compute the gaussian.
            amp is the amplitude of the gaussian.
            cen is the center of the gaussian.
            sig is the sigma of the gaussian.
            noise is the type of noise to add to the signal. Available options are 'poisson', 'uniform' or 'none'.
            noise multiplier is the multiplier of the noise, only relevant for uniform noise.
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
        # Update init parameters and set simulation type to Constant if not specified otherwise in init_sim_params
        self._update_init_params(sim_type_default=SimulationType.CONSTANT)

    def _compute_sim_state(self, signal_name: str) -> None:
        """Update the simulated state of the device.

        It will update the value in self.sim_state with the value computed by
        the chosen simulation type.

        Args:
            signal_name (str): Name of the signal to update.
        """
        if self.get_sim_type() == SimulationType.CONSTANT:
            value = self._compute_constant()
        elif self.get_sim_type() == SimulationType.GAUSSIAN:
            value = self._compute_gaussian()

        self.update_sim_state(signal_name, value)

    def _compute_constant(self) -> float:
        """Computes constant value and adds noise if activated."""
        v = self._active_params["amp"]
        if self._active_params["noise"] == NoiseType.POISSON:
            v = np.random.poisson(np.round(v), 1)[0]
            return v
        elif self._active_params["noise"] == NoiseType.UNIFORM:
            v += np.random.uniform(-1, 1) * self._active_params["noise_multiplier"]
            return v
        elif self._active_params["noise"] == NoiseType.NONE:
            v = self._active_params["amp"]
            return v
        else:
            # TODO Propagate msg to client!
            logger.warning(
                f"Unknown noise type {self._active_params['noise']}. Please choose from 'poisson',"
                " 'uniform' or 'none'. Returning 0."
            )
            return 0

    def _compute_gaussian(self) -> float:
        """Computes return value for sim_type = "gauss".

        The value is based on the parameters for the gaussian in
        self._active_params and the position of the ref_motor
        and adds noise based on the noise type.

        If computation fails, it returns 0.

        Returns: float
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
    """Simulated class to compute data for a 2D camera."""

    def init_paramaters(self, **kwargs):
        """Initialize the parameters for the simulated data

        This method will fill self._all_params with the default parameters for
        SimulationType.CONSTANT and SimulationType.GAUSSIAN.
        New simulation types can be added by adding a new key to self._all_params,
        together with the required parameters for that simulation type. Please
        also complement the docstring of this method with the new simulation type.

        For SimulationType.CONSTANT:
            Amp is the amplitude of the constant value.
            Noise is the type of noise to add to the signal. Available options are 'poisson', 'uniform' or 'none'.
            Noise multiplier is the multiplier of the noise, only relevant for uniform noise.

        For SimulationType.GAUSSIAN:
            amp is the amplitude of the gaussian.
            cen_off is the pixel offset from the center of the gaussian from the center of the image.
                It is passed as a numpy array.
            cov is the 2D covariance matrix used to specify the shape of the gaussian.
                It is a 2x2 matrix and will be passed as a numpy array.
            noise is the type of noise to add to the signal. Available options are 'poisson', 'uniform' or 'none'.
            noise multiplier is the multiplier of the noise, only relevant for uniform noise.
        """
        self._all_params = {
            SimulationType.CONSTANT: {
                "amp": 100,
                "noise": NoiseType.POISSON,
                "noise_multiplier": 0.1,
            },
            SimulationType.GAUSSIAN: {
                "amp": 100,
                "cen_off": np.array([0, 0]),
                "cov": np.array([[10, 5], [5, 10]]),
                "noise": NoiseType.NONE,
                "noise_multiplier": 0.1,
            },
        }
        # Update init parameters and set simulation type to Gaussian if not specified otherwise in init_sim_params
        self._update_init_params(sim_type_default=SimulationType.GAUSSIAN)

    def _compute_sim_state(self, signal_name: str) -> None:
        """Update the simulated state of the device.

        It will update the value in self.sim_state with the value computed by
        the chosen simulation type.

        Args:
            signal_name (str): Name of the signal to update.
        """
        if self.get_sim_type() == SimulationType.CONSTANT:
            value = self._compute_constant()
        elif self.get_sim_type() == SimulationType.GAUSSIAN:
            value = self._compute_gaussian()

        self.update_sim_state(signal_name, value)

    def _compute_constant(self) -> float:
        """Compute a return value for sim_type = Constant."""

        # tuple with shape
        shape = self.sim_state[self.parent.image_shape.name]["value"]
        v = self._active_params["amp"] * np.ones(shape, dtype=np.uint16)
        if self._active_params["noise"] == NoiseType.POISSON:
            v = np.random.poisson(np.round(v), v.shape)
            return v
        if self._active_params["noise"] == NoiseType.UNIFORM:
            multiplier = self._active_params["noise_multiplier"]
            v += np.random.randint(-multiplier, multiplier, v.shape)
            return v
        if self._active_params["noise"] == NoiseType.NONE:
            return v
        # TODO Propagate msg to client!
        logger.warning(
            f"Unknown noise type {self._active_params['noise']}. Please choose from 'poisson',"
            " 'uniform' or 'none'. Returning 0."
        )
        return 0

    def _compute_multivariate_gaussian(
        self, pos: np.ndarray, cen_off: np.ndarray, cov: np.ndarray
    ) -> np.ndarray:
        """Computes and returns the multivariate Gaussian distribution.

        Args:
            pos (np.ndarray): Position of the gaussian.
            cen_off (np.ndarray): Offset from cener of image for the gaussian.
            cov (np.ndarray): Covariance matrix of the gaussian.

        Returns:
            np.ndarray: Multivariate Gaussian distribution.
        """

        dim = cen_off.shape[0]
        cov_det = np.linalg.det(cov)
        cov_inv = np.linalg.inv(cov)
        N = np.sqrt((2 * np.pi) ** dim * cov_det)
        # This einsum call calculates (x-mu)T.Sigma-1.(x-mu) in a vectorized
        # way across all the input variables.
        fac = np.einsum("...k,kl,...l->...", pos - cen_off, cov_inv, pos - cen_off)

        return np.exp(-fac / 2) / N

    def _compute_gaussian(self) -> float:
        """Computes return value for sim_type = "gauss".

        The value is based on the parameters for the gaussian in
        self._active_params and adds noise based on the noise type.

        If computation fails, it returns 0.

        Returns: float
        """

        params = self._active_params
        shape = self.sim_state[self.parent.image_shape.name]["value"]
        try:
            X, Y = np.meshgrid(
                np.linspace(-shape[0] / 2, shape[0] / 2, shape[0]),
                np.linspace(-shape[1] / 2, shape[1] / 2, shape[1]),
            )
            pos = np.empty((*X.shape, 2))
            pos[:, :, 0] = X
            pos[:, :, 1] = Y

            v = self._compute_multivariate_gaussian(
                pos=pos, cen_off=params["cen_off"], cov=params["cov"]
            )
            # divide by max(v) to ensure that maximum is params["amp"]
            v *= params["amp"] / np.max(v)

            # TODO add dependency from motor position -> #transmission factor, sigmoidal form from 0 to 1 as a function of motor pos
            # motor_pos = self.device_manager.devices[params["ref_motor"]].obj.read()[
            #     params["ref_motor"]
            # ]["value"]

            if params["noise"] == NoiseType.POISSON:
                v = np.random.poisson(np.round(v), v.shape)
                return v
            if params["noise"] == NoiseType.UNIFORM:
                multiplier = params["noise_multiplier"]
                v += np.random.uniform(-multiplier, multiplier, v.shape)
                return v
            if self._active_params["noise"] == NoiseType.NONE:
                return v
        except SimulatedDataException as exc:
            # TODO Propagate msg to client!
            logger.warning(
                f"Could not compute gaussian for {params['ref_motor']} with {exc} raised."
                "Returning 0 instead."
            )
            return 0
