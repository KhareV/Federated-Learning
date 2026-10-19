# PTBXL_EXTERNAL_CHECK_V1 — results

Protocol: `docs/ptbxl/PTBXL_EXTERNAL_CHECK_V1.md` (SHA-256 `a4bf4af176e6ff32…`, recorded in `reports/ptbxl/external_check_v1.json`; written before any score existed and unchanged). Reproduce: `python -m scripts.ptbxl_external_check` (about 30 minutes; the synthetic-adapted states are cached after the first run).

**What this is.** Frozen NHM models scored on real 12-lead clinical ECG (lead II, PTB-XL v1.0.3) that no model was trained, selected, calibrated or evaluated on, with the record-level target `PTBXL_PREMATURE_BEAT_RECORD_V1` (a record is positive when a cardiologist statement or the extra-beat field says it contains premature beats). 21,535 non-paced records, none excluded for a missing lead, length or flat signal. **What it is not:** the locked beat-level `AAMI_SVF_WINDOW_V1` target (PTB-XL has no beat annotations), a clinical or diagnostic result, or a calibrated one (fixed 0.5 rule, no calibration). Intervals are 95 % patient-cluster bootstrap (2,000 resamples).

## Headline (label rule A, union of the two label sources)

| Model | Primary, folds 9-10 (4,336 records, 476 positives, 3,809 patients): AUROC / AUPRC / F1 at 0.5 | Replication, folds 1-8 (17,199 records, 1,893 positives): AUROC / AUPRC / F1 |
|---|---|---|
| MODEL_V1 (central, frozen) | 0.701 [0.674, 0.729] / 0.313 / 0.324 | 0.679 / 0.310 / 0.301 |
| **MODEL_V2_FINAL (central)** | **0.911 [0.896, 0.926] / 0.705 [0.665, 0.743] / 0.547** | **0.896 / 0.674 / 0.527** |
| V2-FL-001 round 50 (federated, 50 rounds) | 0.910 [0.893, 0.927] / 0.731 [0.693, 0.771] / 0.662 | 0.897 / 0.703 / 0.634 |
| V2-FL-001 round 38 (best-validation) | 0.910 / 0.720 / 0.636 | 0.899 / 0.697 / 0.633 |
| central V2 + 10 rounds on the original synthetic cohort | 0.875 / 0.534 / 0.281 | 0.863 / 0.540 / 0.277 |
| central V2 + 10 rounds on the realistic synthetic cohort | 0.865 / 0.476 / 0.490 | 0.855 / 0.438 / 0.482 |

Prevalence is 0.110, so AUPRC 0.705 is a lift of 6.4 over chance. Paired differences against the central V2 (same resampled patients, mean difference with 95 % interval; primary set, replication in the results file):
* MODEL_V1: AUROC -0.210 [-0.237, -0.184], AUPRC -0.389 [-0.432, -0.347].
* Federated round 50: AUROC -0.001 [-0.011, +0.009] (no difference), AUPRC +0.027 [+0.001, +0.051] (replication +0.028 [+0.015, +0.042]); F1 at 0.5 is higher because it flags fewer false positives (specificity 0.95 against 0.85, sensitivity 0.71 against 0.83).
* Adapted to the original synthetic cohort: AUROC -0.036 [-0.049, -0.023], AUPRC -0.169 [-0.203, -0.135]; at 0.5 it flags almost everything (sensitivity 0.96, specificity 0.40).
* Adapted to the realistic synthetic cohort: AUROC -0.046 [-0.057, -0.035], AUPRC -0.229 [-0.265, -0.191].

## What this establishes
1. **The pretrained V2 transfers to real, project-unexposed ECG it was never trained on.** On records where both label sources agree (rule B) its AUROC is 0.981 and AUPRC 0.824; with clean negatives (normal sinus rhythm only) AUROC is 0.954. The label source matters: the two sources agree on only about half of the premature-beat records (1,052 both, 472 statement only, 902 extra-beats only), and the model flags 98 % of the records both sources agree on, 83 % of statement-only and 64 % of extra-beats-only records.
2. **V2 is clearly better than V1 on unseen real ECG** (paired AUROC difference +0.21, interval excludes zero by a wide margin). This is stronger than the earlier internal comparison, where the release-seed paired interval crossed zero; it is a different, record-level target, so it supports V2 as the runtime model without rewriting that earlier disposition.
3. **Federated training on real patients matches centralized training** (AUROC identical; AUPRC slightly better, interval just above zero on the primary set and clearly above on the replication set).
4. **Adapting to a synthetic cohort hurts on unseen real ECG, and by more than the MIT-BIH validation probe suggested** (AUROC -0.04 to -0.05, AUPRC -0.17 to -0.23; the original-cohort adaptation loses specificity). A synthetic-cohort candidate is therefore not a better ECG model than the released one, now shown on data nobody selected anything on.

## Descriptive error analysis (central V2, rule A, primary set; no selection)
Negatives are flagged 15 % of the time overall, 3 % for normal sinus rhythm, and **74 % for records with atrial fibrillation** (irregular rhythm without premature beats: about 30 % of all false positives). Negatives with the dataset's own noise flags are flagged about as often as the rest (baseline drift 14 %, static noise 15 %, burst noise 13 %), unlike the synthetic cohort, where large motion artifacts drove 82 % of false positives; the noise flags are coarse and the burst-noise group is small (76 records), so this is suggestive only. Sensitivity rises with the number of extra beats recorded (84 % for one, 96 % for three or more).

## Limits (unchanged by the result)
Record-level labels from cardiologist statements and an extra-beat field, not beat annotations; the two sources disagree; positives and negatives are not defined by the locked beat rule; 12-lead records read on lead II only; one 10 s window per record; PTB-XL is one population (German hospital recordings), so this is one external check, not general validity. No threshold, calibration or model was selected from it, and no clinical claim follows.

## Can adapting to a synthetic cohort be made safer? (diagnostic, after the main result)
`python -m scripts.fl_mitigation_ptbxl` (`reports/ptbxl/mitigation.json`): the same start (central V2) adapted three other ways and scored the same way (rule A, paired against the central V2, one run per cell). Summary of the primary-set change in AUROC (full table and the recorded-noise cohort in `docs/realistic/REALISTIC_COHORT_V3.md`):
* **Fewer rounds helps, but only where the cohort is not harmful to begin with:** 3 FedAvg rounds on the original cohort -0.009 (interval touches zero) against -0.036 for 10 rounds; on the invented-noise realistic cohort 3 rounds was worse (-0.073) because it ends inside the transient dip of rounds 2 to 5.
* **FedProx did not help:** the engine's frozen mu = 0.1 matched FedAvg; a stronger mu = 1.0 (patched inside the script only) recovered a little AUPRC and no more than 0.006 AUROC.
* **The cohort matters more than the optimiser:** adapting on the recorded-noise cohort costs least at every setting (10 rounds -0.024, 3 rounds -0.006).
These are single runs and a diagnostic, not a method selection for any run.

