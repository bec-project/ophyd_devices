from typing import Protocol, runtime_checkable


@runtime_checkable
class BECDeviceBase(Protocol):
    """Base class for BEC devices with zero functionality."""

    name: str
    _destroyed: bool

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
