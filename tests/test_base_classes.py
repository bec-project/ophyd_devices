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


def test_pre_scan(detector_base):
    with mock.patch.object(detector_base, "on_pre_scan") as mock_on_pre_scan:
        detector_base.pre_scan()
        mock_on_pre_scan.assert_called_once()


def test_trigger(detector_base):
    status = DeviceStatus(detector_base)
    with mock.patch.object(
        detector_base, "on_trigger", side_effect=[None, status]
    ) as mock_on_trigger:
        st = detector_base.trigger()
        assert isinstance(st, DeviceStatus)
        st.wait(timeout=1)
        assert st.done is True
        st = detector_base.trigger()
        assert st.done is False
        assert id(st) == id(status)


def test_unstage(detector_base):
    detector_base.stopped = True
    with (mock.patch.object(detector_base, "on_unstage") as mock_on_unstage,):
        rtr = detector_base.unstage()
        assert isinstance(rtr, list)
        assert mock_on_unstage.call_count == 1
        detector_base.stopped = False
        rtr = detector_base.unstage()
        assert isinstance(rtr, list)
        assert mock_on_unstage.call_count == 2


def test_complete(detector_base):
    status = DeviceStatus(detector_base)
    with mock.patch.object(
        detector_base, "on_complete", side_effect=[None, status]
    ) as mock_on_complete:
        st = detector_base.complete()
        assert isinstance(st, DeviceStatus)
        time.sleep(0.1)
        assert st.done is True
        st = detector_base.complete()
        assert st.done is False
        assert id(st) == id(status)


def test_stop(detector_base):
    with mock.patch.object(detector_base, "on_stop") as mock_on_stop:
        detector_base.stop()
        mock_on_stop.assert_called_once()
        assert detector_base.stopped is True
