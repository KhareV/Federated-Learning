# PTBXL_EXTERNAL_CHECK_V1 — predeclared protocol

Written and committed to the working tree BEFORE any PTB-XL window was scored by any NHM model. The script records this file's SHA-256 in its output. A change after results exist is an amendment (a new version of this file), never a silent edit.

## Purpose and claim boundary
Does a frozen NHM model detect records that contain premature beats on **real 12-lead clinical ECG that no NHM model was ever trained, selected, calibrated or evaluated on** (PTB-XL v1.0.3 was removed from the v2.2 execution scope, so unlike INCART it is not project-exposed)? A second purpose: does adapting a model to a synthetic cohort change its performance on this unseen real ECG?

This is an **extension**, outside the locked scientific scope: PTB-XL has no beat annotations, so the locked `AAMI_SVF_WINDOW_V1` target cannot be applied. The target here is a different, record-level one, `PTBXL_PREMATURE_BEAT_RECORD_V1`. No frozen V1/V2 evidence is changed, nothing is retuned, no model, threshold or calibration is selected from these results, and no clinical, diagnostic or device claim is made. Labels come from cardiologist statements and an extra-beat field, not from beat annotations (see Label sources).

## Data
`data/raw/ptbxl` (PTB-XL v1.0.3, `ptbxl_database.csv`, `scp_statements.csv`, `records500`). One 10 s record = one window. Lead: the signal whose header name is exactly `II` (as for INCART); a record without it is excluded and counted. 500 Hz, 5,000 samples; a record of another length, or with a non-finite or flat (std < 1e-6) lead-II signal, is excluded and counted.

## Preprocessing (PREPROC_V1 family, extension version PREPROC_V1_PTBXL_EXT)
The validated T011 resamplers cover 360 and 257 Hz only and are not edited. For 500 Hz a separate causal decimator is used: a 101-tap Kaiser (beta 5) low-pass FIR with a 100 Hz cut-off, applied forward-only (`lfilter`), keeping every second sample (500 -> 250 Hz). Then the frozen causal `PREPROC_V1_ECG_FILTER_V1` (0.5-40 Hz SOS) and the per-window z-score (`normalize_window_zscore`). The chain is causal; the 2 s pre-roll is a hold of the record's first sample (causal, uses no future sample) and is discarded; the window is the last 2,500 filtered samples (so its first ~0.1 s is the hold, a deterministic group delay). No quality gating and no noise-based exclusion (the dataset's own noise flags are only used to describe errors).

## Label sources (they disagree, so three rules are reported)
* SCP statements: `PVC`, `PAC`, `PRC(S)`, `BIGU`, `TRIGU` (premature complexes and bigeminal/trigeminal patterns). Rhythm disorders (`AFIB`, `AFLT`, `SVTAC`, `SVARR`, `PSVT`) are NOT positives.
* `extra_beats` field: non-empty means extra beats were recorded.
* Paced records (`PACE` statement or any `pacemaker` entry) are excluded (they correspond to the Q class the locked target excludes).

Rules (all on non-paced records):
* **A (primary), union:** positive if either source says premature beats; negative only if neither does.
* **B, agreement:** positive if both sources agree; negative if neither; records where exactly one source says so are excluded.
* **C, statements only:** positive if an SCP statement says so; `extra_beats` ignored.
Secondary population for A: negatives restricted to `NORM` with `SR` (a clean-negative view that removes atrial fibrillation, infarction and similar).

## Evaluation sets
* **Primary:** `strat_fold` 9 and 10 (every record human-validated).
* **Replication:** `strat_fold` 1 to 8. No model is trained or tuned on any fold, so all folds are legitimate evaluation data; the split only separates the higher-quality labels from the larger sample.
Unit of resampling: `patient_id`.

## Models (all frozen; raw probability, fixed threshold 0.5, no calibration)
1. MODEL_V1 (central, frozen). 2. MODEL_V2_FINAL (central). 3. V2-FL-001 round 50 (federated, 50 rounds, real MIT-BIH patients). 4. V2-FL-001 round 38 (its best-validation checkpoint). 5. MODEL_V2_FINAL after 10 federated rounds on the ORIGINAL synthetic cohort (Studio engine, seed as in the cohort manifest). 6. MODEL_V2_FINAL after 10 federated rounds on the REALISTIC synthetic cohort.

## Metrics and statistics
AUROC and AUPRC (primary, threshold-free; AUPRC also as lift = AUPRC / prevalence because prevalence differs between sets), and sensitivity, specificity, precision and F1 at the fixed 0.5 rule. 95 % patient-cluster percentile bootstrap (2,000 resamples, patients resampled with replacement, all their records kept, metric recomputed on the pooled replicate; seed 20271118) for rule A on both sets. Paired differences between models use the same resampled patients. Point estimates only for rules B and C and the clean-negative view.

## Descriptive error analysis (no selection)
For the central V2 on rule A, primary set, the share of negatives flagged at 0.5 by the dataset's own noise flags (`burst_noise`, `static_noise`, `baseline_drift`), by an `AFIB` statement, and the share of positives flagged by the number of extra beats recorded.

## What would make this check uninformative
If every model scores near chance (AUROC ~0.5) the likely causes are a preprocessing mismatch or label unreliability, and the result is reported as inconclusive, not as evidence about the models. Sanity checks printed with the results: window finiteness and z-score, the mean model score for `NORM` records against positives, the agreement between the two label sources.
