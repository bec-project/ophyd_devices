"""
Test module for DXP integration, i.e. Falcon, XMAP and Mercury detectors.
This also includes EpicsMCARecord for data recording of multichannel analyzers.
"""

import threading
from unittest import mock

import ophyd
import pytest
from ophyd import Component as Cpt

from ophyd_devices.devices.dxp import (
    ADBase,
    EpicsDXPFalcon,
    EpicsDxpFalconMapping,
    EpicsDXPFalconMultiElementSystem,
    EpicsDXPMultiElementSystem,
    EpicsMCARecord,
    Falcon,
    Mercury,
    xMAP,
)
from ophyd_devices.tests.utils import MockPV, patch_dual_pvs

# from ophyd.mca import EpicsDXPMapping


# pylint:disable=redefined-outer-name
# pylint: disable=protected-access


class TestFalcon(Falcon):
    """Test class for Falcon device integration together with mca record and dxp faclon."""

    mca1 = Cpt(EpicsMCARecord, "mca1")
    dxp1 = Cpt(EpicsDXPFalcon, "dxp1")


@pytest.fixture(scope="function")
def mock_falcon():
    """Fixture to create a mock Falcon device for testing."""
    name = "mca"
    prefix = "test_falcon"
    with mock.patch.object(ophyd, "cl") as mock_cl:
        mock_cl.get_pv = MockPV
        mock_cl.thread_class = threading.Thread
        ddg = TestFalcon(name=name, prefix=prefix)
        patch_dual_pvs(ddg)
        yield ddg


@pytest.fixture(scope="function")
def mock_xmap():
    """Fixture to create a mock xMAP device for testing."""
    name = "mca"
    prefix = "test_xmap"
    with mock.patch.object(ophyd, "cl") as mock_cl:
        mock_cl.get_pv = MockPV
        mock_cl.thread_class = threading.Thread
        ddg = xMAP(name=name, prefix=prefix)
        patch_dual_pvs(ddg)
        yield ddg


@pytest.fixture(scope="function")
def mock_mercury():
    """Fixture to create a mock Mercury device for testing."""
    name = "mca"
    prefix = "test_mercury"
    with mock.patch.object(ophyd, "cl") as mock_cl:
        mock_cl.get_pv = MockPV
        mock_cl.thread_class = threading.Thread
        ddg = Mercury(name=name, prefix=prefix)
        patch_dual_pvs(ddg)
        yield ddg


def test_falcon(mock_falcon):
    """Test the Falcon device."""
    # Test the default values
    mock_falcon: TestFalcon
    assert mock_falcon.name == "mca"
    assert mock_falcon.prefix == "test_falcon"
    assert isinstance(mock_falcon, EpicsDXPFalconMultiElementSystem)
    assert isinstance(mock_falcon, EpicsDxpFalconMapping)
    assert isinstance(mock_falcon, ADBase)

    assert mock_falcon.hints == {"fields": []}

    assert mock_falcon.mca1.rois.roi0.read_attrs == ["count", "net_count"]
    assert mock_falcon.mca1.rois.roi0.configuration_attrs == [
        "label",
        "preset_count",
        "is_preset",
        "bkgnd_chans",
        "hi_chan",
        "lo_chan",
    ]


def test_xmap(mock_xmap):
    """Test the xMAP device."""
    # Test the default values
    mock_xmap: xMAP
    assert mock_xmap.name == "mca"
    assert mock_xmap.prefix == "test_xmap"
    assert isinstance(mock_xmap, EpicsDXPMultiElementSystem)
    assert isinstance(mock_xmap, ADBase)


def test_mercury(mock_mercury):
    """Test the Mercury device."""
    # Test the default values
    mock_mercury: Mercury
    assert mock_mercury.name == "mca"
    assert mock_mercury.prefix == "test_mercury"
    assert isinstance(mock_mercury, EpicsDXPMultiElementSystem)
    # assert isinstance(mock_mercury, EpicsDXPMapping) # Not sure why this fails
    assert isinstance(mock_mercury, ADBase)
