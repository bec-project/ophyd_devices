# Repository Guidelines — `ophyd_devices`

`ophyd_devices` is the hardware abstraction layer for
[BEC (Beamline Experiment Control)](https://github.com/bec-project/bec). It extends
[ophyd](https://github.com/bluesky/ophyd) with reusable device support for motion controllers,
detectors, shutters, undulators, monochromators, and simulation devices that let BEC run end-to-end
without hardware attached.

This file is an agent-oriented operating manual. User-facing documentation lives at
<https://bec.readthedocs.io>; general ophyd concepts are documented at
<https://blueskyproject.io/ophyd/>.

## Core Rules

- Inherit from the `PSI*` base classes instead of `ophyd.Device` directly.
- Prefer `ophyd_devices` status, signal, and helper classes when this repo provides counterparts to
  plain `ophyd` classes.
- Never block the device server in `stage()`, `trigger()`, or movement code; return a status object
  that reports completion instead.
- Set signal `kind` deliberately. `hinted` data is recorded by default; `omitted` and `config` are
  not.
- Always implement safe interrupt behavior through `stop()`.
- Emit BEC-facing data through `ophyd_devices/utils/bec_signals.py` rather than inventing message
  shapes.
- Check device implementations against the protocols in `interfaces/protocols/bec_protocols.py`.
- Add an example config under `ophyd_devices/configs/` when adding a reusable device family.
- Do not edit `ophyd_devices/devices/device_list.md` by hand; CI regenerates it on pushes to `main`.
- Keep diffs focused. Avoid unrelated refactors while fixing a specific issue.
- Add regression tests for bug fixes.
- Do not commit, push, or open PRs unless explicitly asked.

## First Read

Start here when orienting yourself:

- `ophyd_devices/interfaces/base_classes/psi_device_base.py` — base class for BEC-aware devices
- `ophyd_devices/interfaces/base_classes/psi_positioner_base.py` — base class for BEC-aware motors
- `ophyd_devices/interfaces/protocols/bec_protocols.py` — contracts expected by BEC
- `ophyd_devices/utils/psi_device_base_utils.py` — status classes and `FileHandler`
- `ophyd_devices/utils/bec_signals.py` — signals that publish BEC live data
- `ophyd_devices/utils/bec_scaninfo_mixin.py` — scan metadata integration
- `ophyd_devices/sim/` — simulation devices and data generators
- `tests/conftest.py` and `ophyd_devices/tests/utils.py` — reusable test fixtures and helpers
- `README.md` — human-facing project overview

## Repo Layout

`ophyd_devices/` is the importable package:

- `ophyd_devices/interfaces/base_classes/` — classes to inherit from:
  `PSIDeviceBase`, `PSIPositionerBase`, `PSIPseudoDeviceBase`, `PSIPseudoMotorBase`
- `ophyd_devices/interfaces/protocols/` — `typing.Protocol` definitions for BEC device contracts
- `ophyd_devices/interfaces/device_config_templates/` — templates for generated device config
  entries
- `ophyd_devices/devices/` — concrete device implementations and generated `device_list.md`
- `ophyd_devices/sim/` — simulation framework, including `SimPositioner`, `SimCamera`,
  `SimMonitor`, `SimWaveform`, `SimFlyer`, and `sim_data.py`
- `ophyd_devices/utils/` — shared helpers for signals, scan info, controllers, sockets, static
  config checks, statuses, and async tasks
- `ophyd_devices/configs/` — example device configuration YAML files, including the local
  simulation config
- `ophyd_devices/npoint/`, `rt_lamni/`, `sls_devices/`, `smaract/` — vendor- and facility-specific
  integrations
- `tests/` — flat unit test suite, usually one `test_<area>.py` file per area

Related but separate repos:

- `bec` — core library and services; `bec_lib` is a direct dependency, and `bec_server` drives
  these devices from the device server
- `bec_widgets` — Qt widgets and GUI toolkit that display device data
- `bec_docs` — published documentation
- beamline plugin repos — beamline-specific devices, scans, and widgets

A device used at exactly one beamline belongs in that beamline's plugin repository. This repository
is for hardware support that is reusable across beamlines and facilities.

Treat `pyproject.toml` as the source of truth for dependencies, scripts, release settings, and tool
configuration.

## Local Overlay

If `AGENTS_PERSONAL.md` exists beside this file, treat it as an extension of this file.
Machine-specific environment and workflow instructions in `AGENTS_PERSONAL.md` take precedence over
the generic guidance here.

- `AGENTS_PERSONAL.md` is untracked and local to one developer machine
- do not commit it
- do not reference it from committed files
- do not assume it exists

## Common Task Routing

If you change:

- `ophyd_devices/interfaces/base_classes/*`: inspect relevant protocols, simulation devices, and
  existing concrete devices; run focused tests around staging, subscriptions, movement, and stop
  behavior
- `ophyd_devices/utils/psi_device_base_utils.py`: review all status subclasses and timeout behavior;
  run tests that compose statuses
- `ophyd_devices/utils/bec_signals.py`: check device-server and BEC consumer expectations; report
  any compatibility risk with `bec` and `bec_widgets`
- `ophyd_devices/sim/*`: validate affected simulation devices and any tests that rely on simulated
  scan data
- `ophyd_devices/configs/*`: run `ophyd_test` against the changed config; use `--connect` only when
  explicitly validating real hardware
- `ophyd_devices/devices/*`: add or update targeted tests; for a new reusable family, include an
  example config and hardware/simulation validation notes
- docs only: no broad test run is required unless commands, paths, examples, or generated lists
  changed

If the requested change sounds like one of these, it probably belongs elsewhere:

- core BEC messaging, scan logic, or service behavior: `bec`
- published docs or install guide changes: `bec_docs`
- GUI/widget behavior: `bec_widgets`
- beamline-specific hardware or one-off device logic: a beamline plugin repo

## Writing A Device

Inherit from a `PSI*` base class, not from `ophyd.Device` directly. `PSIDeviceBase` wires up the
subscription types BEC's device manager expects, including `readback`, `value`, `done_moving`,
`motor_is_moving`, `progress`, `file_event`, `device_monitor_1d`, and `device_monitor_2d`. It also
provides `scan_info`, `device_manager`, and `FileHandler`. A bare `ophyd.Device` can appear to work
locally and then misbehave inside a running BEC deployment.

```python
from ophyd import Component as Cpt, EpicsSignal, EpicsSignalRO

from ophyd_devices.interfaces.base_classes.psi_device_base import PSIDeviceBase


class MyDetector(PSIDeviceBase):
    """One-line description; this text reaches the generated device list."""

    acquire = Cpt(EpicsSignal, "ACQ", kind="omitted")
    readback = Cpt(EpicsSignalRO, "VAL", kind="hinted")

    def on_stage(self) -> None:
        ...  # prepare for a scan

    def on_complete(self) -> None:
        ...  # wait for acquisition to finish

    def on_unstage(self) -> None:
        ...  # release resources
```

Where `ophyd_devices` provides a counterpart to an `ophyd` class, import the `ophyd_devices` one.
Several classes are subclassed here to add BEC behavior, and the plain ophyd version silently loses
it. The status classes in `ophyd_devices/utils/psi_device_base_utils.py` add timeout diagnostics
that report which device and call is stuck, plus the `&` operator for composing statuses.

```python
from ophyd_devices.utils.psi_device_base_utils import DeviceStatus, MoveStatus  # yes
from ophyd.status import DeviceStatus, MoveStatus  # no
```

This applies to anything re-exported from `ophyd_devices/__init__.py`. Import directly from `ophyd`
only for classes with no BEC-aware counterpart here, such as `Component`, `EpicsSignal`, `Kind`, and
`PositionerBase`.

## Validation

Run the smallest relevant test target first. For substantial changes, cross-module changes, or work
that touches shared device contracts, run the affected tests before finishing.

Unit tests are the default. CI runs them with `--random-order`, so local validation should do the
same when practical. Mock EPICS and sockets. Use `get_mock_scan_info` from
`ophyd_devices/tests/utils.py` and fixtures in `tests/conftest.py` instead of constructing scan
metadata by hand. Prefer `sim/` devices when you need a working device in a test.

Reference test commands:

```bash
python -m pytest --random-order ./tests
python -m pytest -v --maxfail=2 --junitxml=report.xml --random-order ./tests
coverage run --source=./ophyd_devices --omit=*/ophyd_devices/tests/* \
  -m pytest --random-order ./tests
coverage report
```

Every new device class needs at least tests that show:

- it instantiates
- it satisfies the relevant protocol
- its `stop()` is safe to call

### Validating A Device Configuration

`ophyd_test` statically analyzes a device configuration YAML and can optionally connect to hardware:

```bash
ophyd_test --config ./ophyd_devices/configs/ophyd_devices_simulation.yaml
ophyd_test --config /path/to/beamline_config.yaml --connect --timeout-per-device 30
```

Reports are written to `./device_test_reports` by default. Run this before proposing a configuration
change for a real beamline. Do not use `--connect` unless the user explicitly wants hardware
validation and the target beamline is reachable.

## Running With BEC Locally

No EPICS IOC or hardware is required for most development. Unit tests mock connections, and the
simulation devices provide a working beamline in software.

Redis must be reachable, usually at `localhost:6379`, for full BEC service validation.

Start services from the `bec` repo or an environment where `bec-server` is installed:

```bash
bec-server start
```

Open the client in another shell:

```bash
bec
```

Use `bec-server restart` after changing code that is loaded by an already-running device server.
Otherwise you may be testing stale service code.

## Style And Change Hygiene

- Python 3.11+, 4-space indentation, 100-character line limit
- use `f`-strings instead of `%` formatting or `str.format()`
- use `pathlib` instead of manual path-string manipulation
- type-annotate new public functions and methods
- follow the existing docstring style
- public functions, classes, and modules should have docstrings
- device class docstrings are required; the first line is picked up by the generated device list
- use `snake_case` for modules, functions, and test files
- use `PascalCase` for device classes; names should read as the hardware they represent, such as
  `SimPositioner`, `PSIMotor`, or `DelayGenerator645`
- avoid formatting or import-order churn in untouched files

Run Black and isort on changed files or the affected package. The whole-repo equivalents are:

```bash
black --line-length=100 --skip-magic-trailing-comma .
isort --line-length=100 --profile=black --multi-line=3 --trailing-comma .
```

Pylint runs in CI against `ophyd_devices`. Do not introduce new warnings. Beamline-idiomatic names
such as `scanID`, `RID`, `pointID`, `*_1D`, and `*_2D` are allowed by `pyproject.toml`.

## Development Environment

Requires Python 3.11+. CI currently runs Python 3.11, 3.12, and 3.13.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
```

The `dev` extra pulls in `bec-server`, which is what device-server-facing tests exercise. Verify
that the environment resolves to this checkout:

```bash
python -c "import ophyd_devices; print(ophyd_devices.__file__)"
```

If you are working in a separate clone or git worktree, reinstall editable packages from that
checkout. A single virtualenv cannot point at multiple editable copies of the same package reliably.

## Platform Notes

Code must run on macOS and Linux. Windows is unsupported and untested. Prefer portable `pathlib`
usage and do not add Windows-specific branches unless explicitly requested.

## Commit And PR Notes

- Branch from `main` for new work
- use Conventional Commits: `<type>(<scope>): <summary>`
- allowed types are `build`, `chore`, `ci`, `docs`, `feat`, `fix`, `perf`, `refactor`, `style`, and
  `test`
- breaking changes need `!` or a `BREAKING CHANGE:` footer
- leave the eventual PR author with a short summary of what changed, why, and what you validated
- for a new device, state which hardware it was tested against, or state explicitly that it was
  tested only in simulation
- update `bec_docs` when necessary
