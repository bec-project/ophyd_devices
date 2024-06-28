# CHANGELOG

## v1.5.1 (2024-06-28)

### Documentation

* docs: Update device list ([`f818ff0`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/f818ff0234edb75840ab7ba60b66d0aa47d1d520))

* docs: Update device list ([`ac5e794`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/ac5e79425ddf5b52350e45d392e2e6f048b5856a))

* docs: Update device list ([`cc6773e`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/cc6773e14e1c758ec3296c41e969731e8ce4cfe4))

* docs: Update device list ([`2ad4a70`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/2ad4a70971e73ed8d38d0e3ed54f18053e79048b))

### Fix

* fix: update timestamp upon reading of non computed readback signal ([`17e8cd9`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/17e8cd9234727e1bdc3d2a2ba2c47a9c8ec43c32))

## v1.5.0 (2024-06-19)

### Feature

* feat: add option to return DeviceStatus for on_trigger, on_complete; extend wait_for_signals ([`2c7c48a`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/2c7c48a7576cca90cc7be0d22b5a86c416f49fa9))

## v1.4.0 (2024-06-17)

### Documentation

* docs: Update device list ([`22a6970`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/22a69705865ee137f76c207807240562d4609560))

### Feature

* feat(config): added epics example config ([`a10e5bc`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/a10e5bcadcbd3e8bfbc061abd247d0655534095d))

## v1.3.5 (2024-06-14)

### Fix

* fix: fixed pyepics version for now as it segfaults on startup ([`f1a2368`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/f1a2368101e6b4af2d08d1a3540680f7f3ff9762))

## v1.3.4 (2024-06-07)

### Fix

* fix: remove inheritance from ophyd.PostionerBase for simflyer ([`c9247ef`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/c9247ef82ee32aeb50474979d414b98d67a2b840))

## v1.3.3 (2024-06-06)

### Fix

* fix: make done and successful mandatory args. ([`79b821a`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/79b821ae7e38b78e35ab5165db590cb7123afbf4))

* fix: make filepath a signal ([`e9aaa03`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/e9aaa0383e4120a09b6aa40b7e33fb53f31cb9a3))

## v1.3.2 (2024-06-04)

### Documentation

* docs: Update device list ([`c1e977f`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/c1e977f639633167fe4e7dfb5f34b066c26933d0))

* docs: Update device list ([`92be39f`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/92be39f14fac756749631e64113d24f732bb5551))

### Fix

* fix: adapt SimPositioner, make tolerance changeable signal ([`3606a2f`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/3606a2fc5ad74ec949d388cc23fbd6618d1f3083))

## v1.3.1 (2024-06-03)

### Documentation

* docs: Update device list ([`33f5d8a`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/33f5d8a6291e4ddfd905d83ff5c9384d648a632d))

* docs: Update device list ([`6f29a79`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/6f29a797965187ed0a608d0bb07eaa25f414440e))

### Fix

* fix: bugfix to fill data butter with value, timestamp properly ([`8520800`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/85208002a305fa657c469ff98b45174eb2c1f29a))

## v1.3.0 (2024-06-03)

### Documentation

* docs: Update device list ([`f9b126c`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/f9b126c60ce710fba221ffb208d66541b8264c0b))

* docs: Update device list ([`be25cba`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/be25cbae92540b074bb4533331656d20a049a809))

### Feature

* feat: add async monitor, add on_complete to psi_det_base and rm duplicated mocks, closes #67 ([`1aece61`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/1aece61a3b09267f87f0771b163a5d07b4549eff))

### Refactor

* refactor: add .wait() to set methods ([`7334925`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/73349257ee0228a9563051d4f8e0bf5f7e6b551f))

* refactor: removed deprecated devices ([`8ef6d10`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/8ef6d10eb759e6ce874ddf05a38c586e9475eed3))

### Test

* test: add tests for new device ([`c554422`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/c5544226be3f12d238a0793a0f41da07af36e460))

## v1.2.1 (2024-05-29)

### Documentation

* docs: Update device list ([`5a591ce`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/5a591ce024b7815a432460fe9e8d97e648dcdb5e))

* docs: Update device list ([`ae0c766`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/ae0c766975cdfc69ffe9d48eca92ad8d51a0497c))

### Fix

* fix: fixed psi_detector_base to allow init with mocked device_manager ([`e566c7f`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/e566c7f982ee519a5ec3e350cef349c3238eebae))

## v1.2.0 (2024-05-29)

### Ci

* ci: fix bec_core_branch triggering in ci file ([`3cab569`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/3cab5690db3fbabffecc179cbaadf6878f0ab2f1))

### Documentation

* docs: Update device list ([`08dfc9e`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/08dfc9e314a1b498ec2fc1f9056234fe732d6428))

* docs: Update device list ([`106233f`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/106233f8d951794e261b08a11b20db6cbf4ef63a))

* docs: Update device list ([`9c93916`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/9c9391610845bc1b21e342e7c3b34b8db978a038))

* docs: Update device list ([`018fdac`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/018fdaced4120557ea64501c107c027e362c93fb))

### Feature

* feat: add option to save Camera data to disk, closes #66 ([`60b2e75`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/60b2e756550196fb5c07bb91abb4c1ae5b815c6c))

### Test

* test: add tests ([`af908fa`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/af908fa210914519de9a713ed2ef3e2e0c743742))

## v1.1.0 (2024-05-27)

### Feature

* feat: refactor psi_detector_base class, add tests ([`a0ac8c9`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/a0ac8c9ad701f52429f393a134fd0705583eddb1))

### Refactor

* refactor: add publish file location to base class ([`e8510fb`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/e8510fb249b136781c03849497d85dfb11cca43a))

## v1.0.2 (2024-05-23)

### Documentation

* docs: Update device list ([`d4f2ead`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/d4f2ead61b9eb4defb43d7e966a1ed5206461abd))

* docs: Update device list ([`2f575d3`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/2f575d3aa221e646166bfeb0470de1847358acca))
