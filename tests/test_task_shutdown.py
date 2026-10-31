"""
Task shutdown acknowledges thread exit before device resources can be released.
"""

import threading
from unittest.mock import Mock

import pytest
from ophyd import Component, Device, Signal

from ophyd_devices.interfaces.base_classes.psi_device_base import PSIDeviceBase
from ophyd_devices.utils.psi_device_base_utils import (
    TaskKilledError,
    TaskShutdownError,
    destroy_subdevices,
)


class WorkerDevice(PSIDeviceBase):
    """
    A worker may use this signal in its final cleanup.
    """

    value = Component(Signal, value=1)


@pytest.mark.parametrize("grouping", ["root", "ordinary", "custom"])
def test_destroy_timeout_keeps_worker_subtree_alive_for_retry(monkeypatch, grouping):
    """
    Neither root cleanup nor group traversal may bypass an unquiesced worker.
    """

    class Group(Device):
        worker = Component(WorkerDevice)

    class CustomGroup(Group):
        def destroy(self):
            destroy_subdevices(self)
            super().destroy()

    class Root(PSIDeviceBase):
        group = Component(CustomGroup if grouping == "custom" else Group)

    root = WorkerDevice(name="root") if grouping == "root" else Root(name="root")
    worker = root if grouping == "root" else root.group.worker
    entered, release = threading.Event(), threading.Event()
    cleanup_values = []
    # Model native I/O that defers Python cancellation until it returns. Merely
    # entering the task does not guarantee Event.wait is already blocking.
    monkeypatch.setattr("ophyd_devices.utils.psi_device_base_utils.set_async_exc", lambda *_args: 1)

    def task():
        try:
            entered.set()
            release.wait()
        finally:
            assert not worker.value._destroyed
            cleanup_values.append(worker.value.get())

    status = worker.task_handler.submit_task(task)
    thread = worker.task_handler._tasks[status.task_id][1]
    shutdown = worker.task_handler.shutdown
    monkeypatch.setattr(worker.task_handler, "shutdown", lambda: shutdown(timeout=0.02))
    try:
        assert entered.wait(timeout=1)
        with pytest.raises(TaskShutdownError, match="did not stop"):
            root.destroy()
        assert not root.destroyed
        assert not worker.destroyed
        assert not worker.value._destroyed
        with pytest.raises(TaskShutdownError):
            worker.task_handler.submit_task(lambda: None)
    finally:
        release.set()
        thread.join(timeout=1)
    assert not thread.is_alive()
    assert cleanup_values == [1]
    with pytest.raises(TaskKilledError):
        status.wait(timeout=1)
    root.destroy()
    assert root.destroyed
    assert worker.value._destroyed


def test_destroy_waits_for_worker_cleanup_before_disconnect(monkeypatch):
    """
    A successful destruction waits for the worker's final signal access.
    """
    root = WorkerDevice(name="root")
    entered, release = threading.Event(), threading.Event()
    cleanup_values = []

    def task():
        try:
            entered.set()
            release.wait()
        finally:
            assert not root.value._destroyed
            cleanup_values.append(root.value.get())

    status = root.task_handler.submit_task(task)
    thread = root.task_handler._tasks[status.task_id][1]
    join = thread.join
    cancel = Mock()
    # Exercise the join/resource barrier independently of asynchronous exception
    # delivery, which is covered by the task-cancellation tests.
    monkeypatch.setattr(root.task_handler, "kill_task", cancel)

    def release_and_join(*, timeout):
        assert thread.is_alive()
        assert not root.destroyed
        assert not root.value._destroyed
        release.set()
        join(timeout=timeout)
        assert not thread.is_alive()
        assert cleanup_values == [1]

    joined = Mock(side_effect=release_and_join)
    monkeypatch.setattr(thread, "join", joined)
    try:
        assert entered.wait(timeout=1)
        root.destroy()
    finally:
        release.set()
        join(timeout=1)
    cancel.assert_called_once_with(status)
    joined.assert_called_once()
    assert cleanup_values == [1]
    assert root.value._destroyed
    assert status.done


def test_shutdown_cancels_unstarted_tasks_and_allows_next_scan():
    """
    Cancelled deferred work cannot run later; a drained handler can accept new work.
    """
    root = WorkerDevice(name="root")
    work = Mock()
    status = root.task_handler.submit_task(work, run=False)
    root.task_handler.shutdown(timeout=1)
    with pytest.raises(TaskKilledError):
        status.wait(timeout=1)
    with pytest.raises(TaskShutdownError):
        root.task_handler.start_task(status)
    work.assert_not_called()
    root.task_handler.submit_task(work).wait(timeout=1)
    root.task_handler.shutdown(timeout=1)
    work.assert_called_once()
    root.destroy()


def test_shutdown_retires_worker_before_its_execution_wrapper_enters(monkeypatch):
    """
    A started thread delayed before the protected wrapper cannot run cancelled work.
    """
    root = WorkerDevice(name="root")
    entered, release = threading.Event(), threading.Event()
    execute = root.task_handler._wrap_task
    work = Mock()

    def delayed(*args, **kwargs):
        entered.set()
        release.wait()
        return execute(*args, **kwargs)

    monkeypatch.setattr(root.task_handler, "_wrap_task", delayed)
    status = root.task_handler.submit_task(work)
    thread = root.task_handler._tasks[status.task_id][1]
    try:
        assert entered.wait(timeout=1)
        with pytest.raises(TaskShutdownError):
            root.task_handler.shutdown(timeout=0.02)
    finally:
        release.set()
        thread.join(timeout=1)
    assert not thread.is_alive()
    work.assert_not_called()
    with pytest.raises(TaskKilledError):
        status.wait(timeout=1)
    root.destroy()


def test_worker_stop_cannot_claim_its_own_resources_are_released():
    """
    Self-stop avoids self-join and prevents teardown while the worker still runs.
    """
    unstaged = Mock()

    class Detector(WorkerDevice):
        def on_stop(self):
            self.task_handler.shutdown(timeout=1)
            unstaged()

    root = Detector(name="root")
    status = root.task_handler.submit_task(root.stop, run=False)
    thread = root.task_handler._tasks[status.task_id][1]
    root.task_handler.start_task(status)
    with pytest.raises(TaskShutdownError, match="own shutdown"):
        status.wait(timeout=1)
    thread.join(timeout=1)
    assert not thread.is_alive()
    unstaged.assert_not_called()
    assert not root.value._destroyed
    root.destroy()


def test_task_interruption_during_execution_cleanup_cannot_retain_task_id():
    """
    An interruption at the inner cleanup boundary is retried by final bookkeeping.
    """

    class InterruptedSet(set):
        interrupted = False

        def discard(self, value):
            if not self.interrupted:
                self.interrupted = True
                raise TaskKilledError("interrupted during execution cleanup")
            super().discard(value)

    root = WorkerDevice(name="root")
    root.task_handler._executing_tasks = InterruptedSet()
    status = root.task_handler.submit_task(lambda: None, run=False)
    thread = root.task_handler._tasks[status.task_id][1]
    root.task_handler.start_task(status)
    with pytest.raises(TaskKilledError):
        status.wait(timeout=1)
    thread.join(timeout=1)
    assert not thread.is_alive()
    assert not root.task_handler._executing_tasks
    assert not root.task_handler._tasks
    root.destroy()


def test_killing_deferred_task_does_not_block_future_work():
    """
    Cancelling a task with no thread finishes it and leaves the handler reusable.
    """
    root = WorkerDevice(name="root")
    work = Mock()
    status = root.task_handler.submit_task(work, run=False)
    root.task_handler.kill_task(status)
    with pytest.raises(TaskKilledError):
        status.wait(timeout=1)
    assert not root.task_handler._tasks
    assert not root.task_handler._cancelled_tasks
    work.assert_not_called()
    root.task_handler.submit_task(work).wait(timeout=1)
    root.task_handler.shutdown(timeout=1)
    work.assert_called_once()
    root.destroy()
