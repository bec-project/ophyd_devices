""" Class for EpicsMotorRecord rotation stages for omography applications."""

from ophyd import EpicsMotor
from ophyd import Component
from ophyd_devices.utils import bec_utils


class RotationBaseError(Exception):
    """Error specific for TomoRotationBase"""


class ReadOnlyError(RotationBaseError):
    """ReadOnly Error specific to  TomoRotationBase"""


class EpicsMotorRotationError(Exception):
    """Error specific for TomoRotationBase"""


class RotationDeviceMixin:

    def __init__(self, parent=None, **kwargs):
        """Mixin class to add rotation specific methods and properties.
        This class should not be used directly, but inherited by the children classes and implement the methods if needed.
        Args:

            parent: parent class needs to inherit from TomoRotationBase

        Methods:
        These methods need to be overridden by the children classes

            apply_mod360: Apply modulos 360 to the current position
            get_valid_rotation_modes: Get valid rotation modes for the implemented motor
        """
        super().__init__(parent=parent, **kwargs)
        self.parent = parent
        # pylint: disable=protected-access
        self.parent._has_mod360 = False
        self.parent._has_freerun = False
        self._valid_rotation_modes = []

    def apply_mod360(self) -> None:
        """Method to apply the modulus 360 operation on the specific device.

        Children classes should override this method
        """

    def get_valid_rotation_modes(self) -> list[str]:
        """Get valid rotation modes for the implemented motor

        Chilren classes should ensure that all valid rotation modes are written
        in the _valid_rotation_modes list as strings
        """
        return self._valid_rotation_modes


class EpicsMotorRotationMixin(RotationDeviceMixin):

    def __init__(self, parent=None, **kwargs):
        """Mixin class implementing rotation specific functionality and parameter for EpicsMotorRecord.

        Args:
            parent: parent class should inherit from TomoRotationBase
        """
        super().__init__(parent=parent, **kwargs)
        # pylint: disable=protected-access
        self.parent._has_mod360 = True
        self.parent._has_freerun = True
        self._valid_rotation_modes = ["target", "radiography"]

    def apply_mod360(self) -> None:
        """Apply modulos 360 to the current position using the set_current_position method of ophyd EpicsMotor."""
        if self.parent.has_mod360 and self.parent.allow_mod360.get():
            cur_val = self.parent.user_readback.get()
            new_val = cur_val % 360
            try:
                self.parent.set_current_position(new_val)
            except Exception as exc:
                error_msg = f"Failed to set net position {new_val} from {cur_val} on device {self.parent.name} with error {exc}"
                raise EpicsMotorRotationError(error_msg) from exc


class RotationBase:

    allow_mod360 = Component(
        bec_utils.ConfigSignal,
        name="allow_mod360",
        kind="config",
        config_storage_name="tomo_config",
    )

    USER_ACCESS = ["apply_mod360", "get_valid_rotation_modes"]

    custom_prepare_cls = RotationDeviceMixin

    def __init__(self, name: str, tomo_rotation_config: dict = None, **kwargs):
        self.name = name
        self.tomo_config = {"allow_mod360": False}
        self._has_mod360 = None
        self._has_freerun = None

        for k, v in tomo_rotation_config.items():
            self.tomo_config[k] = v

        self.custom_prepare = self.custom_prepare_cls(parent=self, **kwargs)
        super().__init__(name=name, **kwargs)

    @property
    def has_mod360(self) -> bool:
        """tbd"""
        return self._has_mod360

    @has_mod360.setter
    def has_mod360(self):
        raise ReadOnlyError(f"ReadOnly Property of {self.name}")

    @property
    def has_freerun(self) -> bool:
        """Property to check if the motor has freerun option"""
        return self._has_freerun

    @has_freerun.setter
    def has_freerun(self):
        """Property setter for has_freerun"""
        raise ReadOnlyError(f"ReadOnly Property of {self.name}")

    def apply_mod360(self):
        """Apply modulos 360 to the current position"""
        self.custom_prepare.apply_mod360()

    def get_valid_rotation_modes(self):
        """Get valid rotation modes for the implemented motor"""
        return self.custom_prepare.get_valid_rotation_modes()


class EpicsMotorTomoRotation(RotationBase, EpicsMotor):
    custom_prepare_cls = EpicsMotorRotationMixin
