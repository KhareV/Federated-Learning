# V2-FL-EVAL-001 — frozen FL family held-out + external evaluation (handoff)

**Result: PASS (V2FLEG0 = PASS; performance-independent).** Observational evidence only: no model promotion, no calibration, no tuning, no selection. Scientific model fits added 0; federated client updates added 0.

## Terminology (claim boundary)
- **INTERNAL_TEST** = *held out from the V2 federated development lineage* (V2-FL-001/002/003 never accessed it; all checkpoints and μ were frozen without it). The broader project evaluated centralized models on it earlier → **NOT project-globally unseen**.
- **INCART** = *post-freeze external FL second-look* on a previously project-exposed dataset → **NOT project-blind, NOT untouched external validation**. INCART selected no architecture/round/μ/hyperparameter/manifest.

## Chronology
Entry `0c51b8e` → pre-access METHOD commit `39f20cb` → pre-access amendment `92e4c67` (audit script now records the true method commit; no exposure existed) → pre-access audit `7a0a9f5` (all checks PASS, guards NOT_STARTED, regression PASS) → ONE one-shot family invocation → prediction commit `a06de4e` → statistics commit `6d8d1dc` (prediction-only) → this result commit.

## Frozen family (V2_FL_TEST_FAMILY_V1, 20 checkpoints)
V1/V2 × FedAvg/FedProx × IID/LABEL/QUANTITY/FEATURE/COMBINED, development-selected best-VALIDATION checkpoints (V1 FedProx μ=0.01 per FEDPROX_MU_V1; V2 FedProx μ=0.1 per FEDPROX_MU_V2; V2 FedProx LABEL = the selected μ=0.1 candidate alias). Excluded and never evaluated: V2 μ=0.001/0.01 candidates, rejected V1 candidates, any round-50/intermediate checkpoint, MODEL_V2_FINAL, centralized MODEL_V1. Checkpoint hashes in `configs/model_v2/fl_test_family_v1.yaml` and the family lock.

## Protocol
Raw `sigmoid(raw_logit)`, threshold 0.5 (`>=`, `FL_EVAL_RAW_THRESHOLD_0P5_V1`), PER_WINDOW_ZSCORE_V1 → float32 [1,2500]; **no CAL_V1/CAL_V2/temperature/threshold fitting; CALIBRATION not accessed**. Patient-cluster bootstrap B=2000, seed 20260927, PCG64, multiplicity preserved (6 slots/replicate INTERNAL_TEST; 32 INCART), no redraw, shared draws for every model and paired contrast; draws reproduce the frozen T018/T020 npz exactly; nominal 95% percentile CIs, no p-values, no multiplicity adjustment. One orchestration command, one guarded invocation per dataset (guards COMPLETED; a second begin raises `ALREADY_CONSUMED`; historical guards untouched).

## Populations (verified against frozen expectations before inference)
INTERNAL_TEST: 7 frozen groups, **6 contributing** (MITDB_P107 has 0 eligible windows), 2520 candidate → **2157 eligible** (1156 pos / 1001 neg; prevalence 0.536). INCART: 75 records, **32 patient clusters** (never 75), **26864 eligible** (prevalence 0.487). All 20 models have identical ordered example-ID sets. Development VALIDATION prevalence ≈ 0.235, so absolute AUPRC is not comparable across datasets.

**Small-N limitation:** INTERNAL_TEST has 6 contributing clusters; intervals are wide/unstable and patient-level metrics are not population estimates.

## INTERNAL_TEST — FL-LINEAGE HELD-OUT: all 20 models
| model | AUPRC [95% CI] | AUROC | F1@0.5 | patient-macro F1 [95% CI] | prec | sens | spec | BCE |
|---|---|---|---|---|---|---|---|---|
| V1_FEDAVG_COMBINED | 0.9297 [0.771, 0.993] | 0.931 | 0.000 | 0.000 [0.000, 0.000] | 0.000 | 0.000 | 1.000 | 0.690 |
| V1_FEDAVG_FEATURE | 0.8566 [0.729, 0.994] | 0.905 | 0.698 | 0.592 [0.277, 0.900] | 0.536 | 1.000 | 0.000 | 0.681 |
| V1_FEDAVG_IID | 0.8774 [0.768, 0.996] | 0.918 | 0.698 | 0.592 [0.277, 0.900] | 0.536 | 1.000 | 0.000 | 0.678 |
| V1_FEDAVG_LABEL | 0.8395 [0.548, 0.986] | 0.820 | 0.231 | 0.108 [0.001, 0.314] | 0.962 | 0.131 | 0.994 | 0.670 |
| V1_FEDAVG_QUANTITY | 0.8277 [0.589, 0.965] | 0.756 | 0.647 | 0.399 [0.092, 0.734] | 0.938 | 0.494 | 0.962 | 0.592 |
| V1_FEDPROX_COMBINED | 0.9338 [0.770, 0.991] | 0.932 | 0.000 | 0.000 [0.000, 0.000] | 0.000 | 0.000 | 1.000 | 0.693 |
| V1_FEDPROX_FEATURE | 0.8551 [0.725, 0.994] | 0.903 | 0.698 | 0.592 [0.277, 0.900] | 0.536 | 1.000 | 0.000 | 0.681 |
| V1_FEDPROX_IID | 0.8749 [0.760, 0.996] | 0.915 | 0.698 | 0.592 [0.277, 0.900] | 0.536 | 1.000 | 0.000 | 0.679 |
| V1_FEDPROX_LABEL | 0.7283 [0.289, 0.986] | 0.705 | 0.201 | 0.096 [0.000, 0.281] | 0.956 | 0.112 | 0.994 | 0.682 |
| V1_FEDPROX_QUANTITY | 0.8575 [0.671, 0.967] | 0.804 | 0.691 | 0.439 [0.124, 0.780] | 0.938 | 0.547 | 0.958 | 0.559 |
| V2_FEDAVG_COMBINED | 0.9987 [0.994, 1.000] | 0.998 | 0.977 | 0.744 [0.417, 0.981] | 0.995 | 0.960 | 0.994 | 0.083 |
| V2_FEDAVG_FEATURE | 0.9997 [0.999, 1.000] | 1.000 | 0.994 | 0.822 [0.491, 0.994] | 0.994 | 0.994 | 0.993 | 0.024 |
| V2_FEDAVG_IID | 0.9989 [0.996, 1.000] | 0.998 | 0.992 | 0.827 [0.495, 0.997] | 0.995 | 0.990 | 0.994 | 0.031 |
| V2_FEDAVG_LABEL | 0.9989 [0.995, 1.000] | 0.998 | 0.967 | 0.668 [0.338, 0.971] | 0.997 | 0.939 | 0.997 | 0.135 |
| V2_FEDAVG_QUANTITY | 0.9988 [0.996, 1.000] | 0.998 | 0.992 | 0.798 [0.468, 0.994] | 0.998 | 0.985 | 0.998 | 0.029 |
| V2_FEDPROX_COMBINED | 0.9982 [0.991, 1.000] | 0.998 | 0.980 | 0.732 [0.404, 0.984] | 0.995 | 0.965 | 0.994 | 0.075 |
| V2_FEDPROX_FEATURE | 0.9997 [0.999, 1.000] | 1.000 | 0.994 | 0.822 [0.491, 0.994] | 0.996 | 0.992 | 0.995 | 0.024 |
| V2_FEDPROX_IID | 0.9995 [0.998, 1.000] | 0.999 | 0.994 | 0.828 [0.496, 0.998] | 0.994 | 0.993 | 0.993 | 0.027 |
| V2_FEDPROX_LABEL | 0.9928 [0.959, 0.999] | 0.989 | 0.955 | 0.634 [0.305, 0.961] | 0.994 | 0.919 | 0.994 | 0.186 |
| V2_FEDPROX_QUANTITY | 0.9986 [0.996, 1.000] | 0.997 | 0.991 | 0.797 [0.467, 0.993] | 0.998 | 0.984 | 0.998 | 0.033 |

## INCART — POST-FREEZE EXTERNAL FL SECOND-LOOK, NOT PROJECT-BLIND: all 20 models
| model | AUPRC [95% CI] | AUROC | F1@0.5 | patient-macro F1 [95% CI] | prec | sens | spec | BCE |
|---|---|---|---|---|---|---|---|---|
| V1_FEDAVG_COMBINED | 0.6057 [0.485, 0.739] | 0.664 | 0.000 | 0.000 [0.000, 0.000] | 0.000 | 0.000 | 1.000 | 0.689 |
| V1_FEDAVG_FEATURE | 0.6559 [0.488, 0.825] | 0.704 | 0.657 | 0.568 [0.450, 0.687] | 0.489 | 0.999 | 0.008 | 0.690 |
| V1_FEDAVG_IID | 0.6398 [0.483, 0.804] | 0.694 | 0.660 | 0.570 [0.453, 0.689] | 0.494 | 0.995 | 0.030 | 0.689 |
| V1_FEDAVG_LABEL | 0.6874 [0.546, 0.828] | 0.719 | 0.333 | 0.241 [0.150, 0.334] | 0.832 | 0.208 | 0.960 | 0.661 |
| V1_FEDAVG_QUANTITY | 0.7553 [0.577, 0.888] | 0.759 | 0.677 | 0.561 [0.444, 0.675] | 0.648 | 0.710 | 0.633 | 0.590 |
| V1_FEDPROX_COMBINED | 0.6058 [0.487, 0.738] | 0.662 | 0.000 | 0.000 [0.000, 0.000] | 0.000 | 0.000 | 1.000 | 0.690 |
| V1_FEDPROX_FEATURE | 0.6589 [0.490, 0.830] | 0.706 | 0.656 | 0.568 [0.450, 0.687] | 0.488 | 1.000 | 0.004 | 0.690 |
| V1_FEDPROX_IID | 0.6405 [0.483, 0.806] | 0.694 | 0.659 | 0.570 [0.452, 0.689] | 0.492 | 0.997 | 0.022 | 0.690 |
| V1_FEDPROX_LABEL | 0.6678 [0.520, 0.820] | 0.706 | 0.240 | 0.179 [0.102, 0.262] | 0.771 | 0.142 | 0.960 | 0.668 |
| V1_FEDPROX_QUANTITY | 0.7579 [0.582, 0.891] | 0.762 | 0.683 | 0.566 [0.449, 0.680] | 0.647 | 0.722 | 0.626 | 0.597 |
| V2_FEDAVG_COMBINED | 0.9452 [0.896, 0.977] | 0.943 | 0.846 | 0.773 [0.678, 0.859] | 0.858 | 0.835 | 0.869 | 0.306 |
| V2_FEDAVG_FEATURE | 0.9885 [0.972, 0.996] | 0.987 | 0.947 | 0.893 [0.841, 0.938] | 0.959 | 0.936 | 0.962 | 0.149 |
| V2_FEDAVG_IID | 0.9766 [0.944, 0.994] | 0.976 | 0.923 | 0.852 [0.767, 0.923] | 0.921 | 0.926 | 0.925 | 0.242 |
| V2_FEDAVG_LABEL | 0.9750 [0.942, 0.993] | 0.973 | 0.871 | 0.773 [0.681, 0.858] | 0.972 | 0.789 | 0.978 | 0.283 |
| V2_FEDAVG_QUANTITY | 0.9866 [0.968, 0.996] | 0.985 | 0.936 | 0.872 [0.797, 0.935] | 0.924 | 0.947 | 0.926 | 0.180 |
| V2_FEDPROX_COMBINED | 0.9282 [0.860, 0.971] | 0.926 | 0.842 | 0.757 [0.657, 0.848] | 0.808 | 0.878 | 0.802 | 0.370 |
| V2_FEDPROX_FEATURE | 0.9869 [0.970, 0.995] | 0.985 | 0.942 | 0.883 [0.832, 0.927] | 0.965 | 0.919 | 0.968 | 0.160 |
| V2_FEDPROX_IID | 0.9723 [0.932, 0.994] | 0.973 | 0.913 | 0.851 [0.757, 0.926] | 0.881 | 0.948 | 0.878 | 0.298 |
| V2_FEDPROX_LABEL | 0.9678 [0.933, 0.988] | 0.964 | 0.839 | 0.745 [0.649, 0.833] | 0.967 | 0.740 | 0.976 | 0.328 |
| V2_FEDPROX_QUANTITY | 0.9861 [0.967, 0.996] | 0.985 | 0.940 | 0.888 [0.820, 0.945] | 0.945 | 0.935 | 0.949 | 0.169 |

## Primary estimands (INTERNAL_TEST)
- **V2 FedAvg IID**: AUPRC 0.9989 [0.996, 1.000]; patient-macro F1@0.5 0.827 [0.495, 0.997]; AUROC 0.998; F1 0.992; sens 0.990; spec 0.994.
- **Architecture effect, V2 FedAvg IID − V1 FedAvg IID**: INTERNAL_TEST AUPRC +0.121 [+0.003, +0.231], patient-macro F1 +0.235 [+0.024, +0.540]; INCART AUPRC +0.337 [+0.184, +0.480], patient-macro F1 +0.282 [+0.191, +0.372].
- **Secondary method effect, V2 FedProx IID − V2 FedAvg IID**: INTERNAL_TEST AUPRC +0.001 [-0.000, +0.002]; INCART AUPRC -0.004 [-0.014, +0.002].

## Architecture effect by condition (V2 − V1, same algorithm and heterogeneity; AUPRC delta [paired 95% CI] / patient-macro-F1 delta)
| contrast | INTERNAL_TEST AUPRC | INTERNAL pm-F1 | INCART AUPRC | INCART pm-F1 |
|---|---|---|---|---|
| V2_FEDAVG_IID_minus_V1_FEDAVG_IID | +0.121 [+0.003, +0.231] | +0.235 [+0.024, +0.540] | +0.337 [+0.184, +0.480] | +0.282 [+0.191, +0.372] |
| V2_FEDAVG_LABEL_minus_V1_FEDAVG_LABEL | +0.159 [+0.014, +0.450] | +0.560 [+0.238, +0.855] | +0.288 [+0.158, +0.408] | +0.532 [+0.415, +0.647] |
| V2_FEDAVG_QUANTITY_minus_V1_FEDAVG_QUANTITY | +0.171 [+0.033, +0.409] | +0.399 [+0.127, +0.698] | +0.231 [+0.105, +0.399] | +0.311 [+0.209, +0.412] |
| V2_FEDAVG_FEATURE_minus_V1_FEDAVG_FEATURE | +0.143 [+0.006, +0.270] | +0.231 [+0.024, +0.522] | +0.333 [+0.168, +0.495] | +0.325 [+0.230, +0.420] |
| V2_FEDAVG_COMBINED_minus_V1_FEDAVG_COMBINED | +0.069 [+0.007, +0.223] | +0.744 [+0.417, +0.981] | +0.340 [+0.221, +0.437] | +0.773 [+0.678, +0.859] |
| V2_FEDPROX_IID_minus_V1_FEDPROX_IID | +0.125 [+0.004, +0.239] | +0.236 [+0.024, +0.541] | +0.332 [+0.177, +0.475] | +0.282 [+0.189, +0.375] |
| V2_FEDPROX_LABEL_minus_V1_FEDPROX_LABEL | +0.264 [+0.013, +0.683] | +0.538 [+0.215, +0.851] | +0.300 [+0.154, +0.424] | +0.566 [+0.449, +0.676] |
| V2_FEDPROX_QUANTITY_minus_V1_FEDPROX_QUANTITY | +0.141 [+0.031, +0.327] | +0.358 [+0.097, +0.665] | +0.228 [+0.101, +0.395] | +0.323 [+0.216, +0.430] |
| V2_FEDPROX_FEATURE_minus_V1_FEDPROX_FEATURE | +0.145 [+0.006, +0.274] | +0.231 [+0.024, +0.522] | +0.328 [+0.164, +0.492] | +0.315 [+0.220, +0.408] |
| V2_FEDPROX_COMBINED_minus_V1_FEDPROX_COMBINED | +0.064 [+0.008, +0.223] | +0.732 [+0.404, +0.984] | +0.322 [+0.208, +0.414] | +0.757 [+0.657, +0.848] |

## FedProx effect within V2 (V2 FedProx − V2 FedAvg)
| condition | INTERNAL AUPRC | INTERNAL pm-F1 | INCART AUPRC | INCART pm-F1 |
|---|---|---|---|---|
| IID | +0.001 [-0.000, +0.002] | +0.001 [+0.000, +0.002] | -0.004 [-0.014, +0.002] | -0.001 [-0.025, +0.024] |
| LABEL | -0.006 [-0.036, -0.001] | -0.034 [-0.081, -0.005] | -0.007 [-0.016, -0.000] | -0.028 [-0.052, -0.007] |
| QUANTITY | -0.000 [-0.001, +0.000] | -0.001 [-0.003, +0.001] | -0.000 [-0.003, +0.002] | +0.017 [-0.005, +0.045] |
| FEATURE | +0.000 [-0.000, +0.000] | -0.000 [-0.001, +0.001] | -0.002 [-0.005, +0.001] | -0.010 [-0.031, +0.008] |
| COMBINED | -0.000 [-0.004, -0.000] | -0.012 [-0.041, +0.006] | -0.017 [-0.037, -0.004] | -0.016 [-0.060, +0.019] |

Full paired contrasts (23 per dataset incl. V2 condition − V2 IID) and shift tables: `tables/paired_effects.csv`, `tables/shift_v2_models.csv`, `shift_tables.json` (development→INTERNAL_TEST and INTERNAL_TEST→INCART are *shift descriptors*, not causal and not calibration drift).

## Findings, exactly as observed
1. **The V2 architectural advantage survives federated training on held-out and external data.** In all 10 same-algorithm/same-condition contrasts, on both datasets, V2 > V1 for pooled AUPRC and for patient-macro F1@0.5, and every paired 95% CI excludes 0 — but the INTERNAL_TEST lower bounds are small for some contrasts (e.g. IID AUPRC +0.003) because only 6 clusters exist.
2. **Threshold caveat for patient-macro F1:** several V1 models are degenerate at the raw 0.5 threshold on these datasets (V1 FedAvg IID/FEATURE and FedProx IID/FEATURE: sensitivity ≈ 1.0, specificity ≈ 0; V1 COMBINED: sensitivity 0). The V1→V2 patient-macro-F1 deltas therefore partly reflect V1's uncalibrated raw-probability operating point; the threshold-independent AUPRC/AUROC deltas are the cleaner architecture comparison.
3. **V2 FedProx vs V2 FedAvg is essentially neutral:** INTERNAL_TEST differences are tiny (|ΔAUPRC| ≤ 0.007); INCART shows small negatives in AUPRC (−0.0005 to −0.017). μ=0.1 gives no consistent held-out benefit, consistent with FedProx being a secondary comparison; no promotion.
4. **Heterogeneity conditions:** V2 FedAvg stays near AUPRC 0.999 on INTERNAL_TEST in all conditions (ceiling-like; COMBINED lowest on patient-macro F1) and 0.945–0.989 on INCART. These are training-condition effects, not deployment candidates; no condition was ranked or chosen.
5. **Context (HISTORICAL FROZEN REFERENCE, centralized, not rerun):** MODEL_V2_FINAL AUPRC 0.9995 (INTERNAL_TEST) / 0.9700 (INCART); MODEL_V1 0.9089 / 0.7892. The V2 FL models are numerically close to the centralized V2 reference on these datasets; the comparison used different calibration/threshold conventions and is context only.
6. **Not claimed:** no superiority across datasets beyond the contrasts above, no clinical performance, no operational-model change (MODEL_V1 remains the software default), no best-of-20 selection, no p-values or multiplicity-adjusted claims.

## Reproducibility / integrity
All statistics were computed only from the frozen prediction tables; two fresh-process reproductions (no checkpoint loaded, no source data opened) are byte/value-identical to the canonical statistics. Method files (hash-pinned at freeze) are unchanged after exposure; no post-access scientific edit. Firewall: INTERNAL_TEST and INCART only (via the one-shot guards); CALIBRATION, NSTDB, BIDMC, WEARABLE, WEARABLE_SIM not accessed; CAL_V1/CAL_V2 not used; threshold not tuned. Protected artifacts (all 20 checkpoints, FL/FedProx locks, protocols, historical T018/T020 evidence, MODEL_V1/V2_FINAL/CALs) unchanged.

## Process notes / disclosures
- A pre-exposure amendment (`92e4c67`) corrected the audit script's recorded method commit; no held-out inference existed then. The post-exposure chunked regression writes to `post_exposure_regression/` so the committed pre-access regression evidence is preserved.
- Lifecycle tests: `tests/test_model_v2_current_lifecycle.py` (control state, exact PASS/NOT_STARTED map) transitioned prospectively; five older control/lifecycle tests were adjusted to admit the completed state. One of them (`tests/test_v2_fl_003_method.py`) is hash-pinned by the V2-FL-003 freeze; all V2-FL-003 scientific-method (non-test) files remain byte-identical. Classified in `lifecycle_test_drift_audit.json`.
- ruff, `pip check`, chunked pytest (0 missing / duplicate / unexpected / failed) PASS. CI never queried or triggered.

## Decision
V2-FL-EVAL-001 accepted; V2FLEG0 PASS; V2-FL-004 may start (not started).
