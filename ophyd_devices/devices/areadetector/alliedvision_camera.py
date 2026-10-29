"""ADVimba camera example with explicit acquisition hooks."""

from ophyd import ADBase, Component, Kind

from ophyd_devices.devices.areadetector.cam import VimbaDetectorCam
from ophyd_devices.devices.areadetector.camera_components import ADCameraComponents, CameraImage
from ophyd_devices.devices.areadetector.configuration import configure_ad_signals
from ophyd_devices.devices.areadetector.trigger_modes import VimbaTriggerMode
from ophyd_devices.interfaces.base_classes.camera_base import CameraBase
from ophyd_devices.utils.bec_roi_signals.ad_roi_signal import ADROIProcessing
from ophyd_devices.utils.psi_device_base_utils import StatusBase, SubscriptionStatus


@configure_ad_signals
class AlliedVisionSignals(ADBase):
    """
    Complete PV layout for this IOC, including its explicit ROI/Stats pair.
    """

    # Respect Component kinds instead of ADBase's empty configuration list.
    _default_configuration_attrs = None

    # Define a CameraHDF5 component here when the IOC provides a file writer.
    hdf5 = None
    # BEC deviceConfig may map its data directories to different IOC mount points.
    hdf5_path_mapping: dict[str, str] | None = None

    cam = Component(VimbaDetectorCam, "cam1:", kind=Kind.config)
    image = Component(CameraImage, "image1:", kind=Kind.omitted)
    roi1 = Component(
        ADROIProcessing,
        "",
        roi_suffix="ROI1:",
        stats_suffix="Stats1:",
        manage_capture=False,
        active=True,
        roi_name="roi1",
        roi_config={"type": "rect", "x": 100, "y": 100, "width": 100, "height": 100},
        selected_operations=["basic_statistics"],
        kind=Kind.config,
    )


class AlliedVisionCamera(  # pyright: ignore[reportIncompatibleMethodOverride]
    CameraBase, AlliedVisionSignals
):
    """
    The full acquisition sequence is here; no acquisition super() calls.
    """

    internal_trigger_mode = VimbaTriggerMode.OFF
    external_trigger_mode: VimbaTriggerMode | None = None

    ########################################
    #  Beamline Specific Implementations   #
    ########################################

    def on_init(self) -> None:
        """
        Called when the device is initialized.

        No signals are connected at this point. If you like to
        set default values on signals, please use on_connected instead.
        """
        self.components = ADCameraComponents(self)
        self._frame_origin = 0

    def on_connected(self) -> None:
        """
        Called after the device is connected and its signals are connected.
        Default values for signals should be set here.
        """
        self.components.initialize_camera()
        self.components.stop_camera()
        for roi in self.components.get_rois():
            roi.on_connected()
        self.components.initialize_settings()
        self._live_ready = True
        if self.live_enabled.get():
            self.start_live(update_preference=False).wait(timeout=self.io_timeout)

    def on_stage(self) -> StatusBase | None:
        """
        Called while staging the device.

        Stage acquisition in this order:

        1. Pause live input without changing the user's live preference.
        2. Prime a cold HDF5 writer with an unsaved frame when saving is enabled.
        3. Resolve scan timing or retain the manual controller settings.
        4. Select the acquisition lifecycle from the readout priority.
        5. Configure camera and ROI capture and arm an optional HDF5 scan file.
        6. Return readiness; baseline acquisition runs later in on_pre_scan.

        Baseline waits for on_pre_scan after all devices have staged. Monitored
        waits for BEC triggers. Async uses acquisition_source to select internal
        clock or external pulses and acquisition_mode to select a fixed frame count
        or continuous input. It arms ROI buffers before starting input. Fixed
        acquisition finishes naturally; on_complete stops continuous input. ROI
        samples per scan must fit the IOC waveform capacity. External
        pulses must remain quiet until the returned startup status has completed.
        On-request devices retain their live behavior. Setup failures stop hardware
        before propagating to the device server. Cold HDF5 priming blocks with
        acquisition_timeout; scan acquisition remains status-based.

        Returns:
            StatusBase | None: Async/live startup readiness, or None when finite
                scan settings have been prepared without starting acquisition.
        """
        self.stop_live(update_preference=False).wait(timeout=self.io_timeout)
        try:
            if self.readout_priority == "on_request":
                return self.start_live(update_preference=False)

            self.components.prime_hdf5()
            self.components.resolve_scan_settings()
            return self.components.stage_camera()
        except Exception:
            self.stop()
            raise

    def on_unstage(self) -> StatusBase | None:
        """
        Called while unstaging the device.

        Unstage acquisition in this order:

        1. Stop the optional Redis preview timer.
        2. Cancel pending capture statuses and acknowledge camera/ROI shutdown.
        3. Resume live input only when the user has enabled it.

        Live startup applies the selected live-versus-scan timing policy and returns
        readiness. Shutdown failures propagate before live input can restart.
        """
        self.stop_polling()
        self.components.stop_camera()
        if self.live_enabled.get():
            return self.start_live(update_preference=False)
        return None

    def on_pre_scan(self) -> StatusBase | None:
        """
        Called right before the scan starts on all devices automatically.

        Acquire one finite burst for baseline priority after staging has completed.
        Publish its ROI statistics as one value per result before acknowledging
        readiness. Monitored cameras wait for BEC triggers; async input is already
        running, and on-request cameras retain their live behavior.

        Returns:
            StatusBase | None: Baseline acquisition, ROI drain and publication status,
                or None for other readout priorities. BEC waits for this status before
                executing the scan core. Failure and stop propagate through it.
        """
        if self.readout_priority == "baseline":
            return self.components.trigger_camera()
        return None

    def on_trigger(self) -> StatusBase | None:
        """
        Called when the device is triggered.

        Start one finite burst for monitored readout priority.
        Return the status covering ROI readiness, acquisition, drain and publication.
        Independent input is already armed and returns None without being retriggered.
        Baseline also returns None because its single acquisition ran in on_pre_scan.
        Synchronous setup failures stop hardware before propagating to the device server.
        """
        if self.readout_priority == "baseline":
            return None  # The single baseline acquisition already ran in on_pre_scan.
        try:
            return self.components.trigger_camera()
        except Exception:
            self.stop()
            raise

    def on_complete(self) -> StatusBase | None:
        """
        Called to inquire if a device has completed a scans.

        Wait for a pending software burst or stop independent input, then drain ROI
        capture and publish remaining results. Return the shared
        completion status so BEC waits for ROI publication and optional HDF5 file
        closure before unstaging the camera.
        On-request devices return None and keep their live behavior.
        """
        if self.readout_priority == "on_request":
            return None
        return self.components.complete_camera()

    def on_kickoff(self) -> None:
        """
        Called to kickoff a device for a fly scan. Has to be called explicitly.
        """

    def on_stop(self) -> None:
        """
        Called when the device is stopped.

        Cancel pending statuses and stop live input, scan input and ROI capture.
        """
        self.stopped = True
        try:
            self.stop_live(update_preference=False).wait(timeout=self.io_timeout)
        finally:
            self.components.stop_camera()

    def on_destroy(self) -> None:
        """
        Called when the device is destroyed. Cleanup resources here.

        Stop acquisition and the preview timer, then release live subscriptions.
        """
        self.live_enabled.unsubscribe(self._live_subscription)
        if self._live_ready:
            self.on_stop()
        else:
            self.stop_polling()

    def on_live_mode_starts(self) -> SubscriptionStatus | None:
        """
        Configure continuous internal acquisition and return startup readiness.

        Called after connection or unstage, or when live mode is enabled outside
        a scan. The IOC publishes ZMQ directly; no publisher is created here.
        """
        return self.components.start_live()

    def on_live_mode_stops(self) -> None:
        """
        Acknowledge camera and ROI shutdown when leaving live acquisition.

        Called before staging, disabling live or stopping the device. The Redis
        preview timer is already stopped before acquisition settings are changed.
        Scan completion and abort cleanup remain in on_complete and on_stop.
        """
        self.components.stop_live()

    def on_poll(self) -> None:
        """
        Publish an optional Redis preview on the live preview timer.

        No timer runs when redis_update_frequency is zero. Async ROI publication
        uses Stats subscription statuses; IOC ZMQ publication is independent.
        """
        self.components.publish_previews()
