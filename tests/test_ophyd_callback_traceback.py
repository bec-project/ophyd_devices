"""Regression coverage for diagnostics from Ophyd subscription callbacks."""

import os
import subprocess
import sys

import pytest
from bec_lib.logger import bec_logger
from ophyd import Signal
from ophyd.ophydobj import UnknownSubscription

from ophyd_devices.utils.psi_device_base_utils import SubscriptionStatus


@pytest.fixture
def bec_error_messages():
    messages = []
    sink_id = bec_logger.logger.add(
        lambda message: messages.append(message.record["message"]), level="ERROR"
    )
    try:
        yield messages
    finally:
        bec_logger.logger.remove(sink_id)


class BadReprCallback:
    def __init__(self, error):
        self.error = error

    def __call__(self, **kwargs):
        raise self.error

    def __repr__(self):
        raise RuntimeError("callback repr exploded")


def test_subscription_failure_message_contains_callback_traceback(bec_error_messages):
    signal = Signal(name="traceback_signal")
    delivered = []

    def failing_callback(**kwargs):
        raise RuntimeError("callback exploded")

    def succeeding_callback(**kwargs):
        delivered.append(kwargs["value"])

    signal.subscribe(failing_callback, run=False)
    signal.subscribe(succeeding_callback, run=False)

    signal.put(3)

    assert delivered == [3]
    (message,) = bec_error_messages
    assert "Traceback (most recent call last)" in message
    assert "failing_callback" in message
    assert "traceback_signal" in message
    assert "value" in message
    assert "RuntimeError: callback exploded" in message


def test_callback_with_bad_repr_does_not_interrupt_other_subscribers(bec_error_messages):
    signal = Signal(name="bad_repr_signal")
    delivered = []
    signal.subscribe(BadReprCallback(ValueError("original callback failure")), run=False)
    signal.subscribe(lambda **kwargs: delivered.append(kwargs["value"]), run=False)

    signal.put(6)

    assert delivered == [6]
    (message,) = bec_error_messages
    assert "BadReprCallback" in message
    assert "ValueError: original callback failure" in message
    assert "callback repr exploded" not in message


def test_original_callback_can_be_cleared_after_patch(bec_error_messages):
    signal = Signal(name="clearable_signal")
    invocations = []

    def failing_callback(**kwargs):
        invocations.append(kwargs["value"])
        raise RuntimeError("clearable callback exploded")

    signal.subscribe(failing_callback, run=False)
    signal.put(1)
    signal.clear_sub(failing_callback)
    signal.put(2)

    assert invocations == [1]
    assert len(bec_error_messages) == 1


def test_cached_subscription_replay_logs_failure_and_keeps_subscription(bec_error_messages):
    signal = Signal(name="replay_signal")
    signal.put(7)
    invocations = []

    def replay_callback(**kwargs):
        invocations.append(kwargs["value"])
        raise ValueError("replayed callback exploded")

    cid = signal.subscribe(replay_callback, run=True)
    assert invocations == [7]
    signal.put(8)
    signal.unsubscribe(cid)
    signal.put(9)

    assert invocations == [7, 8]
    assert len(bec_error_messages) == 2
    assert all("replay_callback" in message for message in bec_error_messages)
    assert all(
        "ValueError: replayed callback exploded" in message for message in bec_error_messages
    )


def test_subscription_failure_message_identifies_registration_site(bec_error_messages):
    signal = Signal(name="registered_signal")

    def failing_callback(**kwargs):
        raise RuntimeError("registered callback exploded")

    def register_from_named_helper():
        signal.subscribe(failing_callback, run=False)

    register_from_named_helper()
    signal.put(4)

    (message,) = bec_error_messages
    assert "register_from_named_helper" in message


def test_subscription_status_callback_failure_has_traceback(bec_error_messages):
    signal = Signal(name="status_signal")

    def failing_status_callback(**kwargs):
        raise RuntimeError("status callback exploded")

    status = SubscriptionStatus(signal, callback=failing_status_callback, run=False)
    signal.put(5)

    with pytest.raises(RuntimeError, match="status callback exploded"):
        status.wait(timeout=1)

    (message,) = bec_error_messages
    assert "Traceback (most recent call last)" in message
    assert "failing_status_callback" in message
    assert "status_signal" in message
    assert "RuntimeError: status callback exploded" in message


def test_subscription_status_callback_with_bad_repr_keeps_original_error(bec_error_messages):
    signal = Signal(name="bad_repr_status_signal")
    original_error = ValueError("original status callback failure")
    status = SubscriptionStatus(signal, callback=BadReprCallback(original_error), run=False)

    signal.put(8)

    with pytest.raises(ValueError) as exc_info:
        status.wait(timeout=1)
    assert exc_info.value is original_error
    (message,) = bec_error_messages
    assert "BadReprCallback" in message
    assert "bad_repr_status_signal" in message
    assert "ValueError: original status callback failure" in message
    assert "callback repr exploded" not in message


def test_subscribe_preserves_validation_and_default_event():
    signal = Signal(name="validated_signal")

    with pytest.raises(ValueError, match="callback must be callable"):
        signal.subscribe(None, run=False)
    with pytest.raises(UnknownSubscription):
        signal.subscribe(lambda **kwargs: None, event_type="missing", run=False)

    events = []
    signal.subscribe(lambda **kwargs: events.append(kwargs["sub_type"]), run=False)
    signal.put(1)
    assert events == ["value"]


def test_patch_installation_and_reload_do_not_stack_wrappers():
    # Isolate module reload so a failing assertion cannot leave the process patched.
    script = """
import importlib

import ophyd_devices
from ophyd import Signal
from ophyd.ophydobj import OphydObject
from ophyd_devices.utils import ophyd_callback_patch

original = OphydObject.subscribe.__wrapped__
ophyd_callback_patch.install_ophyd_callback_patch()
ophyd_callback_patch.install_ophyd_callback_patch()
assert OphydObject.subscribe.__wrapped__ is original

importlib.reload(ophyd_callback_patch)
ophyd_callback_patch.install_ophyd_callback_patch()
assert OphydObject.subscribe.__wrapped__ is original

signal = Signal(name="reload_signal")
received = []
signal.subscribe(lambda **kwargs: received.append(kwargs["value"]), run=False)
signal.put(5)
assert received == [5]
"""
    env = os.environ.copy()
    env["OPHYD_CONTROL_LAYER"] = "dummy"
    result = subprocess.run([sys.executable, "-c", script], env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
