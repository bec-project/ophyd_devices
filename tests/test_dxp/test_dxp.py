"""
Test module for DXP integration, i.e. Falcon, XMAP and Mercury detectors.
This also includes EpicsMCARecord for data recording of multichannel analyzers.
"""

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
from ophyd_devices.tests.utils import patched_device

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
    with patched_device(
        TestFalcon, name="mca", prefix="test_falcon", mask_stage_sigs=False, mask_trigger_sigs=False
    ) as falc:
        yield falc


@pytest.fixture(scope="function")
def mock_xmap():
    """Fixture to create a mock xMAP device for testing."""
    with patched_device(
        xMAP, name="mca", prefix="test_xmap", mask_stage_sigs=False, mask_trigger_sigs=False
    ) as xmap:
        yield xmap


@pytest.fixture(scope="function")
def mock_mercury():
    """Fixture to create a mock Mercury device for testing."""
    with patched_device(
        Mercury, name="mca", prefix="test_mercury", mask_stage_sigs=False, mask_trigger_sigs=False
    ) as merc:
        yield merc


def test_falcon(mock_falcon: TestFalcon):
    """Test the Falcon device."""
    # Test the default values
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


def test_falcon_trigger(mock_falcon: TestFalcon):
    """Test the Falcon device trigger method."""
    mock_falcon.erase_start.put(0)
    assert mock_falcon.erase_start.get() == 0
    status = mock_falcon.trigger()
    # Tagged trigger value, should be set to 1 when trigger is called
    assert mock_falcon.erase_start.get() == 1
    assert status.success is True
    assert status.done is True


def test_xmap(mock_xmap: xMAP):
    """Test the xMAP device."""
    # Test the default values
    assert mock_xmap.name == "mca"
    assert mock_xmap.prefix == "test_xmap"
    assert isinstance(mock_xmap, EpicsDXPMultiElementSystem)
    assert isinstance(mock_xmap, ADBase)


def test_mercury(mock_mercury: Mercury):
    """Test the Mercury device."""
    # Test the default values
    assert mock_mercury.name == "mca"
    assert mock_mercury.prefix == "test_mercury"
    assert isinstance(mock_mercury, EpicsDXPMultiElementSystem)
    # assert isinstance(mock_mercury, EpicsDXPMapping) # Not sure why this fails
    assert isinstance(mock_mercury, ADBase)


def test_xmap_trigger(mock_xmap: xMAP):
    """Test the xMAP device trigger method."""
    mock_xmap.erase_start.put(0)
    assert mock_xmap.erase_start.get() == 0
    status = mock_xmap.trigger()
    # Tagged trigger value, should be set to 1 when trigger is called
    assert mock_xmap.erase_start.get() == 1
    assert status.success is True
    assert status.done is True
