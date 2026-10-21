"""
Simulated camera that streams live preview frames as JPEG (or raw counts) to BEC.

The frames look like a diffraction detector: rings, a diffuse background, Bragg spots, module
gaps, a beam stop and Poisson noise. Frame size, encoding, JPEG quality, frame rate and the
8-bit scaling can all be changed while the stream is running, e.g. from the BEC client:

>>> dev.jpeg_cam.configure_stream(width=2048, height=2048, encoding="jpeg_gray", quality=90)
>>> dev.jpeg_cam.start_live()

JPEG frames are sent through the regular preview signal as a flat uint8 array holding the
JPEG bytes. The message metadata says how to read it:

``{"encoding": "jpeg", "shape": [h, w], "channels": 1 | 3, ...}``

Raw frames are sent as a 2D uint16 array with ``{"encoding": "raw", ...}``.
"""

from __future__ import annotations

import threading
import time
from typing import Literal

import numpy as np
from bec_lib.logger import bec_logger
from ophyd import Component as Cpt
from ophyd import Device, Kind, Signal

from ophyd_devices.interfaces.base_classes.psi_device_base import PSIDeviceBase
from ophyd_devices.utils.bec_signals import PreviewSignal
from ophyd_devices.utils.psi_device_base_utils import DeviceStatus, StatusBase

try:  # simplejpeg (libjpeg-turbo) is several times faster than Pillow
    import simplejpeg
except ImportError:  # pragma: no cover - depends on the environment
    simplejpeg = None

logger = bec_logger.logger

Encoding = Literal["jpeg_gray", "jpeg_rgb", "raw"]
ENCODINGS: tuple[str, ...] = ("jpeg_gray", "jpeg_rgb", "raw")
MAX_EDGE = 8192
NOISE_FRAMES = 4

# Anchor colours of a magma-like colour map, used for the colour JPEG mode
_MAGMA_ANCHORS = np.array(
    [
        [0, 0, 4],
        [28, 16, 68],
        [79, 18, 123],
        [129, 37, 129],
        [181, 54, 122],
        [229, 80, 100],
        [251, 135, 97],
        [254, 194, 135],
        [252, 253, 191],
    ],
    dtype=np.float32,
)


def _magma_lut() -> np.ndarray:
    """256-entry RGB lookup table interpolated from the magma anchors."""
    x = np.linspace(0, len(_MAGMA_ANCHORS) - 1, 256)
    lut = np.stack(
        [np.interp(x, np.arange(len(_MAGMA_ANCHORS)), _MAGMA_ANCHORS[:, c]) for c in range(3)],
        axis=1,
    )
    return lut.astype(np.uint8)


MAGMA_LUT = _magma_lut()


def encode_jpeg(image: np.ndarray, quality: int) -> bytes:
    """
    Encode a uint8 image as JPEG.

    Args:
        image (np.ndarray): (h, w) grayscale or (h, w, 3) RGB uint8 image.
        quality (int): JPEG quality, 1 to 100.

    Returns:
        bytes: The JPEG file content.
    """
    image = np.ascontiguousarray(image)
    if simplejpeg is not None:
        if image.ndim == 2:
            return simplejpeg.encode_jpeg(image[..., None], quality=quality, colorspace="GRAY")
        return simplejpeg.encode_jpeg(image, quality=quality, colorspace="RGB")
    # pylint: disable=import-outside-toplevel
    import io

    from PIL import Image

    buffer = io.BytesIO()
    Image.fromarray(image).save(buffer, format="JPEG", quality=quality)
    return buffer.getvalue()


class DiffractionFrameSource:
    """
    Fast generator of diffraction-like uint16 frames.

    The expensive part (the expected intensity and a few Poisson draws) is computed once per
    frame size. Each frame is one of the noise frames, shifted along a slow circle so the
    stream visibly moves.
    """

    def __init__(self, seed: int = 0):
        self._rng = np.random.default_rng(seed)
        self._shape: tuple[int, int] | None = None
        self._frames: list[np.ndarray] = []
        self._counter = 0

    @property
    def shape(self) -> tuple[int, int] | None:
        """Shape of the frames currently generated."""
        return self._shape

    def _build(self, shape: tuple[int, int]) -> None:
        h, w = shape
        y = np.arange(h, dtype=np.float32)[:, None]
        x = np.arange(w, dtype=np.float32)[None, :]
        cy, cx = h * 0.52, w * 0.48
        r = np.hypot(y - cy, x - cx) / max(h, w)
        lam = 40 * np.exp(-r * 6) + 5
        for r0, amp in ((0.08, 300), (0.15, 220), (0.22, 160), (0.31, 120)):
            lam += amp * np.exp(-((r - r0) ** 2) / (2 * 0.003**2))
        # beam stop: a disc and its holder arm
        lam[r < 0.025] = 0.5
        arm = (np.abs(y - cy) < max(2, h * 0.006)) & (x > cx)
        lam[np.broadcast_to(arm, lam.shape)] = 0.5
        frames = []
        n_spots = max(50, int(300 * h * w / 2048**2))
        for _ in range(NOISE_FRAMES):
            frame = self._rng.poisson(lam).astype(np.float32)
            sy, sx = self._rng.integers(0, h, n_spots), self._rng.integers(0, w, n_spots)
            frame[sy, sx] += self._rng.integers(1000, 30000, n_spots)
            frame = np.clip(frame, 0, 65535).astype(np.uint16)
            # module gaps, like a tiled detector
            frame[:, w // 2 - 4 : w // 2 + 4] = 0
            frame[h // 2 - 2 : h // 2 + 2, :] = 0
            frames.append(frame)
        self._frames = frames
        self._shape = shape

    def next_frame(self, shape: tuple[int, int]) -> np.ndarray:
        """
        Return the next frame of the given shape.

        Args:
            shape (tuple[int, int]): Frame height and width.

        Returns:
            np.ndarray: (h, w) uint16 frame.
        """
        if shape != self._shape:
            self._build(shape)
        self._counter += 1
        frame = self._frames[self._counter % NOISE_FRAMES]
        angle = self._counter * 0.15
        radius = max(2, min(shape) // 100)
        shift = (int(radius * np.sin(angle)), int(radius * np.cos(angle)))
        return np.roll(frame, shift, axis=(0, 1))


class SimJpegCameraControl(Device):
    """Control layer of the simulated JPEG camera: stream settings and the preview signal."""

    frame_width = Cpt(Signal, value=2048, kind=Kind.config, doc="Frame width in pixels")
    frame_height = Cpt(Signal, value=2048, kind=Kind.config, doc="Frame height in pixels")
    encoding = Cpt(
        Signal, value="jpeg_gray", kind=Kind.config, doc="jpeg_gray, jpeg_rgb or raw (uint16)"
    )
    jpeg_quality = Cpt(Signal, value=90, kind=Kind.config, doc="JPEG quality, 1 to 100")
    frame_rate = Cpt(Signal, value=5.0, kind=Kind.config, doc="Frames per second")
    jpeg_max_counts = Cpt(
        Signal,
        value=0.0,
        kind=Kind.config,
        doc="Counts mapped to 255 in JPEG modes; 0 uses the 99.9th percentile of each frame",
    )
    live = Cpt(Signal, value=False, kind=Kind.config, doc="Whether the live stream is running")
    preview = Cpt(PreviewSignal, name="preview", ndim=2, num_rotation_90=0)


class SimJpegCamera(PSIDeviceBase, SimJpegCameraControl):
    """Simulated camera streaming live preview frames as JPEG or raw counts."""

    USER_ACCESS = ["start_live", "stop_live", "set_resolution", "configure_stream"]

    def __init__(
        self,
        name: str,
        scan_info=None,
        device_manager=None,
        live_on_connect: bool = False,
        **kwargs,
    ):
        """
        Args:
            name (str): Device name.
            scan_info: Scan info passed by BEC.
            device_manager: Device manager passed by BEC.
            live_on_connect (bool): Start the live stream as soon as the device is connected.
        """
        self._live_on_connect = live_on_connect
        self._source = DiffractionFrameSource()
        self._stop_event = threading.Event()
        self._wake_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._frame_id = 0
        super().__init__(name=name, scan_info=scan_info, device_manager=device_manager, **kwargs)

    ########################################
    #  Beamline Specific Implementations   #
    ########################################

    def on_init(self) -> None:
        """
        Called when the device is initialized.

        No signals are connected at this point. If you like to
        set default values on signals, please use on_connected instead.
        """

    def on_connected(self) -> None:
        """
        Called after the device is connected and its signals are connected.
        Default values for signals should be set here.
        """
        self._start_thread()
        if self._live_on_connect:
            self.start_live()

    def on_stage(self) -> DeviceStatus | StatusBase | None:
        """
        Called while staging the device.

        Information about the upcoming scan can be accessed from the scan_info (self.scan_info.msg) object.
        """

    def on_unstage(self) -> DeviceStatus | StatusBase | None:
        """Called while unstaging the device."""

    def on_pre_scan(self) -> DeviceStatus | StatusBase | None:
        """Called right before the scan starts on all devices automatically."""

    def on_trigger(self) -> DeviceStatus | StatusBase | None:
        """Called when the device is triggered."""

    def on_complete(self) -> DeviceStatus | StatusBase | None:
        """Called to inquire if a device has completed a scans."""

    def on_kickoff(self) -> DeviceStatus | StatusBase | None:
        """Called to kickoff a device for a fly scan. Has to be called explicitly."""

    def on_stop(self) -> None:
        """Called when the device is stopped."""
        self.stop_live()

    def on_destroy(self) -> None:
        """Called when the device is destroyed. Cleanup resources here."""
        self._stop_event.set()
        self._wake_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    ########################################
    #            User Access               #
    ########################################

    def start_live(self) -> None:
        """Start streaming preview frames."""
        self.live.put(True)
        self._start_thread()
        self._wake_event.set()

    def stop_live(self) -> None:
        """Stop streaming preview frames."""
        self.live.put(False)

    def set_resolution(self, width: int, height: int) -> None:
        """
        Change the frame size, also while streaming.

        Args:
            width (int): Frame width in pixels.
            height (int): Frame height in pixels.
        """
        self.configure_stream(width=width, height=height)

    def configure_stream(
        self,
        width: int | None = None,
        height: int | None = None,
        encoding: Encoding | None = None,
        quality: int | None = None,
        frame_rate: float | None = None,
        max_counts: float | None = None,
    ) -> dict:
        """
        Change any stream setting, also while streaming. Unset arguments stay as they are.

        Args:
            width (int | None): Frame width in pixels, 16 to 8192.
            height (int | None): Frame height in pixels, 16 to 8192.
            encoding (str | None): "jpeg_gray", "jpeg_rgb" or "raw".
            quality (int | None): JPEG quality, 1 to 100.
            frame_rate (float | None): Frames per second, 0.1 to 100.
            max_counts (float | None): Counts mapped to 255 in JPEG modes; 0 means automatic.

        Returns:
            dict: The stream settings now in use.
        """
        if width is not None:
            self.frame_width.put(int(np.clip(width, 16, MAX_EDGE)))
        if height is not None:
            self.frame_height.put(int(np.clip(height, 16, MAX_EDGE)))
        if encoding is not None:
            if encoding not in ENCODINGS:
                raise ValueError(f"Unknown encoding {encoding!r}; use one of {ENCODINGS}")
            self.encoding.put(encoding)
        if quality is not None:
            self.jpeg_quality.put(int(np.clip(quality, 1, 100)))
        if frame_rate is not None:
            self.frame_rate.put(float(np.clip(frame_rate, 0.1, 100)))
        if max_counts is not None:
            self.jpeg_max_counts.put(max(0.0, float(max_counts)))
        self._wake_event.set()
        return self.stream_settings()

    ########################################
    #            Helper Methods            #
    ########################################

    def stream_settings(self) -> dict:
        """Current stream settings as a plain dict."""
        return {
            "width": int(self.frame_width.get()),
            "height": int(self.frame_height.get()),
            "encoding": str(self.encoding.get()),
            "quality": int(self.jpeg_quality.get()),
            "frame_rate": float(self.frame_rate.get()),
            "max_counts": float(self.jpeg_max_counts.get()),
            "live": bool(self.live.get()),
        }

    def _start_thread(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._stream_loop, name=f"{self.name}_live", daemon=True
        )
        self._thread.start()

    def _stream_loop(self) -> None:
        while not self._stop_event.is_set():
            if not self.live.get():
                self._wake_event.wait(0.5)
                self._wake_event.clear()
                continue
            t_start = time.perf_counter()
            try:
                self.publish_frame()
            except Exception:  # pylint: disable=broad-except
                logger.exception(f"{self.name}: failed to publish a preview frame")
            period = 1.0 / max(0.1, float(self.frame_rate.get()))
            remaining = period - (time.perf_counter() - t_start)
            if remaining > 0:
                self._wake_event.wait(remaining)
                self._wake_event.clear()

    def make_frame(self) -> tuple[np.ndarray, dict]:
        """
        Generate and encode one frame with the current settings.

        Returns:
            tuple[np.ndarray, dict]: The preview payload and its message metadata.
        """
        settings = self.stream_settings()
        shape = (settings["height"], settings["width"])
        t_capture = time.time()
        t0 = time.perf_counter()
        frame = self._source.next_frame(shape)
        generate_ms = (time.perf_counter() - t0) * 1e3
        self._frame_id += 1
        metadata = {
            "encoding": "raw",
            "shape": list(shape),
            "frame_id": self._frame_id,
            "timestamp_capture": t_capture,
            "raw_nbytes": int(frame.nbytes),
            "generate_ms": round(generate_ms, 2),
            "encode_ms": 0.0,
        }
        if settings["encoding"] == "raw":
            return frame, metadata

        t0 = time.perf_counter()
        top = settings["max_counts"]
        if top <= 0:
            top = float(np.percentile(frame[::8, ::8], 99.9)) or 1.0
        frame8 = np.clip(frame * np.float32(255.0 / top), 0, 255).astype(np.uint8)
        if settings["encoding"] == "jpeg_rgb":
            frame8 = MAGMA_LUT[frame8]
        jpeg = encode_jpeg(frame8, settings["quality"])
        metadata.update(
            {
                "encoding": "jpeg",
                "channels": 3 if frame8.ndim == 3 else 1,
                "quality": settings["quality"],
                "scale_max_counts": top,
                "encode_ms": round((time.perf_counter() - t0) * 1e3, 2),
            }
        )
        return np.frombuffer(jpeg, dtype=np.uint8), metadata

    def publish_frame(self) -> None:
        """Generate, encode and send one preview frame."""
        data, metadata = self.make_frame()
        self.preview.put(data, metadata=metadata)
