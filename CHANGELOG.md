# CHANGELOG


## v1.11.1 (2024-12-10)

### Bug Fixes

- Cleanup protocols, moved event_types to BECBaseProtocol
  ([`6e71da7`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/6e71da79c82aae9d847dccd3624643193c478fc4))

- Update protocls for docs in main
  ([`482e232`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/482e2320b9ec80cabc6b81a024e7bf851fa161be))


## v1.11.0 (2024-12-04)

### Bug Fixes

- Falcon and xMAP inherit ADBase
  ([`e37accd`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/e37accdf94f48b2f3de767ba736e1ca7595978c5))

It is needed for ND plugins to inspect the asyn pipeline.

### Documentation

- Update device list
  ([`49630f8`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/49630f82abdfa2588100a268798766b1a4d8b655))

### Features

- Xmap and FalconX devices
  ([`3cf9d15`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/3cf9d15bd35a50cac873d1b75effeb4b482f9efd))


## v1.10.6 (2024-12-04)

### Bug Fixes

- Bump ophyd version to 1.10, remove patch, fix corresponding test
  ([`f166847`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/f1668473872e4fd8231204c123dac6a07d201266))

### Continuous Integration

- Update ci syntax for dependency job
  ([`35f3819`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/35f3819c03fc4ad16fccc72a5fdea1f59318a764))


## v1.10.5 (2024-11-19)

### Bug Fixes

- Add __init__ to tests folder
  ([`2034539`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/203453976981b7077815a571697447c5e96aa747))

### Continuous Integration

- Update no pragma for coverage
  ([`cd64d57`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/cd64d57c658f3ff166aa610153e534b9c82135aa))


## v1.10.4 (2024-11-19)

### Bug Fixes

- **device base**: Added missing property to BECDeviceBase
  ([`cc0e26a`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/cc0e26a91a84b015b03aa7656ccd0528d7465697))

- **sim**: Ensure to update the state before setting the status to finished
  ([`2e8ddbb`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/2e8ddbb1adafca0727a5235b24e7cbe8de078708))


## v1.10.3 (2024-11-18)

### Bug Fixes

- Allow bec v3
  ([`93cd972`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/93cd972040d1e213dabcfdea5e9bbf7a2c48fad8))

### Build System

- Allow bec v3
  ([`bd3897f`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/bd3897fe842cdebcb7bcc41646bd53185418674d))

### Documentation

- Update device list
  ([`6f50660`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/6f50660e8ad5f86ac6b6d2a74897912ccaf0f070))


## v1.10.2 (2024-10-25)

### Bug Fixes

- Ensure filepath is set to the required value before waiting
  ([`db9e191`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/db9e191e4a5c1ee340094400dff93b7ba10f8dfb))


## v1.10.1 (2024-10-25)

### Bug Fixes

- Ophyd patch, compatibility with Python >=3.12
  ([`97982dd`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/97982dd1385f065b04aa780c91aee9f67b9beda2))

"find_module" has been deleted from Finder class

### Refactoring

- Refactored SimCamera write_to_disk option to continously write to h5 file.
  ([`41c54aa`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/41c54aa851e7fcf22b139aeb041d000395524b7e))


## v1.10.0 (2024-10-22)

### Bug Fixes

- Improved patching of Ophyd 1.9
  ([`8a9a6a9`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/8a9a6a9910b44d55412e80443f145d629b1cfc2f))

### Features

- Add test device for return status for stage/unstage
  ([`f5ab78e`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/f5ab78e933c2bbb34c571a72c25a7fc5c2b20e65))


## v1.9.6 (2024-10-17)

### Bug Fixes

- Cleanup and bugfix in positioner; closes #84
  ([`6a7c074`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/6a7c0745e33a2b2cc561b42ad90e61ac08fb9d51))

### Refactoring

- Cleanup sim module namespace; closes #80
  ([`fa32b42`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/fa32b4234b786d93ddf872c7a8220f2d0518b465))


## v1.9.5 (2024-10-01)

### Bug Fixes

- Bugfix for proxy devices
  ([`b1639ea`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/b1639ea3baddec722a444b7c65bdc39d763b7d07))

- Fixed SimWaveform, works as async device and device_monitor_1d simultaneously
  ([`7ff37c0`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/7ff37c0dcdd87bfa8f518b1dd7acc4aab353b71f))

### Refactoring

- Cleanup of scan_status prints in scaninfo_mixin
  ([`449dadb`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/449dadb593a0432d31f905e4e507102d0c4f3fd6))


## v1.9.4 (2024-10-01)

### Bug Fixes

- Increased min version of typeguard
  ([`e379282`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/e3792826644e01adf84435891d500ec5bef85cda))

### Build System

- Allow numpy v2
  ([`825a7de`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/825a7dee5e948d9decb4e8649c0573a2d9d4b83f))


## v1.9.3 (2024-09-06)

### Bug Fixes

- Remove bodge (readback) in SimMonitor
  ([`cd75fc0`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/cd75fc0e01e565445f7176e52faada264544d439))


## v1.9.2 (2024-09-05)

### Bug Fixes

- Change inheritance for simmonitor from device to signal
  ([`a675420`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/a6754208a0991f8ccf546cbb2bee015f6daecb93))

### Refactoring

- Bodge to make simmonitor compatible with tests; to be removed asap
  ([`9d9a5fe`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/9d9a5fe305981f845c87e3417dd1072d2b8692b0))
