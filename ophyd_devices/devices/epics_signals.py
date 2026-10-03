"""
This module contains thin wrappers around the ophyd EpicsSignal and EpicsSignalWithRBV classes
that use the StatusBase object from ophyd_devices to improve handling of timeout errors during
set calls.
"""

import threading
import time
from typing import Any

import numpy as np
from ophyd import EpicsSignal as EpicsSignal_
from ophyd import EpicsSignalRO  # Keep import for EpicsSignalRO be able to import from this module
from ophyd import SignalRO  # Keep import for EpicsSignalRO be able to import from this module
from ophyd import Signal as Signal_
from ophyd.signal import DEFAULT_WRITE_TIMEOUT
from ophyd.utils.epics_pvs import _compare_maybe_enum

from ophyd_devices.utils.psi_device_base_utils import StatusBase


# Custom methods for set calls on signals.
def _wait_for_value(
    signal: Signal_,
    val: Any,
    status: StatusBase,  # Custom addition to allow for external finishing
    logger=None,  # Custom addition to allow for logging using logger from the signal object
    poll_time: float = 0.01,
    rtol: float | None = None,
    atol: float | None = None,
):
    """
    Overwrite of the wait method for set commands on signals. Timeouts are handled by the StatusBase object
    together with any externally initialized abort of the set command. We check the status object for
    external finishing of the set command and break the wait loop if the status is done. This allows for
    more robust handling of timeouts or any other external finishing of the set command.

    Args:
        signal (Signal_): The signal to wait on.
        val (Any): The value to wait for.
        status (StatusBase): The status object of the set command.
        poll_time (float): The time to wait between polls.
        rtol (float | None): The relative tolerance for the value comparison.
        atol (float | None): The absolute tolerance for the value comparison.

    """
    # CUSTOM PART: Removed previous timeout logic here.

    # OPHYD SECTION: copied from OPHYD source code
    get_kwargs = {}
    if isinstance(val, (list, np.ndarray, tuple)):
        get_kwargs["count"] = len(val)
    current_value = signal.get(**get_kwargs)

    if atol is None and hasattr(signal, "tolerance"):
        atol = signal.tolerance
    if rtol is None and hasattr(signal, "rtolerance"):
        rtol = signal.rtolerance

    try:
        enum_strings = signal.enum_strs
    except AttributeError:
        enum_strings = ()

    if atol is not None:
        within_str = [f"within {atol!r}"]
    else:
        within_str = []

    if rtol is not None:
        within_str.append(f"(relative tolerance of {rtol!r})")

    if within_str:
        within_str = " ".join([""] + within_str)
    else:
        within_str = ""

    while (val is not None and current_value is None) or not _compare_maybe_enum(
        val, current_value, enum_strings, atol, rtol
    ):
        # CUSTOM PART: break if status indicates that it is done.
        if status.done is True:
            break

        # OPHYD SECTION: copied from OPHYD source code
        time.sleep(poll_time)
        if poll_time < 0.1:
            poll_time *= 2  # logarithmic back-off
        current_value = signal.get(**get_kwargs)
        # CUSTOM PART: removed previous timeout logic here.


def _set_and_wait(
    signal: Signal_,
    val: Any,
    status: StatusBase,  # Custom addition to allow for external finishing
    logger=None,  # Custom addition to allow for logging using logger from the signal object
    poll_time: float = 0.01,
    rtol: float | None = None,
    atol: float | None = None,
    **kwargs,
):
    """
    Custom method to put a value to a signal,
    and wait for the value to be set using the custom _wait_for_value method.
    """
    signal.put(val, **kwargs)
    _wait_for_value(
        signal, val, status=status, logger=logger, poll_time=poll_time, rtol=rtol, atol=atol
    )


def shared_set_thread(
    signal: Signal_,
    value: Any,
    thread_done_event: threading.Event,
    status: StatusBase | None = None,
    **kwargs,
):
    """
    Shared set thread method for the signal wrapper classes of this module.
    It is used for example by the Signal.set() method to avoid code duplication.

    Args:
        signal (Signal_): The signal to set.
        value (Any): The value to set the signal to.
        timeout (float | None): The timeout for the operation. If not specified, it will use the default write timeout.
        status (StatusBase | None): The status object of the set command. If provided, the method will check if the status has externally finished.
        **kwargs: Additional keyword arguments to pass to the _set_and_wait method.
    """
    try:
        _set_and_wait(
            signal,
            value,
            status=status,
            logger=signal.log,
            atol=signal.tolerance,
            rtol=signal.rtolerance,
            **kwargs,
        )
    except Exception as e:  # pylint: disable=broad-except
        if not status.done:
            status.set_exception(e)
    else:
        if not status.done:
            status.set_finished()
    finally:
        thread_done_event.clear()


class Signal(Signal_):
    """
    Custom Signal class to avoid running into a potential deadlock when
    using the set method with a timeout.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._set_thread_event: threading.Event = threading.Event()

    def set(self, value, *, timeout=None, settle_time=None, **kwargs):
        """
        Custom set method for Signal using the shared_set_thread function to improve error
        and timeout handling and avoid potential deadlocks. Further also improve,
        """

        if self._set_thread_event.is_set():
            raise RuntimeError(f"Another set() call is still in progress for {self.name}")

        status = StatusBase(
            obj=self,
            timeout=timeout,
            settle_time=settle_time,
            description=f"Trying to set signal '{self.name}' to value: {value}.",
        )

        _set_thread = self.cl.thread_class(
            target=shared_set_thread,
            args=(self, value),
            kwargs={"status": status, "thread_done_event": self._set_thread_event, **kwargs},
        )
        _set_thread.daemon = True
        self._set_thread_event.set()  # Signal that a set operation is in progress
        _set_thread.start()
        return status


class EpicsSignal(EpicsSignal_):
    """Custom EpicsSignal class that uses the StatusBase object from ophyd_devices."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._set_thread_event: threading.Event = threading.Event()

    def set(self, value, *, timeout=DEFAULT_WRITE_TIMEOUT, settle_time=None):
        """
        Custom set method for EpicsSignal that uses the StatusBase object from
        ophyd_devices.

        Args:
            value: The value to set the signal to.
            timeout: The timeout for the operation. If not specified, it will
                use the default write timeout.
            settle_time: The time to wait after the put operation before
                considering it complete. If not specified, it will use the
                default settle time.
        Returns:
            A StatusBase object that can be used to monitor the progress of the
            operation.
        """
        if timeout is DEFAULT_WRITE_TIMEOUT:
            timeout = self.write_timeout

        if self._set_thread_event.is_set():
            raise RuntimeError(f"Another set() call is still in progress for {self.name}")

        status = StatusBase(
            obj=self,
            timeout=timeout,
            settle_time=settle_time,
            description=f"Trying to set signal '{self.name}' to value: {value}.",
        )

        if not self._put_complete:
            # Logic basically from Signal.set(), just duplicated due to inheritance

            _set_thread = self.cl.thread_class(
                target=shared_set_thread,
                args=(self, value),
                kwargs={"status": status, "thread_done_event": self._set_thread_event},
            )
            _set_thread.daemon = True
            _set_thread.start()
            return status

        def put_callback(**kwargs):
            # Only call set_finished if the status is not already done, to avoid potential race conditions.
            if status.done is False:
                status.set_finished()
            self._set_thread_event.clear()  # Signal that the set operation is complete

        self._set_thread_event.set()  # Signal that a set operation is in progress
        self.put(value, use_complete=True, callback=put_callback)
        return status


class EpicsSignalWithRBV(EpicsSignal):
    """Custom EpicsSignal class that uses the StatusBase object from ophyd_devices."""

    def __init__(self, prefix, **kwargs):
        super().__init__(prefix + "_RBV", write_pv=prefix, **kwargs)
