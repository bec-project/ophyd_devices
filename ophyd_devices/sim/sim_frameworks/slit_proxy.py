import numpy as np
from scipy.ndimage import gaussian_filter

from ophyd_devices.sim.sim_data import NoiseType
from ophyd_devices.sim.sim_frameworks.device_proxy import DeviceProxy


class SlitProxy(DeviceProxy):
    """
    Simulation framework to immitate the behaviour of slits.

    This device is a proxy that is meant to override the behaviour of a SimCamera.
    You may use this to simulate the effect of slits on the camera image.

    Parameters can be configured via the DeviceConfig field in the device_config.
    The example below shows the configuration for a pinhole simulation on an Eiger detector,
    where the pinhole is defined by the position of motors samx and samy. These devices must
    exist in your config.

    To update for instance the pixel_size directly, you can directly access the DeviceConfig via
    `dev.eiger.get_device_config()` or update it `dev.eiger.set_device_config({'eiger' : {'pixel_size': 0.1}})`

    An example for the configuration of this is device is in ophyd_devices.configs.ophyd_devices_simulation.yaml
    """

    USER_ACCESS = ["enabled", "lookup", "help"]

    def __init__(self, name, *args, device_manager=None, **kwargs):
        self._gaussian_blur_sigma = 5
        super().__init__(name, *args, device_manager=device_manager, **kwargs)

    def help(self) -> None:
        """Print documentation for the SlitLookup device."""
        print(self.__doc__)

    def _compute(self, device_name: str, *args, **kwargs) -> np.ndarray:
        """
        Compute the lookup table for the simulated camera.
        It copies the sim_camera behaviour and adds a mask to simulate the effect of a pinhole.

        Args:
            device_name (str): Name of the device.
            signal_name (str): Name of the signal.

        Returns:
            np.ndarray: Lookup table for the simulated camera.
        """
        device_obj = self.device_manager.devices.get(device_name).obj
        params = device_obj.sim.params
        shape = device_obj.image_shape.get()
        params.update(
            {
                "noise": NoiseType.POISSON,
                "covariance": np.array(self.config[device_name]["covariance"]),
                "center_offset": np.array(self.config[device_name]["center_offset"]),
            }
        )
        amp = params.get("amplitude")
        cov = params.get("covariance")
        cen_off = params.get("center_offset")

        pos, offset, cov, amp = device_obj.sim._prepare_params_gauss(
            amp=amp, cov=cov, offset=cen_off, shape=shape
        )
        v = device_obj.sim._compute_multivariate_gaussian(pos=pos, cen_off=offset, cov=cov, amp=amp)
        device_pos = self.config[device_name]["pixel_size"] * pos
        valid_mask = self._create_mask(
            device_pos=device_pos,
            ref_motors=self.config[device_name]["ref_motors"],
            width=self.config[device_name]["slit_width"],
            direction=self.config[device_name]["motor_dir"],
        )
        valid_mask = self._blur_image(valid_mask, sigma=self._gaussian_blur_sigma)
        v *= valid_mask
        v = device_obj.sim._add_noise(
            v, noise=params["noise"], noise_multiplier=params["noise_multiplier"]
        )
        v = device_obj.sim._add_hot_pixel(
            v,
            coords=params["hot_pixel_coords"],
            hot_pixel_types=params["hot_pixel_types"],
            values=params["hot_pixel_values"],
        )
        return v

    def _blur_image(self, image: np.ndarray, sigma: float = 1) -> np.ndarray:
        """Blur the image with a gaussian filter.

        Args:
            image (np.ndarray): Image to be blurred.
            sigma (float): Sigma for the gaussian filter.

        Returns:
            np.ndarray: Blurred image.
        """
        return gaussian_filter(image, sigma=sigma)

    def _create_mask(
        self,
        device_pos: np.ndarray,
        ref_motors: list[str],
        width: list[float],
        direction: list[int],
    ):
        mask = np.ones_like(device_pos)
        for ii, motor_name in enumerate(ref_motors):
            motor_pos = self.device_manager.devices.get(motor_name).obj.read()[motor_name]["value"]
            edges = [motor_pos + width[ii] / 2, motor_pos - width[ii] / 2]
            mask[..., direction[ii]] = np.logical_and(
                device_pos[..., direction[ii]] > np.min(edges),
                device_pos[..., direction[ii]] < np.max(edges),
            )

        return np.prod(mask, axis=2)
