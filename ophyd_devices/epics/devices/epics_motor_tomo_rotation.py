""" Class for EpicsMotorRecord stages for tomography purposes"""

from ophyd import EpicsMotor
from ophyd import Component
from ophyd_devices.utils import bec_utils
from abc import ABC, abstractmethod

class TomoRotation(ABC):

    def __init__(*args, parent=None, **kwargs):
        self.parent._has_mod360 = False
        self.parent._has_freerun = False

    def apply_mod360(self)->None:
        """to be overriden by children"""
        pass
    

class EpicsMotorTomoRotationError(Exception):
    """Error specific for EpicsMotorTomoRotation"""

class TomoRotationEpics(TomoRotation):

    def __init__(*args, parent=None, **kwargs):
        super().__init__(*args, parent=parent, **kwargs)
        self.parent._has_mod360 = False
        self.parent._has_freerun = False


    def apply_mod360(self)->None:
        """tbd"""
        if self.has_mod360 and self.allow_mod360.get():
            cur_val = self.user_readback.get()
            new_val = cur_val %360
            try:
                self.set_current_position(new_val)
            except Exception as exc:
                raise(exc)

    # def get_valid_rotation_modes(self) -> None:
        


class EpicsMotorTomoRotation(EpicsMotor):

    allow_mod360 = Component(
        bec_utils.ConfigSignal,
        name="allow_mod360",
        kind="config",
        config_storage_name="tomo_config",
    )

    USER_ACCESS = ["apply_mod360"]

    custom_prepare_cls = TomoRotationEpics

    def __init__(self, name:str, prefix:str, *args, tomo_rotation_config:dict=None, **kwargs):

        super().__init__(name=name, prefix=prefix, *args, **kwargs)
        self.tomo_config={'allow_mod360' : False}
        self._has_mod360 = None
        self._has_freerun = None

        #To be discussed what is the appropriate way
        [self.tomo_config.update({key : value}) for key,value in tomo_rotation_config.items() if tomo_rotation_config ]

        self.custom_prepare = self.custom_prepare_cls(parent=self)
        
    @property
    def has_mod360(self) -> bool:
        """tbd"""
        return self._has_mod360

    @has_mod360.setter
    def has_mod360(self):
        raise(f'ReadOnly Property of {self.name}')

    @property
    def has_freerun(self) -> bool:
        return self._has_freerun

    @has_freerun.setter
    def has_freerun(self):
        raise(f'ReadOnly Property of {self.name}')

    @abstractmethod
    def apply_mod360(self):
        """to be implemented"""

    def apply_mod360(self):
        self.custom_prepare.apply_mod360()

    # def get_valid_rotation_modes(self):
    #     return self.custom_prepare.get_valid_rotation_modes(self)



        






    

    





