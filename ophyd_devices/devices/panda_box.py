
from ophyd_devices.utils.controller import ControllerError
from pandablocks.blocking import BlockingClient
from pandablocks.responses import ReadyData, EndData, FrameData
from pandablocks.commands import GetState, SetState, Arm, Disarm, Raw
import os
import threading
import time
from ophyd import Device, DeviceStatus, Component, Kind
from ophyd_devices.sim.sim_signals import SetableSignal
from ophyd_devices.utils.bec_scaninfo_mixin import BecScaninfoMixin
from ophyd_devices.utils import bec_utils
from bec_lib.messages import DeviceMessage
from bec_lib.endpoints import MessageEndpoints
from bec_lib.logger import bec_logger
import numpy as np
from collections import defaultdict

logger = bec_logger.logger


class PandaControllerError(ControllerError):
    pass

PANDA_CONFIGS = {
    "step" : "/data/test/x07da-test-bec/bec_deployment/ophyd_devices/ophyd_devices/devices/panda_box/panda_cfg_software_trigger_step_scan.ini",
    "step_with_clock" : "/data/test/x07da-test-bec/bec_deployment/ophyd_devices/ophyd_devices/devices/panda_box/panda_cfg_software_trigger_step_scan_with_clock_sampling.ini",
    "fly" : "ophyd_devices/ophyd_devices/devices/panda_box/panda_cfg_software_trigger.ini",
    "fly_with_clock" : "ophyd_devices/ophyd_devices/devices/panda_box/panda_cfg_software_trigger_with_clock_sampling.ini"
    }

class PandaController(Device):

    USER_ACCESS = ["_panda_cfg_files", "load_state_from_disk", "_get_capture_signal_keys"]

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
        self._panda_cfg_files = PANDA_CONFIGS
        self._panda_config = None
        self.socket_host = socket_host
        if device_manager:
            self._update_service_config()
            self.device_manager = device_manager
        else:
            self.device_manager = bec_utils.DMMock()
            base_path = kwargs["basepath"] if "basepath" in kwargs else "."
            self.service_cfg = {"base_path": os.path.abspath(base_path)}

        self.connector = self.device_manager.connector
        self._stream_ttl = 1800
        self._update_scaninfo()

    def describe(self) -> dict:
        ret = super().describe()
        # ret.update({"INENC2.VAL.Value" : {}})
        ret.update((f"{key}.Value", {"source" : f"SIM:{key}",
                           "dtype" : "float",
                           "shape" : [],
                           "precision" : 3}) for key in self._get_capture_signal_keys() if key.strip("."))
        return ret

    def _update_service_config(self):
        from bec_lib.bec_service import SERVICE_CONFIG

        if SERVICE_CONFIG:
            self.service_cfg = SERVICE_CONFIG.config["service_config"]["file_writer"]
            return
        self.service_cfg = {"base_path": os.path.abspath(".")}
    
    def _update_scaninfo(self) -> None:
        """Update scaninfo from BecScaninfoMixing
        This depends on device manager and operation/sim_mode
        """
        self.scaninfo = BecScaninfoMixin(self.device_manager)
        self.scaninfo.load_scan_metadata()

    def _get_capture_signal_keys(self) -> list[str]:
        ret = self.send_command(Raw("*CAPTURE?"))
        ret = [key.split(" ")[0].strip("!") for key in ret if key.strip(".")]
        self.capture_signal_names.set(ret)
        return ret

    def write_state_to_disk(self, filename:str):
        state = "\n".join(self.get_state_panda())
        with open(filename, "w", encoding="utf-8") as f:
            f.write(state)

    def get_state_panda(self) -> list[str]:
        with BlockingClient(self.socket_host) as client:
            out = client.send(GetState())
        return out
    
    def read_state_from_disk(self, filename:str) -> list[str]:
        if not os.path.exists(filename):
            raise PandaControllerError(f"Could not find state file {filename}.")
        with open(filename, "r", encoding="utf-8") as f:
            input_data = f.read().splitlines()
        return input_data


    def load_state_from_disk(self, filename:str):
        input_data = self.read_state_from_disk(filename)
        with BlockingClient(self.socket_host) as client:
            client.send(SetState(input_data))

    def _send_data_to_bec(self, data:np.array) -> None:
        out = defaultdict(lambda : defaultdict(list))
        keys = data.dtype.names
        for entry in data:
            for i, key in enumerate(keys):
                out[key]["value"].append(entry[i])
        #TODO add here reduction option for higher sampling frequencies
        # my_func -> out
        msg = DeviceMessage(signals=out, metadata={"async_update" :"extend"})#TODO add here scan_msg metadata + done flag
        self.connector.xadd(
            topic=MessageEndpoints.device_async_readback(scan_id=self.scaninfo.scan_id, device=self.name), 
            msg_dict={"data" : msg},
            expire=self._stream_ttl,
            )
        
        
    def _run_data_readout(self):
        with BlockingClient(self.socket_host) as client:
            try:
                for data in client.data(scaled=False):
                    if isinstance(data, ReadyData):
                        logger.debug(f"Device {self.name} received ready data {data}")
                        self.started_event.set()
                        continue

                    if isinstance(data, FrameData):
                        logger.debug(f"Device {self.name} received frame data")
                        self._send_data_to_bec(data.data)
                        continue
                    
                    if isinstance(data, EndData):
                        logger.info(f"Device {self.name} received end data {data}")
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
        self.scaninfo.load_scan_metadata()
        self.on_stage()
        # Load capture signals
        self._get_capture_signal_keys()
        self.run()
        # Arm PCAP after starting data capture
        ret = super().stage()
        if not self.scaninfo.scan_type == "step":
            return ret
        status = self.kickoff()
        timeout = 2
        timer = 0
        while not status.done:
            logger.info(f"Device {self.name} is kicked off, waiting for status to be done.")
            time.sleep(0.1)
            timer += 0.1
            if timer > timeout:
                raise PandaControllerError(f"Failed to kickoff device {self.name} during stage.")
        return ret
    
    def trigger(self) -> DeviceStatus:
        #TODO make this a threaded call,
        status = DeviceStatus(self) 
        self.on_trigger()
        status.set_finished()
        return status
    
    def on_trigger(self):
        self.send_command(Raw("BITS.B=1"))
        self.send_command(Raw("BITS.B=0"))
    
    def on_stage(self):
        commands = []
        if self.scaninfo.scan_type == "step":
            self.load_state_from_disk(self._panda_cfg_files["step"])
            #TODO Check how to bundle commands in a single chain; check documentation
            commands.extend(["BITS.B=0", "BITS.A=1"])
            commands.extend(["INENC2.VAL.CAPTURE=Value",
                             "PCAP.BITS1.CAPTURE=No",
                             "PCAP.BITS2.CAPTURE=No",
                             "COUNTER1.OUT.CAPTURE=No"])
        elif self.scaninfo.scan_type == "fly":
            self.load_state_from_disk(self._panda_cfg_files["fly"])
            commands.extend(["PULSE1.PULSES=1",
                        "PULSE1.WIDTH.UNITS=s" 
                        f"PULSE1.WIDTH={self.scaninfo.exp_time}",
                        f"PULSE1.STEP={self.scaninfo.frames_per_trigger}",
                        ])
        if len(commands)>0:
            ret = [self.send_command(Raw(cmd)) for cmd in commands]

    def send_command(self, command: str):
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
    from bec_lib.client import BECClient
    bec = BECClient()
    bec.start()
    dm = bec.device_manager
    controller = PandaController(name="redpanda", socket_host="x02da-panda-2.psi.ch", device_manager=dm)
    controller.on_stage()
    # Load capture signals
    controller.capture_signal_names.set(controller._get_capture_signal_keys())
    print(controller.describe())
    # controller.write_state_to_disk("ophyd_devices/ophyd_devices/devices/panda_box/panda_cfg_software_trigger_step_scan_with_clock_sampling.ini")
#     fname = PANDA_CONFIGS["step"]
#     controller.load_state_from_disk(fname)
#     controller.on_stage()
#     start_time = time.time()
#     controller.scaninfo.scan_id = "1111"
#     controller.stage()
#     print(f"\n Time after stage: {time.time()- start_time}\n")
#     controller.kickoff().wait()
#     print(f"\nTime after kickoff {time.time()- start_time}\n")
#     time.sleep(2)
#     print(f"\nTime after sleep {time.time()- start_time}\n")
#     controller.unstage()
#     print(f"\nTime after unstage {time.time()- start_time}\n")

    # print("-----------")
    # print(len(controller.data_bucket))
    # print(sum([len(data.data)for data in controller.data_bucket]))


    # try:
    #     controller.on()
    #     controller.write_state_to_disk("test_config.ini")
    # finally:
    #     controller.off()