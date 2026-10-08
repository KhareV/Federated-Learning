**Candidate and state lineage**

| state | sha256 | previous_state_sha256 | source_artifact | equals_frozen_3_round_reference | status | finite |
|---|---|---|---|---|---|---|
| R00 | 6a2923ca87793fb78571b4cffad4026f8b4ce99d9dfcb3abe885e259c68a572f | UNDEFINED | FL_INIT_V2 | True | initial state | True |
| R01 | 40cee0654e1a05eb76f3e6a4d177be1953add71b7fcdad07c6e8d8f2d974c0a1 | 6a2923ca87793fb78571b4cffad4026f8b4ce99d9dfcb3abe885e259c68a572f | states/R01.bin | True | INTERMEDIATE_STATE | True |
| R02 | 6237c0b1752c58daedcbd6e9456ab349c35318d513e706bd8bec36941ee7d2ef | 40cee0654e1a05eb76f3e6a4d177be1953add71b7fcdad07c6e8d8f2d974c0a1 | states/R02.bin | True | INTERMEDIATE_STATE | True |
| R03 | 3f0b7762ae7e05f21eb1709521404ed4d7968cae34f89e1797a0cbabd47c70e4 | 6237c0b1752c58daedcbd6e9456ab349c35318d513e706bd8bec36941ee7d2ef | states/R03.bin | True | INTERMEDIATE_STATE | True |
| R04 | 5904292f8ce36ea15877ca4e588ca56fe243a1cec12afb0ab2890a6143cb1d54 | 3f0b7762ae7e05f21eb1709521404ed4d7968cae34f89e1797a0cbabd47c70e4 | states/R04.bin | UNDEFINED | INTERMEDIATE_STATE | True |
| R05 | b734e5244040216601e44b8a8024a48a845d64b5256edb91bfbcda11e81d6001 | 5904292f8ce36ea15877ca4e588ca56fe243a1cec12afb0ab2890a6143cb1d54 | states/R05.bin | UNDEFINED | INTERMEDIATE_STATE | True |
| R06 | 819fb528e418adb39aa0c02aeebcac39b44339f344e2081ac956473c4717a9d8 | b734e5244040216601e44b8a8024a48a845d64b5256edb91bfbcda11e81d6001 | states/R06.bin | UNDEFINED | INTERMEDIATE_STATE | True |
| R07 | 19e05fd0ef4bf6e408d30c1cca4c18df5e003885e46fe37a469c59e21309399e | 819fb528e418adb39aa0c02aeebcac39b44339f344e2081ac956473c4717a9d8 | states/R07.bin | UNDEFINED | INTERMEDIATE_STATE | True |
| R08 | ba3b95ef5b739e089df5dbd42176c779de73d827fea2acc194bffb27047b7b96 | 19e05fd0ef4bf6e408d30c1cca4c18df5e003885e46fe37a469c59e21309399e | states/R08.bin | UNDEFINED | INTERMEDIATE_STATE | True |
| R09 | 4f8bac97d0983703016830e3e86b79e063102cbf27f74ec914cb07aa8fe57158 | ba3b95ef5b739e089df5dbd42176c779de73d827fea2acc194bffb27047b7b96 | states/R09.bin | UNDEFINED | INTERMEDIATE_STATE | True |
| R10 | 5ae2c3a44eb5ac1ce70108fb06e23fa695359dbb42349af6dde0b0b29723355f | 4f8bac97d0983703016830e3e86b79e063102cbf27f74ec914cb07aa8fe57158 | states/R10.bin | UNDEFINED | FINAL_CANDIDATE | True |

*Lineage R00-R10 (null = no frozen reference exists for that round).*
