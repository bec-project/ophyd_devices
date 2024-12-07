from bec_lib import messages
from bec_lib.endpoints import MessageEndpoints
from ophyd import Component as Cpt
from ophyd import Kind

from ophyd_devices.interfaces.base_classes.bec_device_base import BECDeviceBase, CustomPrepare
from ophyd_devices.sim.sim_signals import SetableSignal


class CustomDetectorMixin(CustomPrepare):
    """Deprecated, use CustomPrepare instead. Here for backwards compatibility."""

    def publish_file_location(
        self,
        done: bool,
        successful: bool,
        filepath: str = None,
        hinted_locations: dict = None,
        metadata: dict = None,
    ) -> None:
        """
        Publish the filepath to REDIS.

        We publish two events here:
        - file_event: event for the filewriter
        - public_file: event for any secondary service (e.g. radial integ code)

        Args:
            done (bool): True if scan is finished
            successful (bool): True if scan was successful
            filepath (str): Optional, filepath to publish. If None, it will be taken from self.parent.filepath.get()
            hinted_locations (dict): Optional, dictionary with hinted locations; {dev_name : h5_entry}
            metadata (dict): additional metadata to publish
        """
        if metadata is None:
            metadata = {}

        if filepath is None:
            file_path = self.parent.filepath.get()

        msg = messages.FileMessage(
            file_path=self.parent.filepath.get(),
            hinted_locations=hinted_locations,
            done=done,
            successful=successful,
            metadata=metadata,
        )
        pipe = self.parent.connector.pipeline()
        self.parent.connector.set_and_publish(
            MessageEndpoints.public_file(self.parent.scaninfo.scan_id, self.parent.name),
            msg,
            pipe=pipe,
        )
        self.parent.connector.set_and_publish(
            MessageEndpoints.file_event(self.parent.name), msg, pipe=pipe
        )
        pipe.execute()


class PSIDetectorBase(BECDeviceBase):
    """Deprecated, use BECDeviceBase instead. Here for backwards compatibility."""

    custom_prepare_cls = CustomDetectorMixin

    filepath = Cpt(SetableSignal, value="", kind=Kind.config)
