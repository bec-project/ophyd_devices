from ophyd import SoftPositioner as _SoftPositioner


class SoftPositioner(_SoftPositioner):
    """
    A patched version of ophyd's SoftPositioner that complies with
    ophyd device protocol.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._destroyed = False

    def destroy(self):
        self._destroyed = True
        super().destroy()
