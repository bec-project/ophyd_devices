"""Add useful traceback details to Ophyd subscription callback errors."""

import functools
import traceback

from bec_lib.logger import bec_logger
from ophyd.ophydobj import OphydObject, UnknownSubscription

_original_subscribe = getattr(
    OphydObject.subscribe, "_ophyd_devices_original_subscribe", OphydObject.subscribe
)


def callback_name(callback) -> str:
    """Identify a callback without invoking a user-defined ``__repr__``."""
    try:
        name = getattr(callback, "__qualname__", None)
    except Exception:  # pylint: disable=broad-except
        name = None
    return name if isinstance(name, str) else type(callback).__name__


def object_name(obj) -> str:
    """Identify an Ophyd object without invoking a custom ``__repr__``."""
    try:
        name = getattr(obj, "name", None)
    except Exception:  # pylint: disable=broad-except
        name = None
    if not isinstance(name, str):
        name = "<unnamed>"
    return f"{type(obj).__name__}({name})"


@functools.wraps(_original_subscribe)
def _subscribe_with_traceback(self, callback, event_type=None, run=True):
    """Keep Ophyd's subscription behavior and enrich swallowed callback errors."""
    if not callable(callback):
        raise ValueError("callback must be callable")
    if event_type is None:
        event_type = self._default_sub
    if event_type is None:
        raise ValueError(
            f"Subscription type not set and object {self.name} of class"
            f" {self.__class__.__name__} has no default subscription set"
        )
    if event_type not in self.subscriptions:
        raise UnknownSubscription(
            f"Unknown subscription {event_type!r}, must be one of {self.subscriptions!r}"
        )

    registration_stack = traceback.extract_stack(limit=12)[:-1]

    @functools.wraps(callback)
    def wrapped_callback(*args, **kwargs):
        try:
            return callback(*args, **kwargs)
        except Exception:  # pylint: disable=broad-except
            # Keep the traceback in the message for sinks that forward only text.
            bec_logger.logger.error(
                f"Subscription {kwargs.get('sub_type', event_type)} callback {callback_name(callback)} "
                f"exception on {object_name(self)}.\n"
                f"Registered from:\n{''.join(traceback.format_list(registration_stack))}"
                f"Callback traceback:\n{traceback.format_exc()}"
            )

    # Match Ophyd's registration order and keep the original for clear_sub().
    cid = next(self._cb_count)
    self._unwrapped_callbacks[event_type][cid] = callback
    self._callbacks[event_type][cid] = wrapped_callback
    self._cid_to_event_mapping[cid] = event_type

    if run:
        cached = self._args_cache[event_type]
        if cached is not None:
            args, kwargs = cached
            wrapped_callback(*args, **kwargs)

    return cid


_subscribe_with_traceback._ophyd_devices_callback_patch = True
_subscribe_with_traceback._ophyd_devices_original_subscribe = _original_subscribe


def install_ophyd_callback_patch():
    """Install once, including when ophyd_devices is reloaded."""
    if not getattr(OphydObject.subscribe, "_ophyd_devices_callback_patch", False):
        OphydObject.subscribe = _subscribe_with_traceback
