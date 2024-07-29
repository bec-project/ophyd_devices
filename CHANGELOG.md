# CHANGELOG

## v1.7.2 (2024-07-29)

### Build

* build(ci): update variable for ophyd_devices branch ([`1d55214`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/1d55214fbd25a111f8a81d804fd7f39470934c74))

### Ci

* ci: made BEC a child pipeline ([`9eb67a0`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/9eb67a0900159248e785b17e4250ae6a7e954348))

* ci: moved to awi utils trigger pipelines ([`0f6494a`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/0f6494ae2caafc0727a394683718031670614aeb))

* ci: changed default branch ([`fe5f1c3`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/fe5f1c314f51cb07bae4044a406ed5dc738c7837))

* ci: fixed default branch for ophyd ci var ([`85630f3`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/85630f3d733897945ef3421b9805e66191edb537))

### Fix

* fix: add write_access attribute to simulated readonly signal ([`c3e17ba`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/c3e17ba05632309adcc896f858e52ecb07048a30))

* fix: remove print for select_model method of sim module ([`5009316`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/5009316a82897d739b2a26eb341e9f5a1e083e51))

* fix: Improve asyn_monitor and camera on_trigger and on_complete to return status ([`f311876`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/f3118765b0efc38dd12a3d72d290e517490f9fbf))

### Refactor

* refactor: review DeviceStatus and error handling in simulation ([`87858ed`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/87858edfe290cb711bc30c2f3ba2653460d15af6))

* refactor: rename monitor to device_monitor_2d ([`6a6b907`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/6a6b907022532e20626b8ed97d347da04beea4b0))

### Test

* test: Fix and add test scenarios for DeviceStatus error handling ([`4397db9`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/4397db919a852d70c53d80a532540eaabdffc3ad))

* test: adapt tests to consider returned DeviceStatus for on_trigger/complete ([`f8e9aaf`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/f8e9aaf55a5734f3bf557bbf5e51eb7ea41257d4))

### Unknown

* wip ([`35141e9`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/35141e94b1c8a6ba70e96b915b45871d19bd5f7e))

## v1.7.1 (2024-07-24)

### Fix

* fix: add run._subs SUB_VALUE to settable signal put method ([`ca6d96e`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/ca6d96e25b4a2d5011c0882e512b84e16cf7b264))

## v1.7.0 (2024-07-10)

### Feature

* feat: add SimLinearTrajectoryPositioner to better motion simulation ([`b5918c4`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/b5918c424de005d1510afedc05b0e217fd09616e))

### Fix

* fix: _update_state() does not raise an exception if stopped ([`207b9b5`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/207b9b571c6df1c2de75b187e794d2dcd7bd0108))

### Refactor

* refactor: make it easier to subclass SimPositioner ([`9037553`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/903755325230b2c93eba219dd0e4d2aadd05d16f))

### Test

* test: add test for SimLinearTrajectoryPositioner ([`ba7db78`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/ba7db7819439c89c3f160acaf399b1ffd538ac7f))

## v1.6.1 (2024-07-05)

### Fix

* fix(softpositioner): fixed input args for softpositioner ([`e80811c`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/e80811c19736cd70be2dbcfac0bcedfe975bf419))

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
