# CHANGELOG



## v1.0.0 (2024-05-08)

### Breaking

* refactor!: moved to new ophyd_devices repo structure

BREAKING CHANGE: cleaned up and migrated to the new repo structure. Only shared devices will be hosted in ophyd_devices. Everything else will be in the beamline-specific repositories ([`3415ae2`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/3415ae2007cc447835906271de23e5f7a41ba373))

### Ci

* ci: fix dep and add CI JOB for package dep checks ([`d89f8b8`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/d89f8b87568d30d467279d96b0100cd318e2b5a2))

* ci: added trigger for xtreme-bec ([`be689ba`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/be689baa29d54632bbac9b523f0fe3a66e061f84))


## v0.33.6 (2024-05-08)

### Ci

* ci: made pipeline interruptible ([`44de499`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/44de499d40db01e2d9ad0ae50235240e2103bf02))

* ci: added downstream pipelines ([`b8134ed`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/b8134edbff58e1f92c45c3ab9b41f88e1ad3069b))

* ci: added support for different branches in child pipelines ([`c74cbe3`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/c74cbe358cf24943e1badc32ef53ced1f8d149f1))

* ci: fixed typo ([`81f1fee`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/81f1feea853882e8d557063612cc0acc601bbe2a))

* ci: fixed rules for downstream pipelines ([`f5e69f9`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/f5e69f9b9528871d9a011b2257b87c1faf89e6b0))

* ci: limit stages to run in child pipelines ([`815921a`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/815921a6c9cd97e5df94a584c5d4c2c22a4d408a))

* ci: removed awi-utils for now ([`27d4b6a`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/27d4b6ae83ec3d0f4d7a85c3cd4f6f70ecd528eb))

* ci: added parent-child pipelines ([`e27d2db`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/e27d2db4ac21830c95f2db2ccba58c650c25cad5))

### Documentation

* docs: improved doc strings for controllerr ([`339f050`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/339f050a8662de86ed2528ad4ffed18482dd546b))

### Fix

* fix: fixed controller error classes ([`c3fa7ad`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/c3fa7ad30d1b9a151bce599b34b4a3f82e4e6ce8))

### Refactor

* refactor: added common controller methods ([`00b3ae8`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/00b3ae82580df6bbe8a01a52d37c43199cf761bd))

### Unknown

* Update file .gitlab-ci.yml ([`2f8772b`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/2f8772b618836fc4029691ad03f7dafee17f1ca5))

* Update file .gitlab-ci.yml ([`bd01f60`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/bd01f6050a6c4957e4943577dff1ff53a5179f8b))


## v0.33.5 (2024-05-02)

### Fix

* fix: fixed device data signature ([`e8290db`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/e8290dbf4466f1415fb9c963ae203a4e6da7cc42))


## v0.33.4 (2024-04-29)

### Ci

* ci: removed redundant build step ([`a919632`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/a9196328e7d7efe4b6718b22d72c6df9bf59411c))

* ci(gitlab-ci): trigger gitlab job template from awi_utils ([`4ffeba4`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/4ffeba4c3b890b2fcd8c694347a254b3bc1e3c96))

### Fix

* fix: static device test should use yaml_load ([`c77f924`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/c77f924bb3665ab0896bc56076d05331e8b01f55))


## v0.33.3 (2024-04-24)

### Ci

* ci: removed allow_failure from config check ([`d34b396`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/d34b39669c4faf2d1c5518a632239303a48c2fd6))

### Fix

* fix: updated device configs to new import schema ([`5725fc3`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/5725fc36c7aff052fc704782a99bd04cfb13c112))


## v0.33.2 (2024-04-22)

### Fix

* fix(pyproject.toml): add bec-server to dev dependencies; closes #62 ([`9353b46`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/9353b46be804de967810f0d9370d230dfae5c92b))


## v0.33.1 (2024-04-20)

### Fix

* fix: fix pyproject.toml ([`6081eb4`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/6081eb4ba54b2a6a2072f638af06c6f1cf264b69))


## v0.33.0 (2024-04-19)

### Feature

* feat: move csaxs devices to plugin structure, fix imports and tests ([`74f6fa7`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/74f6fa7ffdf339399504e15f27564e3f0e43db56))


## v0.32.0 (2024-04-19)

### Ci

* ci: do not wait for additional tests to start ([`b88545f`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/b88545f6864a7d11ca39435906bcbd2cd0bb12b0))

### Feature

* feat: added support for nestes device configs ([`288f394`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/288f39483e83575d0bf3ec7a8e0d872b41b5b183))


## v0.31.0 (2024-04-19)

### Build

* build: fixed dependencies to compatible releases ([`26c04b5`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/26c04b5d03683b0159d5af127f19cda664bfb292))

### Ci

* ci: cleanup; added static device test job ([`ed66eac`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/ed66eacc5310e878deb35be69f335f1b8eb10950))

* ci: added pipeline as trigger source ([`e59def1`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/e59def138fb465abf7a33d13e47e78ac382feebf))

* ci: changed master to main ([`701be52`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/701be5262ad402ff6e6a665db4bd1d5b30b3abac))

* ci: pull images via gitlab dependency proxy ([`8d68e7d`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/8d68e7df70e54984e460f50cee5356a7ada4e761))

* ci: remove AdditionalTests dependency on pytest job ([`4ee86ab`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/4ee86aba371698820ea16ff94ae6946cd0041fe4))

### Feature

* feat: added support for directories as input for the static device test ([`9748ca6`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/9748ca666c3c8668e8ced80e7d24eeaf7f19c28e))


## v0.30.5 (2024-04-12)

### Ci

* ci: fixed bec install ([`a954640`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/a9546402f5b2f1a43e1c4e17f977c544c326e5dc))

### Fix

* fix: fixed bec_server import ([`434fa36`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/434fa36ca43f8dacd9c4f8fdd7556d77bd0a4b03))

### Refactor

* refactor(device_config): removed outdated config file ([`80a964f`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/80a964fae7203cbfb642980e3f89ed35ad6ff0da))

* refactor(device_config): fixed device schema ([`0f3665c`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/0f3665c32fec2f0f95cc57af81d448eca6978919))

* refactor(device_config): upgraded device configs; closes #56 ([`65c72c9`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/65c72c924847644f80fac768ed35e995a6999404))
