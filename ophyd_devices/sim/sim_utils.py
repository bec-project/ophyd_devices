import math
import os
import time
from pathlib import Path

import h5py
import hdf5plugin
import numpy as np


class H5Writer:
    """Utility class to write data from device to disk"""

    def __init__(self, file_path: str = None, h5_entry: str = None):
        self.file_path = file_path
        self.h5_entry = h5_entry
        self.h5_file = None
        self.file_handle = None
        self.data_container = []

    def create_dir(self):
        """Create directory if it does not exist"""
        file_path = str(Path(self.file_path).resolve())
        base_dir = os.path.dirname(file_path)
        if not os.path.exists(base_dir):
            os.makedirs(base_dir)

    def receive_data(self, data: any):
        """Store data to be written to h5 file"""
        self.data_container.append(data)
        if len(self.data_container) > 2:
            self.write_data()

    def on_stage(self, file_path: str, h5_entry: str):
        """Prepare to write data to h5 file"""
        self.data_container.clear()
        self.file_path = file_path
        self.h5_entry = h5_entry
        self.create_dir()
        # Create file and truncate if it exists
        with h5py.File(self.file_path, "w") as f:
            pass

    def on_complete(self):
        """Write data to h5 file"""
        if len(self.data_container) > 0:
            self.write_data()

    def on_unstage(self):
        """Close file handle"""

    def write_data(self):
        """Write data to h5 file. If the scan is started, the file will be truncated first"""
        with h5py.File(self.file_path, "a") as f:
            dataset = self.h5_entry
            value = self.data_container
            if isinstance(value, list):
                shape = (
                    value[0].shape if hasattr(value[0], "shape") else (len(value), len(value[0]))
                )
                shape = (None, *shape)
            if dataset not in f:
                f.create_dataset(
                    dataset, data=np.array(value), maxshape=shape, chunks=True, **hdf5plugin.LZ4()
                )
            else:
                f[dataset].resize((f[dataset].shape[0] + len(value)), axis=0)
                f[dataset][-len(value) :] = np.array(value)
            self.data_container.clear()


class LinearTrajectory:
    def __init__(
        self, initial_position, final_position, max_velocity, acceleration, initial_time=None
    ):
        self.initial_position = initial_position
        self.final_position = final_position
        self.max_velocity = abs(max_velocity)
        self.acceleration = abs(acceleration)
        self.initial_time = initial_time if initial_time is not None else time.time()
        self._velocity_profile = []
        self.ended = False

        self.distance = self.final_position - self.initial_position
        self.direction = np.sign(self.distance)
        self.distance = abs(self.distance)

        # Calculate time to reach max velocity and the distance covered during this time
        self.time_to_max_velocity = self.max_velocity / self.acceleration
        self.distance_to_max_velocity = 0.5 * self.acceleration * self.time_to_max_velocity**2

        if self.distance < 2 * self.distance_to_max_velocity:
            # If the distance is too short to reach max velocity (triangular profile)
            self.time_accel = np.sqrt(self.distance / self.acceleration)
            self.time_decel = self.time_accel
            self.time_const_vel = 0
            self.total_time = 2 * self.time_accel
        else:
            # If the distance allows reaching max velocity (trapezoidal profile)
            self.time_accel = self.time_to_max_velocity
            self.time_decel = self.time_to_max_velocity
            self.time_const_vel = (
                self.distance - 2 * self.distance_to_max_velocity
            ) / self.max_velocity
            self.total_time = self.time_accel + self.time_const_vel + self.time_decel

    def _get_velocity_at_time(self, dt):
        if dt <= self.time_accel:
            # Acceleration phase
            return self.direction * self.acceleration * dt
        elif dt <= self.time_accel + self.time_const_vel:
            # Constant velocity phase
            return self.direction * self.max_velocity
        elif dt <= self.total_time:
            # Deceleration phase
            return self.direction * self.acceleration * (self.total_time - dt)
        else:
            return 0

    def _get_pos_at_time(self, dt):
        if dt <= self.time_accel:
            # Acceleration phase
            return self.initial_position + self.direction * 0.5 * self.acceleration * dt**2
        elif dt <= self.time_accel + self.time_const_vel:
            # Constant velocity phase
            return self.initial_position + self.direction * (
                self.distance_to_max_velocity + self.max_velocity * (dt - self.time_accel)
            )
        elif dt <= self.total_time:
            # Deceleration phase
            return (
                self.final_position
                - self.direction * 0.5 * self.acceleration * (self.total_time - dt) ** 2
            )
        else:
            return self.final_position

    def position(self, t=None):
        if t is None:
            t = time.time()
        dt = t - self.initial_time

        if dt < 0:
            raise ValueError("Time cannot be before initial time.")

        current_position = self._get_pos_at_time(dt)
        current_velocity = self._get_velocity_at_time(dt)

        self._velocity_profile.append([t, current_velocity])

        if dt > self.total_time:
            self.ended = True

        return current_position

    @property
    def velocity_profile(self):
        return np.array(self._velocity_profile)

    def plot_trajectory(self):
        # visual check of LinearTrajectory class
        try:
            import matplotlib.pyplot as plt
        except ImportError:
            raise ImportError("plot_trajectory requires matplotlib to be installed")

        initial_time = time.time()
        trajectory = LinearTrajectory(
            self.initial_position,
            self.final_position,
            self.max_velocity,
            self.acceleration,
            initial_time,
        )

        # Simulate some time points
        positions = []
        times = []
        while not trajectory.ended:
            times.append(time.time())
            pos = trajectory.position(times[-1])
            positions.append(pos)
            time.sleep(0.01)

        # Plotting
        plt.figure(figsize=(12, 6))

        # Plot velocity profile
        plt.subplot(1, 2, 1)
        plt.plot(
            trajectory.velocity_profile[:, 0] - initial_time,
            trajectory.velocity_profile[:, 1],
            label="Velocity",
        )
        plt.xlabel("Time (s)")
        plt.ylabel("Velocity (m/s)")
        plt.title("Velocity Profile")
        plt.grid(True)
        plt.legend()

        # Plot position profile
        plt.subplot(1, 2, 2)
        plt.plot(np.array(times) - initial_time, positions, label="Position")
        plt.xlabel("Time (s)")
        plt.ylabel("Position (m)")
        plt.title("Position Profile")
        plt.grid(True)
        plt.legend()

        plt.tight_layout()
        plt.show()


def stop_trajectory(trajectory, stop_time=None):
    """Return a trajectory that starts to decelerate at stop_time,
    with same characteristics as given trajectory"""
    if stop_time is None:
        stop_time = time.time()
    # Calculate current position and velocity at the stop time
    dt = stop_time - trajectory.initial_time
    current_position = trajectory._get_pos_at_time(dt)
    current_velocity = trajectory._get_velocity_at_time(dt)

    dec_time = abs(current_velocity / trajectory.acceleration)
    decel_distance = trajectory.direction * (
        current_velocity * current_velocity / (2 * trajectory.acceleration)
    )

    # Create a new trajectory from current position-decel_distance to a stop at current position+decel_distance
    new_trajectory = LinearTrajectory(
        current_position - decel_distance,
        current_position + decel_distance,
        abs(current_velocity),
        trajectory.acceleration,
        stop_time - dec_time,
    )
    # Keep velocity profile data, so it is possible to check the move
    new_trajectory._velocity_profile = trajectory._velocity_profile[:]

    return new_trajectory
