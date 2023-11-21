# Changelog

<!--next-version-placeholder-->

## v0.13.3 (2023-11-21)

### Fix

* Fix auto_monitor=True for MockPV by add add_callback = mock.MagicMock() ([`e7f7f9d`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/e7f7f9d6658a27ca98ac17ffb998efae51ec3497))
* Renamed to prepare_detector_backend ([`16022c5`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/16022c53ef9e3134fe486892c27f26e5c12fad2e))
* Rename custome_prepare.prepare_detector_backend, bugfix in custom_prepare.wait_for_signals ([`f793ec7`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/f793ec7b1f3f2d03a686d592d4cd9c2e2f087faf))
* Add __init__ and super().__init__ to falcon,eiger and pilatus ([`9e26fc2`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/9e26fc2a3c82e610d0c570db9a08a698c3394bc8))

### Documentation

* Imporive pylint score ([`5b27e6f`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/5b27e6fe1e20a50894c47144a412b9361ab1c4e6))
* Add docstrings, improve pylint score ([`5874466`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/587446670444f245ec2c24db0355578921b8fe59))
* Add docstring ([`cbe8c8c`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/cbe8c8c4e5a53a0b38a58e11b85b11307e92ced7))

## v0.13.2 (2023-11-20)

### Fix

* Remove stop from falcon.custom_prepare.arm_acquisition; closes #23 ([`9e1a6da`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/9e1a6daa6edbfe2a9e7c9b15f21af5785a119474))
* Remove stop from pilatus.custom_prepare.finished ([`334eeb8`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/334eeb83dc3e1c7c37ce41d2ba5f720c3880ef46))
* Remove duplicated stop call from eiger.custom_prepare.finished ([`175700b`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/175700b6ad135cb7491eb88431ecde56704fd0b4))

## v0.13.1 (2023-11-18)

### Fix

* Include all needed files in packaged distro ([`204f94e`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/204f94e0e4496f8347772f869bb0722e6ffb9ccf))

## v0.13.0 (2023-11-17)

### Feature

* Refactor falcon for psi_detector_base class; adapted eiger; added and debugged tests ([`bcc3210`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/bcc321076153ccd6ae8419b95553b5b4916e82ad))
* Add CustomDetectorMixin, and Eiger9M setup to separate core functionality in the ophyd integration ([`c8f05fe`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/c8f05fe290485dd7703dfb7a4bfc660d7d01d67d))
* Add docstring to detector base class; closes #12 ([`2252779`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/225277949d91febd4482475a12c1ea592b735385))
* Add SLSDetectorBaseclass as a baseclass for detectors at SLS ([`13180b5`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/13180b56dac614206ca5a8ad088e223407b83977))

### Fix

* Fixed MIN_readout, and made it a class attribute with set/get functions ([`b9d0a5d`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/b9d0a5d86977ff08962a27ac507296ca5dae229c))
* Add User_access to cSAXS falcon and eiger ([`e8ec101`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/e8ec101f5399ac7be2aeb1b1d69d6866d6d2f69b))
* Removed __init__ from eiger9mcSAXS ([`c614873`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/c614873f8f913e0c1d417b63cf6dea2f39708741))
* Fix imports to match bec_lib changes ([`9db00ad`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/9db00add047536c7aa35d2b08daafb248d5c8c01))
* Fixed merge conflict ([`d46dafd`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/d46dafdbe85b9f2a1c080297bd361a3445779d60))
* Removed sls_detector_baseclass, add psi_detector_base, fixed tests and eiger9m_csaxs ([`90cd05e`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/90cd05e68ea7640a6bc1a8b98d47f9edc7a7f3a0))
* Add PSIDetectorBase ([`a8a1210`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/a8a12103ea2108c5183a710ead04db4379627d83))
* Small bugfix ([`ee5cf17`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/ee5cf17a05ededda6eff25edece6d6f437d0f372))
* Fixed imports to comply with bec_lib refactoring ([`79cfaf6`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/79cfaf6dc03bad084673fe1945828c15bba4b6e8))
* Bugfix ([`7fefb44`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/7fefb44462c4bfa7853b0519b33ef492ace53050))
* Add remaining function, propose mechanism to avoid calling stage twice ([`3e1a2b8`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/3e1a2b86c31a241ac92ef9808ad2b92fed020ec8))
* Changed file_writer to det_fw ([`575b4e6`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/575b4e6260e95d4c4c40d76b3fc38f258e43a381))

## v0.12.0 (2023-11-17)

### Feature

* Added syndynamiccomponents for BEC CI tests ([`824ae0b`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/824ae0bde63f2ba5278e532812fe41d07f179099))

## v0.11.0 (2023-11-16)

### Feature

* Add pylint check to ci pipeline ([`a45ffe7`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/a45ffe7740714a57aad54fbc56164971144a6b7d))

## v0.10.2 (2023-11-12)

### Fix

* Remove pytest dependency for eiger, falcon and pilatus; closes #18 and #9 ([`c6e6737`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/c6e6737547face4f298758e4017099208748d1a9))

## v0.10.1 (2023-11-09)

### Fix

* Adding pytest as dependency; should be removed! ([`a6a621f`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/a6a621f5ea88370152256908cdd4d60ce4489c7b))

## v0.10.0 (2023-11-08)

### Feature

* Added fupr ([`9840491`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/9840491ab7f92eacdb7616b9530659b1800654af))
* Added support for flomni galil ([`23664e5`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/23664e542cfcccafe31d0e41d1421c277bd00d23))
* Added galil for flomni ([`7b17b84`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/7b17b8401a516613ee3e67f1e03892ba573e392c))

### Fix

* Changed dependency injection for controller classes; closes #13 ([`fb9a17c`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/fb9a17c5e383e2a378d0a3e9cc7cc185dd20c96e))
* Fixed fupr number of axis ([`9080d45`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/9080d45075158b1a7d7a60838ea33f058260755f))
* Fixed fupr axis_is_referenced ([`ce94a6a`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/ce94a6a88df6f90409c4fb4c29260ad77048f27d))
* Fixed fupr axis_is_referenced ([`3396ff4`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/3396ff44d94955155c38a84a08880b93cb400cca))
* Fixed fupr axis_is_referenced ([`d72dc82`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/d72dc82264051e3e0a77527b06d29bd055e7bcdc))
* Fixed import; fixed file name ([`2ddc074`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/2ddc074e4fe9638bac77df5f3bbd2b1c4600814c))
* Fixed drive_to_limit ([`1aae1eb`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/1aae1eba12c05dfa5c4196edec3be488fa4f2b1e))
* Fixed drive_to_limit ([`3eea89a`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/3eea89acc5b2e18dd9d7b4a91e50590ca9702bba))
* Fixed id assignment ([`9b3139e`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/9b3139ecf106150170d2299303997d3dd8a97b4d))
* Fixed import for fgalil ([`3f76ef7`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/3f76ef76d736965b3257770efee1d2971afd90b3))

## v0.9.2 (2023-11-08)

### Fix

* Bugfixes after adding tests ([`72b8848`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/72b88482ca8b5104dbcf3e8a4e430497eb5fd5f8))

## v0.9.1 (2023-11-02)

### Fix

* Fixed complete call for non-otf scans ([`9e6dc2a`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/9e6dc2a9f72c5615abd8bea1fcdea6719a35f1ad))

## v0.9.0 (2023-10-31)

### Feature

* Added file-based replay for xtreme ([`d25f92c`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/d25f92c6323cccea6de8471f4445b997cfab85a3))

## v0.8.1 (2023-09-27)

### Fix

* Fixed formatting ([`48445e8`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/48445e8b61031496712bfdb262a944c6d058029f))
* Add ndarraymode and formatting ([`712674e`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/712674e4b8f662b3081d21ed7c2d053260a728e6))
* Online changes e21536 ([`0372f6f`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/0372f6f726f14b3728921ca498634b4c4ad5e0cb))

## v0.8.0 (2023-09-15)

### Feature

* First draft for Epics sequencer class ([`c418b87`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/c418b87ad623f32368197a247e83fc99444dc071))

### Fix

* Format online changes via black ([`f221f9e`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/f221f9e88ee40e7e24a572d7f12e80a98d70f553))
* Minor changes on the sgalil controller ([`b6bf7bc`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/b6bf7bc9b3b5e4e581051bec2822d329da432b50))
* Small changes in epics_motor_ex, potentially only comments ([`f9f9ed5`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/f9f9ed5e23d7478c5661806b67368c9e4711c9f5))
* Online changes in e20639 for mcs card operating full 2D grid ([`67115a0`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/67115a0658b1122881332e90a3ae9fa2780ca129))
* Online changes e20643 ([`0bf308a`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/0bf308a13d55f795c6537c66972a80d66ec081dd))
* Online changes sgalil e20636 ([`592ddfe`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/592ddfe6da87af467cfe507b46d423ccb03c21dd))
* Online changes pilatus_2 e20636 ([`76f88ef`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/76f88efa31b1c599a7ee8233a7721aed30e6a611))
* Online changes e20636 mcs ([`bb12181`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/bb12181020b8ebf16c13d13e7fabc9ad8cc26909))
* Online changes e20636 falcon ([`7939045`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/793904566dfb4bd1a22ac349f270a5ea2c7bc75f))
* Online changes eiger9m ([`e299c71`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/e299c71ec060f53563529f64ab43c6906efd938c))
* Online changes DDG ([`c261fbb`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/c261fbb55a3379f17cc7a14e915c6c5ec309281b))

## v0.7.0 (2023-09-07)

### Feature

* Add timeout functionality to ophyd devices ([`c80d9ab`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/c80d9ab29bcc85a46b59f3be8fb86b990c3ed299))

## v0.6.0 (2023-09-07)

### Feature

* Add falcon and progress bar option to devices ([`3bab432`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/3bab432a2f01e3a62811e13b9143d67da495fbb8))
* Extension for epics motors from xiaoqiang ([`057d93a`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/057d93ab60d2872b2b029bdc7b6dcab35a6a21a5))
* Add mcs_readout_monitor and stream ([`ab22056`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/ab220562fc1eac3bcffff01fd92085445dd774e7))
* Add ConfigSignal to bec_utils ([`ac6de9d`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/ac6de9da54444dda21820591dd8e3ad098d3f0ac))
* Adding mcs card to repository ([`96a131d`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/96a131d3743c8d62aaac309868ac1309d83fe9aa))
* Add bec_utils to repo for generic functions ([`86e93af`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/86e93afe28fc91b5c0a773c489d99cf272c52878))
* Add bec_scaninfo_mixin to repo ([`01c824e`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/01c824ecead89a1c83cefacff53bf9f76b02d423))
* Bec_scaninfo_mixin class for scaninfo ([`49f95e0`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/49f95e04765e2e4035c030a35272bdb7f06f8d8f))
* Add eiger9m csaxs ([`f3e4575`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/f3e4575359994c134e1b207915fadb9f8f92e4d9))
* Add mcs ophyd device ([`448890a`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/448890ab27ba1bfeb24870d792c498b96aa7cc47))

### Fix

* Online changes ([`3a12697`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/3a126976cd7cfb3f294556110d77249da6fbc99d))
* Adjusted __init__ for epics motor extension ([`ac8b96b`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/ac8b96b9ba76ba52920aeca7486ca9046e07326c))
* Changes for sgalil grid scan from BEC ([`3e594b5`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/3e594b5e0461d43431e0103cb713bcd9fd22ca1c))
* Working acquire, line and grid scan using mcs, ddg and eiger9m ([`58caf2d`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/58caf2ddd3416deaace82b6e321fc0753771b282))
* DDG logic to wait for burst in trigger ([`5ce6fbc`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/5ce6fbcbb92d2fafb6cfcb4bb7b1f5ee616140b8))
* Online changes SAXS ([`911c8a2`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/911c8a2438c9cdf1ca2a9685e1dbbbf4a1913f5c))
* Working mcs readout ([`8ad3eb2`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/8ad3eb29b79a0a8a742d1bc319cfedf60fcc150f))
* Fix ddg code ([`b3237ce`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/b3237ceda5468058e294da4a3e608c4344e582dc))
* Bugfix online fixes ([`ba9cb77`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/ba9cb77ed9b0d1a7e0f744558360c90f393b6f08))
* Bugfix in delaygenerators ([`2dd8f25`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/2dd8f25c8727759a8cf98a0abee87e379c9307d7))
* Online changes to all devices in preparation for beamtime ([`c0b3418`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/c0b34183661b11c39d65eb117c3670a714f9eb5c))
* Online changes ([`b6101cc`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/b6101cced24b8b37a3363efa5554a627fdc875b1))
* Mcs working ([`08efb64`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/08efb6405bc615b40855288067c1e811f1471423))
* Add std_daq_client and pyepics to setup ([`5d86382`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/5d86382d80c033fb442afef74e95a19952cd5937))
* Bugfix for polarity ([`fe404bf`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/fe404bff9c960ff8a3f56686b24310d056ad4eda))
* Test function ([`2dc3290`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/2dc3290787a2c2cc79141b9d1da3a805b2c67ccd))
* Online changes to integrate devices in BEC ([`fbfa562`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/fbfa562713adaf374dfaf67ebf30cbd1895dd428))
* Fixed stop command ([`d694f65`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/d694f6594d0bd81fd62be570142bc2f6b19cf6f4))
* Running ophyd for mcs card, pending fix mcs_read_all epics channel ([`7c45682`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/7c45682367c363207257fff7b6ce53ffee1449df))
* Bec_utils mixin ([`ed0ef33`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/ed0ef338eb606977993d45c98421ebde0f477927))
* Sgalil scan ([`cc6c8cb`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/cc6c8cb41bc6e3388a580adeee0af8a1c7dbca27))
* Pil300k device, pending readout ([`b91f8db`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/b91f8dbc6854cf46d1d504610855d50563a8df36))
* Adjusted delaygen ([`17347ac`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/17347ac93032c9b57247d9f565f638340a9973af))
* Add readout time to mock scaninfo ([`8dda7f3`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/8dda7f30c1e797287ddf52f6448604c1052ce3ce))
* Add flyscan option ([`3258e3a`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/3258e3a1c7e799c4d718dc9cb7f5abfcf87e59f3))
* Stepscan logic implemented in ddg ([`c365b8e`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/c365b8e9543ac0eca3bc3da34f662422e7daeef7))
* Use bec_scaninfo_mixin in ophyd class ([`6ee819d`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/6ee819de53d39d8d14a4c4df29b0781f83f930ec))
* Add status update std_daq ([`39142ff`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/39142ffc92440916b6c68beb260222f4dd8a0548))
* Mcs updates ([`14ca550`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/14ca550af143cdca9237271311b9c5ea280d7809))
* Falcon updates ([`b122de6`](https://gitlab.psi.ch/bec/ophyd_devices/-/commit/b122de69acfd88d82eaba85534840e7fae21b718))

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
