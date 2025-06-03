# CHANGELOG


## v1.20.0 (2025-06-03)

### Continuous Integration

- Add issue sync to bec project
  ([`e47472d`](https://github.com/bec-project/ophyd_devices/commit/e47472d8861c6e7242a416235280da522532d036))

### Features

- Restructure bec signals
  ([`585fbbb`](https://github.com/bec-project/ophyd_devices/commit/585fbbbb71deddf7921ef0932236699ef08316e6))

- **waveform**: Add bec signal to waveform simulation
  ([`b02485c`](https://github.com/bec-project/ophyd_devices/commit/b02485c4611a3a2e4cb7cb3e80142f2be907a7be))


## v1.19.0 (2025-05-30)

### Bug Fixes

- **PreviewSignal**: Use dotted name instead of signal name
  ([`780cc64`](https://github.com/bec-project/ophyd_devices/commit/780cc641c639204889f61c3a51ee7a43a275cde0))

### Continuous Integration

- Fix semantic release variables for github release
  ([`d8926e0`](https://github.com/bec-project/ophyd_devices/commit/d8926e0b126529e360b53f804918b93ddcd2087e))

### Features

- **sim**: Add preview signal to camera simulation
  ([`ed9d813`](https://github.com/bec-project/ophyd_devices/commit/ed9d8136b878950a7b4683fb2cd3e383ed2b6f49))


## v1.18.0 (2025-05-30)

### Features

- Add bec_signals with BECMessages to utils
  ([`97adcb8`](https://github.com/bec-project/ophyd_devices/commit/97adcb8f8d4b146c338b5028a6d51b21422cb891))

### Refactoring

- Improve typehints, remove redundant signal
  ([`81d2314`](https://github.com/bec-project/ophyd_devices/commit/81d2314c8ba60ab760651959a33fb0f777682d22))


## v1.17.0 (2025-05-26)

### Chores

- **formatter**: Upgrade to black v25
  ([`673be87`](https://github.com/bec-project/ophyd_devices/commit/673be87a2d449b4860adaf921679b68574e431c6))

### Continuous Integration

- Add github actions
  ([`a458d69`](https://github.com/bec-project/ophyd_devices/commit/a458d6942d45356cf2dfdc32fb1dfb74c271fdf1))

### Documentation

- Update device list
  ([`4625dee`](https://github.com/bec-project/ophyd_devices/commit/4625dee50bee9211b8fa8af0470ba38f40c6ded4))

- Update device list
  ([`b69f229`](https://github.com/bec-project/ophyd_devices/commit/b69f229da5a52ac18ea247387bf7db4d2a70b16c))

### Features

- **areadetector**: Add ADASItpx device
  ([`bb60ed1`](https://github.com/bec-project/ophyd_devices/commit/bb60ed1cef86bffa810ebb49f5f8aac2b75e073c))

### Refactoring

- **dxp**: Refactor dxp integration, support rois with proper kinds in EpicsMCARecord
  ([`f6e3bf3`](https://github.com/bec-project/ophyd_devices/commit/f6e3bf36ce7476e78bfefdafc4663815fd74db42))

- **dxp**: Remove _default_read_attrs from base integration
  ([`19a1d84`](https://github.com/bec-project/ophyd_devices/commit/19a1d84186f21d4f2eeae0a7afed5d07d542e4af))

- **psi-device-base**: Add device_manager to signature
  ([`a44b07c`](https://github.com/bec-project/ophyd_devices/commit/a44b07c5da063c5186dbb6522d2d7efa3b9da635))

- **psi-device-base**: Remove device_manager from kwargs, improve Status return on stage/unstage
  ([`a7bffb8`](https://github.com/bec-project/ophyd_devices/commit/a7bffb8e3ad631eb84c33f3a9e26ef57e0137726))

### Testing

- **psi-device-base**: Enhance PSIDeviceBase tests with additional user method hooks
  ([`0cb64d1`](https://github.com/bec-project/ophyd_devices/commit/0cb64d1ea86464451009d43efbbd572dc03e44ce))


## v1.16.1 (2025-04-30)

### Bug Fixes

- Add prefix to signature of PSIDeviceBase
  ([`ab63839`](https://github.com/bec-project/ophyd_devices/commit/ab6383959f1eb45efd4fff52332ebc1442a01c78))


## v1.16.0 (2025-04-07)

### Features

- **sim_waveform**: Added option to emit data with add_slice
  ([`21746e5`](https://github.com/bec-project/ophyd_devices/commit/21746e5445f32cfd41e6cca80cae5acc45c808ec))

### Refactoring

- Update schema validation to use BEC device model
  ([`7797e40`](https://github.com/bec-project/ophyd_devices/commit/7797e4003b1e0fb3b9acd33aa937c80405febbd8))

- **psi_device_base**: Add method to wait for a condition to PSIDeviceBase
  ([`1fd4fc7`](https://github.com/bec-project/ophyd_devices/commit/1fd4fc7f21a70804c2b8956b6c636278ea54f2dc))


## v1.15.4 (2025-03-18)

### Bug Fixes

- **dynamic_pseudo**: Fix exec for py313
  ([`74695dc`](https://github.com/bec-project/ophyd_devices/commit/74695dcb0a13ff7e3e4f402715363e47e14fe0f0))

### Build System

- Min bec dependency is 3.13 due to ScanInfo
  ([`91465fb`](https://github.com/bec-project/ophyd_devices/commit/91465fbc38db60efbf92b00b26f3501737ba50ed))

### Documentation

- Update device list
  ([`761498f`](https://github.com/bec-project/ophyd_devices/commit/761498f51d0b8176341443ab213ff2cdec398cc7))


## v1.15.3 (2025-03-06)

### Bug Fixes

- Fix sim camera complete call, improve typhints for psi device base
  ([`8cdcfe7`](https://github.com/bec-project/ophyd_devices/commit/8cdcfe7a44658f1d2cb44966e600f2450d4bc652))

### Testing

- Fix and improve tests camera on complete
  ([`0ed2920`](https://github.com/bec-project/ophyd_devices/commit/0ed29209e41836211246a9304f20f420346b9b31))


## v1.15.2 (2025-03-05)

### Bug Fixes

- **sim**: Moved SimWaveform and SimMonitor to new async update structure
  ([`63eff57`](https://github.com/bec-project/ophyd_devices/commit/63eff57ec441b19428d53d6ba6301d996d487edb))

### Refactoring

- Improve logging if fake scan msg is created
  ([`75f3280`](https://github.com/bec-project/ophyd_devices/commit/75f32800f80aa0803d44261cbf150cf473ea6b94))


## v1.15.1 (2025-02-26)

### Bug Fixes

- Remove metadata updates on ScanStatusMessage
  ([`0659ec0`](https://github.com/bec-project/ophyd_devices/commit/0659ec01d16a826e5479328fe35f8fabffcf495f))


## v1.15.0 (2025-02-25)

### Features

- **psi_device_base**: Add psi_device_base
  ([`ac4f0c5`](https://github.com/bec-project/ophyd_devices/commit/ac4f0c5af7c58927c6b1725934ef98cb400d4b3f))

### Refactoring

- Cleanup
  ([`b75207b`](https://github.com/bec-project/ophyd_devices/commit/b75207b7c0955c4d11e9694b8c19698f5b2d89ca))

### Testing

- **psi-device-base-utils**: Add tests for task handler
  ([`8ed3f37`](https://github.com/bec-project/ophyd_devices/commit/8ed3f37b1400165313a0df04e3f11176837913b3))


## v1.14.1 (2025-02-21)

### Bug Fixes

- **AD**: Fix typo in AreaDetector plugin instantiation
  ([`cc4a9ad`](https://github.com/bec-project/ophyd_devices/commit/cc4a9ad5e98bea400a1e5a6117f355ca0a4257b5))

### Testing

- Fix flaky test for positioner is moving
  ([`1cc8a67`](https://github.com/bec-project/ophyd_devices/commit/1cc8a67dedbc5063411402dd0d5f035da7a7137c))


## v1.14.0 (2025-01-29)

### Bug Fixes

- Allow SettableSignal.get to take kwargs
  ([`5d8ef8c`](https://github.com/bec-project/ophyd_devices/commit/5d8ef8c8eb41647020c95bba9a476cfb2a940444))

Passed by ophyd signal.set for array/tuple values

- Tie h5proxy config to properties
  ([`8fd17c5`](https://github.com/bec-project/ophyd_devices/commit/8fd17c53d7dd907f95c364d32863880bf8062f63))

### Build System

- Update hdf5plugin deps for version
  ([`0584a53`](https://github.com/bec-project/ophyd_devices/commit/0584a53b342b37c5592041e3a27fa5182a6dc6a3))

### Continuous Integration

- Push bec_server and bec_lib dependency >=3.0
  ([`87b885a`](https://github.com/bec-project/ophyd_devices/commit/87b885a85dc9c2cece4c33c8cd0f30066bbce2ae))

### Features

- **simulation**: Add stage camera proxy
  ([`1c6cacd`](https://github.com/bec-project/ophyd_devices/commit/1c6cacd55076989565ffff08566c14379456ae83))

### Refactoring

- Split device proxies into separate files in a module
  ([`7abd212`](https://github.com/bec-project/ophyd_devices/commit/7abd21233faad3c0b693eecb754fc00520362a10))


## v1.13.0 (2025-01-22)

### Features

- Add sim device for tests that returns device status for stage/unstage
  ([`5c02e1e`](https://github.com/bec-project/ophyd_devices/commit/5c02e1ecaea2b282e838fcea13c0e18d9beeb10e))


## v1.12.4 (2025-01-22)

### Bug Fixes

- Change default values for hot pixels to avoid issues while casting to uint16
  ([`35a45a3`](https://github.com/bec-project/ophyd_devices/commit/35a45a3a738f528b431e1146236b6baca177d742))

### Testing

- Fix flaky test for positioner is moving signal
  ([`92a3176`](https://github.com/bec-project/ophyd_devices/commit/92a3176bfd07e1cfa7a1112bb8a7b59dac63bded))


## v1.12.3 (2025-01-14)

### Bug Fixes

- Cleanup after testing with HW
  ([`13f456e`](https://github.com/bec-project/ophyd_devices/commit/13f456e78eb6009203fd9884a13fbf3b560ab9b8))

- Cleanup, add test for ddg base class
  ([`7fe80c1`](https://github.com/bec-project/ophyd_devices/commit/7fe80c1608c6940413ed5aacc499beed91096835))

### Documentation

- Update device list
  ([`d7294e1`](https://github.com/bec-project/ophyd_devices/commit/d7294e183eae45d77f808c2fb63cd353325bd466))

- Update docstrings for base class
  ([`f10060b`](https://github.com/bec-project/ophyd_devices/commit/f10060bceefac2a776e0d5d9300770b33c2e8ac0))

### Refactoring

- Refactored delay generator DG645
  ([`8f51789`](https://github.com/bec-project/ophyd_devices/commit/8f51789f5b0e0e62b949bb202a3b7c3159cd86e5))

- Reviewed and refactored based class for device integration
  ([`5b55ff2`](https://github.com/bec-project/ophyd_devices/commit/5b55ff25b6c06972ac597c0829f60dcd890963a9))

### Testing

- Fixed import of BECDeviceBase
  ([`88ca831`](https://github.com/bec-project/ophyd_devices/commit/88ca831bca90c31199c4d0b50f587712954a6c52))

- Update tests
  ([`a1da3a5`](https://github.com/bec-project/ophyd_devices/commit/a1da3a5f40d432560d68c59fad05581217a54b9c))


## v1.12.2 (2025-01-14)

### Bug Fixes

- **sim positions**: Fixed support for setting a new setpoint while the motor is still moving
  ([`1482124`](https://github.com/bec-project/ophyd_devices/commit/1482124e24e338611daadfb5a6d782231b764ad7))


## v1.12.1 (2025-01-07)

### Bug Fixes

- **sim**: Fixed device for testing a describe failure
  ([`905535b`](https://github.com/bec-project/ophyd_devices/commit/905535b049c3f8809c755599bee3428dabf476c6))


## v1.12.0 (2024-12-19)

### Features

- **tests**: Added simulated device for testing disconnected iocs
  ([`6cd4044`](https://github.com/bec-project/ophyd_devices/commit/6cd404434d5ef50b76c566b9f44be26d48fcc2dd))


## v1.11.1 (2024-12-10)

### Bug Fixes

- Cleanup protocols, moved event_types to BECBaseProtocol
  ([`6e71da7`](https://github.com/bec-project/ophyd_devices/commit/6e71da79c82aae9d847dccd3624643193c478fc4))

- Update protocls for docs in main
  ([`482e232`](https://github.com/bec-project/ophyd_devices/commit/482e2320b9ec80cabc6b81a024e7bf851fa161be))


## v1.11.0 (2024-12-04)

### Bug Fixes

- Falcon and xMAP inherit ADBase
  ([`e37accd`](https://github.com/bec-project/ophyd_devices/commit/e37accdf94f48b2f3de767ba736e1ca7595978c5))

It is needed for ND plugins to inspect the asyn pipeline.

### Documentation

- Update device list
  ([`49630f8`](https://github.com/bec-project/ophyd_devices/commit/49630f82abdfa2588100a268798766b1a4d8b655))

### Features

- Xmap and FalconX devices
  ([`3cf9d15`](https://github.com/bec-project/ophyd_devices/commit/3cf9d15bd35a50cac873d1b75effeb4b482f9efd))


## v1.10.6 (2024-12-04)

### Bug Fixes

- Bump ophyd version to 1.10, remove patch, fix corresponding test
  ([`f166847`](https://github.com/bec-project/ophyd_devices/commit/f1668473872e4fd8231204c123dac6a07d201266))

### Continuous Integration

- Update ci syntax for dependency job
  ([`35f3819`](https://github.com/bec-project/ophyd_devices/commit/35f3819c03fc4ad16fccc72a5fdea1f59318a764))


## v1.10.5 (2024-11-19)

### Bug Fixes

- Add __init__ to tests folder
  ([`2034539`](https://github.com/bec-project/ophyd_devices/commit/203453976981b7077815a571697447c5e96aa747))

### Continuous Integration

- Update no pragma for coverage
  ([`cd64d57`](https://github.com/bec-project/ophyd_devices/commit/cd64d57c658f3ff166aa610153e534b9c82135aa))


## v1.10.4 (2024-11-19)

### Bug Fixes

- **device base**: Added missing property to BECDeviceBase
  ([`cc0e26a`](https://github.com/bec-project/ophyd_devices/commit/cc0e26a91a84b015b03aa7656ccd0528d7465697))

- **sim**: Ensure to update the state before setting the status to finished
  ([`2e8ddbb`](https://github.com/bec-project/ophyd_devices/commit/2e8ddbb1adafca0727a5235b24e7cbe8de078708))


## v1.10.3 (2024-11-18)

### Bug Fixes

- Allow bec v3
  ([`93cd972`](https://github.com/bec-project/ophyd_devices/commit/93cd972040d1e213dabcfdea5e9bbf7a2c48fad8))

### Build System

- Allow bec v3
  ([`bd3897f`](https://github.com/bec-project/ophyd_devices/commit/bd3897fe842cdebcb7bcc41646bd53185418674d))

### Documentation

- Update device list
  ([`6f50660`](https://github.com/bec-project/ophyd_devices/commit/6f50660e8ad5f86ac6b6d2a74897912ccaf0f070))


## v1.10.2 (2024-10-25)

### Bug Fixes

- Ensure filepath is set to the required value before waiting
  ([`db9e191`](https://github.com/bec-project/ophyd_devices/commit/db9e191e4a5c1ee340094400dff93b7ba10f8dfb))


## v1.10.1 (2024-10-25)

### Bug Fixes

- Ophyd patch, compatibility with Python >=3.12
  ([`97982dd`](https://github.com/bec-project/ophyd_devices/commit/97982dd1385f065b04aa780c91aee9f67b9beda2))

"find_module" has been deleted from Finder class

### Refactoring

- Refactored SimCamera write_to_disk option to continously write to h5 file.
  ([`41c54aa`](https://github.com/bec-project/ophyd_devices/commit/41c54aa851e7fcf22b139aeb041d000395524b7e))


## v1.10.0 (2024-10-22)

### Bug Fixes

- Improved patching of Ophyd 1.9
  ([`8a9a6a9`](https://github.com/bec-project/ophyd_devices/commit/8a9a6a9910b44d55412e80443f145d629b1cfc2f))

### Features

- Add test device for return status for stage/unstage
  ([`f5ab78e`](https://github.com/bec-project/ophyd_devices/commit/f5ab78e933c2bbb34c571a72c25a7fc5c2b20e65))


## v1.9.6 (2024-10-17)

### Bug Fixes

- Cleanup and bugfix in positioner; closes #84
  ([`6a7c074`](https://github.com/bec-project/ophyd_devices/commit/6a7c0745e33a2b2cc561b42ad90e61ac08fb9d51))

### Refactoring

- Cleanup sim module namespace; closes #80
  ([`fa32b42`](https://github.com/bec-project/ophyd_devices/commit/fa32b4234b786d93ddf872c7a8220f2d0518b465))


## v1.9.5 (2024-10-01)

### Bug Fixes

- Bugfix for proxy devices
  ([`b1639ea`](https://github.com/bec-project/ophyd_devices/commit/b1639ea3baddec722a444b7c65bdc39d763b7d07))

- Fixed SimWaveform, works as async device and device_monitor_1d simultaneously
  ([`7ff37c0`](https://github.com/bec-project/ophyd_devices/commit/7ff37c0dcdd87bfa8f518b1dd7acc4aab353b71f))

### Refactoring

- Cleanup of scan_status prints in scaninfo_mixin
  ([`449dadb`](https://github.com/bec-project/ophyd_devices/commit/449dadb593a0432d31f905e4e507102d0c4f3fd6))


## v1.9.4 (2024-10-01)

### Bug Fixes

- Increased min version of typeguard
  ([`e379282`](https://github.com/bec-project/ophyd_devices/commit/e3792826644e01adf84435891d500ec5bef85cda))

### Build System

- Allow numpy v2
  ([`825a7de`](https://github.com/bec-project/ophyd_devices/commit/825a7dee5e948d9decb4e8649c0573a2d9d4b83f))


## v1.9.3 (2024-09-06)

### Bug Fixes

- Remove bodge (readback) in SimMonitor
  ([`cd75fc0`](https://github.com/bec-project/ophyd_devices/commit/cd75fc0e01e565445f7176e52faada264544d439))


## v1.9.2 (2024-09-05)

### Bug Fixes

- Change inheritance for simmonitor from device to signal
  ([`a675420`](https://github.com/bec-project/ophyd_devices/commit/a6754208a0991f8ccf546cbb2bee015f6daecb93))

- Fix inheritance for SimMonitor
  ([`f56961b`](https://github.com/bec-project/ophyd_devices/commit/f56961ba8c179d4ca75e574fd8565ae4c3f41eed))

### Continuous Integration

- Prefill variables for manual pipeline start
  ([`3f2c6dc`](https://github.com/bec-project/ophyd_devices/commit/3f2c6dc4efddfa06bebff13ac2984e45efd13a90))

### Refactoring

- Bodge to make simmonitor compatible with tests; to be removed asap
  ([`9d9a5fe`](https://github.com/bec-project/ophyd_devices/commit/9d9a5fe305981f845c87e3417dd1072d2b8692b0))


## v1.9.1 (2024-08-28)

### Bug Fixes

- Removed arguments for callback call
  ([`d83c102`](https://github.com/bec-project/ophyd_devices/commit/d83c102d14430b9acd8525d1d61e6e092d9f6043))

### Refactoring

- Moved sim test devices to sim_test_devices
  ([`a49c6f6`](https://github.com/bec-project/ophyd_devices/commit/a49c6f6a625a576524fceca62dd0a1582a4a4a7d))


## v1.9.0 (2024-08-28)

### Features

- Add dual patch pvs to ophyd_devices
  ([`c47918d`](https://github.com/bec-project/ophyd_devices/commit/c47918d6e7ff41721aa4fa67043ff6cd1aeee2c7))


## v1.8.1 (2024-08-15)

### Bug Fixes

- Fixed import of simpositioner test devices
  ([`f1f9721`](https://github.com/bec-project/ophyd_devices/commit/f1f9721fe9c71da747558e4bb005c04592aa2bde))

### Build System

- Moved pyepics deps to >=3.5.5
  ([`8046f22`](https://github.com/bec-project/ophyd_devices/commit/8046f22a807f94f1dc7d9ab77ab3b9c3ce821633))

3.5.3 and 3.5.4 should not be used


## v1.8.0 (2024-08-14)

### Features

- **sim**: Added dedicated positioner with controller
  ([`4ad5723`](https://github.com/bec-project/ophyd_devices/commit/4ad57230e327c3714a03ae138bc12a5028acb1dd))


## v1.7.3 (2024-08-08)

### Bug Fixes

- Small bugfix to ensure motor_is_moving updates at the end of a move
  ([`577b35f`](https://github.com/bec-project/ophyd_devices/commit/577b35f287ec997a41ce27fae2db9bbc669a2d9d))

### Testing

- Add test case
  ([`76e1cfc`](https://github.com/bec-project/ophyd_devices/commit/76e1cfc4aade9c691d9b5bfd4db0b678b7e2f1cc))


## v1.7.2 (2024-07-29)

### Bug Fixes

- Add write_access attribute to simulated readonly signal
  ([`c3e17ba`](https://github.com/bec-project/ophyd_devices/commit/c3e17ba05632309adcc896f858e52ecb07048a30))

- Improve asyn_monitor and camera on_trigger and on_complete to return status
  ([`f311876`](https://github.com/bec-project/ophyd_devices/commit/f3118765b0efc38dd12a3d72d290e517490f9fbf))

- Remove print for select_model method of sim module
  ([`5009316`](https://github.com/bec-project/ophyd_devices/commit/5009316a82897d739b2a26eb341e9f5a1e083e51))

### Build System

- **ci**: Update variable for ophyd_devices branch
  ([`1d55214`](https://github.com/bec-project/ophyd_devices/commit/1d55214fbd25a111f8a81d804fd7f39470934c74))

### Continuous Integration

- Changed default branch
  ([`fe5f1c3`](https://github.com/bec-project/ophyd_devices/commit/fe5f1c314f51cb07bae4044a406ed5dc738c7837))

- Fixed default branch for ophyd ci var
  ([`85630f3`](https://github.com/bec-project/ophyd_devices/commit/85630f3d733897945ef3421b9805e66191edb537))

- Made BEC a child pipeline
  ([`9eb67a0`](https://github.com/bec-project/ophyd_devices/commit/9eb67a0900159248e785b17e4250ae6a7e954348))

- Moved to awi utils trigger pipelines
  ([`0f6494a`](https://github.com/bec-project/ophyd_devices/commit/0f6494ae2caafc0727a394683718031670614aeb))

### Refactoring

- Rename monitor to device_monitor_2d
  ([`6a6b907`](https://github.com/bec-project/ophyd_devices/commit/6a6b907022532e20626b8ed97d347da04beea4b0))

- Review DeviceStatus and error handling in simulation
  ([`87858ed`](https://github.com/bec-project/ophyd_devices/commit/87858edfe290cb711bc30c2f3ba2653460d15af6))

### Testing

- Adapt tests to consider returned DeviceStatus for on_trigger/complete
  ([`f8e9aaf`](https://github.com/bec-project/ophyd_devices/commit/f8e9aaf55a5734f3bf557bbf5e51eb7ea41257d4))

- Fix and add test scenarios for DeviceStatus error handling
  ([`4397db9`](https://github.com/bec-project/ophyd_devices/commit/4397db919a852d70c53d80a532540eaabdffc3ad))


## v1.7.1 (2024-07-24)

### Bug Fixes

- Add run._subs SUB_VALUE to settable signal put method
  ([`ca6d96e`](https://github.com/bec-project/ophyd_devices/commit/ca6d96e25b4a2d5011c0882e512b84e16cf7b264))


## v1.7.0 (2024-07-10)

### Bug Fixes

- _update_state() does not raise an exception if stopped
  ([`207b9b5`](https://github.com/bec-project/ophyd_devices/commit/207b9b571c6df1c2de75b187e794d2dcd7bd0108))

### Features

- Add SimLinearTrajectoryPositioner to better motion simulation
  ([`b5918c4`](https://github.com/bec-project/ophyd_devices/commit/b5918c424de005d1510afedc05b0e217fd09616e))

### Refactoring

- Make it easier to subclass SimPositioner
  ([`9037553`](https://github.com/bec-project/ophyd_devices/commit/903755325230b2c93eba219dd0e4d2aadd05d16f))

### Testing

- Add test for SimLinearTrajectoryPositioner
  ([`ba7db78`](https://github.com/bec-project/ophyd_devices/commit/ba7db7819439c89c3f160acaf399b1ffd538ac7f))


## v1.6.1 (2024-07-05)

### Bug Fixes

- **softpositioner**: Fixed input args for softpositioner
  ([`e80811c`](https://github.com/bec-project/ophyd_devices/commit/e80811c19736cd70be2dbcfac0bcedfe975bf419))


## v1.6.0 (2024-07-05)

### Features

- **devices**: Added softpositioner
  ([`e803829`](https://github.com/bec-project/ophyd_devices/commit/e803829f6c2bab1724a2f30eb0633fd52033ffe7))


## v1.5.4 (2024-07-05)

### Bug Fixes

- **sim**: Fixed sim positioner moving state update
  ([`8efa93a`](https://github.com/bec-project/ophyd_devices/commit/8efa93a7023c939ce535f829a5e41468372ae78e))


## v1.5.3 (2024-07-03)

### Bug Fixes

- Device sim params can be set through init
  ([`f481c1f`](https://github.com/bec-project/ophyd_devices/commit/f481c1f81298552067aea91fba54e90d61cd2dcb))

### Refactoring

- Ensure temporary backward compatibility after API changes
  ([`73c636b`](https://github.com/bec-project/ophyd_devices/commit/73c636b46f35381ac0a82b99f9965612770ca6c1))


## v1.5.2 (2024-07-02)

### Bug Fixes

- Put noqa comment on hdf5plugin import, compress HDF5 test file to ensure it requires the module
  for reading
  ([`55ea6a1`](https://github.com/bec-project/ophyd_devices/commit/55ea6a16be831e375281f014c75f0146b1b9a488))

hd5plugin import has the side effect of installing LZ4 codec

- Split simulation classes in multiple files
  ([`2622ddb`](https://github.com/bec-project/ophyd_devices/commit/2622ddbee2edfe9e092c643fbbfbabeed0c06e35))


## v1.5.1 (2024-06-28)

### Bug Fixes

- Update timestamp upon reading of non computed readback signal
  ([`17e8cd9`](https://github.com/bec-project/ophyd_devices/commit/17e8cd9234727e1bdc3d2a2ba2c47a9c8ec43c32))

### Documentation

- Update device list
  ([`f818ff0`](https://github.com/bec-project/ophyd_devices/commit/f818ff0234edb75840ab7ba60b66d0aa47d1d520))

- Update device list
  ([`ac5e794`](https://github.com/bec-project/ophyd_devices/commit/ac5e79425ddf5b52350e45d392e2e6f048b5856a))

- Update device list
  ([`cc6773e`](https://github.com/bec-project/ophyd_devices/commit/cc6773e14e1c758ec3296c41e969731e8ce4cfe4))

- Update device list
  ([`2ad4a70`](https://github.com/bec-project/ophyd_devices/commit/2ad4a70971e73ed8d38d0e3ed54f18053e79048b))


## v1.5.0 (2024-06-19)

### Features

- Add option to return DeviceStatus for on_trigger, on_complete; extend wait_for_signals
  ([`2c7c48a`](https://github.com/bec-project/ophyd_devices/commit/2c7c48a7576cca90cc7be0d22b5a86c416f49fa9))


## v1.4.0 (2024-06-17)

### Documentation

- Update device list
  ([`22a6970`](https://github.com/bec-project/ophyd_devices/commit/22a69705865ee137f76c207807240562d4609560))

### Features

- **config**: Added epics example config
  ([`a10e5bc`](https://github.com/bec-project/ophyd_devices/commit/a10e5bcadcbd3e8bfbc061abd247d0655534095d))


## v1.3.5 (2024-06-14)

### Bug Fixes

- Fixed pyepics version for now as it segfaults on startup
  ([`f1a2368`](https://github.com/bec-project/ophyd_devices/commit/f1a2368101e6b4af2d08d1a3540680f7f3ff9762))


## v1.3.4 (2024-06-07)

### Bug Fixes

- Remove inheritance from ophyd.PostionerBase for simflyer
  ([`c9247ef`](https://github.com/bec-project/ophyd_devices/commit/c9247ef82ee32aeb50474979d414b98d67a2b840))


## v1.3.3 (2024-06-06)

### Bug Fixes

- Make done and successful mandatory args.
  ([`79b821a`](https://github.com/bec-project/ophyd_devices/commit/79b821ae7e38b78e35ab5165db590cb7123afbf4))

- Make filepath a signal
  ([`e9aaa03`](https://github.com/bec-project/ophyd_devices/commit/e9aaa0383e4120a09b6aa40b7e33fb53f31cb9a3))


## v1.3.2 (2024-06-04)

### Bug Fixes

- Adapt SimPositioner, make tolerance changeable signal
  ([`3606a2f`](https://github.com/bec-project/ophyd_devices/commit/3606a2fc5ad74ec949d388cc23fbd6618d1f3083))

### Documentation

- Update device list
  ([`c1e977f`](https://github.com/bec-project/ophyd_devices/commit/c1e977f639633167fe4e7dfb5f34b066c26933d0))

- Update device list
  ([`92be39f`](https://github.com/bec-project/ophyd_devices/commit/92be39f14fac756749631e64113d24f732bb5551))


## v1.3.1 (2024-06-03)

### Bug Fixes

- Bugfix to fill data butter with value, timestamp properly
  ([`8520800`](https://github.com/bec-project/ophyd_devices/commit/85208002a305fa657c469ff98b45174eb2c1f29a))

### Documentation

- Update device list
  ([`33f5d8a`](https://github.com/bec-project/ophyd_devices/commit/33f5d8a6291e4ddfd905d83ff5c9384d648a632d))

- Update device list
  ([`6f29a79`](https://github.com/bec-project/ophyd_devices/commit/6f29a797965187ed0a608d0bb07eaa25f414440e))


## v1.3.0 (2024-06-03)

### Documentation

- Update device list
  ([`f9b126c`](https://github.com/bec-project/ophyd_devices/commit/f9b126c60ce710fba221ffb208d66541b8264c0b))

- Update device list
  ([`be25cba`](https://github.com/bec-project/ophyd_devices/commit/be25cbae92540b074bb4533331656d20a049a809))

### Features

- Add async monitor, add on_complete to psi_det_base and rm duplicated mocks, closes #67
  ([`1aece61`](https://github.com/bec-project/ophyd_devices/commit/1aece61a3b09267f87f0771b163a5d07b4549eff))

### Refactoring

- Add .wait() to set methods
  ([`7334925`](https://github.com/bec-project/ophyd_devices/commit/73349257ee0228a9563051d4f8e0bf5f7e6b551f))

- Removed deprecated devices
  ([`8ef6d10`](https://github.com/bec-project/ophyd_devices/commit/8ef6d10eb759e6ce874ddf05a38c586e9475eed3))

### Testing

- Add tests for new device
  ([`c554422`](https://github.com/bec-project/ophyd_devices/commit/c5544226be3f12d238a0793a0f41da07af36e460))


## v1.2.1 (2024-05-29)

### Bug Fixes

- Fixed psi_detector_base to allow init with mocked device_manager
  ([`e566c7f`](https://github.com/bec-project/ophyd_devices/commit/e566c7f982ee519a5ec3e350cef349c3238eebae))

### Documentation

- Update device list
  ([`5a591ce`](https://github.com/bec-project/ophyd_devices/commit/5a591ce024b7815a432460fe9e8d97e648dcdb5e))

- Update device list
  ([`ae0c766`](https://github.com/bec-project/ophyd_devices/commit/ae0c766975cdfc69ffe9d48eca92ad8d51a0497c))


## v1.2.0 (2024-05-29)

### Continuous Integration

- Fix bec_core_branch triggering in ci file
  ([`3cab569`](https://github.com/bec-project/ophyd_devices/commit/3cab5690db3fbabffecc179cbaadf6878f0ab2f1))

### Documentation

- Update device list
  ([`08dfc9e`](https://github.com/bec-project/ophyd_devices/commit/08dfc9e314a1b498ec2fc1f9056234fe732d6428))

- Update device list
  ([`106233f`](https://github.com/bec-project/ophyd_devices/commit/106233f8d951794e261b08a11b20db6cbf4ef63a))

- Update device list
  ([`9c93916`](https://github.com/bec-project/ophyd_devices/commit/9c9391610845bc1b21e342e7c3b34b8db978a038))

- Update device list
  ([`018fdac`](https://github.com/bec-project/ophyd_devices/commit/018fdaced4120557ea64501c107c027e362c93fb))

### Features

- Add option to save Camera data to disk, closes #66
  ([`60b2e75`](https://github.com/bec-project/ophyd_devices/commit/60b2e756550196fb5c07bb91abb4c1ae5b815c6c))

### Testing

- Add tests
  ([`af908fa`](https://github.com/bec-project/ophyd_devices/commit/af908fa210914519de9a713ed2ef3e2e0c743742))


## v1.1.0 (2024-05-27)

### Features

- Refactor psi_detector_base class, add tests
  ([`a0ac8c9`](https://github.com/bec-project/ophyd_devices/commit/a0ac8c9ad701f52429f393a134fd0705583eddb1))

### Refactoring

- Add publish file location to base class
  ([`e8510fb`](https://github.com/bec-project/ophyd_devices/commit/e8510fb249b136781c03849497d85dfb11cca43a))


## v1.0.2 (2024-05-23)

### Bug Fixes

- Pep8 compliant naming #64
  ([`d705958`](https://github.com/bec-project/ophyd_devices/commit/d7059589c84bacb560f738f4e4ae4aaf811b25d9))

### Continuous Integration

- Added ci token to update job
  ([`180891b`](https://github.com/bec-project/ophyd_devices/commit/180891becdc1aa16da0c3b83c407e82a288d36d1))

- Added device-list-update job
  ([`3405e2a`](https://github.com/bec-project/ophyd_devices/commit/3405e2acf59cea33b025d376291ccda96db9ea07))

- Fixed dependency for bec
  ([`6630740`](https://github.com/bec-project/ophyd_devices/commit/663074055977ca0a046a81bd9ba5187acf95afed))

### Documentation

- Update device list
  ([`d4f2ead`](https://github.com/bec-project/ophyd_devices/commit/d4f2ead61b9eb4defb43d7e966a1ed5206461abd))

- Update device list
  ([`2f575d3`](https://github.com/bec-project/ophyd_devices/commit/2f575d3aa221e646166bfeb0470de1847358acca))

- Update device list
  ([`b5adc09`](https://github.com/bec-project/ophyd_devices/commit/b5adc097674068a90783a2ce4a093150d21cb736))


## v1.0.1 (2024-05-15)

### Bug Fixes

- Bec_lib imports
  ([`3d8b023`](https://github.com/bec-project/ophyd_devices/commit/3d8b0231a3359db9a5430e49912147c049dbfab9))

### Continuous Integration

- Added echo to highlight the current branch
  ([`68b593f`](https://github.com/bec-project/ophyd_devices/commit/68b593f20d73c6463d5e97ddf7dcf94a5b036b06))

- Fixed bec core dependency
  ([`8158e14`](https://github.com/bec-project/ophyd_devices/commit/8158e145fe2358a736a2fb9d2d3de7e6c8db021c))

- Fixed bec_widgets env var
  ([`e900a4c`](https://github.com/bec-project/ophyd_devices/commit/e900a4cb47c5ecaae8eca30d106771034dc9296d))


## v1.0.0 (2024-05-08)

### Continuous Integration

- Added trigger for xtreme-bec
  ([`be689ba`](https://github.com/bec-project/ophyd_devices/commit/be689baa29d54632bbac9b523f0fe3a66e061f84))

- Fix dep and add CI JOB for package dep checks
  ([`d89f8b8`](https://github.com/bec-project/ophyd_devices/commit/d89f8b87568d30d467279d96b0100cd318e2b5a2))

### Refactoring

- Moved to new ophyd_devices repo structure
  ([`3415ae2`](https://github.com/bec-project/ophyd_devices/commit/3415ae2007cc447835906271de23e5f7a41ba373))

BREAKING CHANGE: cleaned up and migrated to the new repo structure. Only shared devices will be
  hosted in ophyd_devices. Everything else will be in the beamline-specific repositories

### Breaking Changes

- Cleaned up and migrated to the new repo structure. Only shared devices will be hosted in
  ophyd_devices. Everything else will be in the beamline-specific repositories


## v0.33.6 (2024-05-08)

### Bug Fixes

- Fixed controller error classes
  ([`c3fa7ad`](https://github.com/bec-project/ophyd_devices/commit/c3fa7ad30d1b9a151bce599b34b4a3f82e4e6ce8))

### Continuous Integration

- Added downstream pipelines
  ([`b8134ed`](https://github.com/bec-project/ophyd_devices/commit/b8134edbff58e1f92c45c3ab9b41f88e1ad3069b))

- Added parent-child pipelines
  ([`e27d2db`](https://github.com/bec-project/ophyd_devices/commit/e27d2db4ac21830c95f2db2ccba58c650c25cad5))

- Added support for different branches in child pipelines
  ([`c74cbe3`](https://github.com/bec-project/ophyd_devices/commit/c74cbe358cf24943e1badc32ef53ced1f8d149f1))

- Fixed rules for downstream pipelines
  ([`f5e69f9`](https://github.com/bec-project/ophyd_devices/commit/f5e69f9b9528871d9a011b2257b87c1faf89e6b0))

- Fixed typo
  ([`81f1fee`](https://github.com/bec-project/ophyd_devices/commit/81f1feea853882e8d557063612cc0acc601bbe2a))

- Limit stages to run in child pipelines
  ([`815921a`](https://github.com/bec-project/ophyd_devices/commit/815921a6c9cd97e5df94a584c5d4c2c22a4d408a))

- Made pipeline interruptible
  ([`44de499`](https://github.com/bec-project/ophyd_devices/commit/44de499d40db01e2d9ad0ae50235240e2103bf02))

- Removed awi-utils for now
  ([`27d4b6a`](https://github.com/bec-project/ophyd_devices/commit/27d4b6ae83ec3d0f4d7a85c3cd4f6f70ecd528eb))

### Documentation

- Improved doc strings for controllerr
  ([`339f050`](https://github.com/bec-project/ophyd_devices/commit/339f050a8662de86ed2528ad4ffed18482dd546b))

### Refactoring

- Added common controller methods
  ([`00b3ae8`](https://github.com/bec-project/ophyd_devices/commit/00b3ae82580df6bbe8a01a52d37c43199cf761bd))


## v0.33.5 (2024-05-02)

### Bug Fixes

- Fixed device data signature
  ([`e8290db`](https://github.com/bec-project/ophyd_devices/commit/e8290dbf4466f1415fb9c963ae203a4e6da7cc42))


## v0.33.4 (2024-04-29)

### Bug Fixes

- Static device test should use yaml_load
  ([`c77f924`](https://github.com/bec-project/ophyd_devices/commit/c77f924bb3665ab0896bc56076d05331e8b01f55))

### Continuous Integration

- Removed redundant build step
  ([`a919632`](https://github.com/bec-project/ophyd_devices/commit/a9196328e7d7efe4b6718b22d72c6df9bf59411c))

- **gitlab-ci**: Trigger gitlab job template from awi_utils
  ([`4ffeba4`](https://github.com/bec-project/ophyd_devices/commit/4ffeba4c3b890b2fcd8c694347a254b3bc1e3c96))


## v0.33.3 (2024-04-24)

### Bug Fixes

- Updated device configs to new import schema
  ([`5725fc3`](https://github.com/bec-project/ophyd_devices/commit/5725fc36c7aff052fc704782a99bd04cfb13c112))

### Continuous Integration

- Removed allow_failure from config check
  ([`d34b396`](https://github.com/bec-project/ophyd_devices/commit/d34b39669c4faf2d1c5518a632239303a48c2fd6))


## v0.33.2 (2024-04-22)

### Bug Fixes

- **pyproject.toml**: Add bec-server to dev dependencies; closes #62
  ([`9353b46`](https://github.com/bec-project/ophyd_devices/commit/9353b46be804de967810f0d9370d230dfae5c92b))


## v0.33.1 (2024-04-20)

### Bug Fixes

- Fix pyproject.toml
  ([`6081eb4`](https://github.com/bec-project/ophyd_devices/commit/6081eb4ba54b2a6a2072f638af06c6f1cf264b69))


## v0.33.0 (2024-04-19)

### Features

- Move csaxs devices to plugin structure, fix imports and tests
  ([`74f6fa7`](https://github.com/bec-project/ophyd_devices/commit/74f6fa7ffdf339399504e15f27564e3f0e43db56))


## v0.32.0 (2024-04-19)

### Continuous Integration

- Do not wait for additional tests to start
  ([`b88545f`](https://github.com/bec-project/ophyd_devices/commit/b88545f6864a7d11ca39435906bcbd2cd0bb12b0))

### Features

- Added support for nestes device configs
  ([`288f394`](https://github.com/bec-project/ophyd_devices/commit/288f39483e83575d0bf3ec7a8e0d872b41b5b183))


## v0.31.0 (2024-04-19)

### Build System

- Fixed dependencies to compatible releases
  ([`26c04b5`](https://github.com/bec-project/ophyd_devices/commit/26c04b5d03683b0159d5af127f19cda664bfb292))

### Continuous Integration

- Added pipeline as trigger source
  ([`e59def1`](https://github.com/bec-project/ophyd_devices/commit/e59def138fb465abf7a33d13e47e78ac382feebf))

- Changed master to main
  ([`701be52`](https://github.com/bec-project/ophyd_devices/commit/701be5262ad402ff6e6a665db4bd1d5b30b3abac))

- Cleanup; added static device test job
  ([`ed66eac`](https://github.com/bec-project/ophyd_devices/commit/ed66eacc5310e878deb35be69f335f1b8eb10950))

- Pull images via gitlab dependency proxy
  ([`8d68e7d`](https://github.com/bec-project/ophyd_devices/commit/8d68e7df70e54984e460f50cee5356a7ada4e761))

- Remove AdditionalTests dependency on pytest job
  ([`4ee86ab`](https://github.com/bec-project/ophyd_devices/commit/4ee86aba371698820ea16ff94ae6946cd0041fe4))

### Features

- Added support for directories as input for the static device test
  ([`9748ca6`](https://github.com/bec-project/ophyd_devices/commit/9748ca666c3c8668e8ced80e7d24eeaf7f19c28e))


## v0.30.5 (2024-04-12)

### Bug Fixes

- Fixed bec_server import
  ([`434fa36`](https://github.com/bec-project/ophyd_devices/commit/434fa36ca43f8dacd9c4f8fdd7556d77bd0a4b03))

### Code Style

- Moved black config to pyproject.toml
  ([`769a45d`](https://github.com/bec-project/ophyd_devices/commit/769a45d7ff97f5d3bc5de5aa63bd2230654ea9d4))

- Moved isort config to pyproject.toml
  ([`98d61b1`](https://github.com/bec-project/ophyd_devices/commit/98d61b13e42ec294c2be059029e33021ba6ef3a0))

- Moved pylint to pyproject.toml
  ([`fcfe024`](https://github.com/bec-project/ophyd_devices/commit/fcfe0242326c61be9251bd98cf9cf29de499facd))

### Continuous Integration

- Fixed bec install
  ([`a954640`](https://github.com/bec-project/ophyd_devices/commit/a9546402f5b2f1a43e1c4e17f977c544c326e5dc))

- Fixed changelog file
  ([`deded6f`](https://github.com/bec-project/ophyd_devices/commit/deded6ffaca10369fb1e6cf2629f67ded3ab44b5))

- Fixed twine upload if version did not change
  ([`d7646e8`](https://github.com/bec-project/ophyd_devices/commit/d7646e835ff5d2c8ea749f3b4e24121d992c1454))

### Refactoring

- **device_config**: Fixed device schema
  ([`0f3665c`](https://github.com/bec-project/ophyd_devices/commit/0f3665c32fec2f0f95cc57af81d448eca6978919))

- **device_config**: Removed outdated config file
  ([`80a964f`](https://github.com/bec-project/ophyd_devices/commit/80a964fae7203cbfb642980e3f89ed35ad6ff0da))

- **device_config**: Upgraded device configs; closes #56
  ([`65c72c9`](https://github.com/bec-project/ophyd_devices/commit/65c72c924847644f80fac768ed35e995a6999404))


## v0.30.4 (2024-04-12)

### Bug Fixes

- Fixed release upload
  ([`361dc3a`](https://github.com/bec-project/ophyd_devices/commit/361dc3a182231b458e1893da2e6382b1b17e9d5a))

- Upgraded pyproject.toml
  ([`9d67ace`](https://github.com/bec-project/ophyd_devices/commit/9d67ace30d606caa2aaa919fe8225208c4632c7e))

### Continuous Integration

- Fixed upload of release
  ([`3c37da8`](https://github.com/bec-project/ophyd_devices/commit/3c37da8f515b2effea0950e3236bb9843b7b7b95))


## v0.30.3 (2024-04-12)

### Bug Fixes

- Fixed pyproject.toml
  ([`2793ca3`](https://github.com/bec-project/ophyd_devices/commit/2793ca3eb0c278f6159b0c6d7fcb121b5c969e12))

### Build System

- Fixed build
  ([`88ff3bc`](https://github.com/bec-project/ophyd_devices/commit/88ff3bc0cf3c21d87ba50c24e7d9e2352df751c9))


## v0.30.2 (2024-04-12)

### Bug Fixes

- Fixed release update
  ([`3267514`](https://github.com/bec-project/ophyd_devices/commit/3267514c2055f406277b16f13a13744846e3ba77))


## v0.30.1 (2024-04-12)

### Bug Fixes

- Fixed release upload
  ([`abc6aad`](https://github.com/bec-project/ophyd_devices/commit/abc6aad167226fd01e02d51ae4739d4c4688e153))

### Build System

- Upgraded to sem release 9
  ([`0864c0c`](https://github.com/bec-project/ophyd_devices/commit/0864c0c04972a2b12be5ad9d3a53fb1a18a8907d))


## v0.30.0 (2024-04-12)

### Build System

- Added black to pyproject
  ([`eb21600`](https://github.com/bec-project/ophyd_devices/commit/eb2160000a19f89c000caf25a69a79e8249e5bf2))

- Moved to pyproject.toml
  ([`6ba2428`](https://github.com/bec-project/ophyd_devices/commit/6ba2428dd8e297c3c2098f9a795bb76595a4f5e7))

### Code Style

- **black**: Skip magic trailing comma
  ([`b1f3531`](https://github.com/bec-project/ophyd_devices/commit/b1f353139b1ecdcfc266219a7a1a4bf525684bea))

### Continuous Integration

- Updated default BEC branch
  ([`f287efc`](https://github.com/bec-project/ophyd_devices/commit/f287efc831069d7c09de876ed1bf4dff4bd5908e))

### Features

- Add SimWaveform for 1D waveform simulations
  ([`bf73bf4`](https://github.com/bec-project/ophyd_devices/commit/bf73bf41c4f209ed251bf21d4b0014d031226a4f))

### Refactoring

- Renamed pointID to point_id
  ([`b746278`](https://github.com/bec-project/ophyd_devices/commit/b74627820a5594dc896b059399703baa4917097a))

- **sim**: Added logger statement to flyer
  ([`6c45dd6`](https://github.com/bec-project/ophyd_devices/commit/6c45dd6a8b8c76776351289c98990dbc05222f5f))


## v0.29.2 (2024-04-08)

### Bug Fixes

- Adapt to FileWriter refactoring
  ([`e9c626a`](https://github.com/bec-project/ophyd_devices/commit/e9c626a7c8e5ec1b40d70ad412eff85d7796cba9))


## v0.29.1 (2024-04-06)

### Bug Fixes

- **utils**: Fixed scan status message in sim mode
  ([`c87f6ef`](https://github.com/bec-project/ophyd_devices/commit/c87f6ef63f669d6d1288e3521b80b3e0065bf2f4))

### Continuous Integration

- Added isort to pre-commit and ci
  ([`36d5cef`](https://github.com/bec-project/ophyd_devices/commit/36d5cef4ef14e5566649834b3afdd1efdbfdfc2d))

### Refactoring

- Applied isort to repo
  ([`284c6c4`](https://github.com/bec-project/ophyd_devices/commit/284c6c47a1db25d7ed840404730b1e97da960c14))

- Applied isort to tomcat rotation motors
  ([`fd1f8c0`](https://github.com/bec-project/ophyd_devices/commit/fd1f8c0ff58c630051cb67d404c6dd07f3403c5b))

- Fixed formatter
  ([`1e03114`](https://github.com/bec-project/ophyd_devices/commit/1e031140ed0ae4347a8d16a6a5e8647b48573d96))


## v0.29.0 (2024-03-28)

### Features

- Add protocols and rotation base device
  ([`ddd0b79`](https://github.com/bec-project/ophyd_devices/commit/ddd0b790f8ef3e53966c660c431d2f7a9ceda97c))

### Refactoring

- Add set for positioner protocol
  ([`d844168`](https://github.com/bec-project/ophyd_devices/commit/d844168c1f7f31543ff747bb6f2ef3a2f7f1077e))

- Cleanup aerotech, fix packaging for release
  ([`ce43924`](https://github.com/bec-project/ophyd_devices/commit/ce43924ca1601c409a17855957af6847b75ff261))

- Move protocol and base classes to different directory
  ([`8b77df8`](https://github.com/bec-project/ophyd_devices/commit/8b77df833f4d389293d14f8e3e54de7b38c9f291))

### Testing

- Add test for simulated devices and BECprotocols
  ([`b34817a`](https://github.com/bec-project/ophyd_devices/commit/b34817acf8ef6e60ef493bc2bb830a3a254e7ced))

- Add tests for proxies
  ([`2c43559`](https://github.com/bec-project/ophyd_devices/commit/2c43559aa8e60950ff95e72772820d784aacaa62))

- Fix tests after merge conflict
  ([`5f5ec72`](https://github.com/bec-project/ophyd_devices/commit/5f5ec72d02c2cb217ab540e82014d90fe5ef8216))


## v0.28.0 (2024-03-26)

### Features

- **ophyd**: Temporary until new Ophyd release, prevent Status objects threads
  ([`df8ce79`](https://github.com/bec-project/ophyd_devices/commit/df8ce79ca0606ad415f45cfd5d80b057aec107d9))

Monkey-patching of Ophyd library


## v0.27.4 (2024-03-26)

### Bug Fixes

- Fix CI pipeline for py 3.10 and 3.11
  ([`391c889`](https://github.com/bec-project/ophyd_devices/commit/391c889ff17d9b97388d01731ed88251b41d6ecd))

### Continuous Integration

- Added BEC_CORE_BRANCH var name to .gitlab-ci.yml
  ([`d3a26ff`](https://github.com/bec-project/ophyd_devices/commit/d3a26ff3b2d2612128d0da4bd4fcc698b314ae9a))

### Refactoring

- Renamed queueID to queue_id
  ([`5fca3ec`](https://github.com/bec-project/ophyd_devices/commit/5fca3ec1292ba423d575ed106a636a3c8613a99d))

- Renamed scanID to scan_id
  ([`1c7737c`](https://github.com/bec-project/ophyd_devices/commit/1c7737ccda71a18c0a9c09f38c8c543834dfe833))


## v0.27.3 (2024-03-21)

### Bug Fixes

- Remove missplaced readme from aerotech
  ([`ad96b72`](https://github.com/bec-project/ophyd_devices/commit/ad96b729b47318007d403f7024524379f5a32a84))

### Testing

- Added simpositioner with failure signal
  ([`4ea98b1`](https://github.com/bec-project/ophyd_devices/commit/4ea98b18c3280c077a08325081f5743a737760a9))


## v0.27.2 (2024-03-15)

### Bug Fixes

- Add numpy and scipy to dynamic_pseudo
  ([`b66b224`](https://github.com/bec-project/ophyd_devices/commit/b66b224caeab9e3cf75de61fcfdccd0712fb9027))

- Bug fixes from online test at microxas
  ([`c2201e5`](https://github.com/bec-project/ophyd_devices/commit/c2201e5e332c9bab64f6fcdfe034cb8d37da5857))

### Refactoring

- Numpy as np
  ([`d9ad1e8`](https://github.com/bec-project/ophyd_devices/commit/d9ad1e87f7e6e2a5da6c3ea9b59952ca319c50ae))

### Testing

- Fix tests
  ([`2f2e519`](https://github.com/bec-project/ophyd_devices/commit/2f2e51977265006f7fbb9a97648824dfb6f8b5b3))


## v0.27.1 (2024-03-13)

### Bug Fixes

- Bug fix
  ([`6c776bb`](https://github.com/bec-project/ophyd_devices/commit/6c776bb4ae72e7f0a4b858a27a34f25baed726d2))


## v0.27.0 (2024-03-12)

### Features

- Moving the Automation1 device to BEC repo
  ([`26ee4e2`](https://github.com/bec-project/ophyd_devices/commit/26ee4e2d9bd9cb37eebefe9102ca78aa0fd55b33))

- Moving the Automation1 device to BEC repo
  ([`853d621`](https://github.com/bec-project/ophyd_devices/commit/853d621042e400c83940fdde50f1db66941f540b))

### Refactoring

- Fixed formatter for aerotech
  ([`573da8a`](https://github.com/bec-project/ophyd_devices/commit/573da8a20b9be502b274b4c79e581b9e35a1e25d))


## v0.26.1 (2024-03-10)

### Bug Fixes

- Fixed dynamic pseudo
  ([`33e4458`](https://github.com/bec-project/ophyd_devices/commit/33e4458c59cce44e93d9f3bae44ce41028688471))


## v0.26.0 (2024-03-08)

### Documentation

- Improved doc strings for computed signal
  ([`c68c3c1`](https://github.com/bec-project/ophyd_devices/commit/c68c3c1b54ecff2c51417168ee3e91b4056831fc))

### Features

- Added computed signal
  ([`d9f09b0`](https://github.com/bec-project/ophyd_devices/commit/d9f09b0d866f97a859c9b437474928e7a9e8c1b6))

### Testing

- Added tests for dynamic_pseudo
  ([`c76e1a0`](https://github.com/bec-project/ophyd_devices/commit/c76e1a0b4e012271b4e4baaa2ff8210f59a984b9))


## v0.25.3 (2024-03-08)

### Bug Fixes

- Fix type conversion for SimCamera uniform noise
  ([`238ecb5`](https://github.com/bec-project/ophyd_devices/commit/238ecb5ff84b55f028b75df32fccdc3685609d69))


## v0.25.2 (2024-03-08)

### Bug Fixes

- **smaract**: Added user access for axis_is_referenced and all_axes_referenced
  ([`4fbba73`](https://github.com/bec-project/ophyd_devices/commit/4fbba7393adbb01ebf80667b205a1dbaab9bb15c))

- **smaract**: Fixed axes_referenced
  ([`a9f58d2`](https://github.com/bec-project/ophyd_devices/commit/a9f58d2b5686370a07766ed72903f82f5e2d9cb1))


## v0.25.1 (2024-03-05)

### Bug Fixes

- Device_read should use set_and_publish
  ([`afd7912`](https://github.com/bec-project/ophyd_devices/commit/afd7912329b14bc916e14fd565ebcf7506ecb045))

- Device_status should use set
  ([`6d179ea`](https://github.com/bec-project/ophyd_devices/commit/6d179ea8a8e41374cfe2b92939e0b71b7962f7cb))


## v0.25.0 (2024-03-04)

### Bug Fixes

- Add dependency for env
  ([`eb4e10e`](https://github.com/bec-project/ophyd_devices/commit/eb4e10e86bba9b55623d089572f104d21d96601e))

- Fix bug in computation of negative data within SimMonitor
  ([`f4141f0`](https://github.com/bec-project/ophyd_devices/commit/f4141f0dbf8d98f1d1591c66ccd147099019afc7))

### Features

- Add proxy for h5 image replay for SimCamera
  ([`5496b59`](https://github.com/bec-project/ophyd_devices/commit/5496b59ae2254495845a0fae2754cdd935b4fb7b))

### Refactoring

- Fix _add_noise
  ([`aff4cb2`](https://github.com/bec-project/ophyd_devices/commit/aff4cb227cd2bb857c3e0903e3c3e2710bd05ab7))

- Fix docstrings
  ([`e5fada8`](https://github.com/bec-project/ophyd_devices/commit/e5fada8e9dc43fab6781624388d966743ebc1356))

- Small fix to int return
  ([`9a154f0`](https://github.com/bec-project/ophyd_devices/commit/9a154f01e48e33c0e28921b8a5c59af4d4585aeb))


## v0.24.2 (2024-03-01)

### Bug Fixes

- Sim_monitor negative readback fixed
  ([`91e587b`](https://github.com/bec-project/ophyd_devices/commit/91e587b09271a436e7405c44dda60ea4b536865b))

### Testing

- Add tests for sim
  ([`5ca6812`](https://github.com/bec-project/ophyd_devices/commit/5ca681212f7b8f2225236adcb0da67f29e20b4d5))


## v0.24.1 (2024-02-26)

### Bug Fixes

- Simcamera return uint16, SimMonitor uint32
  ([`dc9634b`](https://github.com/bec-project/ophyd_devices/commit/dc9634b73988b5c3cd430008eac5c94319b33ae1))

### Refactoring

- Cleanup
  ([`961041e`](https://github.com/bec-project/ophyd_devices/commit/961041e07299b1c811e9f0aaf6f7540bca688fd9))

- Cleanup and exclude ComplexConstantModel
  ([`6eca704`](https://github.com/bec-project/ophyd_devices/commit/6eca704adcdc7955d88a60ffc7075d32afba43c9))


## v0.24.0 (2024-02-23)

### Bug Fixes

- Extend bec_device with root, parent, kind
  ([`db00803`](https://github.com/bec-project/ophyd_devices/commit/db00803f539791ceefd5f4f0424b00c0e2ae91e6))

### Documentation

- Added doc strings
  ([`2da6379`](https://github.com/bec-project/ophyd_devices/commit/2da6379e8eb346d856a68a8e5bc678dfff5b1600))

### Features

- Add lmfit for SimMonitor, refactored sim_data with baseclass, introduce slitproxy
  ([`800c22e`](https://github.com/bec-project/ophyd_devices/commit/800c22e9592e288f8fe8dea2fb572b81742c6841))

### Refactoring

- Bugfix in camera data, model constant
  ([`00f1898`](https://github.com/bec-project/ophyd_devices/commit/00f1898a354cd2f557854b02223df11a18f4dde5))

- Fix Kind import in bec_device_base
  ([`8b04b5c`](https://github.com/bec-project/ophyd_devices/commit/8b04b5c84eb4e42c8a0ec7e28727ff907a584a4f))

### Testing

- Added devices for e2e tests
  ([`bc97346`](https://github.com/bec-project/ophyd_devices/commit/bc973467b75d8ee494463afcd82fb84289371586))


## v0.23.1 (2024-02-21)

### Bug Fixes

- Replaced outdated enable_set by read_only
  ([`f91d0c4`](https://github.com/bec-project/ophyd_devices/commit/f91d0c482d194e5f69c7206d0f6ad0971f84b0e1))


## v0.23.0 (2024-02-21)

### Bug Fixes

- Separate BECDevice and BECDeviceBase
  ([`2f2cef1`](https://github.com/bec-project/ophyd_devices/commit/2f2cef10f7fb77e502cbf274a6b350f2feb0ad22))

### Continuous Integration

- Added environment variable for downstream pipelines
  ([`406f27c`](https://github.com/bec-project/ophyd_devices/commit/406f27c27ea9742bc1f33028234e06520cd891be))

### Features

- **static_device_test**: Added check against BECDeviceBase protocol
  ([`82cfefb`](https://github.com/bec-project/ophyd_devices/commit/82cfefb3b969f0fdebc357f8bd5b404ec503d7ce))

### Refactoring

- Made BECDeviceBase a protocol
  ([`84fed4e`](https://github.com/bec-project/ophyd_devices/commit/84fed4ee82980d6a44650bd97070b615d36aa4b2))

### Testing

- **BECDeviceBase**: Add test
  ([`399d6d9`](https://github.com/bec-project/ophyd_devices/commit/399d6d94cc3ce29a67ae7c6daba536aa66df9d76))

- **flomni**: Added more tests
  ([`7a97e05`](https://github.com/bec-project/ophyd_devices/commit/7a97e05e04478394423e398f871629fc9c3ef345))


## v0.22.0 (2024-02-17)

### Features

- Add simulation framework for pinhole scan
  ([`491e105`](https://github.com/bec-project/ophyd_devices/commit/491e105af0871449cd0f48b08c126023aa28445b))

- Extend sim_data to allow execution from function of secondary devices extracted from lookup
  ([`851a088`](https://github.com/bec-project/ophyd_devices/commit/851a088b81cfd7e9d323955f923174a394155bfd))

### Refactoring

- Add DeviceProxy class to sim_framework
  ([`01c8559`](https://github.com/bec-project/ophyd_devices/commit/01c8559319836cca3d5d61267ddfb19791aea902))

refactor(__init__): remove bec_device_base from import

refactor: cleanup __init__

refactor: cleanup

refactor: cleanup, renaming and small fixes to sim_framework.

refactor: cleanup imports

- Quickfix connector/producer import in scaninfo mixin
  ([`65b9f23`](https://github.com/bec-project/ophyd_devices/commit/65b9f23332f440a5d467fde789747166c18e1458))


## v0.21.1 (2024-02-17)

### Bug Fixes

- **deprecation**: Remove all remaining .dumps(), .loads() and producer->connector
  ([`4159f3e`](https://github.com/bec-project/ophyd_devices/commit/4159f3e3ec20727b395808118f3c0c166d9d1c0c))


## v0.21.0 (2024-02-16)

### Bug Fixes

- Fixed import after rebase conflict
  ([`747aa36`](https://github.com/bec-project/ophyd_devices/commit/747aa36837fa823cd2f05e294e2ee9ee83074f43))

- Online changes during flomni comm
  ([`4760456`](https://github.com/bec-project/ophyd_devices/commit/4760456e6318b66fa26f35205f669dbbf7d0e777))

### Features

- Flomni stages
  ([`5e9d3ae`](https://github.com/bec-project/ophyd_devices/commit/5e9d3aed17ce02142f12ba69ea562d6c30b41ae3))

- Flomni stages
  ([`b808659`](https://github.com/bec-project/ophyd_devices/commit/b808659d4d8b1af262d6f62174b027b0736a005a))

- **galil**: Added lights on/off
  ([`366f592`](https://github.com/bec-project/ophyd_devices/commit/366f592e08a4cb50ddae7b3f8ba3aa214574f61f))

### Refactoring

- Formatting; fixed tests for expected return
  ([`bf38e89`](https://github.com/bec-project/ophyd_devices/commit/bf38e89f797bd72b45f2457df19c5c468af7cc9c))

- **fgalil**: Cleanup
  ([`b9e777c`](https://github.com/bec-project/ophyd_devices/commit/b9e777c14e1d4e8804c89e2c401ba5956316bb22))

### Testing

- Added tests for fupr and flomni galil
  ([`1c95220`](https://github.com/bec-project/ophyd_devices/commit/1c95220234b65f95c95d5033551e17a1689f1249))

- **rt_flomni**: Added tests
  ([`6d7fd5f`](https://github.com/bec-project/ophyd_devices/commit/6d7fd5fd9f8c293c834a0e321348f31855658744))


## v0.20.1 (2024-02-13)

### Bug Fixes

- Use getpass.getuser instead of os.getlogin to retrieve user name
  ([`bd42d9d`](https://github.com/bec-project/ophyd_devices/commit/bd42d9d56093316f4a9f90a3329b6b5a6d1c851e))


## v0.20.0 (2024-02-13)

### Refactoring

- Cleanup and renaming according to MR comments
  ([`8cc7e40`](https://github.com/bec-project/ophyd_devices/commit/8cc7e408a52fb6ca98673fa2045f1658cfcc3925))

- Remove send msg to BEC, seems to be not needed
  ([`fa6e24f`](https://github.com/bec-project/ophyd_devices/commit/fa6e24f04894c8e9a6b5920d04468c5194bf45a4))

- **__init__**: Merge branch 'master' into 'cleanup/sim_framework'
  ([`87ff927`](https://github.com/bec-project/ophyd_devices/commit/87ff92796f07f5d54666791f58101212be5e031b))


## v0.19.3 (2024-02-10)

### Bug Fixes

- Add imports for core config updates
  ([`fdb2da5`](https://github.com/bec-project/ophyd_devices/commit/fdb2da5839e72359b53c3837292eeced957e43de))

- Separated core simulation classes from additional devices
  ([`2225daf`](https://github.com/bec-project/ophyd_devices/commit/2225dafb7438f576d7033e220910b4cf8769fd33))

### Features

- Add BECDeviceBase to ophyd_devices.utils
  ([`8ee5022`](https://github.com/bec-project/ophyd_devices/commit/8ee502242457f3ac63c122f81e7600e300fdf73a))

### Refactoring

- Moved bec_scaninfo_mixin to ophyd_devices/utils
  ([`6fb912b`](https://github.com/bec-project/ophyd_devices/commit/6fb912bd9c4453d4474dd0dc5a94676988f356bc))

- Refactored SimMonitor and SimCamera
  ([`96a5f1b`](https://github.com/bec-project/ophyd_devices/commit/96a5f1b86a17f099a935c460baf397d9c93bc612))


## v0.19.2 (2024-02-07)

### Bug Fixes

- Fixed bec_scaninfo_mixin
  ([`ec3ea35`](https://github.com/bec-project/ophyd_devices/commit/ec3ea35744e300fa363be3724f5e6c7b81abe7f1))


## v0.19.1 (2024-02-07)

### Bug Fixes

- Remove set and from sim_signals
  ([`bd128ea`](https://github.com/bec-project/ophyd_devices/commit/bd128ea8a459d08f6018c0d8459a534d6a828073))


## v0.19.0 (2024-01-31)

### Bug Fixes

- Temporal fix for imports
  ([`6cac04a`](https://github.com/bec-project/ophyd_devices/commit/6cac04aa5227340f4e5758e4bfcc1798acbc1ed7))

### Continuous Integration

- Added downstream_pipeline
  ([`eccd1aa`](https://github.com/bec-project/ophyd_devices/commit/eccd1aa539e9e4e34a3d8908da649a8c94bb754f))

- Added security detection
  ([`3b731bb`](https://github.com/bec-project/ophyd_devices/commit/3b731bbf4a1145f91133bf8295a0cf00b4c2e15e))

- Fix secret detection
  ([`2ccd096`](https://github.com/bec-project/ophyd_devices/commit/2ccd096ead884cc5a9916cac389ee4e43add4a68))

### Features

- Introduce new general class to simulate data for devices
  ([`8cc955b`](https://github.com/bec-project/ophyd_devices/commit/8cc955b202bd7b45acba06322779079e7a8423a3))

- Move signals to own file and refactor access pattern to sim_state data.
  ([`6f3c238`](https://github.com/bec-project/ophyd_devices/commit/6f3c2383b5d572cf1f6d51acecb63c786ac16196))

- Refactor simulation, introduce SimCamera, SimMonitor in addition to existing classes
  ([`f311ce5`](https://github.com/bec-project/ophyd_devices/commit/f311ce5d1c082c107f782916c2fb724a34a92099))

### Refactoring

- Remove sleep from trigger, and adressed MR comments in sim_data
  ([`10e9acf`](https://github.com/bec-project/ophyd_devices/commit/10e9acff8adf15386f1de404d99fd6f8f42a5bf3))


## v0.18.0 (2024-01-26)

### Build System

- Fixed dev dependencies
  ([`5759b2a`](https://github.com/bec-project/ophyd_devices/commit/5759b2a814f1f89d17bacf22b9e5743ea8516798))

### Continuous Integration

- Added no-cover to static device test
  ([`97e102f`](https://github.com/bec-project/ophyd_devices/commit/97e102fddb8990a85a6102640545160ffc051d3f))

- Moved dependency to ci pipeline; not needed for dev
  ([`68025e3`](https://github.com/bec-project/ophyd_devices/commit/68025e3341929e9172c8a505cfed2c5ac300d207))

### Features

- Added basic function tests
  ([`b54b5d4`](https://github.com/bec-project/ophyd_devices/commit/b54b5d4b00150ef581247da495804cc5e801e24e))

### Refactoring

- Fixed pragma statement (hopefully)
  ([`257a316`](https://github.com/bec-project/ophyd_devices/commit/257a316f6ed7bf331c0ed5670848f2f58fbf0917))

### Testing

- Added test for static_device_test
  ([`baac1ff`](https://github.com/bec-project/ophyd_devices/commit/baac1ffe879f296c01e09375e6b137effc77a1e4))


## v0.17.1 (2024-01-26)

### Bug Fixes

- Changed default for connecting to a device
  ([`802eb29`](https://github.com/bec-project/ophyd_devices/commit/802eb295562ecc39f833d4baba8820a892c674a2))


## v0.17.0 (2024-01-24)

### Features

- Added static_device_test
  ([`bb02a61`](https://github.com/bec-project/ophyd_devices/commit/bb02a619e56749c03d3efadb0364e845fc4a7724))

- Added tests for connecting devices
  ([`8c6d0f5`](https://github.com/bec-project/ophyd_devices/commit/8c6d0f50cdb61843532c7a2f2a03a421acdb126a))


## v0.16.0 (2023-12-24)

### Bug Fixes

- Fix cobertura syntax in ci-pipeline
  ([`40eb699`](https://github.com/bec-project/ophyd_devices/commit/40eb6999c73bf18af875a3665e1f0006bd645d44))

### Build System

- Fix python requirement
  ([`4362697`](https://github.com/bec-project/ophyd_devices/commit/43626973caaef58b9a3c96e3bcfecba8d163dc09))

### Features

- Add detector, grashopper tomcat to repository
  ([`ca726c6`](https://github.com/bec-project/ophyd_devices/commit/ca726c606605085e2849402cd0fae3865550514f))

### Refactoring

- Fix syntax .gitlab-ci.yml file
  ([`a67d6a2`](https://github.com/bec-project/ophyd_devices/commit/a67d6a2d5f7fda76330eab76be80d0ec1e7a4bef))

- Refactor docstrings
  ([`0d14f9a`](https://github.com/bec-project/ophyd_devices/commit/0d14f9aac6c0eb4fee74cecf5a81b4cf4e496e33))

- Renamed SynAxisOPPAS to SimPositioner; moved readback/setpoint/ismoving signal to sim_signals;
  closes 27
  ([`2db65a3`](https://github.com/bec-project/ophyd_devices/commit/2db65a385524b81bef1943a2a91693f327de4213))

- Replace deprecated imports from typing
  ([`952c92e`](https://github.com/bec-project/ophyd_devices/commit/952c92e4b9e6a64a18f445871147ba4ce62fd2f0))

https://peps.python.org/pep-0585/#implementation

- Temporary add SynAxisOPAAS to __init__.py
  ([`adaa943`](https://github.com/bec-project/ophyd_devices/commit/adaa9435e3f751a13e4eb171de9a6156de7d9cc0))

- Updates related to bec_lib refactoring
  ([`13f75aa`](https://github.com/bec-project/ophyd_devices/commit/13f75aa2fd8c9386d7bfec5c61ecc4d498f55cef))


## v0.15.0 (2023-12-12)

### Bug Fixes

- Add python 3.12 to ci pipeline
  ([`31b9646`](https://github.com/bec-project/ophyd_devices/commit/31b964663c5384de2a6c8858ca3ac8f2cabf5bbb))

- Fix syntax/bug
  ([`069f89f`](https://github.com/bec-project/ophyd_devices/commit/069f89f0e7083d5893619f6335f16b5f52352a1b))

### Documentation

- Add files
  ([`ae5c27f`](https://github.com/bec-project/ophyd_devices/commit/ae5c27f045e21aaae11ae5b937f46ecaa2633f8b))

### Features

- Update ci to default to python3.9
  ([`849e152`](https://github.com/bec-project/ophyd_devices/commit/849e15284f6e1f90e970c0706b158116aed29afa))

### Testing

- Fix bug in usage of mock for tests
  ([`c732855`](https://github.com/bec-project/ophyd_devices/commit/c732855314de3cf452181f9cbcf9a4ff8b97288f))


## v0.14.1 (2023-11-23)

### Bug Fixes

- Bugfix tests DDG
  ([`9e67a7a`](https://github.com/bec-project/ophyd_devices/commit/9e67a7a7d469af0505b60bb29ed54b15ac083806))


## v0.14.0 (2023-11-23)

### Bug Fixes

- Bugfix and reorder call logic in _init
  ([`138d181`](https://github.com/bec-project/ophyd_devices/commit/138d18168fa64a2dfb31218266e1f653a74ff4d5))

- Fix imports of renamed classes
  ([`6780c52`](https://github.com/bec-project/ophyd_devices/commit/6780c523bd2192fc2234296987bdabeb45f81ee4))

### Documentation

- Reviewed docstrings
  ([`da44e5d`](https://github.com/bec-project/ophyd_devices/commit/da44e5d7bb122abda480a918327faf5d460cb396))

- Reviewed docstrings
  ([`d295741`](https://github.com/bec-project/ophyd_devices/commit/d295741bd04930fc4397c89ac039a01c526d2d1e))

### Features

- Add delay_generator_csaxs
  ([`e5c90ee`](https://github.com/bec-project/ophyd_devices/commit/e5c90ee2156ac076d7cea56975c1ed459adb8727))

- Add test for class
  ([`19faece`](https://github.com/bec-project/ophyd_devices/commit/19faece0a5e119e1f1403372c09825748de5e032))

- Create base class for DDG at psi
  ([`d837ddf`](https://github.com/bec-project/ophyd_devices/commit/d837ddfd1cd7935b4f472b976b925d2d70056cd7))

### Refactoring

- Moved burst_enable/disable, set_trigger to base class
  ([`a734116`](https://github.com/bec-project/ophyd_devices/commit/a73411646d86f100dead46698b2f7c8f0684bcb6))

- Remove readme.md for DDG. Classes have sufficient docstrings
  ([`3851983`](https://github.com/bec-project/ophyd_devices/commit/385198342d002c6fed273ff7d68f2e060bc6b9aa))

- Removed burst_enabl/disable etc.. slight refactoring of prepare_ddg
  ([`f218a9b`](https://github.com/bec-project/ophyd_devices/commit/f218a9b11425f25ff38977d366f4eb8e0ae5e886))


## v0.13.4 (2023-11-23)

### Bug Fixes

- Bugfix: remove std_client from psi_det_base_class; closes #25
  ([`3ad0daa`](https://github.com/bec-project/ophyd_devices/commit/3ad0daa5bcefe585d4f89992e49c9856a55e6183))


## v0.13.3 (2023-11-21)

### Bug Fixes

- Add __init__ and super().__init__ to falcon,eiger and pilatus
  ([`9e26fc2`](https://github.com/bec-project/ophyd_devices/commit/9e26fc2a3c82e610d0c570db9a08a698c3394bc8))

- Fix auto_monitor=True for MockPV by add add_callback = mock.MagicMock()
  ([`e7f7f9d`](https://github.com/bec-project/ophyd_devices/commit/e7f7f9d6658a27ca98ac17ffb998efae51ec3497))

- Rename custome_prepare.prepare_detector_backend, bugfix in custom_prepare.wait_for_signals
  ([`f793ec7`](https://github.com/bec-project/ophyd_devices/commit/f793ec7b1f3f2d03a686d592d4cd9c2e2f087faf))

- Renamed to prepare_detector_backend
  ([`16022c5`](https://github.com/bec-project/ophyd_devices/commit/16022c53ef9e3134fe486892c27f26e5c12fad2e))

### Documentation

- Add docstring
  ([`cbe8c8c`](https://github.com/bec-project/ophyd_devices/commit/cbe8c8c4e5a53a0b38a58e11b85b11307e92ced7))

- Add docstrings, improve pylint score
  ([`5874466`](https://github.com/bec-project/ophyd_devices/commit/587446670444f245ec2c24db0355578921b8fe59))

- Imporive pylint score
  ([`5b27e6f`](https://github.com/bec-project/ophyd_devices/commit/5b27e6fe1e20a50894c47144a412b9361ab1c4e6))

### Refactoring

- Fix __ini__ and add comment to psi_detector_base
  ([`3a37de9`](https://github.com/bec-project/ophyd_devices/commit/3a37de9eda90d55714f77192ad949043c3694f2c))

- Mcs_card inherits from base class psi_detector_base
  ([`d77e8e2`](https://github.com/bec-project/ophyd_devices/commit/d77e8e255de46c701b9fa5357a5b740cec269625))

- Mcs_csaxs complies with psi_detector_base
  ([`8bd65b7`](https://github.com/bec-project/ophyd_devices/commit/8bd65b7d671b148f1c0826a27dd6c998e029eac9))

- Remove redundant __init__ calls
  ([`7f6db66`](https://github.com/bec-project/ophyd_devices/commit/7f6db669dbac3680e782c183883f1adb6a0f19c5))

### Testing

- Add tests
  ([`4e7f1b5`](https://github.com/bec-project/ophyd_devices/commit/4e7f1b559347d7472d1912d4c7f64c574d0c8fea))

- Fix test_send_data_to_bec
  ([`a3cf93e`](https://github.com/bec-project/ophyd_devices/commit/a3cf93e41b50b99bf28898ee038662a3cebed712))


## v0.13.2 (2023-11-20)

### Bug Fixes

- Remove duplicated stop call from eiger.custom_prepare.finished
  ([`175700b`](https://github.com/bec-project/ophyd_devices/commit/175700b6ad135cb7491eb88431ecde56704fd0b4))

- Remove stop from falcon.custom_prepare.arm_acquisition; closes #23
  ([`9e1a6da`](https://github.com/bec-project/ophyd_devices/commit/9e1a6daa6edbfe2a9e7c9b15f21af5785a119474))

- Remove stop from pilatus.custom_prepare.finished
  ([`334eeb8`](https://github.com/bec-project/ophyd_devices/commit/334eeb83dc3e1c7c37ce41d2ba5f720c3880ef46))


## v0.13.1 (2023-11-18)

### Bug Fixes

- Include all needed files in packaged distro
  ([`204f94e`](https://github.com/bec-project/ophyd_devices/commit/204f94e0e4496f8347772f869bb0722e6ffb9ccf))

Fix #21


## v0.13.0 (2023-11-17)

### Bug Fixes

- Add PSIDetectorBase
  ([`a8a1210`](https://github.com/bec-project/ophyd_devices/commit/a8a12103ea2108c5183a710ead04db4379627d83))

- Add remaining function, propose mechanism to avoid calling stage twice
  ([`3e1a2b8`](https://github.com/bec-project/ophyd_devices/commit/3e1a2b86c31a241ac92ef9808ad2b92fed020ec8))

- Add User_access to cSAXS falcon and eiger
  ([`e8ec101`](https://github.com/bec-project/ophyd_devices/commit/e8ec101f5399ac7be2aeb1b1d69d6866d6d2f69b))

- Bugfix
  ([`7fefb44`](https://github.com/bec-project/ophyd_devices/commit/7fefb44462c4bfa7853b0519b33ef492ace53050))

- Changed file_writer to det_fw
  ([`575b4e6`](https://github.com/bec-project/ophyd_devices/commit/575b4e6260e95d4c4c40d76b3fc38f258e43a381))

- Fix imports to match bec_lib changes
  ([`9db00ad`](https://github.com/bec-project/ophyd_devices/commit/9db00add047536c7aa35d2b08daafb248d5c8c01))

- Fixed imports to comply with bec_lib refactoring
  ([`79cfaf6`](https://github.com/bec-project/ophyd_devices/commit/79cfaf6dc03bad084673fe1945828c15bba4b6e8))

- Fixed merge conflict
  ([`d46dafd`](https://github.com/bec-project/ophyd_devices/commit/d46dafdbe85b9f2a1c080297bd361a3445779d60))

- Fixed MIN_readout, and made it a class attribute with set/get functions
  ([`b9d0a5d`](https://github.com/bec-project/ophyd_devices/commit/b9d0a5d86977ff08962a27ac507296ca5dae229c))

- Removed __init__ from eiger9mcSAXS
  ([`c614873`](https://github.com/bec-project/ophyd_devices/commit/c614873f8f913e0c1d417b63cf6dea2f39708741))

- Removed sls_detector_baseclass, add psi_detector_base, fixed tests and eiger9m_csaxs
  ([`90cd05e`](https://github.com/bec-project/ophyd_devices/commit/90cd05e68ea7640a6bc1a8b98d47f9edc7a7f3a0))

- Small bugfix
  ([`ee5cf17`](https://github.com/bec-project/ophyd_devices/commit/ee5cf17a05ededda6eff25edece6d6f437d0f372))

### Features

- Add CustomDetectorMixin, and Eiger9M setup to separate core functionality in the ophyd integration
  ([`c8f05fe`](https://github.com/bec-project/ophyd_devices/commit/c8f05fe290485dd7703dfb7a4bfc660d7d01d67d))

- Add docstring to detector base class; closes #12
  ([`2252779`](https://github.com/bec-project/ophyd_devices/commit/225277949d91febd4482475a12c1ea592b735385))

- Add SLSDetectorBaseclass as a baseclass for detectors at SLS
  ([`13180b5`](https://github.com/bec-project/ophyd_devices/commit/13180b56dac614206ca5a8ad088e223407b83977))

- Refactor falcon for psi_detector_base class; adapted eiger; added and debugged tests
  ([`bcc3210`](https://github.com/bec-project/ophyd_devices/commit/bcc321076153ccd6ae8419b95553b5b4916e82ad))

### Refactoring

- Clean up code
  ([`4c86f8c`](https://github.com/bec-project/ophyd_devices/commit/4c86f8cfb2f816faa76493c0c471374a5f155566))

- Refactored pilatus to psi_detector_base class and adapted tests
  ([`e9d9711`](https://github.com/bec-project/ophyd_devices/commit/e9d9711aa7cc70de4490433844b6b92130c56650))

- Refactored pylint formatting
  ([`8bf208e`](https://github.com/bec-project/ophyd_devices/commit/8bf208e6975184714dae728a29c5b84cde073ebd))

### Testing

- Remove tests from pylint check
  ([`6e4b7c6`](https://github.com/bec-project/ophyd_devices/commit/6e4b7c6b18ccce6f60c503f47a4082d5a6eeabbd))


## v0.12.0 (2023-11-17)

### Features

- Added syndynamiccomponents for BEC CI tests
  ([`824ae0b`](https://github.com/bec-project/ophyd_devices/commit/824ae0bde63f2ba5278e532812fe41d07f179099))


## v0.11.0 (2023-11-16)

### Features

- Add pylint check to ci pipeline
  ([`a45ffe7`](https://github.com/bec-project/ophyd_devices/commit/a45ffe7740714a57aad54fbc56164971144a6b7d))

### Refactoring

- Fix bec_lib imports
  ([`d851cf6`](https://github.com/bec-project/ophyd_devices/commit/d851cf6f8e7bb80eee64866584f2acc9350b8c46))


## v0.10.2 (2023-11-12)

### Bug Fixes

- Remove pytest dependency for eiger, falcon and pilatus; closes #18 and #9
  ([`c6e6737`](https://github.com/bec-project/ophyd_devices/commit/c6e6737547face4f298758e4017099208748d1a9))

### Refactoring

- Add configurable timeout and ClassInitError
  ([`a7d713b`](https://github.com/bec-project/ophyd_devices/commit/a7d713b50d7b65f39f4975cfecb2159cb6a87a6c))

- Refacoring of falcon sitoro
  ([`97b6111`](https://github.com/bec-project/ophyd_devices/commit/97b61118321dd13bf1a41b8e24e6bc84d77af16a))

- Refactore falcon __init__
  ([`38db08c`](https://github.com/bec-project/ophyd_devices/commit/38db08c87749ad8e1c75920b0efdd93c5cf9d622))

- Remove obsolet test.py function; relates to #19
  ([`a4efb59`](https://github.com/bec-project/ophyd_devices/commit/a4efb59589c8530ee9f45a44f2ed7137e4672c07))

### Testing

- Fix mock_cl.thread_class for eiger,falcon and pilatus; add tests for falcon csaxs; fix bugs in
  code based on tests
  ([`e3e134c`](https://github.com/bec-project/ophyd_devices/commit/e3e134c65d63305289137ce525db3dcf6733c453))


## v0.10.1 (2023-11-09)

### Bug Fixes

- Adding pytest as dependency; should be removed!
  ([`a6a621f`](https://github.com/bec-project/ophyd_devices/commit/a6a621f5ea88370152256908cdd4d60ce4489c7b))

### Refactoring

- Fixed formatting
  ([`b59f9b4`](https://github.com/bec-project/ophyd_devices/commit/b59f9b40ed33d3215fbf6a86a65b6e853edfe03e))


## v0.10.0 (2023-11-08)

### Bug Fixes

- Changed dependency injection for controller classes; closes #13
  ([`fb9a17c`](https://github.com/bec-project/ophyd_devices/commit/fb9a17c5e383e2a378d0a3e9cc7cc185dd20c96e))

- Fixed drive_to_limit
  ([`1aae1eb`](https://github.com/bec-project/ophyd_devices/commit/1aae1eba12c05dfa5c4196edec3be488fa4f2b1e))

- Fixed drive_to_limit
  ([`3eea89a`](https://github.com/bec-project/ophyd_devices/commit/3eea89acc5b2e18dd9d7b4a91e50590ca9702bba))

- Fixed fupr axis_is_referenced
  ([`ce94a6a`](https://github.com/bec-project/ophyd_devices/commit/ce94a6a88df6f90409c4fb4c29260ad77048f27d))

- Fixed fupr axis_is_referenced
  ([`3396ff4`](https://github.com/bec-project/ophyd_devices/commit/3396ff44d94955155c38a84a08880b93cb400cca))

- Fixed fupr axis_is_referenced
  ([`d72dc82`](https://github.com/bec-project/ophyd_devices/commit/d72dc82264051e3e0a77527b06d29bd055e7bcdc))

- Fixed fupr number of axis
  ([`9080d45`](https://github.com/bec-project/ophyd_devices/commit/9080d45075158b1a7d7a60838ea33f058260755f))

- Fixed id assignment
  ([`9b3139e`](https://github.com/bec-project/ophyd_devices/commit/9b3139ecf106150170d2299303997d3dd8a97b4d))

- Fixed import for fgalil
  ([`3f76ef7`](https://github.com/bec-project/ophyd_devices/commit/3f76ef76d736965b3257770efee1d2971afd90b3))

- Fixed import; fixed file name
  ([`2ddc074`](https://github.com/bec-project/ophyd_devices/commit/2ddc074e4fe9638bac77df5f3bbd2b1c4600814c))

### Features

- Added fupr
  ([`9840491`](https://github.com/bec-project/ophyd_devices/commit/9840491ab7f92eacdb7616b9530659b1800654af))

- Added galil for flomni
  ([`7b17b84`](https://github.com/bec-project/ophyd_devices/commit/7b17b8401a516613ee3e67f1e03892ba573e392c))

- Added support for flomni galil
  ([`23664e5`](https://github.com/bec-project/ophyd_devices/commit/23664e542cfcccafe31d0e41d1421c277bd00d23))

### Refactoring

- Cleanup and unifying galil classes
  ([`981b877`](https://github.com/bec-project/ophyd_devices/commit/981b87703884299bf193ad73bf65a0e716091cd3))

### Testing

- Fixed controller init
  ([`89cf412`](https://github.com/bec-project/ophyd_devices/commit/89cf4125516bc1b398d213c9f30ec115da5af0bf))


## v0.9.2 (2023-11-08)

### Bug Fixes

- Bugfixes after adding tests
  ([`72b8848`](https://github.com/bec-project/ophyd_devices/commit/72b88482ca8b5104dbcf3e8a4e430497eb5fd5f8))

### Refactoring

- Add _send_requests_delete
  ([`4ce26b5`](https://github.com/bec-project/ophyd_devices/commit/4ce26b5dd5e6bdb3ff9926ffcbce17a70afe98ae))

- Add min_readouttime, add complemented test cases; closes #11 #10
  ([`ba01cf7`](https://github.com/bec-project/ophyd_devices/commit/ba01cf7b2da25d40611f0a059493ac22f66a36c7))

- Addressed comments from review; fixed docstring; add DeviceClassInitError
  ([`bda859e`](https://github.com/bec-project/ophyd_devices/commit/bda859e93d171602e8fa7de1d88d8f2bfe22230f))

- Class renaming and minor changes in variable names
  ([`5d02a13`](https://github.com/bec-project/ophyd_devices/commit/5d02a13ad0fea7e07c41a2ece291df190328bc4c))

- Fixed tests and mocks for refactor init
  ([`256aa41`](https://github.com/bec-project/ophyd_devices/commit/256aa41690e19a165b3ee17119e380893c568a08))

- Generalize sim_mode
  ([`9dcf92a`](https://github.com/bec-project/ophyd_devices/commit/9dcf92af006ba903f2aedc970f468e470b2dd05c))

- Refactored tests and eiger
  ([`d2cd6a4`](https://github.com/bec-project/ophyd_devices/commit/d2cd6a442baced6ce8b6a7fa04a36290515fb87e))

- Remove bluesky runengine dependency from re_test.py
  ([`57a4362`](https://github.com/bec-project/ophyd_devices/commit/57a436261c46a3287320b7dfc0a29e16a9482f33))

- Remove test case without sim_mode from init, fix pending
  ([`70ba2ba`](https://github.com/bec-project/ophyd_devices/commit/70ba2baedcfa64c81e5c9e70e297a02e275f57ee))

- Rename infomsgmock and add docstrings
  ([`8a19ce1`](https://github.com/bec-project/ophyd_devices/commit/8a19ce1508d7d00d4999aa89b5bb0537f973bc54))

- Renaming
  ([`a80d13a`](https://github.com/bec-project/ophyd_devices/commit/a80d13ae66e066b2fad6d8493b20731fb40f3677))

- Requests put and delete moved to separate functions
  ([`13d26c6`](https://github.com/bec-project/ophyd_devices/commit/13d26c65379704291526b45397e8160668aec57a))

### Testing

- Add first tests for pilatus
  ([`a02e0f0`](https://github.com/bec-project/ophyd_devices/commit/a02e0f09b0f30e1b1ad73bf7f51b06c4bf9ab51c))

- Add tests for close and stop filewriter
  ([`d3e8ece`](https://github.com/bec-project/ophyd_devices/commit/d3e8ece029c0d672888cc43f05cf2258684de801))

- Add tests for eiger
  ([`78ba00c`](https://github.com/bec-project/ophyd_devices/commit/78ba00ce14490ac38bb0439737faced6ae7282a3))

- Fix test to mock PV access
  ([`7e9abdb`](https://github.com/bec-project/ophyd_devices/commit/7e9abdb32310037b115b12bf439bdbe5f3724948))

- Fixed all eiger test with updated mock PV; closes #11
  ([`cb49a2a`](https://github.com/bec-project/ophyd_devices/commit/cb49a2a2055de471200d1a26bdb762676a199708))

- Fixed pilatus tests; closes #10
  ([`188c832`](https://github.com/bec-project/ophyd_devices/commit/188c8321cab0be96a2b5e435b6efbc4c39c9872d))

- Fixed tests
  ([`cf4f195`](https://github.com/bec-project/ophyd_devices/commit/cf4f195365aa3aa4bf0083a146cb1154b6feed58))

- Fixed tests for eigerl; closes #11
  ([`6b0b8de`](https://github.com/bec-project/ophyd_devices/commit/6b0b8de8c0a869577cd233814bad48b9e1a806c4))

- Resolved problem after merge conflict
  ([`f32fdbc`](https://github.com/bec-project/ophyd_devices/commit/f32fdbc845b445f1254207d7a2c1780ff6f958f1))

- Test init filewriter
  ([`ee77013`](https://github.com/bec-project/ophyd_devices/commit/ee77013ba29d705de3b1f499ea6c9256c3a6194b))


## v0.9.1 (2023-11-02)

### Bug Fixes

- Fixed complete call for non-otf scans
  ([`9e6dc2a`](https://github.com/bec-project/ophyd_devices/commit/9e6dc2a9f72c5615abd8bea1fcdea6719a35f1ad))


## v0.9.0 (2023-10-31)

### Features

- Added file-based replay for xtreme
  ([`d25f92c`](https://github.com/bec-project/ophyd_devices/commit/d25f92c6323cccea6de8471f4445b997cfab85a3))

### Refactoring

- Add _init function to all classes
  ([`55d20a0`](https://github.com/bec-project/ophyd_devices/commit/55d20a0ed056b0f2855a89b14672d1ee8f3a99a7))

- Add comment to loggers in _update_std_cfg
  ([`4c6e99a`](https://github.com/bec-project/ophyd_devices/commit/4c6e99af118c0987a6b01c28cce503ecfa63d0a5))

- Add docstrings and clean cam classes; dxp and hdf for falcon
  ([`702b212`](https://github.com/bec-project/ophyd_devices/commit/702b212f50629d9ccf36071d38cc001fc155c1da))

- Add docstrings to errors
  ([`88d3b92`](https://github.com/bec-project/ophyd_devices/commit/88d3b92b33c9076311a3ff4ce012de94cf6de758))

- Add documentation, clean up init function and unify classes
  ([`22e63c4`](https://github.com/bec-project/ophyd_devices/commit/22e63c4976eb2c19acc3234ccb8296dbed1b3d22))

- Change _init filewriter and detector for eiger9m
  ([`920d7bb`](https://github.com/bec-project/ophyd_devices/commit/920d7bb2b108e8f48d8b28ae3b5e35fcb9113e05))

- Change _init for falcon detector
  ([`6f49be4`](https://github.com/bec-project/ophyd_devices/commit/6f49be47758a269e8f5f8a8ca9661f8e79dfafda))

- Change _init for pilatus
  ([`c5951b3`](https://github.com/bec-project/ophyd_devices/commit/c5951b3c5bea572a8962d920c780870a78e98d39))

- Cleanup import for detectors
  ([`217c27b`](https://github.com/bec-project/ophyd_devices/commit/217c27bfdb38e7b1141565317b69c4955d5b6df4))

- Eiger, adapt publish file
  ([`7346f5d`](https://github.com/bec-project/ophyd_devices/commit/7346f5d76aa82c2fe34b1d8df18f95cb37b664d7))

- Eiger, add documentation for stage
  ([`cbeb679`](https://github.com/bec-project/ophyd_devices/commit/cbeb6794784a116a03f5a95858320965e6a86b2a))

- Eiger, add trigger function
  ([`e6d05c9`](https://github.com/bec-project/ophyd_devices/commit/e6d05c9d022a13fa93d2642ef8560a0c38a425ac))

- Eiger, fix _on_trigger
  ([`8eb60a9`](https://github.com/bec-project/ophyd_devices/commit/8eb60a980aa209796a8c0f5d87de4c1624ef34ef))

- Eiger, refactoring done of unstage, stop and closing det and filewriter
  ([`d9606a4`](https://github.com/bec-project/ophyd_devices/commit/d9606a47075847219a0e0a0bd63f7b533e1606fa))

- Eiger, small bugfix
  ([`583c61f`](https://github.com/bec-project/ophyd_devices/commit/583c61ff411bb87349297c9163453a7ba8f5876c))

- Eiger, small refactoring of docs and names
  ([`0f5fe04`](https://github.com/bec-project/ophyd_devices/commit/0f5fe04e59ae7054567b72fdfeec4dd8d3f96d78))

- Eiger9m stage function, refactoring
  ([`6dae767`](https://github.com/bec-project/ophyd_devices/commit/6dae767c5e21cd1e6ce3e045e6d99bf984098c2c))

- Falcon, adapt to eiger refactoring
  ([`0dec88e`](https://github.com/bec-project/ophyd_devices/commit/0dec88eda59e33de5763199ea6db2f98d8f71a2d))

- Falcon, add trigger function
  ([`7f4082a`](https://github.com/bec-project/ophyd_devices/commit/7f4082a6e9071c853c826d84aa5de1b2f46bb1a5))

- Pilatus bugfix
  ([`7876510`](https://github.com/bec-project/ophyd_devices/commit/78765100bada2afebea8f3b6c266859d53af341d))

- Pilatus changes from stage and minor changes for eiger and falcon
  ([`08e35df`](https://github.com/bec-project/ophyd_devices/commit/08e35df0f2acb44b657318c0c499f149fbbadb8a))

- Prep detector and filewriter for falcon; stage refactored
  ([`4c120b0`](https://github.com/bec-project/ophyd_devices/commit/4c120b0d4f4f1bd6a5a2d55a96d8ee7b85eb97a4))

- Reworked arm to
  ([`ce8616a`](https://github.com/bec-project/ophyd_devices/commit/ce8616a9798f191659e8dd1afa52d9038e4cff84))

- Small change on eiger arm
  ([`c2e4bbc`](https://github.com/bec-project/ophyd_devices/commit/c2e4bbc4067427113f0a1ec1ede69a2c84a381e5))


## v0.8.1 (2023-09-27)

### Bug Fixes

- Add ndarraymode and formatting
  ([`712674e`](https://github.com/bec-project/ophyd_devices/commit/712674e4b8f662b3081d21ed7c2d053260a728e6))

- Fixed formatting
  ([`48445e8`](https://github.com/bec-project/ophyd_devices/commit/48445e8b61031496712bfdb262a944c6d058029f))

- Online changes e21536
  ([`0372f6f`](https://github.com/bec-project/ophyd_devices/commit/0372f6f726f14b3728921ca498634b4c4ad5e0cb))


## v0.8.0 (2023-09-15)

### Bug Fixes

- Format online changes via black
  ([`f221f9e`](https://github.com/bec-project/ophyd_devices/commit/f221f9e88ee40e7e24a572d7f12e80a98d70f553))

- Minor changes on the sgalil controller
  ([`b6bf7bc`](https://github.com/bec-project/ophyd_devices/commit/b6bf7bc9b3b5e4e581051bec2822d329da432b50))

- Online changes DDG
  ([`c261fbb`](https://github.com/bec-project/ophyd_devices/commit/c261fbb55a3379f17cc7a14e915c6c5ec309281b))

- Online changes e20636 falcon
  ([`7939045`](https://github.com/bec-project/ophyd_devices/commit/793904566dfb4bd1a22ac349f270a5ea2c7bc75f))

- Online changes e20636 mcs
  ([`bb12181`](https://github.com/bec-project/ophyd_devices/commit/bb12181020b8ebf16c13d13e7fabc9ad8cc26909))

- Online changes e20643
  ([`0bf308a`](https://github.com/bec-project/ophyd_devices/commit/0bf308a13d55f795c6537c66972a80d66ec081dd))

- Online changes eiger9m
  ([`e299c71`](https://github.com/bec-project/ophyd_devices/commit/e299c71ec060f53563529f64ab43c6906efd938c))

- Online changes in e20639 for mcs card operating full 2D grid
  ([`67115a0`](https://github.com/bec-project/ophyd_devices/commit/67115a0658b1122881332e90a3ae9fa2780ca129))

- Online changes pilatus_2 e20636
  ([`76f88ef`](https://github.com/bec-project/ophyd_devices/commit/76f88efa31b1c599a7ee8233a7721aed30e6a611))

- Online changes sgalil e20636
  ([`592ddfe`](https://github.com/bec-project/ophyd_devices/commit/592ddfe6da87af467cfe507b46d423ccb03c21dd))

- Small changes in epics_motor_ex, potentially only comments
  ([`f9f9ed5`](https://github.com/bec-project/ophyd_devices/commit/f9f9ed5e23d7478c5661806b67368c9e4711c9f5))

### Features

- First draft for Epics sequencer class
  ([`c418b87`](https://github.com/bec-project/ophyd_devices/commit/c418b87ad623f32368197a247e83fc99444dc071))


## v0.7.0 (2023-09-07)

### Features

- Add timeout functionality to ophyd devices
  ([`c80d9ab`](https://github.com/bec-project/ophyd_devices/commit/c80d9ab29bcc85a46b59f3be8fb86b990c3ed299))


## v0.6.0 (2023-09-07)


## v0.5.0 (2023-09-01)

### Bug Fixes

- Add bec producer message to stage
  ([`83c395c`](https://github.com/bec-project/ophyd_devices/commit/83c395cf3511bb56d0f58b75bb5c00c5bc00992f))

- Add flyscan option
  ([`3258e3a`](https://github.com/bec-project/ophyd_devices/commit/3258e3a1c7e799c4d718dc9cb7f5abfcf87e59f3))

- Add initialization functionality
  ([`41e0e40`](https://github.com/bec-project/ophyd_devices/commit/41e0e40bc70d4b4547d331cf237feeaa39b5d721))

- Add readout time to mock scaninfo
  ([`8dda7f3`](https://github.com/bec-project/ophyd_devices/commit/8dda7f30c1e797287ddf52f6448604c1052ce3ce))

- Add status update std_daq
  ([`39142ff`](https://github.com/bec-project/ophyd_devices/commit/39142ffc92440916b6c68beb260222f4dd8a0548))

- Add std_daq_client and pyepics to setup
  ([`5d86382`](https://github.com/bec-project/ophyd_devices/commit/5d86382d80c033fb442afef74e95a19952cd5937))

- Added pyepics dependency
  ([`66d283b`](https://github.com/bec-project/ophyd_devices/commit/66d283baeb30da261d0f27e73bca4c9b90d0cadd))

- Adjust ophyd class layout
  ([`eccacf1`](https://github.com/bec-project/ophyd_devices/commit/eccacf169bf0a265fac1e20e8fe86af6277a9d4a))

- Adjusted __init__ for epics motor extension
  ([`ac8b96b`](https://github.com/bec-project/ophyd_devices/commit/ac8b96b9ba76ba52920aeca7486ca9046e07326c))

- Adjusted delaygen
  ([`17347ac`](https://github.com/bec-project/ophyd_devices/commit/17347ac93032c9b57247d9f565f638340a9973af))

- Bec_utils mixin
  ([`ed0ef33`](https://github.com/bec-project/ophyd_devices/commit/ed0ef338eb606977993d45c98421ebde0f477927))

- Bugfix for polarity
  ([`fe404bf`](https://github.com/bec-project/ophyd_devices/commit/fe404bff9c960ff8a3f56686b24310d056ad4eda))

- Bugfix in delaygenerators
  ([`2dd8f25`](https://github.com/bec-project/ophyd_devices/commit/2dd8f25c8727759a8cf98a0abee87e379c9307d7))

- Bugfix online fixes
  ([`ba9cb77`](https://github.com/bec-project/ophyd_devices/commit/ba9cb77ed9b0d1a7e0f744558360c90f393b6f08))

- Changes for sgalil grid scan from BEC
  ([`3e594b5`](https://github.com/bec-project/ophyd_devices/commit/3e594b5e0461d43431e0103cb713bcd9fd22ca1c))

- Ddg logic to wait for burst in trigger
  ([`5ce6fbc`](https://github.com/bec-project/ophyd_devices/commit/5ce6fbcbb92d2fafb6cfcb4bb7b1f5ee616140b8))

- Falcon updates
  ([`b122de6`](https://github.com/bec-project/ophyd_devices/commit/b122de69acfd88d82eaba85534840e7fae21b718))

- Fix ddg code
  ([`b3237ce`](https://github.com/bec-project/ophyd_devices/commit/b3237ceda5468058e294da4a3e608c4344e582dc))

- Fixed stop command
  ([`d694f65`](https://github.com/bec-project/ophyd_devices/commit/d694f6594d0bd81fd62be570142bc2f6b19cf6f4))

- Mcs updates
  ([`14ca550`](https://github.com/bec-project/ophyd_devices/commit/14ca550af143cdca9237271311b9c5ea280d7809))

- Mcs working
  ([`08efb64`](https://github.com/bec-project/ophyd_devices/commit/08efb6405bc615b40855288067c1e811f1471423))

- Online changes
  ([`3a12697`](https://github.com/bec-project/ophyd_devices/commit/3a126976cd7cfb3f294556110d77249da6fbc99d))

- Online changes
  ([`b6101cc`](https://github.com/bec-project/ophyd_devices/commit/b6101cced24b8b37a3363efa5554a627fdc875b1))

- Online changes SAXS
  ([`911c8a2`](https://github.com/bec-project/ophyd_devices/commit/911c8a2438c9cdf1ca2a9685e1dbbbf4a1913f5c))

- Online changes to all devices in preparation for beamtime
  ([`c0b3418`](https://github.com/bec-project/ophyd_devices/commit/c0b34183661b11c39d65eb117c3670a714f9eb5c))

- Online changes to integrate devices in BEC
  ([`fbfa562`](https://github.com/bec-project/ophyd_devices/commit/fbfa562713adaf374dfaf67ebf30cbd1895dd428))

- Pil300k device, pending readout
  ([`b91f8db`](https://github.com/bec-project/ophyd_devices/commit/b91f8dbc6854cf46d1d504610855d50563a8df36))

- Running ophyd for mcs card, pending fix mcs_read_all epics channel
  ([`7c45682`](https://github.com/bec-project/ophyd_devices/commit/7c45682367c363207257fff7b6ce53ffee1449df))

- Sgalil scan
  ([`cc6c8cb`](https://github.com/bec-project/ophyd_devices/commit/cc6c8cb41bc6e3388a580adeee0af8a1c7dbca27))

- Stage works again, unstage not yet
  ([`96d746c`](https://github.com/bec-project/ophyd_devices/commit/96d746c2860221d336a755535e920ea0af8375b9))

- Stepscan logic implemented in ddg
  ([`c365b8e`](https://github.com/bec-project/ophyd_devices/commit/c365b8e9543ac0eca3bc3da34f662422e7daeef7))

- Test function
  ([`2dc3290`](https://github.com/bec-project/ophyd_devices/commit/2dc3290787a2c2cc79141b9d1da3a805b2c67ccd))

- Use bec_scaninfo_mixin in ophyd class
  ([`6ee819d`](https://github.com/bec-project/ophyd_devices/commit/6ee819de53d39d8d14a4c4df29b0781f83f930ec))

- Working acquire, line and grid scan using mcs, ddg and eiger9m
  ([`58caf2d`](https://github.com/bec-project/ophyd_devices/commit/58caf2ddd3416deaace82b6e321fc0753771b282))

- Working mcs readout
  ([`8ad3eb2`](https://github.com/bec-project/ophyd_devices/commit/8ad3eb29b79a0a8a742d1bc319cfedf60fcc150f))

### Features

- Add bec_scaninfo_mixin to repo
  ([`01c824e`](https://github.com/bec-project/ophyd_devices/commit/01c824ecead89a1c83cefacff53bf9f76b02d423))

- Add bec_utils to repo for generic functions
  ([`86e93af`](https://github.com/bec-project/ophyd_devices/commit/86e93afe28fc91b5c0a773c489d99cf272c52878))

- Add ConfigSignal to bec_utils
  ([`ac6de9d`](https://github.com/bec-project/ophyd_devices/commit/ac6de9da54444dda21820591dd8e3ad098d3f0ac))

- Add eiger9m csaxs
  ([`f3e4575`](https://github.com/bec-project/ophyd_devices/commit/f3e4575359994c134e1b207915fadb9f8f92e4d9))

- Add falcon and progress bar option to devices
  ([`3bab432`](https://github.com/bec-project/ophyd_devices/commit/3bab432a2f01e3a62811e13b9143d67da495fbb8))

- Add mcs ophyd device
  ([`448890a`](https://github.com/bec-project/ophyd_devices/commit/448890ab27ba1bfeb24870d792c498b96aa7cc47))

- Add mcs_readout_monitor and stream
  ([`ab22056`](https://github.com/bec-project/ophyd_devices/commit/ab220562fc1eac3bcffff01fd92085445dd774e7))

- Added derived signals for xtreme
  ([`1276e1d`](https://github.com/bec-project/ophyd_devices/commit/1276e1d0db44315d8e95cdf19ec32d68c7426fc8))

- Added falcon ophyd device to repo
  ([`88b238a`](https://github.com/bec-project/ophyd_devices/commit/88b238ac13856ed1593dd01b9d2f7a762ca00111))

- Adding mcs card to repository
  ([`96a131d`](https://github.com/bec-project/ophyd_devices/commit/96a131d3743c8d62aaac309868ac1309d83fe9aa))

- Bec_scaninfo_mixin class for scaninfo
  ([`49f95e0`](https://github.com/bec-project/ophyd_devices/commit/49f95e04765e2e4035c030a35272bdb7f06f8d8f))

- Extension for epics motors from xiaoqiang
  ([`057d93a`](https://github.com/bec-project/ophyd_devices/commit/057d93ab60d2872b2b029bdc7b6dcab35a6a21a5))

### Refactoring

- Bugfix
  ([`e8f2f82`](https://github.com/bec-project/ophyd_devices/commit/e8f2f8203934381898d05709e06cd32e66692914))

- Class refactoring, pending change to SlsDetectorCam
  ([`b1150c4`](https://github.com/bec-project/ophyd_devices/commit/b1150c41fe4199be91ed164e089db5379a8f0435))

- Class refactoring, with other 2 detectors
  ([`fb8619d`](https://github.com/bec-project/ophyd_devices/commit/fb8619d0473dbd16ed147503662f7372b3b5d638))

- Eiger9m updates, operation in gating mode
  ([`053f1d9`](https://github.com/bec-project/ophyd_devices/commit/053f1d91814905fa3fa20a79f9a986ac19942c7b))

- Online changes
  ([`2786791`](https://github.com/bec-project/ophyd_devices/commit/278679125ee50bd1de4daf3c4aa08d2afaa43c20))

- Refactoring of eiger9m class, alsmost compatible with pilatus
  ([`287c667`](https://github.com/bec-project/ophyd_devices/commit/287c667621582506dd85c02c022a4aeddba1fb7b))

- Remove some unnecessary test code
  ([`c969927`](https://github.com/bec-project/ophyd_devices/commit/c96992798d291773e202caabf421000c74fa79d3))

- Updated scaninfo mix
  ([`7de0ff2`](https://github.com/bec-project/ophyd_devices/commit/7de0ff236c4afe14dbe16540653183af25353e36))


## v0.4.0 (2023-08-18)

### Bug Fixes

- Simple end-to-end test works at beamline
  ([`28b91ee`](https://github.com/bec-project/ophyd_devices/commit/28b91eeda22af03c3709861ff7fb045fe5b2cf9b))

### Features

- Add pilatus_2 ophyd class to repository
  ([`9476fde`](https://github.com/bec-project/ophyd_devices/commit/9476fde13ab427eba61bd7a5776e8b71aca92b0a))


## v0.3.0 (2023-08-17)

### Bug Fixes

- Bugfix burstenable and burstdisalbe
  ([`f3866a2`](https://github.com/bec-project/ophyd_devices/commit/f3866a29e9b7952f6b416758a067bfa2940ca945))

- Bugfix on delaystatic and dummypositioner
  ([`416d781`](https://github.com/bec-project/ophyd_devices/commit/416d781d16f46513d6c84f4cf3108e61b4a37bc2))

- Bugfix stage/unstage
  ([`39220f2`](https://github.com/bec-project/ophyd_devices/commit/39220f20ea7f81825fe73fbc37592462f2e02a6e))

- Limit handling flyscan and error handling axes ref
  ([`a620e6c`](https://github.com/bec-project/ophyd_devices/commit/a620e6cf5077272d306fc7636e5a8eee1741068f))

- Small fixes to fly_grid_scan
  ([`87ac0ed`](https://github.com/bec-project/ophyd_devices/commit/87ac0edf999eb2bc589e69807ffc6e980241a19f))

### Documentation

- Add documentation for delay generator
  ([`7ad423b`](https://github.com/bec-project/ophyd_devices/commit/7ad423b36434ad05d2f9b46824b6d850f55861f2))

- Details on encoder reading of sgalilg controller
  ([`e0d93a1`](https://github.com/bec-project/ophyd_devices/commit/e0d93a1561ca9203aaf1b5aaf2d6a0dec9f0689e))

- Documentation update
  ([`5d9fb98`](https://github.com/bec-project/ophyd_devices/commit/5d9fb983301a5513a1fb9a9a3ed56537626848ee))

- Updated documentation
  ([`eb3e90e`](https://github.com/bec-project/ophyd_devices/commit/eb3e90e8a25834cbba5692eda34013f63295737f))

### Features

- Add continous readout of encoder while scanning
  ([`69fdeb1`](https://github.com/bec-project/ophyd_devices/commit/69fdeb1e965095147dc18dc0abfe0b7962ba8b38))

- Add readout_encoder_position to sgalil controller
  ([`a94c12a`](https://github.com/bec-project/ophyd_devices/commit/a94c12ac125211f16dfcda292985d883e770b44b))

- Adding io access to delay pairs
  ([`4513110`](https://github.com/bec-project/ophyd_devices/commit/451311027a50909247aaf99571269761b68dcb27))

- Read_encoder_position, does not run yet
  ([`9cb8890`](https://github.com/bec-project/ophyd_devices/commit/9cb889003933bf296b9dc1d586f7aad50421d0cf))

### Refactoring

- Bugfix of sgalil flyscans
  ([`291e9ba`](https://github.com/bec-project/ophyd_devices/commit/291e9ba04b4e899536d1a5a69c123df7decfdb13))

- Fix format sgalil
  ([`b267284`](https://github.com/bec-project/ophyd_devices/commit/b267284e977c55babfbda4e7a6c302b8785efe8c))

- Fix formatting DDG
  ([`0d74b34`](https://github.com/bec-project/ophyd_devices/commit/0d74b34121696922cf4caa647d5cba10f7d29452))

- Small adjustments to fly scans
  ([`04b4bd5`](https://github.com/bec-project/ophyd_devices/commit/04b4bd509c3a10124f527194cc1c4d5756a38328))

- Small bugfix and TODO comments
  ([`7782d5f`](https://github.com/bec-project/ophyd_devices/commit/7782d5faabd897803f8f4b4172a4e2b5d297a346))


## v0.2.1 (2023-07-21)

### Bug Fixes

- Fixed sim readback timestamp
  ([`7a47134`](https://github.com/bec-project/ophyd_devices/commit/7a47134a6b8726c0389d8e631028af8f8be54cc2))

### Continuous Integration

- Fixed python-semantic-release version to 7.*
  ([`1c66d5a`](https://github.com/bec-project/ophyd_devices/commit/1c66d5a2c872044a27d4e9eac176ea01a897fd17))


## v0.2.0 (2023-07-04)

### Bug Fixes

- Bec_lib.core import
  ([`25c7ce0`](https://github.com/bec-project/ophyd_devices/commit/25c7ce04e3c2a5c2730ce5aa079f37081d7289cd))

- Fixed galil sgalil_ophyd confusion from former commit
  ([`f488f0b`](https://github.com/bec-project/ophyd_devices/commit/f488f0b21cbe5addd6bd5c4c54aa00eeffde0648))

- Formatting DDG
  ([`4e10a96`](https://github.com/bec-project/ophyd_devices/commit/4e10a969c8625bc48d6db99fc7f5be9d46807df1))

- Recover galil_ophyd from master
  ([`5f655ca`](https://github.com/bec-project/ophyd_devices/commit/5f655caf29fe9941ba597fdaee6c4b2a20625ca8))

### Build System

- Added missing dependencies
  ([`e226dbe`](https://github.com/bec-project/ophyd_devices/commit/e226dbe3c3164664d36a385ec60266a867ac25d6))

### Documentation

- Improved readme
  ([`781affa`](https://github.com/bec-project/ophyd_devices/commit/781affacb5bc0c204cb7501b629027e66e47a0b1))

### Features

- Add DDG and prel. sgalil devices
  ([`00c5501`](https://github.com/bec-project/ophyd_devices/commit/00c55016e789f184ddb5c2474eb251fd62470e04))


## v0.1.0 (2023-06-28)

### Bug Fixes

- Added default_sub
  ([`9b9d3c4`](https://github.com/bec-project/ophyd_devices/commit/9b9d3c4d7fc629c42f71b527d86b6be0bf4524bc))

- Added missing file
  ([`5a7f8ac`](https://github.com/bec-project/ophyd_devices/commit/5a7f8ac40781f5ccf48b6ca94a569665592dc15b))

- Adjustments for new bec_lib
  ([`eee8856`](https://github.com/bec-project/ophyd_devices/commit/eee88565655eaab62ec66f018dcbe02d09594716))

- Fixed bpm4i for subs
  ([`4c6b7f8`](https://github.com/bec-project/ophyd_devices/commit/4c6b7f87219dbf8f369df9a65e4e8cec278d0568))

- Fixed epics import
  ([`ec3a93f`](https://github.com/bec-project/ophyd_devices/commit/ec3a93f96e3e07e5ac88d40fe1858915f667e64c))

- Fixed gitignore file
  ([`598d72b`](https://github.com/bec-project/ophyd_devices/commit/598d72b4ec9e9b1c5b100321d93370bf4b9ed426))

- Fixed harmonic signal
  ([`60c7878`](https://github.com/bec-project/ophyd_devices/commit/60c7878dad4839531b6e055eb1be94d696c6e2a7))

- Fixed pv name for sample manipulator
  ([`41929a5`](https://github.com/bec-project/ophyd_devices/commit/41929a59ab26b7502bef38f4d72c846d136bab03))

- Fixed rt_lamni for new hinted flyers
  ([`419ce9d`](https://github.com/bec-project/ophyd_devices/commit/419ce9dfdaf3ebdb30a2ece25f37a8ebe1a53572))

- Fixed rt_lamni hints
  ([`2610542`](https://github.com/bec-project/ophyd_devices/commit/26105421247cf5ea2b145e51525db8326b02852e))

- Fixed timestamp update for bpm4i
  ([`dacfd1c`](https://github.com/bec-project/ophyd_devices/commit/dacfd1c39b7966993080774c6154f856070c8b27))

- Fixed x07ma devices
  ([`959789b`](https://github.com/bec-project/ophyd_devices/commit/959789b26f21f1375d36db91dc6d5f9ac32a677d))

- Formatter
  ([`9e938f3`](https://github.com/bec-project/ophyd_devices/commit/9e938f3745106fb62e176d344aee6ee5c1fffa90))

- Minor adjustments to comply with the openapi schema; set default onFailure to retry
  ([`cdb3fef`](https://github.com/bec-project/ophyd_devices/commit/cdb3feff6013516e52d77b958f4c39296edee7bf))

- Moved to hint structure for flyers
  ([`fc17741`](https://github.com/bec-project/ophyd_devices/commit/fc17741d2ac46632e3adb96814d2c41e8000dcc6))

- Moved to new bec_client_lib structure
  ([`35d5ec8`](https://github.com/bec-project/ophyd_devices/commit/35d5ec8e9d94c0a845b852b6cd8182897464fca8))

- Online bug fixes
  ([`bf5f981`](https://github.com/bec-project/ophyd_devices/commit/bf5f981f52f063df687042567b8bc6e40cdb1d85))

- Online fixes
  ([`1395044`](https://github.com/bec-project/ophyd_devices/commit/1395044432dbf9235adce0fd5d46c019ea5db2db))

- Removed matplotlib dependency
  ([`b5611d2`](https://github.com/bec-project/ophyd_devices/commit/b5611d20c81cfa07f7451aaed2b9146e8bbca960))

### Continuous Integration

- Added additional tests for other python versions
  ([`d92c7ca`](https://github.com/bec-project/ophyd_devices/commit/d92c7cadcc4764e35b23a8ed4fe93a21ef9f9ae2))

- Added semver
  ([`9c0bd1e`](https://github.com/bec-project/ophyd_devices/commit/9c0bd1e1946eed2b14146c690b3e63825bcc77fe))

- Added semver
  ([`daa5d9e`](https://github.com/bec-project/ophyd_devices/commit/daa5d9e822eaec6afb5817348db65d9a2ac1ead9))

- Cleanup
  ([`56e5d5d`](https://github.com/bec-project/ophyd_devices/commit/56e5d5d61e8dbf5d6e7a7ce60c91c8449ab631f8))

- Fixed typo
  ([`2b0ee22`](https://github.com/bec-project/ophyd_devices/commit/2b0ee223bb4ed50036554875862f0f166cce1eb9))

- Moved to morgana harbor
  ([`77845a4`](https://github.com/bec-project/ophyd_devices/commit/77845a4042bb9fcc138f5bf8f0cb028aaaa3dad9))

### Features

- Added dev install to setup.py
  ([`412a0e4`](https://github.com/bec-project/ophyd_devices/commit/412a0e4480a0a5e7d2921cef529ef8aceda90bb7))

- Added missing epics devices for xtreme
  ([`2bf57ed`](https://github.com/bec-project/ophyd_devices/commit/2bf57ed43331ae138e211f14ece8cfd9a1b79046))

- Added nested object
  ([`059977d`](https://github.com/bec-project/ophyd_devices/commit/059977db1f160c8a21dccf845967dc265d34aa6a))

- Added otf sim
  ([`f351320`](https://github.com/bec-project/ophyd_devices/commit/f3513207d92e077a8a5e919952c3682250e5afa1))

- Added pylintrc
  ([`020459e`](https://github.com/bec-project/ophyd_devices/commit/020459ed902ab226d1cea659f6626d7a887cb99a))

- Added sls detector
  ([`63ece90`](https://github.com/bec-project/ophyd_devices/commit/63ece902a387c2c4a5944eb766f6a94e58b48755))

- Added test functions for rpc calls
  ([`5648ea2`](https://github.com/bec-project/ophyd_devices/commit/5648ea2d15c1994b34353fe51e83bf5d7a634520))

### Refactoring

- Cleanup
  ([`0ae9367`](https://github.com/bec-project/ophyd_devices/commit/0ae93670142947d25ea1a88cbd9eed4c542b4139))

- Cleanup
  ([`7bd602c`](https://github.com/bec-project/ophyd_devices/commit/7bd602c49c2a87ae465c5421b46438448f10305c))

- Fixed black formatting
  ([`db32219`](https://github.com/bec-project/ophyd_devices/commit/db32219bd34a64052703408f335f1725aeab0868))

- Formatter
  ([`f2d2a0a`](https://github.com/bec-project/ophyd_devices/commit/f2d2a0ab4569985972ac1010cdd00b61f54ed34a))

- Formatting
  ([`872d845`](https://github.com/bec-project/ophyd_devices/commit/872d845516abfef6face42fdcb30c102cd43d993))

- Prep for semver
  ([`428a13c`](https://github.com/bec-project/ophyd_devices/commit/428a13ceeb65fe32e2c2028e11cdebf6cf489331))

- Prep for semver
  ([`c5931a4`](https://github.com/bec-project/ophyd_devices/commit/c5931a4010d49fc3770311433f111f2ae7cc94c2))
