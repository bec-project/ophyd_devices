# PR #225 default-timeout findings — how to reproduce them (simulation only)

Everything here runs against simulated devices. No hardware is touched.

Files:

- `audit/timeout_bugs_demo.py` — standalone script, shows **all 15 findings**, no BEC needed.
- `audit/timeout_kwarg_demo.py` — small A/B script for the constructor `timeout` handling
  (run it on this branch and on `main`).
- `audit/timeout_demo_config.yaml` — demo devices for the running BEC session.
- `ophyd_devices/sim/timeout_demo.py` — the demo device classes.

Requirements: this branch checked out (`audit/default_timeout_arg` = PR head `e65d271` plus
this tooling) with the ophyd_devices environment active. The BEC device server imports device
modules once per process, so it must have been (re)started after the checkout and after any
change to `timeout_demo.py`.

---

## A. Standalone script (all findings, ~20 s)

```bash
python audit/timeout_bugs_demo.py
```

Each numbered section prints what the code does today and marks the problem with `BUG`.
Errors that the library would otherwise only print to stderr (the wait thread crashing with
`OverflowError` in #2, the `TypeError` ophyd swallows in a subscription callback in #13) are
captured and shown as evidence lines inside their section.

| # | What it shows |
|---|---|
| 1 | `_timeout` is set after `super().__init__()`: a status created during init crashes the device construction; an invalid timeout is rejected only after the device was built; positioners see the raw value (-5) during init |
| 2 | NaN and inf pass the guard: NaN → every status fails instantly, inf → the status never completes |
| 3 | `ExceptionStatus` watchdog inherits the default and fails a healthy composite |
| 4 | `task_handler.submit_task` tasks inherit the default; a 0.8 s task on a 0.3 s device ends as a failed status with state "completed" |
| 5 | a timed-out `DeviceStatus` calls `device.stop()`; `call_stop_on_failure=False` no longer accepted |
| 6 | positioner: `move(1, timeout=10)` still dies at the device default; exception type varies between identical moves |
| 7 | the VME motor's "move completion" timeout config now caps every status of the motor |
| 8 | pseudo motor: `_timeout` says 3.0, `move()` returns a status with timeout `None` |
| 9 | `pos.timeout = 30` (ophyd API) silently rewrites the status default; `-3` is accepted |
| 10 | `complete()` fallback status is not `done` right after the call |
| 11 | `timeout=None` means "use the default", `timeout=0` fails instantly — no way to say "no timeout" |
| 12 | a nested PSI sub-device never inherits the parent's default |
| 13 | `np.int64` rejected, `True` accepted as 1 s; the signal-sync pattern silently keeps a stale value |
| 14 | PandaBox: the staging error handler is bypassed |
| 15 | `DeviceStatus(MagicMock(spec=PSIDeviceBase))` raises `AttributeError` |

---

## B. Live in the BEC IPython client

Every command below was run against a local, simulated BEC instance (demo config) on
this branch; the outputs quoted are the real ones.

### Step 1 — add the demo devices (once)

Start the IPython client in the repository root so the relative path resolves, then:

```python
bec.config.add_to_session("audit/timeout_demo_config.yaml")
```

Devices (all with `timeout: 0.5` in `deviceConfig`, exposures of 1 s):

| device | class | what it is |
|---|---|---|
| `demo_det` | `TimeoutDemoDetector` | trigger = `DeviceStatus`, finished after `exposure` s; probes: `applied_timeout`, `status_timeout`, `stop_count` |
| `demo_watchdog` | `TimeoutDemoWatchdogDetector` | same, but the exposure (60 s budget) is guarded by an `ExceptionStatus` watchdog |
| `demo_cam` | `TimeoutDemoCamera` | SimCamera whose trigger is a background task (`submit_task`) taking `exposure` s |
| `demo_pos` | `TimeoutDemoPositioner` | PSI positioner on fake EPICS signals, moves never finish; `timeout` is **not** in its `__init__` (like every real positioner) |
| `demo_pos_ctor` | `TimeoutDemoPositionerCtor` | same, but `timeout` is declared in `__init__` (the PR's intended path) |

They are already in your running session. Enable/disable a device with
`dev.demo_det.enabled = False`; update its config with
`bec.device_manager.config_helper.send_config_request(action="update", config={"demo_det": {"deviceConfig": {...}}})`.
Config updates are refused while a scan is running.

### Step 2 — the config path: `timeout` never reaches a normal device (new finding)

The device server only passes `deviceConfig` keys that appear in the class's *own* `__init__`
signature. Every PSI device that relies on `**kwargs` (SimCamera, PandaBox, all detectors) never
gets the kwarg; the key falls through to `update_config`, which rejects unknown attributes.

Try it on the stock eiger (nothing changes, the update is rejected):

```python
bec.device_manager.config_helper.send_config_request(
    action="update", config={"eiger": {"deviceConfig": {"device_access": True, "timeout": 2}}}
)
```

Output: `DeviceConfigError: ... Unknown config parameter timeout for device of type SimCamera. ... No devices were updated.`

The same happens when a device is *added* with `timeout` in its config — that is why the demo
detector classes declare `timeout` explicitly in `__init__` (remove the parameter to see the
device fail to initialize: `Failed to initialize device demo_det: DeviceConfigError: Unknown
config parameter timeout`).

For positioners the key is accepted — not through the PR's constructor, but because ophyd's
`PositionerBase` has a `timeout` property that the device server sets with `setattr`, with no
validation at all (Step 7 shows what that does).

### Step 3 — detector: 1 s exposure vs 0.5 s timeout → scan aborts, device gets stopped

```python
dev.demo_cam.enabled = False
dev.demo_watchdog.enabled = False
dev.demo_det.enabled = True
scans.line_scan(dev.samx, -1, 1, steps=3, exp_time=0.1, relative=False)
```

Output: scan **aborted**, alarm
`StatusTimeoutError — Status timeout for demo_det in method 'on_trigger'`
(the exposure is a plain `DeviceStatus` that inherited the device default). Then:

```python
dev.demo_det.stop_calls()          # -> 1  : the timeout called device.stop() on the detector
```

Positive control — exposure shorter than the timeout, everything is fine:

```python
bec.device_manager.config_helper.send_config_request(
    action="update", config={"demo_det": {"deviceConfig": {"exposure": 0.2}}}
)
scans.line_scan(dev.samx, -1, 1, steps=3, exp_time=0.1, relative=False)   # completes
dev.demo_det.read()   # applied_timeout 0.5, status_timeout 0.5, stop_count 1.0
```

Set `exposure` back to `1.0` afterwards.

### Step 4 — watchdog status takes a healthy scan down

```python
dev.demo_det.enabled = False
dev.demo_watchdog.enabled = True
scans.line_scan(dev.samx, -1, 1, steps=3, exp_time=0.1, relative=False)
```

Output: aborted, `Status timeout for demo_watchdog in method 'on_trigger' waiting for signal error.`
The exposure itself had a 60 s budget; the `ExceptionStatus` on the error signal inherited the
0.5 s default and failed the composite.

### Step 5 — camera: the background trigger task inherits the default

```python
dev.demo_watchdog.enabled = False
dev.demo_cam.enabled = True
scans.line_scan(dev.samx, -1, 1, steps=3, exp_time=0.1, relative=False)
```

Output: aborted, `Status timeout for demo_cam in method 'on_trigger'` — the `submit_task`
status of the 1 s exposure failed at 0.5 s.

### Step 6 — positioner: the exception type is a lottery

```python
scans.umv(dev.demo_pos_ctor, 1, relative=False)
scans.umv(dev.demo_pos_ctor, 2, relative=False)
scans.umv(dev.demo_pos_ctor, 3, relative=False)
```

Each move fails after 0.5 s, but with different errors for identical failures — observed
`StatusTimeoutError`, then `UnknownStatusFailure`, then `StatusTimeoutError`. Two watchdogs
(the caller's `MoveStatus` and the internal completion status) race for the same deadline.
The standalone script (#6) additionally shows that `move(1, timeout=10)` is ignored.

### Step 7 — positioner config `timeout: -1` = "fail instantly", and it breaks unrelated scans

```python
bec.device_manager.config_helper.send_config_request(
    action="update", config={"demo_pos": {"deviceConfig": {"prefix": "SIM:DEMO:", "timeout": -1}}}
)
scans.umv(dev.demo_pos, 1, relative=False)
```

Accepted (ophyd setter path, no normalization) — the move fails at `elapsed=0.0`:
`StatusTimeoutError: Status MoveStatus(done=False, pos=demo_pos, elapsed=0.0, ...) failed to complete in specified timeout.`
The PR documents non-positive as "no timeout".

Worse: `demo_pos` is a baseline device that never moves during a line scan, yet now **every**
scan aborts:

```python
scans.line_scan(dev.samx, -1, 1, steps=3, exp_time=0.1, relative=False)
```

Output: aborted, `Status timeout for demo_pos in method 'complete'` — the `complete()`
fallback status (created and finished in consecutive statements) inherited the default and
lost the race against its own timer. Restore with `"timeout": 0.5`.

### Cleanup

```python
dev.demo_det.enabled = True; dev.demo_watchdog.enabled = True; dev.demo_cam.enabled = True
```

To remove the demo devices entirely, reload your session config (e.g.
`bec.config.load_demo_config()` if the session is the demo config).

### Not reproducible through BEC (script only)

NaN/inf (runtime config updates of `timeout` are rejected, see Step 2, so the only way in is
the YAML: `timeout: .nan` on a demo detector makes every status fail instantly, `.inf` makes
them never complete), numpy/bool inputs,
nested sub-devices, the pseudo motor, PandaBox, the mock crash and the opt-out semantics are
internal and are covered by the standalone script. The VME motor finding (#7) needs a
positioner with a `timeout` signal; the script uses `make_fake_device(EpicsUserMotorVME)`.

### A BEC quirk noticed on the way (not the PR)

At stage time devices see `scan_info.msg.scan_parameters["exp_time"] == 0` for `line_scan`
(the legacy field is not filled for v4 scans), while the scan itself runs with the requested
exposure. `SimCamera.on_stage` reads exactly that field. Worth a separate look.
