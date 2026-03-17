"""Tests for processed-signal behavior and integration patterns."""

# pylint: disable=redefined-outer-name

import pytest
from bec_server.device_server.tests.utils import DMMock
from ophyd import Component as Cpt
from ophyd import Device

from ophyd_devices.sim.sim_positioner import SimPositioner
from ophyd_devices.utils.bec_processed_signal import BECProcessedSignal, ProcessedSignalModel


class TestProcessedSignalDevice(Device):
    """Fixture device with two sub-positioners and one processed signal."""

    motor_a = Cpt(SimPositioner, name="motor_a", delay=0)
    motor_b = Cpt(SimPositioner, name="motor_b", delay=0)
    processed = Cpt(BECProcessedSignal, name="processed", model_config=None)

    def __init__(self, name, device_manager, **kwargs):
        self.device_manager = device_manager
        super().__init__(name=name, **kwargs)
        self.processed.set_compute_method(
            self.compute, motor_a=self.motor_a.readback, motor_b=self.motor_b.readback, offset=0.5
        )

    @staticmethod
    def compute(motor_a, motor_b, offset=0):
        """Compute processed value from two motor readbacks."""
        return float(motor_a.get() + motor_b.get() + offset)


@pytest.fixture(name="device_manager")
def fixture_device_manager():
    """Mock device manager fixture."""
    return DMMock()


@pytest.fixture(name="processed_device")
def fixture_processed_device(device_manager):
    """Fixture for TestProcessedSignalDevice."""
    dev = TestProcessedSignalDevice(name="processed_dev", device_manager=device_manager)
    dev.motor_a.wait_for_connection()
    dev.motor_b.wait_for_connection()
    dev.processed.wait_for_connection()
    return dev


@pytest.fixture(name="samx")
def fixture_samx():
    """Standalone left motor fixture."""
    return SimPositioner(name="samx", delay=0)


@pytest.fixture(name="samy")
def fixture_samy():
    """Standalone right motor fixture."""
    return SimPositioner(name="samy", delay=0)


@pytest.fixture(name="device_manager_with_signals")
def fixture_device_manager_with_signals(samx, samy):
    """Device manager fixture with motor mapping and session needs."""
    dm = DMMock()
    dm.devices["samx"] = samx
    dm.devices["samy"] = samy
    dm.current_session = {"devices": [{"name": "processed_signal", "needs": ["samx", "samy"]}]}
    return dm


@pytest.fixture(name="processed_signal_from_device_manager")
def fixture_processed_signal_from_device_manager(device_manager_with_signals):
    """Processed signal fixture using dotted-name resolution through the device manager."""

    signal = BECProcessedSignal(name="processed_signal", device_manager=device_manager_with_signals)
    signal_1 = BECProcessedSignal.get_device_object_from_bec(
        "samx.readback", "processed_signal", device_manager_with_signals
    )
    signal_2 = BECProcessedSignal.get_device_object_from_bec(
        "samy.readback", "processed_signal", device_manager_with_signals
    )
    signal.set_compute_method(
        lambda signal_1, signal_2, offset=1.0: float(signal_1.get() + signal_2.get() + offset),
        signal_1=signal_1,
        signal_2=signal_2,
        offset=1.0,
    )
    signal.wait_for_connection()
    return signal


def test_processed_signal_with_sub_components(processed_device):
    """Test processed signal updates from sub-component motor readbacks."""
    processed_device.motor_a.move(2).wait(timeout=2)
    processed_device.motor_b.move(3).wait(timeout=2)
    assert processed_device.processed.get() == pytest.approx(5.5)

    processed_device.motor_a.move(-1).wait(timeout=2)
    assert processed_device.processed.get() == pytest.approx(2.5)


def test_processed_signal_device_manager_resolution(
    processed_signal_from_device_manager, samx, samy
):
    """Test processed signal using device-manager string key resolution."""
    samx.move(1).wait(timeout=2)
    samy.move(2).wait(timeout=2)
    assert processed_signal_from_device_manager.get() == pytest.approx(4)

    samy.move(5).wait(timeout=2)
    assert processed_signal_from_device_manager.get() == pytest.approx(7)


def test_processed_signal_describe_metadata(processed_signal_from_device_manager):
    """Test describe contains compute method metadata and extra kwargs."""
    info = processed_signal_from_device_manager.describe()["processed_signal"]
    assert info["compute_method"] == "<lambda>"
    assert info["extra_kwargs"] == {"offset": 1.0}
    assert "samx.readback" in info["method_inputs"]
    assert "samy.readback" in info["method_inputs"]


def test_processed_signal_model_rejects_missing_required_inputs():
    """Test compute model validation when required kwargs are missing."""

    def compute(signal_1, signal_2):
        return signal_1 + signal_2

    with pytest.raises(ValueError, match="missing required inputs"):
        ProcessedSignalModel.model_validate(
            {"method_inputs": {"signal_1": 1}, "compute_method": compute}
        )


def test_processed_signal_model_rejects_unexpected_inputs():
    """Test compute model validation when unknown kwargs are provided."""

    def compute(signal_1):
        return signal_1

    with pytest.raises(ValueError, match="unexpected inputs"):
        ProcessedSignalModel.model_validate(
            {"method_inputs": {"signal_1": 1, "extra": 2}, "compute_method": compute}
        )


def test_processed_signal_requires_compute_method(device_manager):
    """Test wait_for_connection fails when no compute model is configured."""
    signal = BECProcessedSignal(name="no_model", device_manager=device_manager)
    with pytest.raises(ValueError, match="No compute model provided"):
        signal.wait_for_connection()
