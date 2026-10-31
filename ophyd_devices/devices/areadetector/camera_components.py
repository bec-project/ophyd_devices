"""Shared AreaDetector timing, acquisition and publication operations."""

from math import isfinite
from threading import RLock
from typing import Any, Generic, TypeVar, cast
from uuid import uuid4

import numpy as np
from bec_lib import messages
from bec_lib.utils.rpc_utils import rgetattr
from ophyd.utils.errors import InvalidState

from ophyd_devices.devices.areadetector.hdf5_capture import ADHDF5Capture
from ophyd_devices.devices.areadetector.plugins import HDF5Plugin_V35, ImagePlugin_V35
from ophyd_devices.interfaces.base_classes.camera_base import (
    AcquisitionMode,
    AcquisitionSource,
    CameraBusyError,
)
from ophyd_devices.interfaces.base_classes.psi_device_base import DeviceStoppedError
from ophyd_devices.interfaces.protocols.ad_camera import ADCamera
from ophyd_devices.utils.bec_roi_signals.ad_roi_signal import ADROIProcessing
from ophyd_devices.utils.camera_preview import CameraPreview
from ophyd_devices.utils.psi_device_base_utils import (
    CompareStatus,
    DeviceStatus,
    SequenceStatus,
    StatusBase,
    SubscriptionStatus,
    TransitionStatus,
    all_statuses,
    release_statuses,
)

CameraT = TypeVar("CameraT")


class CameraImage(ImagePlugin_V35):
    """
    Image plugin read explicitly for optional Redis previews.

    Disable the unused derived image so device metadata can be described before
    the IOC has produced its first frame.
    """

    shaped_image = None


class CameraHDF5(HDF5Plugin_V35):
    """
    HDF5 plugin prepared by the camera-owned ADHDF5Capture helper.

    Ophyd stages children before on_stage. Defer preparation to that hook so
    disabled writers need no priming and enabled writers can acquire an unsaved
    frame before scan capture is armed. Do not configure native stage_sigs here.
    """

    def stage(self) -> list[object]:
        """
        Leave preparation to the camera's explicit staging sequence.
        """
        return []

    def unstage(self) -> list[object]:
        """
        Leave shutdown to the camera's completion and stop hooks.
        """
        return []


class ADCameraComponents(Generic[CameraT]):
    """
    Camera operations called explicitly by the concrete device hooks.

    Owns no PVs, workers or publishing sockets. Acquisition readiness and completion
    are represented by subscription/composite statuses. ROI buffer state and result publication belong to each
    ADROIProcessing device. Timing is resolved here from camera config/scan info.
    """

    def __init__(self, camera: CameraT) -> None:
        """
        Attach shared operations to a concrete camera without hardware I/O.

        Args:
            camera: Camera owning the PVs, config signals and standard device hooks.
        """
        self.camera: CameraT = camera
        # Ophyd descriptors appear as Components during structural matching, but
        # resolve to signals on an instance. Keep that typing bridge at this boundary.
        self._camera = cast(ADCamera, camera)
        self._software_trigger = True
        self._async_frames: int | None = None
        self._correlation_group = "monitored"
        self._last_preview_id: int | None = None
        self._pre_scan_timing: tuple[float, float] | None = None
        self._capture_lock = RLock()
        self._stream_statuses: dict[ADROIProcessing, StatusBase] = {}
        self._stream_limit_status: StatusBase | None = None
        self._stream_error: Exception | None = None
        self._acquisition_status: StatusBase | None = None
        self.hdf5 = ADHDF5Capture(
            self._camera,
            command_lock=self._capture_lock,
            on_failure=self._cleanup_failed_acquisition,
        )

    ########################################
    #        Camera initialization         #
    ########################################

    def initialize_camera(self) -> None:
        """
        Prepare camera configuration from the normal on_connected hook.

        Describe existing preview transports, validate camera-owned ROIs and remove
        acquisition-controlled PVs from native stage_sigs. Preserve unrelated gain,
        transform and beamline stage settings. This performs no acquisition PV I/O
        and creates no publisher or worker. The concrete on_connected hook also
        initializes timing and stops input; the concrete camera starts live acquisition
        from its on_connected hook.

        Raises:
            ValueError: A camera ROI still has legacy capture management enabled.
        """
        self._camera._configure_preview_transports(
            ["preview", *(f"{roi.dotted_name}.preview" for roi in self.get_rois())]
        )
        for roi in self.get_rois():
            if roi.manage_capture:
                raise ValueError("Camera ROI requires manage_capture=False")
        # Native staging must not overwrite acquisition-owned PVs. Keep gain,
        # transform and other unrelated beamline stage settings intact.
        managed = [
            getattr(self._camera.cam, name, None)
            for name in (
                "acquire",
                "acquire_time",
                "acquire_period",
                "num_images",
                "image_mode",
                "trigger_mode",
                "array_callbacks",
            )
        ]
        if self._camera.image is not None:
            managed.append(self._camera.image.enable)
        for roi in self.get_rois():
            managed.extend((roi.roi1.enable, roi.stats1.enable))
        for child in [self._camera, *(child for _, child in self._camera.walk_subdevices())]:
            for key in tuple(child.stage_sigs):
                signal = rgetattr(child, key) if isinstance(key, str) else key
                if any(signal is owned for owned in managed if owned is not None):
                    del child.stage_sigs[key]

    ########################################
    #            ROI discovery             #
    ########################################

    def get_rois(self) -> list[ADROIProcessing]:
        """
        Return all ADROIProcessing descendants in declaration order.

        Includes lazy and nested devices. Discovery is performed on every call;
        capture state belongs to each ROI, rather than a cached camera-side list.

        Returns:
            ROI devices, including inactive ROIs whose enablement must be updated.
        """
        return [
            child
            for _, child in self._camera.walk_subdevices(include_lazy=True)
            if isinstance(child, ADROIProcessing)
        ]

    ########################################
    #    Live and scan timing settings     #
    ########################################

    def initialize_settings(self) -> None:
        """
        Read initial effective timing/count from the controller after connection.

        Called from on_connected using bounded PV reads.
        Does not change controller PVs. The controller
        remains the source of manual settings; there are no duplicate config signals.
        """
        camera = self._camera
        camera.exposure, camera.period = self._read_controller_timing()
        camera.frames_per_trigger = self._validate_frames(
            camera.cam.num_images.get(timeout=camera.io_timeout, use_monitor=False)
        )

    def _read_controller_timing(self) -> tuple[float, float]:
        """
        Read and validate fresh controller exposure and period, bypassing monitor caches.
        """
        cam, io = self._camera.cam, self._camera.io_timeout
        return self._validate_timing(
            cam.acquire_time.get(timeout=io, use_monitor=False),
            cam.acquire_period.get(timeout=io, use_monitor=False),
        )

    def resolve_scan_settings(self) -> None:
        """
        Resolve and validate scan settings before changing hardware.

        use_scan_timing selects incoming scan settings or current controller settings.
        Incoming exposure is the requested period minus the larger of scan readout
        time and detector_readout_time. The same flag selects frames_per_trigger. Commit effective values only after validation;
        leave controller PVs unchanged until stage_camera applies the resolved values.

        Raises:
            ValueError: Timing or frame count is invalid.
            KeyError: Required incoming scan parameters are missing.
        """
        camera = self._camera
        info = camera._scan_message.info
        if camera.use_scan_timing.get():
            period = float(info["exp_time"])
            readout = max(float(info.get("readout_time", 0)), camera.detector_readout_time)
            if not isfinite(readout) or readout < 0 or period <= readout:
                raise ValueError("Scan period must exceed nonnegative readout time")
            exposure = period - readout
            frames = info["frames_per_trigger"]
        else:
            exposure, period = self._read_controller_timing()
            frames = camera.cam.num_images.get(timeout=camera.io_timeout, use_monitor=False)
        exposure, period = self._validate_timing(exposure, period)
        frames = self._validate_frames(frames)
        with self._capture_lock:
            camera.check_cancelled()
            camera.exposure, camera.period, camera.frames_per_trigger = exposure, period, frames

    def live_timing(self) -> tuple[float, float]:
        """
        Select scan timing or restore the controller timing from before a scan.

        With live_follows_scan_timing enabled, use the latest resolved scan timing.
        Otherwise restore the pre-scan exposure/period if a scan replaced them;
        outside a scan transition, keep whatever is currently set on the controller.
        The flag is evaluated when live resumes, so changes during a scan are deferred.
        """
        camera = self._camera
        if camera.live_follows_scan_timing.get():
            return self._validate_timing(camera.exposure, camera.period)
        if self._pre_scan_timing is not None:
            return self._pre_scan_timing
        return self._read_controller_timing()

    ########################################
    #     AD scan acquisition methods      #
    ########################################

    def stage_camera(self) -> StatusBase | None:
        """
        Configure camera acquisition from its scan readout priority.

        Select the lifecycle:

        - Baseline: prepare one finite burst; on_pre_scan starts it after staging.
        - Monitored: prepare finite bursts and wait for each BEC trigger.
        - Async: arm ROI capture and start input from acquisition_source here.
          acquisition_mode=fixed acquires the configured total and completion waits
          for the camera to finish. continuous runs until on_complete stops input.
          With ROI outputs selected, samples per scan must fit the IOC buffer.
        - On-request: retain live behavior without scan capture.

        Prepare the scan in this order:

        1. Validate the BEC trigger configuration and optional external input.
        2. Stop previous camera/ROI input and save pre-scan controller timing.
        3. Apply exposure, period, image count, image mode and trigger source.
        4. Disable the image plugin, record frame origins and defer ROI changes.
        5. Arm optional HDF5 writing before any scan acquisition starts.

        BEC softwareTrigger must be true for monitored cameras and false for async
        cameras. It is validated rather than used as another acquisition selector.
        Baseline trigger calls do not acquire additional frames. IOC ZMQ publication
        is independent of this method. External pulses must remain quiet until the
        returned readiness status completes.

        Returns:
            Startup status for async input; None for baseline/monitored preparation
            or on-request priority. Bounded configuration I/O runs before returning.

        Raises:
            ValueError: Unsupported source or inconsistent BEC softwareTrigger setting.
            NotImplementedError: External acquisition has no configured driver input.
            ROI arming and input-start failures are reported through the returned status.
        """
        camera, cam, io = self._camera, self._camera.cam, self._camera.io_timeout
        camera.check_cancelled()
        group = camera.readout_priority
        if group == "on_request":
            return None
        if group not in ("baseline", "monitored", "async"):
            raise ValueError(f"Unsupported camera readout priority: {group}")
        software_trigger = group in ("baseline", "monitored")
        if camera.device_manager is not None and group in ("monitored", "async"):
            configured = camera.device_manager.devices[camera.name].software_trigger
            required = group == "monitored"
            if configured != required:
                raise ValueError(
                    f"Camera readout priority {group!r} requires softwareTrigger={required}"
                )
        external_trigger = (
            group == "async"
            and AcquisitionSource(camera.acquisition_source.get()) == AcquisitionSource.EXTERNAL
        )
        async_frames = None
        capture_capacity = camera.async_frame_limit
        if (
            group == "async"
            and AcquisitionMode(camera.acquisition_mode.get()) == AcquisitionMode.FIXED
        ):
            if camera.use_scan_timing.get():
                points = self._validate_frames(camera._scan_message.info["num_points"])
                async_frames = points * camera.frames_per_trigger
            else:
                async_frames = camera.frames_per_trigger  # Resolved controller NumImages.
            if capture_capacity is not None:
                self._validate_frames(capture_capacity)
                if async_frames > capture_capacity and any(
                    roi.active.get() and roi.selected_operations.get() for roi in self.get_rois()
                ):
                    raise ValueError("Fixed async acquisition exceeds async_frame_limit")
            capture_capacity = async_frames
        if external_trigger and (
            camera.external_trigger_mode is None or getattr(cam, "trigger_mode", None) is None
        ):
            raise NotImplementedError(
                "External triggering requires a configured camera trigger input"
            )
        with self._capture_lock:
            camera.check_cancelled()
            self.stop_camera()
            self._async_frames = async_frames
            self._software_trigger = software_trigger
            self._correlation_group = group
            self._acquisition_status = None
        if self._pre_scan_timing is None:
            previous_timing = self._read_controller_timing()
            with self._capture_lock:
                camera.check_cancelled()
                if self._pre_scan_timing is None:
                    self._pre_scan_timing = previous_timing
        settings = [(cam.acquire_time, camera.exposure), (cam.acquire_period, camera.period)]
        if software_trigger or self._async_frames is not None:
            count = camera.frames_per_trigger if software_trigger else self._async_frames
            settings.extend([(cam.num_images, count), (cam.image_mode, "Multiple")])
        else:
            settings.append((cam.image_mode, "Continuous"))
        settings.append((cam.array_callbacks, 1))
        if getattr(cam, "trigger_mode", None) is not None:
            mode = (
                camera.external_trigger_mode if external_trigger else camera.internal_trigger_mode
            )
            settings.append((cam.trigger_mode, mode.value))
        if camera.image is not None:
            settings.append((camera.image.enable, "Disable"))
        for signal, value in settings:
            with self._capture_lock:
                camera.check_cancelled()
                signal.put(value, wait=True, timeout=io)
        frame_origin = int(cam.array_counter.get(timeout=io, use_monitor=False))
        with self._capture_lock:
            camera.check_cancelled()
            camera.session_id = uuid4().hex
            self._stream_error = None
            camera._frame_origin = frame_origin
            for roi in self.get_rois():
                roi._capture_outputs = {}
                roi.update_received.block_updates(owner="capture")
        self.stage_hdf5()
        if software_trigger:
            return None

        with self._capture_lock:
            camera.check_cancelled()
            startup = SequenceStatus(
                camera,
                steps=[
                    lambda: self.arm_rois(capacity=capture_capacity),
                    self._start_scan_input,
                    camera.check_cancelled,
                ],
                on_failure=self._cleanup_failed_acquisition,
                description="Camera scan input armed/running",
                run=False,
            )
            self._acquisition_status = startup
            # Own cancellation before either operation can submit input. The
            # sequence preserves an internal failure through reentrant stop cleanup.
            # Its final ownership check also rejects a stop during the start write.
            camera.cancel_on_stop(startup)
        startup.run()
        return startup

    def _start_scan_input(self) -> CompareStatus:
        """
        Start independent input after ROI arming and return its running acknowledgement.

        Subscribe before Acquire and register the watcher immediately. Retain the
        camera command lock and lifecycle check before submitting input. Release any
        partial watcher if setup fails before the sequence can take ownership.
        """
        camera, cam, io = self._camera, self._camera.cam, self._camera.io_timeout
        camera.check_cancelled()
        self.start_streaming()
        started = CompareStatus(
            cam.acquire, 1, run=False, timeout=io, description="Camera scan input started"
        )
        try:
            camera.cancel_on_stop(started)
            with self._capture_lock:
                camera.check_cancelled()
                cam.acquire.put(1, wait=False, timeout=io)
            return started
        except Exception:
            release_statuses((started,), reason="Camera scan startup interrupted")
            raise

    def arm_rois(self, *, capacity: int | None) -> StatusBase | DeviceStatus:
        """
        Arm every ROI/Stats pair and return their combined readiness status.

        Each ROI owns plugin enablement, buffer settings, reset acknowledgement and
        cancellation. Camera input must remain stopped until all ROIs are ready.
        Declaration order is preserved when submitting the arming commands.

        Args:
            capacity (int | None): Maximum samples per ROI: burst size for triggered
                input or total samples per scan for async input. None uses each ROI's
                selected waveform capacity. An explicit limit must fit every waveform.

        Returns:
            Combined readiness status. The no-ROI case is already finished, so callers
            can install the next acquisition callback without a separate branch.
            ROI failures propagate through the status; the caller owns camera cleanup.
        """
        return all_statuses(
            roi.arm_capture(camera=self._camera, capacity=capacity) for roi in self.get_rois()
        )

    def trigger_camera(self) -> StatusBase | None:
        """
        Acquire one software burst and return readiness, capture and publication status.

        Execute the burst in this order:

        1. Arm all ROI buffers before camera input starts.
        2. Subscribe to the frame count and Acquire-to-Done transition.
        3. Issue Acquire only after those subscriptions are installed.
        4. Wait for camera input to finish, then drain accepted ROI frames.
        5. Publish ROI DynamicSignals before completing the returned status.

        Registering subscriptions before Acquire also covers immediate completion.
        Baseline and monitored priorities select finite bursts during staging.
        Async priority returns without retriggering its independently running input.
        The scan-wide scan_type does not change this lifecycle.

        Returns:
            A status covering ROI arming, camera acquisition, drain and publication.
            Returns None for independent acquisition, whose input is already running.
            Averaging follows each ROI's average_frames_per_trigger setting. Baseline
            reduction is selected by the baseline priority; the concrete hook acquires
            that single burst in on_pre_scan and ignores subsequent baseline triggers.

        Raises:
            RuntimeError: A previous camera acquisition is still in progress.
            Acquisition, timeout and publication failures are forwarded through the
            returned status after hardware cleanup. Stop cancels pending work.
        """
        camera = self._camera
        if not self._software_trigger:
            return None  # Async input is already running; do not retrigger it.
        with self._capture_lock:
            camera.check_cancelled()
            if self._acquisition_status is not None and not self._acquisition_status.done:
                raise CameraBusyError("Camera acquisition is already in progress")
            sequence = SequenceStatus(
                camera,
                steps=[
                    lambda: self.arm_rois(capacity=camera.frames_per_trigger),
                    self._acquire_burst,
                    self._drain_rois,
                    self._publish_rois,
                ],
                on_failure=self._cleanup_failed_acquisition,
                description="Camera burst and ROI publication",
                run=False,
            )
            self._acquisition_status = sequence
        camera.cancel_on_stop(sequence)
        sequence.run()
        return sequence

    def _acquire_burst(self) -> StatusBase:
        """
        Install frame/idle watchers before issuing one finite Acquire command.

        The returned status covers both the requested frame count and the camera's
        acquiring-to-idle transition. Observe both states after subscribing so the
        camera's initial idle state cannot acknowledge the new burst.
        Each watcher is registered immediately so failure during setup is interruptible.
        Hardware submission retains the same lock and final cancellation check as stop.
        """
        camera, cam, io = self._camera, self._camera.cam, self._camera.io_timeout
        camera.check_cancelled()
        timeout = max(
            camera.acquisition_timeout, camera.period * camera.frames_per_trigger * 2 + io
        )
        target = (
            int(cam.array_counter.get(timeout=io, use_monitor=False)) + camera.frames_per_trigger
        )
        owned: list[StatusBase] = []
        try:
            camera.check_cancelled()
            frames_ready = CompareStatus(
                cam.array_counter,
                target,
                operation_success=">=",
                run=True,
                timeout=timeout,
                description="Camera produced requested frames",
            )
            owned.append(frames_ready)
            camera.cancel_on_stop(frames_ready)
            camera_done = TransitionStatus(
                cam.acquire,
                transitions=[1, 0],
                run=False,
                timeout=timeout,
                description="Camera burst complete",
            )
            owned.append(camera_done)
            camera.cancel_on_stop(camera_done)
            acquired = all_statuses((frames_ready, camera_done))
            with self._capture_lock:
                camera.check_cancelled()
                cam.acquire.put(1, wait=False, timeout=io)
            return acquired

        except Exception:
            release_statuses(owned, reason="Camera burst startup interrupted")
            raise

    def _drain_rois(self) -> StatusBase:
        """
        Stop streaming, validate a fixed async total and wait for all ROI buffers to drain.
        """
        camera = self._camera
        camera.check_cancelled()
        self.stop_streaming()
        if self._async_frames is not None:
            received = (
                int(camera.cam.array_counter.get(timeout=camera.io_timeout, use_monitor=False))
                - camera._frame_origin
            )
            if received < self._async_frames:
                raise RuntimeError(
                    f"Fixed async acquisition received {received} frames, "
                    f"expected {self._async_frames}"
                )
        return all_statuses(roi.drain_capture(camera=camera) for roi in self.get_rois())

    def _publish_rois(self) -> None:
        """
        Publish drained results before completing acquisition; baseline emits one value.
        """
        camera = self._camera
        camera.check_cancelled()
        with self._capture_lock:
            for roi in self.get_rois():
                roi.publish_capture(
                    camera=camera,
                    source_path=roi.dotted_name,
                    group=self._correlation_group,
                    frame_origin=camera._frame_origin,
                    single_value=camera.readout_priority == "baseline",
                    average_frames=self._software_trigger,
                )

    def complete_camera(self) -> StatusBase:
        """
        Finish camera input, drain accepted ROI frames and publish remaining results.

        Select how camera input finishes:

        - Fixed async acquisition: wait for the configured input to finish.
        - Continuous async acquisition: request camera stop.
        - Pending startup or software burst: return its existing operation status.

        Fixed async input is allowed to finish its configured count naturally.
        Continuous async input is stopped here. Both wait for camera idle before
        draining results; fixed async acquisitions reject a short final count.

        Once input finishes:

        1. Detach streaming watchers.
        2. Drain the ROI plugins using the actual camera and Stats counters.
        3. Publish remaining frames and close the optional HDF5 file.

        Returns:
            Status covering camera completion, ROI drain and final publication. If a
            startup or burst operation is still pending, return that operation's status.
            The acquisition_timeout bounds waiting for camera input to stop.

        Raises:
            Exception: A previously recorded streaming failure is raised immediately.
            Timeout, drain and publication failures are reported
            through the returned status. Cleanup stops camera and ROI input on failure.
        """
        if self._acquisition_status is not None and not self._acquisition_status.done:
            if self._software_trigger:
                return self.complete_hdf5(self._acquisition_status)
            return self._acquisition_status
        camera, cam = self._camera, self._camera.cam
        if self._stream_error is not None:
            raise self._stream_error
        camera_done = CompareStatus(
            cam.acquire,
            0,
            run=True,
            timeout=camera.acquisition_timeout,
            description="Camera input finished",
        )
        camera.cancel_on_stop(camera_done)
        result = self.complete_hdf5(self._drain_and_publish_after(camera_done))
        with self._capture_lock:
            if result.done and not result.success:
                return result  # Cleanup has already retained the original failure.
            camera.check_cancelled()
            self._acquisition_status = result
        if not self._software_trigger and self._async_frames is None:
            try:
                with self._capture_lock:
                    camera.check_cancelled()
                    cam.acquire.put(0, wait=False, timeout=camera.io_timeout)
            except Exception as error:  # noqa: BLE001 - forward stop failures.
                result.set_exception(error)
        return result

    def _drain_and_publish_after(self, acquired: StatusBase) -> SequenceStatus:
        """
        Include Stats drain and publication after a camera completion status.
        """
        return SequenceStatus(
            self._camera,
            steps=[lambda: acquired, self._drain_rois, self._publish_rois],
            on_failure=self._cleanup_failed_acquisition,
            description="Camera ROI results published",
        )

    def _cleanup_failed_acquisition(self, error: Exception) -> None:
        """
        Stop hardware and preserve the original failure if shutdown also fails.
        """
        try:
            with self._camera._shutdown_scope(self._capture_lock):
                try:
                    if not self._camera.destroyed:
                        self._camera.stop()
                except Exception as cleanup_error:  # noqa: BLE001 - retain acquisition failure.
                    error.add_note(f"Camera stop also failed: {cleanup_error!r}")
        except DeviceStoppedError:
            return  # The interrupting transition owns hardware shutdown.

    ########################################
    #     AD live acquisition methods      #
    ########################################

    def start_live(self) -> CompareStatus | None:
        """
        Apply selected live timing and start continuous internal acquisition.

        Enable camera array callbacks and the image plugin, install the running
        subscription before Acquire and register it for cancellation. This method
        uses bounded configuration writes. The IOC owns ZMQ publication; optional
        Redis snapshots are handled by the live preview timer.

        Returns:
            Startup acknowledgement status, or None when live mode is disabled.

        Raises:
            ValueError: The selected live timing is invalid.
        """
        camera = self._camera
        if not camera.live_enabled.get():
            return None
        with self._capture_lock:
            camera.check_cancelled()
            self.stop_camera()
        exposure, period = self.live_timing()
        cam, io = camera.cam, camera.io_timeout
        settings = [
            (cam.acquire_time, exposure),
            (cam.acquire_period, period),
            (cam.image_mode, "Continuous"),
            (cam.array_callbacks, 1),
        ]
        if getattr(cam, "trigger_mode", None) is not None:
            settings.append((cam.trigger_mode, camera.internal_trigger_mode.value))
        if camera.image is not None:
            settings.append((camera.image.enable, "Enable"))
        for signal, value in settings:
            # Stop and each live command share one lock. The startup context check
            # rejects obsolete writes, including when a newer session is already live.
            with self._capture_lock:
                camera.check_cancelled()
                signal.put(value, wait=True, timeout=io)
        running = CompareStatus(
            cam.acquire, 1, run=False, timeout=io, description="Camera live acquisition running"
        )
        self._camera.cancel_on_stop(running)
        with self._capture_lock:
            self._camera.check_cancelled()
            cam.acquire.put(1, wait=False, timeout=io)
            self._pre_scan_timing = None
        return running

    def stop_live(self) -> None:
        """
        Stop live input and acknowledge camera/ROI shutdown.

        Called from on_live_mode_stops. Uses the same
        shutdown sequence as scan interruption; does not resume acquisition or
        reconfigure the IOC's ZMQ publisher. Shutdown errors propagate to the caller.
        """
        self.stop_camera()

    ########################################
    #  AD capture and publication methods  #
    ########################################

    def start_streaming(self) -> None:
        """
        Publish ROI results as accepted Stats frame counters advance.

        Each fixed buffer starts at zero and retains earlier samples while input
        continues. Watch its index and publish the available common waveform prefix.
        Selected ROI data limits async acquisition to the smallest armed buffer for
        the whole scan; a camera-counter subscription stops and fails acquisition if
        that limit is exceeded, even after the Stats buffer has stopped advancing.
        Cameras without selected ROI outputs have no ROI sample limit. There is no
        acquisition polling task. stop_streaming releases all subscriptions.
        """
        self.stop_streaming()
        self._stream_error = None
        rois = [roi for roi in self.get_rois() if roi._capture_outputs]
        if rois:
            camera = self._camera
            limit = min(
                int(roi.stats1.ts_num_points.get(timeout=camera.io_timeout)) for roi in rois
            )
            exceeded = SubscriptionStatus(
                camera.cam.array_counter,
                lambda *, value, **_: int(value) - camera._frame_origin > limit,
                run=True,
                settle_time=0.001,
                description="Async ROI scan sample limit exceeded",
            )
            self._stream_limit_status = exceeded

            def fail_at_limit(status):
                with self._capture_lock:
                    if self._stream_limit_status is not status:
                        return
                    self._stream_error = RuntimeError(
                        f"Async ROI scan exceeds IOC buffer capacity ({limit} samples). "
                        "Reduce the number of frames per scan or disable ROI outputs."
                    )
                camera.stop()

            exceeded.add_callback(fail_at_limit)
        for roi in rois:
            self._watch_roi(roi)

    def _watch_roi(self, roi: ADROIProcessing) -> None:
        camera = self._camera
        # A small settle time puts readout on the status completion thread,
        # rather than performing CA reads inside the EPICS monitor callback.
        changed = SubscriptionStatus(
            roi.stats1.ts_current_index,
            lambda *, value, **_: int(value) > roi._capture_offset,
            run=True,
            settle_time=0.001,
            description="New ROI frames available",
        )
        self._stream_statuses[roi] = changed

        def publish(status):
            try:
                with self._capture_lock:
                    if self._stream_statuses.get(roi) is not status:
                        return
                    status.wait(timeout=0)
                    camera.check_cancelled()
                    roi.publish_capture(
                        camera=camera,
                        source_path=roi.dotted_name,
                        group=self._correlation_group,
                        frame_origin=camera._frame_origin,
                        check_overflow=True,
                    )
                    self._watch_roi(roi)
            except Exception as error:  # noqa: BLE001 - report errors through acquisition statuses.
                with self._capture_lock:
                    if self._stream_error is None:
                        self._stream_error = error
                camera.stop()

        changed.add_callback(publish)

    def stop_streaming(self) -> None:
        """
        Detach streaming statuses and finish an in-flight publication.
        """
        with self._capture_lock:
            statuses = list(self._stream_statuses.values())
            self._stream_statuses.clear()
            if self._stream_limit_status is not None:
                statuses.append(self._stream_limit_status)
                self._stream_limit_status = None
            release_statuses(statuses, reason="ROI streaming stopped")

    ########################################
    #          AD preview methods          #
    ########################################

    def publish_previews(self) -> None:
        """
        Optionally read IOC-oriented values and update preview signals in Redis.
        """
        camera = self._camera
        if not camera._redis_preview_due():
            return
        io = camera.io_timeout
        if camera.image is None:
            return
        identifier = int(camera._read_preview_signal(camera.image.unique_id))
        if identifier == self._last_preview_id:
            return
        width = int(camera._read_preview_signal(camera.image.array_size.width))
        height = int(camera._read_preview_signal(camera.image.array_size.height))
        if width <= 0 or height <= 0:
            return
        color_signal = getattr(camera.image, "color_mode", None)
        color = camera._read_preview_signal(color_signal) if color_signal is not None else 0
        if isinstance(color, str) and color.isdecimal():
            color = int(color)
        if isinstance(color, str):
            color = {"Mono": 0, "Bayer": 1, "RGB1": 2, "RGB2": 3, "RGB3": 4}.get(color, color)
        depth = int(camera._read_preview_signal(camera.image.array_size.depth))
        if color == 2:
            if width != 3:
                raise ValueError("RGB1 requires a three-channel first dimension")
            width, height = (height, depth)
        elif color == 3:
            if height != 3:
                raise ValueError("RGB2 requires a three-channel second dimension")
            height = depth
        elif color == 4 and depth != 3:
            raise ValueError("RGB3 requires a three-channel third dimension")
        if width <= 0 or height <= 0:
            return
        flat = np.asarray(camera._read_preview_signal(camera.image.array_data))
        channels = 3 if color in (2, 3, 4) else 1
        size = width * height * channels
        if flat.size < size:
            raise RuntimeError("AD image is shorter than its declared dimensions")
        if color in (0, 1):
            data = flat[:size].reshape(height, width)
        elif color == 2:
            data = flat[:size].reshape(height, width, 3)
        elif color == 3:
            data = flat[:size].reshape(height, 3, width).transpose(0, 2, 1)
        elif color == 4:
            data = flat[:size].reshape(3, height, width).transpose(1, 2, 0)
        else:
            raise NotImplementedError(f"Unsupported AD ColorMode: {color!r}")
        if int(camera._read_preview_signal(camera.image.unique_id)) != identifier:
            return
        timestamp = float(camera.image.array_data.timestamp)
        previews = [CameraPreview("preview", data.copy(), identifier, timestamp, oriented=True)]
        for roi in self.get_rois():
            if not roi.active.get():
                continue
            values, names = roi.read_preview_values(io_timeout=io, stop_event=camera._poll_stop)
            previews.append(
                CameraPreview(
                    f"{roi.dotted_name}.preview",
                    values,
                    identifier,
                    timestamp,
                    {"outputs": names},
                    oriented=True,
                )
            )
        self._last_preview_id = identifier

        for preview in previews:
            if camera._poll_stop.is_set():
                return
            signal = rgetattr(camera, preview.signal)
            message = messages.DevicePreviewMessage(
                device=camera.name,
                signal=preview.signal,
                data=preview.data,
                metadata={
                    **preview.metadata,
                    "timestamp": preview.timestamp,
                    "frame_id": preview.frame_id,
                },
            )
            signal.put(message, oriented=True)

    ########################################
    #         AD shutdown methods          #
    ########################################

    def stop_camera(self, *, preserve_acquisition_owner: bool = False) -> None:
        """
        Stop camera input and every ROI capture, acknowledging each shutdown.

        Cancel registered status objects, request camera stop and then stop each ROI
        independently. Attempt all shutdowns even if one fails, then raise the first
        error. ROI shutdown releases only capture-owned blocking; scan locks remain. Called during
        connection setup and normal lifecycle hooks. Serialize hardware stop with the
        final acquisition startup check/write so an interrupted startup cannot restart input.

        Args:
            preserve_acquisition_owner (bool): Reserve shutdown for the current scan
                during unstage. Reject an obsolete caller and block replacement setup
                until shutdown finishes. Forced stop/destroy paths leave this False.
        """
        if preserve_acquisition_owner:
            with self._camera._shutdown_scope(self._capture_lock, allow_stopped=True):
                self.stop_camera()
            return
        errors = []
        try:
            self.stop_streaming()
        except Exception as error:  # noqa: BLE001 - still stop input after watcher cleanup fails.
            errors.append(error)
        try:
            self._camera._stop_stoppable_status_objects()
        except Exception as error:  # noqa: BLE001 - attempt every shutdown.
            errors.append(error)
        io = self._camera.io_timeout
        if self._camera.cam is not None:
            acquire = self._camera.cam.acquire
            stopped: CompareStatus | None = None
            try:
                with self._capture_lock:
                    stopped = CompareStatus(
                        acquire, 0, run=False, timeout=io, description="AD stop acknowledged"
                    )
                    acquire.put(0, wait=False, timeout=io)
                # An unchanged idle record need not emit another monitor event.
                # Only a fresh read after the command may acknowledge that case.
                if int(acquire.get(timeout=io, use_monitor=False)) == 0 and not stopped.done:
                    try:
                        stopped.set_finished()
                    except InvalidState:
                        pass  # The idle monitor completed concurrently.
                stopped.wait(timeout=io)
                if int(acquire.get(timeout=io, use_monitor=False)) != 0:
                    raise RuntimeError("Camera input did not stop after the stop command")
            except Exception as error:  # noqa: BLE001 - attempt every shutdown.
                errors.append(error)
            finally:
                if stopped is not None:
                    try:
                        release_statuses((stopped,), reason="AD stop aborted")
                    except Exception as error:  # noqa: BLE001 - still stop ROI capture and writing.
                        errors.append(error)
        for roi in self.get_rois():
            try:
                roi.stop_capture(io_timeout=io)
            except Exception as error:  # noqa: BLE001 - stop every ROI before reporting failure.
                errors.append(error)
        try:
            self.hdf5.stop()
        except Exception as error:  # noqa: BLE001 - attempt every shutdown.
            errors.append(error)
        if errors:
            raise errors[0]

    ########################################
    #           HDF5 file writing          #
    ########################################

    def prime_hdf5(self) -> None:
        """
        Prime a cold enabled HDF5 writer with one unsaved internal frame.

        The helper restores controller settings before returning and keeps the
        acquisition component's command lock and lifecycle ownership checks.
        """
        self.hdf5.prime()

    def stage_hdf5(self) -> None:
        """
        Configure and arm the optional HDF5 file before scan input starts.
        """
        self.hdf5.stage(ioc_path=self.hdf5_ioc_path)

    def hdf5_ioc_path(self, path: str) -> str:
        """
        Translate a BEC filename through the configured IOC directory mapping.

        Args:
            path (str): BEC-visible filename used in file events.

        Returns:
            str: IOC-visible filename, preserving whole directory-prefix matching.
        """
        return self.hdf5.ioc_path(path)

    def complete_hdf5(self, acquisition: StatusBase) -> StatusBase:
        """
        Close and validate the optional scan file after acquisition finishes.

        Args:
            acquisition (StatusBase): Camera/ROI completion to await before the writer.

        Returns:
            StatusBase: Acquisition status unchanged when no file is owned; otherwise
                the shared sequence covering writer drain, closure and final file event.
                The returned status owns failure cleanup, including command failures
                forwarded by complete_camera(). Overrides must preserve this contract.
        """
        return self.hdf5.complete(
            acquisition, software_trigger=self._software_trigger, async_frames=self._async_frames
        )

    ########################################
    #       Configuration validation       #
    ########################################

    @staticmethod
    def _validate_timing(exposure: Any, period: Any) -> tuple[float, float]:
        """
        Convert exposure/period to seconds and validate their relationship.

        Returns:
            Finite positive exposure and a period at least as long as the exposure.

        Raises:
            ValueError: Values are nonfinite, nonpositive or period is too short.
            TypeError: A value cannot be converted to a floating-point number.
        """
        exposure, period = float(exposure), float(period)
        if not isfinite(exposure) or not isfinite(period) or exposure <= 0 or period < exposure:
            raise ValueError("Timing requires finite positive exposure and period >= exposure")
        return exposure, period

    @staticmethod
    def _validate_frames(frames: Any) -> int:
        """
        Return a positive integer frame count, rejecting booleans.

        Raises:
            ValueError: The value is not an integer greater than zero.
        """
        if type(frames) is not int or frames < 1:
            raise ValueError("frames_per_trigger must be a positive integer")
        return frames
