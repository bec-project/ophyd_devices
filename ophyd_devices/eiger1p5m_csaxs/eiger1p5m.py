import os
import time

from bec_lib import MessageEndpoints, bec_logger, messages
from ophyd import Component as Cpt
from ophyd import Device, DeviceStatus, EpicsSignal, EpicsSignalRO, Signal

logger = bec_logger.logger


class _SLSDetectorConfigSignal(Signal):
    def put(self, value, *, timestamp=None, force=False):
        self._readback = value
        self.parent.sim_state[self.name] = value

    def get(self):
        self._readback = self.parent.sim_state[self.name]
        return self.parent.sim_state[self.name]


# if (_eigerinvac_is_on == 1) {
#   tic("setup eiger in vac")
#   epics_put("X12SA-ES1-DOUBLE-02",0)
#     unix(sprintf("mkdir -p /sls/X12SA/data/%s/Data10/eiger_4/S%05d-%05d/S%05d",_username,int((SCAN_N+1)/1000)*1000,int((SCAN_N+1)/1000)*1000+999,SCAN_N+1))

#     epics_put("XOMNYI-DET-OUTDIR:0.DESC",sprintf("/sls/X12SA/data/%s/Data10/eiger_4/",_username))
#     epics_put("XOMNYI-DET-OUTDIR:1.DESC",sprintf("S%05d-%05d/S%05d",int((SCAN_N+1)/1000)*1000,int((SCAN_N+1)/1000)*1000+999,SCAN_N+1))
#    epics_put("XOMNYI-DET-CYCLES:0", _lamni_scan_numberofpts)
#     epics_put("XOMNYI-DET-EXPTIME:0", $2)
#     epics_put("XOMNYI-DET-INDEX:0", SCAN_N+1)

#     epics_put("XOMNYI-DET-CONTROL:0.DESC", "begin")
#     if(_eigerinvac_burst==0)
#     {
#       epics_put("XOMNYI-DET-CYCLES:0", _lamni_scan_numberofpts)
#       epics_put("XOMNYI-DET-EXPTIME:0", $2)
#       metadata_set("eiger_burst", "int", 1, 1)
#     }
#     else
#     {
#       metadata_set("eiger_burst", "int", 1, (int($2/0.0085)))
#       epics_put("XOMNYI-DET-CYCLES:0", _lamni_scan_numberofpts*(int($2/0.0085)))
#       epics_put("XOMNYI-DET-EXPTIME:0", 0.005)
#     }
#  global _DC_acquisition_ID
#     _DC_acquisition_ID = SCAN_N+1


class Eiger1p5MDetector(Device):
    USER_ACCESS = []
    file_path = Cpt(EpicsSignal, name="file_path", read_pv="XOMNYI-DET-OUTDIR:0.DESC")
    detector_out_scan_dir = Cpt(
        EpicsSignal, name="detector_out_scan_dir", read_pv="XOMNYI-DET-OUTDIR:1.DESC"
    )
    frames = Cpt(EpicsSignal, name="frames", read_pv="XOMNYI-DET-CYCLES:0")
    exp_time = Cpt(EpicsSignal, name="exp_time", read_pv="XOMNYI-DET-EXPTIME:0")
    index = Cpt(EpicsSignal, name="index", read_pv="XOMNYI-DET-INDEX:0")
    detector_control = Cpt(
        EpicsSignal, name="detector_control", read_pv="XOMNYI-DET-CONTROL:0.DESC"
    )
    framescaught = Cpt(EpicsSignalRO, name="framescaught", read_pv="XOMNYI-DET-CONTROL:0.VAL")

    file_pattern = Cpt(_SLSDetectorConfigSignal, name="file_pattern", value="")
    burst = Cpt(_SLSDetectorConfigSignal, name="burst", value=1)
    save_file = Cpt(_SLSDetectorConfigSignal, name="save_file", value=False)

    def __init__(self, *, name, kind=None, parent=None, device_manager=None, **kwargs):
        self.device_manager = device_manager
        super().__init__(name=name, parent=parent, kind=kind, **kwargs)
        self.sim_state = {
            f"{self.name}_file_path": "~/Data10/data/",
            f"{self.name}_file_pattern": f"{self.name}_{{:05d}}.h5",
            f"{self.name}_frames": 1,
            f"{self.name}_burst": 1,
            f"{self.name}_save_file": False,
            f"{self.name}_exp_time": 0,
        }
        self._stopped = False
        self.file_name = ""
        self.metadata = {}
        self.username = "e20588"  # TODO get from config

    def _get_current_scan_msg(self) -> messages.ScanStatusMessage:
        return self.device_manager.connector.get(MessageEndpoints.scan_status())

    def _get_scan_dir(self, scan_bundle, scan_number, leading_zeros=None):
        if leading_zeros is None:
            leading_zeros = len(str(scan_bundle))
        floor_dir = scan_number // scan_bundle * scan_bundle
        return f"S{floor_dir:0{leading_zeros}d}-{floor_dir+scan_bundle-1:0{leading_zeros}d}/S{scan_number:0{leading_zeros}d}"

    def stage(self) -> list[object]:
        scan_msg = self._get_current_scan_msg()
        self.metadata = {
            "scanID": scan_msg.content["scanID"],
            "RID": scan_msg.content["info"]["RID"],
            "queueID": scan_msg.content["info"]["queueID"],
        }
        scan_number = scan_msg.content["info"]["scan_number"]
        exp_time = scan_msg.content["info"]["exp_time"]

        # set base path for detector output
        self.file_path.set(f"/sls/X12SA/data/{self.username}/Data10/eiger_4/")

        # set scan directory (e.g. S00000-00999/S00020)
        scan_dir = self._get_scan_dir(scan_bundle=1000, scan_number=scan_number, leading_zeros=5)
        self.detector_out_scan_dir.set(scan_dir)

        self.file_name = os.path.join(f"/sls/X12SA/data/{self.username}/Data10/eiger_4/", scan_dir)

        # set the scan number
        self.index.set(scan_number)

        # set the number of frames
        self.frames.set(scan_msg.content["info"]["num_points"])

        # set the exposure time
        self.exp_time.set(exp_time)

        # wait for detector control to become "ready"
        while True:
            det_ctrl = self.detector_control.get()
            if det_ctrl == "ready":
                break
            time.sleep(0.005)

        # send the "begin" flag to start processing the above commands
        self.detector_control.set("begin")

        # wait for detector to be "armed"
        logger.info("Waiting for detector setup")
        while True:
            det_ctrl = self.detector_control.get()
            if det_ctrl == "armed":
                break
            time.sleep(0.005)

        self.detector_control.put("acquiring")

        return super().stage()

    def unstage(self) -> list[object]:
        time_waited = 0
        sleep_time = 0.2
        framesexpected = self.frames.get()
        while True:
            framescaught = self.framescaught.get()
            if self.framescaught.get() < framesexpected:
                logger.info(
                    f"Waiting for frames: Transferred {framescaught} out of {framesexpected}"
                )
                time_waited += sleep_time
                time.sleep(sleep_time)
                if self._stopped:
                    break
                continue
            break
        self.detector_control.put("stop")
        signals = {"config": self.read(), "data": self.file_name}
        msg = messages.DeviceMessage(signals=signals, metadata=self.metadata)
        self.device_manager.connector.set_and_publish(MessageEndpoints.device_read(self.name), msg)
        self._stopped = False
        return super().unstage()

    def stop(self, *, success=False):
        self.detector_control.put("stop")
        super().stop(success=success)
        self._stopped = True


if __name__ == "__main__":
    eiger = Eiger1p5MDetector(name="eiger1p5m", label="eiger1p5m")
    breakpoint()
