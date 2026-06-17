from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Literal

from bec_lib.endpoints import MessageEndpoints
from bec_lib.logger import bec_logger
from bec_lib.messages import ROIAnalysisConfig, ROIAvailableAnalysisMessage, ROIConfigurationMessage
from bec_lib.redis_connector import RedisConnector
from ophyd import Component as Cpt
from ophyd import Device, Signal, SignalRO
from ophyd.device import required_for_connection

from ophyd_devices.utils.bec_roi_signals.signals import (
    AvailableOperationsSignal,
    ConfigUpdateReceivedSignal,
    SelectedOperationSignal,
)
from ophyd_devices.utils.bec_signals import DynamicSignal

if TYPE_CHECKING:
    from bec_lib.connector import MessageObject

logger = bec_logger.logger

LITERAL_ROI_PROCESSING_CONFIG = dict[
    str, dict[Literal["scalar_outputs", "waveform_outputs"], list[str]]
]


class ROIProcessing(Device, ABC):
    """Abstract base class for ROI processing signals"""

    REQUIRES_WAIT_FOR_CONNECTION = True

    result_scalar = Cpt(
        DynamicSignal,
        name="result_scalar",
        max_size=1000,
        signals=[],
        ndim=0,
        async_update={"type": "add", "max_shape": [None]},
    )
    result_waveform = Cpt(
        DynamicSignal,
        name="result_waveform",
        max_size=1000,
        signals=[],
        ndim=1,
        async_update={"type": "add", "max_shape": [None, None]},
    )

    active = Cpt(Signal, value=False, kind="config")
    roi_name = Cpt(Signal, value="roi", kind="config")
    x = Cpt(Signal, value=0, kind="config")
    y = Cpt(Signal, value=0, kind="config")
    width = Cpt(Signal, value=10, kind="config")
    height = Cpt(Signal, value=10, kind="config")
    selected_operations = Cpt(SelectedOperationSignal, value=[], kind="config")
    available_operations = Cpt(AvailableOperationsSignal, kind="config")
    update_received = Cpt(ConfigUpdateReceivedSignal, kind="omitted")

    def __init__(self, *args, **kwargs):
        kwargs, signal_kwargs = self._get_kwargs_for_signals(kwargs)
        super().__init__(*args, **kwargs)
        self._signal_kwargs = signal_kwargs
        self._connector: RedisConnector | None = None
        # Setup the DynamicSignal outputs based on the available operations and outputs
        self._prepare_result_signals()

    def _prepare_result_signals(self):
        """Prepare the result signals based on the available operations and outputs."""
        self.result_scalar.signals = self.result_scalar._unify_signals(self.get_scalar_outputs())
        self.result_waveform.signals = self.result_waveform._unify_signals(
            self.get_waveform_outputs()
        )

    def _get_kwargs_for_signals(self, kwargs) -> tuple[dict, dict[str, dict]]:
        """Get the kwargs for the signals of this device."""
        ret_kwargs = {}
        for k in ["active", "roi_name", "x", "y", "width", "height", "selected_operations"]:
            if k in kwargs:
                ret_kwargs[k] = kwargs.pop(k)
        return kwargs, ret_kwargs

    @required_for_connection
    def wait_for_connection(self, all_signals=False, timeout=...):
        """Wait for the ROI processing signal to be connected to Redis."""
        self._connector: RedisConnector | None = (
            self.root.device_manager.connector if hasattr(self.root, "device_manager") else None
        )
        if self._connector is None:
            raise RuntimeError(
                f"Signal {self.name} is not connected to Redis, please provide a Redis Connector during the initialization."
            )
        super().wait_for_connection(all_signals, timeout)
        # Set initial values for the configuration signals from the kwargs provided during initialization
        for signal_name, value in self._signal_kwargs.items():
            signal = getattr(self, signal_name)
            signal.put(value)

        # Connect to relevant endpoint for ROI configuration updates
        self.update_received.subscribe(
            self._on_config_update, event_type=self.update_received.SUB_VALUE, run=False
        )
        self._connector.register(
            MessageEndpoints.roi_config(device=self.root.name, signal=self.endpoint_signal_name),
            cb=self.receive_roi_configuration_message,
        )
        self.publish_available_analysis()

    def destroy(self):
        """Clean up the ROI processing signal and unregister from Redis."""
        if self._connector is not None:
            self._connector.unregister(
                MessageEndpoints.roi_config(
                    device=self.root.name, signal=self.endpoint_signal_name
                ),
                cb=self.receive_roi_configuration_message,
            )
        super().destroy()

    @abstractmethod
    def get_scalar_outputs(self) -> list[str]:
        """Return the scalar output signal for the ROI processing signal."""

    @abstractmethod
    def get_waveform_outputs(self) -> list[str]:
        """Return the waveform output signal for the ROI processing signal."""

    @abstractmethod
    def get_available_analysis_operations(self) -> list[str]:
        """Return the available analysis operations for the ROI processing signal."""

    @property
    def endpoint_signal_name(self) -> str:
        """Return the component signal name used for BEC ROI endpoints."""
        return getattr(self, "dotted_name", None) or getattr(self, "attr_name", None) or self.name

    def compile_roi_analysis_config(self) -> ROIAnalysisConfig:
        """Compile the ROI analysis configuration from the available operations and outputs."""
        return ROIAnalysisConfig(
            available_operations=self.get_available_analysis_operations(),
            waveform_results=self.get_waveform_outputs(),
            scalar_results=self.get_scalar_outputs(),
        )

    def publish_available_analysis(self) -> None:
        """Publish the available ROI analysis operations and result signals."""
        if self._connector is None:
            raise RuntimeError(
                f"Signal {self.name} is not connected to Redis and cannot publish ROI analysis."
            )
        message = ROIAvailableAnalysisMessage(
            device=self.root.name,
            signal=self.endpoint_signal_name,
            config=self.compile_roi_analysis_config(),
        )
        self._connector.set_and_publish(
            MessageEndpoints.available_roi_analysis(
                device=self.root.name, signal=self.endpoint_signal_name
            ),
            message,
        )

    def receive_roi_configuration_message(self, message: MessageObject):
        """Receive a ROI configuration message and update the ROI processing signal accordingly."""
        message: ROIConfigurationMessage = message.value
        if message.device != self.root.name or message.signal != self.endpoint_signal_name:
            logger.warning(
                f"Ignoring ROI configuration for {message.device}.{message.signal}; "
                f"this ROIProcessing is {self.root.name}.{self.endpoint_signal_name}."
            )
            return
        self.update_received.put(message)

    def _on_config_update(self, value, **kwargs):
        """Callback for when a new ROI configuration message is received."""
        if not isinstance(value, ROIConfigurationMessage):
            raise TypeError(
                f"Expected ROIConfigurationMessage, got {type(value).__name__} instead."
            )
        self.active.put(value.active)
        self.roi_name.put(value.name)
        self.x.put(value.roi_config.x)
        self.y.put(value.roi_config.y)
        self.width.put(value.roi_config.width)
        self.height.put(value.roi_config.height)
        self.selected_operations.put(value.selected_operations)
