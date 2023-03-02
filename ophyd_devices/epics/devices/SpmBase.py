import numpy as np
from ophyd import Component, Device, EpicsSignal, EpicsSignalRO


class SpmBase(Device):
    """Python wrapper for the Staggered Blade Pair Monitors

    SPM's consist of a set of four horizontal tungsten blades and are
    used to monitor the beam height (only Y) for the bending magnet
    beamlines of SLS.

    Note: EPICS provided signals are read only, but the users can
    change the beam position offset.
    """

    # Motor interface
    s1 = Component(EpicsSignalRO, "Current1", auto_monitor=True)
    s2 = Component(EpicsSignalRO, "Current2", auto_monitor=True)
    s3 = Component(EpicsSignalRO, "Current3", auto_monitor=True)
    s4 = Component(EpicsSignalRO, "Current4", auto_monitor=True)
    sum = Component(EpicsSignalRO, "SumAll", auto_monitor=True)
    y = Component(EpicsSignalRO, "Y", auto_monitor=True)
    scale = Component(EpicsSignal, "PositionScaleY", auto_monitor=True)
    offset = Component(EpicsSignal, "PositionOffsetY", auto_monitor=True)


class SpmSim(SpmBase):
    """Python wrapper for simulated Staggered Blade Pair Monitors

    SPM's consist of a set of four horizontal tungsten blades and are
    used to monitor the beam height (only Y) for the bending magnet
    beamlines of SLS.

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

        # Define normalized 2D gaussian
        def gaus2d(x=0, y=0, mx=0, my=0, sx=1, sy=1):
            return np.exp(
                -((x - mx) ** 2.0 / (2.0 * sx**2.0) + (y - my) ** 2.0 / (2.0 * sy**2.0))
            )

        # Generator for dynamic values
        self._MX = 0.75 * self._MX + 0.25 * (10.0 * np.random.random() - 5.0)
        self._MY = 0.75 * self._MY + 0.25 * (10.0 * np.random.random() - 5.0)
        self._I0 = 0.75 * self._I0 + 0.25 * (255.0 * np.random.random())

        arr = self._I0 * gaus2d(self._x, self._y, self._MX, self._MY)
        return arr

    def sim(self):
        # Get next frame
        beam = self._simFrame()
        total = np.sum(beam) - np.sum(beam[24:48, :])
        rnge = np.floor(np.log10(total) - 0.0)
        s1 = np.sum(beam[0:16, :]) / 10**rnge
        s2 = np.sum(beam[16:24, :]) / 10**rnge
        s3 = np.sum(beam[40:48, :]) / 10**rnge
        s4 = np.sum(beam[48:64, :]) / 10**rnge

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
    spm1 = SpmSim("X06D-FE-BM1:", name="spm1")
    spm2 = SpmSim("X06D-FE-BM2:", name="spm2")

    spm1.wait_for_connection(timeout=5)
    spm2.wait_for_connection(timeout=5)

    spm1.rangew.set(1).wait()
    spm2.rangew.set(1).wait()

    while True:
        print("---")
        spm1.sim()
        spm2.sim()
