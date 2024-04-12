# CHANGELOG



## v0.30.4 (2024-04-12)

### Ci

* ci: fixed upload of release ([`3c37da8`](https://gitlab.com/bec/ophyd_devices/-/commit/3c37da8f515b2effea0950e3236bb9843b7b7b95))

### Fix

* fix: fixed release upload ([`361dc3a`](https://gitlab.com/bec/ophyd_devices/-/commit/361dc3a182231b458e1893da2e6382b1b17e9d5a))

* fix: upgraded pyproject.toml ([`9d67ace`](https://gitlab.com/bec/ophyd_devices/-/commit/9d67ace30d606caa2aaa919fe8225208c4632c7e))


## v0.30.3 (2024-04-12)

### Build

* build: fixed build ([`88ff3bc`](https://gitlab.com/bec/ophyd_devices/-/commit/88ff3bc0cf3c21d87ba50c24e7d9e2352df751c9))

### Fix

* fix: fixed pyproject.toml ([`2793ca3`](https://gitlab.com/bec/ophyd_devices/-/commit/2793ca3eb0c278f6159b0c6d7fcb121b5c969e12))


## v0.30.2 (2024-04-12)

### Fix

* fix: fixed release update ([`3267514`](https://gitlab.com/bec/ophyd_devices/-/commit/3267514c2055f406277b16f13a13744846e3ba77))


## v0.30.1 (2024-04-12)

### Build

* build: upgraded to sem release 9 ([`0864c0c`](https://gitlab.com/bec/ophyd_devices/-/commit/0864c0c04972a2b12be5ad9d3a53fb1a18a8907d))

### Fix

* fix: fixed release upload ([`abc6aad`](https://gitlab.com/bec/ophyd_devices/-/commit/abc6aad167226fd01e02d51ae4739d4c4688e153))


## v0.30.0 (2024-04-12)

### Build

* build: added black to pyproject ([`eb21600`](https://gitlab.com/bec/ophyd_devices/-/commit/eb2160000a19f89c000caf25a69a79e8249e5bf2))

* build: moved to pyproject.toml ([`6ba2428`](https://gitlab.com/bec/ophyd_devices/-/commit/6ba2428dd8e297c3c2098f9a795bb76595a4f5e7))

### Ci

* ci: updated default BEC branch ([`f287efc`](https://gitlab.com/bec/ophyd_devices/-/commit/f287efc831069d7c09de876ed1bf4dff4bd5908e))

### Feature

* feat: add SimWaveform for 1D waveform simulations ([`bf73bf4`](https://gitlab.com/bec/ophyd_devices/-/commit/bf73bf41c4f209ed251bf21d4b0014d031226a4f))

### Refactor

* refactor(sim): added logger statement to flyer ([`6c45dd6`](https://gitlab.com/bec/ophyd_devices/-/commit/6c45dd6a8b8c76776351289c98990dbc05222f5f))

* refactor: renamed pointID to point_id ([`b746278`](https://gitlab.com/bec/ophyd_devices/-/commit/b74627820a5594dc896b059399703baa4917097a))

### Style

* style(black): skip magic trailing comma ([`b1f3531`](https://gitlab.com/bec/ophyd_devices/-/commit/b1f353139b1ecdcfc266219a7a1a4bf525684bea))

### Unknown

* flomni/check_tracker_signal ([`9c09274`](https://gitlab.com/bec/ophyd_devices/-/commit/9c092740b9b38eac7f1046ae07e0667f91983c87))


## v0.29.2 (2024-04-08)

### Fix

* fix: Adapt to FileWriter refactoring ([`e9c626a`](https://gitlab.com/bec/ophyd_devices/-/commit/e9c626a7c8e5ec1b40d70ad412eff85d7796cba9))

### Unknown

* Update .gitlab-ci.yml file ([`32b6d47`](https://gitlab.com/bec/ophyd_devices/-/commit/32b6d476ca4b0deb0eec75519618c005212cc2dd))


## v0.29.1 (2024-04-06)

### Ci

* ci: added isort to pre-commit and ci ([`36d5cef`](https://gitlab.com/bec/ophyd_devices/-/commit/36d5cef4ef14e5566649834b3afdd1efdbfdfc2d))

### Fix

* fix(utils): fixed scan status message in sim mode ([`c87f6ef`](https://gitlab.com/bec/ophyd_devices/-/commit/c87f6ef63f669d6d1288e3521b80b3e0065bf2f4))

### Refactor

* refactor: applied isort to tomcat rotation motors ([`fd1f8c0`](https://gitlab.com/bec/ophyd_devices/-/commit/fd1f8c0ff58c630051cb67d404c6dd07f3403c5b))

* refactor: fixed formatter ([`1e03114`](https://gitlab.com/bec/ophyd_devices/-/commit/1e031140ed0ae4347a8d16a6a5e8647b48573d96))

* refactor: applied isort to repo ([`284c6c4`](https://gitlab.com/bec/ophyd_devices/-/commit/284c6c47a1db25d7ed840404730b1e97da960c14))

### Unknown

* added fourth channel to signal strength readout ([`321bf0c`](https://gitlab.com/bec/ophyd_devices/-/commit/321bf0c403a77efcbf970ea377b53a59377e38d0))


## v0.29.0 (2024-03-28)

### Feature

* feat: add protocols and rotation base device ([`ddd0b79`](https://gitlab.com/bec/ophyd_devices/-/commit/ddd0b790f8ef3e53966c660c431d2f7a9ceda97c))

### Refactor

* refactor: add set for positioner protocol ([`d844168`](https://gitlab.com/bec/ophyd_devices/-/commit/d844168c1f7f31543ff747bb6f2ef3a2f7f1077e))

* refactor: move protocol and base classes to different directory ([`8b77df8`](https://gitlab.com/bec/ophyd_devices/-/commit/8b77df833f4d389293d14f8e3e54de7b38c9f291))

* refactor: cleanup aerotech, fix packaging for release ([`ce43924`](https://gitlab.com/bec/ophyd_devices/-/commit/ce43924ca1601c409a17855957af6847b75ff261))

### Test

* test: fix tests after merge conflict ([`5f5ec72`](https://gitlab.com/bec/ophyd_devices/-/commit/5f5ec72d02c2cb217ab540e82014d90fe5ef8216))

* test: add test for simulated devices and BECprotocols ([`b34817a`](https://gitlab.com/bec/ophyd_devices/-/commit/b34817acf8ef6e60ef493bc2bb830a3a254e7ced))

* test: add tests for proxies ([`2c43559`](https://gitlab.com/bec/ophyd_devices/-/commit/2c43559aa8e60950ff95e72772820d784aacaa62))


## v0.28.0 (2024-03-26)

### Feature

* feat(ophyd): temporary until new Ophyd release, prevent Status objects threads

Monkey-patching of Ophyd library ([`df8ce79`](https://gitlab.com/bec/ophyd_devices/-/commit/df8ce79ca0606ad415f45cfd5d80b057aec107d9))


## v0.27.4 (2024-03-26)

### Ci

* ci: added BEC_CORE_BRANCH var name to .gitlab-ci.yml ([`d3a26ff`](https://gitlab.com/bec/ophyd_devices/-/commit/d3a26ff3b2d2612128d0da4bd4fcc698b314ae9a))

### Fix

* fix: fix CI pipeline for py 3.10 and 3.11 ([`391c889`](https://gitlab.com/bec/ophyd_devices/-/commit/391c889ff17d9b97388d01731ed88251b41d6ecd))

### Refactor

* refactor: renamed queueID to queue_id ([`5fca3ec`](https://gitlab.com/bec/ophyd_devices/-/commit/5fca3ec1292ba423d575ed106a636a3c8613a99d))

* refactor: renamed scanID to scan_id ([`1c7737c`](https://gitlab.com/bec/ophyd_devices/-/commit/1c7737ccda71a18c0a9c09f38c8c543834dfe833))

### Unknown

* small fixes ([`46063b9`](https://gitlab.com/bec/ophyd_devices/-/commit/46063b905bb003f175d4edf7054afa9c556fb4db))


## v0.27.3 (2024-03-21)

### Fix

* fix: remove missplaced readme from aerotech ([`ad96b72`](https://gitlab.com/bec/ophyd_devices/-/commit/ad96b729b47318007d403f7024524379f5a32a84))

### Test

* test: added simpositioner with failure signal ([`4ea98b1`](https://gitlab.com/bec/ophyd_devices/-/commit/4ea98b18c3280c077a08325081f5743a737760a9))


## v0.27.2 (2024-03-15)

### Fix

* fix: bug fixes from online test at microxas ([`c2201e5`](https://gitlab.com/bec/ophyd_devices/-/commit/c2201e5e332c9bab64f6fcdfe034cb8d37da5857))

* fix: add numpy and scipy to dynamic_pseudo ([`b66b224`](https://gitlab.com/bec/ophyd_devices/-/commit/b66b224caeab9e3cf75de61fcfdccd0712fb9027))

### Refactor

* refactor: numpy as np ([`d9ad1e8`](https://gitlab.com/bec/ophyd_devices/-/commit/d9ad1e87f7e6e2a5da6c3ea9b59952ca319c50ae))

### Test

* test: fix tests ([`2f2e519`](https://gitlab.com/bec/ophyd_devices/-/commit/2f2e51977265006f7fbb9a97648824dfb6f8b5b3))

### Unknown

* wip: fixed import for scipy too ([`46bbdfa`](https://gitlab.com/bec/ophyd_devices/-/commit/46bbdfaebb14e86f866ebd5dc89e3b715249b5b3))


## v0.27.1 (2024-03-13)

### Fix

* fix: bug fix ([`6c776bb`](https://gitlab.com/bec/ophyd_devices/-/commit/6c776bb4ae72e7f0a4b858a27a34f25baed726d2))


## v0.27.0 (2024-03-12)

### Feature

* feat: Moving the Automation1 device to BEC repo ([`853d621`](https://gitlab.com/bec/ophyd_devices/-/commit/853d621042e400c83940fdde50f1db66941f540b))

### Refactor

* refactor: fixed formatter for aerotech ([`573da8a`](https://gitlab.com/bec/ophyd_devices/-/commit/573da8a20b9be502b274b4c79e581b9e35a1e25d))

### Unknown

* Merge branch &#39;feature/device-aeroauto1&#39; of https://gitlab.psi.ch/bec/ophyd_devices into feature/device-aeroauto1 ([`75360a9`](https://gitlab.com/bec/ophyd_devices/-/commit/75360a9636740db76c6fc48dd84042669918a973))

* Update __init__.py ([`456983f`](https://gitlab.com/bec/ophyd_devices/-/commit/456983f334a387f26b927a8b0194d9cc449cf21a))

* Flaking ([`4b5a270`](https://gitlab.com/bec/ophyd_devices/-/commit/4b5a270071093e3889c028510b17350826453b7c))

* Update README.md ([`7baf9ec`](https://gitlab.com/bec/ophyd_devices/-/commit/7baf9ec118bb0713a02cf5a776f0b2f039a20c90))

* Update office_teststand_bec_config.yaml ([`ea2dc32`](https://gitlab.com/bec/ophyd_devices/-/commit/ea2dc32501e1db195c9c510a71a31010961a76d2))

* Basic examples ([`8be3937`](https://gitlab.com/bec/ophyd_devices/-/commit/8be3937ceca3e21fef00693aedd3d926bc5567cb))

* Moved aerotech to its own directory ([`6f8ae68`](https://gitlab.com/bec/ophyd_devices/-/commit/6f8ae68d0e6a9c994d6b270b3fe94356945e6049))

* Added simplified scripted sequence scan ([`034413f`](https://gitlab.com/bec/ophyd_devices/-/commit/034413f777629edf73e68016a0eb267361b38993))

* New complete with added IOC functionality ([`f2fed06`](https://gitlab.com/bec/ophyd_devices/-/commit/f2fed0639ee7ecd0c6a320a8bb9d51686e9b0fde))

* Added templated scan and required status updates ([`48d5939`](https://gitlab.com/bec/ophyd_devices/-/commit/48d59392aa9ac5f02b001695838772eef9e1e51d))

* Scans are still hanging... ([`4c71eb0`](https://gitlab.com/bec/ophyd_devices/-/commit/4c71eb0ca7425891a6338b154a0f2c0b26766f52))

* More cleanup with testing ([`fc10620`](https://gitlab.com/bec/ophyd_devices/-/commit/fc106200bec5b4950102c824919727a3c84ecf15))

* More cleanup with testing ([`6c279b7`](https://gitlab.com/bec/ophyd_devices/-/commit/6c279b717f1d64e4054371490478dc82588d320e))

* Extended motor class ([`204274f`](https://gitlab.com/bec/ophyd_devices/-/commit/204274ff8c10d6e57b7b5e2dd8f28be0093f06c1))

* Smaller fixes from cross testing ([`a7593bb`](https://gitlab.com/bec/ophyd_devices/-/commit/a7593bb90b5aa793fdc059ae56a79f0e1abf1cd5))

* Seuence scan via Ophyd works ([`9378d9f`](https://gitlab.com/bec/ophyd_devices/-/commit/9378d9f74cad4fb0d6cd70b2e0bc7beff1d2e7f4))

* Update __init__.py ([`65a0556`](https://gitlab.com/bec/ophyd_devices/-/commit/65a05562434c92a44227fb6d3ade051423f533e1))

* Flaking ([`1dda0e0`](https://gitlab.com/bec/ophyd_devices/-/commit/1dda0e04ba263fe541e33ea05108343064138e5f))

* Update README.md ([`1b328d3`](https://gitlab.com/bec/ophyd_devices/-/commit/1b328d31de0575aeb56ec58ef8e50aac878d537e))

* Update office_teststand_bec_config.yaml ([`172d735`](https://gitlab.com/bec/ophyd_devices/-/commit/172d735672c5115ffdf6ca2a2653aa9bea75934a))

* Merging master ([`c323354`](https://gitlab.com/bec/ophyd_devices/-/commit/c323354feaaff8b5e05145fa16a638fa7bbc8a7c))

* various_fixes_and_printouts ([`e5f8a4e`](https://gitlab.com/bec/ophyd_devices/-/commit/e5f8a4e772c1ce77e4549b25e1ce097961e1306e))


## v0.26.1 (2024-03-10)

### Fix

* fix: fixed dynamic pseudo ([`33e4458`](https://gitlab.com/bec/ophyd_devices/-/commit/33e4458c59cce44e93d9f3bae44ce41028688471))


## v0.26.0 (2024-03-08)

### Documentation

* docs: improved doc strings for computed signal ([`c68c3c1`](https://gitlab.com/bec/ophyd_devices/-/commit/c68c3c1b54ecff2c51417168ee3e91b4056831fc))

### Feature

* feat: added computed signal ([`d9f09b0`](https://gitlab.com/bec/ophyd_devices/-/commit/d9f09b0d866f97a859c9b437474928e7a9e8c1b6))

### Test

* test: added tests for dynamic_pseudo ([`c76e1a0`](https://gitlab.com/bec/ophyd_devices/-/commit/c76e1a0b4e012271b4e4baaa2ff8210f59a984b9))


## v0.25.3 (2024-03-08)

### Fix

* fix: fix type conversion for SimCamera uniform noise ([`238ecb5`](https://gitlab.com/bec/ophyd_devices/-/commit/238ecb5ff84b55f028b75df32fccdc3685609d69))

### Unknown

* Basic examples ([`7a486a1`](https://gitlab.com/bec/ophyd_devices/-/commit/7a486a17da95b87113aa7487c3436d17bfb34008))


## v0.25.2 (2024-03-08)

### Fix

* fix(smaract): added user access for axis_is_referenced and all_axes_referenced ([`4fbba73`](https://gitlab.com/bec/ophyd_devices/-/commit/4fbba7393adbb01ebf80667b205a1dbaab9bb15c))

* fix(smaract): fixed axes_referenced ([`a9f58d2`](https://gitlab.com/bec/ophyd_devices/-/commit/a9f58d2b5686370a07766ed72903f82f5e2d9cb1))

### Unknown

* Moved aerotech to its own directory ([`413de89`](https://gitlab.com/bec/ophyd_devices/-/commit/413de89a83e7311aada61e7fc51da1e9b62d5e7d))

* Added simplified scripted sequence scan ([`3fd19f8`](https://gitlab.com/bec/ophyd_devices/-/commit/3fd19f85bab3b4ad4b5e18a5eef8237e1d478653))

* New complete with added IOC functionality ([`174e5fd`](https://gitlab.com/bec/ophyd_devices/-/commit/174e5fdb6120a7da70dabc42fb9ee66da612042b))

* fixed formatting ([`4ff7c4b`](https://gitlab.com/bec/ophyd_devices/-/commit/4ff7c4b8d9ed99dd63bdf665b266bcef320f0721))

* added show all to sample storage ([`02f950d`](https://gitlab.com/bec/ophyd_devices/-/commit/02f950de8d6b2eba142495f71b2f470133f13187))

* cd: drop python/3.9 ([`345a95d`](https://gitlab.com/bec/ophyd_devices/-/commit/345a95dbe72c939150272445b07e017f6a203f87))

* Added templated scan and required status updates ([`16f033a`](https://gitlab.com/bec/ophyd_devices/-/commit/16f033a8338be8df620622d298bb4ed425b8f2a2))


## v0.25.1 (2024-03-05)

### Fix

* fix: device_status should use set ([`6d179ea`](https://gitlab.com/bec/ophyd_devices/-/commit/6d179ea8a8e41374cfe2b92939e0b71b7962f7cb))

* fix: device_read should use set_and_publish ([`afd7912`](https://gitlab.com/bec/ophyd_devices/-/commit/afd7912329b14bc916e14fd565ebcf7506ecb045))


## v0.25.0 (2024-03-04)

### Feature

* feat: add proxy for h5 image replay for SimCamera ([`5496b59`](https://gitlab.com/bec/ophyd_devices/-/commit/5496b59ae2254495845a0fae2754cdd935b4fb7b))

### Fix

* fix: add dependency for env ([`eb4e10e`](https://gitlab.com/bec/ophyd_devices/-/commit/eb4e10e86bba9b55623d089572f104d21d96601e))

* fix: fix bug in computation of negative data within SimMonitor ([`f4141f0`](https://gitlab.com/bec/ophyd_devices/-/commit/f4141f0dbf8d98f1d1591c66ccd147099019afc7))

### Refactor

* refactor: fix docstrings ([`e5fada8`](https://gitlab.com/bec/ophyd_devices/-/commit/e5fada8e9dc43fab6781624388d966743ebc1356))

* refactor: fix _add_noise ([`aff4cb2`](https://gitlab.com/bec/ophyd_devices/-/commit/aff4cb227cd2bb857c3e0903e3c3e2710bd05ab7))

* refactor: small fix to int return ([`9a154f0`](https://gitlab.com/bec/ophyd_devices/-/commit/9a154f01e48e33c0e28921b8a5c59af4d4585aeb))

### Unknown

* Scans are still hanging... ([`1f3ef42`](https://gitlab.com/bec/ophyd_devices/-/commit/1f3ef42a9de547c4f9eab6488e3fcd8dc42222e1))


## v0.24.2 (2024-03-01)

### Fix

* fix: sim_monitor negative readback fixed ([`91e587b`](https://gitlab.com/bec/ophyd_devices/-/commit/91e587b09271a436e7405c44dda60ea4b536865b))

### Test

* test: add tests for sim ([`5ca6812`](https://gitlab.com/bec/ophyd_devices/-/commit/5ca681212f7b8f2225236adcb0da67f29e20b4d5))

### Unknown

* More cleanup with testing ([`e44ca3d`](https://gitlab.com/bec/ophyd_devices/-/commit/e44ca3d48090347a0918c223cf20d48809cb7333))

* More cleanup with testing ([`49da8b3`](https://gitlab.com/bec/ophyd_devices/-/commit/49da8b32da4ea5e70ec590f266a8c0133526a93f))


## v0.24.1 (2024-02-26)

### Fix

* fix: SimCamera return uint16, SimMonitor uint32 ([`dc9634b`](https://gitlab.com/bec/ophyd_devices/-/commit/dc9634b73988b5c3cd430008eac5c94319b33ae1))

### Refactor

* refactor: cleanup and exclude ComplexConstantModel ([`6eca704`](https://gitlab.com/bec/ophyd_devices/-/commit/6eca704adcdc7955d88a60ffc7075d32afba43c9))

* refactor: cleanup ([`961041e`](https://gitlab.com/bec/ophyd_devices/-/commit/961041e07299b1c811e9f0aaf6f7540bca688fd9))

### Unknown

* Revert &#34;Revert &#34;fix(deprecation): remove all remaining .dumps(), .loads() and producer-&gt;connector&#34;&#34;

This reverts commit b12292246fd9d8204c76cd1f4927da5a1b981857 ([`f1e9d1c`](https://gitlab.com/bec/ophyd_devices/-/commit/f1e9d1ceaa00d38f38bccd7516913bd57e10bf49))


## v0.24.0 (2024-02-23)

### Documentation

* docs: added doc strings ([`2da6379`](https://gitlab.com/bec/ophyd_devices/-/commit/2da6379e8eb346d856a68a8e5bc678dfff5b1600))

### Feature

* feat: add lmfit for SimMonitor, refactored sim_data with baseclass, introduce slitproxy ([`800c22e`](https://gitlab.com/bec/ophyd_devices/-/commit/800c22e9592e288f8fe8dea2fb572b81742c6841))

### Fix

* fix: extend bec_device with root, parent, kind ([`db00803`](https://gitlab.com/bec/ophyd_devices/-/commit/db00803f539791ceefd5f4f0424b00c0e2ae91e6))

### Refactor

* refactor: fix Kind import in bec_device_base ([`8b04b5c`](https://gitlab.com/bec/ophyd_devices/-/commit/8b04b5c84eb4e42c8a0ec7e28727ff907a584a4f))

* refactor: bugfix in camera data, model constant ([`00f1898`](https://gitlab.com/bec/ophyd_devices/-/commit/00f1898a354cd2f557854b02223df11a18f4dde5))

### Test

* test: added devices for e2e tests ([`bc97346`](https://gitlab.com/bec/ophyd_devices/-/commit/bc973467b75d8ee494463afcd82fb84289371586))

### Unknown

* Extended motor class ([`524ed77`](https://gitlab.com/bec/ophyd_devices/-/commit/524ed777f0b6b5fbe2dd361bc0663c495f64131a))

* Smaller fixes from cross testing ([`bb37167`](https://gitlab.com/bec/ophyd_devices/-/commit/bb37167d33d65edb796a38deb2e696b23379602f))


## v0.23.1 (2024-02-21)

### Fix

* fix: replaced outdated enable_set by read_only ([`f91d0c4`](https://gitlab.com/bec/ophyd_devices/-/commit/f91d0c482d194e5f69c7206d0f6ad0971f84b0e1))


## v0.23.0 (2024-02-21)

### Ci

* ci: added environment variable for downstream pipelines ([`406f27c`](https://gitlab.com/bec/ophyd_devices/-/commit/406f27c27ea9742bc1f33028234e06520cd891be))

### Feature

* feat(static_device_test): added check against BECDeviceBase protocol ([`82cfefb`](https://gitlab.com/bec/ophyd_devices/-/commit/82cfefb3b969f0fdebc357f8bd5b404ec503d7ce))

### Fix

* fix: separate BECDevice and BECDeviceBase ([`2f2cef1`](https://gitlab.com/bec/ophyd_devices/-/commit/2f2cef10f7fb77e502cbf274a6b350f2feb0ad22))

### Refactor

* refactor: made BECDeviceBase a protocol ([`84fed4e`](https://gitlab.com/bec/ophyd_devices/-/commit/84fed4ee82980d6a44650bd97070b615d36aa4b2))

### Test

* test(BECDeviceBase): add test ([`399d6d9`](https://gitlab.com/bec/ophyd_devices/-/commit/399d6d94cc3ce29a67ae7c6daba536aa66df9d76))

* test(flomni): added more tests ([`7a97e05`](https://gitlab.com/bec/ophyd_devices/-/commit/7a97e05e04478394423e398f871629fc9c3ef345))

### Unknown

* Seuence scan via Ophyd works ([`47815ee`](https://gitlab.com/bec/ophyd_devices/-/commit/47815ee2386bee5b5e0ae3dbbb940d10c6ce1bd4))

* Revert &#34;refactor: quickfix connector/producer import in scaninfo mixin&#34;

This reverts commit 65b9f23332f440a5d467fde789747166c18e1458 ([`8d5b32e`](https://gitlab.com/bec/ophyd_devices/-/commit/8d5b32ebd6e01d6870755c4894f31078ade40317))

* Revert &#34;fix(deprecation): remove all remaining .dumps(), .loads() and producer-&gt;connector&#34;

This reverts commit 4159f3e3ec20727b395808118f3c0c166d9d1c0c ([`b122922`](https://gitlab.com/bec/ophyd_devices/-/commit/b12292246fd9d8204c76cd1f4927da5a1b981857))


## v0.22.0 (2024-02-17)

### Feature

* feat: Add simulation framework for pinhole scan ([`491e105`](https://gitlab.com/bec/ophyd_devices/-/commit/491e105af0871449cd0f48b08c126023aa28445b))

* feat: extend sim_data to allow execution from function of secondary devices extracted from lookup ([`851a088`](https://gitlab.com/bec/ophyd_devices/-/commit/851a088b81cfd7e9d323955f923174a394155bfd))

### Refactor

* refactor: quickfix connector/producer import in scaninfo mixin ([`65b9f23`](https://gitlab.com/bec/ophyd_devices/-/commit/65b9f23332f440a5d467fde789747166c18e1458))

* refactor: add DeviceProxy class to sim_framework

refactor(__init__): remove bec_device_base from import

refactor: cleanup __init__

refactor: cleanup

refactor: cleanup, renaming and small fixes to sim_framework.

refactor: cleanup imports

refactor: cleanup ([`01c8559`](https://gitlab.com/bec/ophyd_devices/-/commit/01c8559319836cca3d5d61267ddfb19791aea902))


## v0.21.1 (2024-02-17)

### Fix

* fix(deprecation): remove all remaining .dumps(), .loads() and producer-&gt;connector ([`4159f3e`](https://gitlab.com/bec/ophyd_devices/-/commit/4159f3e3ec20727b395808118f3c0c166d9d1c0c))


## v0.21.0 (2024-02-16)

### Feature

* feat(galil): added lights on/off ([`366f592`](https://gitlab.com/bec/ophyd_devices/-/commit/366f592e08a4cb50ddae7b3f8ba3aa214574f61f))

* feat: flomni stages ([`5e9d3ae`](https://gitlab.com/bec/ophyd_devices/-/commit/5e9d3aed17ce02142f12ba69ea562d6c30b41ae3))

* feat: flomni stages ([`b808659`](https://gitlab.com/bec/ophyd_devices/-/commit/b808659d4d8b1af262d6f62174b027b0736a005a))

### Fix

* fix: fixed import after rebase conflict ([`747aa36`](https://gitlab.com/bec/ophyd_devices/-/commit/747aa36837fa823cd2f05e294e2ee9ee83074f43))

* fix: online changes during flomni comm ([`4760456`](https://gitlab.com/bec/ophyd_devices/-/commit/4760456e6318b66fa26f35205f669dbbf7d0e777))

### Refactor

* refactor(fgalil): cleanup ([`b9e777c`](https://gitlab.com/bec/ophyd_devices/-/commit/b9e777c14e1d4e8804c89e2c401ba5956316bb22))

* refactor: formatting; fixed tests for expected return ([`bf38e89`](https://gitlab.com/bec/ophyd_devices/-/commit/bf38e89f797bd72b45f2457df19c5c468af7cc9c))

### Test

* test(rt_flomni): added tests ([`6d7fd5f`](https://gitlab.com/bec/ophyd_devices/-/commit/6d7fd5fd9f8c293c834a0e321348f31855658744))

* test: added tests for fupr and flomni galil ([`1c95220`](https://gitlab.com/bec/ophyd_devices/-/commit/1c95220234b65f95c95d5033551e17a1689f1249))


## v0.20.1 (2024-02-13)

### Feature

* feat: Moving the Automation1 device to BEC repo ([`26ee4e2`](https://gitlab.com/bec/ophyd_devices/-/commit/26ee4e2d9bd9cb37eebefe9102ca78aa0fd55b33))

### Fix

* fix: Use getpass.getuser instead of os.getlogin to retrieve user name ([`bd42d9d`](https://gitlab.com/bec/ophyd_devices/-/commit/bd42d9d56093316f4a9f90a3329b6b5a6d1c851e))


## v0.20.0 (2024-02-13)

### Refactor

* refactor: Remove send msg to BEC, seems to be not needed ([`fa6e24f`](https://gitlab.com/bec/ophyd_devices/-/commit/fa6e24f04894c8e9a6b5920d04468c5194bf45a4))

* refactor: cleanup and renaming according to MR comments ([`8cc7e40`](https://gitlab.com/bec/ophyd_devices/-/commit/8cc7e408a52fb6ca98673fa2045f1658cfcc3925))

* refactor(__init__): Merge branch &#39;master&#39; into &#39;cleanup/sim_framework&#39; ([`87ff927`](https://gitlab.com/bec/ophyd_devices/-/commit/87ff92796f07f5d54666791f58101212be5e031b))


## v0.19.3 (2024-02-10)

### Feature

* feat: add BECDeviceBase to ophyd_devices.utils ([`8ee5022`](https://gitlab.com/bec/ophyd_devices/-/commit/8ee502242457f3ac63c122f81e7600e300fdf73a))

### Fix

* fix: add imports for core config updates ([`fdb2da5`](https://gitlab.com/bec/ophyd_devices/-/commit/fdb2da5839e72359b53c3837292eeced957e43de))

* fix: separated core simulation classes from additional devices ([`2225daf`](https://gitlab.com/bec/ophyd_devices/-/commit/2225dafb7438f576d7033e220910b4cf8769fd33))

### Refactor

* refactor: moved bec_scaninfo_mixin to ophyd_devices/utils ([`6fb912b`](https://gitlab.com/bec/ophyd_devices/-/commit/6fb912bd9c4453d4474dd0dc5a94676988f356bc))

* refactor: refactored SimMonitor and SimCamera ([`96a5f1b`](https://gitlab.com/bec/ophyd_devices/-/commit/96a5f1b86a17f099a935c460baf397d9c93bc612))


## v0.19.2 (2024-02-07)

### Fix

* fix: fixed bec_scaninfo_mixin ([`ec3ea35`](https://gitlab.com/bec/ophyd_devices/-/commit/ec3ea35744e300fa363be3724f5e6c7b81abe7f1))


## v0.19.1 (2024-02-07)

### Fix

* fix: remove set and from sim_signals ([`bd128ea`](https://gitlab.com/bec/ophyd_devices/-/commit/bd128ea8a459d08f6018c0d8459a534d6a828073))


## v0.19.0 (2024-01-31)

### Ci

* ci: fix secret detection ([`2ccd096`](https://gitlab.com/bec/ophyd_devices/-/commit/2ccd096ead884cc5a9916cac389ee4e43add4a68))

* ci: added security detection ([`3b731bb`](https://gitlab.com/bec/ophyd_devices/-/commit/3b731bbf4a1145f91133bf8295a0cf00b4c2e15e))

* ci: added downstream_pipeline ([`eccd1aa`](https://gitlab.com/bec/ophyd_devices/-/commit/eccd1aa539e9e4e34a3d8908da649a8c94bb754f))

### Feature

* feat: refactor simulation, introduce SimCamera, SimMonitor in addition to existing classes ([`f311ce5`](https://gitlab.com/bec/ophyd_devices/-/commit/f311ce5d1c082c107f782916c2fb724a34a92099))

* feat: introduce new general class to simulate data for devices ([`8cc955b`](https://gitlab.com/bec/ophyd_devices/-/commit/8cc955b202bd7b45acba06322779079e7a8423a3))

* feat: move signals to own file and refactor access pattern to sim_state data. ([`6f3c238`](https://gitlab.com/bec/ophyd_devices/-/commit/6f3c2383b5d572cf1f6d51acecb63c786ac16196))

### Fix

* fix: temporal fix for imports ([`6cac04a`](https://gitlab.com/bec/ophyd_devices/-/commit/6cac04aa5227340f4e5758e4bfcc1798acbc1ed7))

### Refactor

* refactor: remove sleep from trigger, and adressed MR comments in sim_data ([`10e9acf`](https://gitlab.com/bec/ophyd_devices/-/commit/10e9acff8adf15386f1de404d99fd6f8f42a5bf3))


## v0.18.0 (2024-01-26)

### Build

* build: fixed dev dependencies ([`5759b2a`](https://gitlab.com/bec/ophyd_devices/-/commit/5759b2a814f1f89d17bacf22b9e5743ea8516798))

### Ci

* ci: moved dependency to ci pipeline; not needed for dev ([`68025e3`](https://gitlab.com/bec/ophyd_devices/-/commit/68025e3341929e9172c8a505cfed2c5ac300d207))

* ci: added no-cover to static device test ([`97e102f`](https://gitlab.com/bec/ophyd_devices/-/commit/97e102fddb8990a85a6102640545160ffc051d3f))

### Feature

* feat: added basic function tests ([`b54b5d4`](https://gitlab.com/bec/ophyd_devices/-/commit/b54b5d4b00150ef581247da495804cc5e801e24e))

### Refactor

* refactor: fixed pragma statement (hopefully) ([`257a316`](https://gitlab.com/bec/ophyd_devices/-/commit/257a316f6ed7bf331c0ed5670848f2f58fbf0917))

### Test

* test: added test for static_device_test ([`baac1ff`](https://gitlab.com/bec/ophyd_devices/-/commit/baac1ffe879f296c01e09375e6b137effc77a1e4))


## v0.17.1 (2024-01-26)

### Fix

* fix: changed default for connecting to a device ([`802eb29`](https://gitlab.com/bec/ophyd_devices/-/commit/802eb295562ecc39f833d4baba8820a892c674a2))

### Unknown

* reactor: rerun formatting with black24 ([`710beb8`](https://gitlab.com/bec/ophyd_devices/-/commit/710beb83707cd87afe4580b47a6184d7e9978fdf))


## v0.17.0 (2024-01-24)

### Feature

* feat: added tests for connecting devices ([`8c6d0f5`](https://gitlab.com/bec/ophyd_devices/-/commit/8c6d0f50cdb61843532c7a2f2a03a421acdb126a))

* feat: added static_device_test ([`bb02a61`](https://gitlab.com/bec/ophyd_devices/-/commit/bb02a619e56749c03d3efadb0364e845fc4a7724))


## v0.16.0 (2023-12-24)

### Build

* build: fix python requirement ([`4362697`](https://gitlab.com/bec/ophyd_devices/-/commit/43626973caaef58b9a3c96e3bcfecba8d163dc09))

### Feature

* feat: add detector, grashopper tomcat to repository ([`ca726c6`](https://gitlab.com/bec/ophyd_devices/-/commit/ca726c606605085e2849402cd0fae3865550514f))

### Fix

* fix: fix cobertura syntax in ci-pipeline ([`40eb699`](https://gitlab.com/bec/ophyd_devices/-/commit/40eb6999c73bf18af875a3665e1f0006bd645d44))

### Refactor

* refactor: fix syntax .gitlab-ci.yml file ([`a67d6a2`](https://gitlab.com/bec/ophyd_devices/-/commit/a67d6a2d5f7fda76330eab76be80d0ec1e7a4bef))

* refactor: refactor docstrings ([`0d14f9a`](https://gitlab.com/bec/ophyd_devices/-/commit/0d14f9aac6c0eb4fee74cecf5a81b4cf4e496e33))

* refactor: updates related to bec_lib refactoring ([`13f75aa`](https://gitlab.com/bec/ophyd_devices/-/commit/13f75aa2fd8c9386d7bfec5c61ecc4d498f55cef))

* refactor: temporary add SynAxisOPAAS to __init__.py ([`adaa943`](https://gitlab.com/bec/ophyd_devices/-/commit/adaa9435e3f751a13e4eb171de9a6156de7d9cc0))

* refactor: renamed SynAxisOPPAS to SimPositioner; moved readback/setpoint/ismoving signal to sim_signals; closes 27 ([`2db65a3`](https://gitlab.com/bec/ophyd_devices/-/commit/2db65a385524b81bef1943a2a91693f327de4213))

* refactor: replace deprecated imports from typing

https://peps.python.org/pep-0585/#implementation ([`952c92e`](https://gitlab.com/bec/ophyd_devices/-/commit/952c92e4b9e6a64a18f445871147ba4ce62fd2f0))

### Unknown

* tests: add tests for grashopper ([`2d4c5e8`](https://gitlab.com/bec/ophyd_devices/-/commit/2d4c5e84348883f5dc337fc38b9e01331ed5e117))

* fix SimPositioner to import DummyController ([`b166341`](https://gitlab.com/bec/ophyd_devices/-/commit/b166341e6f515617f3ed6861fae437eb42ef7a0c))


## v0.15.0 (2023-12-12)

### Documentation

* docs: add files ([`ae5c27f`](https://gitlab.com/bec/ophyd_devices/-/commit/ae5c27f045e21aaae11ae5b937f46ecaa2633f8b))

### Feature

* feat: update ci to default to python3.9 ([`849e152`](https://gitlab.com/bec/ophyd_devices/-/commit/849e15284f6e1f90e970c0706b158116aed29afa))

### Fix

* fix: add python 3.12 to ci pipeline ([`31b9646`](https://gitlab.com/bec/ophyd_devices/-/commit/31b964663c5384de2a6c8858ca3ac8f2cabf5bbb))

* fix: fix syntax/bug ([`069f89f`](https://gitlab.com/bec/ophyd_devices/-/commit/069f89f0e7083d5893619f6335f16b5f52352a1b))

### Test

* test: fix bug in usage of mock for tests ([`c732855`](https://gitlab.com/bec/ophyd_devices/-/commit/c732855314de3cf452181f9cbcf9a4ff8b97288f))

### Unknown

* Revert &#34;NIDAQ Ophyd runner for X01DA&#34;

This reverts commit b7a62ea6b1617aa221117fb247f612ff456f58a6 ([`0767eb5`](https://gitlab.com/bec/ophyd_devices/-/commit/0767eb51c9c7f43fc6b96b506e34cf37f3df5c7b))

* NIDAQ Ophyd runner for X01DA ([`b7a62ea`](https://gitlab.com/bec/ophyd_devices/-/commit/b7a62ea6b1617aa221117fb247f612ff456f58a6))


## v0.14.1 (2023-11-23)

### Fix

* fix: bugfix tests DDG ([`9e67a7a`](https://gitlab.com/bec/ophyd_devices/-/commit/9e67a7a7d469af0505b60bb29ed54b15ac083806))


## v0.14.0 (2023-11-23)

### Documentation

* docs: reviewed docstrings ([`da44e5d`](https://gitlab.com/bec/ophyd_devices/-/commit/da44e5d7bb122abda480a918327faf5d460cb396))

* docs: reviewed docstrings ([`d295741`](https://gitlab.com/bec/ophyd_devices/-/commit/d295741bd04930fc4397c89ac039a01c526d2d1e))

### Feature

* feat: add test for class ([`19faece`](https://gitlab.com/bec/ophyd_devices/-/commit/19faece0a5e119e1f1403372c09825748de5e032))

* feat: add delay_generator_csaxs ([`e5c90ee`](https://gitlab.com/bec/ophyd_devices/-/commit/e5c90ee2156ac076d7cea56975c1ed459adb8727))

* feat: create base class for DDG at psi ([`d837ddf`](https://gitlab.com/bec/ophyd_devices/-/commit/d837ddfd1cd7935b4f472b976b925d2d70056cd7))

### Fix

* fix: bugfix and reorder call logic in _init ([`138d181`](https://gitlab.com/bec/ophyd_devices/-/commit/138d18168fa64a2dfb31218266e1f653a74ff4d5))

* fix: fix imports of renamed classes ([`6780c52`](https://gitlab.com/bec/ophyd_devices/-/commit/6780c523bd2192fc2234296987bdabeb45f81ee4))

### Refactor

* refactor: remove readme.md for DDG. Classes have sufficient docstrings ([`3851983`](https://gitlab.com/bec/ophyd_devices/-/commit/385198342d002c6fed273ff7d68f2e060bc6b9aa))

* refactor: removed burst_enabl/disable etc.. slight refactoring of prepare_ddg ([`f218a9b`](https://gitlab.com/bec/ophyd_devices/-/commit/f218a9b11425f25ff38977d366f4eb8e0ae5e886))

* refactor: moved burst_enable/disable, set_trigger to base class ([`a734116`](https://gitlab.com/bec/ophyd_devices/-/commit/a73411646d86f100dead46698b2f7c8f0684bcb6))


## v0.13.4 (2023-11-23)

### Fix

* fix: bugfix: remove std_client from psi_det_base_class; closes #25 ([`3ad0daa`](https://gitlab.com/bec/ophyd_devices/-/commit/3ad0daa5bcefe585d4f89992e49c9856a55e6183))


## v0.13.3 (2023-11-21)

### Documentation

* docs: imporive pylint score ([`5b27e6f`](https://gitlab.com/bec/ophyd_devices/-/commit/5b27e6fe1e20a50894c47144a412b9361ab1c4e6))

* docs: add docstrings, improve pylint score ([`5874466`](https://gitlab.com/bec/ophyd_devices/-/commit/587446670444f245ec2c24db0355578921b8fe59))

* docs: add docstring ([`cbe8c8c`](https://gitlab.com/bec/ophyd_devices/-/commit/cbe8c8c4e5a53a0b38a58e11b85b11307e92ced7))

### Fix

* fix: fix auto_monitor=True for MockPV by add add_callback = mock.MagicMock() ([`e7f7f9d`](https://gitlab.com/bec/ophyd_devices/-/commit/e7f7f9d6658a27ca98ac17ffb998efae51ec3497))

* fix: renamed to prepare_detector_backend ([`16022c5`](https://gitlab.com/bec/ophyd_devices/-/commit/16022c53ef9e3134fe486892c27f26e5c12fad2e))

* fix: rename custome_prepare.prepare_detector_backend, bugfix in custom_prepare.wait_for_signals ([`f793ec7`](https://gitlab.com/bec/ophyd_devices/-/commit/f793ec7b1f3f2d03a686d592d4cd9c2e2f087faf))

* fix: add __init__ and super().__init__ to falcon,eiger and pilatus ([`9e26fc2`](https://gitlab.com/bec/ophyd_devices/-/commit/9e26fc2a3c82e610d0c570db9a08a698c3394bc8))

### Refactor

* refactor: remove redundant __init__ calls ([`7f6db66`](https://gitlab.com/bec/ophyd_devices/-/commit/7f6db669dbac3680e782c183883f1adb6a0f19c5))

* refactor: mcs_cSAXS complies with psi_detector_base ([`8bd65b7`](https://gitlab.com/bec/ophyd_devices/-/commit/8bd65b7d671b148f1c0826a27dd6c998e029eac9))

* refactor: mcs_card inherits from base class psi_detector_base ([`d77e8e2`](https://gitlab.com/bec/ophyd_devices/-/commit/d77e8e255de46c701b9fa5357a5b740cec269625))

* refactor: fix __ini__ and add comment to psi_detector_base ([`3a37de9`](https://gitlab.com/bec/ophyd_devices/-/commit/3a37de9eda90d55714f77192ad949043c3694f2c))

### Test

* test: fix test_send_data_to_bec ([`a3cf93e`](https://gitlab.com/bec/ophyd_devices/-/commit/a3cf93e41b50b99bf28898ee038662a3cebed712))

* test: add tests ([`4e7f1b5`](https://gitlab.com/bec/ophyd_devices/-/commit/4e7f1b559347d7472d1912d4c7f64c574d0c8fea))


## v0.13.2 (2023-11-20)

### Fix

* fix: remove stop from falcon.custom_prepare.arm_acquisition; closes #23 ([`9e1a6da`](https://gitlab.com/bec/ophyd_devices/-/commit/9e1a6daa6edbfe2a9e7c9b15f21af5785a119474))

* fix: remove stop from pilatus.custom_prepare.finished ([`334eeb8`](https://gitlab.com/bec/ophyd_devices/-/commit/334eeb83dc3e1c7c37ce41d2ba5f720c3880ef46))

* fix: remove duplicated stop call from eiger.custom_prepare.finished ([`175700b`](https://gitlab.com/bec/ophyd_devices/-/commit/175700b6ad135cb7491eb88431ecde56704fd0b4))


## v0.13.1 (2023-11-18)

### Fix

* fix: include all needed files in packaged distro

Fix #21 ([`204f94e`](https://gitlab.com/bec/ophyd_devices/-/commit/204f94e0e4496f8347772f869bb0722e6ffb9ccf))


## v0.13.0 (2023-11-17)

### Feature

* feat: refactor falcon for psi_detector_base class; adapted eiger; added and debugged tests ([`bcc3210`](https://gitlab.com/bec/ophyd_devices/-/commit/bcc321076153ccd6ae8419b95553b5b4916e82ad))

* feat: add CustomDetectorMixin, and Eiger9M setup to separate core functionality in the ophyd integration ([`c8f05fe`](https://gitlab.com/bec/ophyd_devices/-/commit/c8f05fe290485dd7703dfb7a4bfc660d7d01d67d))

* feat: add docstring to detector base class; closes #12 ([`2252779`](https://gitlab.com/bec/ophyd_devices/-/commit/225277949d91febd4482475a12c1ea592b735385))

* feat: add SLSDetectorBaseclass as a baseclass for detectors at SLS ([`13180b5`](https://gitlab.com/bec/ophyd_devices/-/commit/13180b56dac614206ca5a8ad088e223407b83977))

### Fix

* fix: fixed MIN_readout, and made it a class attribute with set/get functions ([`b9d0a5d`](https://gitlab.com/bec/ophyd_devices/-/commit/b9d0a5d86977ff08962a27ac507296ca5dae229c))

* fix: add User_access to cSAXS falcon and eiger ([`e8ec101`](https://gitlab.com/bec/ophyd_devices/-/commit/e8ec101f5399ac7be2aeb1b1d69d6866d6d2f69b))

* fix: removed __init__ from eiger9mcSAXS ([`c614873`](https://gitlab.com/bec/ophyd_devices/-/commit/c614873f8f913e0c1d417b63cf6dea2f39708741))

* fix: fix imports to match bec_lib changes ([`9db00ad`](https://gitlab.com/bec/ophyd_devices/-/commit/9db00add047536c7aa35d2b08daafb248d5c8c01))

* fix: fixed merge conflict ([`d46dafd`](https://gitlab.com/bec/ophyd_devices/-/commit/d46dafdbe85b9f2a1c080297bd361a3445779d60))

* fix: removed sls_detector_baseclass, add psi_detector_base, fixed tests and eiger9m_csaxs ([`90cd05e`](https://gitlab.com/bec/ophyd_devices/-/commit/90cd05e68ea7640a6bc1a8b98d47f9edc7a7f3a0))

* fix: add PSIDetectorBase ([`a8a1210`](https://gitlab.com/bec/ophyd_devices/-/commit/a8a12103ea2108c5183a710ead04db4379627d83))

* fix: small bugfix ([`ee5cf17`](https://gitlab.com/bec/ophyd_devices/-/commit/ee5cf17a05ededda6eff25edece6d6f437d0f372))

* fix: fixed imports to comply with bec_lib refactoring ([`79cfaf6`](https://gitlab.com/bec/ophyd_devices/-/commit/79cfaf6dc03bad084673fe1945828c15bba4b6e8))

* fix: bugfix ([`7fefb44`](https://gitlab.com/bec/ophyd_devices/-/commit/7fefb44462c4bfa7853b0519b33ef492ace53050))

* fix: add remaining function, propose mechanism to avoid calling stage twice ([`3e1a2b8`](https://gitlab.com/bec/ophyd_devices/-/commit/3e1a2b86c31a241ac92ef9808ad2b92fed020ec8))

* fix: changed file_writer to det_fw ([`575b4e6`](https://gitlab.com/bec/ophyd_devices/-/commit/575b4e6260e95d4c4c40d76b3fc38f258e43a381))

### Refactor

* refactor: refactored pylint formatting ([`8bf208e`](https://gitlab.com/bec/ophyd_devices/-/commit/8bf208e6975184714dae728a29c5b84cde073ebd))

* refactor: clean up code ([`4c86f8c`](https://gitlab.com/bec/ophyd_devices/-/commit/4c86f8cfb2f816faa76493c0c471374a5f155566))

* refactor: refactored pilatus to psi_detector_base class and adapted tests ([`e9d9711`](https://gitlab.com/bec/ophyd_devices/-/commit/e9d9711aa7cc70de4490433844b6b92130c56650))

### Test

* test: remove tests from pylint check ([`6e4b7c6`](https://gitlab.com/bec/ophyd_devices/-/commit/6e4b7c6b18ccce6f60c503f47a4082d5a6eeabbd))

### Unknown

* doc: refactor docstrings ([`5c7fe09`](https://gitlab.com/bec/ophyd_devices/-/commit/5c7fe09a4b2ee02b774eed6c3cca625e6d29f1d3))

* doc: add docstrings for functions ([`3478435`](https://gitlab.com/bec/ophyd_devices/-/commit/3478435e02d31ccf3ed701be8c1bdfee41a3a2fc))

* fix; add other abstract methods, except: stage/unstage/_finished and _publish_file_location ([`9c398e6`](https://gitlab.com/bec/ophyd_devices/-/commit/9c398e6ac65450e699f02eda1c54b9311ba15ea7))


## v0.12.0 (2023-11-17)

### Feature

* feat: added syndynamiccomponents for BEC CI tests ([`824ae0b`](https://gitlab.com/bec/ophyd_devices/-/commit/824ae0bde63f2ba5278e532812fe41d07f179099))


## v0.11.0 (2023-11-16)

### Feature

* feat: add pylint check to ci pipeline ([`a45ffe7`](https://gitlab.com/bec/ophyd_devices/-/commit/a45ffe7740714a57aad54fbc56164971144a6b7d))

### Refactor

* refactor: fix bec_lib imports ([`d851cf6`](https://gitlab.com/bec/ophyd_devices/-/commit/d851cf6f8e7bb80eee64866584f2acc9350b8c46))


## v0.10.2 (2023-11-12)

### Fix

* fix: remove pytest dependency for eiger, falcon and pilatus; closes #18 and #9 ([`c6e6737`](https://gitlab.com/bec/ophyd_devices/-/commit/c6e6737547face4f298758e4017099208748d1a9))

### Refactor

* refactor: add configurable timeout and ClassInitError ([`a7d713b`](https://gitlab.com/bec/ophyd_devices/-/commit/a7d713b50d7b65f39f4975cfecb2159cb6a87a6c))

* refactor: remove obsolet test.py function; relates to #19 ([`a4efb59`](https://gitlab.com/bec/ophyd_devices/-/commit/a4efb59589c8530ee9f45a44f2ed7137e4672c07))

* refactor: refacoring of falcon sitoro ([`97b6111`](https://gitlab.com/bec/ophyd_devices/-/commit/97b61118321dd13bf1a41b8e24e6bc84d77af16a))

* refactor: refactore falcon __init__ ([`38db08c`](https://gitlab.com/bec/ophyd_devices/-/commit/38db08c87749ad8e1c75920b0efdd93c5cf9d622))

### Test

* test: fix mock_cl.thread_class for eiger,falcon and pilatus; add tests for falcon csaxs; fix bugs in code based on tests ([`e3e134c`](https://gitlab.com/bec/ophyd_devices/-/commit/e3e134c65d63305289137ce525db3dcf6733c453))


## v0.10.1 (2023-11-09)

### Fix

* fix: adding pytest as dependency; should be removed! ([`a6a621f`](https://gitlab.com/bec/ophyd_devices/-/commit/a6a621f5ea88370152256908cdd4d60ce4489c7b))

### Refactor

* refactor: fixed formatting ([`b59f9b4`](https://gitlab.com/bec/ophyd_devices/-/commit/b59f9b40ed33d3215fbf6a86a65b6e853edfe03e))


## v0.10.0 (2023-11-08)

### Feature

* feat: added fupr ([`9840491`](https://gitlab.com/bec/ophyd_devices/-/commit/9840491ab7f92eacdb7616b9530659b1800654af))

* feat: added support for flomni galil ([`23664e5`](https://gitlab.com/bec/ophyd_devices/-/commit/23664e542cfcccafe31d0e41d1421c277bd00d23))

* feat: added galil for flomni ([`7b17b84`](https://gitlab.com/bec/ophyd_devices/-/commit/7b17b8401a516613ee3e67f1e03892ba573e392c))

### Fix

* fix: changed dependency injection for controller classes; closes #13 ([`fb9a17c`](https://gitlab.com/bec/ophyd_devices/-/commit/fb9a17c5e383e2a378d0a3e9cc7cc185dd20c96e))

* fix: fixed fupr number of axis ([`9080d45`](https://gitlab.com/bec/ophyd_devices/-/commit/9080d45075158b1a7d7a60838ea33f058260755f))

* fix: fixed fupr axis_is_referenced ([`ce94a6a`](https://gitlab.com/bec/ophyd_devices/-/commit/ce94a6a88df6f90409c4fb4c29260ad77048f27d))

* fix: fixed fupr axis_is_referenced ([`3396ff4`](https://gitlab.com/bec/ophyd_devices/-/commit/3396ff44d94955155c38a84a08880b93cb400cca))

* fix: fixed fupr axis_is_referenced ([`d72dc82`](https://gitlab.com/bec/ophyd_devices/-/commit/d72dc82264051e3e0a77527b06d29bd055e7bcdc))

* fix: fixed import; fixed file name ([`2ddc074`](https://gitlab.com/bec/ophyd_devices/-/commit/2ddc074e4fe9638bac77df5f3bbd2b1c4600814c))

* fix: fixed drive_to_limit ([`1aae1eb`](https://gitlab.com/bec/ophyd_devices/-/commit/1aae1eba12c05dfa5c4196edec3be488fa4f2b1e))

* fix: fixed drive_to_limit ([`3eea89a`](https://gitlab.com/bec/ophyd_devices/-/commit/3eea89acc5b2e18dd9d7b4a91e50590ca9702bba))

* fix: fixed id assignment ([`9b3139e`](https://gitlab.com/bec/ophyd_devices/-/commit/9b3139ecf106150170d2299303997d3dd8a97b4d))

* fix: fixed import for fgalil ([`3f76ef7`](https://gitlab.com/bec/ophyd_devices/-/commit/3f76ef76d736965b3257770efee1d2971afd90b3))

### Refactor

* refactor: cleanup and unifying galil classes ([`981b877`](https://gitlab.com/bec/ophyd_devices/-/commit/981b87703884299bf193ad73bf65a0e716091cd3))

### Test

* test: fixed controller init ([`89cf412`](https://gitlab.com/bec/ophyd_devices/-/commit/89cf4125516bc1b398d213c9f30ec115da5af0bf))


## v0.9.2 (2023-11-08)

### Refactor

* refactor: addressed comments from review; fixed docstring; add DeviceClassInitError ([`bda859e`](https://gitlab.com/bec/ophyd_devices/-/commit/bda859e93d171602e8fa7de1d88d8f2bfe22230f))

* refactor: rename infomsgmock and add docstrings ([`8a19ce1`](https://gitlab.com/bec/ophyd_devices/-/commit/8a19ce1508d7d00d4999aa89b5bb0537f973bc54))

* refactor: remove bluesky runengine dependency from re_test.py ([`57a4362`](https://gitlab.com/bec/ophyd_devices/-/commit/57a436261c46a3287320b7dfc0a29e16a9482f33))

* refactor: add min_readouttime, add complemented test cases; closes #11 #10 ([`ba01cf7`](https://gitlab.com/bec/ophyd_devices/-/commit/ba01cf7b2da25d40611f0a059493ac22f66a36c7))

* refactor: requests put and delete moved to separate functions ([`13d26c6`](https://gitlab.com/bec/ophyd_devices/-/commit/13d26c65379704291526b45397e8160668aec57a))

* refactor: add _send_requests_delete ([`4ce26b5`](https://gitlab.com/bec/ophyd_devices/-/commit/4ce26b5dd5e6bdb3ff9926ffcbce17a70afe98ae))

* refactor: refactored tests and eiger ([`d2cd6a4`](https://gitlab.com/bec/ophyd_devices/-/commit/d2cd6a442baced6ce8b6a7fa04a36290515fb87e))

* refactor: renaming ([`a80d13a`](https://gitlab.com/bec/ophyd_devices/-/commit/a80d13ae66e066b2fad6d8493b20731fb40f3677))

* refactor: class renaming and minor changes in variable names ([`5d02a13`](https://gitlab.com/bec/ophyd_devices/-/commit/5d02a13ad0fea7e07c41a2ece291df190328bc4c))

* refactor: fixed tests and mocks for refactor init ([`256aa41`](https://gitlab.com/bec/ophyd_devices/-/commit/256aa41690e19a165b3ee17119e380893c568a08))

### Test

* test: resolved problem after merge conflict ([`f32fdbc`](https://gitlab.com/bec/ophyd_devices/-/commit/f32fdbc845b445f1254207d7a2c1780ff6f958f1))

* test: fixed tests ([`cf4f195`](https://gitlab.com/bec/ophyd_devices/-/commit/cf4f195365aa3aa4bf0083a146cb1154b6feed58))

* test: fixed pilatus tests; closes #10 ([`188c832`](https://gitlab.com/bec/ophyd_devices/-/commit/188c8321cab0be96a2b5e435b6efbc4c39c9872d))

* test: fixed tests for eigerl; closes #11 ([`6b0b8de`](https://gitlab.com/bec/ophyd_devices/-/commit/6b0b8de8c0a869577cd233814bad48b9e1a806c4))

* test: fixed all eiger test with updated mock PV; closes #11 ([`cb49a2a`](https://gitlab.com/bec/ophyd_devices/-/commit/cb49a2a2055de471200d1a26bdb762676a199708))

* test: fix test to mock PV access ([`7e9abdb`](https://gitlab.com/bec/ophyd_devices/-/commit/7e9abdb32310037b115b12bf439bdbe5f3724948))

* test: test init filewriter ([`ee77013`](https://gitlab.com/bec/ophyd_devices/-/commit/ee77013ba29d705de3b1f499ea6c9256c3a6194b))

* test: add tests for close and stop filewriter ([`d3e8ece`](https://gitlab.com/bec/ophyd_devices/-/commit/d3e8ece029c0d672888cc43f05cf2258684de801))

* test: add first tests for pilatus ([`a02e0f0`](https://gitlab.com/bec/ophyd_devices/-/commit/a02e0f09b0f30e1b1ad73bf7f51b06c4bf9ab51c))

### Unknown

* Merge branch &#39;eiger_refactor&#39; into &#39;master&#39;

refactoring and tests for eiger and pilatus detectors

Closes #11 and #10

See merge request bec/ophyd_devices!36 ([`47d3a5a`](https://gitlab.com/bec/ophyd_devices/-/commit/47d3a5a65be9a00130a37e6f47f6bfd527a84c2d))

* Update .gitlab-ci.yml file ([`a14223c`](https://gitlab.com/bec/ophyd_devices/-/commit/a14223cc7c25d74ef8b575e90ad4743661c9137d))

* Merge branch &#39;master&#39; into &#39;eiger_refactor&#39;, resolve merge conflicts

# Conflicts:
#   ophyd_devices/epics/devices/eiger9m_csaxs.py
#   ophyd_devices/epics/devices/pilatus_csaxs.py ([`324f509`](https://gitlab.com/bec/ophyd_devices/-/commit/324f5091ec4e97b4323b048b679618d4d063a5e5))


## v0.9.1 (2023-11-02)

### Fix

* fix: fixed complete call for non-otf scans ([`9e6dc2a`](https://gitlab.com/bec/ophyd_devices/-/commit/9e6dc2a9f72c5615abd8bea1fcdea6719a35f1ad))


## v0.9.0 (2023-10-31)

### Feature

* feat: added file-based replay for xtreme ([`d25f92c`](https://gitlab.com/bec/ophyd_devices/-/commit/d25f92c6323cccea6de8471f4445b997cfab85a3))

### Fix

* fix: bugfixes after adding tests ([`72b8848`](https://gitlab.com/bec/ophyd_devices/-/commit/72b88482ca8b5104dbcf3e8a4e430497eb5fd5f8))

### Refactor

* refactor: remove test case without sim_mode from init, fix pending ([`70ba2ba`](https://gitlab.com/bec/ophyd_devices/-/commit/70ba2baedcfa64c81e5c9e70e297a02e275f57ee))

* refactor: generalize sim_mode ([`9dcf92a`](https://gitlab.com/bec/ophyd_devices/-/commit/9dcf92af006ba903f2aedc970f468e470b2dd05c))

* refactor: pilatus changes from stage and  minor changes for eiger and falcon ([`08e35df`](https://gitlab.com/bec/ophyd_devices/-/commit/08e35df0f2acb44b657318c0c499f149fbbadb8a))

* refactor: falcon, add trigger function ([`7f4082a`](https://gitlab.com/bec/ophyd_devices/-/commit/7f4082a6e9071c853c826d84aa5de1b2f46bb1a5))

* refactor: falcon, adapt to eiger refactoring ([`0dec88e`](https://gitlab.com/bec/ophyd_devices/-/commit/0dec88eda59e33de5763199ea6db2f98d8f71a2d))

* refactor: eiger, small refactoring of docs and names ([`0f5fe04`](https://gitlab.com/bec/ophyd_devices/-/commit/0f5fe04e59ae7054567b72fdfeec4dd8d3f96d78))

* refactor: eiger, small bugfix ([`583c61f`](https://gitlab.com/bec/ophyd_devices/-/commit/583c61ff411bb87349297c9163453a7ba8f5876c))

* refactor: eiger, refactoring done of unstage, stop and closing det and filewriter ([`d9606a4`](https://gitlab.com/bec/ophyd_devices/-/commit/d9606a47075847219a0e0a0bd63f7b533e1606fa))

* refactor: eiger, adapt publish file ([`7346f5d`](https://gitlab.com/bec/ophyd_devices/-/commit/7346f5d76aa82c2fe34b1d8df18f95cb37b664d7))

* refactor: eiger, fix _on_trigger ([`8eb60a9`](https://gitlab.com/bec/ophyd_devices/-/commit/8eb60a980aa209796a8c0f5d87de4c1624ef34ef))

* refactor: eiger, add documentation for stage ([`cbeb679`](https://gitlab.com/bec/ophyd_devices/-/commit/cbeb6794784a116a03f5a95858320965e6a86b2a))

* refactor: eiger, add trigger function ([`e6d05c9`](https://gitlab.com/bec/ophyd_devices/-/commit/e6d05c9d022a13fa93d2642ef8560a0c38a425ac))

* refactor: pilatus bugfix ([`7876510`](https://gitlab.com/bec/ophyd_devices/-/commit/78765100bada2afebea8f3b6c266859d53af341d))

* refactor: prep detector and filewriter for falcon; stage refactored ([`4c120b0`](https://gitlab.com/bec/ophyd_devices/-/commit/4c120b0d4f4f1bd6a5a2d55a96d8ee7b85eb97a4))

* refactor: small change on eiger arm ([`c2e4bbc`](https://gitlab.com/bec/ophyd_devices/-/commit/c2e4bbc4067427113f0a1ec1ede69a2c84a381e5))

* refactor: reworked arm to ([`ce8616a`](https://gitlab.com/bec/ophyd_devices/-/commit/ce8616a9798f191659e8dd1afa52d9038e4cff84))

* refactor: eiger9m stage function, refactoring ([`6dae767`](https://gitlab.com/bec/ophyd_devices/-/commit/6dae767c5e21cd1e6ce3e045e6d99bf984098c2c))

* refactor: change _init for pilatus ([`c5951b3`](https://gitlab.com/bec/ophyd_devices/-/commit/c5951b3c5bea572a8962d920c780870a78e98d39))

* refactor: change _init for falcon detector ([`6f49be4`](https://gitlab.com/bec/ophyd_devices/-/commit/6f49be47758a269e8f5f8a8ca9661f8e79dfafda))

* refactor: add comment to loggers in _update_std_cfg ([`4c6e99a`](https://gitlab.com/bec/ophyd_devices/-/commit/4c6e99af118c0987a6b01c28cce503ecfa63d0a5))

* refactor: change _init filewriter and detector for eiger9m ([`920d7bb`](https://gitlab.com/bec/ophyd_devices/-/commit/920d7bb2b108e8f48d8b28ae3b5e35fcb9113e05))

* refactor: add _init function to all classes ([`55d20a0`](https://gitlab.com/bec/ophyd_devices/-/commit/55d20a0ed056b0f2855a89b14672d1ee8f3a99a7))

* refactor: add documentation, clean up init function and unify classes ([`22e63c4`](https://gitlab.com/bec/ophyd_devices/-/commit/22e63c4976eb2c19acc3234ccb8296dbed1b3d22))

* refactor: add docstrings and clean cam classes; dxp and hdf for falcon ([`702b212`](https://gitlab.com/bec/ophyd_devices/-/commit/702b212f50629d9ccf36071d38cc001fc155c1da))

* refactor: add docstrings to errors ([`88d3b92`](https://gitlab.com/bec/ophyd_devices/-/commit/88d3b92b33c9076311a3ff4ce012de94cf6de758))

* refactor: cleanup import for detectors ([`217c27b`](https://gitlab.com/bec/ophyd_devices/-/commit/217c27bfdb38e7b1141565317b69c4955d5b6df4))

### Test

* test: add tests for eiger ([`78ba00c`](https://gitlab.com/bec/ophyd_devices/-/commit/78ba00ce14490ac38bb0439737faced6ae7282a3))

### Unknown

* Merge branch &#39;xtreme_sim&#39; into &#39;master&#39;

feat: added file-based replay for xtreme

See merge request bec/ophyd_devices!37 ([`de7df4f`](https://gitlab.com/bec/ophyd_devices/-/commit/de7df4f0c303176f911b2a6dacfae8dafceae0a7))

* Merge branch &#39;csaxs_detectors&#39; into &#39;master&#39;

Csaxs detectors

Closes #3

See merge request bec/ophyd_devices!35 ([`8bf5b76`](https://gitlab.com/bec/ophyd_devices/-/commit/8bf5b764a656a6870853b38a9bbbfc4f02289866))


## v0.8.1 (2023-09-27)

### Fix

* fix: fixed formatting ([`48445e8`](https://gitlab.com/bec/ophyd_devices/-/commit/48445e8b61031496712bfdb262a944c6d058029f))

* fix: add ndarraymode and formatting ([`712674e`](https://gitlab.com/bec/ophyd_devices/-/commit/712674e4b8f662b3081d21ed7c2d053260a728e6))

* fix: online changes e21536 ([`0372f6f`](https://gitlab.com/bec/ophyd_devices/-/commit/0372f6f726f14b3728921ca498634b4c4ad5e0cb))


## v0.8.0 (2023-09-15)

### Feature

* feat: first draft for Epics sequencer class ([`c418b87`](https://gitlab.com/bec/ophyd_devices/-/commit/c418b87ad623f32368197a247e83fc99444dc071))

### Fix

* fix: format online changes via black ([`f221f9e`](https://gitlab.com/bec/ophyd_devices/-/commit/f221f9e88ee40e7e24a572d7f12e80a98d70f553))

* fix: minor changes on the sgalil controller ([`b6bf7bc`](https://gitlab.com/bec/ophyd_devices/-/commit/b6bf7bc9b3b5e4e581051bec2822d329da432b50))

* fix: small changes in epics_motor_ex, potentially only comments ([`f9f9ed5`](https://gitlab.com/bec/ophyd_devices/-/commit/f9f9ed5e23d7478c5661806b67368c9e4711c9f5))

* fix: online changes in e20639 for mcs card operating full 2D grid ([`67115a0`](https://gitlab.com/bec/ophyd_devices/-/commit/67115a0658b1122881332e90a3ae9fa2780ca129))

* fix: online changes e20643 ([`0bf308a`](https://gitlab.com/bec/ophyd_devices/-/commit/0bf308a13d55f795c6537c66972a80d66ec081dd))

* fix: online changes sgalil e20636 ([`592ddfe`](https://gitlab.com/bec/ophyd_devices/-/commit/592ddfe6da87af467cfe507b46d423ccb03c21dd))

* fix: online changes pilatus_2 e20636 ([`76f88ef`](https://gitlab.com/bec/ophyd_devices/-/commit/76f88efa31b1c599a7ee8233a7721aed30e6a611))

* fix: online changes e20636 mcs ([`bb12181`](https://gitlab.com/bec/ophyd_devices/-/commit/bb12181020b8ebf16c13d13e7fabc9ad8cc26909))

* fix: online changes e20636 falcon ([`7939045`](https://gitlab.com/bec/ophyd_devices/-/commit/793904566dfb4bd1a22ac349f270a5ea2c7bc75f))

* fix: online changes eiger9m ([`e299c71`](https://gitlab.com/bec/ophyd_devices/-/commit/e299c71ec060f53563529f64ab43c6906efd938c))

* fix: online changes DDG ([`c261fbb`](https://gitlab.com/bec/ophyd_devices/-/commit/c261fbb55a3379f17cc7a14e915c6c5ec309281b))


## v0.7.0 (2023-09-07)

### Feature

* feat: add timeout functionality to ophyd devices ([`c80d9ab`](https://gitlab.com/bec/ophyd_devices/-/commit/c80d9ab29bcc85a46b59f3be8fb86b990c3ed299))


## v0.6.0 (2023-09-07)

### Feature

* feat: add falcon and progress bar option to devices ([`3bab432`](https://gitlab.com/bec/ophyd_devices/-/commit/3bab432a2f01e3a62811e13b9143d67da495fbb8))

* feat: extension for epics motors from xiaoqiang ([`057d93a`](https://gitlab.com/bec/ophyd_devices/-/commit/057d93ab60d2872b2b029bdc7b6dcab35a6a21a5))

### Fix

* fix: online changes ([`3a12697`](https://gitlab.com/bec/ophyd_devices/-/commit/3a126976cd7cfb3f294556110d77249da6fbc99d))

* fix: adjusted __init__ for epics motor extension ([`ac8b96b`](https://gitlab.com/bec/ophyd_devices/-/commit/ac8b96b9ba76ba52920aeca7486ca9046e07326c))

* fix: changes for sgalil grid scan from BEC ([`3e594b5`](https://gitlab.com/bec/ophyd_devices/-/commit/3e594b5e0461d43431e0103cb713bcd9fd22ca1c))

* fix: working acquire, line and grid scan using mcs, ddg and eiger9m ([`58caf2d`](https://gitlab.com/bec/ophyd_devices/-/commit/58caf2ddd3416deaace82b6e321fc0753771b282))

* fix: DDG logic to wait for burst in trigger ([`5ce6fbc`](https://gitlab.com/bec/ophyd_devices/-/commit/5ce6fbcbb92d2fafb6cfcb4bb7b1f5ee616140b8))

* fix: online changes SAXS ([`911c8a2`](https://gitlab.com/bec/ophyd_devices/-/commit/911c8a2438c9cdf1ca2a9685e1dbbbf4a1913f5c))

* fix: working mcs readout ([`8ad3eb2`](https://gitlab.com/bec/ophyd_devices/-/commit/8ad3eb29b79a0a8a742d1bc319cfedf60fcc150f))

* fix: fix ddg code ([`b3237ce`](https://gitlab.com/bec/ophyd_devices/-/commit/b3237ceda5468058e294da4a3e608c4344e582dc))

* fix: bugfix online fixes ([`ba9cb77`](https://gitlab.com/bec/ophyd_devices/-/commit/ba9cb77ed9b0d1a7e0f744558360c90f393b6f08))

* fix: bugfix in delaygenerators ([`2dd8f25`](https://gitlab.com/bec/ophyd_devices/-/commit/2dd8f25c8727759a8cf98a0abee87e379c9307d7))

* fix: online changes to all devices in preparation for beamtime ([`c0b3418`](https://gitlab.com/bec/ophyd_devices/-/commit/c0b34183661b11c39d65eb117c3670a714f9eb5c))

### Unknown

* Merge branch &#39;csaxs_detector_integration&#39; into &#39;master&#39;

Csaxs detector integration

See merge request bec/ophyd_devices!34 ([`4902964`](https://gitlab.com/bec/ophyd_devices/-/commit/49029649aa4b1bd06f157b7c27a3127d98802314))

* Merge branch &#39;master&#39; into &#39;csaxs_detector_integration&#39;

# Conflicts:
#   setup.py ([`0a1ee98`](https://gitlab.com/bec/ophyd_devices/-/commit/0a1ee98f169f3c221a78fae50f336142d2e7477d))


## v0.5.0 (2023-09-01)

### Feature

* feat: added derived signals for xtreme ([`1276e1d`](https://gitlab.com/bec/ophyd_devices/-/commit/1276e1d0db44315d8e95cdf19ec32d68c7426fc8))

* feat: add mcs_readout_monitor and stream ([`ab22056`](https://gitlab.com/bec/ophyd_devices/-/commit/ab220562fc1eac3bcffff01fd92085445dd774e7))

* feat: add ConfigSignal to bec_utils ([`ac6de9d`](https://gitlab.com/bec/ophyd_devices/-/commit/ac6de9da54444dda21820591dd8e3ad098d3f0ac))

* feat: adding mcs card to repository ([`96a131d`](https://gitlab.com/bec/ophyd_devices/-/commit/96a131d3743c8d62aaac309868ac1309d83fe9aa))

* feat: add bec_utils to repo for generic functions ([`86e93af`](https://gitlab.com/bec/ophyd_devices/-/commit/86e93afe28fc91b5c0a773c489d99cf272c52878))

* feat: add bec_scaninfo_mixin to repo ([`01c824e`](https://gitlab.com/bec/ophyd_devices/-/commit/01c824ecead89a1c83cefacff53bf9f76b02d423))

* feat: bec_scaninfo_mixin class for scaninfo ([`49f95e0`](https://gitlab.com/bec/ophyd_devices/-/commit/49f95e04765e2e4035c030a35272bdb7f06f8d8f))

* feat: add eiger9m csaxs ([`f3e4575`](https://gitlab.com/bec/ophyd_devices/-/commit/f3e4575359994c134e1b207915fadb9f8f92e4d9))

* feat: add mcs ophyd device ([`448890a`](https://gitlab.com/bec/ophyd_devices/-/commit/448890ab27ba1bfeb24870d792c498b96aa7cc47))

* feat: added falcon ophyd device to repo ([`88b238a`](https://gitlab.com/bec/ophyd_devices/-/commit/88b238ac13856ed1593dd01b9d2f7a762ca00111))

### Fix

* fix: added pyepics dependency ([`66d283b`](https://gitlab.com/bec/ophyd_devices/-/commit/66d283baeb30da261d0f27e73bca4c9b90d0cadd))

* fix: online changes ([`b6101cc`](https://gitlab.com/bec/ophyd_devices/-/commit/b6101cced24b8b37a3363efa5554a627fdc875b1))

* fix: mcs working ([`08efb64`](https://gitlab.com/bec/ophyd_devices/-/commit/08efb6405bc615b40855288067c1e811f1471423))

* fix: add std_daq_client and pyepics to setup ([`5d86382`](https://gitlab.com/bec/ophyd_devices/-/commit/5d86382d80c033fb442afef74e95a19952cd5937))

* fix: bugfix for polarity ([`fe404bf`](https://gitlab.com/bec/ophyd_devices/-/commit/fe404bff9c960ff8a3f56686b24310d056ad4eda))

* fix: test function ([`2dc3290`](https://gitlab.com/bec/ophyd_devices/-/commit/2dc3290787a2c2cc79141b9d1da3a805b2c67ccd))

* fix: online changes to integrate devices in BEC ([`fbfa562`](https://gitlab.com/bec/ophyd_devices/-/commit/fbfa562713adaf374dfaf67ebf30cbd1895dd428))

* fix: fixed stop command ([`d694f65`](https://gitlab.com/bec/ophyd_devices/-/commit/d694f6594d0bd81fd62be570142bc2f6b19cf6f4))

* fix: running ophyd for mcs card, pending fix mcs_read_all epics channel ([`7c45682`](https://gitlab.com/bec/ophyd_devices/-/commit/7c45682367c363207257fff7b6ce53ffee1449df))

* fix: bec_utils mixin ([`ed0ef33`](https://gitlab.com/bec/ophyd_devices/-/commit/ed0ef338eb606977993d45c98421ebde0f477927))

* fix: sgalil scan ([`cc6c8cb`](https://gitlab.com/bec/ophyd_devices/-/commit/cc6c8cb41bc6e3388a580adeee0af8a1c7dbca27))

* fix: pil300k device, pending readout ([`b91f8db`](https://gitlab.com/bec/ophyd_devices/-/commit/b91f8dbc6854cf46d1d504610855d50563a8df36))

* fix: adjusted delaygen ([`17347ac`](https://gitlab.com/bec/ophyd_devices/-/commit/17347ac93032c9b57247d9f565f638340a9973af))

* fix: add readout time to mock scaninfo ([`8dda7f3`](https://gitlab.com/bec/ophyd_devices/-/commit/8dda7f30c1e797287ddf52f6448604c1052ce3ce))

* fix: add flyscan option ([`3258e3a`](https://gitlab.com/bec/ophyd_devices/-/commit/3258e3a1c7e799c4d718dc9cb7f5abfcf87e59f3))

* fix: stepscan logic implemented in ddg ([`c365b8e`](https://gitlab.com/bec/ophyd_devices/-/commit/c365b8e9543ac0eca3bc3da34f662422e7daeef7))

* fix: use bec_scaninfo_mixin in ophyd class ([`6ee819d`](https://gitlab.com/bec/ophyd_devices/-/commit/6ee819de53d39d8d14a4c4df29b0781f83f930ec))

* fix: add status update std_daq ([`39142ff`](https://gitlab.com/bec/ophyd_devices/-/commit/39142ffc92440916b6c68beb260222f4dd8a0548))

* fix: mcs updates ([`14ca550`](https://gitlab.com/bec/ophyd_devices/-/commit/14ca550af143cdca9237271311b9c5ea280d7809))

* fix: falcon updates ([`b122de6`](https://gitlab.com/bec/ophyd_devices/-/commit/b122de69acfd88d82eaba85534840e7fae21b718))

* fix: add bec producer message to stage ([`83c395c`](https://gitlab.com/bec/ophyd_devices/-/commit/83c395cf3511bb56d0f58b75bb5c00c5bc00992f))

* fix: add initialization functionality ([`41e0e40`](https://gitlab.com/bec/ophyd_devices/-/commit/41e0e40bc70d4b4547d331cf237feeaa39b5d721))

* fix: adjust ophyd class layout ([`eccacf1`](https://gitlab.com/bec/ophyd_devices/-/commit/eccacf169bf0a265fac1e20e8fe86af6277a9d4a))

* fix: stage works again, unstage not yet ([`96d746c`](https://gitlab.com/bec/ophyd_devices/-/commit/96d746c2860221d336a755535e920ea0af8375b9))

### Refactor

* refactor: online changes ([`2786791`](https://gitlab.com/bec/ophyd_devices/-/commit/278679125ee50bd1de4daf3c4aa08d2afaa43c20))

* refactor: eiger9m updates, operation in gating mode ([`053f1d9`](https://gitlab.com/bec/ophyd_devices/-/commit/053f1d91814905fa3fa20a79f9a986ac19942c7b))

* refactor: updated scaninfo mix ([`7de0ff2`](https://gitlab.com/bec/ophyd_devices/-/commit/7de0ff236c4afe14dbe16540653183af25353e36))

* refactor: bugfix ([`e8f2f82`](https://gitlab.com/bec/ophyd_devices/-/commit/e8f2f8203934381898d05709e06cd32e66692914))

* refactor: remove some unnecessary test code ([`c969927`](https://gitlab.com/bec/ophyd_devices/-/commit/c96992798d291773e202caabf421000c74fa79d3))

* refactor: class refactoring, with other 2 detectors ([`fb8619d`](https://gitlab.com/bec/ophyd_devices/-/commit/fb8619d0473dbd16ed147503662f7372b3b5d638))

* refactor: class refactoring, pending change to SlsDetectorCam ([`b1150c4`](https://gitlab.com/bec/ophyd_devices/-/commit/b1150c41fe4199be91ed164e089db5379a8f0435))

* refactor: refactoring of eiger9m class, alsmost compatible with pilatus ([`287c667`](https://gitlab.com/bec/ophyd_devices/-/commit/287c667621582506dd85c02c022a4aeddba1fb7b))


## v0.4.0 (2023-08-18)

### Feature

* feat: add pilatus_2 ophyd class to repository ([`9476fde`](https://gitlab.com/bec/ophyd_devices/-/commit/9476fde13ab427eba61bd7a5776e8b71aca92b0a))

### Fix

* fix: simple end-to-end test works at beamline ([`28b91ee`](https://gitlab.com/bec/ophyd_devices/-/commit/28b91eeda22af03c3709861ff7fb045fe5b2cf9b))

### Unknown

* Merge branch &#39;pilatus_2&#39; into &#39;master&#39;

Pilatus 2

See merge request bec/ophyd_devices!33 ([`33e317c`](https://gitlab.com/bec/ophyd_devices/-/commit/33e317c01aa6596b2e9aa686ec3cd8116fac2fa2))


## v0.3.0 (2023-08-17)

### Documentation

* docs: details on encoder reading of sgalilg controller ([`e0d93a1`](https://gitlab.com/bec/ophyd_devices/-/commit/e0d93a1561ca9203aaf1b5aaf2d6a0dec9f0689e))

* docs: documentation update ([`5d9fb98`](https://gitlab.com/bec/ophyd_devices/-/commit/5d9fb983301a5513a1fb9a9a3ed56537626848ee))

* docs: add documentation for delay generator ([`7ad423b`](https://gitlab.com/bec/ophyd_devices/-/commit/7ad423b36434ad05d2f9b46824b6d850f55861f2))

* docs: updated documentation ([`eb3e90e`](https://gitlab.com/bec/ophyd_devices/-/commit/eb3e90e8a25834cbba5692eda34013f63295737f))

### Feature

* feat: add continous readout of encoder while scanning ([`69fdeb1`](https://gitlab.com/bec/ophyd_devices/-/commit/69fdeb1e965095147dc18dc0abfe0b7962ba8b38))

* feat: adding io access to delay pairs ([`4513110`](https://gitlab.com/bec/ophyd_devices/-/commit/451311027a50909247aaf99571269761b68dcb27))

* feat: read_encoder_position, does not run yet ([`9cb8890`](https://gitlab.com/bec/ophyd_devices/-/commit/9cb889003933bf296b9dc1d586f7aad50421d0cf))

* feat: add readout_encoder_position to sgalil controller ([`a94c12a`](https://gitlab.com/bec/ophyd_devices/-/commit/a94c12ac125211f16dfcda292985d883e770b44b))

### Fix

* fix: bugfix on delaystatic and dummypositioner ([`416d781`](https://gitlab.com/bec/ophyd_devices/-/commit/416d781d16f46513d6c84f4cf3108e61b4a37bc2))

* fix: bugfix burstenable and burstdisalbe ([`f3866a2`](https://gitlab.com/bec/ophyd_devices/-/commit/f3866a29e9b7952f6b416758a067bfa2940ca945))

* fix: limit handling flyscan and error handling axes ref ([`a620e6c`](https://gitlab.com/bec/ophyd_devices/-/commit/a620e6cf5077272d306fc7636e5a8eee1741068f))

* fix: bugfix stage/unstage ([`39220f2`](https://gitlab.com/bec/ophyd_devices/-/commit/39220f20ea7f81825fe73fbc37592462f2e02a6e))

* fix: small fixes to fly_grid_scan ([`87ac0ed`](https://gitlab.com/bec/ophyd_devices/-/commit/87ac0edf999eb2bc589e69807ffc6e980241a19f))

### Refactor

* refactor: fix format sgalil ([`b267284`](https://gitlab.com/bec/ophyd_devices/-/commit/b267284e977c55babfbda4e7a6c302b8785efe8c))

* refactor: fix formatting DDG ([`0d74b34`](https://gitlab.com/bec/ophyd_devices/-/commit/0d74b34121696922cf4caa647d5cba10f7d29452))

* refactor: small bugfix and TODO comments ([`7782d5f`](https://gitlab.com/bec/ophyd_devices/-/commit/7782d5faabd897803f8f4b4172a4e2b5d297a346))

* refactor: bugfix of sgalil flyscans ([`291e9ba`](https://gitlab.com/bec/ophyd_devices/-/commit/291e9ba04b4e899536d1a5a69c123df7decfdb13))

* refactor: small adjustments to fly scans ([`04b4bd5`](https://gitlab.com/bec/ophyd_devices/-/commit/04b4bd509c3a10124f527194cc1c4d5756a38328))

### Unknown

* Merge branch &#39;sgalil_flyscan&#39; into &#39;master&#39;

Sgalil flyscan

See merge request bec/ophyd_devices!32 ([`2847371`](https://gitlab.com/bec/ophyd_devices/-/commit/284737163a9048ad8db8e38bea410211ed5ac97d))

* doc: add sgalil controller file &#39;sgalil.dmc&#39; to folder ([`bb9af77`](https://gitlab.com/bec/ophyd_devices/-/commit/bb9af7732e1fbc2d02379f336dc9956a5c655ce3))

* add grid scan and sgalil_reference to ophyd class ([`6b5d829`](https://gitlab.com/bec/ophyd_devices/-/commit/6b5d829960e94eff10ceb92af53df1667345dce4))


## v0.2.1 (2023-07-21)

### Ci

* ci: fixed python-semantic-release version to 7.* ([`1c66d5a`](https://gitlab.com/bec/ophyd_devices/-/commit/1c66d5a2c872044a27d4e9eac176ea01a897fd17))

### Fix

* fix: fixed sim readback timestamp ([`7a47134`](https://gitlab.com/bec/ophyd_devices/-/commit/7a47134a6b8726c0389d8e631028af8f8be54cc2))


## v0.2.0 (2023-07-04)

### Build

* build: added missing dependencies ([`e226dbe`](https://gitlab.com/bec/ophyd_devices/-/commit/e226dbe3c3164664d36a385ec60266a867ac25d6))

### Documentation

* docs: improved readme ([`781affa`](https://gitlab.com/bec/ophyd_devices/-/commit/781affacb5bc0c204cb7501b629027e66e47a0b1))

### Feature

* feat: add DDG and prel. sgalil devices ([`00c5501`](https://gitlab.com/bec/ophyd_devices/-/commit/00c55016e789f184ddb5c2474eb251fd62470e04))

### Fix

* fix: formatting DDG ([`4e10a96`](https://gitlab.com/bec/ophyd_devices/-/commit/4e10a969c8625bc48d6db99fc7f5be9d46807df1))

* fix: bec_lib.core import ([`25c7ce0`](https://gitlab.com/bec/ophyd_devices/-/commit/25c7ce04e3c2a5c2730ce5aa079f37081d7289cd))

* fix: recover galil_ophyd from master ([`5f655ca`](https://gitlab.com/bec/ophyd_devices/-/commit/5f655caf29fe9941ba597fdaee6c4b2a20625ca8))

* fix: fixed galil sgalil_ophyd confusion from former commit ([`f488f0b`](https://gitlab.com/bec/ophyd_devices/-/commit/f488f0b21cbe5addd6bd5c4c54aa00eeffde0648))

### Unknown

* Merge branch &#39;fix-delaygen&#39; into &#39;sgalil_integration_cSAXS&#39;

Delaygen pseudoaxis fix

See merge request bec/ophyd_devices!30 ([`913188f`](https://gitlab.com/bec/ophyd_devices/-/commit/913188fd8596f3f490af55d0887a44ffd5e973e5))

* test

common

sgalil integration tests ([`003cf9d`](https://gitlab.com/bec/ophyd_devices/-/commit/003cf9d94f0f7e009e575fe116671cf29e21bdd0))

* Code formatting ([`519859c`](https://gitlab.com/bec/ophyd_devices/-/commit/519859caacb1ca674f0733b93dbfba513f63b597))

* Fixed but to remove Thread Signal from Axis movements - working motions on samx/samy ([`26f834b`](https://gitlab.com/bec/ophyd_devices/-/commit/26f834b9333aead64c7d2ee1b89a437432d0ee45))

* SGalil ophyd device, samx integration still pending ([`822b6b1`](https://gitlab.com/bec/ophyd_devices/-/commit/822b6b18f67a591430c9bc0dc93a8daffae435cb))


## v0.1.0 (2023-06-28)

### Ci

* ci: fixed typo ([`2b0ee22`](https://gitlab.com/bec/ophyd_devices/-/commit/2b0ee223bb4ed50036554875862f0f166cce1eb9))

* ci: added semver ([`daa5d9e`](https://gitlab.com/bec/ophyd_devices/-/commit/daa5d9e822eaec6afb5817348db65d9a2ac1ead9))

* ci: added semver ([`9c0bd1e`](https://gitlab.com/bec/ophyd_devices/-/commit/9c0bd1e1946eed2b14146c690b3e63825bcc77fe))

* ci: added additional tests for other python versions ([`d92c7ca`](https://gitlab.com/bec/ophyd_devices/-/commit/d92c7cadcc4764e35b23a8ed4fe93a21ef9f9ae2))

* ci: cleanup ([`56e5d5d`](https://gitlab.com/bec/ophyd_devices/-/commit/56e5d5d61e8dbf5d6e7a7ce60c91c8449ab631f8))

* ci: moved to morgana harbor ([`77845a4`](https://gitlab.com/bec/ophyd_devices/-/commit/77845a4042bb9fcc138f5bf8f0cb028aaaa3dad9))

### Feature

* feat: added dev install to setup.py ([`412a0e4`](https://gitlab.com/bec/ophyd_devices/-/commit/412a0e4480a0a5e7d2921cef529ef8aceda90bb7))

* feat: added pylintrc ([`020459e`](https://gitlab.com/bec/ophyd_devices/-/commit/020459ed902ab226d1cea659f6626d7a887cb99a))

* feat: added sls detector ([`63ece90`](https://gitlab.com/bec/ophyd_devices/-/commit/63ece902a387c2c4a5944eb766f6a94e58b48755))

* feat: added missing epics devices for xtreme ([`2bf57ed`](https://gitlab.com/bec/ophyd_devices/-/commit/2bf57ed43331ae138e211f14ece8cfd9a1b79046))

* feat: added otf sim ([`f351320`](https://gitlab.com/bec/ophyd_devices/-/commit/f3513207d92e077a8a5e919952c3682250e5afa1))

* feat: added nested object ([`059977d`](https://gitlab.com/bec/ophyd_devices/-/commit/059977db1f160c8a21dccf845967dc265d34aa6a))

* feat: added test functions for rpc calls ([`5648ea2`](https://gitlab.com/bec/ophyd_devices/-/commit/5648ea2d15c1994b34353fe51e83bf5d7a634520))

### Fix

* fix: fixed gitignore file ([`598d72b`](https://gitlab.com/bec/ophyd_devices/-/commit/598d72b4ec9e9b1c5b100321d93370bf4b9ed426))

* fix: adjustments for new bec_lib ([`eee8856`](https://gitlab.com/bec/ophyd_devices/-/commit/eee88565655eaab62ec66f018dcbe02d09594716))

* fix: moved to new bec_client_lib structure ([`35d5ec8`](https://gitlab.com/bec/ophyd_devices/-/commit/35d5ec8e9d94c0a845b852b6cd8182897464fca8))

* fix: fixed harmonic signal ([`60c7878`](https://gitlab.com/bec/ophyd_devices/-/commit/60c7878dad4839531b6e055eb1be94d696c6e2a7))

* fix: fixed pv name for sample manipulator ([`41929a5`](https://gitlab.com/bec/ophyd_devices/-/commit/41929a59ab26b7502bef38f4d72c846d136bab03))

* fix: added missing file ([`5a7f8ac`](https://gitlab.com/bec/ophyd_devices/-/commit/5a7f8ac40781f5ccf48b6ca94a569665592dc15b))

* fix: fixed x07ma devices ([`959789b`](https://gitlab.com/bec/ophyd_devices/-/commit/959789b26f21f1375d36db91dc6d5f9ac32a677d))

* fix: online bug fixes ([`bf5f981`](https://gitlab.com/bec/ophyd_devices/-/commit/bf5f981f52f063df687042567b8bc6e40cdb1d85))

* fix: fixed rt_lamni hints ([`2610542`](https://gitlab.com/bec/ophyd_devices/-/commit/26105421247cf5ea2b145e51525db8326b02852e))

* fix: fixed rt_lamni for new hinted flyers ([`419ce9d`](https://gitlab.com/bec/ophyd_devices/-/commit/419ce9dfdaf3ebdb30a2ece25f37a8ebe1a53572))

* fix: moved to hint structure for flyers ([`fc17741`](https://gitlab.com/bec/ophyd_devices/-/commit/fc17741d2ac46632e3adb96814d2c41e8000dcc6))

* fix: added default_sub ([`9b9d3c4`](https://gitlab.com/bec/ophyd_devices/-/commit/9b9d3c4d7fc629c42f71b527d86b6be0bf4524bc))

* fix: minor adjustments to comply with the openapi schema; set default onFailure to retry ([`cdb3fef`](https://gitlab.com/bec/ophyd_devices/-/commit/cdb3feff6013516e52d77b958f4c39296edee7bf))

* fix: fixed timestamp update for bpm4i ([`dacfd1c`](https://gitlab.com/bec/ophyd_devices/-/commit/dacfd1c39b7966993080774c6154f856070c8b27))

* fix: fixed bpm4i for subs ([`4c6b7f8`](https://gitlab.com/bec/ophyd_devices/-/commit/4c6b7f87219dbf8f369df9a65e4e8cec278d0568))

* fix: formatter ([`9e938f3`](https://gitlab.com/bec/ophyd_devices/-/commit/9e938f3745106fb62e176d344aee6ee5c1fffa90))

* fix: online fixes ([`1395044`](https://gitlab.com/bec/ophyd_devices/-/commit/1395044432dbf9235adce0fd5d46c019ea5db2db))

* fix: removed matplotlib dependency ([`b5611d2`](https://gitlab.com/bec/ophyd_devices/-/commit/b5611d20c81cfa07f7451aaed2b9146e8bbca960))

* fix: fixed epics import ([`ec3a93f`](https://gitlab.com/bec/ophyd_devices/-/commit/ec3a93f96e3e07e5ac88d40fe1858915f667e64c))

### Refactor

* refactor: prep for semver ([`c5931a4`](https://gitlab.com/bec/ophyd_devices/-/commit/c5931a4010d49fc3770311433f111f2ae7cc94c2))

* refactor: prep for semver ([`428a13c`](https://gitlab.com/bec/ophyd_devices/-/commit/428a13ceeb65fe32e2c2028e11cdebf6cf489331))

* refactor: cleanup ([`0ae9367`](https://gitlab.com/bec/ophyd_devices/-/commit/0ae93670142947d25ea1a88cbd9eed4c542b4139))

* refactor: formatting ([`872d845`](https://gitlab.com/bec/ophyd_devices/-/commit/872d845516abfef6face42fdcb30c102cd43d993))

* refactor: formatter ([`f2d2a0a`](https://gitlab.com/bec/ophyd_devices/-/commit/f2d2a0ab4569985972ac1010cdd00b61f54ed34a))

* refactor: fixed black formatting ([`db32219`](https://gitlab.com/bec/ophyd_devices/-/commit/db32219bd34a64052703408f335f1725aeab0868))

* refactor: cleanup ([`7bd602c`](https://gitlab.com/bec/ophyd_devices/-/commit/7bd602c49c2a87ae465c5421b46438448f10305c))

### Unknown

* Merge branch &#39;repo_cleanup&#39; into &#39;master&#39;

ci: added additional tests for other python versions

See merge request bec/ophyd_devices!29 ([`f4d39e7`](https://gitlab.com/bec/ophyd_devices/-/commit/f4d39e7328bbcb1cf3d82b092801bcc2497eaf19))

* Merge branch &#39;master&#39; into repo_cleanup ([`aa96e0f`](https://gitlab.com/bec/ophyd_devices/-/commit/aa96e0fb370d8ad3c005318cf4c0b2c09866c034))

* Merge branch &#39;repo_cleanup&#39; into &#39;master&#39;

refactor: cleanup

See merge request bec/ophyd_devices!28 ([`1ca809c`](https://gitlab.com/bec/ophyd_devices/-/commit/1ca809c884c70247b72b8c65b378154b32949098))

* Merge branch &#39;repo_cleanup&#39; into &#39;master&#39;

Repo cleanup

See merge request bec/ophyd_devices!27 ([`cc52364`](https://gitlab.com/bec/ophyd_devices/-/commit/cc523645f03cb6e15276dbb8ab0db488a7e1e097))

* Merge branch &#39;bec_lib_renaming&#39; into &#39;master&#39;

fix: adjustments for new bec_lib

See merge request bec/ophyd_devices!26 ([`4541868`](https://gitlab.com/bec/ophyd_devices/-/commit/4541868f2755fc28e01bcb55a961b93f80c8ab79))

* Delaygen pseudoaxis fix ([`04cb9e6`](https://gitlab.com/bec/ophyd_devices/-/commit/04cb9e6044001e6efc8df8e652724dd3a7fcc786))

* Merge branch &#39;bec_utils_update&#39; into &#39;master&#39;

fix: moved to new bec_client_lib structure

See merge request bec/ophyd_devices!25 ([`422f963`](https://gitlab.com/bec/ophyd_devices/-/commit/422f963b4c70cf4871f6efcf5491b68344da6804))

* Update .gitlab-ci.yml ([`f86024e`](https://gitlab.com/bec/ophyd_devices/-/commit/f86024e22f72c4963f57c40b4b34fe6553dcf34e))

* Merge branch &#39;xtreme_keithley&#39; into &#39;master&#39;

added more devices for xtreme

See merge request bec/ophyd_devices!24 ([`76b29fb`](https://gitlab.com/bec/ophyd_devices/-/commit/76b29fb8923a6327b1afb43b642fcb95b58e553a))

* added more devices for xtreme ([`67b7b85`](https://gitlab.com/bec/ophyd_devices/-/commit/67b7b8524e5b4a677cefb453c7b42045e8c25922))

* Merge branch &#39;x07ma-workaround&#39; into &#39;master&#39;

X07ma workaround

See merge request bec/ophyd_devices!23 ([`1e44c71`](https://gitlab.com/bec/ophyd_devices/-/commit/1e44c71c55bdebdd0f5cd605de5ec8a3e77f193b))

* Merge branch &#39;x07ma&#39; into &#39;x07ma-workaround&#39;

workaround when magnet setpoint = readback

See merge request bec/ophyd_devices!22 ([`dc8d9ad`](https://gitlab.com/bec/ophyd_devices/-/commit/dc8d9ad412c3337c672d6f757ba720b83559e791))

* workaround when magnet setpoint = readback ([`c5b5b64`](https://gitlab.com/bec/ophyd_devices/-/commit/c5b5b643565c8f10487fffd6e8d691dac9231bf7))

* Merge branch &#39;xtreme_devices_update&#39; into &#39;master&#39;

fix: fixed harmonic signal

See merge request bec/ophyd_devices!21 ([`c8c642c`](https://gitlab.com/bec/ophyd_devices/-/commit/c8c642c8bc9087306750c6f61b3e331664e77e38))

* Merge branch &#39;xtreme_devices_update&#39; into &#39;master&#39;

fix: fixed pv name for sample manipulator

See merge request bec/ophyd_devices!20 ([`4c7b9c0`](https://gitlab.com/bec/ophyd_devices/-/commit/4c7b9c0c0bccc31e11cf0b90656c7baeb60b0ebf))

* Merge branch &#39;xtreme_devices_update&#39; into &#39;master&#39;

Xtreme devices update

See merge request bec/ophyd_devices!19 ([`9fcdbfb`](https://gitlab.com/bec/ophyd_devices/-/commit/9fcdbfb26c264033c6b05974960294f5d6eb83a5))

* Merge branch &#39;xtreme_update&#39; into &#39;master&#39;

Xtreme update

See merge request bec/ophyd_devices!17 ([`7a889f3`](https://gitlab.com/bec/ophyd_devices/-/commit/7a889f3fa5d90e7735cdbc6ea2290d6ec04d6c21))

* Merge branch &#39;master&#39; of gitlab.psi.ch:/bec/ophyd_devices ([`c30df21`](https://gitlab.com/bec/ophyd_devices/-/commit/c30df21c21ae4d3e90e4ec34e28cda0e4e5d6666))

* Merge branch &#39;master&#39; of gitlab.psi.ch:/bec/ophyd_devices ([`d73ac33`](https://gitlab.com/bec/ophyd_devices/-/commit/d73ac3322c21c552c5e9bebfe1741f41592a752f))

* formatter: fixed formatter ([`4de1fb9`](https://gitlab.com/bec/ophyd_devices/-/commit/4de1fb91660c59e2ea239f10c94da00e1570b5eb))

* Merge branch &#39;x07ma&#39; into &#39;master&#39;

X07ma: PGM OtF scan with FlyerInterface

See merge request bec/ophyd_devices!16 ([`7b950de`](https://gitlab.com/bec/ophyd_devices/-/commit/7b950de7a6f4f9a0dae496ace832959f5715b4bf))

* mark scan params as configuration attrs ([`d3d5aa1`](https://gitlab.com/bec/ophyd_devices/-/commit/d3d5aa1d472a9ce38b11f6f2b5bd547d110284a9))

* add SUB_VALUE event to publish intermediate steps ([`6692e53`](https://gitlab.com/bec/ophyd_devices/-/commit/6692e53018b7933dfe76bed425ce4416528032b7))

* fix describe_collect method ([`66d18e8`](https://gitlab.com/bec/ophyd_devices/-/commit/66d18e8ad4a33af4be800f931332caceb0e2f7f5))

* use FlyerInterface for PGM OtF scan ([`b7ead90`](https://gitlab.com/bec/ophyd_devices/-/commit/b7ead905c0fc683f38e1f7cd9083ae4b90040941))

* correct a few signals&#39; kind ([`5cc8cb7`](https://gitlab.com/bec/ophyd_devices/-/commit/5cc8cb7d735eaa2a60918c7c34397c4cead2934b))

* Merge branch &#39;x07ma_devices&#39; into &#39;master&#39;

X07ma devices

See merge request bec/ophyd_devices!15 ([`139418f`](https://gitlab.com/bec/ophyd_devices/-/commit/139418f5313daf4d632605f7338728328aa592b0))

* Merge branch &#39;x07ma&#39; into &#39;x07ma_devices&#39;

X07ma specific devices

See merge request bec/ophyd_devices!14 ([`38c869f`](https://gitlab.com/bec/ophyd_devices/-/commit/38c869f29520cb69d05847ac358f3b98456103b8))

* fix suffixes ([`ff8f2a9`](https://gitlab.com/bec/ophyd_devices/-/commit/ff8f2a904061c50aa642fa3f58431d999e7c01f5))

* fix magnets prefix ([`87c6c4e`](https://gitlab.com/bec/ophyd_devices/-/commit/87c6c4e32fc3de379f8823a2f4aa7d43e7923ec4))

* X07MA devices imported from PShell devices ([`c406c82`](https://gitlab.com/bec/ophyd_devices/-/commit/c406c822b3d033c20dbff6254636eec9230b9d99))

* Add LICENSE ([`376d8c2`](https://gitlab.com/bec/ophyd_devices/-/commit/376d8c2ad7e9d846379081f7e40470ba515c863f))

* Merge branch &#39;fix-mokev-mono-offests&#39; into &#39;master&#39;

Adding Theta2 offsets to mono

See merge request bec/ophyd_devices!13 ([`7320955`](https://gitlab.com/bec/ophyd_devices/-/commit/73209552cc41e78f740d8484769aeee82bb41db7))

* Testing, fixing and blacking ([`0bffecc`](https://gitlab.com/bec/ophyd_devices/-/commit/0bffecc2017031c5d7478e160b5afd2a05e96f7e))

* Adding Theta2 offsets to mono ([`6b20113`](https://gitlab.com/bec/ophyd_devices/-/commit/6b2011318dc9bc4c55dd089da2a561cf4a66e043))

* Merge branch &#39;feat-combined-channels&#39; into &#39;master&#39;

Two solutions for combined EPICS PVs

See merge request bec/ophyd_devices!11 ([`e11ef95`](https://gitlab.com/bec/ophyd_devices/-/commit/e11ef9533c3202524899aa2b14b50238ca251c0b))

* Added to ini files ([`5ecdf39`](https://gitlab.com/bec/ophyd_devices/-/commit/5ecdf39457dc612f733d33d8f1322a2f4a4b0263))

* Added to ini files ([`60708d5`](https://gitlab.com/bec/ophyd_devices/-/commit/60708d54cbd5d8c236415c9f1d93f203eb037bfe))

* Blacked on 3.10 ([`f3a14ab`](https://gitlab.com/bec/ophyd_devices/-/commit/f3a14ab8b442f501d76eb9937e96407e57d3db57))

* With a simple Signal ([`3e5c951`](https://gitlab.com/bec/ophyd_devices/-/commit/3e5c951a14f628eda439f667311513988e7c787a))

* Older blacking ([`e044d7f`](https://gitlab.com/bec/ophyd_devices/-/commit/e044d7f8abe9031fce3a5474dd8684dfcecd26f3))

* Two solutions for combined PVs ([`ae59265`](https://gitlab.com/bec/ophyd_devices/-/commit/ae59265ef749091b2424699e5a6501d1bcd16159))

* Merge branch &#39;sls_info&#39; into &#39;master&#39;

fix: online fixes

See merge request bec/ophyd_devices!10 ([`c1cb33e`](https://gitlab.com/bec/ophyd_devices/-/commit/c1cb33e0fccb2e71b5441694b50704dfaae03a33))

* Merge branch &#39;csaxs_prep&#39; into &#39;master&#39;

fix: fixed epics import

See merge request bec/ophyd_devices!9 ([`48a5503`](https://gitlab.com/bec/ophyd_devices/-/commit/48a55032cd161c622f013187ae5ba1fd36098f3a))

* Merge branch &#39;sls_info&#39; into &#39;master&#39;

Sls info

See merge request bec/ophyd_devices!8 ([`d9bdc19`](https://gitlab.com/bec/ophyd_devices/-/commit/d9bdc19ad1083e5a028c355dafdfc84b97c690b4))

* Merge branch &#39;feature-first-epics-devices&#39; into &#39;master&#39;

First EPICS devices from controls repo

See merge request bec/ophyd_devices!1 ([`e119f12`](https://gitlab.com/bec/ophyd_devices/-/commit/e119f122de4f113f3fa6d42a60abbcbc5f55fce3))

* Older blacking ([`7adb38d`](https://gitlab.com/bec/ophyd_devices/-/commit/7adb38ddfc975e6b8b123fccc7a6a13de908844a))

* Merge branch &#39;virtual-motors-for-detector&#39; into &#39;feature-first-epics-devices&#39;

Virtual motors for detector

See merge request bec/ophyd_devices!7 ([`9c27f8f`](https://gitlab.com/bec/ophyd_devices/-/commit/9c27f8f999169b600a7509b5c70072a2ebb9bc2a))

* Blacked ([`c9abd2a`](https://gitlab.com/bec/ophyd_devices/-/commit/c9abd2a9da510247b454aa913f07157b05b5bf3d))

* Tested monochromator virtual axes ([`a0a0c13`](https://gitlab.com/bec/ophyd_devices/-/commit/a0a0c1398db555319c16a951ac37ff66112b63dd))

* Mono motors in read only mode ([`bbf53a3`](https://gitlab.com/bec/ophyd_devices/-/commit/bbf53a3e64a770c86d97172e48928c33c7c8a859))

* All devices instantiate ([`fd7208e`](https://gitlab.com/bec/ophyd_devices/-/commit/fd7208ed3e7742b8617a88b6eb4470911019cfa8))

* Adding virtual otors for mono bender and detector ([`c483b50`](https://gitlab.com/bec/ophyd_devices/-/commit/c483b50043b2ab69d7a9d0061ffbe874c6edefdb))

* Flaking ([`7bb9c11`](https://gitlab.com/bec/ophyd_devices/-/commit/7bb9c11249fbdd4bfc70ef03fc123b7680e40910))

* Better config ([`6c2ae5c`](https://gitlab.com/bec/ophyd_devices/-/commit/6c2ae5c1662154399f0659a79e8a105351668ba3))

* Output formatting ([`5725af8`](https://gitlab.com/bec/ophyd_devices/-/commit/5725af830729e5e7d1b5f95284ae4dedaac47396))

* bug fixes for sls devices ([`62054c5`](https://gitlab.com/bec/ophyd_devices/-/commit/62054c56af02bf278ed999948b1d8140f2f812af))

* added auto_monitor forwarder to sls_info ([`e0c0469`](https://gitlab.com/bec/ophyd_devices/-/commit/e0c04697958c3fd08e0d2f4f8e5c61bf034c51cc))

* Merge branch &#39;sls_info&#39; of gitlab.psi.ch:/bec/ophyd_devices into sls_info ([`8c6a96c`](https://gitlab.com/bec/ophyd_devices/-/commit/8c6a96ca2c13f06774bdfd13738937c2a585e8f2))

* removed duplicated pv ([`08a8272`](https://gitlab.com/bec/ophyd_devices/-/commit/08a8272ac03556c8091247a9a5f58753c43a2622))

* improvements for sls info ([`7bf193e`](https://gitlab.com/bec/ophyd_devices/-/commit/7bf193eaa6b3217c1386a9405ea41c0f64f2fb53))

* Flaking ([`cb1549c`](https://gitlab.com/bec/ophyd_devices/-/commit/cb1549cf2ddf574e84c4321f796d05a1bc95ef8c))

* Flaking ([`5f251db`](https://gitlab.com/bec/ophyd_devices/-/commit/5f251db89144b488f4b80c949a2c2e36ec0f83a8))

* Small chanege ([`15950e6`](https://gitlab.com/bec/ophyd_devices/-/commit/15950e6d05611d5f70e353132602e4980745f368))

* Codestyle ([`3a7dd4e`](https://gitlab.com/bec/ophyd_devices/-/commit/3a7dd4e3cfc84517e8be86b29a1f2811fbdbc513))

* Flaking ([`c7867a9`](https://gitlab.com/bec/ophyd_devices/-/commit/c7867a910fb93f9d8bab71f86612712e6736c7c7))

* Added insertion device proxy ([`19f5f72`](https://gitlab.com/bec/ophyd_devices/-/commit/19f5f728cc5c224f0802bc88a6084d073d6f78ac))

* A few more fixes ([`82a37ce`](https://gitlab.com/bec/ophyd_devices/-/commit/82a37ceb3857e5bf4dcb9744cd0bbccacb7685d3))

* XBPM proxies ([`8b74d08`](https://gitlab.com/bec/ophyd_devices/-/commit/8b74d08097705f66b4aa92816cb0c8e87d736080))

* Added device factory ([`2443269`](https://gitlab.com/bec/ophyd_devices/-/commit/244326937135acec09890544e227fcb85f29e550))

* Merge branch &#39;sls_info&#39; into &#39;master&#39;

Sls info

See merge request bec/ophyd_devices!6 ([`0397ec4`](https://gitlab.com/bec/ophyd_devices/-/commit/0397ec43239fe8befeca33d96f5c22885c9555c2))

* Merge branch &#39;master&#39; into sls_info ([`f5096a9`](https://gitlab.com/bec/ophyd_devices/-/commit/f5096a90e50b85cb60c9426a9931b88192ed23d9))

* Merge branch &#39;master&#39; of gitlab.psi.ch:/bec/ophyd_devices ([`e9869d8`](https://gitlab.com/bec/ophyd_devices/-/commit/e9869d8ef1bccf70908bbe089a2287d8d92467cb))

* cleanup ([`c7cabc3`](https://gitlab.com/bec/ophyd_devices/-/commit/c7cabc3eeb41d0ded3c5b05e4de3941437f857d0))

* online_changes ([`7b221ea`](https://gitlab.com/bec/ophyd_devices/-/commit/7b221ea9794ac6079e3392c55ad8b8c0c0605b8e))

* added eiger1p5M ([`bba6109`](https://gitlab.com/bec/ophyd_devices/-/commit/bba61093300a0aecd531e3c789003834074e9b42))

* added beamlineinfo to int ([`bd7b18c`](https://gitlab.com/bec/ophyd_devices/-/commit/bd7b18c1efc50206db1693de25d66eae6cac987c))

* added beamlineinfo ([`bd8d081`](https://gitlab.com/bec/ophyd_devices/-/commit/bd8d081c5b4b5511624f9d2606745db0b0a5b1cc))

* Merge branch &#39;online_changes&#39; into &#39;master&#39;

Online changes

See merge request bec/ophyd_devices!5 ([`2a36549`](https://gitlab.com/bec/ophyd_devices/-/commit/2a365493f24ccdadfa73c5a50fcdfb7e8a8734cb))

* Merge branch &#39;master&#39; into online_changes ([`ca5a03b`](https://gitlab.com/bec/ophyd_devices/-/commit/ca5a03b2f1b244d4ca10b647f39d98cbeeba64b8))

* added lsamx/lsamy from config ([`7be2f9a`](https://gitlab.com/bec/ophyd_devices/-/commit/7be2f9af796ac632a83bb5e54f89109a0b9bde3a))

* Merge branch &#39;online_changes&#39; into &#39;master&#39;

added enabled-set

See merge request bec/ophyd_devices!4 ([`6b4cf3f`](https://gitlab.com/bec/ophyd_devices/-/commit/6b4cf3f79c1d3a073d70b7e436e4f5303d6456e3))

* added enabled-set ([`d71e821`](https://gitlab.com/bec/ophyd_devices/-/commit/d71e82127e2e450490d1f4b0e01ee0b3c0e7f002))

* Merge branch &#39;online_changes&#39; into &#39;master&#39;

added device enable/disable routines to rt_lamni

See merge request bec/ophyd_devices!3 ([`78a944e`](https://gitlab.com/bec/ophyd_devices/-/commit/78a944e46ef7ce1648c97a8eda3d4d64a1a39707))

* added device enable/disable routines to rt_lamni ([`d6452db`](https://gitlab.com/bec/ophyd_devices/-/commit/d6452db5d4ff754173f1cb3ae2cc9dfb2ef08ee6))

* Merge branch &#39;online_changes&#39; into &#39;master&#39;

Online changes

See merge request bec/ophyd_devices!2 ([`31fbefb`](https://gitlab.com/bec/ophyd_devices/-/commit/31fbefb1d687ce170760e474a0da5cf99a0108c7))

* fixed tests ([`faa6e0d`](https://gitlab.com/bec/ophyd_devices/-/commit/faa6e0db1aa412d1a5ac6e2e682434a124f2fe07))

* Update .gitlab-ci.yml ([`be8d113`](https://gitlab.com/bec/ophyd_devices/-/commit/be8d113e5baf65ccb760aff93d1c52706cad1230))

* Update .gitlab-ci.yml ([`22bbfb1`](https://gitlab.com/bec/ophyd_devices/-/commit/22bbfb1d59c11fa770092652856938bb6b4f4a42))

* Update .gitlab-ci.yml ([`cdc0f82`](https://gitlab.com/bec/ophyd_devices/-/commit/cdc0f8294ad34d37ee12814f2d57eba8b0cb04e7))

* updated ci file ([`ab61aa6`](https://gitlab.com/bec/ophyd_devices/-/commit/ab61aa61aebd2593914df8ea59b48390a76cda90))

* fixed formatting for socket ([`28cb54c`](https://gitlab.com/bec/ophyd_devices/-/commit/28cb54c254f62976926ded33544dbbb9fdcbfffa))

* added bec logger ([`ed77e57`](https://gitlab.com/bec/ophyd_devices/-/commit/ed77e575bf9d1e7f01eb8850a9f40cf27eb91b5b))

* fixed bug that lead galil to quit unexpectedly ([`0b774f2`](https://gitlab.com/bec/ophyd_devices/-/commit/0b774f25dd995fdf3d66f0d83a3868dc63a9dabb))

* fixed bug in rt readout ([`e66208c`](https://gitlab.com/bec/ophyd_devices/-/commit/e66208ca182c12711e695bf360964cd4d5d39c6a))

* First EPICS devices from controls repo ([`d6da41f`](https://gitlab.com/bec/ophyd_devices/-/commit/d6da41f5e62b6de87718aa5a2faa562b0a558b20))

* added SynSignalRO ([`a8a2637`](https://gitlab.com/bec/ophyd_devices/-/commit/a8a2637d07026b1ce3d1bc4e3f0da67bb5993d17))

* update timestamp on read ([`fbace69`](https://gitlab.com/bec/ophyd_devices/-/commit/fbace69f0fcc10e51ca4a152a7376752f9e7a8a5))

* replaced staging in tests by direct controller.on calls ([`fbdccf4`](https://gitlab.com/bec/ophyd_devices/-/commit/fbdccf4dd7ca1747629c3e49412a1f2a7123cf6a))

* removed controller.on methods from staging; improvements for detector sim ([`80e101a`](https://gitlab.com/bec/ophyd_devices/-/commit/80e101a5efe47e57d71c315e82b0bf9fb27c05b4))

* added first version of a detector sim ([`d60b58a`](https://gitlab.com/bec/ophyd_devices/-/commit/d60b58a5f5e63fe9a7ad907f37549abb542fa802))

* minor cleanup ([`a3b3efc`](https://gitlab.com/bec/ophyd_devices/-/commit/a3b3efc4a53de547f2dc424e89a316262ff8fc05))

* added pre-commit hook ([`000bdfd`](https://gitlab.com/bec/ophyd_devices/-/commit/000bdfda12ba721261b2e2953a367363a8480083))

* enforced black ([`ac234ed`](https://gitlab.com/bec/ophyd_devices/-/commit/ac234edd56b7b0f29d8f284c704cdc1848ea0b38))

* improvements for flyer sim ([`e6ce939`](https://gitlab.com/bec/ophyd_devices/-/commit/e6ce939eef33a55ea439b29505ca619ab440728b))

* added threadlocks to signals ([`49106b0`](https://gitlab.com/bec/ophyd_devices/-/commit/49106b0539b2a087d8be418ecc9e8fd49c4c9fc9))

* Merge branch &#39;master&#39; of gitlab.psi.ch:/bec/ophyd_devices ([`4a0210c`](https://gitlab.com/bec/ophyd_devices/-/commit/4a0210ca88bd3a2af08c8547df877d8062f42fdb))

* added threadlock decorator to all socket calls; cleanup ([`5ceadfb`](https://gitlab.com/bec/ophyd_devices/-/commit/5ceadfb648208342ef65fbed26fabf9ec02e6ab1))

* online changes; added threadlock for galil ([`4a32d71`](https://gitlab.com/bec/ophyd_devices/-/commit/4a32d71f374f52408fc9c1634b819dc4ceb482e4))

* removed signal entry for now ([`bf0b1cb`](https://gitlab.com/bec/ophyd_devices/-/commit/bf0b1cb280765fd3f1cf32932eb1088d8b20d789))

* black; added push events to rt_lamni ([`98a1426`](https://gitlab.com/bec/ophyd_devices/-/commit/98a1426a98a3d495970e0e03b002d00a1f65361f))

* Merge branch &#39;master&#39; of gitlab.psi.ch:/bec/ophyd_devices ([`069887c`](https://gitlab.com/bec/ophyd_devices/-/commit/069887c5cb977bba4012b8a457362790b4120a85))

* added flyer sim ([`619ff60`](https://gitlab.com/bec/ophyd_devices/-/commit/619ff60e732014b6de83fa7024638a48ac7d6beb))

* Merge branch &#39;master&#39; of https://gitlab.psi.ch/bec/ophyd_devices ([`2434ba3`](https://gitlab.com/bec/ophyd_devices/-/commit/2434ba30e92b2019e080efd137ab7f24cbd34d29))

* online changes; added bec logger; added limits to custom devices ([`6e541cc`](https://gitlab.com/bec/ophyd_devices/-/commit/6e541cc0d0e3696d5767411a83f904a4429f6a89))

* Update .gitlab-ci.yml ([`c97d69e`](https://gitlab.com/bec/ophyd_devices/-/commit/c97d69e03b093586ce41f0cdc99316d133994694))

* Update .gitlab-ci.yml ([`75420a0`](https://gitlab.com/bec/ophyd_devices/-/commit/75420a009510951997974c1b5579f1b6aa22c92a))

* Update .gitlab-ci.yml ([`e9998f1`](https://gitlab.com/bec/ophyd_devices/-/commit/e9998f194a446d34fd34fb6af00843d5412f6990))

* Update .gitlab-ci.yml ([`f8679b0`](https://gitlab.com/bec/ophyd_devices/-/commit/f8679b0dc43a6b47886f00836a73439aa5b48f84))

* added git; changed python image to 3.8 ([`2395ba9`](https://gitlab.com/bec/ophyd_devices/-/commit/2395ba92f3afe1452e878fbe78b4df12cc4c4f6e))

* online changes ([`3b97133`](https://gitlab.com/bec/ophyd_devices/-/commit/3b971336eeb05acc40a06f79ef8d0b76beb9d089))

* online_changes ([`d3acfad`](https://gitlab.com/bec/ophyd_devices/-/commit/d3acfad694dc71d1a363f3de56bbc9e5b401f491))

* Merge branch &#39;master&#39; of https://gitlab.psi.ch/bec/ophyd_devices ([`1ef5035`](https://gitlab.com/bec/ophyd_devices/-/commit/1ef5035f2c39cc9d325cc24b348ecc09bd3df67b))

* online_changes ([`a0bd8bb`](https://gitlab.com/bec/ophyd_devices/-/commit/a0bd8bb02beb89cbe0f03a1f19dd713dc53fa8ba))

* changed to new config attribute device_mapping ([`298094d`](https://gitlab.com/bec/ophyd_devices/-/commit/298094d58bf989205ff4e3e12f0c0452e6e33d68))

* fixed bug fixed again (overwritten by import) ([`8eff1f7`](https://gitlab.com/bec/ophyd_devices/-/commit/8eff1f763804776702f75a6b753256c0b2da1e3a))

* fixed indents ([`a23e197`](https://gitlab.com/bec/ophyd_devices/-/commit/a23e19765924934623a31891faf8ee01911dd8b4))

* import from internal git ([`d727c12`](https://gitlab.com/bec/ophyd_devices/-/commit/d727c12b239f6ce5646490c7ea2864bef6604241))

* fixed bug in device sim for stopping devices ([`fb1c39c`](https://gitlab.com/bec/ophyd_devices/-/commit/fb1c39c9161c2c5694ef351002138f09bb6a1f2e))

* fixed bug in sim ([`a87ab24`](https://gitlab.com/bec/ophyd_devices/-/commit/a87ab24d9e1298008182061610048e92c24f1329))

* export from internal gitlab ([`52ce30d`](https://gitlab.com/bec/ophyd_devices/-/commit/52ce30dc9a79022321f59eadd0a81b831c1f5c1b))

* Initial commit ([`b1a3cd3`](https://gitlab.com/bec/ophyd_devices/-/commit/b1a3cd39194866a0dc13ed7655181ab919495296))
