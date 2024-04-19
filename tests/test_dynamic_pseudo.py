from unittest import mock

import pytest
from bec_server.device_server.tests.utils import DMMock

from ophyd_devices.utils.dynamic_pseudo import ComputedSignal


@pytest.fixture
def device_manager_with_devices():
    dm = DMMock()
    dm.add_device("a")
    dm.add_device("b")
    device_mock = mock.MagicMock()
    device_mock.obj.readback.get.return_value = 20
    dm.devices["a"] = device_mock
    dm.devices["b"] = device_mock

    return dm


def test_computed_signal(device_manager_with_devices):
    signal = ComputedSignal(name="test", device_manager=device_manager_with_devices)
    assert signal.get() is None

    signal.compute_method = "def test(a, b): return a.get() + b.get()"
    signal.input_signals = ["a_readback", "b_readback"]
    assert signal.get() == 40

    # pylint: disable=protected-access
    assert callable(signal._compute_method)
    assert signal._compute_method_str == "def user_compute_method(a, b): return a.get() + b.get()"
