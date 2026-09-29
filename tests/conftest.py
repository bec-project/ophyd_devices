import os

os.environ.setdefault("EPICS_CA_ADDR_LIST", "127.0.0.1")
os.environ.setdefault("EPICS_CA_AUTO_ADDR_LIST", "NO")
os.environ.setdefault("EPICS_CAS_AUTO_BEACON_ADDR_LIST", "NO")
os.environ.setdefault("EPICS_CAS_BEACON_ADDR_LIST", "127.0.0.1")

import ophyd_devices  # ensure we are patched
