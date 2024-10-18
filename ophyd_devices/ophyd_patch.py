import importlib
import importlib.util
import pathlib
import sys
from types import ModuleType

_patched_status_base = """
import threading
from unittest.mock import Mock, patch

_StatusBase = StatusBase

class StatusBase(_StatusBase):
    _bec_patched = True

    def __init__(self, *args, **kwargs):
        timeout = kwargs.get("timeout", None)
        if not timeout:
            with patch("threading.Thread", Mock(spec=threading.Thread)):
                super().__init__(*args, **kwargs)
        else:
            super().__init__(*args, **kwargs)

    def set_finished(self, *args, **kwargs):
        super().set_finished(*args, **kwargs)
        if isinstance(self._callback_thread, Mock):
            if self.settle_time > 0:

                def settle_done():
                    self._settled_event.set()
                    self._run_callbacks()

                threading.Timer(self.settle_time, settle_done).start()
            else:
                self._run_callbacks()

    def set_exception(self, *args, **kwargs):
        super().set_exception(*args, **kwargs)
        if isinstance(self._callback_thread, Mock):
            self._run_callbacks()

"""


class _CustomImporter:
    def __init__(self):
        origin = pathlib.Path(importlib.util.find_spec("ophyd").origin)
        module_file = str(origin.parent / "status.py")

        with open(module_file, "r") as source:
            src = source.read()
            before, _, after = src.partition("class StatusBase")
            orig_status_base, _, final = after.partition("\nclass ")

        self.patched_source = (
            f"{before}class StatusBase{orig_status_base}{_patched_status_base}class {final}"
        )
        self.patched_code = compile(self.patched_source, module_file, "exec")

    def find_module(self, fullname, path):
        if fullname == "ophyd.status":
            return self
        return None

    def load_module(self, fullname, module_dict=None):
        """Load and execute ophyd.status"""
        status_module = ModuleType("ophyd.status")
        status_module.__loader__ = self
        status_module.__file__ = None
        status_module.__name__ = fullname

        exec(self.patched_code, status_module.__dict__)
        sys.modules[fullname] = status_module

        return status_module, True

    def get_source(self, fullname):
        return self.patched_source


def monkey_patch_ophyd():
    sys.meta_path.insert(0, _CustomImporter())
