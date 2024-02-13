class BECDeviceBase:
    """Base class for BEC devices with zero functionality."""

    def __init__(self, name: str, *args, **kwargs):
        self.name = name
        self._connected = True
        self._destroyed = False

    @property
    def hints(self):
        """hints property"""
        return {}

    @property
    def connected(self) -> bool:
        """connected property.
        Check if signals are connected

        Returns:
            bool: True if connected, False otherwise
        """
        return self._connected

    @connected.setter
    def connected(self, value: bool):
        """connected setter"""
        self._connected = value

    def describe(self) -> dict:
        """describe method

        Includes all signals of type Kind.hinted and Kind.normal.
        Override by child class with describe method

        Returns:
            dict: Dictionary with dictionaries with signal descriptions ('source', 'dtype', 'shape')
        """
        return {}

    def describe_configuration(self) -> dict:
        """describe method

        Includes all signals of type Kind.config.
        Override by child class with describe_configuration method

        Returns:
            dict: Dictionary with dictionaries with signal descriptions ('source', 'dtype', 'shape')
        """
        return {}

    def read_configuration(self) -> dict:
        """read_configuration method

        Override by child class with read_configuration method

        Returns:
            dict: Dictionary with nested dictionary of signals with kind.config:
            {'signal_name' : {'value' : .., "timestamp" : ..}, ...}
        """
        return {}

    def read(self) -> dict:
        """read method

        Override by child class with read method

        Returns:
            dict: Dictionary with nested dictionary of signals with kind.normal or kind.hinted:
            {'signal_name' : {'value' : .., "timestamp" : ..}, ...}
        """
        return {}

    def destroy(self):
        """Destroy method"""
        self._destroyed = True
