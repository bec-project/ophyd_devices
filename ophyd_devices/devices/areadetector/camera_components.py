"""Shared AreaDetector timing, acquisition and publication operations."""

from functools import reduce
from math import isfinite
from operator import and_
from pathlib import PurePosixPath
from threading import RLock
from typing import Any, Generic, TypeVar, cast
from uuid import uuid4

import numpy as np
from bec_lib import messages
from bec_lib.utils.rpc_utils import rgetattr
from ophyd.utils.errors import InvalidState, StatusTimeoutError, WaitTimeoutError

from ophyd_devices.devices.areadetector.plugins import HDF5Plugin_V35, ImagePlugin_V35
from ophyd_devices.interfaces.base_classes.camera_base import AcquisitionMode, AcquisitionSource
from ophyd_devices.interfaces.protocols.ad_camera import ADCamera
from ophyd_devices.utils.bec_roi_signals.ad_roi_signal import ADROIProcessing
from ophyd_devices.utils.camera_preview import CameraPreview
from ophyd_devices.utils.psi_device_base_utils import (
    DeviceStatus,
    StatusBase,
    SubscriptionStatus,
    TransitionStatus,
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
    HDF5 plugin whose preparation and capture are owned by ADCameraComponents.

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
        self._hdf5_path: str | None = None
        self._hdf5_completion: StatusBase | None = None

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
            camera.cam.num_images.get(timeout=camera.io_timeout, use_monitor=True)
        )

    def _read_controller_timing(self) -> tuple[float, float]:
        """
        Read and validate the controller's current exposure and period.
        """
        cam, io = self._camera.cam, self._camera.io_timeout
        return self._validate_timing(
            cam.acquire_time.get(timeout=io, use_monitor=True),
            cam.acquire_period.get(timeout=io, use_monitor=True),
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
            frames = camera.cam.num_images.get(timeout=camera.io_timeout, use_monitor=True)
        exposure, period = self._validate_timing(exposure, period)
        frames = self._validate_frames(frames)
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
        self._async_frames = None
        capture_capacity = camera.async_frame_limit
        if (
            group == "async"
            and AcquisitionMode(camera.acquisition_mode.get()) == AcquisitionMode.FIXED
        ):
            if camera.use_scan_timing.get():
                points = self._validate_frames(camera._scan_message.info["num_points"])
                self._async_frames = points * camera.frames_per_trigger
            else:
                self._async_frames = camera.frames_per_trigger  # Resolved controller NumImages.
            if capture_capacity is not None:
                self._validate_frames(capture_capacity)
                if self._async_frames > capture_capacity and any(
                    roi.active.get() and roi.selected_operations.get() for roi in self.get_rois()
                ):
                    raise ValueError("Fixed async acquisition exceeds async_frame_limit")
            capture_capacity = self._async_frames
        if external_trigger and (
            camera.external_trigger_mode is None or getattr(cam, "trigger_mode", None) is None
        ):
            raise NotImplementedError(
                "External triggering requires a configured camera trigger input"
            )
        self.stop_camera()
        self._software_trigger = software_trigger
        self._correlation_group = group
        self._acquisition_status = None
        if self._pre_scan_timing is None:
            self._pre_scan_timing = self._read_controller_timing()
        cam.acquire_time.put(camera.exposure, wait=True, timeout=io)
        cam.acquire_period.put(camera.period, wait=True, timeout=io)
        if software_trigger or self._async_frames is not None:
            count = camera.frames_per_trigger if software_trigger else self._async_frames
            cam.num_images.put(count, wait=True, timeout=io)
            cam.image_mode.put("Multiple", wait=True, timeout=io)
        else:
            cam.image_mode.put("Continuous", wait=True, timeout=io)
        cam.array_callbacks.put(1, wait=True, timeout=io)
        if getattr(cam, "trigger_mode", None) is not None:
            cam.trigger_mode.put(
                (
                    camera.external_trigger_mode
                    if external_trigger
                    else camera.internal_trigger_mode
                ).value,
                wait=True,
                timeout=io,
            )
        if camera.image is not None:
            camera.image.enable.put("Disable", wait=True, timeout=io)
        camera.session_id = uuid4().hex
        self._stream_error = None
        camera._frame_origin = int(cam.array_counter.get(timeout=io, use_monitor=False))
        for roi in self.get_rois():
            roi._capture_outputs = {}
            roi.update_received.block_updates(owner="capture")
        self.stage_hdf5()
        if software_trigger:
            return None

        startup = StatusBase(camera, description="Camera scan input armed/running")
        self._acquisition_status = startup
        rois_armed = self.arm_rois(capacity=capture_capacity)

        def start_input(rois_armed):
            try:
                rois_armed.wait(timeout=0)
                camera.check_cancelled()
                self.start_streaming()
                started = SubscriptionStatus(
                    cam.acquire,
                    lambda *, value, **_: value in (1, "Acquire"),
                    run=False,
                    timeout=io,
                    description="Camera scan input started",
                )
                camera.cancel_on_stop(started)
                started.add_callback(finish_startup)
                # Registration can synchronously deliver cancellation. Serialize the
                # final check/write with hardware stop so Acquire=1 cannot follow a
                # completed stop, including when cancellation comes from another thread.
                with self._capture_lock:
                    if startup.done:
                        return
                    camera.check_cancelled()
                    cam.acquire.put(1, wait=False, timeout=io)
            except Exception as error:  # noqa: BLE001 - forward arming failures.
                self._fail_acquisition(startup, error)

        def finish_startup(input_started):
            try:
                input_started.wait(timeout=0)
                camera.check_cancelled()
                startup.set_finished()
            except Exception as error:  # noqa: BLE001 - forward startup failures.
                self._fail_acquisition(startup, error)

        rois_armed.add_callback(start_input)
        return startup

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
        statuses = [
            roi.arm_capture(camera=self._camera, capacity=capacity) for roi in self.get_rois()
        ]
        if statuses:
            return reduce(and_, statuses)
        ready = StatusBase()
        ready.set_finished()
        return ready

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
        camera, cam = self._camera, self._camera.cam
        if not self._software_trigger:
            return None  # Async input is already running; do not retrigger it.
        if self._acquisition_status is not None and not self._acquisition_status.done:
            raise RuntimeError("Camera acquisition is already in progress")
        io = camera.io_timeout
        timeout = max(
            camera.acquisition_timeout, camera.period * camera.frames_per_trigger * 2 + io
        )
        acquired = StatusBase(camera, description="Camera burst acquired")
        published = self._drain_and_publish_after(acquired)
        self._acquisition_status = published
        rois_armed = self.arm_rois(capacity=camera.frames_per_trigger)

        def start_burst(rois_armed):
            if published.done:
                return
            try:
                rois_armed.wait(timeout=0)
                camera.check_cancelled()
                target = (
                    int(cam.array_counter.get(timeout=io, use_monitor=False))
                    + camera.frames_per_trigger
                )
                frames_ready = SubscriptionStatus(
                    cam.array_counter,
                    lambda *, value, **_: int(value) >= target,
                    run=True,
                    timeout=timeout,
                    description="Camera produced requested frames",
                )
                camera_done = SubscriptionStatus(
                    cam.acquire,
                    lambda *, old_value, value, **_: old_value in (1, "Acquire")
                    and value in (0, "Done"),
                    run=False,
                    timeout=timeout,
                    description="Camera burst complete",
                )
                camera.cancel_on_stop(frames_ready)
                camera.cancel_on_stop(camera_done)
                (frames_ready & camera_done).add_callback(mark_acquired)
                with self._capture_lock:
                    camera.check_cancelled()
                    cam.acquire.put(1, wait=False, timeout=io)
            except Exception as error:  # noqa: BLE001 - forward arming failures.
                if not acquired.done:
                    acquired.set_exception(error)

        def mark_acquired(burst_finished):
            if acquired.done:
                return
            try:
                burst_finished.wait(timeout=0)
                acquired.set_finished()
            except Exception as error:  # noqa: BLE001 - forward burst failures.
                acquired.set_exception(error)

        rois_armed.add_callback(start_burst)
        return published

    def complete_camera(self) -> StatusBase:
        """
        Finish camera input, drain accepted ROI frames and publish remaining results.

        Select how camera input finishes:

        - External or internal acquisition: request camera stop.
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
        camera_done = SubscriptionStatus(
            cam.acquire,
            lambda *, value, **_: value in (0, "Done"),
            run=True,
            timeout=camera.acquisition_timeout,
            description="Camera input finished",
        )
        camera.cancel_on_stop(camera_done)
        result = self.complete_hdf5(self._drain_and_publish_after(camera_done))
        self._acquisition_status = result
        if not self._software_trigger and self._async_frames is None:
            try:
                camera.check_cancelled()
                cam.acquire.put(0, wait=False, timeout=camera.io_timeout)
            except Exception as error:  # noqa: BLE001 - forward stop failures.
                self._fail_acquisition(result, error)
        return result

    def _drain_and_publish_after(self, acquired: StatusBase) -> StatusBase:
        """
        Include Stats drain and publication after a camera completion status.
        """
        camera = self._camera
        # No timeout thread here: the constituent subscription statuses each have
        # a bounded timeout, and errors are forwarded after hardware cleanup.
        published = StatusBase(camera, description="Camera ROI results published")

        def drain(input_finished):
            if published.done:
                return
            try:
                input_finished.wait(timeout=0)
                camera.check_cancelled()
                self.stop_streaming()
                if self._async_frames is not None:
                    received = (
                        int(
                            camera.cam.array_counter.get(
                                timeout=camera.io_timeout, use_monitor=False
                            )
                        )
                        - camera._frame_origin
                    )
                    if received < self._async_frames:
                        raise RuntimeError(
                            f"Fixed async acquisition received {received} frames, "
                            f"expected {self._async_frames}"
                        )
                drains = [roi.drain_capture(camera=camera) for roi in self.get_rois()]
                drained = reduce(and_, drains) if drains else input_finished
                drained.add_callback(publish)
            except Exception as error:  # noqa: BLE001 - report errors through acquisition statuses.
                self._fail_acquisition(published, error)

        def publish(drained):
            if published.done:
                return
            try:
                drained.wait(timeout=0)
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
                published.set_finished()
            except Exception as error:  # noqa: BLE001 - report errors through acquisition statuses.
                self._fail_acquisition(published, error)

        acquired.add_callback(drain)
        return published

    def _fail_acquisition(self, result: StatusBase, error: Exception) -> None:
        """
        Stop hardware before reporting an acquisition or publication failure.
        """
        if result.done:
            return
        try:
            if not self._camera.destroyed:
                self._camera.stop()
        except Exception as cleanup_error:  # noqa: BLE001 - retain the acquisition error.
            error.add_note(f"Camera stop also failed: {cleanup_error!r}")
        finally:
            if not result.done:
                result.set_exception(error)

    ########################################
    #     AD live acquisition methods      #
    ########################################

    def start_live(self) -> SubscriptionStatus | None:
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
        if not self._camera.live_enabled.get():
            return None
        self.stop_camera()
        exposure, period = self.live_timing()
        cam, io = self._camera.cam, self._camera.io_timeout
        cam.acquire_time.put(exposure, wait=True, timeout=io)
        cam.acquire_period.put(period, wait=True, timeout=io)
        cam.image_mode.put("Continuous", wait=True, timeout=io)
        cam.array_callbacks.put(1, wait=True, timeout=io)
        if getattr(cam, "trigger_mode", None) is not None:
            cam.trigger_mode.put(self._camera.internal_trigger_mode.value, wait=True, timeout=io)
        if self._camera.image is not None:
            self._camera.image.enable.put("Enable", wait=True, timeout=io)
        running = SubscriptionStatus(
            cam.acquire,
            lambda *, value, **_: value in (1, "Acquire"),
            run=False,
            timeout=io,
            description="Camera live acquisition running",
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
            for status in statuses:
                if not status.done:
                    try:
                        status.set_exception(RuntimeError("ROI streaming stopped"))
                    except InvalidState:
                        pass  # Completion has already been scheduled by the index update.

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

    def stop_camera(self) -> None:
        """
        Stop camera input and every ROI capture, acknowledging each shutdown.

        Cancel registered status objects, request camera stop and then stop each ROI
        independently. Attempt all shutdowns even if one fails, then raise the first
        error. ROI shutdown releases only capture-owned blocking; scan locks remain. Called during
        connection setup and normal lifecycle hooks. Serialize hardware stop with the
        final acquisition startup check/write so an interrupted startup cannot restart input.
        """
        self.stop_streaming()
        self._camera._stop_stoppable_status_objects()
        io = self._camera.io_timeout
        errors = []
        signals = (
            [(self._camera.cam.acquire, self._camera.cam.acquire)]
            if self._camera.cam is not None
            else []
        )
        for command, readback in signals:
            stopped = SubscriptionStatus(
                readback,
                lambda *, value, **_: value in (0, "Done"),
                run=True,
                timeout=io,
                description="AD stop acknowledged",
            )
            try:
                with self._capture_lock:
                    command.put(0, wait=False, timeout=io)
                stopped.wait(timeout=io)
            except Exception as error:  # noqa: BLE001 - report failure on the operation status.
                errors.append(error)
            finally:
                if not stopped.done:
                    stopped.set_exception(RuntimeError("AD stop aborted"))
        for roi in self.get_rois():
            try:
                roi.stop_capture(io_timeout=io)
            except Exception as error:  # noqa: BLE001 - stop every ROI before reporting failure.
                errors.append(error)
        hdf5 = getattr(self._camera, "hdf5", None)
        if hdf5 is not None:
            try:
                hdf5.capture.put(0, wait=True, timeout=io)
            except Exception as error:  # noqa: BLE001 - finish cleanup before raising.
                errors.append(error)
            finally:
                self._publish_hdf5_event(successful=False)
        if errors:
            raise errors[0]

    ########################################
    #           HDF5 file writing          #
    ########################################

    def prime_hdf5(self) -> None:
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
        if hdf5 is None or not camera.save_frame_data.get():
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
            camera.check_cancelled()
            cam.acquire.put(0, wait=True, timeout=io)
            hdf5.capture.put(0, wait=True, timeout=io)
            for signal, value in settings:
                signal.put(value, wait=True, timeout=io)
            received = SubscriptionStatus(
                hdf5.array_size.width,
                lambda *, value, **_: int(value) > 0,
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
            for status in subscriptions:
                if not status.done:
                    try:
                        status.set_exception(RuntimeError("HDF5 priming interrupted"))
                    except InvalidState:
                        pass  # Completion was already scheduled by its subscription.
            # Stop first. Always restore with writes because monitor caches may
            # not yet contain the temporary values applied above.
            errors = []
            for signal, value in [(cam.acquire, 0), *reversed(originals)]:
                try:
                    signal.put(value, wait=True, timeout=io)
                except Exception as error:  # noqa: BLE001 - attempt all restores.
                    errors.append(error)
            if errors:
                if failure is not None:
                    failure.add_note(f"Restoring HDF5 priming settings also failed: {errors!r}")
                else:
                    raise ExceptionGroup("HDF5 priming restoration failed", errors)

    def stage_hdf5(self) -> None:
        """
        Configure and arm the optional ``hdf5`` plugin when save_frame_data is enabled.

        1. Obtain the scan filename from BEC, without creating directories locally.
        2. Configure one stream file with unlimited capture and lazy opening.
        3. Announce the pending file, arm capture and acknowledge counter reset.

        Before camera input starts, require a fresh zero NumCaptured readback and
        a monitor cache that has caught up to the new capture. Previous-file counts
        must never satisfy completion of the new file.

        Translate BEC directory prefixes with hdf5_path_mapping when the IOC uses
        another mount point. File events always use the BEC path. Preserve its input
        port and XML layout. Capture remains armed across software bursts; complete
        closes it after all accepted frames arrive, including unknown-length scans.
        The saving preference is sampled at stage: disabling it during an active
        capture does not skip file closure or its final event. Previews and ROI
        publication are independent of this preference.
        """
        camera = self._camera
        hdf5 = getattr(camera, "hdf5", None)
        if hdf5 is None or not camera.save_frame_data.get():
            return
        io = camera.io_timeout
        if np.asarray(hdf5.array_size.get(timeout=io, use_monitor=True)).sum() == 0:
            raise RuntimeError("HDF5 is unprimed; call prime_hdf5() before arming scan capture")
        path = camera.file_utils.get_full_path(
            scan_status_msg=camera._scan_message, name=camera.name, create_dir=False
        )
        filename = PurePosixPath(self.hdf5_ioc_path(path))
        hdf5.capture.put(0, wait=True, timeout=io)
        hdf5.enable.put(1, wait=True, timeout=io)
        hdf5.file_path.put(f"{filename.parent}/", wait=True, timeout=io)
        hdf5.file_name.put(filename.name, wait=True, timeout=io)
        hdf5.file_template.put("%s%s", wait=True, timeout=io)
        hdf5.file_write_mode.put(2, wait=True, timeout=io)  # Stream
        hdf5.auto_increment.put(0, wait=True, timeout=io)
        hdf5.auto_save.put(0, wait=True, timeout=io)
        hdf5.lazy_open.put(1, wait=True, timeout=io)
        hdf5.num_capture.put(0, wait=True, timeout=io)  # Until complete/stop
        if hdf5.file_path_exists.get(timeout=io) not in (1, "Yes"):
            raise RuntimeError(
                f"HDF5 output directory is unavailable to the IOC: {filename.parent}"
            )
        # Record ownership before arming so failed startup can announce failure.
        self._hdf5_path = path
        self._hdf5_completion = None
        camera.file_event.put(
            file_path=path,
            done=False,
            successful=False,
            hinted_h5_entries={"data": "/entry/data/data"},
        )
        reset = SubscriptionStatus(
            hdf5.num_captured,
            lambda *, value, **_: int(value) == 0,
            run=False,
            timeout=io,
            description="HDF5 new capture counter reset",
        )
        camera.cancel_on_stop(reset)
        try:
            hdf5.capture.put(1, wait=True, timeout=io)
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
        except Exception as error:
            for cleanup in (
                lambda: hdf5.capture.put(0, wait=True, timeout=io),
                lambda: self._publish_hdf5_event(successful=False),
            ):
                try:
                    cleanup()
                except Exception as cleanup_error:  # noqa: BLE001 - preserve arming failure.
                    error.add_note(f"HDF5 arming cleanup also failed: {cleanup_error!r}")
            if isinstance(error, (WaitTimeoutError, StatusTimeoutError)):
                raise TimeoutError("HDF5 capture counter reset was not acknowledged") from error
            raise
        finally:
            if not reset.done:
                try:
                    reset.set_exception(RuntimeError("HDF5 capture arming aborted"))
                except InvalidState:
                    pass

    def hdf5_ioc_path(self, path: str) -> str:
        """
        Translate a BEC filename to the IOC's mount using directory prefixes.

        An empty mapping leaves the filename unchanged. With a mapping configured,
        require a matching absolute directory prefix; the most specific prefix wins.
        Match whole path components so /data never matches /database.
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

    def complete_hdf5(self, acquisition: StatusBase) -> StatusBase:
        """
        Close the optional scan file after acquisition and queued writes finish.

        1. Wait for camera/ROI completion.
        2. For fixed acquisition, wait for every expected frame to reach the writer.
           Continuous async acquisition has no exact frame-count requirement.
        3. Stop capture and wait for capture and file writing to become idle.
        4. Read final writer status and frame counts directly from the IOC, then
           publish the final file event. Read the current error message on failure.

        Monitor notifications may lag behind file closure. Final validation must not
        reuse cached counts or writer status, even after earlier readiness checks.

        Return a cancellable status. Failed acquisition, missing frames and writer
        errors fail completion and publish an unsuccessful file event. No polling
        thread is used. Fixed acquisition requires the plugin to receive every
        expected frame; continuous async acquisition does not enforce an exact count.
        """
        camera = self._camera
        hdf5 = getattr(camera, "hdf5", None)
        if hdf5 is None or self._hdf5_path is None:
            return acquisition
        if self._hdf5_completion is not None:
            return self._hdf5_completion
        finished = StatusBase(camera, description="HDF5 scan file closed")
        self._hdf5_completion = finished
        # Constituent statuses are cancellable; finish this status only after
        # cleanup has emitted the final file event.

        def drain_file(input_finished):
            if finished.done:
                return
            try:
                input_finished.wait(timeout=0)
                camera.check_cancelled()
                if not self._software_trigger and self._async_frames is None:
                    close_file(input_finished)  # Open-ended acquisition has no exact count.
                    return
                frames = self._async_frames
                if frames is None:
                    frames = (
                        int(
                            camera.cam.array_counter.get(
                                timeout=camera.io_timeout, use_monitor=False
                            )
                        )
                        - camera._frame_origin
                    )
                captured = SubscriptionStatus(
                    hdf5.num_captured,
                    lambda *, value, **_: int(value) >= frames,
                    run=False,
                    timeout=camera.acquisition_timeout,
                    description="HDF5 accepted frames written",
                )
                camera.cancel_on_stop(captured)
                actual = int(hdf5.num_captured.get(timeout=camera.io_timeout, use_monitor=False))
                if actual >= frames and not captured.done:
                    try:
                        captured.set_finished()
                    except InvalidState:
                        pass  # A new frame notification completed concurrently.
                captured.add_callback(close_file)
            except Exception as error:  # noqa: BLE001 - forward failure through completion.
                self._fail_acquisition(finished, error)

        def close_file(frames_written):
            if finished.done:
                return
            try:
                frames_written.wait(timeout=0)
                camera.check_cancelled()
                idle = SubscriptionStatus(
                    hdf5.capture,
                    lambda *, value, **_: value in (0, "Done"),
                    run=False,
                    timeout=camera.acquisition_timeout,
                    description="HDF5 capture closed",
                ) & SubscriptionStatus(
                    hdf5.write_file,
                    lambda *, value, **_: value in (0, "Done"),
                    run=True,
                    timeout=camera.acquisition_timeout,
                    description="HDF5 writer idle",
                )
                camera.cancel_on_stop(idle)
                idle.add_callback(publish_file)
                hdf5.capture.put(0, wait=False, timeout=camera.io_timeout)
            except Exception as error:  # noqa: BLE001 - forward failure through completion.
                self._fail_acquisition(finished, error)

        def publish_file(writer_idle):
            if finished.done:
                return
            try:
                writer_idle.wait(timeout=0)
                camera.check_cancelled()
                io = camera.io_timeout
                write_status = hdf5.write_status.get(timeout=io, use_monitor=False)
                if write_status not in (0, "OK"):
                    message = hdf5.write_message.get(timeout=io, use_monitor=False)
                    raise RuntimeError(f"HDF5 write failed: {message}")
                captured = int(hdf5.num_captured.get(timeout=io, use_monitor=False))
                expected = self._async_frames
                if self._software_trigger:
                    expected = (
                        int(camera.cam.array_counter.get(timeout=io, use_monitor=False))
                        - camera._frame_origin
                    )
                if captured == 0:
                    raise RuntimeError("HDF5 acquisition produced no frames; no file was created")
                if expected is not None and captured < expected:
                    raise RuntimeError(
                        f"HDF5 captured {captured} frames, expected at least {expected}"
                    )
                self._publish_hdf5_event(successful=True)
                finished.set_finished()
            except Exception as error:  # noqa: BLE001 - forward failure through completion.
                self._fail_acquisition(finished, error)

        acquisition.add_callback(drain_file)
        return finished

    def _publish_hdf5_event(self, *, successful: bool) -> None:
        """
        Announce one final file event and release ownership of this scan file.
        """
        if self._hdf5_path is None:
            return
        self._camera.file_event.put(
            file_path=self._hdf5_path,
            done=True,
            successful=successful,
            hinted_h5_entries={"data": "/entry/data/data"},
        )
        self._hdf5_path = None

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
