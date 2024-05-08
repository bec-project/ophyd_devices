import numpy as np
from ophyd import Component, Device, EpicsSignal, EpicsSignalRO


class XbpmCsaxsOp(Device):
    """Python wrapper for custom XBPMs in the cSAXS optics hutch

    This is  completely custom XBPM with templates directly in the
    VME repo. Thus it needs a custom ophyd template as well...

    WARN: The x and y are not updated by the IOC
    """

    sum = Component(EpicsSignalRO, "SUM", auto_monitor=True)
    x = Component(EpicsSignalRO, "POSH", auto_monitor=True)
    y = Component(EpicsSignalRO, "POSV", auto_monitor=True)
    s1 = Component(EpicsSignalRO, "CHAN1", auto_monitor=True)
    s2 = Component(EpicsSignalRO, "CHAN2", auto_monitor=True)
    s3 = Component(EpicsSignalRO, "CHAN3", auto_monitor=True)
    s4 = Component(EpicsSignalRO, "CHAN4", auto_monitor=True)


class XbpmBase(Device):
    """Python wrapper for X-ray Beam Position Monitors

    XBPM's consist of a metal-coated diamond window that ejects
    photoelectrons from the incoming X-ray beam. These electons
    are collected and their current is measured. Effectively
    they act as four quadrant photodiodes and are used as BPMs
    at the undulator beamlines of SLS.

    Note: EPICS provided signals are read only, but the user can
    change the beam position offset.
    """

    # Motor interface
    s1 = Component(EpicsSignalRO, "Current1", auto_monitor=True)
    s2 = Component(EpicsSignalRO, "Current2", auto_monitor=True)
    s3 = Component(EpicsSignalRO, "Current3", auto_monitor=True)
    s4 = Component(EpicsSignalRO, "Current4", auto_monitor=True)
    sum = Component(EpicsSignalRO, "SumAll", auto_monitor=True)
    asymH = Component(EpicsSignalRO, "asymH", auto_monitor=True)
    asymV = Component(EpicsSignalRO, "asymV", auto_monitor=True)
    x = Component(EpicsSignalRO, "X", auto_monitor=True)
    y = Component(EpicsSignalRO, "Y", auto_monitor=True)
    scaleH = Component(EpicsSignal, "PositionScaleX", auto_monitor=False)
    offsetH = Component(EpicsSignal, "PositionOffsetX", auto_monitor=False)
    scaleV = Component(EpicsSignal, "PositionScaleY", auto_monitor=False)
    offsetV = Component(EpicsSignal, "PositionOffsetY", auto_monitor=False)


class XbpmSim(XbpmBase):
    """Python wrapper for simulated X-ray Beam Position Monitors

    XBPM's consist of a metal-coated diamond window that ejects
    photoelectrons from the incoming X-ray beam. These electons
    are collected and their current is measured. Effectively
    they act as four quadrant photodiodes and are used as BPMs
    at the undulator beamlines of SLS.

    Note: EPICS provided signals are read only, but the user can
       change the beam position offset.

    This simulation device extends the basic proxy with a script that
    fills signals with quasi-randomized values.
    """

    # Motor interface
    s1w = Component(EpicsSignal, "Current1:RAW.VAL", auto_monitor=False)
    s2w = Component(EpicsSignal, "Current2:RAW.VAL", auto_monitor=False)
    s3w = Component(EpicsSignal, "Current3:RAW.VAL", auto_monitor=False)
    s4w = Component(EpicsSignal, "Current4:RAW.VAL", auto_monitor=False)
    rangew = Component(EpicsSignal, "RANGEraw", auto_monitor=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._MX = 0
        self._MY = 0
        self._I0 = 255.0
        self._x = np.linspace(-5, 5, 64)
        self._y = np.linspace(-5, 5, 64)
        self._x, self._y = np.meshgrid(self._x, self._y)

    def _simFrame(self):
        """Generator to simulate a jumping gaussian"""

        # define normalized 2D gaussian
        def gaus2d(x=0, y=0, mx=0, my=0, sx=1, sy=1):
            return np.exp(-((x - mx) ** 2.0 / (2.0 * sx**2.0) + (y - my) ** 2.0 / (2.0 * sy**2.0)))

        # Generator for dynamic values
        self._MX = 0.75 * self._MX + 0.25 * (10.0 * np.random.random() - 5.0)
        self._MY = 0.75 * self._MY + 0.25 * (10.0 * np.random.random() - 5.0)
        self._I0 = 0.75 * self._I0 + 0.25 * (255.0 * np.random.random())

        arr = self._I0 * gaus2d(self._x, self._y, self._MX, self._MY)
        return arr

    def sim(self):
        # Get next frame
        beam = self._simFrame()
        total = np.sum(beam)
        rnge = np.floor(np.log10(total) - 0.0)
        s1 = np.sum(beam[32:64, 32:64]) / 10**rnge
        s2 = np.sum(beam[0:32, 32:64]) / 10**rnge
        s3 = np.sum(beam[32:64, 0:32]) / 10**rnge
        s4 = np.sum(beam[0:32, 0:32]) / 10**rnge

        self.s1w.set(s1).wait()
        self.s2w.set(s2).wait()
        self.s3w.set(s3).wait()
        self.s4w.set(s4).wait()
        self.rangew.set(rnge).wait()
        # Print debug info
        print(f"Raw signals: R={rnge}\t{s1}\t{s2}\t{s3}\t{s4}")
        # plt.imshow(beam)
        # plt.show(block=False)
        # plt.pause(0.5)


# Automatically start simulation if directly invoked
if __name__ == "__main__":
    xbpm1 = XbpmSim("X01DA-FE-XBPM1:", name="xbpm1")
    xbpm2 = XbpmSim("X01DA-FE-XBPM2:", name="xbpm2")

    xbpm1.wait_for_connection(timeout=5)
    xbpm2.wait_for_connection(timeout=5)

    xbpm1.rangew.set(1).wait()
    xbpm2.rangew.set(1).wait()

    while True:
        print("---")
        xbpm1.sim()
        xbpm2.sim()
