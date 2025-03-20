"""Module for custom PSI components."""

from typing import Callable, Literal

from ophyd import Component, Kind, Signal
from ophyd.device import DynamicDeviceComponent
from ophyd.signal import EpicsSignalBase
from typeguard import typechecked

from ophyd_devices.utils.psi_signals import (
    DynamicSignal,
    FileEventSignal,
    Preview1DSignal,
    Preview2DSignal,
    ProgressSignal,
)

# pylint: disable=arguments-differ
# pylint: disable=arguments-renamed
# pylint: disable=too-many-arguments
# pylint: disable=signature-differs


class ProgressComponent(Component):
    """Component for progress signals."""

    def __init__(self, *args, doc: str | None = None, **kwargs):
        """
        Create a new ProgressComponent object.

        Args:
            doc (str | None) : The documentation string.
        """
        signal_class = ProgressSignal
        super().__init__(signal_class, *args, doc=doc, **kwargs)


class FileEventComponent(Component):
    """Component for file event signals."""

    def __init__(self, *args, doc: str | None = None, **kwargs):
        """
        Create a new FileEventComponent object.

        Args:
            doc (str | None) : The documentation string.
        """
        signal_class = FileEventSignal
        super().__init__(signal_class, *args, doc=doc, **kwargs)


class Preview1DComponent(Component):
    """Component for 1D preview signals."""

    def __init__(self, *args, doc: str | None = None, **kwargs):
        """
        Create a new Preview1DComponent object.

        Args:
            doc (str | None) : The documentation string.
        """
        signal_class = Preview1DSignal
        self._ndim = 1
        super().__init__(signal_class, *args, doc=doc, **kwargs)

    @property
    def ndim(self):
        """Return the number of dimensions."""
        return self._ndim


class Preview2DComponent(Component):
    """Component for 2D preview signals."""

    def __init__(self, *args, doc: str | None = None, **kwargs):
        """
        Create a new Preview2DComponent object.

        Args:
            doc (str | None) : The documentation string.
        """
        signal_class = Preview2DSignal
        self._ndim = 2
        super().__init__(signal_class, *args, doc=doc, **kwargs)

    @property
    def ndim(self):
        """Return the number of dimensions."""
        return self._ndim


class DynamicSignalComponent(Component):
    """Component for dynamic signals."""

    @typechecked
    def __init__(
        self,
        *args,
        signal_names: list[str] | Callable[[], list[str]],
        doc: str | None = None,
        **kwargs,
    ):
        """
        Create a new DynamicSignalComponent object.

        Args:
            signal_names (list[str] | Callable) : The names of all signals. Can be a list or a callable.
            doc (str | None)                    : The documentation string.
        """

        signal_class = DynamicSignal
        if callable(signal_names):
            self.signal_names = signal_names()
        elif isinstance(signal_names, list):
            self.signal_names = signal_names
        else:
            raise ValueError(f"signal_names {signal_names} must be a list or a callable")
        super().__init__(signal_class, *args, signal_names=signal_names, doc=doc, **kwargs)


class Async1DComponent(DynamicDeviceComponent):  # Probably easy to merge this
    """Component for asynchronous 1D signals.

    Note. DynamicDeviceComponent do not work with simple Signals,
    conflict with the name attribute within the signature
    """

    # Pydantic model for signal_def?
    def __init__(
        self,
        signal_def: dict[
            Literal["name"],
            dict[Literal["kind", "doc", "signal_class", "suffix"] | str, str | Kind],
        ],
        *,
        doc: str | None = None,
    ) -> None:
        """
        Create a new Async1DComponent object.

        Args:

            signal_def (dict) : Dictionary that defines the async sub component signals.
                                Keys are the signal names, values are dictionaries with
                                'kind', 'doc', 'signal_class', 'suffix'  keys.
                                Signal class must be of instance ophyd.Signal. For EpicsSingal,
                                suffix is mandatory.
                                signal_class defaults to ophyd.Signal
                                suffix is optional, mandatory for EpicsSignal and ignored Signal.
                                Kind defaults to Kind.normal, doc defaults to ''.
            doc (str | None)  : The documentation for the async sub component.
        """
        dcpt_defn = {}
        # Parse the signal definition, we init signals with None as value
        for name, signal_def in signal_def.items():
            suffix = signal_def.get("suffix", None)
            kind = signal_def.get("kind", Kind.normal)
            cpt_doc = signal_def.get("doc", "")
            signal_class = signal_def.get("signal_class", Signal)
            if not issubclass(signal_class, Signal):
                raise ValueError(f"signal_class must be a Signal class, got {signal_class}")
            if signal_class is Signal:
                suffix = None
            if issubclass(signal_class, EpicsSignalBase) and suffix is None:
                raise ValueError(
                    f"Any EpicsSignal {signal_class} requires a suffix, got {suffix}. Please specify 'suffix' in signal_def"
                )
            dcpt_defn[name] = (signal_class, suffix, {"kind": kind, "doc": cpt_doc})
        doc = doc if doc else "Sub-device for asynchronous 1D signals"
        # 1D signals
        self._ndim = 1
        super().__init__(defn=dcpt_defn, doc=doc, kind=Kind.omitted)

    @property
    def ndim(self):
        """Return the number of dimensions."""
        return self._ndim

    def subscriptions(self, event_type):
        pass


class Async2DComponent(Async1DComponent):  # Probably easy to merge this
    """Component for asynchronous 1D signals."""

    def __init__(
        self,
        signal_def: dict[Literal["name"], dict[Literal["suffix", "kind", "doc"] | str, str | Kind]],
        *,
        doc: str | None = None,
        **kwargs,
    ) -> None:
        """
        Create a new Async1DComponent object.

        Args:

            signal_def (dict) : A nested dictionary with 'name', 'suffix', 'kind' and 'doc' keys.
                                Suffix is mandatory.
                                Kind defaults to Kind.normal, doc defaults to ''.
            doc (str | None)  : The documentation for the async sub component.
        """
        doc = doc if doc else "Sub-device for asynchronous 2D signals"
        super().__init__(signal_def=signal_def, doc=doc, **kwargs)
        self._ndim = 2
