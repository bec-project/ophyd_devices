# CHANGELOG



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

* ci: fixed twine upload if version did not change ([`d7646e8`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/d7646e835ff5d2c8ea749f3b4e24121d992c1454))

* ci: fixed changelog file ([`deded6f`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/deded6ffaca10369fb1e6cf2629f67ded3ab44b5))

### Fix

* fix: fixed bec_server import ([`434fa36`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/434fa36ca43f8dacd9c4f8fdd7556d77bd0a4b03))

### Refactor

* refactor(device_config): removed outdated config file ([`80a964f`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/80a964fae7203cbfb642980e3f89ed35ad6ff0da))

* refactor(device_config): fixed device schema ([`0f3665c`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/0f3665c32fec2f0f95cc57af81d448eca6978919))

* refactor(device_config): upgraded device configs; closes #56 ([`65c72c9`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/65c72c924847644f80fac768ed35e995a6999404))

### Style

* style: moved isort config to pyproject.toml ([`98d61b1`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/98d61b13e42ec294c2be059029e33021ba6ef3a0))

* style: moved black config to pyproject.toml ([`769a45d`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/769a45d7ff97f5d3bc5de5aa63bd2230654ea9d4))

* style: moved pylint to pyproject.toml ([`fcfe024`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/fcfe0242326c61be9251bd98cf9cf29de499facd))


## v0.30.4 (2024-04-12)

### Ci

* ci: fixed upload of release ([`3c37da8`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/3c37da8f515b2effea0950e3236bb9843b7b7b95))

### Fix

* fix: fixed release upload ([`361dc3a`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/361dc3a182231b458e1893da2e6382b1b17e9d5a))

* fix: upgraded pyproject.toml ([`9d67ace`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/9d67ace30d606caa2aaa919fe8225208c4632c7e))


## v0.30.3 (2024-04-12)

### Build

* build: fixed build ([`88ff3bc`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/88ff3bc0cf3c21d87ba50c24e7d9e2352df751c9))

### Fix

* fix: fixed pyproject.toml ([`2793ca3`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/2793ca3eb0c278f6159b0c6d7fcb121b5c969e12))


## v0.30.2 (2024-04-12)

### Fix

* fix: fixed release update ([`3267514`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/3267514c2055f406277b16f13a13744846e3ba77))


## v0.30.1 (2024-04-12)

### Build

* build: upgraded to sem release 9 ([`0864c0c`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/0864c0c04972a2b12be5ad9d3a53fb1a18a8907d))

### Fix

* fix: fixed release upload ([`abc6aad`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/abc6aad167226fd01e02d51ae4739d4c4688e153))


## v0.30.0 (2024-04-12)

### Build

* build: added black to pyproject ([`eb21600`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/eb2160000a19f89c000caf25a69a79e8249e5bf2))

* build: moved to pyproject.toml ([`6ba2428`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/6ba2428dd8e297c3c2098f9a795bb76595a4f5e7))

### Ci

* ci: updated default BEC branch ([`f287efc`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/f287efc831069d7c09de876ed1bf4dff4bd5908e))

### Feature

* feat: add SimWaveform for 1D waveform simulations ([`bf73bf4`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/bf73bf41c4f209ed251bf21d4b0014d031226a4f))

### Refactor

* refactor(sim): added logger statement to flyer ([`6c45dd6`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/6c45dd6a8b8c76776351289c98990dbc05222f5f))

* refactor: renamed pointID to point_id ([`b746278`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/b74627820a5594dc896b059399703baa4917097a))

### Style

* style(black): skip magic trailing comma ([`b1f3531`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/b1f353139b1ecdcfc266219a7a1a4bf525684bea))

### Unknown

* flomni/check_tracker_signal ([`9c09274`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/9c092740b9b38eac7f1046ae07e0667f91983c87))


## v0.29.2 (2024-04-08)

### Fix

* fix: Adapt to FileWriter refactoring ([`e9c626a`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/e9c626a7c8e5ec1b40d70ad412eff85d7796cba9))
