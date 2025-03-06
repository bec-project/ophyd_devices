""" This module contains tests for the simulation devices in ophyd_devices """

# pylint: disable: all
import os
import threading
import time
from types import SimpleNamespace
from unittest import mock

import h5py
import numpy as np
import pytest
from bec_lib import messages
from bec_lib.devicemanager import ScanInfo
from bec_lib.endpoints import MessageEndpoints
from bec_lib.file_utils import compile_file_components
from bec_server.device_server.tests.utils import DMMock
from ophyd import Device, Signal
from ophyd.status import wait as status_wait

from ophyd_devices.interfaces.protocols.bec_protocols import (
    BECDeviceProtocol,
    BECFlyerProtocol,
    BECPositionerProtocol,
    BECSignalProtocol,
)
from ophyd_devices.sim.sim_camera import SimCamera
from ophyd_devices.sim.sim_flyer import SimFlyer
from ophyd_devices.sim.sim_frameworks.h5_image_replay_proxy import H5ImageReplayProxy
from ophyd_devices.sim.sim_frameworks.slit_proxy import SlitProxy
from ophyd_devices.sim.sim_frameworks.stage_camera_proxy import StageCameraProxy
from ophyd_devices.sim.sim_monitor import SimMonitor, SimMonitorAsync
from ophyd_devices.sim.sim_positioner import SimLinearTrajectoryPositioner, SimPositioner
from ophyd_devices.sim.sim_signals import ReadOnlySignal
from ophyd_devices.sim.sim_utils import H5Writer, LinearTrajectory
from ophyd_devices.sim.sim_waveform import SimWaveform
from ophyd_devices.tests.utils import get_mock_scan_info
from ophyd_devices.utils.bec_device_base import BECDevice, BECDeviceBase


@pytest.fixture(scope="function")
def waveform(name="waveform"):
    """Fixture for SimWaveform."""
    dm = DMMock()
    wave = SimWaveform(name=name, device_manager=dm)
    yield wave


@pytest.fixture(scope="function")
def signal(name="signal"):
    """Fixture for Signal."""
    sig = ReadOnlySignal(name=name, value=0)
    yield sig


@pytest.fixture(scope="function")
def monitor(name="monitor"):
    """Fixture for SimMonitor."""
    dm = DMMock()
    mon = SimMonitor(name=name, device_manager=dm)
    yield mon


@pytest.fixture(scope="function")
def camera(name="camera"):
    """Fixture for SimCamera."""
    dm = DMMock()
    cam = SimCamera(name=name, device_manager=dm, scan_info=ScanInfo)
    cam.filewriter = mock.MagicMock()
    cam.filewriter.compile_full_filename.return_value = ""
    yield cam


@pytest.fixture(scope="function")
def positioner(name="positioner"):
    """Fixture for SimPositioner."""
    dm = DMMock()
    pos = SimPositioner(name=name, device_manager=dm)
    yield pos


@pytest.fixture(scope="function")
def linear_traj_positioner(name="linear_traj_positioner"):
    """Fixture for SimLinearTrajectoryPositioner."""
    dm = DMMock()
    pos = SimLinearTrajectoryPositioner(name=name, device_manager=dm)
    yield pos


@pytest.fixture(scope="function")
def async_monitor(name="async_monitor"):
    """Fixture for SimMonitorAsync."""
    dm = DMMock()
    mon = SimMonitorAsync(name=name, device_manager=dm)
    yield mon


@pytest.fixture(scope="function")
def h5proxy_fixture(camera: SimCamera, name="h5proxy"):
    """Fixture for SimCamera."""
    dm = camera.device_manager
    proxy = H5ImageReplayProxy(name=name, device_manager=dm)
    yield proxy, camera


@pytest.fixture(scope="function")
def slitproxy_fixture(camera, name="slit_proxy"):
    """Fixture for SimCamera."""
    dm = camera.device_manager
    proxy = SlitProxy(name=name, device_manager=dm)
    samx = SimPositioner(name="samx", device_manager=dm)
    yield proxy, camera, samx


@pytest.fixture(scope="function")
def stage_camera_proxy_fixture(camera, name="stage_camera_proxy"):
    """Fixture for SimCamera."""
    dm = camera.device_manager
    proxy = StageCameraProxy(name=name, device_manager=dm)
    samx = SimPositioner(name="samx", limits=[-50, 50], device_manager=dm)
    samy = SimPositioner(name="samy", limits=[-50, 50], device_manager=dm)
    for device in (camera, proxy, samx, samy):
        device_mock = mock.MagicMock()
        device_mock.obj = device
        device_mock.enabled = True
        dm.devices[device.name] = device_mock
    proxy._update_device_config(
        {camera.name: {"signal_name": "image", "ref_motors": [samx.name, samy.name]}}
    )
    camera._registered_proxies.update({proxy.name: camera.image.name})
    proxy.enabled = True
    yield proxy, camera, samx, samy


@pytest.fixture(scope="function")
def flyer(name="flyer"):
    """Fixture for SimFlyer."""
    dm = DMMock()
    fly = SimFlyer(name=name, device_manager=dm)
    yield fly


def test_camera_with_sim_init():
    """Test to see if the sim init parameters are passed to the device"""
    dm = DMMock()
    sim = SimCamera(name="sim", device_manager=dm)
    assert sim.sim._model.value == "gaussian"
    model = "constant"
    params = {
        "amplitude": 300,
        "noise": "uniform",
        "noise_multiplier": 1,
        "hot_pixel_coords": [[0, 0], [50, 50]],
        "hot_pixel_types": ["fluctuating", "constant"],
        "hot_pixel_values": [2.0, 2.0],
    }
    sim = SimCamera(name="sim", device_manager=dm, sim_init={"model": model, "params": params})
    assert sim.sim._model.value == model
    assert sim.sim.params == params


def test_monitor_with_sim_init():
    """Test to see if the sim init parameters are passed to the device"""
    dm = DMMock()
    sim = SimMonitor(name="sim", device_manager=dm)
    assert sim.sim._model._name == "constant"
    model = "GaussianModel"
    params = {
        "amplitude": 500,
        "center": 5,
        "sigma": 4,
        "noise": "uniform",
        "noise_multiplier": 1,
        "ref_motor": "samy",
    }
    sim = SimMonitor(name="sim", device_manager=dm, sim_init={"model": model, "params": params})
    assert sim.sim._model._name == model.strip("Model").lower()
    diff_keys = set(sim.sim.params.keys()) - set(params.keys())
    for k in params:
        assert sim.sim.params[k] == params[k]


def test_signal__init__(signal):
    """Test the BECProtocol class"""
    assert isinstance(signal, BECSignalProtocol)


def test_monitor__init__(monitor):
    """Test the __init__ method of SimMonitor."""
    assert isinstance(monitor, SimMonitor)
    assert isinstance(monitor, BECSignalProtocol)


def test_camera__init__(camera):
    """Test the __init__ method of SimMonitor."""
    assert isinstance(camera, SimCamera)
    assert isinstance(camera, BECDeviceProtocol)


def test_positioner__init__(positioner):
    """Test the __init__ method of SimPositioner."""
    assert isinstance(positioner, SimPositioner)
    assert isinstance(positioner, BECPositionerProtocol)


def test_flyer__init__(flyer):
    """Test the __init__ method of SimFlyer."""
    assert isinstance(flyer, SimFlyer)
    assert isinstance(flyer, BECFlyerProtocol)


def test_init_async_monitor(async_monitor):
    """Test the __init__ method of SimMonitorAsync."""
    assert isinstance(async_monitor, SimMonitorAsync)
    assert isinstance(async_monitor, BECDeviceProtocol)


@pytest.mark.parametrize("center", [-10, 0, 10])
def test_monitor_readback(monitor, center):
    """Test the readback method of SimMonitor."""
    motor_pos = 0
    monitor.device_manager.add_device(name="samx", value=motor_pos)
    for model_name in monitor.sim.get_models():
        monitor.sim.select_model(model_name)
        monitor.sim.params["noise_multipler"] = 10
        monitor.sim.params["ref_motor"] = "samx"
        if "c" in monitor.sim.params:
            monitor.sim.params["c"] = center
        elif "center" in monitor.sim.params:
            monitor.sim.params["center"] = center
        assert isinstance(monitor.read()[monitor.name]["value"], monitor.BIT_DEPTH)
        expected_value = monitor.sim._model.eval(monitor.sim._model_params, x=motor_pos)
        print(expected_value, monitor.read()[monitor.name]["value"])
        tolerance = (
            monitor.sim.params["noise_multipler"] + 1
        )  # due to ceiling in calculation, but maximum +1int
        assert np.isclose(
            monitor.read()[monitor.name]["value"],
            expected_value,
            atol=monitor.sim.params["noise_multipler"] + 1,
        )


@pytest.mark.parametrize("amplitude, noise_multiplier", [(0, 1), (100, 10), (1000, 50)])
def test_camera_readback(camera, amplitude, noise_multiplier):
    """Test the readback method of SimMonitor."""
    for model_name in camera.sim.get_models():
        camera.sim.select_model(model_name)
        camera.sim.params = {"noise_multiplier": noise_multiplier}
        camera.sim.params = {"amplitude": amplitude}
        camera.sim.params = {"noise": "poisson"}
        assert camera.image.get().shape == camera.SHAPE
        assert isinstance(camera.image.get()[0, 0], camera.BIT_DEPTH)
        camera.sim.params = {"noise": "uniform"}
        camera.sim.params = {"hot_pixel_coords": []}
        camera.sim.params = {"hot_pixel_values": []}
        camera.sim.params = {"hot_pixel_types": []}
        assert camera.image.get().shape == camera.SHAPE
        assert isinstance(camera.image.get()[0, 0], camera.BIT_DEPTH)
        assert (camera.image.get() <= (amplitude + noise_multiplier + 1)).all()


def test_positioner_move(positioner):
    """Test the move method of SimPositioner."""
    positioner.move(0).wait()
    assert np.isclose(
        positioner.read()[positioner.name]["value"], 0, atol=positioner.tolerance.get()
    )
    positioner.move(10).wait()
    assert np.isclose(
        positioner.read()[positioner.name]["value"], 10, atol=positioner.tolerance.get()
    )


@pytest.mark.timeout(30)
def test_positioner_motor_is_moving_signal(positioner):
    """Test that motor is moving is 0 and 1 while (not) moving"""

    recorded_data = []
    cid = None

    init_velocity = positioner.velocity.get()

    def motor_is_moving_cb(value: any, obj, **kwargs):
        data = obj.read()[f"{obj.name}_motor_is_moving"]["value"]
        recorded_data.append(data)

    try:
        cid = positioner.subscribe(motor_is_moving_cb, event_type="readback", run=False)

        status = positioner.move(-20)
        status.wait()

        positioner.velocity.set(10)

        status = positioner.move(20)
        status.wait()

        # Check that motor was moving and motor_is_moving switched to "1"
        assert any(recorded_data)

        # Check that motor is not moving and motor_is_moving switched back to "0"
        assert recorded_data[-1] == 0
    finally:
        # Restore initial velocity, remove subscription
        positioner.velocity.set(init_velocity)
        if cid is not None:
            positioner.unsubscribe(cid)


@pytest.mark.parametrize(
    "initial_position, final_position, max_velocity, acceleration",
    [(0, 100, 5, 20), (0, 1, 5, 20)],  # Trapezoidal profile  # Triangular profile
)
def test_linear_traj(initial_position, final_position, max_velocity, acceleration):
    """Test the LinearTrajectory class"""
    initial_time = time.time()
    trajectory = LinearTrajectory(
        initial_position, final_position, max_velocity, acceleration, initial_time
    )

    # Test acceleration phase
    t1 = initial_time + trajectory.time_accel / 2  # Halfway through acceleration phase
    pos1 = trajectory.position(t1)
    expected_pos1 = initial_position + 0.5 * acceleration * (trajectory.time_accel / 2) ** 2
    assert np.isclose(pos1, expected_pos1), f"Expected {expected_pos1}, got {pos1}"

    # Test constant velocity phase
    if trajectory.time_const_vel > 0:
        t2 = (
            initial_time + trajectory.time_accel + trajectory.time_const_vel / 2
        )  # Halfway through constant velocity phase
        pos2 = trajectory.position(t2)
        expected_pos2 = (
            initial_position
            + trajectory.distance_to_max_velocity
            + max_velocity * (t2 - initial_time - trajectory.time_accel)
        )
        assert np.isclose(pos2, expected_pos2), f"Expected {expected_pos2}, got {pos2}"

    # Test deceleration phase
    t3 = (
        initial_time + trajectory.total_time - trajectory.time_decel / 2
    )  # Halfway through deceleration phase
    pos3 = trajectory.position(t3)
    t_decel = t3 - (initial_time + trajectory.time_accel + trajectory.time_const_vel)
    expected_pos3 = final_position - 0.5 * acceleration * (trajectory.time_decel / 2) ** 2
    assert np.isclose(pos3, expected_pos3), f"Expected {expected_pos3}, got {pos3}"

    # Test end
    t4 = initial_time + trajectory.total_time + 0.1  # Slightly after end
    pos4 = trajectory.position(t4)
    assert pos4 == final_position
    assert trajectory.ended


def test_sim_linear_trajectory_positioner(linear_traj_positioner):
    vel = 5  # velocity 5 m.s^-1
    acc = 20  # acceleration 20 m.s^-2
    linear_traj_positioner.velocity.set(vel)
    linear_traj_positioner.acceleration.set(vel / acc)  # acctime 250 ms
    linear_traj_positioner.update_frequency = 100
    assert linear_traj_positioner.position == 0

    t0 = time.time()
    trajectory = LinearTrajectory(0, 50, vel, acc, t0)
    t2 = (
        t0 + trajectory.time_accel + trajectory.time_const_vel / 2
    )  # Halfway through constant velocity phase
    decel_distance = trajectory.position(t0 + trajectory.time_accel)
    expected_pos = trajectory.position(t2) + decel_distance

    linear_traj_positioner.move(50)
    # move is non-blocking, so sleep until it is time to stop:
    time.sleep(t2 - t0)
    linear_traj_positioner.stop()

    # ensure position is ok
    assert pytest.approx(linear_traj_positioner.position - expected_pos, abs=1e-1) == 0


@pytest.mark.parametrize("proxy_active", [True, False])
def test_sim_camera_proxies(camera, proxy_active):
    """Test mocking compute_method with framework class"""
    camera.device_manager.add_device("test_proxy")
    if proxy_active:
        camera._registered_proxies["test_proxy"] = camera.image.name
    else:
        camera._registered_proxies = {}
    proxy = camera.device_manager.devices["test_proxy"]
    mock_method = mock.MagicMock()
    mock_obj = proxy.obj
    mock_obj.lookup = mock.MagicMock()
    mock_obj.lookup.return_value = {camera.name: {"method": mock_method, "args": 1, "kwargs": 1}}
    camera.image.read()
    if proxy_active:
        assert len(mock_obj.lookup.mock_calls) > 0
    elif not proxy_active:
        assert len(mock_obj.lookup.mock_calls) == 0


def test_BECDeviceBase():
    # Test the BECDeviceBase class
    bec_device_base = BECDeviceBase(name="test")
    assert isinstance(bec_device_base, BECDevice)
    assert bec_device_base.connected is True
    signal = Signal(name="signal")
    assert isinstance(signal, BECDevice)
    device = Device(name="device")
    assert isinstance(device, BECDevice)


def test_h5proxy(h5proxy_fixture):
    """Test h5 camera proxy read from h5 file"""
    msg = messages.ScanStatusMessage(
        scan_id="test",
        num_points=10,
        scan_number=1,
        status="open",
        info={},
        scan_parameters={"frames_per_trigger": 1, "exp_time": 1},
    )
    h5proxy, camera = h5proxy_fixture
    mock_proxy = mock.MagicMock()
    camera.device_manager.devices.update({h5proxy.name: mock_proxy})
    mock_proxy.enabled = True
    mock_proxy.obj = h5proxy
    fname = os.path.expanduser("tests/test_data/h5_test_file.h5")
    h5entry = "entry/data/data"
    with h5py.File(fname, "r") as f:
        data = f[h5entry][...]
    # pylint: disable=protected-access
    h5proxy._update_device_config(
        {camera.name: {"signal_name": "image", "file_source": fname, "h5_entry": h5entry}}
    )
    camera._registered_proxies.update({h5proxy.name: camera.image.name})
    camera.sim.params = {"noise": "none", "noise_multiplier": 0}
    # pylint: disable=no-member
    camera.image_shape.set(data.shape[1:])
    with (
        mock.patch.object(camera.file_utils, "get_full_path", return_value="/tmp/path"),
        mock.patch.object(camera.scan_info, "msg", return_value=msg),
    ):
        camera.stage()
        img = camera.image.get()
        assert (img == data[0, ...]).all()
        camera.unstage()


def test_slitproxy(slitproxy_fixture):
    """Test slit proxy to compute readback from readback of positioner samx"""
    proxy, camera, samx = slitproxy_fixture
    for dev_name, dev in proxy.device_manager.devices.items():
        camera.device_manager.devices.update({dev_name: mock.MagicMock()})
        camera.device_manager.devices.get(dev_name).obj = dev
        camera.device_manager.devices.get(dev_name).enabled = True
    px_size = 0.5
    slitwidth = 2
    proxy._update_device_config(
        {
            camera.name: {
                "signal_name": "image",
                "center_offset": [0, 0],
                "covariance": [[1000, 500], [200, 1000]],
                "pixel_size": px_size,
                "ref_motors": [samx.name],
                "slit_width": [slitwidth],
                "motor_dir": [0],
            }
        }
    )
    camera._registered_proxies.update({proxy.name: camera.image.name})
    mock_proxy = mock.MagicMock()
    mock_samx = mock.MagicMock()
    mock_camera = mock.MagicMock()
    camera.device_manager.devices.update(
        {proxy.name: mock_proxy, samx.name: mock_samx, camera.name: mock_camera}
    )

    mock_proxy.enabled = True
    mock_samx.enabled = True
    mock_camera.enabled = True
    mock_camera.obj = camera
    mock_samx.obj = samx
    mock_proxy.obj = proxy
    camera.sim.params = {"noise": "none", "noise_multiplier": 0, "hot_pixel_values": [0, 0, 0]}
    samx.delay = 0
    samx_pos = 0
    samx.move(samx_pos)
    proxy._gaussian_blur_sigma = 0
    img = camera.image.get()
    edges = (
        int(img.shape[0] // 2 - samx_pos / px_size - slitwidth / (2 * px_size)),
        int(img.shape[0] // 2 + samx_pos / px_size + slitwidth / (2 * px_size)),
    )
    assert (img[:, : edges[0]] == 0).all()
    assert (img[:, edges[1] :] == 0).all()
    samx_pos = 13.3
    samx.move(samx_pos)
    img = camera.image.get()
    edges = (
        int(img.shape[0] // 2 + samx_pos / px_size - slitwidth / (2 * px_size)),
        int(img.shape[0] // 2 + samx_pos / px_size + slitwidth / (2 * px_size)),
    )
    assert (img[:, : edges[0]] == 0).all()
    assert (img[:, edges[1] :] == 0).all()


def test_proxy_config_and_props_stay_in_sync(h5proxy_fixture: tuple[H5ImageReplayProxy, SimCamera]):
    h5proxy, cam = h5proxy_fixture
    h5proxy._update_device_config(
        {
            cam.name: {
                "signal_name": "image",
                "file_source": "test first thing",
                "h5_entry": "/entry/data/data",
            }
        }
    )
    h5proxy.file_source = "test different thing"
    assert h5proxy.config[cam.name]["file_source"] == h5proxy.file_source
    h5proxy.h5_entry = "/entry/data/data_000001"
    assert h5proxy.config[cam.name]["h5_entry"] == h5proxy.h5_entry


def test_stage_camera_proxy_image_moves_with_samx_and_samy(
    stage_camera_proxy_fixture: tuple[StageCameraProxy, SimCamera, SimPositioner, SimPositioner]
):
    """Test camera stage proxy to compute readback from readback of positioner samx and samy"""
    proxy, camera, samx, samy = stage_camera_proxy_fixture

    proxy.stage()
    image_at_0: np.ndarray = camera.image.get()
    image_at_0_again: np.ndarray = camera.image.get()
    assert np.array_equal(image_at_0, image_at_0_again)
    samx.move(-10).wait()
    image_at_x_10 = camera.image.get()
    assert not np.array_equal(image_at_0, image_at_x_10)
    samy.move(-10).wait()
    image_at_x_10_y_10 = camera.image.get()
    assert not np.array_equal(image_at_x_10, image_at_x_10_y_10)


def test_stage_camera_proxy_image_shape(
    stage_camera_proxy_fixture: tuple[StageCameraProxy, SimCamera, SimPositioner, SimPositioner]
):
    """Make sure that the produced image has the same shape as the detector being proxied"""
    proxy, camera, samx, samy = stage_camera_proxy_fixture
    test_shape = (102, 77)
    camera.image_shape.set(test_shape).wait()
    proxy.stage()
    image: np.ndarray = camera.image.get()
    assert image.shape == (*reversed(test_shape), 3)


def test_cam_stage_h5writer(camera):
    """Test the H5Writer class"""
    file_dir = None
    suffix = None
    msg = messages.ScanStatusMessage(
        scan_id="test",
        num_points=10,
        scan_number=1,
        status="open",
        info={},
        scan_parameters={
            "frames_per_trigger": 1,
            "exp_time": 1,
            "system_config": {"file_directory": file_dir, "file_suffix": suffix},
            "file_components": compile_file_components(
                base_path="./test", scan_nr=1, file_directory=file_dir, user_suffix=suffix
            ),
        },
    )
    with (
        mock.patch.object(camera, "h5_writer") as mock_h5_writer,
        mock.patch.object(camera, "_run_subs") as mock_run_subs,
        mock.patch.object(camera.scan_info, "msg", return_value=msg),
        mock.patch.object(
            camera.file_utils, "get_full_path", return_value="./data/test_file_camera.h5"
        ),
    ):
        # camera.scan_info.msg.num_points = 10
        # camera.scan_info.msg.scan_parameters["frames_per_trigger"] = 1
        # camera.scan_info.msg.scan_parameters["exp_time"] = 1
        camera.stage()
        assert mock_h5_writer.on_stage.call_count == 0
        camera.unstage()
        camera.write_to_disk.put(True)
        camera.stage()
        calls = [mock.call(file_path="./data/test_file_camera.h5", h5_entry="/entry/data/data")]
        assert mock_h5_writer.on_stage.mock_calls == calls
        # mock_h5_writer.prepare


def test_cam_complete(camera):
    """Test the complete method of SimCamera."""
    finished_event = threading.Event()

    def finished_cb():
        finished_event.set()

    with mock.patch.object(camera, "h5_writer") as mock_h5_writer:
        status = camera.complete()
        status_wait(status)
        assert status.done is True
        assert status.success is True
        assert mock_h5_writer.on_complete.call_count == 0
        camera.write_to_disk.put(True)
        status = camera.complete()
        status.add_callback(finished_cb)
        finished_event.wait()
        assert mock_h5_writer.on_complete.call_count == 1


def test_cam_trigger(camera):
    """Test the trigger method of SimCamera."""
    with mock.patch.object(camera, "h5_writer") as mock_h5_writer:
        data = []
        status = camera.trigger()
        status_wait(status)
        assert status.done is True
        assert status.success is True
        assert mock_h5_writer.receive_data.call_count == 0
        camera.write_to_disk.put(True)
        status = camera.trigger()
        status_wait(status)
        assert mock_h5_writer.receive_data.call_count == 1
        status = camera.trigger()
        status_wait(status)
        assert mock_h5_writer.receive_data.call_count == 2


def test_h5writer(tmp_path):
    """Test the H5Writer class"""

    h5_writer = H5Writer()
    h5_writer.data_container = [np.array([0, 1, 2, 3, 4])]
    fp = tmp_path / "test.h5"
    h5_writer.on_stage(file_path=fp, h5_entry="entry/data/data")
    assert h5_writer.data_container == []
    assert h5_writer.file_path == fp
    assert h5_writer.h5_entry == "entry/data/data"

    data = np.array([0, 1])
    h5_writer.receive_data(data)
    assert h5_writer.data_container == [data]
    new_data = np.array([3, 4])
    h5_writer.receive_data(new_data)
    assert h5_writer.data_container == [data, new_data]
    h5_writer.receive_data(new_data)
    assert h5_writer.data_container == []
    h5_writer.receive_data(new_data)
    h5_writer.on_complete()
    assert h5_writer.data_container == []


def test_async_monitor_stage(async_monitor):
    """Test the stage method of SimMonitorAsync."""
    async_monitor.stage()
    assert async_monitor.data_buffer["value"] == []
    assert async_monitor.data_buffer["timestamp"] == []


def test_async_monitor_prep_random_interval(async_monitor):
    """Test the stage method of SimMonitorAsync."""
    async_monitor.prep_random_interval()
    assert async_monitor._counter == 0
    assert async_monitor.current_trigger.get() == 0
    assert 0 < async_monitor._random_send_interval < 10


def test_async_monitor_complete(async_monitor):
    """Test the on_complete method of SimMonitorAsync."""
    with (
        mock.patch.object(async_monitor, "_send_data_to_bec") as mock_send,
        mock.patch.object(async_monitor, "prep_random_interval") as mock_prep,
    ):
        status = async_monitor.complete()
        status_wait(status)
        assert status.done is True
        assert status.success is True
        assert mock_send.call_count == 0
        async_monitor.data_buffer["value"].append(0)
        status = async_monitor.complete()
        status_wait(status)
        assert status.done is True
        assert status.success is True
        assert mock_send.call_count == 1


def test_async_mon_on_trigger(async_monitor):
    """Test the on_trigger method of SimMonitorAsync."""
    with (mock.patch.object(async_monitor, "_send_data_to_bec") as mock_send,):
        async_monitor.on_stage()
        upper_limit = async_monitor._random_send_interval
        for ii in range(1, upper_limit + 1):
            status = async_monitor.on_trigger()
            status_wait(status)
            assert async_monitor.current_trigger.get() == ii
        assert mock_send.call_count == 1


def test_async_mon_send_data_to_bec(async_monitor):
    """Test the _send_data_to_bec method of SimMonitorAsync."""
    async_monitor.scan_info = get_mock_scan_info(device=async_monitor)
    async_monitor.data_buffer.update({"value": [0, 5], "timestamp": [0, 0]})
    with mock.patch.object(async_monitor.connector, "xadd") as mock_xadd:
        async_monitor._send_data_to_bec()
        dev_msg = messages.DeviceMessage(
            signals={async_monitor.readback.name: async_monitor.data_buffer},
            metadata={"async_update": {"type": "add", "max_shape": [None]}},
        )

        call = [
            mock.call(
                MessageEndpoints.device_async_readback(
                    scan_id=async_monitor.scan_info.msg.scan_id, device=async_monitor.name
                ),
                {"data": dev_msg},
                expire=async_monitor._stream_ttl,
            )
        ]
        assert mock_xadd.mock_calls == call
        assert async_monitor.data_buffer["value"] == []


def test_positioner_updated_timestamp(positioner):
    """Test the updated_timestamp method of SimPositioner."""
    positioner.sim.sim_state[positioner.name]["value"] = 1
    readback = positioner.read()[positioner.name]
    timestamp = readback["timestamp"]
    assert readback["value"] == 1
    positioner.sim.sim_state[positioner.name]["value"] = 5
    readback = positioner.read()[positioner.name]
    assert readback["value"] == 5
    assert readback["timestamp"] > timestamp


def test_waveform(waveform):
    """Test the SimWaveform class"""
    waveform.sim.select_model("GaussianModel")
    waveform.sim.params = {"amplitude": 500, "center": 500, "sigma": 10}
    data = waveform.waveform.get()
    assert isinstance(data, np.ndarray)
    assert data.shape == waveform.SHAPE
    assert np.isclose(np.argmax(data), 500, atol=5)
    waveform.waveform_shape.put(50)
    data = waveform.waveform.get()
    for model in waveform.sim.get_all_sim_models():
        waveform.sim.select_model(model)
        waveform.waveform.get()
    # Now also test the async readback
    mock_connector = waveform.connector = mock.MagicMock()
    mock_run_subs = waveform._run_subs = mock.MagicMock()
    waveform.scan_info = get_mock_scan_info(device=waveform)
    waveform.scan_info.msg.scan_id = "test"
    status = waveform.trigger()
    timer = 0
    while not status.done:
        time.sleep(0.1)
        timer += 0.1
        if timer > 5:
            raise TimeoutError("Trigger did not complete")
    assert status.done is True
    assert mock_connector.xadd.call_count == 1
    assert mock_run_subs.call_count == 1
