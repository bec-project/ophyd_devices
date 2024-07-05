from ophyd import SoftPositioner as _SoftPositioner


class SoftPositioner(_SoftPositioner):
    """
    A patched version of ophyd's SoftPositioner that complies with
    ophyd device protocol.
    """

    def __init__(self, *, egu="", limits=None, source="computed", init_pos=None, **kwargs):
        super().__init__(egu=egu, limits=limits, source=source, init_pos=init_pos, **kwargs)
        self._destroyed = False

    def destroy(self):
        self._destroyed = True
        super().destroy()
