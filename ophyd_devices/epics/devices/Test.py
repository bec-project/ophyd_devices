import os

from ophyd_devices.epics.devices.pilatus_csaxs import PilatusCsaxs

os.environ["EPICS_CA_AUTO_ADDR_LIST"] = "NO"
os.environ["EPICS_CA_ADDR_LIST"] = "129.129.122.255 sls-x12sa-cagw.psi.ch:5824"
# pilatus_2 = PilatusCsaxs(name="pilatus_2", prefix="X12SA-ES-PILATUS300K")

# pilatus_2.stage()
