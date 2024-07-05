# CHANGELOG

## v1.6.0 (2024-07-05)

### Feature

* feat(devices): added softpositioner ([`e803829`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/e803829f6c2bab1724a2f30eb0633fd52033ffe7))

## v1.5.4 (2024-07-05)

### Fix

* fix(sim): fixed sim positioner moving state update ([`8efa93a`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/8efa93a7023c939ce535f829a5e41468372ae78e))

## v1.5.3 (2024-07-03)

### Fix

* fix: device sim params can be set through init ([`f481c1f`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/f481c1f81298552067aea91fba54e90d61cd2dcb))

### Refactor

* refactor: ensure temporary backward compatibility after API changes ([`73c636b`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/73c636b46f35381ac0a82b99f9965612770ca6c1))

## v1.5.2 (2024-07-02)

### Fix

* fix: put noqa comment on hdf5plugin import, compress HDF5 test file to ensure it requires the module for reading

hd5plugin import has the side effect of installing LZ4 codec ([`55ea6a1`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/55ea6a16be831e375281f014c75f0146b1b9a488))

* fix: split simulation classes in multiple files ([`2622ddb`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/2622ddbee2edfe9e092c643fbbfbabeed0c06e35))

### Unknown

* remove unused imports ([`755ee20`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/755ee207c5f9816d2270b6f57f6973ddf525238d))

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

### Documentation

* docs: Update device list ([`08dfc9e`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/08dfc9e314a1b498ec2fc1f9056234fe732d6428))

* docs: Update device list ([`106233f`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/106233f8d951794e261b08a11b20db6cbf4ef63a))
