"""BEC signal metadata updates use a dedicated ophyd subscription event."""

from __future__ import annotations

import numpy as np
import pytest
from bec_lib import messages
from ophyd import Component, Device, Signal

from ophyd_devices.utils.bec_signals import AsyncMultiSignal, AsyncSignal, PreviewSignal


@pytest.mark.filterwarnings("ignore:BECMessageSignal.* is deprecated:DeprecationWarning")
@pytest.mark.parametrize(
    ("field", "value", "equivalent"),
    [
        ("ndim", 1, 1),
        ("signals", [("data", 1)], [["data", 1]]),
        ("signal_metadata", {"custom": True}, {"custom": True}),
        ("num_rotation_90", 1, 1),
        ("transpose", True, True),
        (
            "transports",
            [
                messages.ZMQSignalTransport(
                    address="tcp://detector-host:5555", encoder="adzmq-array-1.0"
                )
            ],
            [
                {
                    "transport": "zmq",
                    "address": "tcp://detector-host:5555",
                    "encoder": "adzmq-array-1.0",
                }
            ],
        ),
    ],
)
def test_metadata_setters_emit_only_for_changes(field, value, equivalent):
    parent = Device(name="detector")
    signal = PreviewSignal(name="preview", parent=parent, ndim=2)
    event_type = signal.SUB_SIGNAL_INFO_CHANGED
    events = []
    signal.subscribe(lambda **event: events.append(event), event_type=event_type, run=False)
    try:
        setattr(signal, field, value)
        assert len(events) == 1
        setattr(signal, field, equivalent)
        assert len(events) == 1
        signal.notify_signal_info_changed()
        assert len(events) == 2
    finally:
        signal.destroy()
        parent.destroy()


def test_async_signal_max_size_emits_only_for_changes():
    parent = Device(name="detector")
    signal = AsyncSignal(name="async_data", parent=parent, ndim=1, max_size=100)
    events = []
    signal.subscribe(
        lambda **event: events.append(event), event_type=signal.SUB_SIGNAL_INFO_CHANGED, run=False
    )
    try:
        signal.max_size = 100
        assert not events
        signal.max_size = 200
        assert len(events) == 1
        assert events[0]["value"].signal_metadata["max_size"] == 200
        signal.max_size = 200
        assert len(events) == 1
    finally:
        signal.destroy()
        parent.destroy()


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


def test_async_signal_stores_string_alias_as_a_mapping():
    class Analysis(Device):
        buffered = Component(AsyncSignal, ndim=1, max_size=10, use_alias=True, alias="reading")
        reading = Component(Signal, value=0)

    class Camera(Device):
        analysis = Component(Analysis, "")

    camera = Camera(name="cam")
    try:
        signal = camera.analysis.buffered
        assert signal.signal_info.aliases == {signal.name: "reading"}
        assert signal.describe()[signal.name]["signal_info"]["aliases"] == {
            signal.name: "cam_analysis_reading"
        }
    finally:
        camera.destroy()


def test_async_multi_signal_describes_aliases_by_declared_source():
    class Camera(Device):
        buffered = Component(
            AsyncMultiSignal,
            ndim=1,
            max_size=10,
            signals=["mean", "std"],
            aliases={"mean": "reading", "std": "deviation"},
            use_alias=True,
        )
        reading = Component(Signal, value=0)
        deviation = Component(Signal, value=0)

    camera = Camera(name="cam")
    try:
        signal = camera.buffered
        assert signal.describe()[signal.name]["signal_info"]["aliases"] == {
            "mean": "cam_reading",
            "std": "cam_deviation",
        }
    finally:
        camera.destroy()


def test_async_multi_signal_accepts_the_declared_key_for_one_signal():
    aliases = {"mean": "reading"}

    class Camera(Device):
        buffered = Component(
            AsyncMultiSignal, ndim=1, max_size=10, signals=["mean"], aliases=aliases, use_alias=True
        )
        reading = Component(Signal, value=0)

    camera = Camera(name="cam")
    try:
        signal = camera.buffered
        assert [name for name, _ in signal.signal_info.signals] == ["cam_buffered"]
        assert signal.signal_info.aliases == {"cam_buffered": "reading"}
        assert signal.describe()[signal.name]["signal_info"]["aliases"] == {
            "cam_buffered": "cam_reading"
        }
        assert aliases == {"mean": "reading"}
    finally:
        camera.destroy()


def test_unaliased_standalone_async_signal_can_be_described():
    signal = AsyncSignal(name="buffered", ndim=1, max_size=10)
    try:
        assert signal.describe()[signal.name]["signal_info"]["aliases"] is None
    finally:
        signal.destroy()


@pytest.mark.parametrize("use_alias", [True, False])
def test_async_multi_signal_rejects_duplicate_active_alias_targets(use_alias):
    class Camera(Device):
        buffered = Component(
            AsyncMultiSignal,
            ndim=1,
            max_size=10,
            signals=["mean", "std"],
            aliases={"mean": "reading", "std": "reading"},
            use_alias=use_alias,
        )
        reading = Component(Signal, value=0)

    camera = Camera(name="cam")
    try:
        if use_alias:
            with pytest.raises(
                ValueError, match="cam_buffered_mean.*cam_buffered_std.*cam_reading"
            ):
                camera.buffered.describe()
        else:
            camera.buffered.describe()
    finally:
        camera.destroy()


@pytest.mark.parametrize("saved", [True, False])
@pytest.mark.parametrize("lazy", [True, False])
def test_separate_async_signals_reject_shared_alias_target(saved, lazy):
    class Analysis(Device):
        first = Component(AsyncSignal, ndim=1, max_size=10, alias="reading", use_alias=True)
        second = Component(
            AsyncSignal, ndim=1, max_size=10, alias="reading", use_alias=True, lazy=lazy
        )
        reading = Component(Signal, value=0)

    class Camera(Device):
        analysis = Component(Analysis, "")

    camera = Camera(name="cam")
    try:
        if saved:
            with pytest.raises(
                ValueError, match="cam_analysis_first.*cam_analysis_second.*cam_analysis_reading"
            ):
                camera.analysis.first.describe()
        else:
            camera.analysis.second.signal_info.saved = False
            camera.analysis.first.describe()
    finally:
        camera.destroy()


def test_async_alias_rejects_collision_with_unaliased_producer():
    class Camera(Device):
        buffered = Component(AsyncSignal, ndim=1, max_size=10, alias="reading", use_alias=True)
        reading = Component(AsyncSignal, ndim=1, max_size=10)

    camera = Camera(name="cam")
    try:
        with pytest.raises(ValueError, match="cam_buffered.*cam_reading.*cam_reading"):
            camera.buffered.describe()
    finally:
        camera.destroy()


def test_async_alias_validation_uses_current_flags():
    class Camera(Device):
        first = Component(AsyncSignal, ndim=1, max_size=10, alias="reading", use_alias=True)
        second = Component(AsyncSignal, ndim=1, max_size=10, alias="reading", use_alias=False)
        reading = Component(Signal, value=0)

    camera = Camera(name="cam")
    try:
        camera.first.describe()
        camera.second.signal_info.use_alias = True
        with pytest.raises(ValueError, match="cam_first.*cam_second.*cam_reading"):
            camera.first.describe()
        camera.second.signal_info.use_alias = False
        camera.first.describe()
    finally:
        camera.destroy()
