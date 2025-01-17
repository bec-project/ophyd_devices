from abc import ABC, abstractmethod
from collections import defaultdict

from ophyd_devices.utils.bec_device_base import BECDeviceBase


class DeviceProxy(BECDeviceBase, ABC):
    """DeviceProxy class inherits from BECDeviceBase.

    It is an abstract class that is meant to be used as a base class for all device proxies.
    The minimum requirement for a device proxy is to implement the _compute method.
    """

    def __init__(self, name, *args, device_manager=None, **kwargs):
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
