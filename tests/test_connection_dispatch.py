"""Connection hooks belong to each owning device, without implicit traversal."""

from ophyd import Component as Cpt
from ophyd import Device, Signal

from ophyd_devices import PSIDeviceBase


def test_default_connection_hook_does_not_instantiate_lazy_children():
    class Child(Device):
        signal = Cpt(Signal, value=0)

        def on_connected(self):
            raise AssertionError("Child hook must be called explicitly")

    class Root(PSIDeviceBase):
        child = Cpt(Child, "", lazy=True)

    root = Root(name="test")
    try:
        root.on_connected()
        assert "child" not in root._signals
    finally:
        root.destroy()


def test_owner_controls_child_connection_order_without_duplicate_dispatch():
    calls = []

    class Child(Device):
        def on_connected(self):
            calls.append(self.dotted_name)

    class Root(PSIDeviceBase):
        first = Cpt(Child, "")
        second = Cpt(Child, "")

        def on_connected(self):
            super().on_connected()
            calls.append("root")
            self.second.on_connected()
            self.first.on_connected()

    root = Root(name="test")
    try:
        root.on_connected()
        assert calls == ["root", "second", "first"]
    finally:
        root.destroy()
