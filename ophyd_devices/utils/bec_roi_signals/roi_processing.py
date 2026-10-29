from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, TypedDict

from bec_lib.endpoints import MessageEndpoints
from bec_lib.logger import bec_logger
from bec_lib.messages import ROIAnalysisConfig, ROIAvailableAnalysisMessage, ROIConfigurationMessage
from bec_lib.redis_connector import RedisConnector
from ophyd import Component as Cpt
from ophyd import Device, Kind, Signal

from ophyd_devices.utils.bec_roi_signals.signals import (
    AvailableOperationsSignal,
    ConfigUpdateReceivedSignal,
    SelectedOperationSignal,
)
from ophyd_devices.utils.bec_signals import DynamicSignal
from ophyd_devices.utils.psi_device_base_utils import destroy_subdevices

if TYPE_CHECKING:
    from bec_lib.connector import MessageObject

logger = bec_logger.logger


class ROIOperationConfig(TypedDict, total=False):
    """Configuration for one selectable ROI analysis operation."""

    scalar_outputs: list[str]
    waveform_outputs: list[str]
    enable_signal: str | None
    source_signals: dict[str, str]


LITERAL_ROI_PROCESSING_CONFIG = dict[str, ROIOperationConfig]


class ROIProcessing(Device, ABC):
    """Abstract base class for ROI processing signals"""

    result_scalar = Cpt(
        DynamicSignal,
        name="result_scalar",
        max_size=1000,
        signals=[],
        ndim=0,
        async_update={"type": "add", "max_shape": [None]},
        data_type="processed",
    )
    result_waveform = Cpt(
        DynamicSignal,
        name="result_waveform",
        max_size=1000,
        signals=[],
        ndim=1,
        async_update={"type": "add", "max_shape": [None, None]},
        data_type="processed",
    )

    active = Cpt(Signal, value=False, kind=Kind.normal)
    roi_name = Cpt(Signal, value="roi", kind=Kind.normal)
    x = Cpt(Signal, value=0, kind=Kind.normal)
    y = Cpt(Signal, value=0, kind=Kind.normal)
    width = Cpt(Signal, value=0, kind=Kind.normal)
    height = Cpt(Signal, value=0, kind=Kind.normal)
    selected_operations = Cpt(SelectedOperationSignal, value=[], kind=Kind.normal)
    available_operations = Cpt(AvailableOperationsSignal, kind=Kind.config)
    update_received = Cpt(ConfigUpdateReceivedSignal, kind=Kind.omitted)

    def __init__(self, *args, **kwargs):
        kwargs, signal_kwargs = self._get_kwargs_for_signals(kwargs)
        super().__init__(*args, **kwargs)
        self._signal_kwargs = signal_kwargs
        self._connector: RedisConnector | None = None
        self._roi_connection_initialized = False
        self._config_subscription = None
        self._config_registered = False
        # Publish statistics under the ROI name, without internal container labels.
        self.result_scalar.name = self.name
        self._update_result_signal_names()

    def _update_result_signal_names(self):
        """
        Update the signal names for the DynamicSignals "result_scalar" and "result_waveform" based on
        the outputs defined in the subclass. This ensures that the signals.
        Subclasses must specify every possible output signal in the get_scalar_outputs and get_waveform_outputs methods.
        """
        # pylint: disable=protected-access
        self.result_scalar.signals = self.result_scalar._unify_signals(self.get_scalar_outputs())
        self.result_waveform.signals = self.result_waveform._unify_signals(
            self.get_waveform_outputs()
        )

    def _get_kwargs_for_signals(self, kwargs) -> tuple[dict, dict[str, dict]]:
        """
        Utility method to extract kwargs for the signals defined in this class.
        This allows to set initial values for the signals during initialization of the ROIProcessing device.
        """
        ret_kwargs = {}
        for k in ["active", "roi_name", "x", "y", "width", "height", "selected_operations"]:
            if k in kwargs:
                ret_kwargs[k] = kwargs.pop(k)
        return kwargs, ret_kwargs

    def on_connected(self) -> None:
        """Initialize Redis integration after EPICS connection, once per instance.

        The owning device calls this hook explicitly from its on_connected hook.
        Standalone callers may invoke it directly after wait_for_connection().
        The root must expose a device_manager with a connector.
        """
        if self._roi_connection_initialized:
            return
        self._connector: RedisConnector | None = (
            self.root.device_manager.connector if hasattr(self.root, "device_manager") else None
        )
        if self._connector is None:
            raise RuntimeError(
                f"Signal {self.name} is not connected to Redis, please provide a Redis Connector during the initialization."
            )
        self.update_received.on_connected()
        # Setup initial values for the signal as provided in the kwargs during initialization
        for signal_name, value in self._signal_kwargs.items():
            signal = getattr(self, signal_name)
            signal.put(value)

        # Connect to relevant endpoint for ROI configuration updates
        if self._config_subscription is None:
            self._config_subscription = self.update_received.subscribe(
                self._apply_requested_config, event_type=self.update_received.SUB_VALUE, run=False
            )
        if not self._config_registered:
            self._connector.register(
                MessageEndpoints.roi_config_request(device=self.root.name, signal=self.dotted_name),
                cb=self._receive_roi_configuration_message,
            )
            self._config_registered = True
        self._publish_available_analysis()
        if self.active.get():
            msg = ROIConfigurationMessage(
                device=self.root.name,
                signal=self.dotted_name,
                active=self.active.get(),
                name=self.roi_name.get(),
                roi_config={
                    "x": self.x.get(),
                    "y": self.y.get(),
                    "width": self.width.get(),
                    "height": self.height.get(),
                },
                selected_operations=self.selected_operations.get(),
            )
            self._on_config_update(msg)  # Apply the initial configuration if active is True
        self._publish_configuration()
        self._roi_connection_initialized = True

    def destroy(self):
        """Clean up the ROI processing signal and unregister from Redis."""
        if self._destroyed:
            return
        if self._connector is not None and self._config_registered:
            self._connector.unregister(
                MessageEndpoints.roi_config_request(device=self.root.name, signal=self.dotted_name),
                cb=self._receive_roi_configuration_message,
            )
        self._config_registered = False
        destroy_subdevices(self)
        super().destroy()

    @abstractmethod
    def get_scalar_outputs(self) -> list[str]:
        """
        Returns a list of strings with all possible scalar output signals for the ROI processing signal.
        All possible outputs must be listed, although not all of them have to be there at the same time.
        """

    @abstractmethod
    def get_waveform_outputs(self) -> list[str]:
        """
        Returns a list of strings with all possible waveform output signals for the ROI processing signal.
        All possible outputs must be listed, although not all of them have to be there at the same time.
        """

    @abstractmethod
    def get_available_analysis_operations(self) -> list[str]:
        """
        Returns a list of strings with all possible analysis operations for the ROI processing signal.
        All possible operations must be listed, although not all of them have to be active at the same time.
        """

    def compile_roi_analysis_config(self) -> ROIAnalysisConfig:
        """Compile the ROI analysis configuration from the available operations and outputs."""
        return ROIAnalysisConfig(
            available_operations=self.get_available_analysis_operations(),
            waveform_results=self.get_waveform_outputs(),
            scalar_results=self.get_scalar_outputs(),
        )

    def _publish_available_analysis(self) -> None:
        """Publish the available ROI analysis operations and result signals."""
        if self._connector is None:
            raise RuntimeError(
                f"Signal {self.name} is not connected to Redis and cannot publish ROI analysis."
            )
        message = ROIAvailableAnalysisMessage(
            device=self.root.name,
            signal=self.dotted_name,
            config=self.compile_roi_analysis_config(),
        )
        self._connector.set_and_publish(
            MessageEndpoints.available_roi_analysis(device=self.root.name, signal=self.dotted_name),
            message,
        )

    def _publish_configuration(self) -> None:
        """Publish the current configuration, never an unprocessed request."""
        if self._connector is None:
            return
        self._connector.set_and_publish(
            MessageEndpoints.roi_config(device=self.root.name, signal=self.dotted_name),
            ROIConfigurationMessage(
                metadata={"timestamp": time.time()},
                device=self.root.name,
                signal=self.dotted_name,
                name=self.roi_name.get(),
                active=bool(self.active.get()),
                roi_config={key: getattr(self, key).get() for key in ("x", "y", "width", "height")},
                selected_operations=self.selected_operations.get(),
            ),
        )

    def _apply_requested_config(self, value: ROIConfigurationMessage, **kwargs) -> None:
        """Publish only after the complete backend implementation succeeds."""
        self._on_config_update(value, **kwargs)
        self._publish_configuration()

    def _receive_roi_configuration_message(self, message: MessageObject):
        """
        Receive a ROI configuration message and update the ROI processing signal accordingly.

        Args:
            message (MessageObject): The received message object containing the ROI configuration.
        """
        message: ROIConfigurationMessage = message.value
        if message.device != self.root.name or message.signal != self.dotted_name:
            logger.warning(
                f"Ignoring ROI configuration for {message.device}.{message.signal}; "
                f"this ROIProcessing is {self.root.name}.{self.dotted_name}."
            )
            return
        self.update_received.put(message)

    def _on_config_update(self, value: ROIConfigurationMessage, **kwargs):
        """
        Callback for when a new ROI configuration message is received.

        Args:
            value (ROIConfigurationMessage): The received ROI configuration message.
        """
        if not isinstance(value, ROIConfigurationMessage):
            raise TypeError(
                f"Expected ROIConfigurationMessage, got {type(value).__name__} instead."
            )
        self.selected_operations.check_value(value.selected_operations)
        self.active.put(value.active)
        self.roi_name.put(value.name)
        self.x.put(value.roi_config.x)
        self.y.put(value.roi_config.y)
        self.width.put(value.roi_config.width)
        self.height.put(value.roi_config.height)
        self.selected_operations.put(value.selected_operations)
