# MODEL_V2 Research Protocol V1

Status: **FROZEN_RESEARCH_PROTOCOL** (owner task: V2-001)

This document is the human-readable mirror of `configs/model_v2/research_protocol_v1.yaml`.
Both encode the same scientific contract; the YAML is authoritative for machine checks, this
file is authoritative for human review. Neither may be mutated after V2-001 freezes this
protocol — any change requires a new `MODEL_V2_RESEARCH_PROTOCOL_V2` successor lock.

This is a **V2 component lock**, not a new canonical `Fxx` freeze registry row. It does not
renumber or alter T001–T036, G0–G22, or F01–F14.

## A. Fixed scientific constants

- Target: `AAMI_SVF_WINDOW_V1`, map: `AAMI_SVF_MAP_V1`, patient split: `MITDB_SPLIT_V1`
- Source lead: exact MLII, sampling: 250 Hz
- Window: 10s / 2500 samples, stride: 5s / 1250 samples
- Preprocessing: `PREPROC_V1` (unchanged); no `PREPROC_V2` in this lineage
- CNN input normalization: `PER_WINDOW_ZSCORE_V1`, epsilon `1e-8`
- Eligibility/exclusion and QUALITY/GAP policy: unchanged from frozen V1

## B. Model seeds

Exactly `20260927`, `20260928`, `20260929` — matched robustness seeds. The release seed is
always `20260927`, regardless of which seed scores best.

## C. Primary metrics

- Primary: pooled AUPRC. Secondary: pooled AUROC.
- Report seed mean, seed SD, seed minimum, fold range, patient/window counts, prevalence,
  parameter count.
- Per-patient AUPRC averaging is forbidden. Threshold metrics are development diagnostics
  only. No weighted composite score.

## D. Patient-cluster bootstrap

- 2000 replicates, deterministic seed `V2_BOOTSTRAP_SEED = 20261002`.
- Each replicate samples patient groups with replacement, keeps all their windows
  (multiplicity preserved), and recomputes the pooled metric.
- Paired comparisons use the identical sampled patient IDs for both models; for multi-seed
  comparison, compute the paired delta per seed on the identical draw, then average the
  seed-level deltas for that replicate.
- Window-level bootstrap is prohibited.

## E. First-line architectures

**ARCH-A — `MODEL_V2_CAPCTRL`** (capacity-only control): Conv1d(1→32,k7) → BN → ReLU →
MaxPool2 → Conv1d(32→64,k5) → BN → ReLU → MaxPool2 → Conv1d(64→128,k5) → ReLU →
AdaptiveAvgPool1d(1) → Flatten → Dropout(0.2) → Linear(128→1). No sigmoid in the model.
Expected ≈51969 trainable parameters (verified mechanically later). Short, V1-like receptive
field.

**ARCH-B — `MODEL_V2_TCN_MEAN`**: stem Conv1d(1→24,k15,stride2,pad7,bias=False)→BN(24)→ReLU,
then 7 residual temporal blocks at 24 channels, kernel 7, dilations 1,2,4,8,16,32,64. Each
block: Conv1d(24,24,k7,dilation=d,pad=3d,bias=False)→BN→ReLU→Dropout(0.1)→
Conv1d(24,24,k7,dilation=d,pad=3d,bias=False)→BN→residual add→ReLU. Head: global temporal
mean → Dropout(0.2) → Linear(24→1). No sigmoid. Analytic receptive field ≈3063 samples
(must be ≥2500, confirmed mechanically/analytically). Expected parameters ≈58k, hard cap
120000.

**ARCH-C — `MODEL_V2_TCN_MEANMAX`**: identical to ARCH-B through the final temporal feature
map; pooling becomes `concat(global_mean, global_max)` over (features, time); head:
Dropout(0.2) → Linear(48→1). Isolates sparse-event pooling.

**Forbidden in the first lineage**: transformer, LSTM, GRU, spectrogram, wavelet model,
self-supervised pretraining, attention pooling, new window size, new target, new patient
split, new lead, PREPROC change, model ensemble.

## F. Architecture search policy

- All primary architecture comparisons use all three seeds; never eliminate after one seed.
- `MODEL_V1_CV_REFERENCE`: 5 folds × 3 seeds = 15 reference fits.
- Primary experiment: 3 architectures × 5 folds × 3 seeds = 45 fits.
- Ranking: mean three-seed pooled OOF AUPRC.
- Practical-improvement rule: mean ΔAUPRC vs. matched reference ≥ **+0.02**.
- AUROC guardrail: mean ΔAUROC must not be worse than **−0.01**.
- Report paired patient-cluster bootstrap CI; do not demand unrealistically narrow CIs from a
  27-patient development population.
- At most two eligible candidate families continue; within one bootstrap SE, prefer the
  simpler/lower-variance architecture.
- The hybrid may run only if the feature-information trigger (Section H) fires.

## G. Feature-ablation contract

- Only frozen `BASELINE_FEATURES_V1` (STAT=13, RR=9, QRS=7).
- Variants: STAT, RR, QRS, RR+QRS, STAT+RR, STAT+QRS, ALL.
- Models: frozen-config Logistic Regression and Random Forest.
- Imputer/scaler/model fit within each TRAIN-CV training fold only.
- No new features, annotations, quality predictor, or patient ID as a feature.
- Minimal adequate subset: smallest subset within 0.02 absolute RF pooled OOF AUPRC of
  ALL-29; ties broken by fewer features first.
- Grouped permutation importance is required.

## H. Hybrid trigger

Run `MODEL_V2_HYBRID` only if:

```
best reduced classical RF TRAIN-CV AUPRC − best learned-only V2 TRAIN-CV AUPRC ≥ 0.03
```

If false, V2-005 becomes `SKIPPED_BY_PROTOCOL`, not `FAILED`. The hybrid branch concatenates
the best temporal ECG backbone with a tiny MLP (max shape input→32→16) over the minimal
adequate deterministic feature subset, producing one raw logit. New identity:
`MODEL_V2_AUX_FEATURES_V1`; `BASELINE_FEATURES_V1` is never mutated.

## I. Loss / sampling

First-line loss remains `BCEWithLogitsLoss`; `pos_weight` is recomputed from each actual
optimisation subset only. No focal loss, asymmetric loss, AUPRC surrogate, or patient-balanced
sampler in the first lineage — these may not be added adaptively.

## J. Optimizer experiment

Architecture search initially uses the V1 training schedule verbatim. Only after the winning
family is determined, V2-006 may run exactly one comparison: **CONTROL** (existing V1
schedule) vs. **CHALLENGER** (AdamW, LR 1e-3, same weight decay, ReduceLROnPlateau
mode=max/factor=0.3/patience=3, monitor inner-validation AUPRC, early-stop patience=8). No
grid. Adopt the challenger only if the mean TRAIN-CV AUPRC improvement exceeds one bootstrap
SE and seed SD does not materially worsen.

## K. Official validation

At most two frozen configurations enter V2-007: trained from scratch on all 27 TRAIN patient
groups, using official VALIDATION for early stopping/checkpoint selection in its locked v2.2
role, seeds 20260927/28/29. Once the first new V2 official VALIDATION result exists, no
architecture/hyperparameter/search-rule change is permitted. Selection: highest mean
three-seed validation AUPRC; ties within one bootstrap SE prefer the simpler/lower-variance
model. The release checkpoint is always seed 20260927.

**Promotion requirement before CALIBRATION**: release-seed V2 validation AUPRC ≥
`0.5328607838787021 + 0.03` ≈ **0.5628608**, with three-seed confirmation of a genuine
improvement (not a single-seed spike), and no material AUROC regression. The frozen classical
references (LR AUPRC 0.645879, RF AUPRC 0.799672) are interpretation benchmarks only, not
hard promotion gates.

## L. Calibration policy

`CAL_V2` happens only **after** `MODEL_V2_FINAL` is frozen: a single positive scalar
temperature fit on CALIBRATION only, by NLL minimization, `p = sigmoid(logit / T_V2)`,
threshold by F1-maximum on calibrated CALIBRATION probabilities with the `>=` comparator and
the same deterministic tie rule as V1. No Platt scaling, isotonic regression, TRAIN-OOF
calibration, TRAIN+VALIDATION calibration, or reuse/mutation of `CAL_V1`. Report NLL/Brier
(raw and calibrated), ECE, reliability bins, patient count, window/class counts. Claim
boundary: MIT-BIH source-domain calibration only.

## M. Post-freeze second look

Only after `MODEL_V2_FINAL` and `CAL_V2` are frozen: one pass each on INTERNAL_TEST (same
eligible population, compared to frozen V1 predictions, V1 is never rerun), INCART (same
clusters/windows, no recalibration, no lead/map change), and NSTDB (same frozen T019 stress
protocol, same paired windows/SNRs, no retuning). All three are labeled **"POST-FREEZE
COMPARATIVE SECOND-LOOK EVIDENCE ON PREVIOUSLY EXPOSED EVALUATION DOMAINS"** — never untouched
V2 validation.

## N. Runtime-acceptance guardrails

Scientific `MODEL_V2_FINAL` and operational runtime acceptance are different decisions;
`MODEL_V2_FINAL` cannot be retuned after second-look exposure. Predeclared guardrails (point
estimates, with paired CIs reported):

| Domain | Guardrail |
|---|---|
| INCART | ΔAUPRC ≥ −0.03, ΔAUROC ≥ −0.03 |
| INTERNAL_TEST | ΔAUPRC ≥ −0.05, ΔAUROC ≥ −0.05 |
| NSTDB | no single SNR ΔAUPRC < −0.10; mean six-SNR ΔAUPRC ≥ −0.05 |

These are guardrails, not tuning objectives. On failure, `MODEL_V2_FINAL` remains a frozen
research result, but `MODEL_V1` remains the operational runtime lineage.

## O. Downstream impact

If runtime-accepted, later phases may create `CAL_V2`, `GATEWAY_ARTIFACT_V2`,
`EXPLAINABILITY_V2`, `API_RUNTIME_V2`, V2 alert/calibration binding, and V2 replay evidence —
all additive. `GATEWAY_ARTIFACT_V1`, `EXPLAINABILITY_V1`, `API_RUNTIME_V1_1`,
`ALERT_POLICY_V1`, and V1 replay evidence must never be mutated. Whether the frontend is
already model-ID-generic is inspected later; it is not versioned merely because V2 exists.
Federated MODEL_V2 experiments are **not** part of this first lineage.
