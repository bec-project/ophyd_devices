TABLES_DT_PUSH_DIST_MM = 890


class DetectorTableTheta(PseudoPositioner):
    """Detector table tilt motor

    Small wrapper to adjust the detector table tilt as angle.
    The table is pushed from one side by a single vertical motor.

    Note: Rarely used!
    """

    # Real axis (in degrees)
    pusher = Component(EpicsMotor, "", name="pusher")
    # Virtual axis
    theta = Component(PseudoSingle, name="theta")

    _real = ["pusher"]

    @pseudo_position_argument
    def forward(self, pseudo_pos):
        return self.RealPosition(
            pusher=tan(pseudo_pos.theta * 3.141592 / 180.0) * TABLES_DT_PUSH_DIST_MM
        )

    @real_position_argument
    def inverse(self, real_pos):
        return self.PseudoPosition(
            theta=-180 * atan(real_pos.pusher / TABLES_DT_PUSH_DIST_MM) / 3.141592
        )
