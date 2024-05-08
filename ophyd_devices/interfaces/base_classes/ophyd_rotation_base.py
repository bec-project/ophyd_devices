from abc import ABC, abstractmethod

from bec_lib import bec_logger
from ophyd import Component as Cpt
from ophyd import EpicsMotor
from typeguard import typechecked

from ophyd_devices.interfaces.protocols.bec_protocols import BECRotationProtocol
from ophyd_devices.utils.bec_utils import ConfigSignal

logger = bec_logger.logger


class OphtyRotationBaseError(Exception):
    """Exception specific for implmenetation of rotation stages."""


class OphydRotationBase(BECRotationProtocol, ABC):

    allow_mod360 = Cpt(ConfigSignal, name="allow_mod360", value=False, kind="config")

    def __init__(self, *args, **kwargs):
        """
        Base class to implement functionality specific for rotation devices.

        Childrens should override the instance attributes:
        - has_mod360
        - has_freerun
        - valid_rotation_modes

        """
        # pylint: disable=protected-access
        self._has_mod360 = False
        self._has_freerun = False
        self._valid_rotation_modes = []
        if "allow_mod360" in kwargs:
            if not isinstance(kwargs["allow_mod360"], bool):
                raise ValueError("allow_mod360 must be a boolean")
            self.allow_mod360.put(kwargs["allow_mod360"])
        super().__init__(*args, **kwargs)

    @abstractmethod
    def apply_mod360(self) -> None:
        """Method to apply the modulus 360 operation on the specific device.

        Childrens should override this method
        """

    @property
    def has_mod360(self) -> bool:
        """Property to check if the device has mod360 operation.

        ReadOnly property, childrens should override this method.
        """
        return self._has_mod360

    @property
    def has_freerun(self) -> bool:
        """Property to check if the device has freerun operation.

        ReadOnly property, childrens should override this method.
        """
        return self._has_freerun

    @property
    def valid_rotation_modes(self) -> list:
        """Method to get the valid rotation modes for the specific device."""
        return self._valid_rotation_modes

    @typechecked
    @valid_rotation_modes.setter
    def valid_rotation_modes(self, value: list[str]):
        """Method to set the valid rotation modes for the specific device."""
        self._valid_rotation_modes = value
        return self._valid_rotation_modes


# pylint: disable=too-many-ancestors
class EpicsRotationBase(OphydRotationBase, EpicsMotor):
    """Class for Epics rotation devices."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._has_freerun = True
        self._has_freerun = True
        self._valid_rotation_modes = ["target", "radiography"]

    def apply_mod360(self) -> None:
        """Apply modulos 360 operation for EpicsMotorRecord.

        EpicsMotor has the function "set_current_position" which can be used for this purpose.
        In addition, there is a check if mod360 is allowed and available.
        """
        if self.has_mod360 and self.allow_mod360.get():
            cur_val = self.user_readback.get()
            new_val = cur_val % 360
            try:
                self.set_current_position(new_val)
            except Exception as exc:
                error_msg = f"Failed to set new position {new_val} from {cur_val} on device {self.name} with error {exc}"
                raise OphtyRotationBaseError(error_msg) from exc
            return
        logger.info(
            f"Did not apply mod360 for device {self.name} with has_mod={self.has_mod360} and allow_mod={self.allow_mod360.get()}"
        )
