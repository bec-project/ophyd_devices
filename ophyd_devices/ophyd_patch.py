import importlib
import importlib.util
import pathlib
import sys
from importlib.abc import Loader, MetaPathFinder
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


class _CustomLoader(Loader):
    def __init__(self, patched_code):
        self.patched_code = patched_code

    def load_module(self, fullname):
        """Load and execute ophyd.status"""
        status_module = ModuleType("ophyd.status")
        status_module.__loader__ = self
        status_module.__file__ = None
        status_module.__name__ = fullname

        exec(self.patched_code, status_module.__dict__)
        sys.modules[fullname] = status_module

        return status_module, True


class _CustomImporter(MetaPathFinder):
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
        self.loader = _CustomLoader(self.patched_code)

    def find_spec(self, fullname, path, target=None):
        # The new import classes are difficult to grasp;
        # why the finder needs a .loader member, it could be returned
        # from here. And also .name, which name has to correspond to
        # the searched module ???
        if fullname == "ophyd.status":
            self.name = fullname
            return self
        return None


def monkey_patch_ophyd():
    sys.meta_path.insert(0, _CustomImporter())
