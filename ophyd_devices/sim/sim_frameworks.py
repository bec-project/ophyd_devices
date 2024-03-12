import numpy as np
from scipy.ndimage import gaussian_filter
from abc import ABC, abstractmethod

import h5py
import hdf5plugin

from ophyd import Staged, Kind

from collections import defaultdict
from ophyd_devices.sim.sim_data import NoiseType
from ophyd_devices.sim.sim_signals import CustomSetableSignal
from ophyd_devices.utils.bec_device_base import BECDeviceBase


class DeviceProxy(BECDeviceBase, ABC):
    """DeviceProxy class inherits from BECDeviceBase.

    It is an abstract class that is meant to be used as a base class for all device proxies.
    The minimum requirement for a device proxy is to implement the _compute method.
    """

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
        super().__init__(name, *args, device_manager=device_manager, **kwargs)
        self._signals = dict()

    @property
    def lookup(self):
        """lookup property"""
        return self._lookup

    @lookup.setter
    def lookup(self, update: dict) -> None:
        """lookup setter"""
        self._lookup.update(update)

    def _update_device_config(self, config: dict) -> None:
        """
        BEC will call this method on every object upon initializing devices to pass over the deviceConfig
        from the config file. It can be conveniently be used to hand over initial parameters to the device.

        Args:
            config (dict): Config dictionary.
        """
        self.config = config
        self._compile_lookup()

    def _compile_lookup(self):
        """Compile the lookup table for the device."""
        for device_name in self.config.keys():
            self._lookup[device_name] = {
                "method": self._compute,
                "signal_name": self.config[device_name]["signal_name"],
                "args": (device_name,),
                "kwargs": {},
            }

    @abstractmethod
    def _compute(self, device_name: str, *args, **kwargs) -> any:
        """
        The purpose of this method is to compute the readback value for the signal of the device
        that this proxy is attached to. This method is meant to be overriden by the user.
        P

        Args:
            device_name (str): Name of the device.

        Returns:
        """


class SlitProxy(DeviceProxy):
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
        readoutPriority: baseline
        deviceClass: SlitProxy
        deviceConfig:
            eiger:
                signal_name: image
                center_offset: [0, 0] # [x,y]
                covariance: [[1000, 500], [200, 1000]] # [[x,x],[y,y]]
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
        self._gaussian_blur_sigma = 5
        super().__init__(name, *args, device_manager=device_manager, **kwargs)

    def help(self) -> None:
        """Print documentation for the SlitLookup device."""
        print(self.__doc__)

    def _compute(self, device_name: str, *args, **kwargs) -> np.ndarray:
        """
        Compute the lookup table for the simulated camera.
        It copies the sim_camera bevahiour and adds a mask to simulate the effect of a pinhole.

        Args:
            device_name (str): Name of the device.
            signal_name (str): Name of the signal.

        Returns:
            np.ndarray: Lookup table for the simulated camera.
        """
        device_obj = self.device_manager.devices.get(device_name).obj
        params = device_obj.sim.sim_params
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


class H5ImageReplayProxy(DeviceProxy):
    """This Proxy class can be used to replay images from an h5 file.

    If the number of requested images is larger than the number of available iamges, the images will be replayed from the beginning.

    h5_image_sim:
        readoutPriority: baseline
        deviceClass: H5ImageReplayProxy
        deviceConfig:
            eiger:
                signal_name: image
                file_source: /path/to/h5file.h5
                h5_entry: /entry/data
        enabled: true
        readOnly: false
    """

    USER_ACCESS = ["file_source", "h5_entry"]

    def __init__(
        self,
        name,
        *args,
        device_manager=None,
        **kwargs,
    ):
        self.h5_file = None
        self.h5_dataset = None
        self._number_of_images = None
        self._staged = Staged.no
        self._image = None
        self._index = 0
        super().__init__(name, *args, device_manager=device_manager, **kwargs)
        self.file_source = CustomSetableSignal(
            name="file_source", value="", parent=self, kind=Kind.normal
        )
        self.h5_entry = CustomSetableSignal(
            name="h5_entry", value="", parent=self, kind=Kind.normal
        )

    @property
    def component_names(self) -> list[str]:
        """Return the names of the components."""
        return ["file_source", "h5_entry"]

    def _update_device_config(self, config: dict) -> None:
        super()._update_device_config(config)
        if len(config.keys()) > 1:
            raise RuntimeError(
                f"The current implementation of device {self.name} can only replay data for a single device. The config has information about multiple devices {config.keys()}"
            )
        self._init_signals()

    def _init_signals(self):
        """Initialize the signals for the device."""
        if "file_source" in self.config[list(self.config.keys())[0]]:
            self.file_source.set(self.config[list(self.config.keys())[0]]["file_source"])
        if "h5_entry" in self.config[list(self.config.keys())[0]]:
            self.h5_entry.set(self.config[list(self.config.keys())[0]]["h5_entry"])

    def _open_h5_file(self) -> None:
        """Opens the HDF5 file found in the file_source signal and the HDF5 dataset specified by the h5_entry signal."""
        self.h5_file = h5py.File(self.file_source.get(), mode="r")
        self.h5_dataset = self.h5_file[self.h5_entry.get()]
        self._number_of_images = self.h5_dataset.shape[0]

    def _close_h5_file(self) -> None:
        """Close the HDF5 file."""
        self.h5_file.close()

    def stop(self) -> None:
        """Stop the device."""
        if self.h5_file:
            self._close_h5_file()
        self.h5_file = None
        self.h5_dataset = None
        self._number_of_images = None
        self._index = 0

    def stage(self) -> list[object]:
        """Stage the device.
        This opens the HDF5 dataset, unstaging will close it.
        """

        if self._staged != Staged.no:
            return [self]
        try:
            self._open_h5_file()
        except Exception as exc:
            if self.h5_file:
                self.stop()
            raise FileNotFoundError(
                f"Could not open h5file {self.file_source.get()} or access data set {self.h5_dataset.get()} in file"
            ) from exc

        self._staged = Staged.yes
        return [self]

    def unstage(self) -> list[object]:
        """Unstage the device, also closes the HDF5 dataset"""
        if self.h5_file:
            self.stop()
        self._staged = Staged.no
        return [self]

    def _load_image(self):
        """Try loading the image from the h5 dataset, and set it to self._image."""
        if self.h5_file:
            slice_nr = self._index % self._number_of_images
            self._index = self._index + 1
            self._image = self.h5_dataset[slice_nr, ...]
            return
        try:
            self.stage()
            slice_nr = self._index % self._number_of_images
            self._index = self._index + 1
            self._image = self.h5_dataset[slice_nr, ...]
            self.unstage()
        except Exception as exc:
            raise FileNotFoundError(
                f"Could not open h5file {self.file_source.get()} or access data set {self.h5_dataset.get()} in file"
            ) from exc

    def _compute(self, device_name: str, *args, **kwargs) -> np.ndarray:
        """Compute the image.

        Returns:
            np.ndarray: Image.
        """
        self._load_image()
        return self._image


if __name__ == "__main__":
    # Example usage
    tmp = H5ImageReplayProxy(name="tmp", device_manager=None)
    config = {
        "eiger": {
            "signal_name": "image",
            "file_source": "/Users/appel_c/switchdrive/Sharefolder/AgBH_2D_gridscan/projection_000006_data_000001.h5",
            "h5_entry": "/entry/data/data",
        }
    }
    tmp._update_device_config(config)
    tmp.stage()
    print(tmp)
