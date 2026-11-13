"""
AreaDetector HDF5 preparation, capture ownership, completion and file events.
"""

from collections.abc import Callable
from contextlib import AbstractContextManager
from pathlib import PurePosixPath
from typing import Any

import numpy as np
from ophyd.utils.errors import InvalidState, StatusTimeoutError, WaitTimeoutError

from ophyd_devices.interfaces.base_classes.camera_base import CaptureSupersededError
from ophyd_devices.interfaces.base_classes.psi_device_base import DeviceStoppedError
from ophyd_devices.interfaces.protocols.ad_camera import ADCamera
from ophyd_devices.utils.psi_device_base_utils import (
    CompareStatus,
    SequenceStatus,
    StatusBase,
    StatusTimeoutErrorWithErrorInfo,
    TransitionStatus,
    all_statuses,
    release_statuses,
)


class ADHDF5Capture:
    """
    Own one camera's optional HDF5 writer without defining PVs or starting workers.

    The camera component creates this helper once. It shares the component's command
    lock and uses the camera's lifecycle checks, so file operations cannot acquire
    independent ownership of camera input. IOC routing and XML layout are preserved.
    """

    def __init__(
        self,
        camera: ADCamera,
        *,
        command_lock: AbstractContextManager[Any],
        on_failure: Callable[[Exception], None],
    ) -> None:
        """
        Attach file operations without reading or writing hardware.

        Args:
            camera (ADCamera): Owning camera and its optional hdf5 plugin.
            command_lock (AbstractContextManager[Any]): The acquisition component's
                existing reentrant command lock.
            on_failure (Callable[[Exception], None]): Stop the owning acquisition on
                failure, preserving the original exception and obsolete-session guards.
        """
        self._camera = camera
        self._capture_lock = command_lock
        self._on_failure = on_failure
        self._path: str | None = None
        self._session: object | None = None
        self._completion: StatusBase | None = None

    ########################################
    #       Preparation and capture        #
    ########################################

    def prime(self) -> None:
        """
        Initialize a cold enabled HDF5 writer with one unsaved internal frame.

        This is a bounded blocking preparation step, called before scan settings
        and capture are applied. Already initialized, absent and disabled writers
        return immediately using monitored dimension readbacks. The caller must
        stop camera input first; this method leaves it stopped.

        Prime the writer in this order:

        1. Save controller/plugin settings and disable capture and automatic saving.
        2. Enable plugin callbacks and select a short, single internal acquisition.
           Temporarily replace exposure and period so previous long exposures cannot
           delay priming; restore both settings on success, failure or cancellation.
        3. Subscribe to valid HDF5 dimensions and Acquire-to-Done before starting input.
        4. Wait for both acknowledgements, then restore settings before returning.

        No ROI scan capture is armed and the user's live preference is unchanged.
        External sources must remain quiet during staging. The controller must
        support single internal acquisition. Stop cancels the acknowledgement
        statuses; cleanup also runs on timeout or a failed acquisition command.

        Raises:
            RuntimeError: Internal triggering is unavailable or received dimensions
                remain invalid after priming.
            TimeoutError: Priming does not finish within acquisition_timeout.
            DeviceStoppedError: The owning camera is stopped during priming.
            ExceptionGroup: Restoring settings fails after successful priming.
            Exception: Backend configuration or acquisition fails. Restoration
                failures are attached as notes without replacing that failure.
        """
        camera, cam = self._camera, self._camera.cam
        hdf5 = getattr(camera, "hdf5", None)
        if hdf5 is None:
            return
        if not camera.save_frame_data.get():
            with self._capture_lock:
                camera.check_cancelled()
                self.stop()
            return
        io = camera.io_timeout
        if np.asarray(hdf5.array_size.get(timeout=io, use_monitor=True)).sum() > 0:
            return
        if getattr(cam, "trigger_mode", None) is None:
            raise RuntimeError("HDF5 priming requires an internally triggered acquisition")
        settings = (
            (hdf5.auto_save, 0),
            (hdf5.enable, 1),
            (cam.array_callbacks, 1),
            (cam.acquire_time, 0.01),
            (cam.acquire_period, 0.01),
            (cam.image_mode, "Single"),
            (cam.trigger_mode, camera.internal_trigger_mode.value),
        )
        originals = [(sig, sig.get(timeout=io, use_monitor=False)) for sig, _ in settings]
        subscriptions = []
        failure = None
        try:
            for signal, value in [(cam.acquire, 0), (hdf5.capture, 0), *settings]:
                with self._capture_lock:
                    camera.check_cancelled()
                    if signal is hdf5.capture:
                        self._write_capture(value, check_current=camera.check_cancelled)
                    else:
                        signal.put(value, wait=True, timeout=io)
            received = CompareStatus(
                hdf5.array_size.width,
                0,
                operation_success=">",
                run=False,
                timeout=camera.acquisition_timeout,
                description="HDF5 received priming dimensions; check input routing and internal triggering",
            )
            subscriptions.append(received)
            idle = TransitionStatus(
                cam.acquire,
                transitions=[1, 0],
                run=False,
                timeout=camera.acquisition_timeout,
                description="HDF5 priming acquisition stopped",
            )
            subscriptions.append(idle)
            for status in subscriptions:
                camera.cancel_on_stop(status)
            primed = received & idle
            with self._capture_lock:
                camera.check_cancelled()
                cam.acquire.put(1, wait=False, timeout=io)
            primed.wait(timeout=camera.acquisition_timeout + io)
            camera.check_cancelled()
            if np.asarray(hdf5.array_size.get(timeout=io, use_monitor=True)).sum() == 0:
                raise RuntimeError("HDF5 received a frame without valid image dimensions")
        except Exception as error:
            failure = error
            error.add_note(
                "HDF5 priming failed. Check plugin input routing and internal triggering; "
                "alternatively disable frame saving with save_frame_data=False."
            )
            raise
        finally:
            cleanup_failure: Exception | None = None
            try:
                release_statuses(subscriptions, reason="HDF5 priming interrupted")
            except Exception as error:  # noqa: BLE001 - restore settings despite cleanup failure.
                cleanup_failure = error
            # Stop first. Always restore with writes because monitor caches may
            # not yet contain the temporary values applied above.
            errors = []
            for signal, value in [(cam.acquire, 0), *reversed(originals)]:
                try:
                    with self._capture_lock:
                        if not camera.stopped:
                            try:
                                camera.check_cancelled()
                            except CaptureSupersededError:
                                break  # A replacement owns its controller settings.
                        signal.put(value, wait=True, timeout=io)
                except Exception as error:  # noqa: BLE001 - attempt all restores.
                    errors.append(error)
            if cleanup_failure is not None:
                if failure is not None:
                    failure.add_note(
                        f"Releasing HDF5 priming subscriptions also failed: {cleanup_failure!r}"
                    )
                else:
                    if errors:
                        cleanup_failure.add_note(
                            f"Restoring HDF5 priming settings also failed: {errors!r}"
                        )
                    raise cleanup_failure
            if errors:
                if failure is not None:
                    failure.add_note(f"Restoring HDF5 priming settings also failed: {errors!r}")
                else:
                    raise ExceptionGroup("HDF5 priming restoration failed", errors)

    def stage(self, *, ioc_path: Callable[[str], str] | None = None) -> None:
        """
        Configure and arm the optional ``hdf5`` plugin when save_frame_data is enabled.

        1. Obtain the scan filename from BEC and create its output directory.
        2. Configure one stream file with unlimited capture and lazy opening.
        3. Announce the pending file, arm capture and acknowledge counter reset.

        Before camera input starts, require a fresh zero NumCaptured readback and
        a monitor cache that has caught up to the new capture. Previous-file counts
        must never satisfy completion of the new file.

        Translate BEC directory prefixes with hdf5_path_mapping when the IOC uses
        another mount point. Create the BEC directory before configuring the IOC's
        translated path, then validate its IOC readback. File events always use the
        BEC path. Preserve its input port and XML layout. Capture remains armed
        across software bursts; complete waits for all expected frames in fixed
        acquisition before closing. Continuous
        async capture closes at completion without an exact frame-count requirement.
        The saving preference is sampled at stage: disabling it during an active
        capture does not skip file closure or its final event. Previews and ROI
        publication are independent of this preference.

        Args:
            ioc_path (Callable[[str], str] | None): Optional owning component's path
                conversion method. Preserve component subclass overrides; None uses
                this helper's configured directory-prefix mapping.
        """
        camera = self._camera
        hdf5 = getattr(camera, "hdf5", None)
        if hdf5 is None:
            return
        if not camera.save_frame_data.get():
            with self._capture_lock:
                camera.check_cancelled()
                self.stop()
            return
        with self._capture_lock:
            camera.check_cancelled()
            session = object()
            self._session = session

        def check_current():
            camera.check_cancelled()
            if self._session is not session:
                raise CaptureSupersededError("HDF5 staging was superseded by another transition")

        io = camera.io_timeout
        if np.asarray(hdf5.array_size.get(timeout=io, use_monitor=True)).sum() == 0:
            raise RuntimeError("HDF5 is unprimed; call prime_hdf5() before arming scan capture")
        path = camera.file_utils.get_full_path(
            scan_status_msg=camera._scan_message, name=camera.name, create_dir=True
        )
        translate_path = self.ioc_path if ioc_path is None else ioc_path
        filename = PurePosixPath(translate_path(path))
        settings = [
            (hdf5.capture, 0),
            (hdf5.enable, 1),
            (hdf5.file_path, f"{filename.parent}/"),
            (hdf5.file_name, filename.name),
            (hdf5.file_template, "%s%s"),
            (hdf5.file_write_mode, 2),  # Stream
            (hdf5.auto_increment, 0),
            (hdf5.auto_save, 0),
            (hdf5.lazy_open, 1),
            (hdf5.num_capture, 0),  # Until complete/stop
        ]
        for signal, value in settings:
            with self._capture_lock:
                check_current()
                if signal is hdf5.capture:
                    self._write_capture(value, check_current=check_current)
                else:
                    signal.put(value, wait=True, timeout=io)
        if hdf5.file_path_exists.get(timeout=io, use_monitor=False) not in (1, "Yes"):
            raise RuntimeError(
                f"HDF5 output directory is unavailable to the IOC: {filename.parent}"
            )
        with self._capture_lock:
            check_current()
            # Record ownership before arming so failed startup can announce failure.
            self._path = path
            self._completion = None
            camera.file_event.put(
                file_path=path,
                done=False,
                successful=False,
                hinted_h5_entries={"data": "/entry/data/data"},
            )
            check_current()
            reset = CompareStatus(
                hdf5.num_captured,
                0,
                run=False,
                timeout=io,
                description="HDF5 new capture counter reset",
            )
            camera.cancel_on_stop(reset)
        failure: Exception | None = None
        try:
            with self._capture_lock:
                check_current()
                self._write_capture(1, check_current=check_current)
            actual = int(hdf5.num_captured.get(timeout=io, use_monitor=False))
            cached = int(hdf5.num_captured.get(timeout=io, use_monitor=True))
            if actual == 0 and cached == 0 and not reset.done:
                try:
                    reset.set_finished()
                except InvalidState:
                    pass  # The reset monitor completed concurrently.
            reset.wait(timeout=io)
            if int(hdf5.num_captured.get(timeout=io, use_monitor=False)) != 0:
                raise RuntimeError("HDF5 capture counter did not reset before scan input")
            with self._capture_lock:
                check_current()
        except Exception as error:
            failure = error
            with self._capture_lock:
                if self._session is session:
                    for cleanup in (
                        lambda: self._write_capture(0),
                        lambda: self._publish_event(successful=False),
                    ):
                        try:
                            cleanup()
                        except Exception as cleanup_error:  # noqa: BLE001
                            error.add_note(f"HDF5 arming cleanup also failed: {cleanup_error!r}")
            if isinstance(error, (WaitTimeoutError, StatusTimeoutError)):
                failure = TimeoutError("HDF5 capture counter reset was not acknowledged")
                raise failure from error
            raise
        finally:
            try:
                release_statuses((reset,), reason="HDF5 capture arming aborted")
            except Exception as cleanup_error:  # noqa: BLE001 - retain the arming failure.
                if failure is None:
                    raise
                failure.add_note(
                    f"Releasing HDF5 arming subscription also failed: {cleanup_error!r}"
                )

    def ioc_path(self, path: str) -> str:
        """
        Translate a BEC filename to the IOC's mount using directory prefixes.

        An empty mapping leaves the filename unchanged. With a mapping configured,
        require a matching absolute directory prefix; the most specific prefix wins.
        Match whole path components so /data never matches /database.

        Args:
            path (str): BEC-visible filename used in file events.

        Returns:
            str: IOC-visible filename, or the original path when no mapping is set.

        Raises:
            TypeError: Mapping entries are not absolute path strings.
            ValueError: A prefix is relative or no configured prefix matches the path.
        """
        mapping = getattr(self._camera, "hdf5_path_mapping", None)
        if mapping is None:
            return path
        if not isinstance(mapping, dict):
            raise TypeError("hdf5_path_mapping must map BEC directories to IOC directories")
        filename = PurePosixPath(path)
        prefixes = []
        for source, target in mapping.items():
            if not isinstance(source, str) or not isinstance(target, str):
                raise TypeError("HDF5 directory prefixes must be absolute path strings")
            source_path, target_path = PurePosixPath(source), PurePosixPath(target)
            if not source_path.is_absolute() or not target_path.is_absolute():
                raise ValueError("HDF5 directory prefixes must be absolute path strings")
            prefixes.append((source_path, target_path))
        for source, target in sorted(prefixes, key=lambda pair: len(pair[0].parts), reverse=True):
            if filename.is_relative_to(source):
                return str(target / filename.relative_to(source))
        if mapping:
            raise ValueError(f"No hdf5_path_mapping prefix matches BEC filename: {path}")
        return path

    ########################################
    #       Completion and shutdown        #
    ########################################

    def _write_capture(
        self, value: int, *, check_current: Callable[[], None] | None = None
    ) -> None:
        """
        Command the busy Capture record and acknowledge its readback explicitly.

        Put completion on Capture=1 lasts until the capture ends. Waiting for that
        callback while arming, or queueing another callback put to stop it, can
        delay shutdown. Use an ordinary put and a bounded readback watcher instead.
        The caller holds the command lock; shutdown watchers remain independent of
        acquisition cancellation so a stopped camera can still acknowledge closure.
        """
        camera, hdf5 = self._camera, self._camera.hdf5
        assert hdf5 is not None
        io = camera.io_timeout
        acknowledged = CompareStatus(
            hdf5.capture,
            value,
            run=False,
            timeout=io,
            description=f"HDF5 capture command {value} acknowledged",
        )
        failure: Exception | None = None
        try:
            if check_current is not None:
                camera.cancel_on_stop(acknowledged)
                check_current()
            hdf5.capture.put(value, wait=False, use_complete=False, timeout=io)
            # An unchanged readback need not emit a new monitor event.
            actual = int(hdf5.capture.get(timeout=io, use_monitor=False))
            if actual == value and not acknowledged.done:
                try:
                    acknowledged.set_finished()
                except InvalidState:
                    pass  # The readback notification completed concurrently.
            acknowledged.wait(timeout=io)
            if check_current is not None:
                check_current()
            if int(hdf5.capture.get(timeout=io, use_monitor=False)) != value:
                raise RuntimeError(f"HDF5 capture did not acknowledge command {value}")
        except (WaitTimeoutError, StatusTimeoutError, StatusTimeoutErrorWithErrorInfo) as error:
            failure = TimeoutError(f"HDF5 capture command {value} was not acknowledged")
            raise failure from error
        except Exception as error:
            failure = error
            raise
        finally:
            try:
                release_statuses((acknowledged,), reason="HDF5 capture command interrupted")
            except Exception as cleanup_error:  # noqa: BLE001 - preserve command failure.
                if failure is None:
                    raise
                failure.add_note(f"Releasing HDF5 capture watcher also failed: {cleanup_error!r}")

    def complete(
        self, acquisition: StatusBase, *, software_trigger: bool, async_frames: int | None
    ) -> StatusBase:
        """
        Await acquisition, drain queued writes, close the file and publish its result.

        Each operation creates its subscriptions before issuing hardware commands.
        Final writer status and frame counts are read directly from the IOC. Fixed
        acquisitions require every accepted frame; continuous async input has no exact
        count requirement. Only this capture may close or publish its file.

        Args:
            acquisition (StatusBase): Camera/ROI completion to await first.
            software_trigger (bool): Camera input consists of finite software bursts.
            async_frames (int | None): Fixed independent frame total, or None for
                continuous independent input. Ignored for software bursts.

        Returns:
            StatusBase: Original acquisition when no file is owned, otherwise the
                shared sequence completing after file validation or failure cleanup.
        """
        camera = self._camera
        with self._capture_lock:
            if getattr(camera, "hdf5", None) is None or self._path is None:
                return acquisition
            camera.check_cancelled()
            if self._completion is not None:
                return self._completion
            session = self._session

            def check_current() -> None:
                camera.check_cancelled()
                if self._session is not session or self._completion is not sequence:
                    raise DeviceStoppedError("HDF5 completion belongs to an interrupted capture")

            def failed(error: Exception) -> None:
                with self._capture_lock:
                    if self._session is not session or self._completion is not sequence:
                        return
                try:
                    self._on_failure(error)
                finally:
                    # Another stop may already own camera shutdown. Its file event
                    # must still precede this completion status reporting failure.
                    with self._capture_lock:
                        if self._session is session:
                            try:
                                self.stop()
                            except Exception as cleanup_error:  # noqa: BLE001
                                error.add_note(
                                    f"HDF5 failure cleanup also failed: {cleanup_error!r}"
                                )

            sequence = SequenceStatus(
                camera,
                steps=[
                    lambda: acquisition,
                    lambda: self._wait_for_written_frames(
                        check_current, software_trigger=software_trigger, async_frames=async_frames
                    ),
                    lambda: self._close_capture(check_current),
                    lambda: self._validate_and_publish_file(
                        check_current, software_trigger=software_trigger, async_frames=async_frames
                    ),
                ],
                on_failure=failed,
                description="HDF5 scan file closed",
                run=False,
            )
            self._completion = sequence
        # Constituents are registered individually. Do not cancel the outer sequence
        # between final file publication and its successful completion.
        sequence.run()
        return sequence

    def _expected_frames(self, *, software_trigger: bool, async_frames: int | None) -> int | None:
        """
        Read accepted software frames freshly, or return the fixed independent total.
        """
        camera = self._camera
        if software_trigger:
            return (
                int(camera.cam.array_counter.get(timeout=camera.io_timeout, use_monitor=False))
                - camera._frame_origin
            )
        return async_frames

    def _wait_for_written_frames(
        self, check_current: Callable[[], None], *, software_trigger: bool, async_frames: int | None
    ) -> StatusBase | None:
        """
        Subscribe to the required writer count, then confirm progress with a fresh read.

        Continuous async input skips the exact-count wait. Release any partially
        constructed watcher if setup fails before the sequence can take ownership.
        """
        check_current()
        if not software_trigger and async_frames is None:
            return None
        camera, hdf5 = self._camera, self._camera.hdf5
        assert hdf5 is not None
        frames = self._expected_frames(software_trigger=software_trigger, async_frames=async_frames)
        assert frames is not None
        check_current()
        captured = CompareStatus(
            hdf5.num_captured,
            frames,
            operation_success=">=",
            run=False,
            timeout=camera.acquisition_timeout,
            description="HDF5 accepted frames written",
        )
        try:
            camera.cancel_on_stop(captured)
            actual = int(hdf5.num_captured.get(timeout=camera.io_timeout, use_monitor=False))
            check_current()
            if actual >= frames and not captured.done:
                try:
                    captured.set_finished()
                except InvalidState:
                    pass  # A new frame notification completed concurrently.
            return captured
        except Exception:
            release_statuses((captured,), reason="HDF5 operation interrupted")
            raise

    def _close_capture(self, check_current: Callable[[], None]) -> StatusBase:
        """
        Install capture/writer idle watchers before submitting Capture=0.
        """
        check_current()
        camera, hdf5 = self._camera, self._camera.hdf5
        assert hdf5 is not None
        owned: list[StatusBase] = []
        try:
            capture_idle = CompareStatus(
                hdf5.capture,
                0,
                run=False,
                timeout=camera.acquisition_timeout,
                description="HDF5 capture closed",
            )
            owned.append(capture_idle)
            camera.cancel_on_stop(capture_idle)
            writer_idle = CompareStatus(
                hdf5.write_file,
                0,
                run=True,
                timeout=camera.acquisition_timeout,
                description="HDF5 writer idle",
            )
            owned.append(writer_idle)
            camera.cancel_on_stop(writer_idle)
            idle = all_statuses((capture_idle, writer_idle))
            camera.cancel_on_stop(idle)
            with self._capture_lock:
                check_current()
                hdf5.capture.put(0, wait=False, use_complete=False, timeout=camera.io_timeout)
            return idle
        except Exception:
            release_statuses(owned, reason="HDF5 operation interrupted")
            raise

    def _validate_and_publish_file(
        self, check_current: Callable[[], None], *, software_trigger: bool, async_frames: int | None
    ) -> None:
        """
        Validate fresh writer readbacks and publish success only for this capture.
        """
        check_current()
        camera, hdf5 = self._camera, self._camera.hdf5
        assert hdf5 is not None
        io = camera.io_timeout
        write_status = hdf5.write_status.get(timeout=io, use_monitor=False)
        if write_status not in (0, "OK"):
            message = hdf5.write_message.get(timeout=io, use_monitor=False)
            raise RuntimeError(f"HDF5 write failed: {message}")
        captured = int(hdf5.num_captured.get(timeout=io, use_monitor=False))
        expected = self._expected_frames(
            software_trigger=software_trigger, async_frames=async_frames
        )
        if captured == 0:
            raise RuntimeError("HDF5 acquisition produced no frames; no file was created")
        if expected is not None and captured < expected:
            raise RuntimeError(f"HDF5 captured {captured} frames, expected at least {expected}")
        with self._capture_lock:
            check_current()
            self._publish_event(successful=True)

    def stop(self) -> None:
        """
        Stop the optional writer and announce failure for any file still owned.

        Attempt final file publication even when the stop command fails. This does
        not stop camera input or ROI capture; the owning component controls that order.
        Disable callbacks and automatic saving too: Single/AutoSave mode can write
        frames independently of Capture, including while scan saving is disabled.
        Capture is a busy record: ordinary puts plus fresh readback acknowledgement
        avoid waiting for completion of the capture being interrupted.
        """
        hdf5 = getattr(self._camera, "hdf5", None)
        if hdf5 is None:
            return
        with self._capture_lock:
            errors = []
            for signal in (hdf5.enable, hdf5.auto_save, hdf5.capture):
                try:
                    if signal is hdf5.capture:
                        self._write_capture(0)
                    else:
                        signal.put(0, wait=True, timeout=self._camera.io_timeout)
                except Exception as error:  # noqa: BLE001 - attempt every shutdown command.
                    errors.append(error)
            try:
                self._publish_event(successful=False)
            except Exception as error:  # noqa: BLE001 - preserve any command failure.
                errors.append(error)
            if errors:
                for error in errors[1:]:
                    errors[0].add_note(f"Additional writer shutdown failure: {error!r}")
                raise errors[0]

    def _publish_event(self, *, successful: bool) -> None:
        """
        Announce one final file event and release ownership of this scan file.
        """
        if self._path is None:
            return
        session = self._session
        self._camera.file_event.put(
            file_path=self._path,
            done=True,
            successful=successful,
            hinted_h5_entries={"data": "/entry/data/data"},
        )
        if self._session is session:
            self._path = None
            self._session = None
