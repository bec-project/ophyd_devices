import inspect
import threading
from unittest.mock import Mock, patch

from ophyd import status as ophyd_status_module
from ophyd.status import StatusBase

dummy_thread = Mock(spec=threading.Thread)


class PatchedStatusBase(StatusBase):
    def __init__(self, *args, **kwargs):
        timeout = kwargs.get("timeout", None)
        if not timeout:
            with patch("threading.Thread", dummy_thread):
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


def monkey_patch_ophyd():
    if ophyd_status_module.StatusBase.__name__ == "PatchedStatusBase":
        # prevent patching multiple times
        return
    for name, klass in inspect.getmembers(
        ophyd_status_module, lambda x: inspect.isclass(x) and StatusBase in x.__mro__
    ):
        mro = klass.mro()
        bases = tuple(PatchedStatusBase if x is StatusBase else x for x in mro)
        new_klass = type("Patched" + name, bases, {})
        setattr(ophyd_status_module, name, new_klass)
