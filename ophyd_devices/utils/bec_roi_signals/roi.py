"""
Backend-independent ROI configuration requests, validation and publication.
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from bec_lib.endpoints import MessageEndpoints
from bec_lib.logger import bec_logger
from bec_lib.messages import RectROIConfig, ROIConfiguration, ROIConfigurationMessage
from bec_lib.redis_connector import RedisConnector
from ophyd import Component, Device, Kind, Signal
from pydantic import BaseModel, TypeAdapter

from ophyd_devices.utils.bec_roi_signals.geometry import ROIGeometryComponent
from ophyd_devices.utils.bec_roi_signals.signals import ConfigUpdateReceivedSignal, ROIConfigSignal
from ophyd_devices.utils.psi_device_base_utils import destroy_subdevices

if TYPE_CHECKING:
    from bec_lib.connector import MessageObject

logger = bec_logger.logger


class ROI(Device):
    """
    Configure backend ROIs without creating processing or result signals.

    The owning device explicitly calls on_connected after connecting its signals.
    Requests arrive through update_received or the user-scoped Redis request
    endpoint. Scan-time deferral, validation, failure propagation and publication
    of applied configuration are shared with ROIProcessing.

    A backend overrides _on_config_update to send the complete typed configuration
    to its controller, then calls super() to record it after successful application.
    Override validate_configuration for backend constraints, calling super() first.
    No analysis methods are required. Use ROIProcessing when this component also
    computes or publishes ROI results. allowed_roi_config_types restricts initial
    and requested shapes, for example [RectROIConfig, CircleROIConfig]. None allows
    every ROI shape supported by BEC.

    The read-only geometry subdevice exposes the applied shape as native configuration
    signals, including type, scalar coordinates and array-valued masks or vertices.
    Its fields are fixed by the permitted schemas at construction and included in
    read_configuration. Changes go through update_received, never individual fields.

    Declare a backend subclass as a normal device component::

        roi1 = Component(
            BackendROI, "", roi_config=RectROIConfig(x=0, y=0, width=100, height=100),
            allowed_roi_config_types=[RectROIConfig, CircleROIConfig],
        )
    """

    _default_configuration_attrs = None

    active = Component(ROIConfigSignal, config_key="active", value=False, kind=Kind.config)
    roi_name = Component(ROIConfigSignal, config_key="name", value="roi", kind=Kind.config)
    geometry = ROIGeometryComponent(kind=Kind.config)
    update_received = Component(ConfigUpdateReceivedSignal, kind=Kind.omitted)

    def __init__(
        self,
        *args: Any,
        roi_config: ROIConfiguration | dict | None = None,
        active: bool = False,
        roi_name: str = "roi",
        allowed_roi_config_types: Sequence[type[ROIConfiguration]] | None = None,
        **kwargs: Any,
    ) -> None:
        """
        Create an ROI configuration component without communicating with its backend.

        The initial shape is validated and copied immediately. Signal defaults, Redis
        subscriptions and backend configuration are applied later by on_connected().
        There are no coordinate mirrors, analysis methods or result signals.

        Args:
            *args (Any): Positional arguments forwarded to ophyd.Device, usually the
                component's PV prefix.
            roi_config (ROIConfiguration | dict | None): Initial typed ROI shape or
                discriminated shape dictionary. None selects an empty RectROIConfig.
                Supply an explicit initial shape if rectangles are not allowed.
            active (bool): Initial backend enablement, applied after connection.
                Defaults to False. Inactive configurations are also sent to the backend.
            roi_name (str): Initial human-readable name. Defaults to "roi".
            allowed_roi_config_types (Sequence[type[ROIConfiguration]] | None): Accepted
                shape classes, such as [RectROIConfig, CircleROIConfig]. The sequence is
                copied to a tuple. None allows all shapes supported by BEC.
            **kwargs (Any): Remaining ophyd.Device arguments, including name, parent,
                kind and connection options.

        Raises:
            ValueError: The allowed-type sequence is empty.
            TypeError: An allowed type is not a model class, or the initial shape is
                excluded by allowed_roi_config_types.
            pydantic.ValidationError: The initial shape does not match a BEC ROI schema.
        """
        self.allowed_roi_config_types = (
            tuple(allowed_roi_config_types) if allowed_roi_config_types is not None else None
        )
        if self.allowed_roi_config_types is not None:
            if not self.allowed_roi_config_types:
                raise ValueError("allowed_roi_config_types must not be empty")
            if any(
                not isinstance(cls, type) or not issubclass(cls, BaseModel)
                for cls in self.allowed_roi_config_types
            ):
                raise TypeError("allowed_roi_config_types must contain ROI configuration classes")
        self._roi_config = (
            TypeAdapter(ROIConfiguration)
            .validate_python(
                roi_config if roi_config is not None else RectROIConfig(x=0, y=0, width=0, height=0)
            )
            .model_copy(deep=True)
        )
        self._validate_roi_config_type(self._roi_config)
        super().__init__(*args, **kwargs)
        self._record_geometry(self._roi_config)
        self._signal_kwargs = {"active": active, "roi_name": roi_name}
        self._connector: RedisConnector | None = None
        self._roi_connection_initialized = False
        self._config_registered = False

    def on_connected(self) -> None:
        """
        Connect ROI configuration and apply its initial state once per instance.

        The owning device calls this method explicitly after its signals connect.
        The root must provide device_manager.connector. Initialization proceeds as follows:

        1. Subscribe the request signal to scan status for deferred updates.
        2. Apply constructor defaults and subscribe to user-scoped ROI requests.
        3. Validate and send the complete initial configuration to the backend, including
           inactive configurations.
        4. Publish the applied state and mark initialization complete.

        Repeated successful calls do nothing. A failed call may be retried without
        registering duplicate request subscriptions.

        Raises:
            RuntimeError: The root has no Redis connector.
            TypeError: The initial shape is not supported by this component.
            ValueError: Configuration validation fails.
            Exception: Backend application or Redis registration/publication fails.
        """
        if self._roi_connection_initialized:
            return
        self._connector: RedisConnector | None = (
            self.root.device_manager.connector if hasattr(self.root, "device_manager") else None
        )
        if self._connector is None:
            raise RuntimeError(f"ROI {self.name} requires a device_manager with a Redis connector.")
        self.update_received.on_connected()
        # Setup initial values for the signal as provided in the kwargs during initialization
        for signal_name, value in self._signal_kwargs.items():
            signal = getattr(self, signal_name)
            Signal.put(signal, value, force=True)

        # Subscribe to every submitting user's request channel. Redis ACLs scope
        # client publication; the device server receives requests as a pattern.
        if not self._config_registered:
            self._connector.register(
                patterns=MessageEndpoints.roi_config_request(
                    device=self.root.name, signal=self.dotted_name, username="*"
                ),
                cb=self._receive_roi_configuration_message,
            )
            self._config_registered = True
        # Send inactive configurations too, so the backend cannot retain a stale ROI.
        configuration = self._configuration_message()
        self.validate_configuration(configuration)
        self._on_config_update(configuration)
        self._publish_configuration()
        self._roi_connection_initialized = True

    def destroy(self) -> None:
        """
        Release request and scan-status subscriptions and destroy child signals.

        The request subscription uses the same user wildcard as on_connected(). Child
        cleanup releases the request signal's scan-status subscription. Repeated calls
        are harmless after successful destruction. Backend acquisition shutdown remains
        owned by the detector; this method does not send a backend disable command.
        Attempt child cleanup even when Redis unregistration fails, then propagate
        the first error with any additional cleanup failures attached as notes.
        """
        if self._destroyed:
            return
        errors = []
        if self._connector is not None and self._config_registered:
            try:
                self._connector.unregister(
                    patterns=MessageEndpoints.roi_config_request(
                        device=self.root.name, signal=self.dotted_name, username="*"
                    ),
                    cb=self._receive_roi_configuration_message,
                )
            except Exception as error:  # noqa: BLE001 - finish child cleanup as well.
                errors.append(error)
            else:
                self._config_registered = False
        for cleanup in (lambda: destroy_subdevices(self), super().destroy):
            try:
                cleanup()
            except Exception as error:  # noqa: BLE001 - finish cleanup before reporting.
                errors.append(error)
        if errors:
            for error in errors[1:]:
                errors[0].add_note(f"Additional ROI cleanup failure: {error!r}")
            raise errors[0]

    def _configuration_message(self) -> ROIConfigurationMessage:
        """
        Build a snapshot of the locally recorded ROI configuration.

        The shape is copied so consumers cannot mutate the stored configuration. The
        snapshot includes the current name, enablement and a publication timestamp;
        configuration-only ROIs advertise no selected analysis operations.

        Returns:
            ROIConfigurationMessage: A complete configuration addressed to this root
                device and component. This method does not query the backend.
        """
        return ROIConfigurationMessage(
            metadata={"timestamp": time.time()},
            device=self.root.name,
            signal=self.dotted_name,
            name=self.roi_name.get(),
            active=bool(self.active.get()),
            roi_config=self._roi_config.model_copy(deep=True),
            selected_operations=[],
        )

    def validate_configuration(self, value: ROIConfigurationMessage) -> None:
        """
        Validate a request before it can be queued or applied to the backend.

        Check the target device/component, allowed shape classes and supported analysis
        operations. Backend subclasses may add constraints after calling super(). Keep
        validation free of backend writes; it also runs for requests held during scans.

        Args:
            value (ROIConfigurationMessage): Complete proposed ROI configuration.

        Raises:
            TypeError: value has the wrong message type or contains a disallowed shape.
            ValueError: The target does not match this ROI or analysis operations are
                unsupported. ROIProcessing validates against its advertised operations.
        """
        if not isinstance(value, ROIConfigurationMessage):
            raise TypeError("Expected ROIConfigurationMessage")
        if value.device != self.root.name or value.signal != self.dotted_name:
            raise ValueError("ROI configuration target does not match this ROI")
        self._validate_roi_config_type(value.roi_config)
        self._validate_selected_operations(value.selected_operations)

    def _validate_roi_config_type(self, config: ROIConfiguration) -> None:
        """
        Check a shape against the component's configured class restriction.

        Args:
            config (ROIConfiguration): An already schema-validated BEC ROI shape.

        Raises:
            TypeError: The shape is not an instance of any allowed class. No restriction
                is applied when allowed_roi_config_types is None.
        """
        if self.allowed_roi_config_types is not None and not isinstance(
            config, self.allowed_roi_config_types
        ):
            allowed = ", ".join(cls.__name__ for cls in self.allowed_roi_config_types)
            raise TypeError(f"This ROI only supports {allowed}; received {type(config).__name__}")

    def _validate_selected_operations(self, operations: list[str]) -> None:
        """
        Reject analysis selections on a configuration-only ROI.

        ROIProcessing overrides this method to validate its available operations.

        Args:
            operations (list[str]): Proposed analysis operation names. An empty list is
                the only supported selection for a configuration-only component.

        Raises:
            ValueError: One or more analysis operations were requested.
        """
        if operations:
            raise ValueError("Configuration-only ROI does not support analysis operations")

    def _publish_configuration(self) -> None:
        """
        Publish the current applied state on this ROI's configuration endpoint.

        Publish a complete snapshot with a new timestamp, rather than the pending
        request. The method does nothing until a Redis connector has been assigned.
        Redis errors propagate to the caller so publication failure is observable.
        """
        if self._connector is not None:
            self._connector.set_and_publish(
                MessageEndpoints.roi_config(device=self.root.name, signal=self.dotted_name),
                self._configuration_message(),
            )

    def _apply_requested_config(self, value: ROIConfigurationMessage, **kwargs) -> None:
        """
        Validate, apply and publish one complete ROI configuration.

        Called by update_received when a request is eligible for application. Backend
        application must finish successfully before the confirmed state is published.
        Exceptions propagate to the request signal, which reports failure or retains a
        failed deferred request for retry.

        Args:
            value (ROIConfigurationMessage): Configuration already selected for immediate
                application or released from the deferred-update queue.
            **kwargs (Any): Additional application context forwarded to _on_config_update.

        Raises:
            Exception: Validation, backend application or configuration publication fails.
        """
        self.validate_configuration(value)
        self._on_config_update(value, **kwargs)
        self._publish_configuration()

    def _receive_roi_configuration_message(self, message: MessageObject) -> None:
        """
        Route a Redis configuration request through the scan-aware request signal.

        Requests addressed to a different device or component are logged and ignored.
        Matching requests follow the same validation and deferral path as direct writes
        of update_received; backend failures propagate to the connector callback boundary.

        Args:
            message (MessageObject): Redis envelope whose value is an
                ROIConfigurationMessage for the requested device and component.
        """
        message: ROIConfigurationMessage = message.value
        if message.device != self.root.name or message.signal != self.dotted_name:
            logger.warning(
                f"Ignoring ROI configuration for {message.device}.{message.signal}; "
                f"this ROI is {self.root.name}.{self.dotted_name}."
            )
            return
        self.update_received.put(message)

    def _on_config_update(self, value: ROIConfigurationMessage, **kwargs: Any) -> None:
        """
        Record a configuration after successful backend application.

        A backend subclass overrides this method to send the full configuration to its
        controller, then calls super() after that operation succeeds. This implementation
        validates the request, updates name/enablement and stores a copied shape. It does
        not communicate with hardware or publish the configuration itself.

        Args:
            value (ROIConfigurationMessage): Complete configuration applied to the backend.
            **kwargs (Any): Additional application context; unused by this implementation.

        Raises:
            TypeError: The message or shape is unsupported.
            ValueError: The target or analysis selection is invalid.
        """
        self.validate_configuration(value)
        Signal.put(self.active, value.active, force=True)
        Signal.put(self.roi_name, value.name, force=True)
        self._record_geometry(value.roi_config)

    def _record_geometry(self, config: ROIConfiguration) -> None:
        """
        Record applied geometry and update its read-only configuration subdevice.

        Call after successful backend application or when confirmed backend readbacks
        change. The typed shape is copied locally; geometry exposes its fields as
        native scalars and arrays. This keeps read_configuration
        and describe_configuration usable before the first acquisition and preserves
        geometry in scan metadata without writable coordinate mirrors.

        Args:
            config (ROIConfiguration): Validated shape confirmed by the backend, or
                the initial constructor geometry before connection.
        """
        self._roi_config = config.model_copy(deep=True)
        self.geometry._record(self._roi_config)
