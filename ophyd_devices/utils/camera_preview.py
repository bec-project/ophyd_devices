"""Image and ROI preview values collected on the camera worker."""

from collections.abc import Mapping
from dataclasses import dataclass, field

from numpy.typing import NDArray


@dataclass(frozen=True)
class CameraPreview:
    """Owned preview data addressed to an exposed PreviewSignal."""

    signal: str
    data: NDArray
    frame_id: int
    timestamp: float
    metadata: Mapping[str, object] = field(default_factory=dict)
    oriented: bool = False
