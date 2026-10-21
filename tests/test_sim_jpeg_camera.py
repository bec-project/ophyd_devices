"""Tests for the simulated JPEG camera."""

import io
import time

import numpy as np
import pytest
from PIL import Image

from ophyd_devices.sim.sim_jpeg_camera import DiffractionFrameSource, SimJpegCamera, encode_jpeg


@pytest.fixture
def jpeg_cam():
    cam = SimJpegCamera(name="jpeg_cam")
    yield cam
    cam.destroy()


def _decode(data: np.ndarray) -> np.ndarray:
    return np.asarray(Image.open(io.BytesIO(data.tobytes())))


@pytest.mark.parametrize("encoding, channels", [("jpeg_gray", 1), ("jpeg_rgb", 3)])
def test_jpeg_frame_decodes_to_requested_shape(jpeg_cam, encoding, channels):
    jpeg_cam.configure_stream(width=320, height=200, encoding=encoding, quality=80)
    data, metadata = jpeg_cam.make_frame()
    assert data.dtype == np.uint8 and data.ndim == 1
    assert metadata["encoding"] == "jpeg"
    assert metadata["shape"] == [200, 320]
    assert metadata["channels"] == channels
    image = _decode(data)
    assert image.shape[:2] == (200, 320)
    assert (image.ndim == 3) == (channels == 3)


def test_raw_frame_is_uint16_array(jpeg_cam):
    jpeg_cam.configure_stream(width=64, height=48, encoding="raw")
    data, metadata = jpeg_cam.make_frame()
    assert data.shape == (48, 64) and data.dtype == np.uint16
    assert metadata["encoding"] == "raw"
    assert metadata["raw_nbytes"] == data.nbytes


def test_configure_stream_clips_and_validates(jpeg_cam):
    settings = jpeg_cam.configure_stream(width=100000, height=1, quality=500, frame_rate=0)
    assert settings["width"] == 8192 and settings["height"] == 16
    assert settings["quality"] == 100 and settings["frame_rate"] == pytest.approx(0.1)
    with pytest.raises(ValueError):
        jpeg_cam.configure_stream(encoding="png")


def test_fixed_max_counts_is_reported(jpeg_cam):
    jpeg_cam.configure_stream(width=64, height=64, max_counts=1000)
    _, metadata = jpeg_cam.make_frame()
    assert metadata["scale_max_counts"] == 1000


def test_frames_move_between_calls():
    source = DiffractionFrameSource()
    first = source.next_frame((64, 64)).copy()
    second = source.next_frame((64, 64))
    assert not np.array_equal(first, second)


def test_encode_jpeg_roundtrip():
    image = np.tile(np.arange(256, dtype=np.uint8), (16, 1))
    decoded = np.asarray(Image.open(io.BytesIO(encode_jpeg(image, 95))))
    assert decoded.shape == image.shape
    assert np.abs(decoded.astype(int) - image).max() < 10


def test_live_stream_publishes_and_stop_halts_it(jpeg_cam):
    received = []
    jpeg_cam.preview.subscribe(lambda **kwargs: received.append(kwargs["value"]), run=False)
    jpeg_cam.configure_stream(width=32, height=32, frame_rate=50)
    jpeg_cam.on_connected()
    jpeg_cam.start_live()
    deadline = time.time() + 5
    while len(received) < 3 and time.time() < deadline:
        time.sleep(0.02)
    assert len(received) >= 3
    jpeg_cam.stop()
    assert jpeg_cam.live.get() is False
    time.sleep(0.1)
    count = len(received)
    time.sleep(0.2)
    assert len(received) == count


def test_destroy_joins_stream_thread(jpeg_cam):
    jpeg_cam.on_connected()
    thread = jpeg_cam._thread
    assert thread.is_alive()
    jpeg_cam.destroy()
    assert not thread.is_alive()


def test_frames_report_sensor_shape(jpeg_cam):
    jpeg_cam.configure_stream(width=64, height=48, encoding="raw")
    _, metadata = jpeg_cam.make_frame()
    assert metadata["sensor_shape"] == [4096, 4096]
    cam = SimJpegCamera(name="small_cam", sensor_shape=(1000, 800))
    try:
        assert cam.make_frame()[1]["sensor_shape"] == [1000, 800]
    finally:
        cam.destroy()


@pytest.mark.parametrize("shape", [(128, 128), (256, 512), (400, 300)])
def test_pattern_stays_put_in_sensor_coordinates(shape):
    """The beam stop sits at the same sensor position for any preview size."""
    sensor = (4096, 4096)
    frame = DiffractionFrameSource().next_frame(shape, sensor)
    h, w = shape
    # sample around the beam stop centre at (0.52, 0.48) of the sensor
    row, col = int(0.52 * h), int(0.48 * w)
    assert frame[row, col] < 10
    assert frame[int(0.2 * h), int(0.2 * w)] > 0
