"""
ROI operation selection and scan-aware configuration request signals.
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Any

from bec_lib.endpoints import MessageEndpoints
from bec_lib.logger import bec_logger
from bec_lib.messages import ROIConfigurationMessage, ScanStatusMessage
from ophyd import Signal, SignalRO

from ophyd_devices.utils.psi_device_base_utils import StatusBase

if TYPE_CHECKING:
    from bec_lib.redis_connector import MessageObject, RedisConnector

logger = bec_logger.logger


class ROIConfigSignal(Signal):
    """
    Apply an individual setting through the parent's complete configuration request.

    Direct writes require a connected ROI and reject scan/capture locks. They apply
    backend configuration before changing local readbacks or publishing applied state.
    Backend observations use Signal.put directly to avoid generating another request.
    """

    def __init__(self, *, config_key: str, **kwargs: Any) -> None:
        """
        Declare a local control for one field of ROIConfigurationMessage.

        Args:
            config_key (str): Message field updated by this signal, such as "active",
                "name" or "selected_operations".
            **kwargs (Any): Standard ophyd.Signal constructor options.
        """
        self._config_key = config_key
        super().__init__(**kwargs)

    def put(self, value, **kwargs):
        """
        Validate and apply a complete configuration with this setting replaced.

        Args:
            value (Any): Proposed local setting value.
            **kwargs (Any): Options forwarded to the configuration request signal.

        Raises:
            RuntimeError: Configuration is locked. Submit a complete configuration
                through update_received to defer the change instead.
        """
        requests = self.parent.update_received
        with requests._update_lock:
            if requests.updates_blocked:
                raise RuntimeError(
                    f"ROI configuration is locked: {self.name} cannot change during a scan. "
                    "Submit a complete configuration through update_received to defer it."
                )
            self.check_value(value)
            values = self.parent._configuration_message().model_dump()
            values[self._config_key] = value
            configuration = ROIConfigurationMessage.model_validate(values)
            return requests.put(configuration, **kwargs)

    def set(self, value, *, timeout=None, settle_time=None, **kwargs):
        """
        Apply a setting and report backend, validation or lock failures on its status.

        Success means the parent's configuration application and publication returned
        successfully. This method does not merely acknowledge a local soft-signal edit.

        Args:
            value (Any): Requested local setting value.
            timeout (float | None): Timeout for the returned status.
            settle_time (float | None): Delay before successful status completion.
            **kwargs (Any): Options forwarded to put.

        Returns:
            StatusBase: Configuration application result, preserving the original failure.
        """
        status = StatusBase(self, timeout=timeout, settle_time=settle_time or 0)
        try:
            self.put(value, **kwargs)
        except Exception as error:  # noqa: BLE001 - expose original failure through status.
            status.set_exception(error)
        else:
            status.set_finished()
        return status


class SelectedOperationSignal(ROIConfigSignal):
    """
    Validate a processing ROI's selected analysis operations.

    The parent component must implement get_available_analysis_operations(). The
    signal stores operation names only; the parent owns backend enablement and result
    publication. Configuration-only ROI components do not instantiate this signal.
    """

    def check_value(self, value: list[str], **kwargs):
        """
        Check that every selected operation is available on the parent component.

        Args:
            value (list[str]): Requested operation names; an empty selection is valid.
            **kwargs (Any): Additional validation context accepted for signal compatibility.

        Returns:
            list[str]: The validated input selection.

        Raises:
            ValueError: Any operation is absent from the parent's available operations.
        """
        available_operations = self.parent.get_available_analysis_operations()
        if not all(v in available_operations for v in value):
            raise ValueError(
                f"Invalid operation(s): {value}. Must be one of {available_operations}."
            )
        return value


class AvailableOperationsSignal(SignalRO):
    """
    Expose a processing ROI's supported analysis operations as a read-only signal.

    Values are obtained from the parent's get_available_analysis_operations() method
    when read, rather than from stored signal data. The parent must provide that method
    without depending on an acquisition having completed.
    """

    def get(self, **kwargs):
        """
        Read available operation names from the parent component.

        Args:
            **kwargs (Any): Signal-read options accepted for compatibility; unused here.

        Returns:
            list[str]: All analysis operations supported by the parent backend.
        """
        return self.parent.get_available_analysis_operations()


class ConfigUpdateReceivedSignal(Signal):
    """
    Accept complete ROI configuration requests and defer them during scans.

    The parent ROI component validates targets, allowed shape types and operations,
    then applies backend settings and publishes the confirmed configuration. This
    signal owns only request acceptance, scan locking and the latest deferred request.
    A newer blocked request replaces the previous one. Setting block_while_scanning
    False on a request explicitly bypasses deferral.

    Backend application runs synchronously in the caller's thread. Immediate failures
    propagate from put() or are recorded in the status returned by set(). A successful
    set() while blocked means the request was queued, not that it reached the backend.
    """

    def __init__(self, name, parent=None, **kwargs):
        """
        Create local request state without connecting to Redis or the backend.

        Args:
            name (str): Ophyd signal name.
            parent (ROI | None): Owning ROI component providing validate_configuration()
                and _apply_requested_config(). A parent is required before requests are used.
            **kwargs (Any): Remaining ophyd.Signal constructor arguments.
        """
        # A request is one opaque message, not an array of its Pydantic fields.
        # Match BECMessageSignal: metadata must not infer shape from the payload.
        kwargs.pop("shape", None)
        super().__init__(name=name, parent=parent, shape=(), **kwargs)
        self._update_received = False
        self._connector: RedisConnector | None = None
        self._next_config = None
        self._next_config_kwargs = None
        self._update_blocks: set[str] = set()
        self._update_lock = threading.RLock()

    @property
    def updates_blocked(self) -> bool:
        """
        Report whether ordinary requests are currently deferred.

        Returns:
            bool: True while any scan, capture or manual owner blocks updates. Requests with
                block_while_scanning=False may still be applied while this flag is True.
        """
        return bool(self._update_blocks)

    @property
    def has_pending_update(self) -> bool:
        """
        Report whether a deferred request is waiting for application or retry.

        Returns:
            bool: True when a request was queued or a deferred application failed.
        """
        return self._update_received

    @property
    def next_config(self):
        """
        Inspect the latest deferred request without applying or removing it.

        Returns:
            ROIConfigurationMessage | None: The pending request, or None when no request
                is queued. This property returns the stored object, not a copy.
        """
        return self._next_config

    def destroy(self):
        """
        Unregister the scan-status callback and destroy the underlying signal.

        This releases only request-signal resources. The parent component owns its ROI
        request subscription and backend cleanup.
        """
        try:
            if self._connector is not None:
                self._connector.unregister(
                    MessageEndpoints.scan_status(), cb=self._handle_scan_status_update
                )
        finally:
            self._connector = None
            super().destroy()

    def on_connected(self) -> None:
        """
        Subscribe to scan status after the parent device has connected.

        Called explicitly by ROI.on_connected(). The root must provide a
        device_manager.connector. Read the current scan status after subscribing so
        connection during an open or paused scan is locked immediately. Repeated
        successful calls do not register twice.

        Raises:
            RuntimeError: The root has no Redis connector.
            Exception: Registering the scan-status callback fails.
        """
        if self._connector is not None:
            return
        connector: RedisConnector | None = (
            self.root.device_manager.connector if hasattr(self.root, "device_manager") else None
        )
        if connector is None:
            raise RuntimeError(
                f"Signal {self.name} is not connected to Redis, please provide a Redis Connector during the initialization."
            )
        with self._update_lock:
            connector.register(MessageEndpoints.scan_status(), cb=self._handle_scan_status_update)
            try:
                current = connector.get(MessageEndpoints.scan_status())
            except Exception:
                connector.unregister(
                    MessageEndpoints.scan_status(), cb=self._handle_scan_status_update
                )
                raise
            self._connector = connector
            if isinstance(current, ScanStatusMessage) and current.status in ("open", "paused"):
                self.block_updates(owner="scan")

    def _handle_scan_status_update(self, message: MessageObject):
        """
        Block requests while a scan is open and release them when it ends.

        Open and paused statuses own a scan lock, including when connecting during
        an existing scan. Other statuses release only that lock and attempt the latest
        pending request when no capture/manual lock remains.

        Args:
            message (MessageObject): Redis envelope containing a ScanStatusMessage.

        Raises:
            Exception: Applying or publishing a released request fails. The request is
                retained for a later retry.
        """
        msg: ScanStatusMessage = message.value
        if msg.status in ("open", "paused"):
            self.block_updates(owner="scan")
        else:
            self.unblock_updates(owner="scan")

    def block_updates(self, *, owner: str = "manual") -> None:
        """
        Defer subsequent ordinary configuration requests until updates are released.

        Calling this method again preserves the latest pending request. Validation still
        runs when a new request arrives, and requests explicitly opting out of scan
        blocking continue to be applied immediately. Owners are independent: capture
        shutdown cannot release the scan-status lock.

        Args:
            owner (str): Lock owner. Defaults to "manual" for explicit callers;
                camera capture uses "capture" and scan status uses "scan".
        """
        with self._update_lock:
            self._update_blocks.add(owner)

    def unblock_updates(self, *, owner: str = "manual"):
        """
        Release deferral and apply the latest pending configuration, if present.

        Backend application and publication run before the signal's accepted value is
        updated. If application fails, restore the pending request so it can be retried.
        Only this owner's lock is released. Pending requests remain deferred until
        every owner has released its lock, even if capture stops before the scan ends.
        A failed application remains queued for retry.

        Args:
            owner (str): Owner to release; defaults to "manual".

        Returns:
            ROIConfigurationMessage | None: The request applied successfully, or None if
                there was no pending request.

        Raises:
            Exception: Backend application, publication or signal notification fails.
        """
        with self._update_lock:
            self._update_blocks.discard(owner)
            if self.updates_blocked or not self._update_received:
                return None

            value = self._next_config
            kwargs = self._next_config_kwargs or {}
            self._next_config = None
            self._next_config_kwargs = None
            self._update_received = False

            try:
                self.parent._apply_requested_config(value)
                super().put(value, **kwargs)
            except Exception:
                self._next_config = value
                self._next_config_kwargs = {
                    "timestamp": None,
                    "force": False,
                    "metadata": None,
                    "timeout": None,
                }
                self._update_received = True
                raise
            return value

    def put(
        self,
        value: ROIConfigurationMessage,
        *,
        timestamp=None,
        force=False,
        metadata=None,
        timeout=None,
        **kwargs,
    ):
        """
        Validate a complete request, then apply it or retain it until the scan ends.

        When updates are blocked, keep only the newest request unless its
        block_while_scanning flag is False. Immediate application calls the parent backend
        and publishes confirmed state before updating this signal's value. Queuing does
        not update the signal's accepted value. A successful immediate request supersedes
        any older request still pending after a deferred application failure.

        Args:
            value (ROIConfigurationMessage): Full target, name, enablement, typed shape
                and analysis selection requested by the caller.
            timestamp (float | None): Timestamp for the accepted signal value. None uses
                the signal's default timestamp behavior.
            force (bool): Forwarded to ophyd.Signal.put(). Parent configuration validation
                is always performed, including when force is True.
            metadata (dict | None): Metadata associated with the accepted signal value.
            timeout (float | None): Signal-write option forwarded to ophyd.Signal.put().
                This does not impose a timeout on the parent's backend implementation.
            **kwargs (Any): Additional signal-write options retained with deferred requests
                or forwarded to ophyd.Signal.put().

        Raises:
            RuntimeError: on_connected() has not assigned a Redis connector.
            ValueError: The input is not a configuration message or its target/operations
                fail parent validation.
            TypeError: The parent rejects the requested ROI shape.
            Exception: Immediate backend application or publication fails.
        """
        if self._connector is None:
            raise RuntimeError(
                f"Signal {self.name} is not connected to Redis and cannot publish updates."
            )
        with self._update_lock:
            self.check_value(value)
            if value.block_while_scanning is False or not self.updates_blocked:
                self.parent._apply_requested_config(value)
                super().put(
                    value,
                    timestamp=timestamp,
                    force=force,
                    metadata=metadata,
                    timeout=timeout,
                    **kwargs,
                )
                # A newer applied edit supersedes any failed or deferred request.
                self._next_config = None
                self._next_config_kwargs = None
                self._update_received = False
                return

            self._next_config = value
            self._next_config_kwargs = dict(
                timestamp=timestamp, force=force, metadata=metadata, timeout=timeout, **kwargs
            )
            self._update_received = True

    def set(self, value, *, timeout=None, settle_time=None, **kwargs):
        """
        Submit a configuration request and return a status describing its acceptance.

        Calls put() synchronously. When unblocked, success means backend application and
        publication returned successfully. When blocked, success means the request was
        queued; the status does not wait for its eventual application. Exceptions raised
        by put() are recorded on the returned status.

        Args:
            value (ROIConfigurationMessage): Complete configuration request.
            timeout (float | None): Timeout for the returned status. It does not cancel
                backend work or forward a backend timeout to put().
            settle_time (float | None): Delay before successful status completion; None
                is treated as zero.
            **kwargs (Any): Additional keyword arguments forwarded to put().

        Returns:
            StatusBase: Request acceptance/application status. A backend or validation error
                can be retrieved by waiting on the status.
        """
        status = StatusBase(self, timeout=timeout, settle_time=settle_time or 0)
        try:
            self.put(value, **kwargs)
        except Exception as exc:  # noqa: BLE001 - propagate failures through the status.
            status.set_exception(exc)
        else:
            status.set_finished()
        return status

    def check_value(self, value, **kwargs):
        """
        Validate the message and delegate backend-specific checks to the owning ROI.

        Validation is performed before a blocked request can replace an existing pending
        request. This method does not write to the backend or change signal state.

        Args:
            value (ROIConfigurationMessage): Proposed configuration request.
            **kwargs (Any): Additional validation context forwarded to ophyd.Signal.

        Raises:
            ValueError: value is not an ROIConfigurationMessage, or the parent rejects
                its target or processing operations.
            TypeError: The parent rejects the configured shape class.
        """
        if not isinstance(value, ROIConfigurationMessage):
            raise ValueError(  # noqa: TRY004 - preserve the existing validation exception.
                f"Invalid value: {value}. Must be an instance of ROIConfigurationMessage."
            )
        self.parent.validate_configuration(value)
        super().check_value(value, **kwargs)
