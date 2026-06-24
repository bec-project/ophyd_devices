from __future__ import annotations

import threading
from typing import TYPE_CHECKING

from bec_lib.endpoints import MessageEndpoints
from bec_lib.logger import bec_logger
from bec_lib.messages import ROIConfigurationMessage, ScanStatusMessage
from ophyd import Signal, SignalRO
from ophyd.status import Status

if TYPE_CHECKING:
    from bec_lib.redis_connector import MessageObject, RedisConnector

logger = bec_logger.logger


class SelectedOperationSignal(Signal):
    """
    Signal for selecting ROI analysis operations.

    The parent class must implement ``get_available_analysis_operations()``.
    """

    def check_value(self, value: list[str], **kwargs):
        """Check that all selected operations are available."""
        available_operations = self.parent.get_available_analysis_operations()
        if not all(v in available_operations for v in value):
            raise ValueError(
                f"Invalid operation(s): {value}. Must be one of {available_operations}."
            )
        return value


class AvailableOperationsSignal(SignalRO):
    """
    Signal for providing the available ROI analysis operations.

    The parent class must implement ``get_available_analysis_operations()``.
    """

    def get(self, **kwargs):
        """Return the list of available operations."""
        return self.parent.get_available_analysis_operations()


class ConfigUpdateReceivedSignal(Signal):
    """
    Signal to publish ROI configuration updates. Based on the updated configuration,
    updates will be published right away or blocked until released.
    """

    def __init__(self, name, parent=None, **kwargs):
        super().__init__(name=name, parent=parent, **kwargs)
        self._update_received = False
        self._connector: RedisConnector | None = None
        self._metadata["connected"] = False
        self._next_config = None
        self._next_config_kwargs = None
        self._updates_blocked = False
        self._update_lock = threading.RLock()

    @property
    def updates_blocked(self) -> bool:
        """Return whether incoming updates are currently held back."""
        return self._updates_blocked

    @property
    def has_pending_update(self) -> bool:
        """Return whether a blocked update is waiting to be published."""
        return self._update_received

    @property
    def next_config(self):
        """Return the latest blocked update without publishing it."""
        return self._next_config

    def destroy(self):
        """Clean up the signal and unregister from Redis."""
        if self._connector is not None and self._metadata.get("connected") is True:
            self._connector.unregister(
                MessageEndpoints.scan_status(), cb=self._handle_scan_status_update
            )
        self._metadata["connected"] = False
        super().destroy()

    @property
    def connected(self) -> bool:
        """Return whether the signal is connected to Redis."""
        if self._destroyed:
            return False
        if self._metadata.get("connected") is not True:
            self.wait_for_connection()
        return self._metadata.get("connected", False)

    def wait_for_connection(self, *args, **kwargs):
        self._connector: RedisConnector | None = (
            self.root.device_manager.connector if hasattr(self.root, "device_manager") else None
        )
        if self._connector is None:
            raise RuntimeError(
                f"Signal {self.name} is not connected to Redis, please provide a Redis Connector during the initialization."
            )
        self._metadata["connected"] = True
        self._connector.register(MessageEndpoints.scan_status(), cb=self._handle_scan_status_update)

    def _handle_scan_status_update(self, message: MessageObject):
        msg: ScanStatusMessage = message.value
        if msg.status == "open":
            self.block_updates()
        elif msg.status != "paused":
            self.unblock_updates()

    def block_updates(self) -> None:
        """Hold back incoming updates until :meth:`unblock_updates` is called."""
        with self._update_lock:
            self._updates_blocked = True

    def unblock_updates(self):
        """Allow updates again and publish the latest update received while blocked."""
        with self._update_lock:
            self._updates_blocked = False
            if not self._update_received:
                return None

            value = self._next_config
            kwargs = self._next_config_kwargs or {}
            self._next_config = None
            self._next_config_kwargs = None
            self._update_received = False

            try:
                super().put(value, **kwargs)
            except Exception:
                self._next_config = value
                self._next_config_kwargs = dict(
                    timestamp=None, force=False, metadata=None, timeout=None
                )
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
        Put a new ROI configuration message to the signal. If updates are currently blocked,
        the update will be cached and published once `unblock_updates` is called. Any subsequent
        updates will overwrite the cached update until updates are unblocked.

        Args:
            value (ROIConfigurationMessage): The new ROI configuration message to put.
        """
        if self._metadata.get("connected") is not True:
            raise RuntimeError(
                f"Signal {self.name} is not connected to Redis and cannot publish updates."
            )
        with self._update_lock:
            self.check_value(value)
            if value.block_while_scanning is False or not self._updates_blocked:
                super().put(
                    value,
                    timestamp=timestamp,
                    force=force,
                    metadata=metadata,
                    timeout=timeout,
                    **kwargs,
                )
                return

            self._next_config = value
            self._next_config_kwargs = dict(
                timestamp=timestamp, force=force, metadata=metadata, timeout=timeout, **kwargs
            )
            self._update_received = True

    def set(self, value, *, timeout=None, settle_time=None, **kwargs):
        """Set the signal value, staging it if updates are currently blocked."""
        status = Status(self, timeout=timeout, settle_time=settle_time or 0)
        try:
            self.put(value, **kwargs)
        except Exception as exc:
            status.set_exception(exc)
        else:
            status.set_finished()
        return status

    def check_value(self, value, **kwargs):
        """Check that the value is a ROI configuration message."""
        if not isinstance(value, ROIConfigurationMessage):
            raise ValueError(
                f"Invalid value: {value}. Must be an instance of ROIConfigurationMessage."
            )
        super().check_value(value, **kwargs)
