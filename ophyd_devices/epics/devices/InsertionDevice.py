from ophyd import PVPositioner, Component, EpicsSignal, EpicsSignalRO, Kind


class InsertionDevice(PVPositioner):
    """Python wrapper for the CSAXS insertion device control

    This wrapper provides a positioner interface for the ID control.
    is completely custom XBPM with templates directly in the
    VME repo. Thus it needs a custom ophyd template as well...

    WARN: The x and y are not updated by the IOC
    """

    status = Component(EpicsSignalRO, "-USER:STATUS", auto_monitor=True)
    errorSource = Component(EpicsSignalRO, "-USER:ERROR-SOURCE", auto_monitor=True)
    isOpen = Component(EpicsSignalRO, "-GAP:ISOPEN", auto_monitor=True)

    # PVPositioner interface
    setpoint = Component(EpicsSignal, "-GAP:SET", auto_monitor=True)
    readback = Component(EpicsSignalRO, "-GAP:READ", auto_monitor=True, kind=Kind.hinted)
    done = Component(EpicsSignalRO, ":DONE", auto_monitor=True)
    stop_signal = Component(EpicsSignal, "-GAP:STOP", kind=Kind.omitted)


# Automatically start simulation if directly invoked
# (NA for important devices)
if __name__ == "__main__":
    pass
