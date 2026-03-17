from ophyd_devices import PSIDeviceBase
from ophyd_devices.utils.bec_processed_signal import BECProcessedSignal


class PSIPseudoDeviceBase(PSIDeviceBase):
    """Base class for pseudo devices at PSI."""

    def wait_for_connection(self, *args, **kwargs):
        """Wait for connection of the pseudo device has to be called manually on BECProcessedSignals"""
        for walk in self.walk_signals():
            if isinstance(walk.item, BECProcessedSignal):
                walk.item.wait_for_connection(*args, **kwargs)
        super().wait_for_connection(*args, **kwargs)
