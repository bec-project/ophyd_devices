# pylint: skip-file
from unittest import mock

import pytest
from ophyd import DeviceStatus, Staged
from ophyd.utils.errors import RedundantStaging

from ophyd_devices.interfaces.base_classes.psi_detector_base import (
    CustomDetectorMixin,
    PSIDetectorBase,
)
from ophyd_devices.utils.bec_scaninfo_mixin import BecScaninfoMixin


@pytest.fixture
def detector_base():
    yield PSIDetectorBase(name="test_detector")


def test_detector_base_init(detector_base):
    assert detector_base.stopped is False
    assert detector_base.name == "test_detector"
    assert "base_path" in detector_base.filewriter.service_config
    assert isinstance(detector_base.scaninfo, BecScaninfoMixin)
    assert issubclass(detector_base.custom_prepare_cls, CustomDetectorMixin)


def test_stage(detector_base):
    detector_base._staged = Staged.yes
    with pytest.raises(RedundantStaging):
        detector_base.stage()
    assert detector_base.stopped is False
    detector_base._staged = Staged.no
    with (
        mock.patch.object(detector_base.custom_prepare, "on_stage") as mock_on_stage,
        mock.patch.object(detector_base.scaninfo, "load_scan_metadata") as mock_load_metadata,
    ):
        rtr = detector_base.stage()
        assert isinstance(rtr, list)
        mock_on_stage.assert_called_once()
        mock_load_metadata.assert_called_once()
        assert detector_base.stopped is False


def test_pre_scan(detector_base):
    with mock.patch.object(detector_base.custom_prepare, "on_pre_scan") as mock_on_pre_scan:
        detector_base.pre_scan()
        mock_on_pre_scan.assert_called_once()


def test_trigger(detector_base):
    with mock.patch.object(detector_base.custom_prepare, "on_trigger") as mock_on_trigger:
        rtr = detector_base.trigger()
        assert isinstance(rtr, DeviceStatus)
        mock_on_trigger.assert_called_once()


def test_unstage(detector_base):
    detector_base.stopped = True
    with (
        mock.patch.object(detector_base.custom_prepare, "on_unstage") as mock_on_unstage,
        mock.patch.object(detector_base, "check_scan_id") as mock_check_scan_id,
    ):
        rtr = detector_base.unstage()
        assert isinstance(rtr, list)
        assert mock_check_scan_id.call_count == 1
        mock_on_unstage.assert_not_called()
        detector_base.stopped = False
        rtr = detector_base.unstage()
        assert isinstance(rtr, list)
        assert mock_check_scan_id.call_count == 2
        assert detector_base.stopped is False
        mock_on_unstage.assert_called_once()


def test_complete(detector_base):
    with mock.patch.object(detector_base.custom_prepare, "on_complete") as mock_on_complete:
        detector_base.complete()
        mock_on_complete.assert_called_once()


def test_stop(detector_base):
    with mock.patch.object(detector_base.custom_prepare, "on_stop") as mock_on_stop:
        detector_base.stop()
        mock_on_stop.assert_called_once()
        assert detector_base.stopped is True


def test_check_scan_id(detector_base):
    detector_base.scaninfo.scan_id = "abcde"
    detector_base.stopped = False
    detector_base.check_scan_id()
    assert detector_base.stopped is True
    detector_base.stopped = False
    detector_base.check_scan_id()
    assert detector_base.stopped is False
