# Realistic synthetic cohort with RECORDED noise (WEARABLE_SIM_REALISTIC_ECG_V3)

Status: built, tested, pinned and **selectable in the Studio** as `REALISTIC_NSTDB` ("Realistic cohort with recorded noise (NSTDB)"). The original cohort stays the default; the invented-noise realistic cohort (V2) and every recorded artefact of either are untouched.

## Why
The diagnostics in `REALISTIC_COHORT_V2.md` showed that 82 % of the pretrained V2's false positives on the V2 cohort came from the generator's own *invented* motion artifacts (wide, QRS-like deflections), while the dataset-flagged noise of real PTB-XL records did not raise the false-positive rate. The noise was the least realistic part of the cohort, so V3 replaces it with recorded noise.

## What changes, what does not
* **Unchanged (same code, same random streams):** the clean ECG, the rhythm, all ectopy (V, S, F beats, couplets, bigeminy, trigeminy, runs), the burden distribution, the site fault and context schedules, the annotation process (2 % of true ectopic beats missed, 4 % of large noise deflections marked as ectopy, 12 ms jitter) and the pipeline. For a given seed the clean waveform and the true ectopic beats are identical to V2's (tested).
* **Changed:** the baseline wander, muscle noise, motion artifacts and electrode pops are the **recorded noise of the MIT-BIH Noise Stress Test Database v1.0.0** (`bw` baseline wander, `em` electrode motion, `ma` muscle artifact; 360 Hz, about 30 minutes, mV; files checked against their official SHA-256 values before every use), combined by power (40 / 40 / 20 %) and scaled to **NSTDB's own documented SNR levels** (24, 18, 12, 6, 0 dB relative to the RMS of the participant's clean waveform). Each participant draws one level (training: mostly clean, probabilities 0.30 / 0.35 / 0.22 / 0.10 / 0.03; evaluation: mildly noisier, 0.18 / 0.28 / 0.26 / 0.20 / 0.08) and a random segment of each record. Training participants draw from the first 60 % of the recordings and evaluation participants from the last 40 %, so no recorded noise segment is shared between the cohorts. A 50 Hz mains sine remains the only invented noise term.
* Cohort: 8 training clients on the logical sites `SIM_FL_SITE_00..07` (participants SIM_P000701-708), 16 fresh evaluation participants (SIM_P000801-816, 1,446 windows, 129 positive, 12 of 16 with both classes), disjoint from every earlier cohort including V2's (participant, session and window-input overlap all zero, computed, not assumed). Per-participant digests and the noise-record digests are pinned in `configs/realistic/realistic_cohort_manifest_v3.json`.

## Honest history
The SNR levels, probabilities, noise shares and regions were fixed in code before any model saw the cohort. The cohort was then **looked at once before it was pinned**: central MODEL_V2_FINAL AUROC 0.949 / AUPRC 0.900, the V2-FL-001 round-50 checkpoint 0.971 / 0.906, an untrained model 0.610 / 0.316, an amplitude logistic 0.816 / 0.671 and a beat-timing logistic 0.918 / 0.888. No parameter changed after that look, so the cohort is fresh, not untouched; its difficulty is whatever recorded noise at NSTDB's levels produces and was not tuned.

## What it turns out to be
* **Easy for the pretrained V2.** On the evaluation holdout the central V2 makes **no false positive among 1,316 negative windows** at any SNR level present (24 to 6 dB), and catches 72 % of the true-ectopy windows; its errors are misses. The recorded noise is not what fools V2 (consistent with the PTB-XL check); the invented artifacts were. The simple beat-timing logistic still keeps pace on AUROC and AUPRC.
* **Little for federated training to add.** 10 rounds from the central V2: AUROC 0.949 -> 0.957, AUPRC 0.900 -> 0.901. From the 50-round federated checkpoint: AUROC 0.971 -> 0.937, AUPRC 0.906 -> 0.896. As a demonstration of federated improvement this cohort is weak; as a faithful-noise sanity check it is honest.
* **It is the least harmful synthetic cohort to adapt to** (next section).

## Adapting to each cohort: effect on unseen real ECG (PTB-XL check, primary folds 9-10, paired against the central V2)
Same start (central V2), same engine, one run per cell; scores on PTB-XL rule A (see `docs/ptbxl/PTBXL_EXTERNAL_CHECK_V1_RESULTS.md`).

| Adapted on | 10 FedAvg rounds: AUROC / AUPRC change | 3 FedAvg rounds | FedProx mu 0.1 / mu 1.0, 10 rounds |
|---|---|---|---|
| original cohort | -0.036 [-0.049, -0.023] / -0.169 | **-0.009 [-0.018, +0.000] / -0.030** | -0.035 / -0.168 ; -0.032 / -0.134 |
| realistic cohort (invented noise) | -0.046 [-0.057, -0.035] / -0.229 | -0.073 [-0.090, -0.056] / -0.193 (worse) | -0.045 / -0.227 ; -0.043 / -0.226 |
| **realistic cohort, recorded noise** | **-0.024 [-0.034, -0.014] / -0.071** | **-0.006 [-0.014, +0.002] / -0.018** | -0.023 / -0.067 ; -0.018 / -0.055 |

Reading: (1) the recorded-noise cohort costs real-ECG performance least at every setting; (2) **fewer rounds is the only lever that helped** (original and recorded-noise cohorts; the intervals of the 3-round change touch zero), while FedProx did nothing at the engine's frozen mu = 0.1 and little at 1.0; (3) on the invented-noise realistic cohort nothing helped, and 3 rounds was worse because it ends inside the transient dip that training shows at rounds 2 to 5; (4) fewer rounds also leaves less to gain on the cohort itself (3-round own-holdout AUROC 0.979 on the original, 0.838 on the invented-noise one). The mu = 1.0 value is patched inside the diagnostic script only; the engine's frozen mu is unchanged. Reproduce: `python -m scripts.fl_mitigation_ptbxl` and `python -m scripts.fl50_cohort_runs` (`reports/ptbxl/mitigation.json`, `reports/realistic/fl50_cohort_runs.json`).

## Limits
* Only the noise is recorded; the ECG, the rhythm and the labels are still synthetic, from plausible round numbers. Still no clinical claim.
* No atrial fibrillation or other irregular-rhythm negatives: that is the largest false-positive source on real PTB-XL records (74 % of AF records flagged) and no synthetic cohort here contains it, so none of them tests that failure mode.
* Four of the 16 evaluation participants have no ectopy; per-participant metrics are undefined for them.
* One run per cell; training is not monotone, so single-run differences of a few hundredths are within run-to-run variation.
* The SNR mix is NSTDB's documented levels with predeclared probabilities, not a population statistic.

## Using it
In the Studio, choose the third cohort button ("Realistic + recorded noise"). It works for the 10-round runs (untrained or pretrained V2 start), the 3-round run from the pretrained V2 start, candidate starts, the live-monitored-site source (the chosen recorded-noise site is streamed through the real monitoring runtime and its emitted windows are the client's data), and the pretrained-V2 recorded-hardware path (its seven peers and its holdout). As for the invented-noise cohort, 3 rounds from the untrained start (the frozen product contract) and a History session as the site signal stay original-cohort only. A run is scored, paired and labelled on `WEARABLE_SIM_REALISTIC_EVAL_COHORT_V3`.
