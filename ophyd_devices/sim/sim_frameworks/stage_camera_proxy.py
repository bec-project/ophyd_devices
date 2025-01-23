import base64
import io
import os
from typing import TYPE_CHECKING, SupportsFloat

import numpy as np
from bec_lib import bec_logger
from ophyd import PositionerBase, Staged

from ophyd_devices.sim.sim_camera import SimCamera
from ophyd_devices.sim.sim_frameworks.assets.default_image import DEFAULT_IMAGE
from ophyd_devices.sim.sim_frameworks.device_proxy import DeviceProxy

try:
    from PIL import Image
except ImportError as e:
    raise Exception(
        "PIL/pillow is not available - please install ophyd_devices with dev dependencies to enable this simulation"
    ) from e
logger = bec_logger.logger


class StageCameraProxy(DeviceProxy):
    """This Proxy class scans an ROI over an image based on some positioners, as if
    a stage was being moved in front of some camera. The sample config expects positioners
    samx and samy to exist in the device manager."""

    def __init__(self, name, *args, device_manager=None, **kwargs):
        self._file_source = (
            ""  # absolute path to an image file to use, or by default use the file from ./assets
        )
        self._staged = Staged.no
        self._roi_fraction: float = 0.15
        self._image: Image.Image | None = None
        self._shape: tuple[int, int] | None = None
        self._name = name

        self._x_roi_fraction: float
        self._y_roi_fraction: float
        self._image_size: tuple[int, int]
        self._motors: tuple[PositionerBase, PositionerBase]

        super().__init__(name, *args, device_manager=device_manager, **kwargs)

    def _validate_motors_from_config(self):
        ref_motors: tuple[list[str], ...] = self.config[self._device_name]["ref_motors"]
        logger.debug(f"using reference_motors {ref_motors} for camera view simulation")
        ref_motor_0 = self.device_manager.devices.get(ref_motors[0]).obj
        ref_motor_1 = self.device_manager.devices.get(ref_motors[1]).obj
        if ref_motor_0 is None:
            raise ValueError(f"{self._name}: device {ref_motor_0} doesn't exist in device manager")
        elif ref_motor_1 is None:
            raise ValueError(f"{self._name}: device {ref_motor_1} doesn't exist in device manager")
        else:
            self._motors: tuple[PositionerBase, PositionerBase] = (ref_motor_0, ref_motor_1)

    def _update_device_config(self, config: dict) -> None:
        super()._update_device_config(config)
        if len(self.config.keys()) > 1:
            raise RuntimeError(
                f"The current implementation of device {self.name} can only replay data for a single device. The config has information about multiple devices {config.keys()}"
            )
        logger.debug(f"{self._name} received config: {self.config}")
        self._device_name = list(self.config.keys())[0]
        roi_fraction = self.config[self._device_name].get("roi_fraction")
        if roi_fraction is not None:
            logger.debug(f"Updating roi_fraction on {self._name} to {roi_fraction}")
            if not isinstance(roi_fraction, SupportsFloat):
                raise ValueError('"roi_fraction" must be a number!')
            self._roi_fraction = roi_fraction

        self._validate_motors_from_config()

    def stop(self) -> None:
        """Stop the device."""
        ...

    def stage(self) -> list[object]:
        """Stage the device; loads the image from file."""
        self._device: SimCamera = self.device_manager.devices.get(self._device_name).obj
        self._shape = self._device.image_shape.get()
        shape_aspect_ratio = self._shape[0] / self._shape[1]
        if self._staged != Staged.no:
            return [self]
        try:
            self._load_image()
        except Exception as exc:
            raise type(e)(
                f"{self._name}: Could not open image file {self._file_source}, relative to {os.getcwd()}"
            ) from exc
        w, h = self._image.size
        self._x_roi_fraction = self._roi_fraction
        self._y_roi_fraction = h / w * self._roi_fraction / shape_aspect_ratio
        self._staged = Staged.yes
        return [self]

    def unstage(self) -> list[object]:
        """Unstage the device"""
        self._image = None
        self._staged = Staged.no
        return [self]

    def _load_image(self):
        """Try loading the image from the filesystem"""
        try:
            if self._file_source == "":
                logger.debug(f"{self._name} is using the default image")
                self._image = Image.open(io.BytesIO((base64.b64decode(DEFAULT_IMAGE))))
            else:
                self._image = Image.open(self.file_source)
            self._image.load()
        except Exception as e:
            raise type(e)(
                f"Make sure you have set the image path in the device config for {self._name}: - currently it is '{self._file_source}'"
            ) from e

    def _compute(self, *args, **kwargs):
        """Compute the image.

        Returns:
            np.ndarray: Image.
        """
        logger.debug("{self._name}: compute called.")

        if self._staged == Staged.no:
            logger.debug("")
            return np.zeros((*self._shape, 3))
        elif self._image is None:
            raise ValueError(
                f"{self._name}: Something went wrong - expected an image to have been loaded"
            )

        def get_positioner_fraction_along_limits(positioner: PositionerBase):
            if (limits := positioner.limits) == [0, 0] or limits[0] == limits[1]:
                raise ValueError(
                    f"Device {positioner} must have limits set to be used as an axis for the camera view simulation"
                )
            return (positioner.position - limits[0]) / (limits[1] - limits[0])

        x, y = (get_positioner_fraction_along_limits(m) for m in self._motors)
        w, h = self._image.size

        # x increases rightwards from the image origin
        cropped_x_min_px = x * (1 - self._x_roi_fraction) * w
        cropped_x_max_px = (x * (1 - self._x_roi_fraction) + self._x_roi_fraction) * w
        # y increases downard from the image origin
        cropped_y_min_px = h - (y * (1 - self._y_roi_fraction) * h)
        cropped_y_max_px = h - ((y * (1 - self._y_roi_fraction) + self._y_roi_fraction) * h)

        cropped_image = self._image.crop(
            (cropped_x_min_px, cropped_y_max_px, cropped_x_max_px, cropped_y_min_px)
        )
        scaled_image = cropped_image.resize(self._shape)

        return np.array(scaled_image)
