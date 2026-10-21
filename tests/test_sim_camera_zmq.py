"""SimCamera ADZMQ previews use mocked sockets and no BEC services or hardware."""

import io
import json
from threading import Event
from unittest import mock

import numpy as np
import pytest
from bec_lib import messages
from bec_lib.endpoints import MessageEndpoints
from ophyd import Device, Kind
from PIL import Image

from ophyd_devices.sim.sim_camera import SimCamera
from ophyd_devices.utils.adzmq_preview import ADZMQPreviewPublisher


def _decode_preview(parts: list[bytes]) -> np.ndarray:
    """Check publisher payloads without depending on an unreleased BEC receiver."""
    header, payload = json.loads(parts[0]), parts[1]
    assert header["htype"] == "array-1.0"
    if header["encoding"] == "jpeg":
        with Image.open(io.BytesIO(payload)) as image:
            assert image.format == "JPEG"
            data = np.array(image)
    else:
        assert header["encoding"] == ""
        byte_order = "<" if header["endianness"] == "little" else ">"
        dtype = np.dtype(header["type"]).newbyteorder(byte_order)
        data = np.frombuffer(payload, dtype=dtype).reshape(header["shape"])
    assert data.shape == tuple(header["shape"])
    return data


@pytest.fixture
def publisher():
    """Capture completed multipart sends from the publishing worker."""
    context, socket = mock.MagicMock(), mock.MagicMock()
    context.__enter__.return_value = context
    context.socket.return_value = socket
    socket.__enter__.return_value = socket
    socket.getsockopt.return_value = b"tcp://127.0.0.1:54321"
    sent = Event()
    packets = []

    def send(parts, **_):
        packets.append(parts)
        sent.set()

    socket.send_multipart.side_effect = send
    with mock.patch("ophyd_devices.utils.adzmq_preview.zmq.Context", return_value=context):
        yield context, socket, packets, sent


@pytest.fixture
def camera():
    """Destroy the camera and all worker resources after each test."""
    cam = SimCamera(name="camera")
    try:
        yield cam
    finally:
        cam.destroy()


def test_no_socket_during_construction_and_compression_config(camera, publisher):
    context, _, _, _ = publisher
    assert not context.socket.called
    assert type(camera.preview).__name__ == "PreviewSignal"
    assert camera.preview.signal_info.transports is None
    assert camera.preview_jpeg_compression.kind == Kind.config
    assert camera.preview_jpeg_compression.get() is False
    assert "camera_preview_jpeg_compression" in camera.read_configuration()


def test_default_transport_and_raw_roundtrip(camera, publisher):
    _, socket, packets, sent = publisher
    camera.on_connected()
    socket.bind.assert_called_once_with("tcp://127.0.0.1:*")
    redis, zmq_transport = camera.preview.signal_info.transports
    assert redis == messages.RedisSignalTransport.from_endpoint_info(
        MessageEndpoints.device_preview("camera", "preview")
    )
    assert zmq_transport.address == "tcp://127.0.0.1:54321"
    assert zmq_transport.encoder == "adzmq-array-1.0"
    assert zmq_transport.topic is None
    assert zmq_transport.socket_type == "sub"
    raw = np.arange(24, dtype=np.uint16).reshape(4, 6)
    camera.preview.put(raw)
    assert sent.wait(3)
    decoded = _decode_preview(packets[-1])
    np.testing.assert_array_equal(decoded, raw)
    np.testing.assert_array_equal(camera.preview.get().data, raw)
    thread = camera._preview_publisher._thread
    camera.destroy()
    assert not thread.is_alive()


def test_remote_transport(publisher):
    camera = SimCamera(
        name="remote",
        preview_zmq_bind_address="tcp://*:5555",
        preview_zmq_connect_address="tcp://detector-host:5555",
    )
    try:
        camera.on_connected()
        assert camera.preview.signal_info.transports[-1].address == "tcp://detector-host:5555"
        publisher[1].bind.assert_called_once_with("tcp://*:5555")
    finally:
        camera.destroy()


def test_toggle_jpeg_preserves_redis_and_raw_dtype(camera, publisher):
    _, _, packets, sent = publisher
    original = np.arange(240, dtype=np.uint16).reshape(12, 20) * 200
    received = []
    camera.preview.subscribe(lambda value, **_: received.append(value), run=False)
    camera.on_connected()
    camera.preview_jpeg_compression.put(True)
    camera.preview.put(original)
    assert sent.wait(3)
    header = json.loads(packets[-1][0])
    assert header["encoding"] == "jpeg"
    assert header["source_dtype"] == "uint16"
    assert header["display_range"] == [0.0, float(original.max())]
    image = _decode_preview(packets[-1])
    assert image.shape == original.shape and image.dtype == np.uint8
    np.testing.assert_array_equal(received[-1].data, original)
    np.testing.assert_array_equal(camera.preview.get().data, original)
    sent.clear()
    camera.preview_jpeg_compression.put(False)
    camera.preview.put(original)
    assert sent.wait(3)
    np.testing.assert_array_equal(_decode_preview(packets[-1]), original)


@pytest.mark.parametrize(
    "data",
    [
        np.full((3, 4), 7, dtype=np.uint16),
        np.full((3, 4), np.nan, dtype=np.float32),
        np.arange(-6, 6, dtype=np.int16).reshape(3, 4),
        np.arange(12, dtype=np.uint8).reshape(3, 4),
    ],
)
def test_jpeg_supported_simulation_dtypes(data):
    before = data.copy()
    parts = ADZMQPreviewPublisher._encode(data, True, 0)
    image = _decode_preview(parts)
    assert image.shape == data.shape and image.dtype == np.uint8
    np.testing.assert_array_equal(data, before)


@pytest.mark.parametrize(
    "data",
    [
        np.arange(12, dtype=">u2").reshape(3, 4),
        np.arange(-6, 6, dtype=np.int16).reshape(3, 4)[:, ::-1],
        np.arange(12, dtype=np.float32).reshape(3, 4),
    ],
)
def test_raw_preserves_dtype_byte_order_and_layout(data):
    decoded = _decode_preview(ADZMQPreviewPublisher._encode(data, False, 0))
    np.testing.assert_array_equal(decoded, data)
    assert decoded.dtype == data.dtype


def test_bind_failure_is_reported_and_worker_stops(camera, publisher):
    publisher[1].bind.side_effect = OSError("port unavailable")
    with pytest.raises(RuntimeError, match="publisher failed"):
        camera.on_connected()
    camera.destroy()
    assert not camera._preview_publisher._thread.is_alive()


def test_repeated_connection_does_not_start_another_publisher(camera, publisher):
    camera.on_connected()
    first = camera._preview_publisher._thread
    camera.on_connected()
    assert camera._preview_publisher._thread is first
    assert publisher[1].bind.call_count == 1


@pytest.mark.parametrize(
    "bind,connect",
    [
        ("tcp://*:5555", None),
        ("tcp://127.0.0.1:*", "tcp://host:5555"),
        ("tcp://127.0.0.1:5555", "tcp://*:5555"),
    ],
)
def test_invalid_advertised_addresses(bind, connect):
    with pytest.raises(ValueError):
        SimCamera(
            name="invalid", preview_zmq_bind_address=bind, preview_zmq_connect_address=connect
        )


def test_latest_snapshot_and_encoding_runs_off_producer_thread(camera, publisher):
    from threading import get_ident

    _, socket, packets, _ = publisher
    entered, release, completed = Event(), Event(), Event()
    producer_thread = get_ident()
    encode = camera._preview_publisher._encode
    calls = []

    def stalled_encode(*args):
        calls.append(get_ident())
        entered.set()
        assert release.wait(3)
        return encode(*args)

    def send(parts, **_):
        packets.append(parts)
        if len(packets) == 2:
            completed.set()

    socket.send_multipart.side_effect = send
    with mock.patch.object(camera._preview_publisher, "_encode", side_effect=stalled_encode):
        try:
            camera.on_connected()
            data = np.zeros((3, 4), dtype=np.uint16)
            camera.preview.put(data)
            assert entered.wait(3)
            data[:] = 99  # The queued frame must own a snapshot.
            for index in range(1, 6):
                camera.preview.put(np.full((3, 4), index, dtype=np.uint16))
            release.set()
            assert completed.wait(3)
            np.testing.assert_array_equal(_decode_preview(packets[0]), np.zeros((3, 4)))
            np.testing.assert_array_equal(_decode_preview(packets[1]), np.full((3, 4), 5))
            assert all(thread != producer_thread for thread in calls)
        finally:
            release.set()
            camera.destroy()


def test_device_config_forwards_transport_addresses(publisher):
    from bec_server.device_server.devices.devicemanager import DeviceManagerDS

    config = {
        "name": "configured",
        "deviceClass": "SimCamera",
        "deviceConfig": {
            "preview_zmq_bind_address": "tcp://*:5555",
            "preview_zmq_connect_address": "tcp://camera-host:5555",
        },
    }
    with mock.patch.object(DeviceManagerDS, "_get_device_class", return_value=SimCamera):
        cam, remaining = DeviceManagerDS.construct_device_obj(config, None)
    try:
        assert remaining == {}
        cam.on_connected()
        assert cam.preview.signal_info.transports[-1].address == "tcp://camera-host:5555"
        publisher[1].bind.assert_called_once_with("tcp://*:5555")
    finally:
        cam.destroy()


def test_nested_camera_advertises_root_redis_endpoint(publisher):
    parent = Device(name="detector_root")
    cam = SimCamera(name="detector_root_camera", parent=parent)
    try:
        cam.on_connected()
        expected = messages.RedisSignalTransport.from_endpoint_info(
            MessageEndpoints.device_preview(cam.root.name, cam.preview.dotted_name)
        )
        assert cam.preview.signal_info.transports[0] == expected
    finally:
        cam.destroy()
        parent.destroy()


def test_startup_timeout_remains_an_error_on_retry(camera, publisher):
    binding, release = Event(), Event()
    worker = camera._preview_publisher

    def delayed_bind(_address):
        binding.set()
        assert release.wait(3)

    def timeout_after_worker_started(_timeout):
        assert binding.wait(3)
        return False

    publisher[1].bind.side_effect = delayed_bind
    try:
        with mock.patch.object(worker._ready, "wait", side_effect=timeout_after_worker_started):
            with pytest.raises(TimeoutError, match="did not bind"):
                camera.on_connected()
        release.set()
        worker._thread.join(3)
        assert not worker._thread.is_alive()
        assert camera.preview.transports is None
        with pytest.raises(RuntimeError, match="Preview publisher failed") as error:
            camera.on_connected()
        assert isinstance(error.value.__cause__, TimeoutError)
        assert publisher[1].bind.call_count == 1
    finally:
        release.set()
        camera.destroy()
