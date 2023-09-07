# Changelog

<!--next-version-placeholder-->

## v0.5.0 (2023-09-01)

### Feature

* Added derived signals for xtreme ([`1276e1d`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/1276e1d0db44315d8e95cdf19ec32d68c7426fc8))

### Fix

* Added pyepics dependency ([`66d283b`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/66d283baeb30da261d0f27e73bca4c9b90d0cadd))

## v0.4.0 (2023-08-18)

### Feature

* Add pilatus_2 ophyd class to repository ([`9476fde`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/9476fde13ab427eba61bd7a5776e8b71aca92b0a))

### Fix

* Simple end-to-end test works at beamline ([`28b91ee`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/28b91eeda22af03c3709861ff7fb045fe5b2cf9b))

## v0.3.0 (2023-08-17)

### Feature

* Add continous readout of encoder while scanning ([`69fdeb1`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/69fdeb1e965095147dc18dc0abfe0b7962ba8b38))
* Adding io access to delay pairs ([`4513110`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/451311027a50909247aaf99571269761b68dcb27))
* Read_encoder_position, does not run yet ([`9cb8890`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/9cb889003933bf296b9dc1d586f7aad50421d0cf))
* Add readout_encoder_position to sgalil controller ([`a94c12a`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/a94c12ac125211f16dfcda292985d883e770b44b))

### Fix

* Bugfix on delaystatic and dummypositioner ([`416d781`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/416d781d16f46513d6c84f4cf3108e61b4a37bc2))
* Bugfix burstenable and burstdisalbe ([`f3866a2`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/f3866a29e9b7952f6b416758a067bfa2940ca945))
* Limit handling flyscan and error handling axes ref ([`a620e6c`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/a620e6cf5077272d306fc7636e5a8eee1741068f))
* Bugfix stage/unstage ([`39220f2`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/39220f20ea7f81825fe73fbc37592462f2e02a6e))
* Small fixes to fly_grid_scan ([`87ac0ed`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/87ac0edf999eb2bc589e69807ffc6e980241a19f))

### Documentation

* Details on encoder reading of sgalilg controller ([`e0d93a1`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/e0d93a1561ca9203aaf1b5aaf2d6a0dec9f0689e))
* Documentation update ([`5d9fb98`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/5d9fb983301a5513a1fb9a9a3ed56537626848ee))
* Add documentation for delay generator ([`7ad423b`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/7ad423b36434ad05d2f9b46824b6d850f55861f2))
* Updated documentation ([`eb3e90e`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/eb3e90e8a25834cbba5692eda34013f63295737f))

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
