"""Module for a simulated 1D Waveform detector, i.e. a Falcon XRF detector."""

import os
import threading
import time
import traceback
from typing import Any

import numpy as np
from bec_lib import messages
from bec_lib.endpoints import MessageEndpoints
from bec_lib.logger import bec_logger
from ophyd import Component as Cpt
from ophyd import Device, DeviceStatus, Kind, Staged
from typeguard import typechecked

from ophyd_devices.sim.sim_data import SimulatedDataWaveform
from ophyd_devices.sim.sim_signals import ReadOnlySignal, SetableSignal
from ophyd_devices.utils import bec_utils
from ophyd_devices.utils.bec_signals import AsyncSignal
from ophyd_devices.utils.errors import DeviceStopError

logger = bec_logger.logger


class AsyncUpdateSignal(SetableSignal):
    """Async updated signal, with check for async_update type."""

    def check_value(self, value, **kwargs) -> None:
        """Check the value of the async_update signal."""
        if value not in ["add_slice", "add"]:
            raise ValueError(f"Invalid async_update type: {value} for signal {self.name}")

    # FIXME: BEC issue #443 remove this method once tests in BEC are updated.
    def put(self, value: Any) -> None:
        """Put the value of the async_update signal."""
        if value in ["append", "extend"]:
            if value == "append":
                logger.warning(
                    f"Deprecated async_update of type {value} for signal {self.name}, falling back to 'add_slice'"
                )
                value = "add_slice"
            elif value == "extend":
                logger.warning(
                    f"Deprecated async_update of type {value} for signal {self.name}, falling back to 'add'"
                )
                value = "add"
        super().put(value)


class SimWaveform(Device):
    """A simulated device mimic any 1D Waveform detector.

    It's waveform is a computed signal, which is configurable by the user and from the command line.
    The corresponding simulation class is sim_cls=SimulatedDataWaveform, more details on defaults within the simulation class.

    >>> waveform = SimWaveform(name="waveform")

    Parameters
    ----------
    name (string)           : Name of the device. This is the only required argmuent, passed on to all signals of the device.
    precision (integer)     : Precision of the readback in digits, written to .describe(). Default is 3 digits.
    sim_init (dict)         : Dictionary to initiate parameters of the simulation, check simulation type defaults for more details.
    parent                  : Parent device, optional, is used internally if this signal/device is part of a larger device.
    kind                    : A member the Kind IntEnum (or equivalent integer), optional. Default is Kind.normal. See Kind for options.
    device_manager          : DeviceManager from BEC, optional . Within startup of simulation, device_manager is passed on automatically.

    """

    USER_ACCESS = ["sim", "registered_proxies", "delay_slice_update"]

    sim_cls = SimulatedDataWaveform
    SHAPE = (1000,)
    BIT_DEPTH = np.uint16

    SUB_MONITOR = "device_monitor_1d"
    _default_sub = SUB_MONITOR

    exp_time = Cpt(SetableSignal, name="exp_time", value=1, kind=Kind.config)
    file_path = Cpt(SetableSignal, name="file_path", value="", kind=Kind.config)
    file_pattern = Cpt(SetableSignal, name="file_pattern", value="", kind=Kind.config)
    frames = Cpt(SetableSignal, name="frames", value=1, kind=Kind.config)
    burst = Cpt(SetableSignal, name="burst", value=1, kind=Kind.config)

    waveform_shape = Cpt(SetableSignal, name="waveform_shape", value=SHAPE, kind=Kind.config)
    waveform = Cpt(
        ReadOnlySignal,
        name="waveform",
        value=np.empty(SHAPE, dtype=BIT_DEPTH),
        compute_readback=True,
        kind=Kind.hinted,
    )
    data = Cpt(AsyncSignal, name="data", ndim=1)
    # Can be extend or append
    async_update = Cpt(AsyncUpdateSignal, value="add", kind=Kind.config)
    slice_size = Cpt(SetableSignal, value=100, dtype=np.int32, kind=Kind.config)

    def __init__(
        self,
        name,
        *,
        kind=None,
        parent=None,
        sim_init: dict = None,
        device_manager=None,
        scan_info=None,
        **kwargs,
    ):
        self.sim_init = sim_init
        self._registered_proxies = {}
        self.sim = self.sim_cls(parent=self, **kwargs)

        super().__init__(name=name, parent=parent, kind=kind, **kwargs)
        if device_manager:
            self.device_manager = device_manager
        else:
            self.device_manager = bec_utils.DMMock()

        self.connector = self.device_manager.connector
        self._stream_ttl = 1800  # 30 min max
        self.stopped = False
        self._staged = Staged.no
        self._trigger_thread = None
        self.scan_info = scan_info
        self._delay_slice_update = False
        if self.sim_init:
            self.sim.set_init(self.sim_init)
        self._slice_index = 0

    @property
    def delay_slice_update(self) -> bool:
        """Delay updates in-between slices specified by waveform_shape and slice_size."""
        return self._delay_slice_update

    @typechecked
    @delay_slice_update.setter
    def delay_slice_update(self, value: bool) -> None:
        self._delay_slice_update = value

    @property
    def registered_proxies(self) -> None:
        """Dictionary of registered signal_names and proxies."""
        return self._registered_proxies

    def trigger(self) -> DeviceStatus:
        """Trigger the camera to acquire images.

        This method can be called from BEC during a scan. It will acquire images and send them to BEC.
        Whether the trigger is send from BEC is determined by the softwareTrigger argument in the device config.

        Here, we also run a callback on SUB_MONITOR to send the image data the device_monitor endpoint in BEC.
        """
        status = DeviceStatus(self)

        def acquire(status: DeviceStatus):
            try:
                for _ in range(self.burst.get()):
                    # values of the Waveform
                    values = self.waveform.get()
                    # add_slice option
                    if self.async_update.get() == "add_slice":
                        size = self.slice_size.get()
                        mod = len(values) % size
                        num_slices = len(values) // size + int(mod > 0)
                        for i in range(num_slices):
                            value_slice = values[i * size : min((i + 1) * size, len(values))]
                            logger.info(
                                f"Sending slice {i} of {self._slice_index} with length {len(value_slice)}"
                            )
                            self._run_subs(sub_type=self.SUB_MONITOR, value=value_slice)
                            self._send_async_update(index=self._slice_index, value=value_slice)
                            if self.delay_slice_update is True:
                                time.sleep(0.025)  # 25ms to be really fast
                            if self.stopped:
                                raise DeviceStopError(f"{self.name} was stopped")
                        self._slice_index += 1
                    # option add
                    elif self.async_update.get() == "add":
                        self._run_subs(sub_type=self.SUB_MONITOR, value=values)
                        self._send_async_update(value=values)
                    else:
                        # This should never happen, but just in case
                        # we raise an exception
                        raise ValueError(f"Invalid async_update type: {self.async_update.get()}")
                    if self.stopped:
                        raise DeviceStopError(f"{self.name} was stopped")
                status.set_finished()
            # pylint: disable=broad-except
            except Exception as exc:
                content = traceback.format_exc()
                status.set_exception(exc=exc)
                logger.warning(f"Error in {self.name} trigger; Traceback: {content}")

        self._trigger_thread = threading.Thread(target=acquire, args=(status,), daemon=True)
        self._trigger_thread.start()
        return status

    def _send_async_update(self, value: Any, index: int | None = None) -> None:
        """
        Send the async update to BEC.

        Args:
            index (int | None): The index of the slice to be sent. If None, the entire waveform is sent.
            value (Any): The value to be sent.
        """
        async_update_type = self.async_update.get()
        waveform_shape = self.waveform_shape.get()
        if async_update_type == "add_slice":
            if index is not None:
                metadata = {
                    "async_update": {
                        "type": "add_slice",
                        "index": index,
                        "max_shape": [None, waveform_shape],
                    }
                }
            else:
                metadata = {"async_update": {"type": "add", "max_shape": [None, waveform_shape]}}
        elif async_update_type == "add":
            metadata = {"async_update": {"type": "add", "max_shape": [None]}}
        else:
            # Again, this should never happen -> check_value,
            # but just in case we raise an exception
            raise ValueError(
                f"Invalid async_update type: {async_update_type} for device {self.name}"
            )

        msg = messages.DeviceMessage(
            signals={self.waveform.name: {"value": value, "timestamp": time.time()}},
            metadata=metadata,
        )
        # Send the message to BEC
        self.connector.xadd(
            MessageEndpoints.device_async_readback(
                scan_id=self.scan_info.msg.scan_id, device=self.name
            ),
            {"data": msg},
            expire=self._stream_ttl,
        )

    def stage(self) -> list[object]:
        """Stage the camera for upcoming scan

        This method is called from BEC in preparation of a scan.
        It receives metadata about the scan from BEC,
        compiles it and prepares the camera for the scan.

        FYI: No data is written to disk in the simulation, but upon each trigger it
        is published to the device_monitor endpoint in REDIS.
        """
        if self._staged is Staged.yes:

            return super().stage()
        self.file_path.set(
            os.path.join(
                self.file_path.get(), self.file_pattern.get().format(self.scan_info.msg.scan_number)
            )
        )
        self.frames.set(
            self.scan_info.msg.num_points * self.scan_info.msg.scan_parameters["frames_per_trigger"]
        )
        self.exp_time.set(self.scan_info.msg.scan_parameters["exp_time"])
        self.burst.set(self.scan_info.msg.scan_parameters["frames_per_trigger"])
        self.stopped = False
        self._slice_index = 0
        logger.warning(f"Staged {self.name}, scan_id : {self.scan_info.msg.scan_id}")
        return super().stage()

    def unstage(self) -> list[object]:
        """Unstage the device

        Send reads from all config signals to redis
        """
        logger.warning(f"Unstaging {self.name}, {self._staged}")
        self._slice_index = 0
        if self.stopped is True or not self._staged:
            return super().unstage()
        return super().unstage()

    def stop(self, *, success=False):
        """Stop the device"""
        self.stopped = True
        if self._trigger_thread:
            self._trigger_thread.join()
        self._trigger_thread = None
        super().stop(success=success)


if __name__ == "__main__":  # pragma: no cover
    waveform = SimWaveform(name="waveform")
    waveform.sim.select_model("GaussianModel")
