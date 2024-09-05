# CHANGELOG

## v1.9.2 (2024-09-05)

### Ci

* ci: prefill variables for manual pipeline start ([`3f2c6dc`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/3f2c6dc4efddfa06bebff13ac2984e45efd13a90))

### Fix

* fix: change inheritance for simmonitor from device to signal ([`a675420`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/a6754208a0991f8ccf546cbb2bee015f6daecb93))

* fix: fix inheritance for SimMonitor ([`f56961b`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/f56961ba8c179d4ca75e574fd8565ae4c3f41eed))

### Refactor

* refactor: bodge to make simmonitor compatible with tests; to be removed asap ([`9d9a5fe`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/9d9a5fe305981f845c87e3417dd1072d2b8692b0))

## v1.9.1 (2024-08-28)

### Fix

* fix: removed arguments for callback call ([`d83c102`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/d83c102d14430b9acd8525d1d61e6e092d9f6043))

### Refactor

* refactor: moved sim test devices to sim_test_devices ([`a49c6f6`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/a49c6f6a625a576524fceca62dd0a1582a4a4a7d))

## v1.9.0 (2024-08-28)

### Feature

* feat: add dual patch pvs to ophyd_devices ([`c47918d`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/c47918d6e7ff41721aa4fa67043ff6cd1aeee2c7))

## v1.8.1 (2024-08-15)

### Build

* build: moved pyepics deps to &gt;=3.5.5

3.5.3 and 3.5.4 should not be used ([`8046f22`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/8046f22a807f94f1dc7d9ab77ab3b9c3ce821633))

### Fix

* fix: fixed import of simpositioner test devices ([`f1f9721`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/f1f9721fe9c71da747558e4bb005c04592aa2bde))

## v1.8.0 (2024-08-14)

### Feature

* feat(sim): added dedicated positioner with controller ([`4ad5723`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/4ad57230e327c3714a03ae138bc12a5028acb1dd))

## v1.7.3 (2024-08-08)

### Fix

* fix: small bugfix to ensure motor_is_moving updates at the end of a move ([`577b35f`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/577b35f287ec997a41ce27fae2db9bbc669a2d9d))

### Test

* test: add test case ([`76e1cfc`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/76e1cfc4aade9c691d9b5bfd4db0b678b7e2f1cc))

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

### Unknown

* remove unused imports ([`755ee20`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/755ee207c5f9816d2270b6f57f6973ddf525238d))
