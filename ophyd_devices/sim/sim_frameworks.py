import numpy as np

from scipy.ndimage import gaussian_filter

from collections import defaultdict
from ophyd_devices.sim.sim_data import NoiseType


class PinholeLookup:
    """Pinhole lookup table for simulated devices.

    When activated, it will create a lookup table for a simulated camera based on the config.
    The lookup table will be used to simulate the effect of a pinhole on the camera image.
    An example config is shown below, for the dev.eiger, with dev.samx and dev.samy as reference motors.

    eiger:
        cen_off: [0, 0] # [x,y]
        cov: [[1000, 500], [200, 1000]] # [[x,x],[y,y]]
        pixel_size: 0.01
        signal: image
        ref_motors: [samx, samy]
        slit_width: [1, 2]
        motor_dir: [0, 1] # x:0 , y:1, z:2 coordinates
    """

    def __init__(
        self,
        *args,
        name,
        device_manager=None,
        config: dict = None,
        **kwargs,
    ):
        self.name = name
        self.device_manager = device_manager
        self.config = config
        self._enabled = True
        self._lookup = defaultdict(dict)
        self._gaussian_blur_sigma = 8
        self._compile_lookup()

    @property
    def lookup(self):
        """lookup property"""
        return (
            self._lookup
            if getattr(self.device_manager.devices, self.name).enabled is True
            else None
        )

    def _compile_lookup(self):
        """Compile the lookup table for the simulated camera."""
        for device_name in self.config.keys():
            self.lookup[device_name] = {
                "obj": self,
                "method": self._compute,
                "args": {},
                "kwargs": {"device_name": device_name},
            }

    def _compute(self, *args, device_name: str = None, **kwargs) -> np.ndarray:
        """
        Compute the lookup table for the simulated camera.
        It copies the sim_camera bevahiour and adds a mask to simulate the effect of a pinhole.

        Args:
            device_name (str): Name of the device.

        Returns:
            np.ndarray: Lookup table for the simulated camera.
        """
        device_obj = self.device_manager.devices.get(device_name)
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
            dir=self.config[device_name]["motor_dir"],
        )
        valid_mask = self._blur_image(valid_mask, sigma=self._gaussian_blur_sigma)
        v *= valid_mask
        v = device_obj.sim._add_noise(v, params["noise"])
        v = device_obj.sim._add_hot_pixel(v, params["hot_pixel"])
        return v

    def _blur_image(self, image: np.ndarray, sigma: float = 5) -> np.ndarray:
        """Blur the image with a gaussian filter.

        Args:
            image (np.ndarray): Image to be blurred.
            sigma (float): Sigma for the gaussian filter.

        Returns:
            np.ndarray: Blurred image.
        """
        return gaussian_filter(image, sigma=sigma)

    def _create_mask(
        self, device_pos: np.ndarray, ref_motors: list[str], width: list[float], dir: list[int]
    ):
        mask = np.ones_like(device_pos, dtype=bool)
        for ii, motor_name in enumerate(ref_motors):
            motor_pos = self.device_manager.devices.get(motor_name).read()[motor_name]["value"]
            edges = [motor_pos + width[ii] / 2, motor_pos - width[ii] / 2]
            mask[..., dir[ii]] = np.logical_and(
                device_pos[..., dir[ii]] > np.min(edges), device_pos[..., dir[ii]] < np.max(edges)
            )

        return np.prod(mask, axis=2)
