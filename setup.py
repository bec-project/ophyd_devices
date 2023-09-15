from setuptools import setup

__version__ = "0.8.0"

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
        ],
        extras_require={"dev": ["pytest", "pytest-random-order", "black"]},
        version=__version__,
    )
