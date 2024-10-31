from typing import Protocol, runtime_checkable

from ophyd import Kind


@runtime_checkable
class BECDevice(Protocol):
    """Protocol for BEC devices with zero functionality."""

    name: str
    _destroyed: bool

    @property
    def kind(self) -> Kind:
        """kind property"""

    @kind.setter
    def kind(self, value: Kind):
        """kind setter"""

    @property
    def parent(self):
        """Property to find the parent device"""

    @property
    def root(self):
        """Property to fint the root device"""

    @property
    def hints(self) -> dict:
        """hints property"""

    @property
    def connected(self) -> bool:
        """connected property.
        Check if signals are connected

        Returns:
            bool: True if connected, False otherwise
        """

    @connected.setter
    def connected(self, value: bool):
        """connected setter"""

    def describe(self) -> dict:
        """describe method

        Includes all signals of type Kind.hinted and Kind.normal.
        Override by child class with describe method

        Returns:
            dict: Dictionary with dictionaries with signal descriptions ('source', 'dtype', 'shape')
        """

    def describe_configuration(self) -> dict:
        """describe method

        Includes all signals of type Kind.config.
        Override by child class with describe_configuration method

        Returns:
            dict: Dictionary with dictionaries with signal descriptions ('source', 'dtype', 'shape')
        """

    def read_configuration(self) -> dict:
        """read_configuration method

        Override by child class with read_configuration method

        Returns:
            dict: Dictionary with nested dictionary of signals with kind.config:
            {'signal_name' : {'value' : .., "timestamp" : ..}, ...}
        """

    def read(self) -> dict:
        """read method

        Override by child class with read method

        Returns:
            dict: Dictionary with nested dictionary of signals with kind.normal or kind.hinted:
            {'signal_name' : {'value' : .., "timestamp" : ..}, ...}
        """

    def destroy(self) -> None:
        """Destroy method"""


class BECDeviceBase:
    """Base class for BEC devices with minimum functionality.

    Device will be initiated and connected,e.g. obj.connected will be True.

    """

    def __init__(self, name: str, *args, parent=None, kind=None, **kwargs):
        self.name = name
        self._connected = True
        self._destroyed = False
        self._parent = parent
        self._kind = kind if kind else Kind.normal

    @property
    def kind(self) -> Kind:
        """Kind property, stems from ophyd."""
        return self._kind

    @kind.setter
    def kind(self, value: Kind):
        """kind setter"""
        self._kind = value

    @property
    def parent(self):
        """Property to find the parent device"""
        return self._parent

    @property
    def root(self):
        """Property to fint the root device"""
        root = self
        while True:
            if root.parent is None:
                return root
            root = root.parent

    @property
    def dotted_name(self):
        """Return the dotted name"""
        names = []
        obj = self
        while obj.parent is not None:
            names.append(obj.name)
            obj = obj.parent
        return ".".join(names[::-1])

    @property
    def hints(self) -> dict:
        """hints property"""
        return {}

    @property
    def connected(self) -> bool:
        """connected property"""
        return self._connected

    @connected.setter
    def connected(self, value: bool):
        """connected setter"""
        self._connected = value

    def describe(self) -> dict:
        """describe method"""
        return {}

    def describe_configuration(self) -> dict:
        """describe_configuration method"""
        return {}

    def read(self) -> dict:
        """read method"""
        return {}

    def read_configuration(self) -> dict:
        """read_configuration method"""
        return {}

    def destroy(self) -> None:
        """destroy method"""
        self._destroyed = True
        self.connected = False
