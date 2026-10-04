# C-V2-FL-003-FREEZE-INTEGRITY — handoff

**Result: PASS.** Provenance/control correction only; V2-FL-003 scientific result unchanged (VALID); V2FLG2 remains PASS; `FEDPROX_MU_V2` = 0.1 unchanged. No training, no new μ, no reselection, no held-out access.

## Chronology
Entry/result commit `8794364`; V2-FL-003 method `dd9d9df`, selection-freeze `89accff` (all preserved, none amended); corrective METHOD commit `4984abe`; corrective result commit follows.

## The defect (reconstructed mechanically)
The V2-FL-003 method freeze pinned `scripts/finalize_v2_fl_003_evidence.py` at `21c640c209577c999d17a30b961d0f74ef1d12e09a2f187e7e1ac30d1bf5ea75`. At the result commit the file was `75692f3260c4832d0abc077c6ce9cdc57c28fdde444fc6f0ce537eab180216c3` — not matching. The post-freeze change had two parts: **A** a legitimate evidence bug fix (eager dict default → lazy communication-byte helper) and **B** a freeze-control weakening (`AMENDMENT_ALLOWED` self-exemption and `method_unchanged := no *unexpected* changes`). The handoff disclosed A and called the audit a PASS; B made that PASS self-referential.

## Correction
- Frozen finalizer **restored byte-identically** (`21c640c209577c999d17a30b961d0f74ef1d12e09a2f187e7e1ac30d1bf5ea75`); it keeps its historical eager-default bug as part of the frozen record. Self-exemption logic is gone from it and absent from the successor.
- Additive successor `scripts/finalize_v2_fl_003_evidence_v2.py` (`V2_FL_003_EVIDENCE_FINALIZER_V2`, sha `ed529780fec5c923df1713f0bea37328f54dbdeb14c8eace828ad9dd43c5def3`): reconstruction-only; the sole code change is the lazy, schema-aware `_logical_bytes`; AST-equal to the frozen file for `bootstrap`, `_patient_stats`, `fedavg_paths`, `selected_mu`, `_runtime`. It reads committed evidence, writes to a separate directory, and the firewall is rebuilt from the ledger as committed at `8794364`.
- `correction_method.json` (committed in the corrective METHOD commit before this attestation) binds the 14 checkpoints and all 7 result / prediction / round-log files, the selection table and lock, the bootstrap implementation and finalizer hashes.
- Dry-run disclosure: the successor was run once against the committed evidence before it was frozen (equality PASS); that output was discarded; the canonical run came after the freeze commit.

## Independent reconstruction (8 artifacts, all byte-for-value identical)
`accounting_audit.json`, `chronology_audit.json`, `communication_compute.json`, `fedavg_vs_fedprox_comparison.json`, `heldout_firewall_audit.json`, `paired_bootstrap.json`, `patient_level_comparison.json`, `selection_audit.json`. Selected μ 0.1; ranking 0.1 > 0.001 > 0.01; 2800/2800 updates; INTERNAL_TEST accessed = false; candidate-table sha `27497d341642…` matches the lock.

## μ=0 re-verified (not scientific retraining)
loss delta 0.0, max gradient delta 0.0, 8 LABEL local-update deltas 0.0, aggregate sha `3f57e799f19a…` = stored V2-FL-002 LABEL round 1. Written to `mu0_rerun/` (the historical `mu0_equivalence.json` is untouched).

## Replays
Two fresh processes x 7 scientific runs: best round, round-1 SHA, checkpoint SHA, VALIDATION predictions, selection (x2) and μ=0 aggregate all reproduced.

## Lifecycle-test drift audit (four files, not three)
| file | classification |
|---|---|
| `tests/test_model_v2_control_plane.py` | FORWARD_LIFECYCLE_ONLY (old `ed5b481a96` → `40235cb690`) |
| `tests/test_v2_fl_001_results.py` | FORWARD_LIFECYCLE_ONLY (old `a87e5e31dc` → `e68e0adef5`) |
| `tests/test_v2_fl_002_method.py` | FORWARD_LIFECYCLE_ONLY (old `ec7d09bca3` → `ccc953e5ca`) |
| `tests/test_v2_fl_002_results.py` | FORWARD_LIFECYCLE_ONLY (old `54a1d47ff4` → `8f8842492a`) |

Every changed assertion only admits the completed V2-FL-003/V2FLG2 state (or adds V2-FL-003/V2FLG2 to an exact expected set); none touches hashes, scientific configuration, firewall, patient integrity, method parameters, reproducibility or prerequisite logic. The two-element relaxations (`{NOT_STARTED, PASS}` for V2-FL-003 in the older results/method tests) are superseded by the new **strict** `tests/test_model_v2_current_lifecycle.py` with exact statuses (V2-FL-001/002/003 PASS, V2FLG0/1/2 PASS, V2-FL-EVAL-001/004/005 and V2-014 NOT_STARTED, V2-005 SKIPPED_BY_PROTOCOL; unknown vocabulary rejected). That file is the single test updated at each future phase transition.

## Historical freeze scope
- **V2-FL-002**: 32 pinned files; all scientific-method files byte-identical; the only drift is `tests/test_v2_fl_002_method.py` (forward-lifecycle assertion). **Not claimed byte-identical today.** Historical freeze unrewritten.
- **V2-FL-001**: 19 files, no drift. **V2-FL-003**: 36 files, no drift after the restore (BYTE-CLEAN).

## Corrective V2FLG2 attestation: PASS
All criteria True: scientific outputs unchanged; μ unchanged; finalizer restored to exact SHA; successor reproduces all evidence; self-exemption removed; no unclassified method drift; V2-FL-002 scientific method unchanged; lifecycle drift control-only; μ=0 exact; two-process replays; INTERNAL_TEST/CALIBRATION/INCART/BIDMC untouched; regression PASS. The historical `v2flg2_criteria.json`, `method_immutability_audit.json` and `run_manifest.json` are preserved unaltered.

## Tests
ruff, `pip check`, chunked pytest (0 missing / duplicate / unexpected / failed), monolithic 2215 passed. CI never queried or triggered.

## Decision
V2-FL-003 accepted cleanly; V2FLG2 accepted cleanly; V2-FL-EVAL-001 allowed (not started).
