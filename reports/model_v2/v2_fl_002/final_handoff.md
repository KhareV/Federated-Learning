# V2-FL-002 — matched MODEL_V2 non-IID FedAvg (LABEL / QUANTITY / FEATURE-NOISE / COMBINED)

**Result: PASS** (V2FLG1 = PASS; performance direction is not a gate criterion). Entry `d67dfde`; method commit `a03fdd8` (pre-result, V2FLG1 defined there); result commit follows.

## Method
Frozen `NONIID_{LABEL,QUANTITY,FEATURE,COMBINED}_V1` manifests and `FL_FEATURE_NOISE_V1` reused by SHA (never regenerated); every condition starts independently from FL_INIT_V2 (round-0 sha `6a2923ca…a572f`, AUPRC 0.25769234928353735, identical in all four; no sequential transfer, no warm start). T025/T026 budget verbatim (8x8 clients, 50 rounds, 1 epoch, batch 64, AdamW 1e-3/1e-4 reset each round, global pos_weight 1.7157717177396683, SAMPLE_COUNT_WEIGHTED_MODEL_DELTA_V1, FL_STATE_TRANSPORT_V1, shuffle namespace FL_IID_V1). Validation is the clean 2880-window MIT-BIH VALIDATION set (never a client, never noised); raw sigmoid, no calibration, CAL_V2 absent.

## Results (clean VALIDATION, development only)
| condition | best round | best AUPRC | round-50 AUPRC | AUROC | F1@0.5 | patient-macro F1 |
|---|---|---|---|---|---|---|
| IID (V2-FL-001) | 38 | 0.8669 | 0.8268 | 0.9299 | 0.7057 | 0.4443 |
| LABEL | 50 | 0.8066 | 0.8066 | 0.9159 | 0.6954 | 0.4206 |
| QUANTITY | 47 | 0.8874 | 0.8797 | 0.9532 | 0.7664 | 0.6622 |
| FEATURE | 50 | 0.8502 | 0.8502 | 0.9310 | 0.6521 | 0.6625 |
| COMBINED | 42 | 0.8202 | 0.8044 | 0.9181 | 0.6849 | 0.4598 |

## V2 non-IID effect vs V2 IID (descriptive; no sign assumed)
| condition | Δ best AUPRC | Δ round-50 AUPRC | Δ AUROC | Δ patient-macro F1 | best-round shift |
|---|---|---|---|---|---|
| LABEL | -0.0603 | -0.0202 | -0.0140 | -0.0237 | +12 |
| QUANTITY | +0.0204 | +0.0528 | +0.0232 | +0.2179 | +9 |
| FEATURE | -0.0168 | +0.0233 | +0.0011 | +0.2182 | +12 |
| COMBINED | -0.0467 | -0.0224 | -0.0118 | +0.0155 | +4 |

## Historical MODEL_V1 (T025/T026, not rerun) vs MODEL_V2 under the same heterogeneity
| condition | V1 best | V2 best | V2−V1 | V1 round-50 | V2 round-50 | V2−V1 | V1/V2 best round | V1/V2 patient-macro F1 |
|---|---|---|---|---|---|---|---|---|
| IID | 0.5062 | 0.8669 | +0.3607 | 0.4002 | 0.8268 | +0.4266 | 1/38 | 0.3081/0.4443 |
| label | 0.5456 | 0.8066 | +0.2611 | 0.5305 | 0.8066 | +0.2761 | 49/50 | 0.0844/0.4206 |
| quantity | 0.5160 | 0.8874 | +0.3713 | 0.4535 | 0.8797 | +0.4261 | 27/47 | 0.4138/0.6622 |
| feature | 0.4929 | 0.8502 | +0.3573 | 0.3157 | 0.8502 | +0.5345 | 1/50 | 0.3081/0.6625 |
| combined | 0.4370 | 0.8202 | +0.3833 | 0.2603 | 0.8044 | +0.5441 | 3/42 | 0.0000/0.4598 |

## Paired validation bootstrap (B=2000, seed 20260927, 7 VALIDATION groups, identical draws)
**DEVELOPMENT DIAGNOSTICS ONLY** — checkpoints are selected on this same VALIDATION partition; these are not untouched-generalization intervals.
| condition | V2 cond − V2 IID: mean [95% CI] | V2 − V1 same condition: mean [95% CI] |
|---|---|---|
| LABEL | -0.063 [-0.294, +0.076] | +0.223 [-0.043, +0.420] |
| QUANTITY | +0.033 [-0.026, +0.178] | +0.345 [+0.112, +0.573] |
| FEATURE | -0.004 [-0.079, +0.120] | +0.341 [+0.140, +0.507] |
| COMBINED | -0.048 [-0.173, +0.090] | +0.351 [+0.170, +0.513] |

## LABEL checkpoint = fixed FedProx baseline for V2-FL-003 (no FedProx run, no μ selected)
`VALIDATION_PATIENT_MACRO_AUPRC_V2` = 0.7247; `VALIDATION_PATIENT_WORST_AUPRC_V2` = 0.0381 (7/7 finite; validation patient groups are evaluation units, not clients).

## Observations (not conclusions)
- The V2 architectural advantage persists under all four frozen heterogeneity conditions (V2−V1 best AUPRC +0.26 to +0.38; lower end LABEL, whose paired CI [−0.043, +0.420] includes 0).
- Within V2, effects vs IID are small relative to the validation uncertainty (all CIs include 0); LABEL and COMBINED are lower, QUANTITY slightly higher; patient-macro F1 differs more than AUPRC.
- LABEL and FEATURE select round 50 (the last round): still improving at the budget edge. The budget was not extended (no retuning).
- LABEL has a very poorly served validation patient (worst patient AUPRC 0.038 vs macro 0.725), which pooled AUPRC hides; this is the baseline FedProx must beat in V2-FL-003.
- Only 7 validation patients; best-round values are selected on VALIDATION and optimistic; round-50 is a fixed-round sensitivity diagnostic, not an independent test estimate.
- Site-local TRAIN diagnostics (mean AUPRC 0.93–0.99; COMBINED has 1 undefined single-class site, preserved as undefined) are TRAIN diagnostics only.

## Accounting / communication / compute
200 rounds, 1600/1600 client updates, 0 failed clients, 0 nonfinite tensors, 0 aggregation failures, 0 loader failures, 0 infrastructure retries. Logical payload 1,926,624 B per direction per round (identical to V2-FL-001), 192,662,400 B total per condition (network traffic not measured). Wall time 3374–3628 s per condition (CPU), 57,553 parameters.

## Firewall / NSTDB role
Accessed: TRAIN, VALIDATION, NSTDB pure-noise records only (ledger `NSTDB_PURE_NOISE_TRAINING_RESOURCE`; FEATURE/COMBINED plus preflight/replay). CALIBRATION, INTERNAL_TEST, INCART, BIDMC, WEARABLE, WEARABLE_SIM: not accessed. **Any future evaluation of these FL models on the same NSTDB noise source is not untouched external evidence.** Feature-noise fixtures reproduce the T026 fixtures exactly (sources, SNR within 0.05 dB, offsets, noisy-sha), deterministic and round-independent.

## Checkpoints (all 8 force-added to Git; `*.pt` is ignored)
- label: best `checkpoints/model_v2/v2_fl_002/FL_LABEL_SKEW_MODEL_V2_V1_best.pt` sha `524f50674dc907f6791c08e7339ee06e338bd6502f14ac8a7e601da52876be82`; round-50 `checkpoints/model_v2/v2_fl_002/FL_LABEL_SKEW_MODEL_V2_V1_round50.pt` sha `5dc1d64b7180bf4ac0feb1322b13fe2c8e120032bd3054b7f4a58bfb41a8c4a8`
- quantity: best `checkpoints/model_v2/v2_fl_002/FL_QUANTITY_SKEW_MODEL_V2_V1_best.pt` sha `7a746369c897239c45adb14d312aa2427eb643a46156db7da5d009aad32b9b47`; round-50 `checkpoints/model_v2/v2_fl_002/FL_QUANTITY_SKEW_MODEL_V2_V1_round50.pt` sha `970f167e980a3847fd8cb2d8ef1aba3f78bfb2aaea782be098a767b340f3502c`
- feature: best `checkpoints/model_v2/v2_fl_002/FL_FEATURE_NOISE_MODEL_V2_V1_best.pt` sha `2e4381aaab044008aa1394cf2fd9a97a4e0280ffa9455ac7db77913a452208ca`; round-50 `checkpoints/model_v2/v2_fl_002/FL_FEATURE_NOISE_MODEL_V2_V1_round50.pt` sha `eddf9264b1fef4f14217b7df68568988f1a21b6675e766db9f9676797c27464f`
- combined: best `checkpoints/model_v2/v2_fl_002/FL_COMBINED_SKEW_MODEL_V2_V1_best.pt` sha `2853733760331fed99ed0e9310e01789de825bac9732344b0c65aa0641cf463a`; round-50 `checkpoints/model_v2/v2_fl_002/FL_COMBINED_SKEW_MODEL_V2_V1_round50.pt` sha `e6ada44aaf9ebd5771ef5e249ec8320c0843fb13478845fbe50e36b3abd8612e`

## Reproducibility
Two fresh-process verifications x 4 conditions: manifest hashes, round-1 replay from FL_INIT_V2 (identical global-state sha), best-round recomputation from the saved log, checkpoint reload with exact VALIDATION-prediction replay, checkpoint hashes — all PASS.

## Process notes
- `scripts/finalize_v2_fl_002_stage1.py` (new, post-freeze evidence helper) runs the frozen finalizer functions before the regression to break a results-test/regression circularity; the frozen finalizer then produced the final criteria. Method files are unchanged since the freeze (audit PASS).
- ruff, `pip check`, chunked pytest: 0 missing / duplicate / unexpected / failed. CI never queried or triggered.

## Decision
V2-FL-002 accepted; V2FLG1 PASS; V2-FL-003 may start (not started).
