# Ophyd Devices

ophyd-devices is an extension to [ophyd](https://github.com/bluesky/ophyd) and provides device support for devices not covered by the standard EPICS implementation in ophyd. 

## Installation

Use the package manager [pip](https://pip.pypa.io/en/stable/) to install ophyd-devices.

```bash
pip install ophyd-devices
```

For development, clone the repository and install the package in editable mode:

```bash
git clone https://gitlab.psi.ch/bec/ophyd_devices.git
cd ophyd_devices
pip install -e .[dev]
```

## Documentation

The documentation for the usage with BEC can be found  [here](https://bec.readthedocs.io/en/latest/). More general documentation can be found [here](https://blueskyproject.io/ophyd/).

## Contributing

Merge requests are very welcome! For major changes, please open an issue first to discuss what you would like to change.
All commits should use the Angular commit scheme:

```
<type>(<scope>): <short summary>
  │       │             │
  │       │             └─⫸ Summary in present tense. Not capitalized. No period at the end.
  │       │
  │       └─⫸ Commit Scope: animations|bazel|benchpress|common|compiler|compiler-cli|core|
  │                          elements|forms|http|language-service|localize|platform-browser|
  │                          platform-browser-dynamic|platform-server|router|service-worker|
  │                          upgrade|zone.js|packaging|changelog|docs-infra|migrations|ngcc|ve|
  │                          devtools
  │
  └─⫸ Commit Type: build|ci|docs|feat|fix|perf|refactor|test
```

The `<type>` and `<summary>` fields are mandatory, the `(<scope>)` field is optional.
##### Type

Must be one of the following:

* **build**: Changes that affect the build system or external dependencies (example scopes: gulp, broccoli, npm)
* **ci**: Changes to our CI configuration files and scripts (examples: CircleCi, SauceLabs)
* **docs**: Documentation only changes
* **feat**: A new feature
* **fix**: A bug fix
* **perf**: A code change that improves performance
* **refactor**: A code change that neither fixes a bug nor adds a feature
* **test**: Adding missing tests or correcting existing tests


Please make sure to update tests as necessary.

## License

[BSD-3-Clause](https://choosealicense.com/licenses/bsd-3-clause/)