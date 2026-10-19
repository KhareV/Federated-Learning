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

Compared with the original cohort: the amplitude logistic fell from AUROC 0.993 to 0.702. The pretrained V2, which was trained only on real MIT-BIH labels and never saw this data, scores AUROC 0.848, AUPRC 0.484 and F1 0.558 here with no training. On the original cohort's frozen holdout the same pretrained V2 scores AUROC 0.931, AUPRC 0.904 and F1 0.842 (1,446 windows, prevalence 0.212; reproduced through the Studio observer's own evaluator), so the realistic cohort is clearly the harder one for it. (Earlier text here quoted AUROC 0.727 / F1 0 as the original-cohort figure; that is the UNTRAINED FL_INIT_V2 state, round 0 of the frozen mode-A run, not the pretrained V2. Corrected.)
Prevalence differs between the two holdouts (0.212 against 0.164), so raw AUPRC is not comparable across them; AUROC and the pretrained V2's drop from 0.931 to 0.848 are. Federated training from the pretrained model improves AUPRC (0.484 to 0.838) and F1 (0.558 to 0.774) and does not collapse to predicting everything positive.
Ranking is not monotone across rounds (round 3 AUROC is below round 1; AUPRC is not monotone either). One run, one seed.

## Honest history of this evaluation cohort
Revision A of the generator was pinned and scored once (amplitude logistic 0.723 / 0.360 / 0.117; timing logistic 0.844 / 0.560 / 0.126; pretrained V2 0.854 / 0.502 / 0.576; round 10 0.901 / 0.811 / 0.736 as AUROC / AUPRC / F1).
A physiology test then found a timing error in bigeminy and trigeminy episodes (the conducted beat after a ventricular beat lacked the compensatory pause). Revision B fixes that timing rule only; no parameter was tuned on any score.
Revision B was re-pinned and re-scored; its results are the ones above, and they tell the same story. Because the cohort was looked at under revision A, it is a fresh cohort, not an untouched one in the strict sense.

## Seed-robust validation (5 training cohorts x 6 evaluation cohorts)
`python -m scripts.realistic_multiseed` (output `reports/realistic/multiseed.json`): five independently seeded training cohorts, each run for 10 FedAvg rounds from MODEL_V2_FINAL (plain aggregation, fixed 0.5 threshold, no calibration), scored on six disjoint-seed evaluation cohorts (prevalence 0.099 to 0.164). Intervals are 95% bootstrap intervals resampled over training seeds and participants; they are nominal because windows overlap within a participant.

| Model | AUROC | AUPRC | lift (AUPRC / prevalence) | F1 at 0.5 |
|---|---|---|---|---|
| Pretrained V2, no training | 0.849 [0.836, 0.859] | 0.445 [0.418, 0.470] | 3.6 | 0.471 |
| Beat-timing logistic | 0.846 [0.826, 0.863] | 0.464 [0.402, 0.531] | 3.7 | 0.271 |
| Amplitude logistic | 0.749 [0.724, 0.774] | 0.310 [0.267, 0.353] | 2.5 | 0.088 |
| Federated, round 10 | 0.899 [0.883, 0.918] | 0.734 [0.687, 0.788] | 6.0 | 0.612 |

What this establishes, and what it does not:
* **Federated round 10 beats the pretrained start on this synthetic cohort family**: AUROC +0.051 [+0.035, +0.069], AUPRC +0.289 [+0.248, +0.338], better in every training/evaluation pairing on both; F1 at 0.5 +0.141 (better in 90%). It also beats the beat-timing logistic on AUROC and AUPRC. This is adaptation to the simulator's event family and says nothing about real patients.
* **The pretrained V2 only ties the beat-timing logistic** on AUROC (+0.003, interval includes zero) and AUPRC (-0.019, includes zero). Its advantage is at the fixed 0.5 threshold (F1 +0.201). The earlier single-draw statement that V2 "beats the simple baselines" holds for the amplitude baseline and for F1 only.
* **Raw AUPRC depends on prevalence** (0.099 to 0.164 across draws); read the lift column, not the raw AUPRC, when comparing cohorts.
* **Training is not monotone.** The mean over the five runs dips sharply at round 2 (AUROC 0.535) and again at round 4 (0.664) before recovering from round 5 and settling by round 7 (0.881 to 0.899). A 3-round run therefore ends in a transient state: round 3 averages AUROC 0.751, below round 1 (0.878), with AUPRC about level (0.521 against 0.508). Read the 10-round result, not the 3-round one, as the converged behaviour.
* **Real-ECG forgetting (a limiting finding).** Scoring each federated state on the real MIT-BIH VALIDATION windows (2,880 windows, 7 patient groups; the partition V2 model selection used, so absolute numbers are optimistic) shows that adapting to the synthetic cohort **costs real-ECG performance**. At round 10 the mean change from the frozen V2 is AUROC -0.060 and AUPRC -0.135 (worst training run -0.124 and -0.187); all five training runs are negative at round 10 (AUROC -0.017 to -0.124), and every round from 1 to 10 is negative on average. Per-run intervals are wide with only 7 patient groups and include zero, so the size is uncertain; the sign was consistent. A candidate trained on the synthetic cohort is therefore **not** a better ECG model than MODEL_V2_FINAL, and the released model is correctly never replaced by it.

Superseding earlier notes: the one-seed "federated R10" figures above are one draw of this distribution, and the five-holdout table in the audit plan used overlapping seed ranges, so its intervals were too narrow.

## Why the pretrained V2 is weaker here than on real ECG (diagnostics)
`python -m scripts.realistic_diagnostics` (output `reports/realistic/diagnostics.json`; inference only, nothing is trained or selected). Pinned realistic holdout, 1,433 windows, central MODEL_V2_FINAL, fixed 0.5 rule:

| Diagnostic | Result |
|---|---|
| Annotation noise off (score against the hidden truth) | Only 9 of 1,433 labels differ (6 missed beats, 3 false marks). AUROC 0.848 -> 0.855, AUPRC 0.484 -> 0.508, F1 0.558 -> 0.571. **Label noise is not the cause.** |
| False positives by window content | 207 false positives against the hidden truth: **169 (82 %) are windows with a large motion artifact** (77 % of such windows are flagged), 21 smaller motion artifacts, 14 electrode pops, 3 with nothing special. Windows with nothing special are flagged 0.4 % of the time (3 of 835), and 75 % of true-ectopy windows are flagged. |
| Threshold re-fitted on the other five holdouts | Fitted thresholds are about 0.9. Mean F1 over six holdouts 0.471 (fixed 0.5) -> 0.466 (re-fitted): fewer false positives but lower recall. **The threshold is not the lever.** |
| What-if: drop windows containing a large motion artifact | Central V2, pinned holdout: AUROC 0.848 -> 0.914, AUPRC 0.484 -> 0.784, F1 0.558 -> 0.734, false positives 212 -> 43 (22 % of windows dropped, pooled). The V2-FL-001 round-50 model: AUROC 0.890 -> 0.953, AUPRC 0.577 -> 0.850, F1 0.596 -> 0.753. |

Reading: the model recognises the synthetic ectopic beats (and ordinary beats) well; what it cannot tell apart is a wide, QRS-like **motion artifact** from a ventricular ectopic beat, because the generator draws motion artifacts to look like wide complexes at 0.6 to 3.2 per minute. In a real pipeline a quality gate would suppress such windows; here every scored window was graded VALID (the quality step removed only 55 windows, for injected faults, none for motion artifacts), which matches the known QUALITY_V1 noise-sensitivity limitation. The what-if gate is an oracle (it uses the generator's artifact times), so it bounds the benefit; a real gate would be imperfect. Higher-noise participants also produce more false positives (flag rate among truly ectopy-free windows 9.9 % / 22.7 % / 19.3 % by noise tercile).

## Starting a 10-round run from each model on both cohorts
`python -m scripts.fl50_cohort_runs` (output `reports/realistic/fl50_cohort_runs.json`): FedAvg, plain aggregation, fixed 0.5, one run per cell, scored on the cohort's own evaluation holdout. The "50-round model" is the round-50 state of V2-FL-001 (50 federated rounds on real MIT-BIH training patients, random start).

| Cohort (windows, prevalence) | Start | R0 AUROC / AUPRC / F1 | R10 AUROC / AUPRC / F1 |
|---|---|---|---|
| Original (1,446, 0.212) | central MODEL_V2_FINAL | 0.931 / 0.904 / 0.842 | 0.999 / 0.996 / 0.975 |
| Original | V2-FL-001 round 50 | 0.917 / 0.865 / 0.680 | 1.000 / 1.000 / 0.987 |
| Realistic (1,433, 0.164) | central MODEL_V2_FINAL | 0.848 / 0.484 / 0.558 | 0.915 / 0.828 / 0.778 |
| Realistic | V2-FL-001 round 50 | 0.890 / 0.577 / 0.596 | 0.915 / 0.846 / 0.814 |

On the original cohort the task is easy for both and the ordering at R0 is mixed (central is higher). On the realistic cohort the round-50 model starts higher (AUROC 0.890 against 0.848) and ends level in AUROC. Single runs: training is not monotone (round 3 and 5 AUROC dip for both) and a repeat run differs by a few hundredths. The untrained start is the one that scores AUROC 0.727 on the original holdout (not the pretrained V2; an earlier line of this document mixed the two up and is corrected above).

A follow-up cohort, `REALISTIC_COHORT_V3.md`, replaces this cohort's invented noise with recorded NSTDB noise (selectable in the Studio as `REALISTIC_NSTDB`); this cohort and its pinned results are unchanged.

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
