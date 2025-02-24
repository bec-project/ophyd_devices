# pylint: skip-file
import time
from unittest import mock

import pytest
from ophyd import DeviceStatus, Staged
from ophyd.utils.errors import RedundantStaging

from ophyd_devices.interfaces.base_classes.psi_device_base import PSIDeviceBase
from ophyd_devices.utils.errors import DeviceStopError, DeviceTimeoutError


@pytest.fixture
def detector_base():
    yield PSIDeviceBase(name="test_detector")


def test_detector_base_init(detector_base):
    assert detector_base.stopped is False
    assert detector_base.name == "test_detector"
    assert detector_base.staged == Staged.no
    assert detector_base.destroyed == False


def test_stage(detector_base):
    assert detector_base._staged == Staged.no
    assert detector_base.stopped is False
    detector_base._staged = Staged.no
    with mock.patch.object(detector_base, "on_stage") as mock_on_stage:
        rtr = detector_base.stage()
        assert isinstance(rtr, list)
        assert mock_on_stage.called is True
        with pytest.raises(RedundantStaging):
            detector_base.stage()
        detector_base._staged = Staged.no
        detector_base.stopped = True
        detector_base.stage()
        assert detector_base.stopped is False
        assert mock_on_stage.call_count == 2


# def test_stage(detector_base):
#     detector_base._staged = Staged.yes
#     with pytest.raises(RedundantStaging):
#         detector_base.stage()
#     assert detector_base.stopped is False
#     detector_base._staged = Staged.no
#     with (
#         mock.patch.object(detector_base.custom_prepare, "on_stage") as mock_on_stage,
#         mock.patch.object(detector_base.scaninfo, "load_scan_metadata") as mock_load_metadata,
#     ):
#         rtr = detector_base.stage()
#         assert isinstance(rtr, list)
#         mock_on_stage.assert_called_once()
#         mock_load_metadata.assert_called_once()
#         assert detector_base.stopped is False


# def test_pre_scan(detector_base):
#     with mock.patch.object(detector_base.custom_prepare, "on_pre_scan") as mock_on_pre_scan:
#         detector_base.pre_scan()
#         mock_on_pre_scan.assert_called_once()


# def test_trigger(detector_base):
#     status = DeviceStatus(detector_base)
#     with mock.patch.object(
#         detector_base.custom_prepare, "on_trigger", side_effect=[None, status]
#     ) as mock_on_trigger:
#         st = detector_base.trigger()
#         assert isinstance(st, DeviceStatus)
#         time.sleep(0.1)
#         assert st.done is True
#         st = detector_base.trigger()
#         assert st.done is False
#         assert id(st) == id(status)


# def test_unstage(detector_base):
#     detector_base.stopped = True
#     with (
#         mock.patch.object(detector_base.custom_prepare, "on_unstage") as mock_on_unstage,
#         mock.patch.object(detector_base, "check_scan_id") as mock_check_scan_id,
#     ):
#         rtr = detector_base.unstage()
#         assert isinstance(rtr, list)
#         assert mock_check_scan_id.call_count == 1
#         assert mock_on_unstage.call_count == 1
#         detector_base.stopped = False
#         rtr = detector_base.unstage()
#         assert isinstance(rtr, list)
#         assert mock_check_scan_id.call_count == 2
#         assert mock_on_unstage.call_count == 2


# def test_complete(detector_base):
#     status = DeviceStatus(detector_base)
#     with mock.patch.object(
#         detector_base.custom_prepare, "on_complete", side_effect=[None, status]
#     ) as mock_on_complete:
#         st = detector_base.complete()
#         assert isinstance(st, DeviceStatus)
#         time.sleep(0.1)
#         assert st.done is True
#         st = detector_base.complete()
#         assert st.done is False
#         assert id(st) == id(status)


# def test_stop(detector_base):
#     with mock.patch.object(detector_base.custom_prepare, "on_stop") as mock_on_stop:
#         detector_base.stop()
#         mock_on_stop.assert_called_once()
#         assert detector_base.stopped is True


# def test_check_scan_id(detector_base):
#     detector_base.scaninfo.scan_id = "abcde"
#     detector_base.stopped = False
#     detector_base.check_scan_id()
#     assert detector_base.stopped is True
#     detector_base.stopped = False
#     detector_base.check_scan_id()
#     assert detector_base.stopped is False


# def test_wait_for_signal(detector_base):
#     my_value = False

#     def my_callback():
#         return my_value

#     detector_base
#     status = detector_base.custom_prepare.wait_with_status(
#         [(my_callback, True)],
#         check_stopped=True,
#         timeout=5,
#         interval=0.01,
#         exception_on_timeout=None,
#     )
#     time.sleep(0.1)
#     assert status.done is False
#     # Check first that it is stopped when detector_base.stop() is called
#     detector_base.stop()
#     # some delay to allow the stop to take effect
#     time.sleep(0.15)
#     assert status.done is True
#     assert status.exception().args == DeviceStopError(f"{detector_base.name} was stopped").args
#     detector_base.stopped = False
#     status = detector_base.custom_prepare.wait_with_status(
#         [(my_callback, True)],
#         check_stopped=True,
#         timeout=5,
#         interval=0.01,
#         exception_on_timeout=None,
#     )
#     # Check that thread resolves when expected value is set
#     my_value = True
#     # some delay to allow the stop to take effect
#     time.sleep(0.15)
#     assert status.done is True
#     assert status.success is True
#     assert status.exception() is None

#     detector_base.stopped = False
#     # Check that wait for status runs into timeout with expectd exception
#     my_value = "random_value"
#     exception = TimeoutError("Timeout")
#     status = detector_base.custom_prepare.wait_with_status(
#         [(my_callback, True)],
#         check_stopped=True,
#         timeout=0.01,
#         interval=0.01,
#         exception_on_timeout=exception,
#     )
#     time.sleep(0.2)
#     assert status.done is True
#     assert id(status.exception()) == id(exception)
#     assert status.success is False


# def test_wait_for_signal_returns_exception(detector_base):
#     my_value = False

#     def my_callback():
#         return my_value

#     # Check that wait for status runs into timeout with expectd exception

#     exception = TimeoutError("Timeout")
#     status = detector_base.custom_prepare.wait_with_status(
#         [(my_callback, True)],
#         check_stopped=True,
#         timeout=0.01,
#         interval=0.01,
#         exception_on_timeout=exception,
#     )
#     time.sleep(0.2)
#     assert status.done is True
#     assert id(status.exception()) == id(exception)
#     assert status.success is False

#     detector_base.stopped = False
#     # Check that standard exception is thrown
#     status = detector_base.custom_prepare.wait_with_status(
#         [(my_callback, True)],
#         check_stopped=True,
#         timeout=0.01,
#         interval=0.01,
#         exception_on_timeout=None,
#     )
#     time.sleep(0.2)
#     assert status.done is True
#     assert (
#         status.exception().args
#         == DeviceTimeoutError(
#             f"Timeout error for {detector_base.name} while waiting for signals {[(my_callback, True)]}"
#         ).args
#     )
#     assert status.success is False
