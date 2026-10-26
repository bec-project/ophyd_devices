"""BEC signal metadata updates use a dedicated ophyd subscription event."""

from __future__ import annotations

import numpy as np
import pytest
from bec_lib import messages
from ophyd import Device

from ophyd_devices.utils.bec_signals import PreviewSignal


def test_preview_accepts_transport_metadata_at_construction():
    transport = messages.ZMQSignalTransport(
        address="tcp://detector-host:5555", encoder="adzmq-array-1.0"
    )
    parent = Device(name="detector")
    preview = PreviewSignal(name="preview", parent=parent, ndim=2, transports=[transport])
    try:
        assert preview.transports == [transport]
        assert preview.signal_info.transports == [transport]
        info = preview.describe()[preview.name]["signal_info"]
        assert info["transports"][0]["address"] == "tcp://detector-host:5555"
    finally:
        preview.destroy()
        parent.destroy()


def test_preview_transport_assignment_validates_and_preserves_old_value():
    from pydantic import ValidationError

    parent = Device(name="detector")
    preview = PreviewSignal(name="preview", parent=parent, ndim=2)
    transport = messages.ZMQSignalTransport(
        address="tcp://detector-host:5555", encoder="adzmq-array-1.0"
    )
    try:
        preview.transports = [transport]
        with pytest.raises(ValidationError):
            preview.transports = [{"transport": "zmq", "address": "", "encoder": ""}]
        assert preview.transports == [transport]
        preview.transports = None
        assert preview.signal_info.transports is None
    finally:
        preview.destroy()
        parent.destroy()


def test_signal_info_uses_dedicated_ophyd_subscription_event():
    parent = Device(name="detector")
    signal = PreviewSignal(name="preview", parent=parent, ndim=2)
    info_events, data_events = [], []
    cid = signal.subscribe(
        lambda **event: info_events.append(event),
        event_type=signal.SUB_SIGNAL_INFO_CHANGED,
        run=False,
    )
    signal.subscribe(lambda **event: data_events.append(event), run=False)
    try:
        transport = messages.ZMQSignalTransport(
            address="tcp://detector-host:5555", encoder="adzmq-array-1.0"
        )
        signal.transports = [transport]
        assert len(info_events) == 1
        assert not data_events
        assert info_events[0]["obj"] is signal
        assert info_events[0]["value"].transports == [transport]
        assert info_events[0]["sub_type"] == signal.SUB_SIGNAL_INFO_CHANGED
        info_events[0]["value"].transports.clear()
        assert signal.transports == [transport]  # Callback receives a snapshot.
        signal.put(np.zeros((2, 3)))
        assert len(data_events) == 1
        assert len(info_events) == 1
        signal.signal_info.signal_metadata["custom"] = True
        signal.notify_signal_info_changed()
        assert info_events[-1]["value"].signal_metadata["custom"] is True
        signal.unsubscribe(cid)
        signal.transports = None
        assert len(info_events) == 2
    finally:
        signal.destroy()
        parent.destroy()


def test_invalid_transport_does_not_emit_metadata_event():
    from pydantic import ValidationError

    signal = PreviewSignal(name="preview", parent=Device(name="detector"), ndim=2)
    events = []
    signal.subscribe(
        lambda **event: events.append(event), event_type=signal.SUB_SIGNAL_INFO_CHANGED, run=False
    )
    try:
        with pytest.raises(ValidationError):
            signal.transports = [{"transport": "zmq", "address": "", "encoder": ""}]
        assert not events
    finally:
        signal.destroy()
        signal.parent.destroy()
