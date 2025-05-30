"""
Module for custom BEC signals, that wrap around ophyd.Signal.
These signals emit BECMessage objects, which comply with the BEC message system.
"""

from typing import Any, Callable, Literal, Type

import numpy as np
from bec_lib import messages
from ophyd import DeviceStatus, Kind, Signal
from pydantic import ValidationError
from typeguard import typechecked

# pylint: disable=arguments-differ
# pylint: disable=arguments-renamed
# pylint: disable=too-many-arguments
# pylint: disable=signature-differs


class BECMessageSignal(Signal):
    """
    Custom signal class that accepts BECMessage objects as values.
    Dictionaries are also accepted if convertible to the correct BECMessage type.
    """

    def __init__(
        self,
        name: str,
        *,
        bec_message_type: Type[messages.BECMessage],
        value: messages.BECMessage | dict | None = None,
        kind: Kind | str = Kind.omitted,
        signal_metadata: dict | None = None,
        **kwargs,
    ):
        """
        Create a new BECMessageSignal object.

        Args:
            name (str)                          : The name of the signal.
            bec_message_type: type[BECMessage]  : The type of BECMessage to accept as values.
            value (BECMessage | dict | None)    : The value of the signal. Defaults to None.
            kind (Kind | str)                   : The kind of the signal. Defaults to Kind.omitted.
        """
        if isinstance(value, dict):
            value = bec_message_type(**value)
        if value and not isinstance(value, bec_message_type):
            raise ValueError(
                f"Value must be a {bec_message_type.__name__} or a dict for signal {name}"
            )
        self.signal_metadata = signal_metadata
        self._bec_message_type = bec_message_type
        kwargs.pop("dtype", None)  # Ignore dtype if specified
        kwargs.pop("shape", None)  # Ignore shape if specified
        super().__init__(name=name, value=value, shape=(), dtype=None, kind=kind, **kwargs)

    def describe(self):
        out = super().describe()
        out[self.name]["signal_metadata"] = self.signal_metadata or {}
        return out

    @property
    def source_name(self) -> str:
        """
        Get the source name of the signal.

        Returns:
            str: The source name of the signal.
        """
        return f"BECMessageSignal:{self.name}"

    def put(self, value: messages.BECMessage | dict | None = None, **kwargs) -> None:
        """
        Put method for BECMessageSignal.

        If value is set to None, BEC's callback will not update REDIS.

        Args:
            value (BECMessage | dict | None) : The value to put.
        """
        if isinstance(value, dict):
            value = self._bec_message_type(**value)
        if value and not isinstance(value, self._bec_message_type):
            raise ValueError(
                f"Value must be a {self._bec_message_type.__name__}"
                f" or a dict for signal {self.name}"
            )
        return super().put(value, **kwargs)

    def set(self, value: messages.BECMessage | dict | None = None, **kwargs) -> DeviceStatus:
        """
        Set method for BECMessageSignal.

        If value is set to None, BEC's callback will not update REDIS.

        Args:
            value (BECMessage | dict | None) : The value to put.
        """
        self.put(value, **kwargs)
        status = DeviceStatus(device=self)
        status.set_finished()
        return status

    def _infer_value_kind(self, inference_func: Any) -> Any:
        return self._bec_message_type.__name__


class ProgressSignal(BECMessageSignal):
    """Signal to emit progress updates."""

    def __init__(
        self, *, name: str, value: messages.ProgressMessage | dict | None = None, **kwargs
    ):
        """
        Create a new ProgressSignal object.

        Args:
            name (str) : The name of the signal.
            value (ProgressMessage | dict | None) : The initial value of the signal. Defaults to None.
        """
        kwargs.pop("kind", None)  # Ignore kind if specified
        super().__init__(
            name=name,
            value=value,
            bec_message_type=messages.ProgressMessage,
            kind=Kind.omitted,
            **kwargs,
        )

    def put(
        self,
        msg: messages.ProgressMessage | dict | None = None,
        *,
        value: float | None = None,
        max_value: float | None = None,
        done: bool | None = None,
        metadata: dict | None = None,
        **kwargs,
    ) -> None:
        """
        Put method for ProgressSignal.

        If msg is provided, it will be directly set as ProgressMessage.
        Dictionaries are accepted and will be converted.
        Otherwise, at least value, max_value and done must be provided.

        Args:
            msg (ProgressMessage | dict | None) : The progress message.
            value (float)               : The current progress value.
            max_value (float)           : The maximum progress value.
            done (bool)                 : Whether the progress is done.
            metadata (dict | None)      : Additional metadata
        """
        # msg is ProgressMessage or dict
        if isinstance(msg, (messages.ProgressMessage, dict)):
            return super().put(msg, **kwargs)
        try:
            msg = messages.ProgressMessage(
                value=value, max_value=max_value, done=done, metadata=metadata
            )
        except ValidationError as exc:
            raise ValueError(f"Error setting signal {self.name}: {exc}") from exc
        return super().put(msg, **kwargs)

    def set(
        self,
        msg: messages.ProgressMessage | dict | None = None,
        *,
        value: float | None = None,
        max_value: float | None = None,
        done: bool | None = None,
        metadata: dict | None = None,
        **kwargs,
    ) -> DeviceStatus:
        """
        Set method for ProgressSignal.

        If msg is provided, it will be directly set as ProgressMessage.
        Dictionaries are accepted and will be converted.
        Otherwise, at least value, max_value and done must be provided.

        Args:
            msg (ProgressMessage | dict | None) : The progress message.
            value (float)               : The current progress value.
            max_value (float)           : The maximum progress value.
            done (bool)                 : Whether the progress is done.
            metadata (dict | None)      : Additional metadata
        """
        self.put(msg=msg, value=value, max_value=max_value, done=done, metadata=metadata, **kwargs)
        status = DeviceStatus(device=self)
        status.set_finished()
        return status


class FileEventSignal(BECMessageSignal):
    """Signal to emit file events."""

    def __init__(self, *, name: str, value: messages.FileMessage | dict | None = None, **kwargs):
        """
        Create a new FileEventSignal object.

        Args:
            name (str) : The name of the signal.
            value (FileMessage | dict | None) : The initial value of the signal. Defaults to None.
            kind (Kind | str) : The kind of the signal. Defaults to Kind.omitted.
        """
        kwargs.pop("kind", None)  # Ignore kind if specified
        super().__init__(
            name=name,
            value=value,
            bec_message_type=messages.FileMessage,
            kind=Kind.omitted,
            **kwargs,
        )

    def put(
        self,
        msg: messages.FileMessage | dict | None = None,
        *,
        file_path: str | None = None,
        done: bool | None = None,
        successful: bool | None = None,
        device_name: str | None = None,
        file_type: str = "h5",
        hinted_h5_entries: dict[str, str] | None = None,
        metadata: dict | None = None,
        **kwargs,
    ) -> None:
        """
        Put method for FileEventSignal.

        If msg is provided, it will be directly set as FileMessage.
        Dictionaries are accepted and will be converted.
        Otherwise, at least file_path, done and successful must be provided.

        Args:
            msg (FileMessage | dict | None)         : The file event message.
            file_path (str)                         : The path of the file.
            done (bool)                             : Whether the file event is done.
            successful (bool)                       : Whether the file event was successful.
            device_name (str | None)                : The name of the device.
            file_type (str | None)                  : The type of the file.
            hinted_h5_entries (dict[str, str] | None): The hinted h5 entries.
            metadata (dict | None)                  : Additional metadata.
        """
        if isinstance(msg, (messages.FileMessage, dict)):
            return super().put(msg, **kwargs)
        # kwargs provided
        try:
            msg = messages.FileMessage(
                file_path=file_path,
                done=done,
                successful=successful,
                device_name=device_name,
                file_type=file_type,
                hinted_h5_entries=hinted_h5_entries,
                metadata=metadata,
            )
        except ValidationError as exc:
            raise ValueError(f"Error setting signal {self.name}: {exc}") from exc
        return super().put(msg, **kwargs)

    # pylint: disable=arguments-differ
    def set(
        self,
        msg: messages.FileMessage | dict | None = None,
        *,
        file_path: str | None = None,
        done: bool | None = None,
        successful: bool | None = None,
        device_name: str | None = None,
        file_type: str = "h5",
        hinted_h5_entries: dict[str, str] | None = None,
        metadata: dict | None = None,
        **kwargs,
    ) -> DeviceStatus:
        """
        Set method for FileEventSignal.

        If msg is provided, it will be directly set as FileMessage.
        Dictionaries are accepted and will be converted.
        Otherwise, at least file_path, done and successful must be provided.

        Args:
            msg (FileMessage | dict | None)         : The file event message.
            file_path (str)                         : The path of the file.
            done (bool)                             : Whether the file event is done.
            successful (bool)                       : Whether the file event was successful.
            device_name (str | None)                : The name of the device.
            file_type (str | None)                  : The type of the file.
            hinted_h5_entries (dict[str, str] | None): The hinted h5 entries.
            metadata (dict | None)                  : Additional metadata.
        """
        self.put(
            msg=msg,
            file_path=file_path,
            done=done,
            successful=successful,
            device_name=device_name,
            file_type=file_type,
            hinted_h5_entries=hinted_h5_entries,
            metadata=metadata,
            **kwargs,
        )
        status = DeviceStatus(device=self)
        status.set_finished()
        return status


class PreviewSignal(BECMessageSignal):
    """Signal to emit preview data."""

    def __init__(
        self,
        *,
        name: str,
        ndim: Literal[1, 2],
        num_rotation_90: Literal[0, 1, 2, 3] = 0,
        transpose: bool = False,
        value: dict | None = None,
        **kwargs,
    ):
        """
        Create a new FileEventSignal object.

        Args:
            name (str) : The name of the signal.
            ndim (Literal[1, 2]) : The number of dimensions.
            value (DeviceMonitorMessage | dict | None) : The initial value of the signal. Defaults to None.
        """
        kwargs.pop("kind", None)
        super().__init__(
            name=name,
            value=value,
            bec_message_type=messages.DevicePreviewMessage,
            kind=Kind.omitted,
            signal_metadata={
                "ndim": ndim,
                "num_rotation_90": num_rotation_90,
                "transpose": transpose,
            },
            **kwargs,
        )

    # pylint: disable=signature-differs
    def put(
        self,
        value: list | np.ndarray | dict | messages.DevicePreviewMessage,
        *,
        metadata: dict | None = None,
        **kwargs,
    ) -> None:
        """
        Put method for PreviewSignal.

        If value is a DevicePreviewMessage, it will be directly set,
        if value is a dict, it will be converted to a DevicePreviewMessage.

        Args:
            value (list | np.ndarray | dict | self._bec_message_type): The preview data. Must be 1D.
            metadata (dict | None): Additional metadata. If dict or self._bec_message_type is passed, it will be ignored.
        """
        signal_name = self.dotted_name or self.name
        device_name = self.parent.name
        if isinstance(value, self._bec_message_type):
            return super().put(value, **kwargs)
        if isinstance(value, dict):
            value["device"] = device_name
            value["signal"] = signal_name
            return super().put(value, **kwargs)

        if isinstance(value, list):
            value = np.array(value)
        try:
            msg = self._bec_message_type(
                data=value, device=device_name, signal=signal_name, metadata=metadata
            )
        except ValidationError as exc:
            raise ValueError(f"Error setting signal {self.name}: {exc}") from exc
        super().put(msg, **kwargs)

    # pylint: disable=signature-differs
    def set(
        self, value: list | np.ndarray | dict, *, metadata: dict | None = None, **kwargs
    ) -> DeviceStatus:
        """
        Put method for PreviewSignal.

        If value is a DevicePreviewMessage, it will be directly set,
        if value is a dict, it will be converted to a DevicePreviewMessage.

        Args:
            value (list | np.ndarray | dict | self._bec_message_type)    : The preview data. Must be 1D.
            metadata (dict | None)      : Additional metadata. If dict or self._bec_message_type is passed, it will be ignored.
        """
        self.put(value=value, metadata=metadata, **kwargs)
        status = DeviceStatus(device=self)
        status.set_finished()
        return status


class DynamicSignal(BECMessageSignal):
    """Signal to emit dynamic device data."""

    @typechecked
    def __init__(
        self,
        *,
        name: str,
        signal_names: list[str] | Callable[[], list[str]],
        value: messages.DeviceMessage | dict | None = None,
        **kwargs,
    ):
        """
        Create a new DynamicSignal object.

        Args:
            name (str)                          : The name of the signal.
            signal_names (list[str] | Callable) : The names of all signals. Can be a list or a callable.
            value (DeviceMessage | dict | None) : The initial value of the signal. Defaults to None.
        """
        _raise = False
        if callable(signal_names):
            self.signal_names = signal_names()
        elif isinstance(signal_names, list):
            self.signal_names = signal_names
        else:
            _raise = True

        if _raise is True or len(self.signal_names) == 0:
            raise ValueError(f"No names provided for Dynamic signal {name} via {signal_names}")
        kwargs.pop("kind", None)  # Ignore kind if specified
        super().__init__(
            name=name,
            value=value,
            bec_message_type=messages.DeviceMessage,
            kind=Kind.omitted,
            **kwargs,
        )

    def put(
        self,
        value: messages.DeviceMessage | dict[str, dict[Literal["value", "timestamp"], Any]],
        *,
        metadata: dict | None = None,
        **kwargs,
    ) -> None:
        """
        Put method for DynamicSignal.

        All signal names must be defined upon signal creation via signal_names_list.
        If value is a DeviceMessage, it will be directly set,
        if value is a dict, it will be converted to a DeviceMessage.

        Args:
            value (dict | DeviceMessage)                : The dynamic device data.
            metadata (dict | None)                      : Additional metadata.
        """
        if isinstance(value, messages.DeviceMessage):
            self._check_signals(value)
            return super().put(value, **kwargs)
        try:
            msg = messages.DeviceMessage(signals=value, metadata=metadata)
        except ValidationError as exc:
            raise ValueError(f"Error setting signal {self.name}: {exc}") from exc
        self._check_signals(msg)
        return super().put(msg, **kwargs)

    def _check_signals(self, msg: messages.DeviceMessage) -> None:
        """Check if all signals are valid."""
        if any(name not in self.signal_names for name in msg.signals):
            raise ValueError(
                f"Invalid signal name in message {list(msg.signals.keys())} for signals {self.signal_names}"
            )

    def set(
        self,
        value: messages.DeviceMessage | dict[str, dict[Literal["value"], Any]],
        *,
        metadata: dict | None = None,
        **kwargs,
    ) -> DeviceStatus:
        """
        Set method for DynamicSignal.

        All signal names must be defined upon signal creation via signal_names_list.
        If value is a DeviceMessage, it will be directly set,
        if value is a dict, it will be converted to a DeviceMessage.

        Args:
            value (dict | DeviceMessage)                : The dynamic device data.
            metadata (dict | None)                      : Additional metadata.
        """
        self.put(value, metadata=metadata, **kwargs)
        status = DeviceStatus(device=self)
        status.set_finished()
        return status
