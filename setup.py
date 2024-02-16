from setuptools import setup

__version__ = "0.21.0"

if __name__ == "__main__":
    setup(
        install_requires=[
            "ophyd",
            "typeguard",
            "prettytable",
            "bec_lib",
            "numpy",
            "pyyaml",
            "std_daq_client",
            "pyepics",
            "pytest",
        ],
        extras_require={"dev": ["pytest", "pytest-random-order", "black", "coverage"]},
        package_data={"ophyd_devices.smaract": ["smaract_sensors.json"]},
        entry_points={"console_scripts": ["ophyd_test = ophyd_devices:launch"]},
        version=__version__,
    )
