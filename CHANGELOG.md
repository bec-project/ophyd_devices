# Changelog

<!--next-version-placeholder-->

## v0.2.1 (2023-07-21)

### Fix

* Fixed sim readback timestamp ([`7a47134`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/7a47134a6b8726c0389d8e631028af8f8be54cc2))

## v0.2.0 (2023-07-04)

### Feature

* Add DDG and prel. sgalil devices ([`00c5501`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/00c55016e789f184ddb5c2474eb251fd62470e04))

### Fix

* Formatting DDG ([`4e10a96`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/4e10a969c8625bc48d6db99fc7f5be9d46807df1))
* Bec_lib.core import ([`25c7ce0`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/25c7ce04e3c2a5c2730ce5aa079f37081d7289cd))
* Recover galil_ophyd from master ([`5f655ca`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/5f655caf29fe9941ba597fdaee6c4b2a20625ca8))
* Fixed galil sgalil_ophyd confusion from former commit ([`f488f0b`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/f488f0b21cbe5addd6bd5c4c54aa00eeffde0648))

### Documentation

* Improved readme ([`781affa`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/781affacb5bc0c204cb7501b629027e66e47a0b1))

## v0.1.0 (2023-06-28)

### Feature

* Added dev install to setup.py ([`412a0e4`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/412a0e4480a0a5e7d2921cef529ef8aceda90bb7))
* Added pylintrc ([`020459e`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/020459ed902ab226d1cea659f6626d7a887cb99a))
* Added sls detector ([`63ece90`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/63ece902a387c2c4a5944eb766f6a94e58b48755))
* Added missing epics devices for xtreme ([`2bf57ed`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/2bf57ed43331ae138e211f14ece8cfd9a1b79046))
* Added otf sim ([`f351320`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/f3513207d92e077a8a5e919952c3682250e5afa1))
* Added nested object ([`059977d`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/059977db1f160c8a21dccf845967dc265d34aa6a))
* Added test functions for rpc calls ([`5648ea2`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/5648ea2d15c1994b34353fe51e83bf5d7a634520))

### Fix

* Fixed gitignore file ([`598d72b`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/598d72b4ec9e9b1c5b100321d93370bf4b9ed426))
* Adjustments for new bec_lib ([`eee8856`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/eee88565655eaab62ec66f018dcbe02d09594716))
* Moved to new bec_client_lib structure ([`35d5ec8`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/35d5ec8e9d94c0a845b852b6cd8182897464fca8))
* Fixed harmonic signal ([`60c7878`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/60c7878dad4839531b6e055eb1be94d696c6e2a7))
* Fixed pv name for sample manipulator ([`41929a5`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/41929a59ab26b7502bef38f4d72c846d136bab03))
* Added missing file ([`5a7f8ac`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/5a7f8ac40781f5ccf48b6ca94a569665592dc15b))
* Fixed x07ma devices ([`959789b`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/959789b26f21f1375d36db91dc6d5f9ac32a677d))
* Online bug fixes ([`bf5f981`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/bf5f981f52f063df687042567b8bc6e40cdb1d85))
* Fixed rt_lamni hints ([`2610542`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/26105421247cf5ea2b145e51525db8326b02852e))
* Fixed rt_lamni for new hinted flyers ([`419ce9d`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/419ce9dfdaf3ebdb30a2ece25f37a8ebe1a53572))
* Moved to hint structure for flyers ([`fc17741`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/fc17741d2ac46632e3adb96814d2c41e8000dcc6))
* Added default_sub ([`9b9d3c4`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/9b9d3c4d7fc629c42f71b527d86b6be0bf4524bc))
* Minor adjustments to comply with the openapi schema; set default onFailure to retry ([`cdb3fef`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/cdb3feff6013516e52d77b958f4c39296edee7bf))
* Fixed timestamp update for bpm4i ([`dacfd1c`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/dacfd1c39b7966993080774c6154f856070c8b27))
* Fixed bpm4i for subs ([`4c6b7f8`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/4c6b7f87219dbf8f369df9a65e4e8cec278d0568))
* Formatter ([`9e938f3`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/9e938f3745106fb62e176d344aee6ee5c1fffa90))
* Online fixes ([`1395044`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/1395044432dbf9235adce0fd5d46c019ea5db2db))
* Removed matplotlib dependency ([`b5611d2`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/b5611d20c81cfa07f7451aaed2b9146e8bbca960))
* Fixed epics import ([`ec3a93f`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/ec3a93f96e3e07e5ac88d40fe1858915f667e64c))
