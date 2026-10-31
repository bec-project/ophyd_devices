"""
Selectable ROI analysis and dynamic results built on shared ROI configuration.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Literal, TypedDict

from bec_lib.endpoints import MessageEndpoints
from bec_lib.messages import ROIAnalysisConfig, ROIAvailableAnalysisMessage, ROIConfigurationMessage
from ophyd import Component as Cpt
from ophyd import Kind, Signal

from ophyd_devices.utils.bec_roi_signals.roi import ROI
from ophyd_devices.utils.bec_roi_signals.signals import (
    AvailableOperationsSignal,
    SelectedOperationSignal,
)
from ophyd_devices.utils.bec_signals import DynamicSignal


class ROIOperationConfig(TypedDict, total=False):
    """
    Describe the signals and controls belonging to one ROI analysis operation.

    Attributes:
        scalar_outputs (list[str]): Scalar result names produced by the operation.
        waveform_outputs (list[str]): Array result names produced by the operation.
        enable_signal (str | None): Backend signal attribute enabling the operation,
            or None when it has no independent enable control.
        source_signals (dict[str, str]): Map result names to backend signal paths.
            Backends use these paths when subscribing to or reading their results.

    All fields are optional; a concrete backend supplies the fields it needs.
    """

    scalar_outputs: list[str]
    waveform_outputs: list[str]
    enable_signal: str | None
    source_signals: dict[str, str]


LITERAL_ROI_PROCESSING_CONFIG = dict[str, ROIOperationConfig]


class ROIProcessing(ROI, ABC):
    """
    Add analysis selection and dynamic results to shared ROI configuration.

    Subclasses declare all supported operations and scalar/waveform result names.
    They also own acquisition and result publication; this base only creates result
    signals, validates selections and publishes analysis capabilities. Configuration
    requests, shape restrictions, scan deferral and confirmed configuration publication
    are inherited from ROI. Use ROI directly for configuration-only backends.

    Attributes:
        result_scalar (DynamicSignal): Scalar result stream, with one-dimensional
            append semantics across acquisitions.
        result_waveform (DynamicSignal): Waveform result stream, with two-dimensional
            append semantics across acquisitions and samples.
        selected_operations (SelectedOperationSignal): Configurable analysis selection.
        available_operations (AvailableOperationsSignal): Read-only supported operations.
    """

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

    selected_operations = Cpt(
        SelectedOperationSignal, config_key="selected_operations", value=[], kind=Kind.config
    )
    available_operations = Cpt(AvailableOperationsSignal, kind=Kind.config)

    def __init__(self, *args, selected_operations: list[str] | None = None, **kwargs) -> None:
        """
        Create processing signals and record the initial analysis selection.

        No backend communication or Redis subscriptions occur during construction.
        The selection is applied by on_connected(), and result names are derived from
        get_scalar_outputs() and get_waveform_outputs().

        Args:
            *args (Any): Positional device arguments forwarded to ROI.
            selected_operations (list[str] | None): Initial analysis operation names.
                None selects no operations. The selection is validated after connection.
            **kwargs (Any): ROI configuration and ophyd.Device arguments, including
                roi_config, allowed_roi_config_types, active, roi_name, name and parent.
        """
        super().__init__(*args, **kwargs)
        self._signal_kwargs["selected_operations"] = selected_operations or []
        self.result_scalar.name = self.name
        self._update_result_signal_names()

    def on_connected(self) -> None:
        """
        Initialize ROI configuration and publish available analysis capabilities.

        The owning device calls this method after connection. The inherited initializer
        validates/applies the initial configuration and registers request subscriptions.
        This method then publishes operation and output metadata. Successful repeated
        calls do nothing; failed initialization can be retried without duplicate request
        subscriptions.

        Raises:
            Exception: Inherited initialization or analysis metadata publication fails.
                The initialization flag is reset before the exception is propagated.
        """
        if self._roi_connection_initialized:
            return
        try:
            super().on_connected()
            self._publish_available_analysis()
        except Exception:
            self._roi_connection_initialized = False
            raise

    def _configuration_message(self) -> ROIConfigurationMessage:
        """
        Add the current analysis selection to the complete ROI snapshot.

        Returns:
            ROIConfigurationMessage: The inherited shape/name/enablement snapshot with a
                copied list of selected processing operations.
        """
        message = super()._configuration_message()
        message.selected_operations = list(self.selected_operations.get())
        return message

    def _validate_selected_operations(self, operations: list[str]) -> None:
        """
        Check an analysis selection against this backend's advertised operations.

        Args:
            operations (list[str]): Proposed operation names.

        Raises:
            ValueError: Any requested operation is not available on this backend.
        """
        self.selected_operations.check_value(operations)

    def _on_config_update(self, value: ROIConfigurationMessage, **kwargs) -> None:
        """
        Record the applied shape, enablement, name and processing selection.

        Backend subclasses apply hardware settings before calling this implementation.
        Configuration validation is inherited from ROI; publication is performed by the
        request application path after the complete update succeeds.

        Args:
            value (ROIConfigurationMessage): Complete configuration applied to the backend.
            **kwargs (Any): Additional application context forwarded to ROI.
        """
        super()._on_config_update(value, **kwargs)
        Signal.put(self.selected_operations, value.selected_operations, force=True)

    def _update_result_signal_names(self):
        """
        Initialize dynamic result schemas from the subclass's declared output names.

        Declare every possible result in get_scalar_outputs() and get_waveform_outputs(),
        including results belonging to currently unselected operations. This keeps signal
        metadata discoverable before any acquisition has produced data.
        """
        # pylint: disable=protected-access
        self.result_scalar.signals = self.result_scalar._unify_signals(self.get_scalar_outputs())
        self.result_waveform.signals = self.result_waveform._unify_signals(
            self.get_waveform_outputs()
        )

    def put_results(
        self,
        kind: Literal["scalar", "waveform"],
        results: dict[str, dict[str, Any]],
        async_update: dict[str, Any] | None = None,
    ) -> None:
        """
        Publish a result subset using the output names declared by this backend.

        DynamicSignal names a single output after the signal itself. Translate that
        convention here so backend code can use the same short result names for one
        or several outputs. Preserve the dynamic signal's schema and validation.

        Args:
            kind (Literal["scalar", "waveform"]): Result stream receiving this update.
            results (dict[str, dict[str, Any]]): Declared output names mapped to value
                and timestamp dictionaries. An empty mapping publishes nothing.
            async_update (dict[str, Any] | None): Optional append/index metadata.
                None keeps the selected dynamic signal's configured metadata.

        Raises:
            ValueError: The stream kind or any result name is unsupported.
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
        payload = {signal.name: results[outputs[0]]} if len(outputs) == 1 else dict(results)
        signal.put(payload, async_update=async_update)

    @abstractmethod
    def get_scalar_outputs(self) -> list[str]:
        """
        Declare every scalar result supported by this backend.

        Implementations must include outputs of unselected operations as well as selected
        ones. This method is called during construction and must not communicate with
        hardware or depend on acquired data.

        Returns:
            list[str]: Scalar result names used to build result_scalar's dynamic schema.
                Return an empty list when the backend has no scalar results.
        """

    @abstractmethod
    def get_waveform_outputs(self) -> list[str]:
        """
        Declare every waveform result supported by this backend.

        Include outputs of all available operations. This method is called during
        construction and must not communicate with hardware or depend on acquired data.

        Returns:
            list[str]: Waveform result names used to build result_waveform's dynamic schema.
                Return an empty list when the backend has no waveform results.
        """

    @abstractmethod
    def get_available_analysis_operations(self) -> list[str]:
        """
        Declare the analysis operations that users may select.

        The selection signal uses this method for validation, and the metadata publisher
        uses it for discovery. Implementations must not require hardware communication.

        Returns:
            list[str]: Supported operation names, including currently unselected operations.
        """

    def compile_roi_analysis_config(self) -> ROIAnalysisConfig:
        """
        Build discovery metadata for supported operations and result streams.

        Returns:
            ROIAnalysisConfig: Available operation names and the complete scalar/waveform
                output schemas. No backend acquisition or publication is performed.
        """
        return ROIAnalysisConfig(
            available_operations=self.get_available_analysis_operations(),
            waveform_results=self.get_waveform_outputs(),
            scalar_results=self.get_scalar_outputs(),
        )

    def _publish_available_analysis(self) -> None:
        """
        Publish processing capabilities on this ROI's analysis discovery endpoint.

        Advertise all supported operations and results independently of the current
        selection, so clients can offer configuration and plotting controls.

        Raises:
            RuntimeError: No Redis connector has been assigned during connection setup.
            Exception: Compiling or publishing analysis metadata fails.
        """
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
