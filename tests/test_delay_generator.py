import threading
from unittest import mock

import ophyd
import pytest

from ophyd_devices.devices.delay_generator_645 import (
    DelayGenerator,
    DelayGeneratorError,
    TriggerSource,
)
from ophyd_devices.tests.utils import (
    MockPV,
    patch_dual_pvs,
    patch_functions_required_for_connection,
)


@pytest.fixture(scope="function")
def mock_ddg():
    name = "ddg"
    prefix = "X12SA-CPCL-DDG3:"
    with mock.patch.object(ophyd, "cl") as mock_cl:
        mock_cl.get_pv = MockPV
        mock_cl.thread_class = threading.Thread
        ddg = DelayGenerator(name=name, prefix=prefix)
        patch_functions_required_for_connection(ddg)
        patch_dual_pvs(ddg)
        yield ddg


def test_ddg_init(mock_ddg):
    """This test the initialization of the DelayGenerator"""
    assert mock_ddg.name == "ddg"
    assert mock_ddg.prefix == "X12SA-CPCL-DDG3:"


def test_set_trigger(mock_ddg):
    """This test the set_trigger method of the DelayGenerator"""
    mock_ddg.set_trigger(TriggerSource.SINGLE_SHOT)
    assert mock_ddg.source.get() == 5
    mock_ddg.set_trigger(TriggerSource.INTERNAL)
    assert mock_ddg.source.get() == 0


def test_burst_enable(mock_ddg):
    """This test the burst_enable method of the DelayGenerator"""
    count = 10
    delay = 0.1
    period = 0.2

    mock_ddg.burst_enable(count=count, delay=delay, period=period)
    assert mock_ddg.burstMode.get() == 1
    assert mock_ddg.burstCount.get() == count
    assert mock_ddg.burstDelay.get() == delay
    assert mock_ddg.burstPeriod.get() == period
    assert mock_ddg.burstConfig.get() == 0
    with pytest.raises(DelayGeneratorError):
        delay = -1
        mock_ddg.burst_enable(count=count, delay=delay, period=period)
    with pytest.raises(DelayGeneratorError):
        delay = 0
        period = 0
        mock_ddg.burst_enable(count=count, delay=delay, period=period)


def test_check_if_ddg_okay(mock_ddg):
    """This test the is_ddg_okay method of the DelayGenerator"""
    # Test for when the status is okay
    mock_ddg.status._read_pv.mock_data = "STATUS OK"
    assert mock_ddg.check_if_ddg_okay() is None
    # Test for when the status is not okay
    mock_ddg.status._read_pv.mock_data = "STATUS NOT OK"
    with pytest.raises(DelayGeneratorError):
        mock_ddg.check_if_ddg_okay()
