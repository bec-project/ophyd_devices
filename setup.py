from setuptools import setup

__version__ = "0.0.0"

if __name__ == "__main__":
    setup(
        install_requires=["ophyd", "typeguard", "prettytable", "bec_lib"],
        extras_require={"dev": ["pytest", "pytest-random-order"]},
        version=__version__,
    )
