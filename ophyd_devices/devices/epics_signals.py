from ophyd import EpicsSignal as EpicsSignal_
from ophyd import EpicsSignalRO
from ophyd import EpicsSignalWithRBV as EpicsSignalWithRBV_
from ophyd.signal import DEFAULT_WRITE_TIMEOUT

from ophyd_devices.utils.psi_device_base_utils import StatusBase


class EpicsSignal(EpicsSignal_):
    """Custom EpicsSignal class that uses the StatusBase object from ophyd_devices."""

    def set(self, value, *, timeout=DEFAULT_WRITE_TIMEOUT, settle_time=None):
        """
        Custom set method for EpicsSignal that uses the StatusBase object from
        ophyd_devices.

        Args:
            value: The value to set the signal to.
            timeout: The timeout for the operation. If not specified, it will
                use the default write timeout.
            settle_time: The time to wait after the put operation before
                considering it complete. If not specified, it will use the
                default settle time.
        Returns:
            A StatusBase object that can be used to monitor the progress of the
            operation.
        """
        if timeout is DEFAULT_WRITE_TIMEOUT:
            timeout = self.write_timeout

        if not self._put_complete:
            return super().set(value, timeout=timeout, settle_time=settle_time)

        # using put completion:
        # timeout and settle time is handled by the status object.
        st = StatusBase(
            obj=self,
            timeout=timeout,
            settle_time=settle_time,
            description=f"Trying to set signal '{self.name}' to value: {value}.",
        )

        def put_callback(**kwargs):
            st._finished(success=True)

        self.put(value, use_complete=True, callback=put_callback)
        return st


class EpicsSignalWithRBV(EpicsSignalWithRBV_):
    """Custom EpicsSignal class that uses the StatusBase object from ophyd_devices."""

    def set(self, value, *, timeout=DEFAULT_WRITE_TIMEOUT, settle_time=None):
        """
        Custom set method for EpicsSignal that uses the StatusBase object from
        ophyd_devices.

        Args:
            value: The value to set the signal to.
            timeout: The timeout for the operation. If not specified, it will
                use the default write timeout.
            settle_time: The time to wait after the put operation before
                considering it complete. If not specified, it will use the
                default settle time.
        Returns:
            A StatusBase object that can be used to monitor the progress of the
            operation.
        """
        if timeout is DEFAULT_WRITE_TIMEOUT:
            timeout = self.write_timeout

        if not self._put_complete:
            return super().set(value, timeout=timeout, settle_time=settle_time)

        # using put completion:
        # timeout and settle time is handled by the status object.
        st = StatusBase(
            obj=self,
            timeout=timeout,
            settle_time=settle_time,
            description=f"Trying to set signal '{self.name}' to value: {value}.",
        )

        def put_callback(**kwargs):
            st._finished(success=True)

        self.put(value, use_complete=True, callback=put_callback)
        return st
