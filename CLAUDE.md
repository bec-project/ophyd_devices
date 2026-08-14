# CLAUDE.md — `ophyd_devices`

@AGENTS.md

The guidelines above are imported from [`AGENTS.md`](AGENTS.md) (single source of
truth). The points that matter most in day-to-day work:

- **Check for `AGENTS_PERSONAL.md` first.** If it exists, it extends `AGENTS.md` with
  machine-specific environment setup and takes precedence over the generic venv/pip instructions there.
  It is untracked and personal — never commit it, and never assume it exists.
- **Inherit from `PSIDeviceBase` / `PSIPositionerBase` / `PSIPseudoDeviceBase`**
  (`ophyd_devices/interfaces/base_classes/`), never from `ophyd.Device` directly — the base classes wire
  up the subscriptions, `scan_info`, and task/file handling that BEC's device server expects.
- **Import the `ophyd_devices` counterpart, never the plain `ophyd` one, wherever one exists.** The
  status classes in `ophyd_devices/utils/psi_device_base_utils.py` (`StatusBase`, `Status`,
  `DeviceStatus`, `MoveStatus`, `SubscriptionStatus`, `AndStatus`) subclass ophyd's to add timeout
  diagnostics and `&` composition, and the module adds BEC-only `CompareStatus`, `ExceptionStatus`,
  `TransitionStatus`, `TaskStatus`; BEC-publishing signals live in `ophyd_devices/utils/bec_signals.py`.
  Importing from `ophyd` directly silently drops that behaviour. Plain `ophyd` imports are correct only
  where there is no counterpart (`Component`, `EpicsSignal`, `Kind`, …).
- **Never block the device server.** Long work goes through `TaskHandler` and reports completion with a
  `DeviceStatus`. Always implement a safe `stop()`.
- **Set `kind` deliberately** (`hinted` / `config` / `omitted`) — it decides what lands in the scan file.
  Emit BEC data through `ophyd_devices/utils/bec_signals.py`, and check the device against the protocols
  in `interfaces/protocols/bec_protocols.py`.
- **Docstring every device class** — the first line feeds the generated
  `ophyd_devices/devices/device_list.md`, which is CI-generated and must not be hand-edited.
- **Tests**: `python -m pytest --random-order ./tests`. Mock EPICS and sockets; build on the `sim/`
  devices; use `get_mock_scan_info` and the `tests/conftest.py` fixtures.
- **Validate configs** with `ophyd_test --config <file.yaml>` (add `--connect` for real hardware).
- **Format before finishing**: `black --line-length=100 --skip-magic-trailing-comma .` and
  `isort --line-length=100 --profile=black --multi-line=3 --trailing-comma .`.
- **A device used at only one beamline belongs in that beamline's plugin repo**, not here.
- **Do not commit or push unless explicitly asked, and never open a pull request.** If you do commit,
  write a single Conventional Commits line — it is parsed into the published changelog. Opening the PR
  is the human's step; leave them the summary and test output they need for it, including whether a new
  device was tested against real hardware or only in simulation.
