from setuptools import setup

__version__ = "0.13.4"

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
        version=__version__,
    )
