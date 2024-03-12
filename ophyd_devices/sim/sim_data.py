from __future__ import annotations

from collections import defaultdict
from abc import ABC, abstractmethod

from prettytable import PrettyTable

import enum
import inspect
import time as ttime
import numpy as np
from lmfit import models, Model

from bec_lib import bec_logger

logger = bec_logger.logger


class SimulatedDataException(Exception):
    """Exception raised when there is an issue with the simulated data."""


class SimulationType2D(str, enum.Enum):
    """Type of simulation to steer simulated data."""

    CONSTANT = "constant"
    GAUSSIAN = "gaussian"


class NoiseType(str, enum.Enum):
    """Type of noise to add to simulated data."""

    NONE = "none"
    UNIFORM = "uniform"
    POISSON = "poisson"


class HotPixelType(str, enum.Enum):
    """Type of hot pixel to add to simulated data."""

    CONSTANT = "constant"
    FLUCTUATING = "fluctuating"


DEFAULT_PARAMS_LMFIT = {
    "c0": 1,
    "c1": 1,
    "c2": 1,
    "c3": 1,
    "c4": 1,
    "c": 100,
    "amplitude": 100,
    "center": 0,
    "sigma": 1,
}

DEFAULT_PARAMS_NOISE = {
    "noise": NoiseType.UNIFORM,
    "noise_multiplier": 10,
}

DEFAULT_PARAMS_MOTOR = {
    "ref_motor": "samx",
}

DEFAULT_PARAMS_CAMERA_GAUSSIAN = {
    "amplitude": 100,
    "center_offset": np.array([0, 0]),
    "covariance": np.array([[400, 100], [100, 400]]),
}

DEFAULT_PARAMS_CAMERA_CONSTANT = {
    "amplitude": 100,
}

DEFAULT_PARAMS_HOT_PIXEL = {
    "hot_pixel_coords": np.array([[24, 24], [50, 20], [4, 40]]),
    "hot_pixel_types": [
        HotPixelType.FLUCTUATING,
        HotPixelType.CONSTANT,
        HotPixelType.FLUCTUATING,
    ],
    "hot_pixel_values": np.array([1e4, 1e6, 1e4]),
}


class SimulatedDataBase(ABC):
    """Abstract base class for simulated data.

    This class should be subclassed to implement the simulated data for a specific device.
    It provides the basic functionality to set and get data from the simulated data class

    ---------------------
    The class provides the following methods:

    - execute_simulation_method:    execute a method from the simulated data class or reroute execution to device proxy class
    - sim_select_model:             select the active simulation model
    - sim_params:                   get the parameters for the active simulation mdoel
    - sim_models:                   get the available simulation models
    - update_sim_state:             update the simulated state of the device
    """

    USER_ACCESS = [
        "sim_params",
        "sim_select_model",
        "sim_get_models",
        "sim_show_all",
    ]

    def __init__(self, *args, parent=None, device_manager=None, **kwargs) -> None:
        """
        Note:
        self._model_params duplicates parameters from _params that are solely relevant for the model used.
        This facilitates easier and faster access for computing the simulated state using the lmfit package.
        """
        self.parent = parent
        self.device_manager = device_manager
        self.sim_state = defaultdict(dict)
        self.registered_proxies = getattr(self.parent, "registered_proxies", {})
        self._model = {}
        self._model_params = None
        self._params = {}

    def execute_simulation_method(self, *args, method=None, signal_name: str = "", **kwargs) -> any:
        """
        Execute either the provided method or reroutes the method execution
        to a device proxy in case it is registered in self.parentregistered_proxies.
        """
        if self.registered_proxies and self.device_manager:
            for proxy_name, signal in self.registered_proxies.items():
                if signal == signal_name or f"{self.parent.name}_{signal}" == signal_name:
                    sim_proxy = self.device_manager.devices.get(proxy_name, None)
                    if sim_proxy and sim_proxy.enabled is True:
                        method = sim_proxy.obj.lookup[self.parent.name]["method"]
                        args = sim_proxy.obj.lookup[self.parent.name]["args"]
                        kwargs = sim_proxy.obj.lookup[self.parent.name]["kwargs"]
                    break

        if method is not None:
            return method(*args, **kwargs)
        raise SimulatedDataException(f"Method {method} is not available for {self.parent.name}")

    def sim_select_model(self, model: str) -> None:
        """
        Method to select the active simulation model.
        It will initiate the model_cls and parameters for the model.

        Args:
            model (str): Name of the simulation model to select.

        """
        model_cls = self.get_model_cls(model)
        self._model = model_cls() if callable(model_cls) else model_cls
        self._params = self.get_params_for_model_cls()
        self._params.update(self._get_additional_params())
        print(self._get_table_active_simulation())

    @property
    def sim_params(self) -> dict:
        """
        Property that returns the parameters for the active simulation model. It can also
        be used to set the parameters for the active simulation updating the parameters of the model.

        Returns:
            dict: Parameters for the active simulation model.

        The following example shows how to update the noise parameter of the current simulation.
        >>> dev.<device>.sim.sim_params = {"noise": "poisson"}
        """
        return self._params

    @sim_params.setter
    def sim_params(self, params: dict):
        """
        Method to set the parameters for the active simulation model.
        """
        for k, v in params.items():
            if k in self.sim_params:
                if k == "noise":
                    self._params[k] = NoiseType(v)
                elif k == "hot_pixel_types":
                    self._params[k] = [HotPixelType(entry) for entry in v]
                else:
                    self._params[k] = v
                if isinstance(self._model, Model) and k in self._model_params:
                    self._model_params[k].value = v
            else:
                raise SimulatedDataException(f"Parameter {k} not found in {self.sim_params}.")

    def sim_get_models(self) -> list:
        """
        Method to get the all available simulation models.
        """
        return self.get_all_sim_models()

    def update_sim_state(self, signal_name: str, value: any) -> None:
        """Update the simulated state of the device.

        Args:
            signal_name (str): Name of the signal to update.
            value (any): Value to update in the simulated state.
        """
        self.sim_state[signal_name]["value"] = value
        self.sim_state[signal_name]["timestamp"] = ttime.time()

    @abstractmethod
    def _get_additional_params(self) -> dict:
        """Initialize the default parameters for the noise."""

    @abstractmethod
    def get_model_cls(self, model: str) -> any:
        """
        Method to get the class for the active simulation model_cls
        """

    @abstractmethod
    def get_params_for_model_cls(self) -> dict:
        """
        Method to get the parameters for the active simulation model.
        """

    @abstractmethod
    def get_all_sim_models(self) -> list[str]:
        """
        Method to get all names from the available simulation models.

        Returns:
            list: List of available simulation models.
        """

    @abstractmethod
    def compute_sim_state(self, signal_name: str, compute_readback: bool) -> None:
        """
        Method to compute the simulated state of the device.
        """

    def _get_table_active_simulation(self, width: int = 140) -> PrettyTable:
        """Return a table with the active simulation model and parameters."""
        table = PrettyTable()
        table.title = f"Currently active model: {self._model}"
        table.field_names = ["Parameter", "Value", "Type"]
        for k, v in self.sim_params.items():
            table.add_row([k, f"{v}", f"{type(v)}"])
        table._min_width["Parameter"] = 25 if width > 75 else width // 3
        table._min_width["Type"] = 25 if width > 75 else width // 3
        table.max_table_width = width
        table._min_table_width = width

        return table

    def _get_table_method_information(self, width: int = 140) -> PrettyTable:
        """Return a table with the information about methods."""
        table = PrettyTable()
        table.max_width["Value"] = 120
        table.hrules = 1
        table.title = "Available methods within the simulation module"
        table.field_names = ["Method", "Docstring"]

        table.add_row(
            [
                self.sim_get_models.__name__,
                f"{self.sim_get_models.__doc__}",
            ]
        )
        table.add_row([self.sim_select_model.__name__, self.sim_select_model.__doc__])
        table.add_row(["sim_params", self.__class__.sim_params.__doc__])
        table.max_table_width = width
        table._min_table_width = width
        table.align["Docstring"] = "l"

        return table

    def sim_show_all(self):
        """Returns a summary about the active simulation and available methods."""
        width = 150
        print(self._get_table_active_simulation(width=width))
        print(self._get_table_method_information(width=width))
        table = PrettyTable()
        table.title = "Simulation module for current device"
        table.field_names = ["All available models"]
        table.add_row([", ".join(self.get_all_sim_models())])
        table.max_table_width = width
        table._min_table_width = width
        print(table)


class SimulatedPositioner(SimulatedDataBase):
    """Simulated data class for a positioner."""

    def _init_default_additional_params(self) -> None:
        """No need to init additional parameters for Positioner."""

    def get_model_cls(self, model: str) -> any:
        """For the simulated positioners, no simulation models are currently implemented."""
        return None

    def get_params_for_model_cls(self) -> dict:
        """For the simulated positioners, no simulation models are currently implemented."""
        return {}

    def get_all_sim_models(self) -> list[str]:
        """
        For the simulated positioners, no simulation models are currently implemented.

        Returns:
            list: List of available simulation models.
        """
        return []

    def _get_additional_params(self) -> dict:
        """No need to add additional parameters for Positioner."""
        return {}

    def compute_sim_state(self, signal_name: str, compute_readback: bool) -> None:
        """
        For the simulated positioners, a computed signal is currently not used.
        The position is updated by the parent device, and readback/setpoint values
        have a jitter/tolerance introduced directly in the parent class (SimPositioner).
        """
        if compute_readback:
            method = None
            value = self.execute_simulation_method(method=method, signal_name=signal_name)
            self.update_sim_state(signal_name, value)


class SimulatedDataMonitor(SimulatedDataBase):
    """Simulated data class for a monitor."""

    def __init__(self, *args, parent=None, device_manager=None, **kwargs) -> None:
        self._model_lookup = self.init_lmfit_models()
        super().__init__(*args, parent=parent, device_manager=device_manager, **kwargs)
        self.bit_depth = self.parent.BIT_DEPTH
        self._init_default()

    def _get_additional_params(self) -> None:
        params = DEFAULT_PARAMS_NOISE.copy()
        params.update(DEFAULT_PARAMS_MOTOR.copy())
        return params

    def _init_default(self) -> None:
        """Initialize the default parameters for the simulated data."""
        self.sim_select_model("ConstantModel")

    def get_model_cls(self, model: str) -> any:
        """Get the class for the active simulation model."""
        if model not in self._model_lookup:
            raise SimulatedDataException(f"Model {model} not found in {self._model_lookup.keys()}.")
        return self._model_lookup[model]

    def get_all_sim_models(self) -> list[str]:
        """
        Method to get all names from the available simulation models from the lmfit.models pool.

        Returns:
            list: List of available simulation models.
        """
        return list(self._model_lookup.keys())

    def get_params_for_model_cls(self) -> dict:
        """Get the parameters for the active simulation model.

        Check if default parameters are available for lmfit parameters.

        Args:
            sim_model (str): Name of the simulation model.
        Returns:
            dict: {name: value} for the active simulation model.
        """
        rtr = {}
        params = self._model.make_params()
        for name, parameter in params.items():
            if name in DEFAULT_PARAMS_LMFIT:
                rtr[name] = DEFAULT_PARAMS_LMFIT[name]
                parameter.value = rtr[name]
            else:
                if not any([np.isnan(parameter.value), np.isinf(parameter.value)]):
                    rtr[name] = parameter.value
                else:
                    rtr[name] = 1
                    parameter.value = 1
        self._model_params = params
        return rtr

    def model_lookup(self):
        """Get available models from lmfit.models."""
        return self._model_lookup

    def init_lmfit_models(self) -> dict:
        """
        Get available models from lmfit.models.

        Exclude Gaussian2dModel, ExpressionModel, Model, SplineModel.

        Returns:
            dictionary of model name : model class pairs for available models from LMFit.
        """
        model_lookup = {}
        for name, model_cls in inspect.getmembers(models):
            try:
                is_model = issubclass(model_cls, Model)
            except TypeError:
                is_model = False
            if is_model and name not in [
                "ComplexConstantModel",
                "Gaussian2dModel",
                "ExpressionModel",
                "Model",
                "SplineModel",
            ]:
                model_lookup[name] = model_cls

        return model_lookup

    def compute_sim_state(self, signal_name: str, compute_readback: bool) -> None:
        """Update the simulated state of the device.

        It will update the value in self.sim_state with the value computed by
        the chosen simulation type.

        Args:
            signal_name (str): Name of the signal to update.
        """
        if compute_readback:
            method = self._compute
            value = self.execute_simulation_method(method=method, signal_name=signal_name)
            value = self.bit_depth(np.max(value, 0))
            self.update_sim_state(signal_name, value)

    def _compute(self, *args, **kwargs) -> int:
        """
        Compute the return value for given motor position and active model.

        Returns:
            float: Value computed by the active model.
        """
        mot_name = self.sim_params["ref_motor"]
        if self.device_manager and mot_name in self.device_manager.devices:
            motor_pos = self.device_manager.devices[mot_name].obj.read()[mot_name]["value"]
        else:
            motor_pos = 0
        method = self._model
        value = int(method.eval(params=self._model_params, x=motor_pos))
        return self._add_noise(value, self.sim_params["noise"], self.sim_params["noise_multiplier"])

    def _add_noise(self, v: int, noise: NoiseType, noise_multiplier: float) -> int:
        """
        Add the currently activated noise to the simulated data.
        If NoiseType.NONE is active, the value will be returned

        Args:
            v (int): Value to add noise to.
        Returns:
            int: Value with added noise.
        """
        if noise == NoiseType.POISSON:
            v = np.random.poisson(v)
            return v
        elif noise == NoiseType.UNIFORM:
            noise = np.ceil(np.random.uniform(0, 1) * noise_multiplier).astype(int)
            v += noise * (np.random.randint(0, 2) * 2 - 1)
            return v if v > 0 else 0
        return v


class SimulatedDataCamera(SimulatedDataBase):
    """Simulated class to compute data for a 2D camera."""

    def __init__(self, *args, parent=None, device_manager=None, **kwargs) -> None:
        self._model_lookup = self.init_2D_models()
        self._all_default_model_params = defaultdict(dict)
        self._init_default_camera_params()
        super().__init__(*args, parent=parent, device_manager=device_manager, **kwargs)
        self.bit_depth = self.parent.BIT_DEPTH
        self._init_default()

    def _init_default(self) -> None:
        """Initialize the default model for a simulated camera

        Use the default model "Gaussian".
        """
        self.sim_select_model(SimulationType2D.GAUSSIAN)

    def init_2D_models(self) -> dict:
        """
        Get the available models for 2D camera simulations.
        """
        model_lookup = {}
        for _, model_cls in inspect.getmembers(SimulationType2D):
            if isinstance(model_cls, SimulationType2D):
                model_lookup[model_cls.value] = model_cls
        return model_lookup

    def _get_additional_params(self) -> None:
        params = DEFAULT_PARAMS_NOISE.copy()
        params.update(DEFAULT_PARAMS_HOT_PIXEL.copy())
        return params

    def _init_default_camera_params(self) -> None:
        """Initiate additional params for the simulated camera."""
        self._all_default_model_params.update(
            {
                self._model_lookup[
                    SimulationType2D.CONSTANT.value
                ]: DEFAULT_PARAMS_CAMERA_CONSTANT.copy()
            }
        )
        self._all_default_model_params.update(
            {
                self._model_lookup[
                    SimulationType2D.GAUSSIAN.value
                ]: DEFAULT_PARAMS_CAMERA_GAUSSIAN.copy()
            }
        )

    def get_model_cls(self, model: str) -> any:
        """For the simulated positioners, no simulation models are currently implemented."""
        if model not in self._model_lookup:
            raise SimulatedDataException(f"Model {model} not found in {self._model_lookup.keys()}.")
        return self._model_lookup[model]

    def get_params_for_model_cls(self) -> dict:
        """For the simulated positioners, no simulation models are currently implemented."""
        return self._all_default_model_params[self._model.value]

    def get_all_sim_models(self) -> list[str]:
        """
        For the simulated positioners, no simulation models are currently implemented.

        Returns:
            list: List of available simulation models.
        """
        return [entry.value for entry in self._model_lookup.values()]

    def compute_sim_state(self, signal_name: str, compute_readback: bool) -> None:
        """Update the simulated state of the device.

        It will update the value in self.sim_state with the value computed by
        the chosen simulation type.

        Args:
            signal_name (str)       : Name of the signal to update.
            compute_readback (bool) : Flag whether to compute readback based on function hosted in SimulatedData
        """
        if compute_readback:
            if self._model == SimulationType2D.CONSTANT:
                method = "_compute_constant"
            elif self._model == SimulationType2D.GAUSSIAN:
                method = "_compute_gaussian"
            value = self.execute_simulation_method(
                signal_name=signal_name, method=getattr(self, method)
            )
        else:
            value = self._compute_empty_image()
        value = self.bit_depth(value)
        self.update_sim_state(signal_name, value)

    def _compute_empty_image(self) -> np.ndarray:
        """Computes return value for sim_type = "empty_image".

        Returns:
            float: 0
        """
        try:
            shape = self.parent.image_shape.get()
            return np.zeros(shape)
        except SimulatedDataException as exc:
            raise SimulatedDataException(
                f"Could not compute empty image for {self.parent.name} with {exc} raised. Deactivate eiger to continue."
            ) from exc

    def _compute_constant(self) -> np.ndarray:
        """Compute a return value for SimulationType2D constant."""
        try:
            shape = self.parent.image_shape.get()
            v = self.sim_params.get("amplitude") * np.ones(shape, dtype=np.float32)
            v = self._add_noise(v, self.sim_params["noise"], self.sim_params["noise_multiplier"])
            return self._add_hot_pixel(
                v,
                coords=self.sim_params["hot_pixel_coords"],
                hot_pixel_types=self.sim_params["hot_pixel_types"],
                values=self.sim_params["hot_pixel_values"],
            )
        except SimulatedDataException as exc:
            raise SimulatedDataException(
                f"Could not compute constant for {self.parent.name} with {exc} raised. Deactivate eiger to continue."
            ) from exc

    def _compute_gaussian(self) -> float:
        """Computes return value for sim_type = "gauss".

        The value is based on the parameters for the gaussian in
        self._active_params and adds noise based on the noise type.

        If computation fails, it returns 0.

        Returns: float
        """

        try:
            amp = self.sim_params.get("amplitude")
            cov = self.sim_params.get("covariance")
            cen_off = self.sim_params.get("center_offset")
            shape = self.sim_state[self.parent.image_shape.name]["value"]
            pos, offset, cov, amp = self._prepare_params_gauss(
                amp=amp, cov=cov, offset=cen_off, shape=shape
            )

            v = self._compute_multivariate_gaussian(pos=pos, cen_off=offset, cov=cov, amp=amp)
            v = self._add_noise(
                v,
                noise=self.sim_params["noise"],
                noise_multiplier=self.sim_params["noise_multiplier"],
            )
            return self._add_hot_pixel(
                v,
                coords=self.sim_params["hot_pixel_coords"],
                hot_pixel_types=self.sim_params["hot_pixel_types"],
                values=self.sim_params["hot_pixel_values"],
            )
        except SimulatedDataException as exc:
            raise SimulatedDataException(
                f"Could not compute gaussian for {self.parent.name} with {exc} raised. Deactivate eiger to continue."
            ) from exc

    def _compute_multivariate_gaussian(
        self,
        pos: np.ndarray | list,
        cen_off: np.ndarray | list,
        cov: np.ndarray | list,
        amp: float,
    ) -> np.ndarray:
        """Computes and returns the multivariate Gaussian distribution.

        Args:
            pos (np.ndarray): Position of the gaussian.
            cen_off (np.ndarray): Offset from center of image for the gaussian.
            cov (np.ndarray): Covariance matrix of the gaussian.

        Returns:
            np.ndarray: Multivariate Gaussian distribution.
        """
        if isinstance(pos, list):
            pos = np.array(pos)
        if isinstance(cen_off, list):
            cen_off = np.array(cen_off)
        if isinstance(cov, list):
            cov = np.array(cov)
        dim = cen_off.shape[0]
        cov_det = np.linalg.det(cov)
        cov_inv = np.linalg.inv(cov)
        norm = np.sqrt((2 * np.pi) ** dim * cov_det)
        # This einsum call calculates (x-mu)T.Sigma-1.(x-mu) in a vectorized
        # way across all the input variables.
        fac = np.einsum("...k,kl,...l->...", pos - cen_off, cov_inv, pos - cen_off)
        v = np.exp(-fac / 2) / norm
        v *= amp / np.max(v)
        return v

    def _prepare_params_gauss(
        self, amp: float, cov: np.ndarray, offset: np.ndarray, shape: tuple
    ) -> tuple:
        """Prepare the positions for the gaussian.

        Args:
            amp (float): Amplitude of the gaussian.
            cov (np.ndarray): Covariance matrix of the gaussian.
            offset (np.ndarray): Offset from the center of the image.
            shape (tuple): Shape of the image.
        Returns:
            tuple: Positions, offset and covariance matrix for the gaussian.
        """
        x, y = np.meshgrid(
            np.linspace(-shape[0] / 2, shape[0] / 2, shape[0]),
            np.linspace(-shape[1] / 2, shape[1] / 2, shape[1]),
        )
        pos = np.empty((*x.shape, 2))
        pos[:, :, 0] = x
        pos[:, :, 1] = y

        return pos, offset, cov, amp

    def _add_noise(self, v: np.ndarray, noise: NoiseType, noise_multiplier: float) -> np.ndarray:
        """Add noise to the simulated data.

        Args:
            v (np.ndarray): Simulated data.
            noise (NoiseType): Type of noise to add.
        """
        if noise == NoiseType.POISSON:
            v = np.random.poisson(np.round(v), v.shape)
            return v
        if noise == NoiseType.UNIFORM:
            v += np.random.uniform(-noise_multiplier, noise_multiplier, v.shape)
            v[v <= 0] = 0
            return v
        if noise == NoiseType.NONE:
            return v

    def _add_hot_pixel(
        self, v: np.ndarray, coords: list, hot_pixel_types: list, values: list
    ) -> np.ndarray:
        """Add hot pixels to the simulated data.

        Args:
            v (np.ndarray): Simulated data.
            hot_pixel (dict): Hot pixel parameters.
        """
        for coord, hot_pixel_type, value in zip(coords, hot_pixel_types, values):
            if coord[0] < v.shape[0] and coord[1] < v.shape[1]:
                if hot_pixel_type == HotPixelType.CONSTANT:
                    v[coord[0], coord[1]] = value
                elif hot_pixel_type == HotPixelType.FLUCTUATING:
                    maximum = np.max(v) if np.max(v) != 0 else 1
                    if v[coord[0], coord[1]] / maximum > 0.5:
                        v[coord[0], coord[1]] = value
        return v
