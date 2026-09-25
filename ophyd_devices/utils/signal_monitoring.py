"""Utility class for monitoring signals in ophyd devices."""

from __future__ import annotations

import threading
import uuid
from typing import Callable

from bec_lib.logger import bec_logger
from ophyd import Signal

logger = bec_logger.logger


class SignalMonitoring:
    """
    This class allows you to register Signal instances or callables that will be polled
    with a specified interval. The interval can be customized. The monitoring may be started
    and stopped when needed, and will happen in a separate thread.

    In general, it should be used with ophyd.Signal instances, but it also accepts a callable
    in case a certain 'script' method needs to be called in order to update a signal.

    """

    def __init__(self, name: str = "SignalMonitoring"):
        self.name = name
        self._signal_instances = {}
        self._callables = {}
        self._lock = threading.RLock()
        self._poll_thread = threading.Thread(target=self._poll_signals, daemon=True)
        self._kill_event = threading.Event()
        self._start_poll_event = threading.Event()
        self._polling_interval_event = threading.Event()
        self._polling_interval = 0.1  # seconds
        self._poll_thread.start()

    @property
    def polling_interval(self):
        """Polling interval in seconds."""
        return self._polling_interval

    @polling_interval.setter
    def polling_interval(self, value: float):
        if value <= 0:
            raise ValueError("Polling interval must be positive.")
        self._polling_interval = value

    def _poll_signals(self):
        """Poll loop that checks registered signals and callables at the specified interval."""
        while (
            self._start_poll_event.wait() and not self._kill_event.is_set()
        ):  # Wait until polling is started
            self._polling_interval_event.wait(
                timeout=self._polling_interval
            )  # Poll at the specified interval
            with self._lock:
                try:
                    for signal in self._signal_instances.values():
                        signal.get()
                    for call in self._callables.values():
                        call()
                except Exception as e:
                    logger.error(f"Error while polling signals: {e}")

    def register_signal(self, signal: Signal | Callable[[], None]) -> str:
        """
        Register a Signal instance or a callable to be monitored.

        Args:
            signal (Signal | Callable[[], None]): The Signal instance or callable to register.
        """
        callback_id = str(uuid.uuid4())
        with self._lock:
            if isinstance(signal, Signal):
                self._signal_instances[callback_id] = signal
            elif callable(signal):
                self._callables[callback_id] = signal
            else:
                raise ValueError(
                    f"Only Signal instances or callables can be registered, got {type(signal)}."
                )
        return callback_id

    def remove_signal(self, callback_id: str):
        """
        Remove a registered signal or callable by its callback ID.

        Args:
            callback_id (str): The unique ID of the signal or callable to remove.
        """
        with self._lock:
            if callback_id in self._signal_instances:
                del self._signal_instances[callback_id]
            elif callback_id in self._callables:
                del self._callables[callback_id]
            else:
                logger.warning(
                    f"Callback ID {callback_id} not found in registered signals or callables."
                )

    def start(self):
        """Start the polling thread to monitor registered signals and callables."""
        self._start_poll_event.set()

    def stop(self):
        """Stop the polling thread without shutting it down."""
        self._start_poll_event.clear()

    def shutdown(self):
        """Shutdown the monitoring thread and clean up resources."""
        with self._lock:
            self._callables.clear()
            self._signal_instances.clear()
        self._kill_event.set()
        self._start_poll_event.set()  # Ensure the polling thread is not waiting
        self._polling_interval_event.set()  # Ensure the polling thread is not waiting
        self._poll_thread.join()
