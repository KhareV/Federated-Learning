# Freeze Registry

`NOT_FROZEN` means no claim of completion or scientific approval. Commit and hash fields remain
unset until a later gate actually freezes the artifact.

The normative machine-readable companion is `manifests/freeze_registry_v1.csv`. This document is
the human-readable view; discrepancies are errors and must be resolved through change control.

| artifact | version/id | status | frozen_at_commit | hash | change_class_required | downstream_dependencies | notes |
|---|---|---|---|---|---|---|---|
| source authority | SPEC_V2.2 / PLAN_V1.0 | FROZEN | T002 source reconciliation | see `reports/t002/source_hashes.json` | C | all project artifacts | v2.2 is technical authority; execution plan v1.0 is sequencing authority; master prompt is planning input only. |
| hardware/data contract | OBSERVED_MONGODB_SCHEMA_V0 | NOT_FROZEN | — | — | B or C by impact | wearable ingestion, synchronization, quality | Shape observed; semantics unverified. |
| dataset versions | — | NOT_FROZEN | — | — | C | splits, training, evaluation | Existing local data is preserved but not accepted or processed in T001. |
| label mapping | AAMI_SVF_MAP_V1 | FROZEN | T008/G4 | `manifests/labels/AAMI_SVF_MAP_V1.yaml` | C | labels, training, evaluation | Frozen mapper; version bump required to change. |
| patient split | MITDB_SPLIT_V1 | FROZEN | T010/G5 | `manifests/splits/MITDB_SPLIT_V1.lock.json` | C | training, evaluation | Patient-disjoint frozen split; 201/202 grouped. |
| preprocessing | PREPROC_V1/GAP_POLICY_V1 | FROZEN | T013/G6 | `manifests/preprocessing/PREPROC_V1.lock.json` | C | features, models, evaluation | Includes causal transforms, window/timestamp conventions, QUALITY_V1, and per-window z-score contract. |
| baseline configuration | BASELINE_V1 / BASELINE_FEATURES_V1 | FROZEN | T014/G7 | `manifests/baselines/BASELINE_V1.lock.json` | C | model comparisons | Waveform-only feature schema, TRAIN-only transforms, majority/LR/RF artifacts, and fixed validation reporting are locked. |
| MODEL_V1 | MODEL_V1 | FROZEN | T016/G8 | `checkpoints/MODEL_V1.manifest.json` | C | calibration, evaluation, FL, deployment | Exact seed-20260927 candidate, frozen config, and synthetic fixed-vector package are hash-bound; changes require MODEL_V2 or controlled Class-C change. |
| calibration | CAL_V1 | FROZEN | T017 | `artifacts/CAL_V1.json` | C | internal/noise/external evaluation, alerts, API/dashboard | MIT-BIH source-domain temperature and pooled-F1 threshold; small-patient-sample uncertainty. |
| internal evaluation | INTERNAL_TEST_V1 | FROZEN | T018/G10 | `reports/internal_test.json` | C | noise/external evaluation and reporting | One guarded MODEL_V1 inference pass; patient-cluster bootstrap method frozen before access. Frozen outputs may support later error analysis, but no model, threshold, preprocessing, metric, or bootstrap retuning. |
| external evaluation | — | NOT_FROZEN | — | — | C | reporting | Deferred. |
| federated configuration | — | NOT_FROZEN | — | — | C | federated experiments | Synthetic research partitions only; implementation deferred. |
| privacy configuration | — | NOT_FROZEN | — | — | B or C by impact | federated/release evidence | Deferred. |
| deployment artifact | — | NOT_FROZEN | — | — | B or C by impact | gateway release | Gateway is mandatory target; implementation deferred. |
| final release | — | NOT_FROZEN | — | — | C | all consumers | Research prototype only. |
