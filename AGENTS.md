# Repository Guidelines — `ophyd_devices`

`ophyd_devices` provides reusable ophyd hardware support and simulation devices for
[BEC](https://github.com/bec-project/bec). Prefer focused changes, follow existing local patterns,
and verify the smallest relevant test scope.

This file is an agent-oriented operating manual. User-facing documentation lives at
<https://bec.readthedocs.io> and is authored in the separate `bec_docs` repository.
Treat `pyproject.toml` as the source of truth for dependencies, scripts, and tool configuration.

## Core Rules

- Use `PSIDeviceBase` when a device needs BEC lifecycle or business logic. A device that merely
  exposes signals can use plain `ophyd.Device`, regardless of the communication backend.
- Separate reusable device control from beamline-specific business logic in `on_*` hooks.
- Prefer repository statuses, signals, and helpers when a BEC-aware counterpart exists.
- Return promptly from device-server calls. Represent unfinished work with a status.
- Implement safe interruption through `on_stop()` and register cancellable statuses.
- Use `bec_signals.py` for BEC live data, progress, and file events.
- Check the relevant device protocols when changing interfaces.
- Add an example configuration for each new reusable device family.
- Do not edit `ophyd_devices/devices/device_list.md`; CI generates it.
- Follow existing local patterns before introducing a new abstraction.
- Keep diffs focused and preserve unrelated local changes.
- Add regression tests for bug fixes.
- Do not commit, push, open a PR, or post a review unless explicitly requested.

## First Read

Read the affected implementation and its tests. For unfamiliar areas, start here:

- `ophyd_devices/interfaces/base_classes/psi_device_base.py` — device lifecycle and BEC integration
- `ophyd_devices/interfaces/base_classes/psi_positioner_base.py` — motion
- `ophyd_devices/interfaces/base_classes/psi_pseudo_device_base.py` — pseudo devices
- `ophyd_devices/interfaces/base_classes/psi_pseudo_motor_base.py` — pseudo motors
- `ophyd_devices/interfaces/protocols/bec_protocols.py` — expected device contracts
- `ophyd_devices/utils/psi_device_base_utils.py` — statuses, tasks, and file helpers
- `ophyd_devices/utils/bec_signals.py` — live data publishing
- `tests/conftest.py` and `ophyd_devices/tests/utils.py` — reusable test helpers
- `README.md` — project overview

## Repo Layout

- `ophyd_devices/interfaces/` — base classes, protocols, and device configuration templates
- `ophyd_devices/devices/` — concrete devices and the generated device list
- `ophyd_devices/sim/` — simulation devices and data generators
- `ophyd_devices/utils/` — shared signals, statuses, controllers, and other helpers
- `ophyd_devices/configs/` — example device configurations
- `tests/` — unit tests

Related but separate repositories:

- `bec` — core messaging, scans, services, and the client
- `bec_widgets` — GUI widgets
- `bec_docs` — published documentation
- beamline plugin repositories — beamline-specific devices, scans, and widgets

## Local Overlay

If `AGENTS_PERSONAL.md` exists beside this file, read it as an extension of these instructions.
Its machine-specific environment and workflow guidance takes precedence over the corresponding
sections here. Keep it local and untracked; do not copy its contents into committed files.

## Common Task Routing

If you change:

- `ophyd_devices/interfaces/base_classes/*`: inspect relevant protocols and affected concrete and
  simulation devices; test staging, subscriptions, movement, and stop behavior.
- `ophyd_devices/utils/psi_device_base_utils.py`: check timeout handling and composition across
  status subclasses.
- `ophyd_devices/utils/bec_signals.py`: check device-server consumers and report compatibility
  risks for `bec` and `bec_widgets`.
- `ophyd_devices/sim/*`: check the affected device and tests consuming its scan data.
- `ophyd_devices/devices/*` or vendor integrations: add targeted device tests; include an example
  configuration and validation notes for a new reusable device family.
- `ophyd_devices/configs/*`: run `ophyd_test --config <changed-config>` and inspect its report.
- Documentation or templates: verify referenced paths, commands, examples, and metadata.
  A broad unit test run is unnecessary when executable behavior is unchanged.

Reusable hardware support belongs here. Devices specific to one beamline belong in its plugin
repository. Route core messaging, scans, and service changes to `bec`, GUI behavior to
`bec_widgets`, and published documentation to `bec_docs`.

## Writing A Device

### Control and business logic

The device's base control class defines how to communicate with the hardware: signal
definitions, commands, protocol handling, and device state. Keep this layer reusable across
beamlines and implement it in `ophyd_devices`. Plain ophyd control classes may be composed into
or combined with a class that uses `PSIDeviceBase` when business logic is needed.

A device that only exposes a collection of signals needs no business-logic layer; plain
`ophyd.Device` is enough. For example, `SLSOperatorMessages` in
`ophyd_devices/devices/sls_devices.py` groups operator messages and their dates using dynamic
components without scan-specific behavior. This applies equally to EPICS and other communication
backends; the need for business logic determines the base class, not the transport.

The `on_*` hooks typically describe business logic: how a beamline uses that control interface
during a scan. For example, the control class exposes acquisition and trigger-mode commands;
a beamline's `on_stage()` chooses the trigger mode and acquisition settings for its experiment,
and `on_trigger()` starts acquisition through the control interface.

Implement bespoke hook behavior in a subclass in the beamline plugin repository. Keep shared
lifecycle behavior generic, and make hooks call reusable control methods rather than duplicating
PV definitions or communication code. This lets beamlines share the same hardware support while
choosing their own acquisition and scan behavior.

### Base classes and hooks

- When lifecycle or business logic is needed, use `PSIDeviceBase` to integrate the control class
  with BEC's lifecycle, scan information, statuses, and subscriptions. Do not add it solely to
  expose a collection of signals.
- Use the lifecycle hooks provided by the base class rather than replacing its wrappers:
  `on_init`, `on_connected`, `on_stage`, `on_pre_scan`, `on_trigger`, `on_complete`,
  `on_kickoff`, `on_unstage`, `on_stop`, and `on_destroy`.
- When implementing a device inheriting from `PSIDeviceBase`, copy the entire
  "Beamline Specific Implementations" section from
  `ophyd_devices/interfaces/base_classes/psi_device_base.py`, including its separator, all ten
  hooks, signatures, and docstrings. Keep the hooks together in that order, including unused
  hooks, so readers can quickly identify the device's business logic.
- Put helper methods outside that section under a separate separator, for example:

  ```python
  ########################################
  #  Beamline Specific Implementations   #
  ########################################

  # All ten on_* hooks belong here.

  ########################################
  #            Helper Methods            #
  ########################################
  ```

- When replacing a hook in a subclass, preserve any required parent behavior with `super()`;
  copied hook stubs must not silently disable an inherited implementation.
- Constructors and `on_init()` must not communicate with devices. Use `on_init()` only for local
  initialization; do not read hardware state or send commands there.
- `on_connected()` is the first hook allowed to communicate with devices and send instructions,
  such as setting hardware defaults. The device server calls it once an enabled device has
  connected; plain instantiation, unit tests, and `ophyd_test` do not, so call it explicitly in
  tests that rely on it. It is not a per-scan hook. Use the scan lifecycle hooks for
  scan-specific instructions and access scan parameters through `self.scan_info.msg`.
- Check the relevant protocols when adding or changing a device interface. Read the base-class
  implementation for hook return semantics; the protocol signatures alone do not describe them.

### Completion and interruption

- Acquisition, staging, completion, and movement must return promptly to the device server.
  Represent unfinished work with a status; do not wait, sleep, or poll on the calling thread.
- Import statuses from `ophyd_devices.utils.psi_device_base_utils`, including `DeviceStatus`,
  `MoveStatus`, and `StatusBase`. These provide BEC timeout diagnostics and status composition.
  Prefer repository helpers whenever a BEC-aware counterpart exists.
- Hooks such as `on_stage()` and `on_complete()` may return a status or `None`. Return `None`
  only when there is no outstanding work. In particular, `complete()` converts `None` into
  an already-finished status; return a pending status while acquisition or file writing continues.
- Register statuses that must fail on interruption with `self.cancel_on_stop(status)`.
  Implement hardware interruption in `on_stop()` and make repeated calls safe. Cancelling a
  status does not by itself stop hardware or a background task.
- Preserve base-class stop and destroy behavior. Release subscriptions, threads, sockets, and
  other owned resources in `on_destroy()`; worker code must be able to exit on interruption.

### Signals and configuration

- Set signal `kind` deliberately. `normal` and `hinted` signals appear in `read()`; `hinted`
  also selects default BEC scan readouts. `config` signals appear in `read_configuration()`;
  `omitted` signals appear in neither. Treat changes to kinds and names as data-interface changes.
- Use the signals in `ophyd_devices/utils/bec_signals.py` for BEC live data, progress, and file
  events. Reuse their message formats instead of publishing custom Redis messages.
- Add an example configuration under `ophyd_devices/configs/` for a new reusable device family.
- Give each device class a docstring with a useful first-line description. CI uses it to generate
  `ophyd_devices/devices/device_list.md`; do not edit that generated file by hand.

### USER_ACCESS

- Prefer methods over properties for functionality exposed through `USER_ACCESS`.
- Give exposed methods verb-based names that describe the operation, such as `set_velocity()`
  or `get_velocity()`, rather than noun-only names such as `velocity()`.

## Validation


Add regression tests for bug fixes. New device tests must cover instantiation, the relevant
protocol, and safe `stop()` behavior. For asynchronous changes, also exercise completion,
failures, and interruption while work is pending.

Use mocked EPICS and sockets for unit tests. Reuse `get_mock_scan_info` from
`ophyd_devices/tests/utils.py` and existing fixtures; use simulation devices when a working device
is needed. Keep tests independent of execution order.

Run the smallest relevant test target first, with `--random-order` when available:

```bash
python -m pytest --random-order tests/test_psi_device_base.py
```

For a full unit test or coverage run:

```bash
python -m pytest --random-order tests
coverage run --source=./ophyd_devices --omit='*/ophyd_devices/tests/*' \
  -m pytest --random-order tests
coverage report
```

`ophyd_test` writes reports to `./device_test_reports` by default. Use `--connect` only when the
user explicitly requests hardware validation and the target is reachable. Report whether device
validation used mocks, simulation, or real hardware; include the model and firmware when known.

## Running BEC Locally

Full service validation needs Redis, usually at `localhost:6379`, and an environment with BEC
services installed. Unit tests normally use mocks and need no hardware.

When service management is part of the requested validation, start services and open the client:

```bash
bec-server start
bec
```

Run the client in another shell. Restart the device server after changing code it has already
loaded; otherwise a running session may use stale code.

## Style And Change Hygiene

- Use Python 3.11-compatible syntax, four-space indentation, and a 100-character line limit.
- Use f-strings and `pathlib`.
- Type-annotate new public functions and methods; document public APIs.
- Follow existing naming and docstring conventions.
- Run Black and isort on changed Python files using `pyproject.toml` configuration.
- Avoid formatting unrelated files and introducing new Pylint warnings.

## Development Environment

Use an existing suitable environment when available. To create one, use Python 3.11 or newer:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
python -c "import ophyd_devices; print(ophyd_devices.__file__)"
```

Verify imports resolve to the checkout under test. Separate worktrees need separate editable
installations; do not repoint another task's environment. The `dev` extra includes `bec-server`.

## Platform Notes

Keep code portable across macOS and Linux. Windows is unsupported and untested.

## Commit And PR Notes

Branch from `main` for new work. Continue an existing PR on its current branch.


The manual PR template lives at `.github/PULL_REQUEST_TEMPLATE/pull_request_template.md`.
When writing a description:

- Lead with the concrete problem and resulting behavior. For a bug fix, explain the trigger and
  before/after result. Describe the final change for a reviewer who has not followed the work.
- Keep detail proportional to the change. Replace prompts and remove unused sections; avoid a
  file-by-file recap. Put lengthy examples in a `<details>` block and label before/after output.
- Use `Closes #123` for resolved issues and `Related to #123` for partial work. Link companion PRs
  and `bec_docs` updates, including any required merge or deployment order.
- Give exact test commands or manual steps and expected outcomes. Separate instructions for
  reviewers from checks already performed; report results and material limitations honestly.
- Explain compatibility changes, affected consumers, defaults, migrations, and remaining limits.
  Include hardware/simulation validation and configuration-check results where applicable.
- State whether documentation was updated or why it is unnecessary. Add design tradeoffs and
  follow-ups only when they help assess the change. Update the description when scope changes.

Use Conventional Commit titles: `<type>(<scope>): <summary>`. Allowed types are `build`, `chore`,
`ci`, `docs`, `feat`, `fix`, `perf`, `refactor`, `style`, and `test`. Mark breaking changes with
`!` or a `BREAKING CHANGE:` footer.

For reviews, use `.github/pull_request_review_template.md`. Separate findings introduced or
exposed by the change from inherited issues and optional suggestions. Identify the reviewed
revision, give concrete evidence, and state validation limits. Return the review in chat unless
posting to GitHub is explicitly requested.
