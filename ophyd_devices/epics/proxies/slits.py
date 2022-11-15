from ophyd import Device, Component, EpicsMotor, PseudoPositioner, PseudoSingle
from ophyd.pseudopos import pseudo_position_argument, real_position_argument


class SlitH(PseudoPositioner):
    """Python wrapper for virtual slits

    These devices should be implemented as an EPICS SoftMotor IOC,
    but thats not the case for all slits. So here is a pure ophyd
    implementation. Uses standard naming convention!

    NOTE: The real and virtual axes are wrapped together.
    """

    # Motor interface
    x1 = Component(EpicsMotor, "TRX1")
    x2 = Component(EpicsMotor, "TRX2")

    cenx = Component(PseudoSingle)
    gapx = Component(PseudoSingle)

    @pseudo_position_argument
    def forward(self, pseudo_pos):
        """Run a forward (pseudo -> real) calculation"""
        return self.RealPosition(
            x1=pseudo_pos.cenx - pseudo_pos.gapx / 2, x2=pseudo_pos.cenx + pseudo_pos.gapx / 2
        )

    @real_position_argument
    def inverse(self, real_pos):
        """Run an inverse (real -> pseudo) calculation"""
        return self.PseudoPosition(
            cenx=(real_pos.x1 + real_pos.x2) / 2, gapx=real_pos.x2 - real_pos.x1
        )


class SlitV(PseudoPositioner):
    """Python wrapper for virtual slits

    These devices should be implemented as an EPICS SoftMotor IOC,
    but thats not the case for all slits. So here is a pure ophyd
    implementation. Uses standard naming convention!

    NOTE: The real and virtual axes are wrapped together.
    """

    # Motor interface
    y1 = Component(EpicsMotor, "TRY1")
    y2 = Component(EpicsMotor, "TRY2")

    ceny = Component(PseudoSingle)
    gapy = Component(PseudoSingle)

    @pseudo_position_argument
    def forward(self, pseudo_pos):
        """Run a forward (pseudo -> real) calculation"""
        return self.RealPosition(
            y1=pseudo_pos.ceny - pseudo_pos.gapy / 2, y2=pseudo_pos.ceny + pseudo_pos.gapy / 2
        )

    @real_position_argument
    def inverse(self, real_pos):
        """Run an inverse (real -> pseudo) calculation"""
        return self.PseudoPosition(
            ceny=(real_pos.y1 + real_pos.y2) / 2, gapy=real_pos.y2 - real_pos.y1
        )
