import argparse
import copy
from io import TextIOWrapper

import ophyd
import ophyd.sim as ops
import yaml
from bec_lib.scibec_validator import SciBecValidator

import ophyd_devices as opd

try:
    from bec_plugins import devices as plugin_devices
except ImportError:
    plugin_devices = None


class StaticDeviceTest:
    def __init__(self, config: str, output_file: TextIOWrapper) -> None:
        self.config = self.read_config(config)
        self.file = output_file

    @staticmethod
    def read_config(config) -> dict:
        """load a config from disk"""
        content = None
        with open(config, "r", encoding="utf-8") as file:
            file_content = file.read()
            content = yaml.safe_load(file_content)
        return content

    def check_signals(self, name, conf) -> None:
        """run checks on EpicsSignals"""
        try:
            dev_class = self._get_device_class(conf["deviceClass"])
            if issubclass(dev_class, ophyd.EpicsMotor):
                if "prefix" not in conf["deviceConfig"]:
                    msg_suffix = ""
                    if "read_pv" in conf["deviceConfig"]:
                        msg_suffix = "Maybe a typo? The device specifies a read_pv instead."
                    raise ValueError(f"{name}: does not specify the prefix. {msg_suffix}")
            if not issubclass(dev_class, ophyd.signal.EpicsSignalBase):
                if issubclass(dev_class, ophyd.Device):
                    for _, sub_name, item in dev_class.walk_components():
                        if not issubclass(item.cls, ophyd.signal.EpicsSignalBase):
                            continue
                        if not item.is_signal:
                            continue
                        if not item.kind < ophyd.Kind.normal:
                            continue
                        # check if auto_monitor is in kwargs
                        self._has_auto_monitor(f"{name}/{sub_name}", item.kwargs)
                return 0
            self._has_auto_monitor(name, conf["deviceConfig"])
            if "read_pv" not in conf["deviceConfig"]:
                raise ValueError(f"{name}: does not specify the read_pv")
            return 0
        except Exception as e:
            self.print_and_write(f"ERROR: {name} is not valid: {e}")
            return 1

    @staticmethod
    def _has_auto_monitor(name: str, config: dict) -> None:
        if "auto_monitor" not in config:
            print(f"WARNING: Device {name} is configured without auto monitor.")

    def _get_device_class(self, dev_type):
        """Return the class object from 'dev_type' string in the form '[module:][submodule:]class_name'

        The class is looked after in ophyd devices[.module][.submodule] first, if it is not
        present plugin_devices, ophyd, ophyd_devices.sim are searched too
        """
        submodule, _, class_name = dev_type.rpartition(":")
        if submodule:
            submodule = f".{submodule.replace(':', '.')}"
        for parent_module in (opd, plugin_devices, ophyd, ops):
            try:
                module = __import__(f"{parent_module.__name__}{submodule}", fromlist=[""])
            except ModuleNotFoundError:
                continue
            else:
                break
        else:
            raise TypeError(f"Unknown device class {dev_type}")
        return getattr(module, class_name)

    def validate_schema(self, name: str, conf: dict) -> None:
        """validate the device config against the json schema"""
        try:
            validator = SciBecValidator()
            db_config = self._translate_to_db_config(name, conf)
            validator.validate_device(db_config)
            return 0
        except Exception as e:
            self.print_and_write(f"ERROR: {name} is not valid: {e}")
            return 1

    @staticmethod
    def _translate_to_db_config(name, config) -> dict:
        """translate the config to the format used by the database"""
        db_config = copy.deepcopy(config)
        db_config["name"] = name
        if "deviceConfig" in db_config and db_config["deviceConfig"] is None:
            db_config["deviceConfig"] = {}
        db_config.pop("deviceType")
        return db_config

    def run(self) -> None:
        """run the test"""
        failed_devices = []
        for name, conf in self.config.items():
            return_val = 0
            self.print_and_write(f"Checking {name}...")
            return_val += self.validate_schema(name, conf)
            return_val += self.check_signals(name, conf)
            if return_val == 0:
                self.print_and_write("OK")
            else:
                self.print_and_write("FAILED")
                failed_devices.append(name)

        self.print_and_write("\n\n")
        self.print_and_write("========================================")
        # print summary
        self.print_and_write("Summary:")
        if len(failed_devices) == 0:
            print("All devices passed the test.")
            self.file.write("All devices passed the test.\n")
        else:
            print(f"{len(failed_devices)} devices failed the test:")
            self.file.write(f"{len(failed_devices)} devices failed the test:\n")
            for device in failed_devices:
                print(f"    {device}")
                self.file.write(f"    {device}\n")

    def print_and_write(self, text: str) -> None:
        print(text)
        self.file.write(text + "\n")


def launch() -> None:
    """launch the test"""
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description="Perform tests on an ophyd device config file.",
    )

    parser.add_argument("--config", help="path to the config file", required=True, type=str)
    optional = parser.add_argument_group("optional arguments")
    optional.add_argument("--output", default="./report.txt", help="path to the output file")
    parser.add_help = True

    clargs = parser.parse_args()

    with open("./report.txt", "w", encoding="utf-8") as file:
        device_config_test = StaticDeviceTest(clargs.config, output_file=file)
        device_config_test.run()
