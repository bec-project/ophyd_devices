import pytest

from ophyd_devices.devices.optics_shutter import OpticsShutter, ShutterEnabled, ShutterOpenState
from ophyd_devices.tests.utils import patched_device


@pytest.fixture(scope="function")
def mock_shutter():
    with patched_device(OpticsShutter, name="shutter", prefix="X10SA-EH1-PSYS:SH-A-") as shutter:
        yield shutter


def test_shutter_open(mock_shutter):
    mock_shutter.epics_control.is_enabled._read_pv.mock_data = ShutterEnabled.ENABLED.value
    mock_shutter.epics_control.is_open._read_pv.mock_data = ShutterOpenState.CLOSED.value
    mock_shutter.is_open._read_pv.mock_data = ShutterOpenState.CLOSED.value
    st = mock_shutter.set_open.set(1)
    assert not st.done
    mock_shutter.is_open._read_pv.mock_data = ShutterOpenState.OPEN.value
    mock_shutter.epics_control.is_open._read_pv.mock_data = ShutterOpenState.OPEN.value
    assert st.done


def test_shutter_close(mock_shutter):
    mock_shutter.epics_control.is_enabled._read_pv.mock_data = ShutterEnabled.ENABLED.value
    mock_shutter.epics_control.is_open._read_pv.mock_data = ShutterOpenState.OPEN.value
    mock_shutter.is_open._read_pv.mock_data = ShutterOpenState.OPEN.value
    st = mock_shutter.set_open.set(0)
    assert not st.done
    mock_shutter.is_open._read_pv.mock_data = ShutterOpenState.CLOSED.value
    mock_shutter.epics_control.is_open._read_pv.mock_data = ShutterOpenState.CLOSED.value
    assert st.done


def test_shutter_not_enabled(mock_shutter):
    with pytest.raises(RuntimeError) as e:
        mock_shutter.set_open.set(1)
    assert e.match(f"The shutter {mock_shutter.name} is disabled!")


def test_shutter_status(mock_shutter):
    mock_shutter.epics_control.is_open._read_pv.mock_data = ShutterOpenState.OPEN.value
    mock_shutter.is_open._read_pv.mock_data = ShutterOpenState.OPEN.value
    assert mock_shutter.is_open.get() == ShutterOpenState.OPEN.value
    mock_shutter.epics_control.is_open._read_pv.mock_data = ShutterOpenState.CLOSED.value
    mock_shutter.is_open._read_pv.mock_data = ShutterOpenState.CLOSED.value
    assert mock_shutter.is_open.get() == ShutterOpenState.CLOSED.value
