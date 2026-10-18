# Realistic synthetic cohort (WEARABLE_SIM_REALISTIC_ECG_V2)

Status: built, tested and **available as a selectable option** in the Studio (see "Using it" below). The original cohort stays the default, and the original cohort and every frozen FL10 artefact are untouched.

## Why
The original synthetic cohort labelled a window positive when a *scheduled* synthetic event lay inside it, and the generator had drawn that event into the ECG as an added Gaussian bump on top of a perfectly regular rhythm.
On the frozen FL10 holdout a six-feature logistic regression (fitted on the training cohort only) reached AUROC 0.993 and F1 0.925 at the fixed 0.5 threshold, while the 10-round federated model reached AUROC 0.966 and, at 0.5, predicted every window positive (F1 0.350).
The task was easy, so its scores said little.

## What the new generator models (`simulation/realistic_ecg_v2.py`)
* Beat-to-beat rhythm variability (respiratory sinus arrhythmia, a 0.1 Hz component, jitter), slow heart-rate drift, QT shortening with rate, per-beat amplitude variation, per-participant morphology and gain.
* Ectopy as rhythm: an ectopic beat replaces a sinus beat and comes early.
  * V (PVC-like): no P wave, wide slurred QRS of either polarity and variable size (some smaller than the normal beat), discordant T, compensatory pause (sinus beats inside the refractory period are blocked; an early coupling can let one through, an interpolated PVC).
  * S (PAC-like): premature narrow QRS, absent / inverted / early P, sinus reset (no full compensatory pause).
  * F (fusion-like): near-normal timing, blended morphology.
  * Isolated beats, couplets, bigeminy, trigeminy and short runs; ectopic burden differs between people, and a few evaluation participants have none.
* Hard negatives: baseline wander, non-stationary muscle noise, mains pickup, motion artifacts that look like wide QRS complexes, electrode pops.
* Labels are ANNOTATIONS, not the hidden truth: 2 % of true ectopic beats are missed, 4 % of large motion artifacts are marked as ectopy, annotation times jitter by 12 ms.

Everything is a Gaussian-sum approximation with plausible round-number parameters. It is not electrophysiology and not a population statistic. No clinical claim.

## Cohorts (`simulation/fl_cohort_realistic_v2.py`)
* Training: 8 clients on the same logical sites `SIM_FL_SITE_00..07` as the original cohort (participants SIM_P000501-508, sessions `SIM_S_RFL_*`, different signals), the original eight site conditions (faults and context), 480 s each. 721 windows, 94 positive (13 %).
* Evaluation: 16 fresh participants `SIM_REAL_EVAL_00..15` (SIM_P000601-616), two per site condition, drawn with a mild covariate shift (noisier, wider spread). 1,433 windows, 235 positive (16.4 %). Two participants have no ectopy, so per-participant metrics are undefined for them.
* Same `ObservedRecord` contract and the same unmodified `build_local_dataset` as the original cohort. Zero participant overlap with every earlier cohort (training, showcase holdout, FL10 holdout, G1) and zero exact window overlap between training and evaluation.
* Per-participant digests are pinned in `configs/realistic/realistic_cohort_manifest_v2.json`; a test fails on drift.

## Results (fixed rule sigmoid(logit) >= 0.5; reproduce with `python -m scripts.realistic_cohort_experiment`)

| Model | AUROC | AUPRC | F1 | TP / FP / TN / FN |
|---|---:|---:|---:|---|
| Prevalence (16.4 %) | 0.500 | 0.164 | 0.282 if always positive | - |
| Logistic, 6 amplitude features | 0.702 | 0.334 | 0.094 | 12 / 9 / 1189 / 223 |
| Logistic, R-peak timing features | 0.854 | 0.574 | 0.131 | 17 / 7 / 1191 / 218 |
| Pretrained V2, no training | 0.848 | 0.484 | 0.558 | 173 / 212 / 986 / 62 |
| FedAvg from pretrained V2, round 1 | 0.897 | 0.609 | 0.658 | 182 / 136 / 1062 / 53 |
| FedAvg from pretrained V2, round 3 | 0.872 | 0.687 | 0.662 | 131 / 30 / 1168 / 104 |
| FedAvg from pretrained V2, round 10 | 0.921 | 0.838 | 0.774 | 156 / 12 / 1186 / 79 |

Compared with the original cohort: the amplitude logistic fell from AUROC 0.993 to 0.702. The pretrained V2, which was trained only on real MIT-BIH labels and never saw this data, now scores AUROC 0.848 and F1 0.558 with no training (original cohort: AUROC 0.727, F1 0).
That is a useful indication that the synthetic ectopy resembles the real ectopy the model learned, not proof of it. Federated training from the pretrained model improves AUPRC (0.484 to 0.838) and F1 (0.558 to 0.774) and does not collapse to predicting everything positive.
Ranking is not monotone across rounds (round 3 AUROC is below round 1; AUPRC is not monotone either). One run, one seed.

## Honest history of this evaluation cohort
Revision A of the generator was pinned and scored once (amplitude logistic 0.723 / 0.360 / 0.117; timing logistic 0.844 / 0.560 / 0.126; pretrained V2 0.854 / 0.502 / 0.576; round 10 0.901 / 0.811 / 0.736 as AUROC / AUPRC / F1).
A physiology test then found a timing error in bigeminy and trigeminy episodes (the conducted beat after a ventricular beat lacked the compensatory pause). Revision B fixes that timing rule only; no parameter was tuned on any score.
Revision B was re-pinned and re-scored; its results are the ones above, and they tell the same story. Because the cohort was looked at under revision A, it is a fresh cohort, not an untouched one in the strict sense.

## Limits
* Same simulator family for training and evaluation (with a covariate shift), so evaluation is not independent of the generator's assumptions. Real expert-annotated ECG remains the only clinical-grade evidence (the MIT-BIH and INCART lanes).
* Few positives in the training cohort (94 windows; some clients have 4 to 6), as ectopy is rare; this is intentional.
* The hardware recording's own labels remain the assigned ones; a recording carries no ground truth.

## Using it (selectable cohort)
Every Studio run now carries a `cohort`: `ORIGINAL` (default; the frozen NHM_FL10_001 cohort, reproduces every recorded result) or `REALISTIC`. The choice sets the eight training clients (or the seven peers of a recorded-hardware run), the evaluation holdout, and the wording that goes with them.

| Where | Realistic option |
|---|---|
| Start a federation run, synthetic cohort, 10 rounds (untrained or pretrained V2 start) | available |
| Same, 3 rounds from the pretrained V2 start | available |
| 3 rounds from the untrained start | original only (the frozen 3-round product contract is defined on the original cohort) |
| Live-monitored simulated site (source mode B) | available: the chosen realistic site is streamed through the real monitoring runtime and its emitted windows are the client's data (parity with the regenerated twin is reported) |
| History monitoring session as the site signal | original only (the session regenerates the original cohort's site signal) |
| Recorded hardware, pretrained V2 | available: the seven synthetic peers and the evaluation holdout come from the realistic cohort; your recording is still client 00 with its assigned labels |
| Recorded hardware, tabular (fresh / warm start) | not applicable (eight recorded blocks, no synthetic peers) |

* A realistic run is scored, paired and labelled on the realistic evaluation cohort (`WEARABLE_SIM_REALISTIC_EVAL_COHORT_V2`, 1,433 windows, 14 of 16 participants have both classes). Its separation proof is computed window by window against the realistic and original training cohorts, the previously exposed 8-participant holdout, the FL10 holdout and the G1 unseen cohort: zero overlap with all five.
* The unseen-cohort generalisation lane (G1, original generator) keeps mirroring every state, so for a realistic run it is a cross-generator check.
* The logical client ids stay `SIM_FL_SITE_00..07` (they name the eight sites, and the UI keys on them); the cohort is carried by the run's `cohort` field, its evaluation cohort id and its labels.
* Frozen-reference checks (prefix parity against the recorded FL10 digests) apply to the original cohort only.
* Older runs have no `cohort` and mean `ORIGINAL`.
