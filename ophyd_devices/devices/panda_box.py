
from ophyd_devices.utils.controller import ControllerError
from pandablocks.blocking import BlockingClient
from pandablocks.responses import ReadyData, EndData, FrameData
from pandablocks.commands import GetState, SetState, Arm, Disarm, Raw
import os
import threading
from ophyd import Device, DeviceStatus, Component, Kind
from ophyd_devices.sim.sim_signals import SetableSignal
from ophyd_devices.utils.bec_scaninfo_mixin import BecScaninfoMixin
from ophyd_devices.utils import bec_utils
from bec_lib.messages import DeviceMessage
from bec_lib.endpoints import MessageEndpoints
import numpy as np
from collections import defaultdict


class PandaControllerError(ControllerError):
    pass


class PandaController(Device):

    capture_signal_names = Component(SetableSignal, value=[""], kind=Kind.normal)
    config_path = Component(SetableSignal, value="", kind=Kind.normal)

    SUB_VALUE = ""

    def __init__(self, *, name, socket_host, kind=None, read_attrs=None, configuration_attrs=None, parent=None, device_manager=None,**kwargs):
        super().__init__(name=name, kind=kind, read_attrs=read_attrs, configuration_attrs=configuration_attrs, parent=parent, **kwargs)
        self.connector = None
        self.scaninfo = None
        self.data_thread = None
        self.kickoff_thread = None
        self.started_event = None
        self.end_event = None
        self.socket_host = socket_host
        if device_manager:
            self._update_service_config()
            self.device_manager = device_manager
        else:
            self.device_manager = bec_utils.DMMock()
            base_path = kwargs["basepath"] if "basepath" in kwargs else "."
            self.service_cfg = {"base_path": os.path.abspath(base_path)}

        self.connector = self.device_manager.connector
        self.data_bucket = []
        self._stream_ttl = 1800
    
    def _update_scaninfo(self) -> None:
        """Update scaninfo from BecScaninfoMixing
        This depends on device manager and operation/sim_mode
        """
        self.scaninfo = BecScaninfoMixin(self.device_manager)
        self.scaninfo.load_scan_metadata()

    def _get_capture_signal_keys(self) -> list[str]:
        ret = self.send_command(Raw("*CAPTURE?"))
        return [key.split(" ")[0].strip("!") for key in ret if key.strip(".")]

    def write_state_to_disk(self, filename:str):
        state = "\n".join(self.get_state_panda())
        with open(filename, "w") as f:
            f.write(state)

    def get_state_panda(self) -> list[str]:
        with BlockingClient(self.socket_host) as client:
            out = client.send(GetState())
        return out

    def load_state_from_disk(self, filename:str):
        if not os.path.exists(filename):
            raise PandaControllerError(f"Could not find state file {filename}.")
        with open(filename, "r") as f:
            input_data = f.read().splitlines()
        with BlockingClient(self.socket_host) as client:
            client.send(SetState(input_data))

    def _send_data_to_bec(self, data:np.array) -> None:
        out = defaultdict(list)
        keys = data.dtype.names
        for entry in data:
            for i, key in enumerate(keys):
                out[key].append(entry[i])
        msg = DeviceMessage(signals=out, metadata={})#TODO add here scan_msg metadata + done flag
        self.connector.xadd(
            topic=MessageEndpoints.device_async_readback(scan_id=self.scaninfo.scan_id, device=self.name), 
            msg={"data" : msg}, 
            expire=self._stream_ttl
            )
        
        
    def _run_data_readout(self):
        with BlockingClient(self.socket_host) as client:
            try:
                for data in client.data(scaled=False):
                    if isinstance(data, ReadyData):
                        # print(f"received ready data: {data}")
                        self.started_event.set()
                        continue

                    if isinstance(data, FrameData):
                        # print(f"received frame data: {data}")
                        self.data_bucket.append(data)
                        continue
                    
                    if isinstance(data, EndData):
                        print(f"received end data {data}")
                        self.end_event.set()
                        break
            finally:
                client.send(Disarm())

    def run(self):
        self.started_event = threading.Event()
        self.end_event = threading.Event()
        self.data_thread = threading.Thread(target=self._run_data_readout, daemon=True)
        self.data_thread.start()

    def stage(self) -> list[object]:
        self.capture_signal_names.set(self._get_capture_signal_keys())
        self.run()
        return super().stage()

    def send_command(self, command):
        with BlockingClient(self.socket_host) as client:
            out = client.send(command)
        return out

    def _wait_for_scan_start(self, status:DeviceStatus):
        try:
            self.started_event.wait(10)
            self.send_command(Arm())
            status.set_finished()
        except Exception as exc:
            status.set_exception(exc)

    def kickoff(self) -> DeviceStatus:
        # wait for the ready data to arrive
        status = DeviceStatus(device=self)
        if self.started_event.is_set():
            self.send_command(Arm())
            status.set_finished()
        else:
            self.kickoff_thread = threading.Thread(target=self._wait_for_scan_start, args=(status,), daemon=True)
            self.kickoff_thread.start()
        return status

    def stop(self, success:bool=False):
        self.send_command(Disarm())
        if self.kickoff_thread:
            self.end_event.wait(10)
            self.kickoff_thread.join()
        if self.data_thread:
            self.data_thread.join()
        self.data_thread = None
        self.kickoff_thread = None
        self.started_event = None
        self.end_event = None
        return super().stop(success=success)


    def unstage(self):
        self.stop(success=True)
        return super().unstage()

if __name__ == "__main__":
    import time
    controller = PandaController(name="redpanda", socket_host="x02da-panda-2.psi.ch")
    # controller.write_state_to_disk("panda_config_time_.ini")
    # controller.load_state_from_disk("test_config.ini")
    start_time = time.time()
    controller.stage()
    print(f"\n Time after stage: {time.time()- start_time}\n")
    controller.kickoff().wait()
    print(f"\nTime after kickoff {time.time()- start_time}\n")
    time.sleep(2)
    print(f"\nTime after sleep {time.time()- start_time}\n")
    controller.unstage()
    print(f"\nTime after unstage {time.time()- start_time}\n")

    print("-----------")
    print(len(controller.data_bucket))
    print(sum([len(data.data)for data in controller.data_bucket]))


    # try:
    #     controller.on()
    #     controller.write_state_to_disk("test_config.ini")
    # finally:
    #     controller.off()