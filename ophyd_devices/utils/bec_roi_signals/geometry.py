"""
Read-only Ophyd configuration fields generated from supported ROI shape schemas.
"""

from __future__ import annotations

from copy import copy
from functools import lru_cache
from typing import TYPE_CHECKING, Any, get_args

import numpy as np
from bec_lib.messages import ROIConfiguration
from ophyd import Component, Device, Kind, Signal, SignalRO
from pydantic import BaseModel

if TYPE_CHECKING:
    from ophyd_devices.utils.bec_roi_signals.roi import ROI


class ROIGeometry(Device):
    """
    Expose applied shape fields as read-only configuration signals.

    A concrete subclass is generated once per allowed-schema combination. Fields
    shared by several shapes appear once; fields absent from the current shape are
    reset to zero or empty arrays. The type signal identifies the active shape.
    Geometry changes never add or remove components. Only the owning ROI records
    backend-confirmed geometry; user changes go through update_received.
    """

    def _record(self, config: ROIConfiguration) -> None:
        """
        Update the read-only fields from a confirmed, validated geometry.

        Args:
            config (ROIConfiguration): Applied shape. Arrays are copied into numeric
                or boolean signals so configuration consumers need no JSON decoding.
        """
        values = config.model_dump()
        for name in self.component_names:
            signal = getattr(self, name)
            default = self._sig_attrs[name].kwargs["value"]
            value = values.get(name, default)
            if isinstance(default, np.ndarray):
                value = np.asarray(value, dtype=default.dtype).copy()
            elif isinstance(default, float):
                value = float(value)
            Signal.put(signal, value, force=True)


@lru_cache
def _geometry_class(schemas: tuple[type[BaseModel], ...]) -> type[ROIGeometry]:
    """
    Build a stable component layout from the union of the permitted schema fields.

    Args:
        schemas (tuple[type[BaseModel], ...]): Supported BEC ROI model classes.

    Returns:
        type[ROIGeometry]: Device class with scalar or array configuration signals.
    """
    fields: dict[str, set[Any]] = {}
    for schema in schemas:
        for name, field in schema.model_fields.items():
            fields.setdefault(name, set()).add(field.annotation)
    components = {}
    for name, field_types in fields.items():
        if name == "type":
            value = ""
        elif name == "mask":
            value = np.empty((0, 0), dtype=bool)
        elif name == "vertices":
            value = np.empty((0, 2), dtype=float)
        elif float in field_types:
            value = 0.0
        elif field_types == {int}:
            value = 0
        else:
            raise TypeError(f"Unsupported ROI geometry field: {name}")
        components[name] = Component(SignalRO, value=value, kind=Kind.config)
    return type("ROIGeometryFields", (ROIGeometry,), components)


class ROIGeometryComponent(Component):
    """
    Create a geometry subdevice using the parent ROI's allowed shape schemas.

    This delegates naming, kinds and parenting to the ordinary Ophyd Component
    implementation. Copy the descriptor before selecting its class so two ROI
    instances can support different shapes without changing shared descriptors.
    """

    def __init__(self, **kwargs: Any) -> None:
        """
        Declare a geometry component without constructing signals or connecting I/O.

        Args:
            **kwargs (Any): Ordinary Component options, including kind and lazy.
        """
        super().__init__(ROIGeometry, **kwargs)

    def create_component(self, instance: ROI) -> ROIGeometry:
        """
        Instantiate the fixed set of fields supported by this ROI.

        Args:
            instance (ROI): Owning ROI with validated allowed_roi_config_types.

        Returns:
            ROIGeometry: Read-only geometry subdevice; no backend communication occurs.
        """
        schemas = instance.allowed_roi_config_types
        if schemas is None:
            # ROIConfiguration is Annotated[Union[shape models], discriminator].
            schemas = get_args(get_args(ROIConfiguration)[0])
        component = copy(self)
        component.cls = _geometry_class(schemas)
        return Component.create_component(component, instance)
