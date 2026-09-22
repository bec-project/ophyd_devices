"""Abstract ROI processing sub-device shared by all ROI-capable detectors."""

from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Literal, TypedDict

from bec_lib.endpoints import MessageEndpoints
from bec_lib.logger import bec_logger
from bec_lib.messages import (
    ROIAnalysisConfig,
    ROIAvailableAnalysisMessage,
    ROIConfig,
    ROIConfigurationMessage,
)
from ophyd import Component as Cpt
from ophyd import Device, Kind, Signal

from ophyd_devices.utils.bec_roi_signals.signals import (
    AvailableOperationsSignal,
    ConfigUpdateReceivedSignal,
    SelectedOperationSignal,
    get_root_connector,
)
from ophyd_devices.utils.bec_signals import DynamicSignal

if TYPE_CHECKING:
    from bec_lib.connector import MessageObject
    from bec_lib.redis_connector import RedisConnector

logger = bec_logger.logger

ResultKind = Literal["scalar", "waveform"]


class ROIOperationConfig(TypedDict, total=False):
    """Configuration for one selectable ROI analysis operation."""

    scalar_outputs: list[str]
    waveform_outputs: list[str]
    enable_signal: str | None
    source_signals: dict[str, str]


LITERAL_ROI_PROCESSING_CONFIG = dict[str, ROIOperationConfig]

#: Signals that can be initialised through kwargs of the Component, e.g. ``Cpt(MyROI, x=10, ...)``.
CONFIG_SIGNAL_NAMES = ("active", "roi_name", "x", "y", "width", "height", "selected_operations")


class ROIProcessing(Device, ABC):
    """
    Abstract base class for ROI processing sub-devices.

    One ROIProcessing component describes a rectangular region of interest (``x``, ``y``,
    ``width``, ``height`` in detector pixels), the analysis operations selected for it and
    publishes the per-ROI results through the ``result_scalar`` and ``result_waveform``
    DynamicSignals. The geometry and selection signals are configuration (``Kind.config``),
    i.e. they end up in ``read_configuration()`` / the baseline, never in ``read()``.

    Requirements on the root device:

    - derive from :class:`~ophyd_devices.interfaces.base_classes.psi_device_base.PSIDeviceBase`:
      it connects components flagged with ``REQUIRES_WAIT_FOR_CONNECTION`` and calls their
      ``on_connected`` hook once all signals of the root are connected;
    - provide a device manager with a Redis connector to receive configuration updates from
      BEC (``MessageEndpoints.roi_config``) and to publish the available operations. Without a
      connector (config validation, unit tests) the component still works locally.

    Subclasses implement the three ``get_*`` methods, react to configuration changes by
    overriding :meth:`_on_config_update` and publish results with :meth:`put_results`.
    Scan hooks other than ``on_connected`` are not forwarded automatically; a root device
    that needs them (e.g. ``ADROIProcessing``) calls them explicitly.
    """

    REQUIRES_WAIT_FOR_CONNECTION = True

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

    active = Cpt(Signal, value=False, kind=Kind.config)
    roi_name = Cpt(Signal, value="roi", kind=Kind.config)
    x = Cpt(Signal, value=0, kind=Kind.config)
    y = Cpt(Signal, value=0, kind=Kind.config)
    width = Cpt(Signal, value=0, kind=Kind.config)
    height = Cpt(Signal, value=0, kind=Kind.config)
    selected_operations = Cpt(SelectedOperationSignal, value=[], kind=Kind.config)
    available_operations = Cpt(AvailableOperationsSignal, kind=Kind.config)
    update_received = Cpt(ConfigUpdateReceivedSignal, kind=Kind.omitted)

    def __init__(self, *args, **kwargs):
        kwargs, signal_kwargs = self._get_kwargs_for_signals(kwargs)
        super().__init__(*args, **kwargs)
        self._signal_kwargs = signal_kwargs
        self._connector: RedisConnector | None = None
        self._config_lock = threading.RLock()
        self._config_subscription: int | None = None
        self._update_result_signal_names()

    def _update_result_signal_names(self):
        """
        Update the signal names for the DynamicSignals "result_scalar" and "result_waveform" based on
        the outputs defined in the subclass. Subclasses must list every possible output signal in
        get_scalar_outputs and get_waveform_outputs.
        """
        # pylint: disable=protected-access
        self.result_scalar.signals = self.result_scalar._unify_signals(self.get_scalar_outputs())
        self.result_waveform.signals = self.result_waveform._unify_signals(
            self.get_waveform_outputs()
        )

    @staticmethod
    def _get_kwargs_for_signals(kwargs) -> tuple[dict, dict[str, Any]]:
        """
        Split the Component kwargs into kwargs for the Device and initial values for the
        configuration signals (see ``CONFIG_SIGNAL_NAMES``).
        """
        signal_kwargs = {k: kwargs.pop(k) for k in CONFIG_SIGNAL_NAMES if k in kwargs}
        return kwargs, signal_kwargs

    ############################
    ## Connection / lifecycle ##
    ############################

    @property
    def redis_connected(self) -> bool:
        """Return whether the component can exchange ROI messages with BEC."""
        return self._connector is not None

    def wait_for_connection(self, all_signals=False, timeout=5):
        """
        Connect the component. Called by the PSIDeviceBase root device before it connects
        its own signals; the root then calls :meth:`on_connected` once everything is connected.
        """
        self._connector = get_root_connector(self)
        if self._connector is None:
            logger.warning(
                f"{self.name}: root device {self.root.name} has no Redis connector; "
                "ROI configuration updates from BEC are disabled."
            )
        self.update_received.wait_for_connection()
        super().wait_for_connection(all_signals=all_signals, timeout=timeout)
        # Apply the initial values given as Component kwargs
        for signal_name, value in self._signal_kwargs.items():
            getattr(self, signal_name).put(value)
        if self._config_subscription is None:
            self._config_subscription = self.update_received.subscribe(
                self._on_config_update, event_type=self.update_received.SUB_VALUE, run=False
            )
        self._publish_available_analysis()
        if self.active.get():
            self._on_config_update(self.current_configuration())

    def on_connected(self) -> None:
        """
        Called by the PSIDeviceBase root device after all its signals are connected.
        Subclasses that need to talk to hardware (EPICS plugins, backends) do it here.
        """

    ########################
    ## Configuration API  ##
    ########################

    def current_configuration(self) -> ROIConfigurationMessage:
        """Return the current ROI configuration as a ROIConfigurationMessage."""
        with self._config_lock:
            return ROIConfigurationMessage(
                device=self.root.name,
                signal=self.dotted_name,
                active=bool(self.active.get()),
                name=self.roi_name.get(),
                roi_config=ROIConfig(
                    x=int(self.x.get()),
                    y=int(self.y.get()),
                    width=int(self.width.get()),
                    height=int(self.height.get()),
                ),
                selected_operations=list(self.selected_operations.get()),
            )

    def get_roi(self) -> tuple[int, int, int, int]:
        """Return the ROI rectangle as ``(x, y, width, height)``, read atomically."""
        with self._config_lock:
            return (
                int(self.x.get()),
                int(self.y.get()),
                int(self.width.get()),
                int(self.height.get()),
            )

    def is_operation_active(self, operation: str) -> bool:
        """Return whether the ROI is active and the given operation is selected."""
        with self._config_lock:
            return bool(self.active.get()) and operation in self.selected_operations.get()

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
        """Publish the available ROI analysis operations and result signals (if connected to BEC)."""
        if self._connector is None:
            logger.debug(
                f"{self.name}: not connected to Redis, skipping available-analysis publish."
            )
            return
        message = ROIAvailableAnalysisMessage(
            device=self.root.name,
            signal=self.dotted_name,
            config=self.compile_roi_analysis_config(),
        )
        self._connector.set_and_publish(
            MessageEndpoints.available_roi_analysis(device=self.root.name, signal=self.dotted_name),
            message,
        )

    ##############
    ## Results  ##
    ##############

    def put_results(
        self, kind: ResultKind, results: dict[str, dict], async_update: dict | None = None
    ) -> None:
        """
        Publish ROI results keyed by result name, i.e. by the names returned from
        ``get_scalar_outputs`` / ``get_waveform_outputs``.

        DynamicSignal names a lone sub-signal after the signal itself
        (``<device>_<roi>_result_scalar`` instead of ``<device>_<roi>_result_scalar_<result>``);
        this method hides that convention from subclasses.

        Args:
            kind: "scalar" for ``result_scalar`` or "waveform" for ``result_waveform``.
            results: ``{result_name: {"value": ..., "timestamp": ...}}``; a subset of the outputs.
            async_update: optional async_update metadata, defaults to the signal's own.
        """
        if kind == "scalar":
            signal, outputs = self.result_scalar, self.get_scalar_outputs()
        elif kind == "waveform":
            signal, outputs = self.result_waveform, self.get_waveform_outputs()
        else:
            raise ValueError(f"Unknown result kind {kind!r}; expected 'scalar' or 'waveform'.")
        unknown = [name for name in results if name not in outputs]
        if unknown:
            raise ValueError(
                f"Unknown {kind} result(s) {unknown} for {self.name}; available: {outputs}."
            )
        if not results:
            return
        if len(outputs) == 1:
            payload = {signal.name: results[outputs[0]]}
        else:
            payload = dict(results)
        signal.put(payload, async_update=async_update)

    ##############################
    ## Configuration reception  ##
    ##############################

    def _receive_roi_configuration_message(self, message: MessageObject) -> None:
        """Forward a ROI configuration message to the update signal (kept for API compatibility)."""
        # pylint: disable=protected-access
        self.update_received._receive_roi_configuration_message(message)

    def _on_config_update(self, value: ROIConfigurationMessage, **kwargs):
        """
        Callback for a newly released ROI configuration message. Subclasses extend this to
        forward the configuration to their backend.

        Args:
            value (ROIConfigurationMessage): The received ROI configuration message.
        """
        if not isinstance(value, ROIConfigurationMessage):
            raise TypeError(
                f"Expected ROIConfigurationMessage, got {type(value).__name__} instead."
            )
        with self._config_lock:
            self.active.put(value.active)
            self.roi_name.put(value.name)
            self.x.put(value.roi_config.x)
            self.y.put(value.roi_config.y)
            self.width.put(value.roi_config.width)
            self.height.put(value.roi_config.height)
            self.selected_operations.put(value.selected_operations)
