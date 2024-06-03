# CHANGELOG



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

### Ci

* ci: fixed dependency for bec ([`6630740`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/663074055977ca0a046a81bd9ba5187acf95afed))

* ci: added ci token to update job ([`180891b`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/180891becdc1aa16da0c3b83c407e82a288d36d1))

* ci: added device-list-update job ([`3405e2a`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/3405e2acf59cea33b025d376291ccda96db9ea07))

### Documentation

* docs: Update device list ([`d4f2ead`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/d4f2ead61b9eb4defb43d7e966a1ed5206461abd))

* docs: Update device list ([`2f575d3`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/2f575d3aa221e646166bfeb0470de1847358acca))

* docs: Update device list ([`b5adc09`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/b5adc097674068a90783a2ce4a093150d21cb736))

### Fix

* fix: pep8 compliant naming #64 ([`d705958`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/d7059589c84bacb560f738f4e4ae4aaf811b25d9))


## v1.0.1 (2024-05-15)

### Ci

* ci: fixed bec_widgets env var ([`e900a4c`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/e900a4cb47c5ecaae8eca30d106771034dc9296d))

* ci: fixed bec core dependency ([`8158e14`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/8158e145fe2358a736a2fb9d2d3de7e6c8db021c))

* ci: added echo to highlight the current branch ([`68b593f`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/68b593f20d73c6463d5e97ddf7dcf94a5b036b06))

### Fix

* fix: bec_lib imports ([`3d8b023`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/3d8b0231a3359db9a5430e49912147c049dbfab9))


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

### Documentation

* docs: improved doc strings for controllerr ([`339f050`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/339f050a8662de86ed2528ad4ffed18482dd546b))

### Fix

* fix: fixed controller error classes ([`c3fa7ad`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/c3fa7ad30d1b9a151bce599b34b4a3f82e4e6ce8))

### Refactor

* refactor: added common controller methods ([`00b3ae8`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/00b3ae82580df6bbe8a01a52d37c43199cf761bd))

### Unknown

* Update file .gitlab-ci.yml ([`2f8772b`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/2f8772b618836fc4029691ad03f7dafee17f1ca5))

* Update file .gitlab-ci.yml ([`bd01f60`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/bd01f6050a6c4957e4943577dff1ff53a5179f8b))
