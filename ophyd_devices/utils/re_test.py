from bluesky import RunEngine
from bluesky.plans import grid_scan
from bluesky.callbacks.best_effort import BestEffortCallback
from bluesky.callbacks.mpl_plotting import LivePlot


RE = RunEngine({})

from bluesky.callbacks.best_effort import BestEffortCallback

bec = BestEffortCallback()

# Send all metadata/data captured to the BestEffortCallback.
RE.subscribe(bec)
# RE.subscribe(dummy)

# RE(grid_scan(dets, motor1, -10, 10, 10, motor2, -10, 10, 10))
