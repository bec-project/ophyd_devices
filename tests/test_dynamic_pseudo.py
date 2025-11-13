from unittest import mock

import pytest
from bec_server.device_server.tests.utils import DMMock

from ophyd_devices.utils.dynamic_pseudo import ComputedSignal, _smart_strip


@pytest.fixture
def device_manager_with_devices():
    dm = DMMock()
    dm.add_device("a")
    dm.add_device("b")
    device_mock = mock.MagicMock()
    dm.devices["a"] = device_mock
    dm.devices["b"] = device_mock

    return dm


@pytest.mark.parametrize(
    "compute_method_str",
    [
        "def test(a, b): return a.get() + b.get()",
        "def   test(a,   b): return a.get() + b.get()",
        "    def my_compute_method(a,b):\n        return a.get() + b.get()\n",
        "#comment goes here\n    def my_compute_method(a,b):\n        return a.get() + b.get()\n",
        "#comment goes here\n\n\n    def my_compute_method(a,b):\n        return a.get() + b.get()\n",
        "#comment goes here\n\n\n    def my_compute_method(a,b):\n#comment inside\n        return a.get() + b.get()\n",
    ],
)
def test_computed_signal(device_manager_with_devices, compute_method_str):
    signal = ComputedSignal(name="test", device_manager=device_manager_with_devices)
    assert signal.get() is None

    # Configure the mocks before setting input signals
    device_manager_with_devices.devices["a"].readback.get.return_value = 20
    device_manager_with_devices.devices["b"].readback.get.return_value = 20

    signal.compute_method = compute_method_str
    signal.input_signals = ["a.readback", "b.readback"]

    assert signal.get() == 40

    # pylint: disable=protected-access
    assert callable(signal._compute_method)
    assert signal._compute_method_str == _smart_strip(compute_method_str)
