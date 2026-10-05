from unittest import mock

import pytest
from ophyd import Component as Cpt
from ophyd import EpicsSignalRO

from ophyd_devices.devices.undulator import UndulatorAlpha, UndulatorGap, UndulatorHarmonic
from ophyd_devices.tests.utils import patched_device


@pytest.fixture(params=[UndulatorGap, UndulatorHarmonic, UndulatorAlpha])
def mock_undulator(request):
    with patched_device(request.param, name="undulator", prefix="TEST:UNDULATOR") as und:
        yield und


@pytest.fixture
def mock_harmonic():
    with patched_device(UndulatorHarmonic, name="harmonic", prefix="TEST:UNDULATOR") as und:
        und.select_control._read_pv.mock_data = 1
        und.done._read_pv.mock_data = 1
        yield und


@pytest.fixture(params=[UndulatorGap, UndulatorHarmonic, UndulatorAlpha])
def mock_validated_undulator(request):
    class ValidatedUndulator(request.param):
        enabled = Cpt(EpicsSignalRO, "ENABLED")
        control_validations = request.param.control_validations + (
            ("enabled", 7, "Undulator is disabled!"),
        )

    with patched_device(ValidatedUndulator, name="undulator", prefix="TEST:UNDULATOR") as und:
        und.select_control._read_pv.mock_data = 1
        und.enabled._read_pv.mock_data = 7
        und.done._read_pv.mock_data = 1
        yield und


def test_shared_init_preserves_readback_naming_and_write_access(mock_undulator):
    und = mock_undulator
    if und.readback is not None:
        readback = und.readback
        assert readback._metadata["write_access"] is False
        assert und.setpoint.name == f"{und.name}_setpoint"
    else:
        readback = und.setpoint
        assert readback.write_access

    assert readback.name == und.name
    assert und.name in und.read()
    assert und.hints == {"fields": [und.name]}


@pytest.mark.parametrize(
    ["start", "end", "in_deadband_expected"],
    [
        (1.0, 1.0, True),
        (0, 1.0, False),
        (-0.004, 0.004, False),
        (-0.0027, -0.0023, True),
        (1, 1.0009, False),
        (1, 1.0007, True),
    ],
)
@mock.patch("ophyd_devices.devices.undulator.PVPositioner.move")
@mock.patch("ophyd_devices.devices.undulator.MoveStatus")
def test_deadband_shortcut_applies_only_to_gap(
    mock_movestatus, mock_super_move, mock_undulator, start, end, in_deadband_expected
):
    mock_undulator.select_control._read_pv.mock_data = 1
    mock_undulator.done._read_pv.mock_data = 1
    mock_undulator._position = start
    mock_undulator.move(end)

    if in_deadband_expected and isinstance(mock_undulator, UndulatorGap):
        mock_movestatus.assert_called_with(mock.ANY, mock.ANY, done=True, success=True)
    else:
        mock_movestatus.assert_not_called()
        mock_super_move.assert_called_once()


def test_undulator_raises_when_disabled(mock_undulator):
    mock_undulator.select_control._read_pv.mock_data = 0
    with pytest.raises(PermissionError) as e:
        mock_undulator.move(5)
    assert e.match("Undulator is operator controlled!")


def test_undulator_stop_call(mock_undulator):
    mock_undulator.select_control._read_pv.mock_data = 1
    mock_undulator.stop_signal.put(0)
    mock_undulator.stop()
    assert mock_undulator.stop_signal.get() == 1
    mock_undulator.stop_signal.put(0)
    mock_undulator.select_control._read_pv.mock_data = 0
    # Error should just be logged, not raised.
    mock_undulator.stop()
    assert mock_undulator.stop_signal.get() == 0


@pytest.mark.parametrize(
    ["signal_name", "value", "error_message"],
    [
        ("select_control", 0, "Undulator is operator controlled!"),
        ("enabled", 6, "Undulator is disabled!"),
    ],
)
@pytest.mark.parametrize("position", [0, 5])
def test_derived_validations_block_moves(
    mock_validated_undulator, signal_name, value, error_message, position
):
    und = mock_validated_undulator
    getattr(und, signal_name)._read_pv.mock_data = value
    und._position = 0

    with mock.patch("ophyd_devices.devices.undulator.PVPositioner.move") as parent_move:
        with pytest.raises(PermissionError, match=error_message):
            und.move(position, wait=False)

    parent_move.assert_not_called()
    assert und.setpoint.get() == 0


@pytest.mark.parametrize(
    ["signal_name", "value", "error_message"],
    [
        ("select_control", 0, "Undulator is operator controlled!"),
        ("enabled", 6, "Undulator is disabled!"),
    ],
)
@pytest.mark.parametrize("force", [False, True])
def test_derived_validations_block_direct_setpoint_writes(
    mock_validated_undulator, signal_name, value, error_message, force
):
    und = mock_validated_undulator
    getattr(und, signal_name)._read_pv.mock_data = value

    with pytest.raises(PermissionError, match=error_message):
        und.setpoint.put(5, force=force)

    assert und.setpoint.get() == 0


@pytest.mark.parametrize(["signal_name", "value"], [("select_control", 0), ("enabled", 6)])
def test_derived_validations_skip_stop_writes(mock_validated_undulator, signal_name, value):
    und = mock_validated_undulator
    getattr(und, signal_name)._read_pv.mock_data = value

    assert und.stop_signal.put(1) is None
    assert und.stop_signal.get() == 0
    und.stop()
    assert und.stop_signal.get() == 0


def test_derived_undulator_moves_and_completes(mock_validated_undulator):
    und = mock_validated_undulator
    status = und.set(5)

    assert und.setpoint.get() == 5
    assert not status.done
    und.done._read_pv.mock_data = 0
    assert not status.done
    if und.readback is not None:
        und.readback._read_pv.mock_data = 5
    und.done._read_pv.mock_data = 1
    status.wait(timeout=1)
    assert status.success
    assert und.position == 5


def test_derived_undulator_stop_waits_for_ioc_done(mock_validated_undulator):
    und = mock_validated_undulator
    status = und.set(5)
    und.done._read_pv.mock_data = 0
    assert not status.done

    und.stop()

    assert und.stop_signal.get() == 1
    assert not status.done
    und.done._read_pv.mock_data = 1
    status.wait(timeout=1)
    assert status.done
    assert status.success


@pytest.mark.parametrize("target", [5, 6])
def test_harmonic_moves_while_busy_wait_for_done_and_can_stop(mock_harmonic, target):
    und = mock_harmonic
    und.set(5)
    und.done._read_pv.mock_data = 0

    with mock.patch.object(und.setpoint, "put", wraps=und.setpoint.put) as put:
        status = und.set(target)
    put.assert_called_once_with(target, wait=True)
    assert not status.done

    und.stop()
    assert und.stop_signal.get() == 1
    und.done._read_pv.mock_data = 1
    status.wait(timeout=1)
    assert status.success


def test_harmonic_retry_after_stop_writes_target_and_waits_for_done(mock_harmonic):
    und = mock_harmonic
    first = und.set(5)
    und.done._read_pv.mock_data = 0
    und.stop()
    und.done._read_pv.mock_data = 1
    first.wait(timeout=1)
    moved_cb = mock.Mock()

    with mock.patch.object(und.setpoint, "put", wraps=und.setpoint.put) as put:
        retry = und.move(5, wait=False, moved_cb=moved_cb)

    put.assert_called_once_with(5, wait=True)
    assert not retry.done
    moved_cb.assert_not_called()
    und.done._read_pv.mock_data = 0
    und.done._read_pv.mock_data = 1
    retry.wait(timeout=1)
    assert retry.success
    moved_cb.assert_called_once_with(retry, obj=und)


@pytest.mark.parametrize(
    ["target", "value", "allowed"],
    [
        (7, 7, True),
        (7, 8, False),
        ([7, 8], 7, True),
        ([7, 8], 8, True),
        ([7, 8], 6, False),
        ([], 7, False),
        (["ready", "enabled"], "enabled", True),
        (["ready", "enabled"], "disabled", False),
        ("ready", "ready", True),
        ("ready", "rea", False),
    ],
)
def test_scalar_and_list_conditions(mock_validated_undulator, target, value, allowed):
    und = mock_validated_undulator
    und.control_validations = UndulatorGap.control_validations + (
        ("enabled", target, "Undulator is disabled!"),
    )
    und.enabled._read_pv.mock_data = value

    if allowed:
        status = und.set(5)
        assert und.setpoint.get() == 5
        und.done._read_pv.mock_data = 0
        und.stop()
        assert und.stop_signal.get() == 1
        und.done._read_pv.mock_data = 1
        status.wait(timeout=1)
        assert status.success
    else:
        with pytest.raises(PermissionError, match="Undulator is disabled!"):
            und.set(5)
        with pytest.raises(PermissionError, match="Undulator is disabled!"):
            und.setpoint.put(5)
        und.stop()
        assert und.setpoint.get() == 0
        assert und.stop_signal.get() == 0
