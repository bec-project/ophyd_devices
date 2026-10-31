"""Local test-environment patch for two baseline constructor-only EPICS tests.

The dummy control layer cannot allocate PVs; use the repository MockPV, without
network I/O, only for tests that assert suffix generation and warning messages.
"""

import threading
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def constructor_pvs(request):
    if request.node.name not in (
        "test_override_suffixes",
        "test_override_suffixes_warns_on_nonimplemented",
    ):
        yield
        return
    import ophyd
    from ophyd_devices.tests.utils import MockPV

    with patch.object(ophyd, "cl") as control:
        control.get_pv = MockPV
        control.thread_class = threading.Thread
        yield
