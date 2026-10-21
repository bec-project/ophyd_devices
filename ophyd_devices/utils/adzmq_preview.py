"""ADZMQ publishing for simulated camera preview signals."""

from __future__ import annotations

import io
import json
from collections.abc import Callable
from threading import Condition, Event, Lock, Thread

import numpy as np
import zmq
from bec_lib import messages
from bec_lib.endpoints import MessageEndpoints
from bec_lib.logger import bec_logger
from PIL import Image

from ophyd_devices.utils.bec_signals import PreviewSignal


class ADZMQPreviewPublisher:
    """Thread-owned, best-effort ADZMQ publishing for an existing preview signal.

    No socket is opened until ``start_zmq`` is called after device connection.
    Redis callbacks retain the original array. ZMQ has a one-frame producer
    mailbox, so intermediate previews may be dropped. JPEG encoding runs in the
    publisher thread and never changes the original acquisition or Redis array.

    Args:
        signal (PreviewSignal): Existing camera preview signal to subscribe to.
    """

    # The publisher owns its thread, lifecycle state, mailbox, and socket settings.
    # pylint: disable=too-many-instance-attributes

    def __init__(self, signal: PreviewSignal) -> None:
        self.signal = signal
        self._subscription: int | None = None
        self._condition = Condition()
        self._lifecycle_lock = Lock()
        self._stop = Event()
        self._ready = Event()
        self._thread: Thread | None = None
        self._pending = None
        self._error: Exception | None = None
        self._address: str | None = None
        self._frame = 0
        self._closed = False
        self._bind_address = "tcp://127.0.0.1:*"
        self._connect_address: str | None = None
        self._jpeg_enabled: Callable[[], bool] = lambda: False

    def configure_zmq(
        self, bind_address: str, connect_address: str | None, jpeg_enabled: Callable[[], bool]
    ) -> None:
        """Configure local bind, advertised URI, and compression switch before starting.

        Args:
            bind_address (str): Local publisher URI, optionally with a wildcard port.
            connect_address (str | None): Client URI for a fixed bind port; None
                advertises the resolved bind URI. Wildcard hosts require an explicit URI.
            jpeg_enabled (Callable[[], bool]): Read the current JPEG configuration.
        """
        if self._thread is not None:
            raise RuntimeError("Cannot configure a started preview publisher")
        if not bind_address:
            raise ValueError("Preview bind address must not be empty")
        if connect_address is not None and (not connect_address or "*" in connect_address):
            raise ValueError("Advertised preview address must be a concrete URI")
        if bind_address.startswith("tcp://"):
            host, port = bind_address[6:].rsplit(":", 1)
            if host in ("*", "0.0.0.0", "[::]") and connect_address is None:
                raise ValueError("Wildcard bind hosts require an advertised preview address")
            if port == "*" and connect_address is not None:
                raise ValueError("An advertised preview address requires a fixed bind port")
        self._bind_address = bind_address
        self._connect_address = connect_address
        self._jpeg_enabled = jpeg_enabled

    def start_zmq(self) -> None:
        """Bind in the socket-owning thread and advertise its resolved client URI.

        Connection-time setup waits at most two seconds for bind completion.
        A failed or timed-out publisher remains failed; destroy and recreate the
        device before retrying. Acquisition and JPEG encoding do not run on the
        connecting thread.
        """
        with self._lifecycle_lock:
            if self._closed:
                raise RuntimeError("Preview signal is destroyed")
            if self._thread is not None:
                if self._error is not None:
                    raise RuntimeError("Preview publisher failed") from self._error
                return
            self._thread = Thread(
                target=self._run, name=f"ADZMQPreview-{self.signal.name}", daemon=True
            )
            try:
                self._thread.start()
            except Exception:
                self._thread = None
                raise
            if not self._ready.wait(2):
                error = TimeoutError("Preview publisher did not bind within two seconds")
                with self._condition:
                    self._error = error
                    self._stop.set()
                    self._condition.notify_all()
                raise error
            if self._error is not None:
                raise RuntimeError("Preview publisher failed") from self._error
            self.signal.transports = [
                self._redis_transport(),
                messages.ZMQSignalTransport(
                    address=self._connect_address or self._address, encoder="adzmq-array-1.0"
                ),
            ]
            self._subscription = self.signal.subscribe(self._on_preview, run=False)

    def _redis_transport(self) -> messages.RedisSignalTransport:
        return messages.RedisSignalTransport.from_endpoint_info(
            MessageEndpoints.device_preview(
                self.signal.root.name, self.signal.dotted_name or self.signal.name
            )
        )

    def _on_preview(self, *, value: messages.DevicePreviewMessage, **_kwargs) -> None:
        if self._error is not None:
            return
        jpeg = bool(self._jpeg_enabled())
        data = np.array(value.data, copy=True)
        with self._condition:
            if self._closed:
                return
            self._pending = (data, jpeg, self._frame)
            self._frame += 1
            self._condition.notify()

    @staticmethod
    def _encode(data: np.ndarray, jpeg: bool, frame: int) -> list[bytes]:
        header = {
            "htype": "array-1.0",
            "shape": list(data.shape),
            "type": data.dtype.name,
            "frame": frame,
            "encoding": "jpeg" if jpeg else "",
            "endianness": (
                "little"
                if data.dtype.byteorder == "<" or (data.dtype.byteorder == "=" and np.little_endian)
                else "big"
            ),
        }
        if jpeg:
            if data.ndim != 2:
                raise ValueError("SimCamera JPEG previews require a 2D grayscale array")
            if data.dtype != np.uint8:
                finite = np.isfinite(data)
                low = float(data[finite].min()) if finite.any() else 0.0
                high = float(data[finite].max()) if finite.any() else 0.0
                header.update(source_dtype=data.dtype.name, display_range=[low, high])
                if high > low:
                    scaled = (data.astype(np.float64) - low) * (255.0 / (high - low))
                    data = (
                        np.nan_to_num(scaled, nan=0, posinf=255, neginf=0)
                        .clip(0, 255)
                        .astype(np.uint8)
                    )
                else:
                    data = np.zeros(data.shape, dtype=np.uint8)
            header["type"] = "uint8"
            output = io.BytesIO()
            Image.fromarray(data).save(output, format="JPEG", quality=90)
            payload = output.getvalue()
        else:
            payload = data.tobytes(order="C")
        return [json.dumps(header).encode(), payload]

    def _run(self) -> None:
        try:
            with zmq.Context() as context:
                with context.socket(zmq.PUB) as socket:
                    socket.setsockopt(zmq.LINGER, 0)
                    socket.setsockopt(zmq.SNDHWM, 2)
                    socket.bind(self._bind_address)
                    self._address = socket.getsockopt(zmq.LAST_ENDPOINT).decode()
                    self._ready.set()
                    while True:
                        with self._condition:
                            self._condition.wait_for(
                                lambda: self._pending is not None or self._stop.is_set()
                            )
                            if self._stop.is_set():
                                return
                            pending, self._pending = self._pending, None
                        parts = self._encode(*pending)
                        if not self._stop.is_set():
                            try:
                                socket.send_multipart(parts, flags=zmq.NOBLOCK, copy=False)
                            except zmq.Again:
                                pass  # Preview delivery is best effort.
                        del pending, parts  # Do not retain the last large image while idle.
        except Exception as exc:  # pylint: disable=broad-exception-caught
            self._error = exc
            bec_logger.logger.error(f"SimCamera preview publisher failed: {exc}")
        finally:
            self._ready.set()

    def destroy(self) -> None:
        """Disconnect the preview callback, join the publisher, and release buffers."""
        with self._lifecycle_lock:
            if self._subscription is not None:
                self.signal.unsubscribe(self._subscription)
                self._subscription = None
            with self._condition:
                self._closed = True
                self._stop.set()
                self._pending = None
                self._condition.notify_all()
            if self._thread is not None:
                self._thread.join()
