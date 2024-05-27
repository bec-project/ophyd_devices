import os
from pathlib import Path

import h5py
import hdf5plugin


class H5Writer:
    """Utility class to write data from device to disk"""

    def __init__(self, file_path: str = None, h5_entry: str = None):
        self.file_path = file_path
        self.h5_entry = h5_entry
        self.h5_file = None
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

    def prepare(self, file_path: str, h5_entry: str):
        """Prepare to write data to h5 file"""
        self.data_container = []
        self.file_path = file_path
        self.h5_entry = h5_entry
        self.create_dir()

    def write_data(self):
        """Write data to h5 file"""
        with h5py.File(self.file_path, "w") as h5_file:
            h5_file.create_dataset(self.h5_entry, data=self.data_container, **hdf5plugin.LZ4())
