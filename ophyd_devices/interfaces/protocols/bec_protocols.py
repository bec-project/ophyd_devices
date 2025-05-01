"""This module provides a range of protocols that describe the expected
interface for different types of devices.

The protocols below can be used as teamplates for functionality to be implemeted
by different type of devices. They further facilitate runtime checks on devices
and provide a minimum set of properties required for a device to be loadable by BEC.

The protocols are:
- BECBaseProtocol: Protocol for devices in BEC. All devices must at least implement this protocol.
- BECSignalProtocol: Protocol for signals.
- BECDeviceProtocol: Protocol for the scan interface.
- BECMixinProtocol: Protocol for utilities in particular relevant for detector implementations.
- BECPositionerProtocol: Protocol for positioners.
- BECFlyerProtocol: Protocol with for flyers.

Keep in mind, that a device of type flyer should generally also implement the BECDeviceProtocol
with the functionality needed for scans. In addition, flyers also implement the BECFlyerProtocol.
Similarly, positioners should also implement the BECDeviceProtocol and BECPositionerProtocol.

"""

from typing import Protocol, runtime_checkable

from ophyd import DeviceStatus, Kind, Staged


@runtime_checkable
class BECBaseProtocol(Protocol):
    """Protocol for ophyd objects with zero functionality."""

    _destroyed: bool

    @property
    def name(self) -> str:
        """name property"""

    @name.setter
    def name(self, value: str) -> None:
        """name setter"""

    @property
    def kind(self) -> Kind:
        """kind property"""

    @kind.setter
    def kind(self, value: Kind):
        """kind setter"""

    @property
    def parent(self) -> object:
        """Property to find the parent device"""

    @property
    def root(self) -> object:
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

    @property
    def event_types(self) -> tuple[str]:
        """Event types property"""

    def _run_subs(self, sub_type: str, **kwargs):
        """Run subscriptions for the event.

        Args:
            sub_type: Subscription type
            kwargs: Keyword arguments
        """

    def subscribe(self, callback: callable, event_type: str = None, run: bool = True):
        """Subscribe to the event.

        Args:
            callback (callable) :   Callback function
                                    The expected callback structure is:
                                    def cb(*args, obj:OphydObject, sub_type:str, **kwargs) -> None:
                                        pass
            event_type (str)    :   Event type, if None it defaults to obj._default_sub
                                    This maps to sub_type in _run_subs
            run (bool)          :   If true, run the callback directly.

        Returns:
            cid (int):              Callback id
        """

    def clear_sub(self, cb: callable, event_type: str = None):
        """Clear subscription, given the origianl callback fucntion

        Args:
            cb (callable)   : Callback
            event_type (str): Event type, if None it will be remove from all event_types
        """

    def unsubscribe(self, cid: int):
        """Unsubscribe from the event.

        Args:
            cid (int): Callback id
        """

    def read(self) -> dict:
        """read method

        Override by child class with read method

        Returns:
            dict: Dictionary with nested dictionary of signals with kind.normal or kind.hinted:
            {'signal_name' : {'value' : .., "timestamp" : ..}, ...}
        """

    def read_configuration(self) -> dict:
        """read_configuration method

        Override by child class with read_configuration method

        Returns:
            dict: Dictionary with nested dictionary of signals with kind.config:
            {'signal_name' : {'value' : .., "timestamp" : ..}, ...}
        """

    def describe(self) -> dict:
        """describe method

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

    def destroy(self) -> None:
        """Destroy method.

        _destroyed must be set to True after calling destroy.
        """

    def trigger(self) -> DeviceStatus:
        """Trigger method on the device

        Returns ophyd DeviceStatus object, which is used to track the status of the trigger.
        It can also be blocking until the trigger is completed, and return the status object
        with set_finished() method called on the DeviceStatus.
        """


@runtime_checkable
class BECSignalProtocol(BECBaseProtocol, Protocol):
    """Protocol for BEC signals with zero functionality.

    This protocol adds the specific implementation for a signal.
    Please be aware that a signal must also implement BECBaseProtocol.

    Note: Currently the implementation of the protocol is not taking into account the
    event_model from ophyd, i.e. _run_sbus
    """

    @property
    def limits(self) -> tuple[float, float]:
        """Limits property for signals.
        If low_limit == high_limit, it is equivalent to NO limits!

        Returns:
            tuple: Tuple with lower and upper limits
        """

    @property
    def high_limit(self) -> float:
        """High limit property for signals.

        Returns:
            float: Upper limit
        """

    @property
    def low_limit(self) -> float:
        """Low limit property for signals.

        Returns:
            float: Lower limit
        """

    @property
    def write_access(self) -> bool:
        """Write access method for signals.

        Returns:
            bool: True if write access is allowed, False otherwise
        """

    def check_value(self, value: float) -> None:
        """Check whether value is within limits

        Args:
            value: value to check

        Raises:
            LimitError in case the requested motion is not inside of limits.
        """

    def put(self, value: any, force: bool = False, timeout: float = None):
        """Put method for signals.
        This method should resolve immediately and not block.
        If not force, the method checks if the value is within limits using check_value.


        Args:
            value (any)     : value to put
            force (bool)    : Flag to force the put and ignore limits
            timeout (float) : Timeout for the put
        """

    def set(self, value: any, timeout: float = None) -> DeviceStatus:
        """Set method for signals.
        This method should be blocking until the set is completed.

        Args:
            value (any)     : value to set
            timeout (float) : Timeout for the set

        Returns:
            DeviceStatus    : DeviceStatus object that will finish upon return
        """


@runtime_checkable
class BECDeviceProtocol(BECBaseProtocol, Protocol):
    """Protocol for devices offering an Protocol with all relevant functionality for scans.

    In BEC, scans typically follow the order of stage, (pre_scan), trigger, unstage.
    Stop should be used to interrupt a scan. Be aware that pre_scan is optional and therefor
    part of the BECMixinProtocol, typically useful for more complex devices such as detectors.

    This protocol allows to perform runtime checks on devices of ophyd.
    It is the minimum set of properties required for a device to be loadable by BEC.
    """

    _staged: Staged
    """Staged property to indicate if the device is staged."""

    def stage(self) -> list[object]:
        """Stage method to prepare the device for an upcoming acquistion.

        This prepares a device for an upcoming acquisition, i.e. it is the first
        method for which the scan parameters are known and the device can be configured.

        It can be used to move scan_motors to their start position
        or also prepare DAQ systems for the upcoming measurement.
        We can further publish the file location for DAQ systems
        to BEC and inform BEC's file writer where data will be written to.

        Stagin is not idempotent. If called twice without an unstage it should raise.
        For ophyd devices, one may used self._staged = True to check if the device is staged.

        Returns:
            list:   List of objects that were staged, i.e. [self]
                    For devices with inheritance from ophyd, return
                    return super().stage() in the child class.
        """

    def unstage(self) -> list[object]:
        """Unstage method to cleanup after the acquisition.

        It can also be used to implement checks whether the acquisition was successful,
        inform BEC that the file has been succesfully written, or raise upon receiving
        feedback that the scan did not finish successful.

        Unstaging is not idempotent. If called twice it should simply resolve.
        It is recommended to return super().unstage() in the child class, if
        the child class also inherits from ophyd repository.
        """

    def stop(self, success: bool) -> None:
        """Stop method to stop the device.

        Args:
            success: Flag to indicate if the scan was successful or not.

        This method should be called to stop the device. It is recommended to call
        super().stop(success=success) if class inherits from ophyd repository.
        """


@runtime_checkable
class BECPositionerProtocol(BECDeviceProtocol, Protocol):
    """Protocol with functionality specific for positioners in BEC."""

    @property
    def limits(self) -> tuple[float, float]:
        """Limits property for positioners.
        For an EpicsMotor, BEC will automatically recover the limits from the IOC.

        If not set, it returns (0,0).
        Note, low_limit = high_limit is equivalent to NO limits!

        Returns:
            tuple: Tuple with lower and upper limits
        """

    @property
    def low_limit(self) -> float:
        """Low limit property for positioners.

        Returns:
            float: Lower limit
        """

    @property
    def high_limit(self) -> float:
        """High limit property for positioners.

        Returns:
            float: Upper limit
        """

    def check_value(self, value: float) -> None:
        """Check whether value is within limits

        Args:
            value: value to check

        Raises:
            LimitError in case the requested motion is not inside of limits.
        """

    def move(self, position: float) -> DeviceStatus:
        """Move method for positioners.
        The returned DeviceStatus is marked as done once the positioner has reached the target
        position. DeviceStatus.wait() can be used to block until the move is completed.

        Args:
            position: position to move to

        Returns:
            DeviceStatus: DeviceStatus object
        """

    def set(self, position: float) -> DeviceStatus:
        """Set method for positioners.

        In principle, a set command is the same as move. This comes from ophyd upstream.
        We will have to review whether BEC requires both.

        Args:
            position: position to move to

        Returns:
            DeviceStatus: DeviceStatus object
        """


@runtime_checkable
class BECFlyerProtocol(BECDeviceProtocol, Protocol):
    """Protocol with functionality specific for flyers in BEC."""

    def kickoff(self) -> DeviceStatus:
        """Kickoff method for flyers.

        The returned DeviceStatus is marked as done once the flyer start flying,
        i.e. is ready to be triggered.

        Returns:
            DeviceStatus: DeviceStatus object
        """

    def complete(self) -> DeviceStatus:
        """Complete method for flyers.

        The returned DeviceStatus is marked as done once the flyer has completed.

        Returns:
            DeviceStatus: DeviceStatus object
        """
