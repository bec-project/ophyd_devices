import numpy as np
from scipy.ndimage import gaussian_filter

from collections import defaultdict
from ophyd_devices.sim.sim_data import NoiseType
from ophyd_devices.utils.bec_device_base import BECDeviceBase


class DeviceProxy(BECDeviceBase):
    """DeviceProxy class inherits from BECDeviceBase."""


class SlitLookup(DeviceProxy):
    """
    Simulation framework to immidate the behaviour of slits.

    This device is a proxy that is meant to overrides the behaviour of a SimCamera.
    You may use this to simulate the effect of slits on the camera image.

    Parameters can be configured via the deviceConfig field in the device_config.
    The example below shows the configuration for a pinhole simulation on an Eiger detector,
    where the pinhole is defined by the position of motors samx and samy. These devices must
    exist in your config.

    To update for instance the pixel_size directly, you can directly access the DeviceConfig via
    `dev.eiger.get_device_config()` or update it `dev.eiger.get_device_config({'eiger' : {'pixel_size': 0.1}})`

    slit_sim:
        readoutPriority: on_request
        deviceClass: SlitLookup
        deviceConfig:
            eiger:
                cen_off: [0, 0] # [x,y]
                cov: [[1000, 500], [200, 1000]] # [[x,x],[y,y]]
                pixel_size: 0.01
                ref_motors: [samx, samy]
                slit_width: [1, 1]
                motor_dir: [0, 1] # x:0 , y:1, z:2 coordinates
        enabled: true
        readOnly: false
    """

    USER_ACCESS = ["enabled", "lookup", "help"]

    def __init__(
        self,
        name,
        *args,
        device_manager=None,
        **kwargs,
    ):
        self.name = name
        self.device_manager = device_manager
        self.config = None
        self._lookup = defaultdict(dict)
        self._gaussian_blur_sigma = 5
        super().__init__(name, *args, **kwargs)

    def help(self) -> None:
        """Print documentation for the SlitLookup device."""
        print(self.__doc__)

    def _update_device_config(self, config: dict) -> None:
        """Update the config from the device_config for the pinhole lookup table.

        Args:
            config (dict): Config dictionary.
        """
        self.config = config
        self._compile_lookup()

    @property
    def lookup(self):
        """lookup property"""
        return self._lookup

    @lookup.setter
    def lookup(self, update: dict) -> None:
        """lookup setter"""
        self._lookup.update(update)

    def _compile_lookup(self):
        """Compile the lookup table for the simulated camera."""
        for device_name in self.config.keys():
            self._lookup[device_name] = {
                # "obj": self,
                "method": self._compute,
                "args": (device_name,),
                "kwargs": {},
            }

    def _compute(self, device_name: str, *args, **kwargs) -> np.ndarray:
        """
        Compute the lookup table for the simulated camera.
        It copies the sim_camera bevahiour and adds a mask to simulate the effect of a pinhole.

        Args:
            device_name (str): Name of the device.

        Returns:
            np.ndarray: Lookup table for the simulated camera.
        """
        device_obj = self.device_manager.devices.get(device_name).obj
        params = device_obj.sim._all_params.get("gauss")
        shape = device_obj.image_shape.get()
        params.update(
            {
                "noise": NoiseType.POISSON,
                "cov": np.array(self.config[device_name]["cov"]),
                "cen_off": np.array(self.config[device_name]["cen_off"]),
            }
        )

        pos, offset, cov, amp = device_obj.sim._prepare_params_gauss(params, shape)
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
        v = device_obj.sim._add_noise(v, params["noise"])
        v = device_obj.sim._add_hot_pixel(v, params["hot_pixel"])
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


if __name__ == "__main__":
    # Example usage
    pinhole = SlitLookup(name="pinhole", device_manager=None)
    pinhole.describe()
    print(pinhole)
