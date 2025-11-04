"""
Module for custom BEC signals, that wrap around ophyd.Signal.
These signals emit BECMessage objects, which comply with the BEC message system.
"""

import time
from typing import Any, Callable, Literal, Type

import numpy as np
from bec_lib import messages
from bec_lib.logger import bec_logger
from ophyd import DeviceStatus, Kind, Signal
from pydantic import BaseModel, Field, ValidationError
from typeguard import typechecked

logger = bec_logger.logger
# pylint: disable=arguments-differ
# pylint: disable=arguments-renamed
# pylint: disable=too-many-arguments
# pylint: disable=signature-differs


__all__ = ["ProgressSignal", "FileEventSignal", "PreviewSignal", "DynamicSignal", "AsyncSignal"]


class SignalInfo(BaseModel):
    """
    Base class for signal information.
    This is used to store metadata about the signal.
    """

    data_type: Literal["raw", "processed"] = Field(
        default="raw",
        description="The data type of the signal indicates whether the signal is raw data or processed data.",
    )
    saved: bool = Field(default=True, description="Indicates whether the signal is saved to disk.")
    ndim: Literal[0, 1, 2] | None = Field(
        default=None,
        description="The number of dimensions of the signal. If None, the signal is not expected to have a shape. "
        "If set to 0, the signal is expected to be a scalar. For signals with multiple sub-signals, "
        "ndim is expected to be valid for all sub-signals.",
    )
    scope: Literal["scan", "continuous"] = Field(
        default="scan",
        description="The scope of the signal indicates whether it is relevant for a specific "
        "scan or provides continuous updates, independent of a scan.",
    )
    role: Literal["main", "preview", "diagnostic", "file event", "progress"] = Field(
        default="main",
        description="The role of the signal provides context for its usage and allows other components to filter"
        " or prioritize signals based on their intended function.",
    )
    enabled: bool = True
    rpc_access: bool = Field(
        default=False,
        description="Indicates whether the signal is accessible via RPC. If False, the signal is not shown in the RPC interface.",
    )
    signals: list[tuple[str, int]] | None = Field(
        default=None, description="List of sub-signals with their kinds."
    )
    signal_metadata: dict | None = Field(
        default=None,
        description="Metadata for the signal, which can include additional information about the signal's properties.",
    )
    acquisition_group: Literal["baseline", "monitored"] | str | None = Field(
        default=None,
        description="""Specifies the acquisition group of the signal.
        It can be in sync with 'baseline' or 'monitored' groups mapping readoutPriority.
        Or mapped to a custom tag that allows grouping signals for acquisition and plotting.
        If None, the signal does not belong to any specific acquisition group.
        """,
    )


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
        data_type: Literal["raw", "processed"] = "raw",
        saved: bool = True,
        ndim: Literal[0, 1, 2] | None = None,
        scope: Literal["scan", "continuous"] = "scan",
        role: Literal["main", "preview", "diagnostic", "file event", "progress"] = "main",
        acquisition_group: Literal["baseline", "monitored"] | str | None = None,
        enabled: bool = True,
        signals: (
            Callable[[], list[str]]
            | Callable[[], list[tuple[str, str | Kind]]]
            | list[tuple[str, str | Kind] | str]
            | None
        ) = None,
        signal_metadata: dict | None = None,
        **kwargs,
    ):
        """
        Create a new BECMessageSignal object.

        Args:
            name (str)                          : The name of the signal.
            bec_message_type: type[BECMessage]  : The type of BECMessage to accept as values.
            value (BECMessage | dict | None)    : The value of the signal. Defaults to None.
        """
        if isinstance(value, dict):
            value = bec_message_type(**value)
        if value and not isinstance(value, bec_message_type):
            raise ValueError(
                f"Value must be a {bec_message_type.__name__} or a dict for signal {name}"
            )
        kwargs.pop("dtype", None)  # Ignore dtype if specified
        kwargs.pop("shape", None)  # Ignore shape if specified
        kind = kwargs.pop("kind", None)  # Ignore kind if specified
        if kind is not None:
            logger.warning("The 'kind' argument is ignored for BECMessageSignal. Please remove it.")
        super().__init__(name=name, value=value, shape=(), dtype=None, kind=Kind.omitted, **kwargs)

        self.data_type = data_type
        self.saved = saved
        self.ndim = ndim if ndim is not None else 0
        self.scope = scope
        self.role = role
        self.enabled = enabled
        self.acquisition_group = acquisition_group
        self.signals = self._unify_signals(signals)
        self.signal_metadata = signal_metadata or {}
        self._bec_message_type = bec_message_type

    def _unify_signals(
        self, signals: Callable[[], list[str]] | list[tuple[str, str | Kind] | str] | str | None
    ) -> list[tuple[str, int]]:
        """
        Unify the signals list to a list of tuples with signal name and kind.

        Args:
            signals (list[tuple[str, str | Kind] | str]): The list of signals to unify.

        Returns:
            list[tuple[str, str]]: The unified list of signals.
        """
        if isinstance(signals, Callable):
            signals = signals()
        if signals is None:
            return [(self.name, Kind.hinted.value)]  # Default to signal name with hinted kind
        if isinstance(signals, str):
            out = [(signals, Kind.hinted.value)]
        else:
            if not isinstance(signals, list):
                raise ValueError(
                    f"Signals must be a list of tuples or strings, got {type(signals).__name__}."
                )
            out = []
            for signal in signals:
                if isinstance(signal, str):
                    kind = Kind.hinted.value if len(signals) == 1 else Kind.normal.value
                    out.append((signal, kind))
                elif isinstance(signal, tuple) and len(signal) == 2:
                    if isinstance(signal[1], Kind):
                        out.append((signal[0], signal[1].value))
                    else:
                        out.append((signal[0], signal[1]))
                else:
                    raise ValueError(
                        f"Invalid signal format: {signal}. Expected a tuple of (name, kind) or a string."
                    )
        if len(out) == 1 and out[0][0] != self.name:
            signal_name, signal_kind = out[0]
            logger.warning(
                f"Signal {self.name} of class {self.__class__.__name__} has only one sub-signal. Signal name {signal_name} will be renamed to {self.name}."
            )
            out = [(self.name, signal_kind)]
        return out

    def describe(self):
        out = super().describe()

        out[self.name]["signal_info"] = SignalInfo(
            data_type=self.data_type,  # type: ignore
            saved=self.saved,
            ndim=self.ndim,  # type: ignore
            scope=self.scope,  # type: ignore
            role=self.role,  # type: ignore
            enabled=self.enabled,
            signals=self.signals,
            signal_metadata=self.signal_metadata,
            acquisition_group=self.acquisition_group,
        ).model_dump()
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
            data_type="raw",
            saved=False,
            ndim=0,
            scope="scan",
            role="progress",
            signal_metadata=None,
            value=value,
            bec_message_type=messages.ProgressMessage,
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
            msg (ProgressMessage | dict | None): The progress message.
            value (float): The current progress value.
            max_value (float): The maximum progress value.
            done (bool): Whether the progress is done.
            metadata (dict | None): Additional metadata
        """
        if msg is None and (value is None or max_value is None or done is None):
            raise ValueError(
                "Either msg must be provided or value, max_value and done must be set."
            )

        if isinstance(msg, messages.ProgressMessage):
            if (
                value is not None
                or max_value is not None
                or done is not None
                or metadata is not None
            ):
                logger.warning(
                    "Ignoring value, max_value, done and metadata arguments when msg is provided."
                )
            return super().put(msg, **kwargs)

        if isinstance(msg, dict):
            if (
                value is not None
                or max_value is not None
                or done is not None
                or metadata is not None
            ):
                logger.warning(
                    "Ignoring value, max_value, done and metadata arguments when msg is provided as dict."
                )
            return super().put(msg, **kwargs)

        if value is None or max_value is None or done is None:
            raise ValueError("If msg is not provided, value, max_value and done must be set.")

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
            msg (ProgressMessage | dict | None): The progress message.
            value (float): The current progress value.
            max_value (float): The maximum progress value.
            done (bool): Whether the progress is done.
            metadata (dict | None): Additional metadata
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
            data_type="raw",
            saved=False,
            ndim=0,
            scope="scan",
            role="file event",
            signal_metadata=None,
            value=value,
            bec_message_type=messages.FileMessage,
            **kwargs,
        )

    def put(
        self,
        msg: messages.FileMessage | dict | None = None,
        *,
        file_path: str | None = None,
        done: bool | None = None,
        successful: bool | None = None,
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
            msg (FileMessage | dict | None): The file event message.
            file_path (str | None): The path of the file.
            done (bool | None): Whether the file event is done.
            successful (bool | None): Whether the file writing finished successfully.
            file_type (str): The type of the file, defaults to "h5".
            hinted_h5_entries (dict[str, str] | None): The hinted h5 entries.
            metadata (dict | None): Additional metadata.

        """
        device_name = self.root.name if self.root else self.name
        if msg is None and (file_path is None or done is None or successful is None):
            raise ValueError(
                "Either msg must be provided or file_path, done and successful must be set."
            )
        if isinstance(msg, messages.FileMessage):
            if (
                file_path is not None
                or done is not None
                or successful is not None
                or file_type != "h5"
                or hinted_h5_entries is not None
                or metadata is not None
            ):
                logger.warning(
                    "Ignoring file_path, done, successful, file_type, "
                    "hinted_h5_entries and metadata arguments when msg is provided."
                )
            msg.device_name = device_name
            return super().put(msg, **kwargs)
        if isinstance(msg, dict):
            if (
                file_path is not None
                or done is not None
                or successful is not None
                or file_type != "h5"
                or hinted_h5_entries is not None
                or metadata is not None
            ):
                logger.warning(
                    "Ignoring file_path, done, successful, device_name, file_type, "
                    "hinted_h5_entries and metadata arguments when msg is provided as dict."
                )
            msg["device_name"] = device_name
            return super().put(msg, **kwargs)

        if file_path is None or done is None or successful is None:
            raise ValueError("If msg is not provided, file_path, done and successful must be set.")
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
            msg (FileMessage | dict | None): The file event message.
            file_path (str | None): The path of the file.
            done (bool | None): Whether the file event is done.
            successful (bool | None): Whether the file writing finished successfully.
            device_name (str | None): The name of the device.
            file_type (str): The type of the file, defaults to "h5".
            hinted_h5_entries (dict[str, str] | None): The hinted h5 entries.
            metadata (dict | None): Additional metadata.
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
        Create a new PreviewSignal object.
        For 2D data, it can be rotated by 90 degrees counter-clockwise and / or transposed for visualization. These modifications
        are applied directly to the data before it is sent to BEC.

        Args:
            name (str): The name of the signal.
            ndim (Literal[1, 2]): The number of dimensions.
            num_rotation_90 (Literal[0, 1, 2, 3]): The number of 90 degree counter-clockwise rotations to apply to the data for visualization.
            transpose (bool): Whether to transpose the data for visualization.
            value (DeviceMonitorMessage | dict | None): The initial value of the signal. Defaults to None.
        """
        kwargs.pop("kind", None)
        super().__init__(
            name=name,
            data_type="raw",
            saved=False,
            ndim=ndim,
            scope="scan",
            role="preview",
            value=value,
            bec_message_type=messages.DevicePreviewMessage,
            signal_metadata={"num_rotation_90": num_rotation_90, "transpose": transpose},
            **kwargs,
        )

    @property
    def num_rotation_90(self) -> Literal[0, 1, 2, 3]:
        """Get the number of 90 degree counter-clockwise rotations applied to the data."""
        return self.signal_metadata["num_rotation_90"]

    @num_rotation_90.setter
    def num_rotation_90(self, value: Literal[0, 1, 2, 3]) -> None:
        self.signal_metadata["num_rotation_90"] = value

    @property
    def transpose(self) -> bool:
        """Get whether the data is transposed."""
        return self.signal_metadata["transpose"]

    @transpose.setter
    def transpose(self, value: bool) -> None:
        self.signal_metadata["transpose"] = value

    def _process_data(self, value: np.ndarray) -> np.ndarray:
        if self.ndim == 1:
            return value

        if self.num_rotation_90:
            value = np.rot90(value, k=self.num_rotation_90, axes=(0, 1))
        if self.transpose:
            value = np.transpose(value)

        return value

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

        if isinstance(value, messages.DevicePreviewMessage):
            value.data = self._process_data(value.data)
            return super().put(value, **kwargs)

        if isinstance(value, dict):
            if "data" not in value:
                raise ValueError("Dictionary value must contain 'data' key.")

            value["device"] = device_name
            value["signal"] = signal_name
            value["data"] = self._process_data(value["data"])
            return super().put(value, **kwargs)

        if isinstance(value, (list, np.ndarray)):
            if not isinstance(value, np.ndarray):
                value = np.array(value)
            value = self._process_data(value)
            try:
                msg = messages.DevicePreviewMessage(
                    data=value, device=device_name, signal=signal_name, metadata=metadata
                )
            except ValidationError as exc:
                raise ValueError(f"Error setting signal {self.name}: {exc}") from exc
            return super().put(msg, **kwargs)

        raise ValueError(
            f"Value must be a {self._bec_message_type.__name__}, a dict, a list or a numpy array for signal {self.name}"
        )

    # pylint: disable=signature-differs
    def set(
        self, value: list | np.ndarray | dict, *, metadata: dict | None = None, **kwargs
    ) -> DeviceStatus:
        """
        Put method for PreviewSignal.

        If value is a DevicePreviewMessage, it will be directly set,
        if value is a dict, it will be converted to a DevicePreviewMessage.

        Args:
            value (list | np.ndarray | dict | self._bec_message_type): The preview data. Must be 1D.
            metadata (dict | None): Additional metadata. If dict or self._bec_message_type is passed, it will be ignored.
        """
        self.put(value=value, metadata=metadata, **kwargs)
        status = DeviceStatus(device=self)
        status.set_finished()
        return status


class DynamicSignal(BECMessageSignal):
    """Signal group to emit dynamic device signal data."""

    strict_signal_validation = False  # Disable strict signal validation

    def __init__(
        self,
        *,
        name: str,
        signals: list[str] | Callable[[], list[str]] | str | None = None,
        value: messages.DeviceMessage | dict | None = None,
        async_update: dict[Literal["type", "max_shape", "index"], Any] | None = None,
        acquisition_group: Literal["baseline", "monitored"] | str | None = None,
        **kwargs,
    ):
        """
        Create a new DynamicSignal object.

        Args:
            name (str): The name of the signal group.
            signal_names (list[str] | Callable): Names of all signals. Can be a list or a callable.
            value (DeviceMessage | dict | None): The initial value of the signal. Defaults to None.
            acquisition_group (Literal["baseline", "monitored"] | str | None): The acquisition group of the signal group.
            async_update (dict | None): Additional metadata for asynchronous updates.
                                        There are three relevant keys "type", "max_shape" and "index".
                                        "type" (str) : Can be one of "add", "add_slice" or "replace". This defines how the new data is added to the existing dataset.
                                                "add" : Appends data to the existing dataset. The data is always appended to the first axis.
                                                "add_slice" : Appends data to the existing dataset, but allows specifying a slice.
                                                              The slice is defined by the "index" key.
                                                "replace" : Replaces the existing dataset with the new data.
                                        "max_shape" (list[int | None]): Required for type 'add' and 'add_slice'. It defines where the data is added. For a 1D dataset,
                                                                        it should be [None]. For a 1D dataset with 3000 elements, it should be [None, 3000].
                                                                        For a 2D dataset with 3000x3000 elements, it should be [None, 3000, 3000].
                                        "index" (int): Only required for type 'add_slice'. It defines the index where the data is added.
        """
        self.async_update = async_update

        kwargs.pop("kind", None)  # Ignore kind if specified
        super().__init__(
            name=name,
            data_type=kwargs.pop("data_type", "raw"),
            saved=kwargs.pop("saved", True),
            ndim=kwargs.pop("ndim", 1),
            scope=kwargs.pop("scope", "scan"),
            role=kwargs.pop("role", "main"),
            signals=signals,
            value=value,
            bec_message_type=kwargs.pop("bec_message_type", messages.DeviceMessage),
            acquisition_group=acquisition_group,
            **kwargs,
        )

    @typechecked
    def put(
        self,
        value: messages.DeviceMessage | dict[str, dict[Literal["value", "timestamp"], Any]],
        *,
        metadata: dict | None = None,
        async_update: dict[Literal["type", "max_shape", "index"], Any] | None = None,
        acquisition_group: Literal["baseline", "monitored"] | str | None = None,
        **kwargs,
    ) -> None:
        """
        Put method for DynamicSignal.

        All signal names must be defined upon signal creation via signal_names_list.
        If value is a DeviceMessage, it will be directly set,
        if value is a dict, it will be converted to a DeviceMessage.

        Args:
            value (dict | DeviceMessage): The dynamic device data.
            metadata (dict | None): Additional metadata.
            async_update (dict[Literal["type", "max_shape", "index"], Any] | None): Additional metadata for asynchronous updates.
            acquisition_group (Literal["baseline", "monitored"] | str | None): The acquisition group of the signal group.
        """
        if isinstance(value, messages.DeviceMessage):
            if metadata is not None or async_update is not None or acquisition_group is not None:
                logger.warning(
                    "Ignoring metadata, async_update and acquisition_group arguments when value is a DeviceMessage."
                )
            self._check_signals(value)
            return super().put(value, **kwargs)
        try:
            metadata = metadata or {}
            if async_update is not None:
                metadata["async_update"] = async_update
            elif self.async_update is not None:
                metadata["async_update"] = self.async_update
            if acquisition_group is not None:
                metadata["acquisition_group"] = acquisition_group
            elif self.acquisition_group is not None:
                metadata["acquisition_group"] = self.acquisition_group

            msg = messages.DeviceMessage(signals=value, metadata=metadata)
        except ValidationError as exc:
            raise ValueError(f"Error setting signal {self.name}: {exc}") from exc
        self._check_signals(msg)
        return super().put(msg, **kwargs)

    def _check_signals(self, msg: messages.DeviceMessage) -> None:
        """Check if all signals are valid, and if relevant metadata is also present."""
        if len(self.signals) == 1:
            if self.name not in msg.signals:
                raise ValueError(
                    f"Signal {self.name} not found in message {list(msg.signals.keys())}"
                )
            return
        available_signals = [f"{self.name}_{signal_name}" for signal_name, _ in self.signals]
        if self.strict_signal_validation:
            if set(msg.signals.keys()) != set(available_signals):
                raise ValueError(
                    f"Signal names in message {list(msg.signals.keys())} do not match expected signals {available_signals}"
                )
        # If strict validation is disabled, we only check if the names are valid
        # and not if all are present
        else:
            if any(name not in available_signals for name in msg.signals):
                raise ValueError(
                    f"Invalid signal name in message {list(msg.signals.keys())} for signals {available_signals}"
                )
        # Check if async_update metadata is present
        if "async_update" not in msg.metadata:
            raise ValueError(
                f"Async update must be provided for signal {self.name} of class {self.__class__.__name__}."
            )
        # Add here validation for async update
        # TODO #629 Issue in BEC: Validate async_update --> bec_lib

    def set(
        self,
        value: messages.DeviceMessage | dict[str, dict[Literal["value"], Any]],
        *,
        metadata: dict | None = None,
        async_update: dict[Literal["type", "max_shape", "index"], Any] | None = None,
        acquisition_group: Literal["baseline", "monitored"] | str | None = None,
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
        self.put(
            value,
            metadata=metadata,
            async_update=async_update,
            acquisition_group=acquisition_group,
            **kwargs,
        )
        status = DeviceStatus(device=self)
        status.set_finished()
        return status


class AsyncMultiSignal(DynamicSignal):
    """Async Signal group to emit asynchronous data from multiple signals."""

    strict_signal_validation = True

    def __init__(
        self,
        *,
        name: str,
        ndim: Literal[0, 1, 2],
        max_size: int,
        signals: list[str] | Callable[[], list[str]],
        value: messages.DeviceMessage | dict | None = None,
        acquisition_group: Literal["baseline", "monitored"] | str | None = None,
        async_update: dict[Literal["type", "max_shape", "index"], Any] | None = None,
        **kwargs,
    ):
        """
        Create a new AsyncSignal object.

        Args:
            name (str): The name of the signal group.
            ndim (Literal[0, 1, 2]): The number of dimensions of the signals.
            max_size (int): The maximum size of the signal buffer. For ndim=2, this should be kept small to avoid large memory usage.
            signals (list[str] | Callable[[], list[str]]): The names of all sub-signals. Names will be prefixed with the group name.
            value (AsyncMessage | dict | None): The initial value of the signal. Defaults to None.
            acquisition_group (Literal["baseline", "monitored"] | str | None): The acquisition group of the signal group.
            async_update (dict | None): Additional metadata for asynchronous updates.
                                        There are three relevant keys "type", "max_shape" and "index".
                                        "type" (str) : Can be one of "add", "add_slice" or "replace". This defines how the new data is added to the existing dataset.
                                                "add" : Appends data to the existing dataset. The data is always appended to the first axis.
                                                "add_slice" : Appends data to the existing dataset, but allows specifying a slice.
                                                              The slice is defined by the "index" key.
                                                "replace" : Replaces the existing dataset with the new data.
                                        "max_shape" (list[int | None]): Required for type 'add' and 'add_slice'. It defines where the data is added. For a 1D dataset,
                                                                        it should be [None]. For a 1D dataset with 3000 elements, it should be [None, 3000].
                                                                        For a 2D dataset with 3000x3000 elements, it should be [None, 3000, 3000].
                                        "index" (int): Only required for type 'add_slice'. It defines the index where the data is added.
        """
        kwargs.pop("kind", None)  # Ignore kind if specified
        super().__init__(
            name=name,
            data_type="raw",
            saved=True,
            ndim=ndim,
            scope="scan",
            role="main",
            value=value,
            bec_message_type=messages.DeviceMessage,
            async_update=async_update,
            signal_metadata={"max_size": max_size},
            acquisition_group=acquisition_group,
            signals=signals,
            **kwargs,
        )


class AsyncSignal(DynamicSignal):
    """Device Signal to emit data asynchronously."""

    strict_signal_validation = True

    def __init__(
        self,
        *,
        name: str,
        ndim: Literal[0, 1, 2],
        max_size: int,
        value: messages.DeviceMessage | dict | None = None,
        acquisition_group: Literal["baseline", "monitored"] | str | None = None,
        async_update: dict[Literal["type", "max_shape", "index"], Any] | None = None,
        **kwargs,
    ):
        """
        Create a new AsyncSignal object.

        Args:
            name (str): The name of the signal.
            ndim (Literal[0, 1, 2]): The number of dimensions of the signals.
            max_size (int): The maximum size of the signal buffer. For ndim=2, this should be kept small to avoid large memory usage.
            value (AsyncMessage | dict | None): The initial value of the signal. Defaults to None.
            acquisition_group (Literal["baseline", "monitored"] | str | None): The acquisition group of the signal group.
            async_update (dict | None): Additional metadata for asynchronous updates.
                                        There are three relevant keys "type", "max_shape" and "index".
                                        "type" (str) : Can be one of "add", "add_slice" or "replace". This defines how the new data is added to the existing dataset.
                                                "add" : Appends data to the existing dataset. The data is always appended to the first axis.
                                                "add_slice" : Appends data to the existing dataset, but allows specifying a slice.
                                                              The slice is defined by the "index" key.
                                                "replace" : Replaces the existing dataset with the new data.
                                        "max_shape" (list[int | None]): Required for type 'add' and 'add_slice'. It defines where the data is added. For a 1D dataset,
                                                                        it should be [None]. For a 1D dataset with 3000 elements, it should be [None, 3000].
                                                                        For a 2D dataset with 3000x3000 elements, it should be [None, 3000, 3000].
                                        "index" (int): Only required for type 'add_slice'. It defines the index where the data is added.
        """
        kwargs.pop("kind", None)  # Ignore kind if specified
        super().__init__(
            name=name,
            data_type="raw",
            saved=True,
            ndim=ndim,
            scope="scan",
            role="main",
            value=value,
            bec_message_type=messages.DeviceMessage,
            async_update=async_update,
            signal_metadata={"max_size": max_size},
            acquisition_group=acquisition_group,
            signals=None,
            **kwargs,
        )

    def put(
        self,
        value: Any,
        timestamp: float | None = None,
        async_update: dict[Literal["type", "max_shape", "index"], Any] | None = None,
        acquisition_group: str | None = None,
        **kwargs,
    ) -> None:
        """
        Put method for AsyncSignal.

        Args:
            value (Any): The value to put.
            timestamp (float | None): The timestamp of the value. If None, the current time is used.
            async_update (dict[Literal["type", "max_shape", "index"], Any] | None): Additional metadata for asynchronous updates. Please refer to the class docstring for details.
            acquisition_group (Literal["baseline", "monitored"] | str | None): The acquisition group of the signal.
        """
        timestamp = timestamp or time.time()
        super().put(
            value={self.name: {"value": value, "timestamp": timestamp}},
            async_update=async_update,
            acquisition_group=acquisition_group,
            **kwargs,
        )

    def set(
        self,
        value: Any,
        timestamp: float | None = None,
        async_update: dict[Literal["type", "max_shape", "index"], Any] | None = None,
        acquisition_group: str | None = None,
        **kwargs,
    ) -> DeviceStatus:
        """
        Set method for AsyncSignal.

        Args:
            value (Any): The value to put.
            timestamp (float | None): The timestamp of the value. If None, the current time is used.
            async_update (dict[Literal["type", "max_shape", "index"], Any] | None): Additional metadata for asynchronous updates. Please refer to the class docstring for details.
            acquisition_group (Literal["baseline", "monitored"] | str | None): The acquisition group of the signal.
        """
        self.put(
            value=value,
            timestamp=timestamp,
            async_update=async_update,
            acquisition_group=acquisition_group,
            **kwargs,
        )
        status = DeviceStatus(device=self)
        status.set_finished()
        return status

    @property
    def max_size(self) -> int:
        """Get the maximum size of the signal buffer."""
        return self.signal_metadata["max_size"]

    @max_size.setter
    def max_size(self, value: int) -> None:
        self.signal_metadata["max_size"] = value
