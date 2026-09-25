"""
Tests for the ophyd_devices Signal wrapper.
"""

import threading
from functools import partial
from unittest import mock

import ophyd
import pytest

from ophyd_devices import EpicsSignal, EpicsSignalWithRBV, Signal
from ophyd_devices.tests.utils import MockPV
from ophyd_devices.utils.psi_device_base_utils import StatusTimeoutErrorWithErrorInfo


@pytest.fixture
def signal() -> Signal:
    """
    Fixture to create a Signal instance for testing.
    Returns:
        Signal: An instance of the Signal class.
    """
    return Signal(name="test_signal", value=0)


@pytest.fixture
def patched_epics_signal() -> EpicsSignal:
    """
    Fixture to create a patched EpicsSignal instance for testing.
    Returns:
        EpicsSignal: An instance of the EpicsSignal class with patched methods.
    """
    pv = "test_epics_signal"
    with mock.patch.object(ophyd, "cl") as mock_cl:
        mock_cl.get_pv = partial(MockPV, _mock_pv_initial_value=1)
        mock_cl.thread_class = threading.Thread
        sig = EpicsSignal(pv)
        return sig


@pytest.fixture
def patched_epics_signal_with_rbv() -> EpicsSignalWithRBV:
    """
    Fixture to create a patched EpicsSignalWithRBV instance for testing.
    Returns:
        EpicsSignalWithRBV: An instance of the EpicsSignalWithRBV class with patched methods.
    """
    pv = "test_epics_signal"
    with mock.patch.object(ophyd, "cl") as mock_cl:
        mock_cl.get_pv = partial(MockPV, _mock_pv_initial_value=1)
        mock_cl.thread_class = threading.Thread
        sig = EpicsSignalWithRBV(pv)
        if sig._read_pv.pvname != sig._write_pv.pvname:
            sig._read_pv = sig._write_pv
        return sig


def test_signal_set(signal: Signal):
    """
    Test the set method of the Signal class."""
    # Test setting the signal to a new value
    sig = signal
    status = sig.set(10)
    status.wait()
    assert status.done is True
    assert sig.get() == 10

    status = sig.set(3)
    status.wait()
    assert status.done is True
    assert sig.get() == 3

    with mock.patch.object(sig, "put"):
        # Test setting the sig to the same value (should not call put)
        status = sig.set(5)
        assert status.done is False
        sig._readback = 5  # Simulate that the readback value has changed to 5
        status.wait(timeout=5)  # Wait for the status to complete
        assert sig.get() == 5
        assert status.done is True
        status = sig.set(5)  # Setting to the same value again
        status.wait(timeout=5)  # Wait for the status to complete
        assert sig.get() == 5
        assert status.done is True


def test_signal_subsequent_set_calls(signal: Signal):
    """
    Test that subsequent set calls raise a RuntimeError if a set is already in progress.
    """
    sig = signal
    with mock.patch.object(sig, "put"):
        status = sig.set(20)
        with pytest.raises(RuntimeError):
            status2 = sig.set(30)


def test_signal_set_with_timeout(signal: Signal):
    """
    Test the set method with a specified timeout.
    """
    sig = signal
    with mock.patch.object(sig, "put"):
        status = sig.set(15, timeout=1)
        with pytest.raises(StatusTimeoutErrorWithErrorInfo):
            status.wait(timeout=2)


def test_epics_signal_set_with_timeout(patched_epics_signal: EpicsSignal):
    """
    Test the set method of the EpicsSignal class with a specified timeout.
    """
    sig = patched_epics_signal
    with mock.patch.object(sig, "put"):
        status = sig.set(25, timeout=1)
        with pytest.raises(StatusTimeoutErrorWithErrorInfo):
            status.wait(timeout=2)


def test_epics_signal_set(patched_epics_signal: EpicsSignal):
    """
    Test the set method of the EpicsSignal class.
    """
    sig = patched_epics_signal
    status = sig.set(10)
    status.wait()
    assert status.done is True
    assert sig.get() == 10


def test_epics_signal_with_rbv_set_with_timeout(patched_epics_signal_with_rbv: EpicsSignalWithRBV):
    """
    Test the set method of the EpicsSignalWithRBV class with a specified timeout.
    """
    sig = patched_epics_signal_with_rbv
    with mock.patch.object(sig, "put"):
        status = sig.set(35, timeout=1)
        with pytest.raises(StatusTimeoutErrorWithErrorInfo):
            status.wait(timeout=2)


def test_epics_signal_with_rbv_set(patched_epics_signal_with_rbv: EpicsSignalWithRBV):
    """
    Test the set method of the EpicsSignalWithRBV class.
    """
    sig = patched_epics_signal_with_rbv
    status = sig.set(20)
    status.wait()
    assert status.done is True
    assert sig.get() == 20


def test_epics_signal_with_put_complete(patched_epics_signal: EpicsSignal):
    """
    Test the set method of the EpicsSignal class with use_complete=True.
    """
    sig = patched_epics_signal
    sig._put_complete = True  # Simulate that the put operation is complete

    with mock.patch.object(sig, "put") as mock_put:
        status = sig.set(50)
        assert status.done is False
        mock_put.assert_called_once_with(50, use_complete=True, callback=mock.ANY)
        with pytest.raises(RuntimeError):
            sig.set(60)  # Attempting to set while another set is in progress

        mock_put.call_args[1]["callback"](pvname=sig.name)  # Simulate the callback being called
        status.wait(timeout=5)  # Wait for the status to complete
        assert status.done is True
        assert status.success is True

        # Test that now we can set again after the previous set has completed
        status2 = sig.set(70)
        assert status2.done is False
        mock_put.assert_called_with(70, use_complete=True, callback=mock.ANY)
