import threading
import time
from unittest.mock import Mock

import pytest
from ophyd.status import StatusBase, StatusTimeoutError

import ophyd_devices  # ensure we are patched


def test_ophyd_status_patch():
    cb = Mock()

    st = StatusBase(timeout=1)
    assert isinstance(st._callback_thread, threading.Thread)
    st.add_callback(cb)
    with pytest.raises(StatusTimeoutError):
        time.sleep(1.1)
        st.wait()
    cb.assert_called_once()
    cb.reset_mock()

    st = StatusBase()
    assert isinstance(st._callback_thread, Mock)
    st.add_callback(cb)
    st.set_finished()
    cb.assert_called_once()
    cb.reset_mock()
    st.wait()

    st = StatusBase(settle_time=1)
    st.add_callback(cb)
    assert isinstance(st._callback_thread, Mock)
    st.set_finished()
    assert cb.call_count == 0
    time.sleep(0.5)
    assert cb.call_count == 0  # not yet!
    time.sleep(0.6)
    cb.assert_called_once()
    cb.reset_mock()
    st.wait()

    class TestException(RuntimeError):
        pass

    st = StatusBase()
    st.add_callback(cb)
    st.set_exception(TestException())
    cb.assert_called_once()
    with pytest.raises(TestException):
        st.wait()
