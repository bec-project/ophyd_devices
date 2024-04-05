""" This module provides a range of protocols that describe the expected interface for different types of devices.

The protocols below can be used as teamplates for functionality to be implemeted by different type of devices.
They further facilitate runtime checks on devices and provide a minimum set of properties required for a device to be loadable by BEC.

The protocols are:
- BECDeviceProtocol: Protocol for devices in BEC. All devices must at least implement this protocol.
- BECSignalProtocol: Protocol for signals.
- BECScanProtocol: Protocol for the scan interface.
- BECMixinProtocol: Protocol for utilities in particular relevant for detector implementations.
- BECPositionerProtocol: Protocol for positioners.
- BECFlyerProtocol: Protocol with for flyers.

Keep in mind, that a device of type flyer should generally also implement the BECScanProtocol that provides the required functionality for scans.
Flyers in addition, also implement the BECFlyerProtocol. Similarly, positioners should also implement the BECScanProtocol and BECPositionerProtocol.

"""

from typing import Protocol, runtime_checkable

from bec_lib.file_utils import FileWriter
from ophyd import Component, DeviceStatus, Kind, Staged

from ophyd_devices.utils import bec_scaninfo_mixin


@runtime_checkable
class BECDeviceProtocol(Protocol):
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
class BECSignalProtocol(Protocol):
    """Protocol for BEC signals with zero functionality.

    This protocol adds the specific implementation for a signal.
    Please be aware that a signal must also implement BECDeviceProtocol.

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
class BECScanProtocol(BECDeviceProtocol, Protocol):
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
class BECMixinProtocol(Protocol):
    """Protocol that offers BEC specific utility functionality for detectors."""

    USER_ACCESS: list[str]
    """
    List of methods/properties that will be exposed to the client interface in addition
    to the the already exposed signals, methods and properties.
    """

    scaninfo: bec_scaninfo_mixin
    """ 
    BEC scan info mixin class that provides an transparent Protocol to scan parameter 
    as provided by BEC. It is recommended to use this Protocol to retrieve scaninfo from Redis. 
    """

    stopped: bool
    """ 
    Flag to indicate if the device is stopped. 
    
    The stop method should set this flag to True, and i.e. stage to set it to False. 
    """

    filewriter: FileWriter
    """
    The file writer mixin main purpose is to unify and centralize the creation of 
    file paths within BEC. Therefore, we recommend devices to use the same mixin for creation of paths.
    """

    def pre_scan(self):
        """Pre-scan method is called from BEC right before executing scancore, thus
        right before the start of an acquisition.

        It can be used to trigger time critical functions from the device, which
        are prone to run into timeouts in case called too early.
        """


@runtime_checkable
class BECPositionerProtocol(Protocol):
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
        The returned DeviceStatus is marked as done once the positioner has reached the target position.
        DeviceStatus.wait() can be used to block until the move is completed.

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
class BECFlyerProtocol(BECScanProtocol, Protocol):
    """Protocol with functionality specific for flyers in BEC."""

    # def configure(self, d: dict):
    #     """Configure method of the flyer.
    #     It is an optional method, but does not need to be implemented by a flyer.
    #     Instead, stage can be used to prepare time critical operations on the device in preparation of a scan.

    #     Method to configure the flyer in preparation of a scan.

    #     Args:
    #         d (dict): Dictionary with configuration parameters, i.e. key value pairs of signal_name : value
    #     """

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


@runtime_checkable
class BECRotationProtocol(Protocol):
    """Protocol which defines functionality for a tomography stage for ophyd devices"""

    allow_mod360: Component
    """Signal to define whether mod360 operations are allowed. """

    @property
    def has_mod360(self) -> bool:
        """Property to check if the motor has mod360 option

        Returns:
            bool: True if mod360 is possible on device, False otherwise
        """

    @property
    def has_freerun(self) -> bool:
        """Property to check if the motor has freerun option

        Returns:
            bool: True if freerun is allowed, False otherwise
        """

    @property
    def valid_rotation_modes(self) -> list[str]:
        """Method to get the valid rotation modes for the implemented motor.

        Returns:
            list: List of strings with valid rotation modes
        """

    def apply_mod360(self) -> None:
        """Method to apply the modulus 360 operation on the specific device.

        Childrens should override this method
        """


@runtime_checkable
class BECEventProtocol(Protocol):
    """Protocol for events in BEC.

    This is a first draft for the event protocol introduced throughout BEC.
    It needs to be review and extended before it can be used in production.
    """

    _callbacks: dict[dict]

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
