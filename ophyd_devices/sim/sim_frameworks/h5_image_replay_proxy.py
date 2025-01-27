import h5py

# Necessary import to allow h5py to open compressed h5files.
# pylint: disable=unused-import
import hdf5plugin  # noqa: F401
import numpy as np
from ophyd import Component, Kind, Staged
from scipy.ndimage import gaussian_filter

from ophyd_devices.sim.sim_frameworks.device_proxy import DeviceProxy


class H5ImageReplayProxy(DeviceProxy):
    """This Proxy class can be used to replay images from an h5 file.

    If the number of requested images is larger than the number of available iamges,
    the images will be replayed from the beginning.

    An example for the configuration of this is device is in ophyd_devices.configs.ophyd_devices_simulation.yaml
    """

    USER_ACCESS = ["file_source", "h5_entry"]

    def __init__(self, name, *args, device_manager=None, **kwargs):
        self.h5_file = None
        self.h5_dataset = None
        self._number_of_images = None
        self._staged = Staged.no
        self._image = None
        self._index = 0
        self._file_source = ""
        self._h5_entry = ""
        super().__init__(name, *args, device_manager=device_manager, **kwargs)

    @property
    def file_source(self) -> str:
        """File source property."""
        return self._file_source

    @file_source.setter
    def file_source(self, file_source: str) -> None:
        self.config[list(self.config.keys())[0]]["file_source"] = file_source
        self._file_source = file_source

    @property
    def h5_entry(self) -> str:
        """H5 entry property."""
        return self._h5_entry

    @h5_entry.setter
    def h5_entry(self, h5_entry: str) -> None:
        self.config[list(self.config.keys())[0]]["h5_entry"] = h5_entry
        self._h5_entry = h5_entry

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
            self.file_source = self.config[list(self.config.keys())[0]]["file_source"]
        if "h5_entry" in self.config[list(self.config.keys())[0]]:
            self.h5_entry = self.config[list(self.config.keys())[0]]["h5_entry"]

    def _open_h5_file(self) -> None:
        """Opens the HDF5 file found in the file_source signal and the HDF5 dataset specified by the h5_entry signal."""
        self.h5_file = h5py.File(self.file_source, mode="r")
        self.h5_dataset = self.h5_file[self.h5_entry]
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
                f"Could not open h5file {self.file_source} or access data set {self.h5_dataset} in file"
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
                f"Could not open h5file {self.file_source} or access data set {self.h5_dataset} in file"
            ) from exc

    def _compute(self, device_name: str, *args, **kwargs) -> np.ndarray:
        """Compute the image.

        Returns:
            np.ndarray: Image.
        """
        self._load_image()
        return self._image
