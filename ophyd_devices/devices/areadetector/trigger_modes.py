"""Driver-specific values written to AreaDetector TriggerMode PVs."""

from enum import IntEnum


class SimDetectorTriggerMode(IntEnum):
    """
    Trigger mode supported by the simulated detector's acquisition implementation.
    """

    INTERNAL = 0


class VimbaTriggerMode(IntEnum):
    """
    GenICam trigger enablement for ADVimba; TriggerSource selects the input separately.
    """

    OFF = 0
    ON = 1


class PilatusTriggerMode(IntEnum):
    """
    ADPilatus trigger modes, including single-trigger and per-frame external operation.
    """

    INTERNAL = 0
    EXT_ENABLE = 1
    EXT_TRIGGER = 2
    MULT_TRIGGER = 3
    ALIGNMENT = 4
