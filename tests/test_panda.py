# skip-file
from unittest import mock

import numpy as np
import pytest
from ophyd import Staged

from ophyd_devices import StatusBase
from ophyd_devices.devices.panda_box.panda_box import FrameData, PandaBox, PandaState
from ophyd_devices.devices.panda_box.utils import (
    PANDA_AVAIL_PCAP_BLOCKS,
    PANDA_AVAIL_PCAP_CAPTURE_FIELDS,
    get_pcap_capture_fields,
)


@pytest.fixture
def _signal_aliases():
    return {"FMC_IN.VAL1.Value": "my_signal_1", "FMC_IN.VAL2.Mean": "my_signal_2"}


@pytest.fixture
def panda_box(_signal_aliases):
    return PandaBox(name="panda_box", host="localhost", signal_alias=_signal_aliases)


def test_panda_box_init(panda_box, _signal_aliases):
    """Test initialization of PandaBox, including default signal aliases."""
    assert panda_box.name == "panda_box"
    assert panda_box.host == "localhost"
    all_signal_names = [name for name, _ in panda_box.data.signals]
    for block in PANDA_AVAIL_PCAP_BLOCKS:
        for field in PANDA_AVAIL_PCAP_CAPTURE_FIELDS:
            signal_name = f"{block}.{field}"
            if signal_name in ("FMC_IN.VAL1.Value", "FMC_IN.VAL2.Mean"):
                # These signals should be renamed
                assert _signal_aliases[signal_name] in all_signal_names
                continue
            assert signal_name in all_signal_names, f"Missing signal: {signal_name}"


def test_panda_wait_for_connection(panda_box):
    """Test that wait_for_connection can be called without error."""
    with mock.patch.object(panda_box, "send_raw") as mock_send_raw:
        mock_send_raw.return_value = "OK"
        panda_box.wait_for_connection(timeout=1)
        mock_send_raw.assert_called_with("*IDN?")


def test_panda_on_connected(panda_box):
    """Test that on_connected sets the connected flag."""
    with mock.patch.object(panda_box, "data_thread") as mock_data_thread:
        panda_box.on_connected()
        mock_data_thread.start.assert_called_once()
        assert len(panda_box._data_callbacks) == 1
        cb_id = list(panda_box._data_callbacks.keys())[0]
        assert panda_box._data_callbacks[cb_id]["callback"] == panda_box._receive_frame_data
        assert panda_box._data_callbacks[cb_id]["data_type"] == PandaState.FRAME

        # Remove callback
        panda_box.remove_data_callback(cb_id)
        assert len(panda_box._data_callbacks) == 0, "Data callback was not removed"


def test_panda_add_status_callback(panda_box):
    """Test that add_status_callback adds proper status callbacks, and resolves them correctly."""

    assert panda_box.panda_state == PandaState.DISARMED, "Initial PandaBox state should be DISARMED"
    status = StatusBase(obj=panda_box)
    # I. Resolve immediately, should be successful
    panda_box.add_status_callback(status=status, success=PandaState.DISARMED, failure=[])
    status.wait(timeout=1)
    assert status.done, "Status should be done"
    assert status.success, "Status should be successful"
    assert len(panda_box._status_callbacks) == 0, "Status callback should never be added"

    # II. Resolve immediately, but with failure state, should be unsuccessful
    status = StatusBase(obj=panda_box)
    panda_box.add_status_callback(status=status, success=[], failure=PandaState.DISARMED)
    with pytest.raises(RuntimeError):
        status.wait(timeout=1)
    assert status.done, "Status should be done"
    assert not status.success, "Status should be unsuccessful"
    assert len(panda_box._status_callbacks) == 0, "Status callback should never be added"

    # III. Resolve status in success
    status = StatusBase(obj=panda_box)
    panda_box.add_status_callback(status=status, success=PandaState.READY, failure=[])
    assert len(panda_box._status_callbacks) == 1, "Status callback should be added"
    panda_box._run_status_callbacks(PandaState.START)
    assert not status.done, "Status should not be done"
    assert not status.success, "Status should not be successful"
    panda_box._run_status_callbacks(PandaState.READY)
    status.wait(timeout=1)
    assert status.done, "Status should be done"
    assert status.success, "Status should be successful"

    # IV. Resolve status in failure
    status = StatusBase(obj=panda_box)
    panda_box.add_status_callback(status=status, success=[PandaState.END], failure=PandaState.START)
    panda_box._run_status_callbacks(PandaState.START)
    with pytest.raises(RuntimeError):
        status.wait(timeout=1)
    assert status.done, "Status should be done"
    assert not status.success, "Status should be unsuccessful"


def test_panda_receive_frame_data(panda_box, _signal_aliases):
    """Test that _receive_frame_data processes data and updates signals."""
    # Create a mock frame data dict
    data = np.array(
        [
            (np.float64(0), np.float64(10)),
            (np.float64(1), np.float64(11)),
            (np.float64(2), np.float64(12)),
        ],
        dtype=[("FMC_IN.VAL1.Value", "<f8"), ("COUNTER2.OUT.Value", "<f8")],
    )
    fdata = FrameData(data)

    panda_box._receive_frame_data(fdata)
    # Check that the correct signals were updated
    expected_data = {
        f"{panda_box.data.name}_my_signal_1": {
            "value": [np.float64(0), np.float64(1), np.float64(2)],
            "timestamp": mock.ANY,
        },
        f"{panda_box.data.name}_COUNTER2.OUT.Value": {
            "value": [np.float64(10), np.float64(11), np.float64(12)],
            "timestamp": mock.ANY,
        },
    }
    md = {
        "async_update": {"type": "add", "max_shape": [None]},
        "acquisition_group": panda_box._acquisition_group,
    }
    d = panda_box.data.read()
    assert d[panda_box.data.name]["value"].metadata == md, "Metadata mismatch"
    for key, v in expected_data.items():
        assert key in d[panda_box.data.name]["value"].signals, f"Missing signal: {key}"
        assert np.isclose(
            d[panda_box.data.name]["value"].signals[key]["value"], v["value"]
        ).all(), f"Incorrect values for {key}"
        assert (
            "timestamp" in d[panda_box.data.name]["value"].signals[key]
        ), f"Missing timestamp for {key}"


def test_panda_on_stop(panda_box):
    """Test that on_stop clears the data callbacks."""
    with mock.patch.object(panda_box, "_disarm") as mock_disarm:
        panda_box.stop()
        mock_disarm.assert_called_once()


def test_panda_on_destroy(panda_box):
    """Test that on_destroy clears the data callbacks."""
    panda_box.destroy()
    assert panda_box.data_thread_kill_event.is_set(), "Data thread kill event not set"
    assert panda_box.data_thread_run_event.is_set(), "Data thread run event not set"


def test_panda_on_stage_on_unstage(panda_box):
    """Test that on_stage sets the acquisition group."""
    panda_box.panda_state = PandaState.DISARMED
    panda_box.stage()
    assert panda_box.data_thread_run_event.is_set(), "Data thread run event not set"
    assert panda_box.staged == Staged.yes

    # Now we will unstage the panda box
    with mock.patch.object(panda_box, "_disarm") as mock_disarm:
        panda_box.unstage()
        mock_disarm.assert_called_once()
        assert panda_box.staged == Staged.no
        assert (
            not panda_box.data_thread_run_event.is_set()
        ), "Data thread run event should be unset after unstage"

    # We call on_stage again, but this time the PandaBox state is incorrect
    panda_box.panda_state = PandaState.FRAME
    with pytest.raises(RuntimeError):
        panda_box._stage_timeout_in_s = 0.1  # Set a short timeout for the test
        panda_box.stage()


def test_panda_get_signal_names_allowed_for_capture(panda_box):
    """Test that get_signal_names_allowed_for_capture returns the correct signal names."""
    return_capture = [
        "!INENC1.VAL",
        "!INENC2.VAL",
        "!INENC3.VAL",
        "!INENC4.VAL",
        "!PCAP.TS_START",
        "!PCAP.TS_END",
        "!PCAP.TS_TRIG",
        "!PCAP.GATE_DURATION",
        "!PCAP.BITS0",
        "!PCAP.BITS1",
        "!PCAP.BITS2",
        "!PCAP.BITS3",
        "!CALC1.OUT",
        "!CALC2.OUT",
        "!COUNTER1.OUT",
        "!COUNTER2.OUT",
        "!COUNTER3.OUT",
        "!COUNTER4.OUT",
        "!COUNTER5.OUT",
        "!COUNTER6.OUT",
        "!COUNTER7.OUT",
        "!COUNTER8.OUT",
        "!FILTER1.OUT",
        "!FILTER2.OUT",
        "!PGEN1.OUT",
        "!PGEN2.OUT",
        "!FMC_IN.VAL1",
        "!FMC_IN.VAL2",
        "!FMC_IN.VAL3",
        "!FMC_IN.VAL4",
        "!FMC_IN.VAL5",
        "!FMC_IN.VAL6",
        "!FMC_IN.VAL7",
        "!FMC_IN.VAL8",
        "!SFP3_SYNC_IN.POS1",
        "!SFP3_SYNC_IN.POS2",
        "!SFP3_SYNC_IN.POS3",
        "!SFP3_SYNC_IN.POS4",
        ".",
    ]

    with mock.patch.object(panda_box, "send_raw") as mock_send_raw:
        mock_send_raw.return_value = return_capture
        list_of_signals = panda_box._get_signal_names_allowed_for_capture()
        mock_send_raw.assert_called_once_with("*CAPTURE.*?")
        assert list_of_signals == PANDA_AVAIL_PCAP_BLOCKS, "Signal names mismatch"


def test_panda_get_signal_names_configured_for_capture(panda_box):
    """Test that get_signal_names_configured_for_capture returns the correct signal names."""
    return_capture = [
        "!INENC1.VAL Min Max Mean",
        "!INENC2.VAL Value",
        "!INENC3.VAL Diff",
        "!INENC4.VAL Sum",
        "!PCAP.TS_START Min Max",
    ]
    possible_signal_names = get_pcap_capture_fields()

    with mock.patch.object(panda_box, "send_raw") as mock_send_raw:
        mock_send_raw.return_value = return_capture
        list_of_signals = panda_box._get_signal_names_configured_for_capture()
        mock_send_raw.assert_called_once_with("*CAPTURE?")
        for signal in list_of_signals:
            assert signal in possible_signal_names, f"Unexpected signal: {signal}"


def test_panda_pre_scan_status_callback(panda_box):
    """Test that pre_scan_status_callback sets the acquisition group."""
    with mock.patch.object(panda_box, "_arm") as mock_arm:
        # I. Called with status that is not done, should do nothing
        status = StatusBase(obj=panda_box)
        panda_box._pre_scan_status_callback(status)
        mock_arm.assert_not_called()  # _arm should not be called in pre_scan_status_callback
        status.set_finished()
        # II. Called with status that is done, should arm the PandaBox
        panda_box._pre_scan_status_callback(status)
        mock_arm.assert_called_once()
        status = StatusBase(obj=panda_box)
        status.set_exception(RuntimeError("Test error"))
        # III. Called with status that is done but not successful, should do nothing
        mock_arm.reset_mock()
        panda_box._pre_scan_status_callback(status)
        mock_arm.assert_not_called()


def test_panda_get_pcap_capture_fields():
    """Test that get_pcap_capture_fields returns the correct list of capture fields."""
    expected_fields = []
    for block in PANDA_AVAIL_PCAP_BLOCKS:
        for field in PANDA_AVAIL_PCAP_CAPTURE_FIELDS:
            expected_fields.append(f"{block}.{field}")
    actual_fields = get_pcap_capture_fields()
    assert actual_fields == expected_fields, "PCAP capture fields mismatch"
