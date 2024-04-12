# CHANGELOG



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

### Unknown

* Update .gitlab-ci.yml file ([`32b6d47`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/32b6d476ca4b0deb0eec75519618c005212cc2dd))


## v0.29.1 (2024-04-06)

### Ci

* ci: added isort to pre-commit and ci ([`36d5cef`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/36d5cef4ef14e5566649834b3afdd1efdbfdfc2d))

### Fix

* fix(utils): fixed scan status message in sim mode ([`c87f6ef`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/c87f6ef63f669d6d1288e3521b80b3e0065bf2f4))

### Refactor

* refactor: applied isort to tomcat rotation motors ([`fd1f8c0`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/fd1f8c0ff58c630051cb67d404c6dd07f3403c5b))

* refactor: fixed formatter ([`1e03114`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/1e031140ed0ae4347a8d16a6a5e8647b48573d96))

* refactor: applied isort to repo ([`284c6c4`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/284c6c47a1db25d7ed840404730b1e97da960c14))

### Unknown

* added fourth channel to signal strength readout ([`321bf0c`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/321bf0c403a77efcbf970ea377b53a59377e38d0))


## v0.29.0 (2024-03-28)

### Feature

* feat: add protocols and rotation base device ([`ddd0b79`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/ddd0b790f8ef3e53966c660c431d2f7a9ceda97c))

### Refactor

* refactor: add set for positioner protocol ([`d844168`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/d844168c1f7f31543ff747bb6f2ef3a2f7f1077e))

* refactor: move protocol and base classes to different directory ([`8b77df8`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/8b77df833f4d389293d14f8e3e54de7b38c9f291))

* refactor: cleanup aerotech, fix packaging for release ([`ce43924`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/ce43924ca1601c409a17855957af6847b75ff261))

### Test

* test: fix tests after merge conflict ([`5f5ec72`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/5f5ec72d02c2cb217ab540e82014d90fe5ef8216))

* test: add test for simulated devices and BECprotocols ([`b34817a`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/b34817acf8ef6e60ef493bc2bb830a3a254e7ced))

* test: add tests for proxies ([`2c43559`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/2c43559aa8e60950ff95e72772820d784aacaa62))


## v0.28.0 (2024-03-26)

### Feature

* feat(ophyd): temporary until new Ophyd release, prevent Status objects threads

Monkey-patching of Ophyd library ([`df8ce79`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/df8ce79ca0606ad415f45cfd5d80b057aec107d9))


## v0.27.4 (2024-03-26)

### Ci

* ci: added BEC_CORE_BRANCH var name to .gitlab-ci.yml ([`d3a26ff`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/d3a26ff3b2d2612128d0da4bd4fcc698b314ae9a))

### Fix

* fix: fix CI pipeline for py 3.10 and 3.11 ([`391c889`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/391c889ff17d9b97388d01731ed88251b41d6ecd))

### Refactor

* refactor: renamed queueID to queue_id ([`5fca3ec`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/5fca3ec1292ba423d575ed106a636a3c8613a99d))

* refactor: renamed scanID to scan_id ([`1c7737c`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/1c7737ccda71a18c0a9c09f38c8c543834dfe833))

### Unknown

* small fixes ([`46063b9`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/46063b905bb003f175d4edf7054afa9c556fb4db))


## v0.27.3 (2024-03-21)

### Fix

* fix: remove missplaced readme from aerotech ([`ad96b72`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/ad96b729b47318007d403f7024524379f5a32a84))

### Test

* test: added simpositioner with failure signal ([`4ea98b1`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/4ea98b18c3280c077a08325081f5743a737760a9))


## v0.27.2 (2024-03-15)

### Fix

* fix: bug fixes from online test at microxas ([`c2201e5`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/c2201e5e332c9bab64f6fcdfe034cb8d37da5857))

* fix: add numpy and scipy to dynamic_pseudo ([`b66b224`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/b66b224caeab9e3cf75de61fcfdccd0712fb9027))

### Refactor

* refactor: numpy as np ([`d9ad1e8`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/d9ad1e87f7e6e2a5da6c3ea9b59952ca319c50ae))

### Test

* test: fix tests ([`2f2e519`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/2f2e51977265006f7fbb9a97648824dfb6f8b5b3))

### Unknown

* wip: fixed import for scipy too ([`46bbdfa`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/46bbdfaebb14e86f866ebd5dc89e3b715249b5b3))


## v0.27.1 (2024-03-13)

### Fix

* fix: bug fix ([`6c776bb`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/6c776bb4ae72e7f0a4b858a27a34f25baed726d2))
