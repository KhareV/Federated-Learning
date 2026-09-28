# Freeze Registry

`NOT_FROZEN` means no claim of completion or scientific approval. Commit and hash fields remain
unset until a later gate actually freezes the artifact.

| artifact | version/id | status | frozen_at_commit | hash | change_class_required | downstream_dependencies | notes |
|---|---|---|---|---|---|---|---|
| source authority | SPEC_V2.2 / PLAN_V1.0 | DOCUMENTED_NOT_FROZEN | — | — | C | all project artifacts | Hierarchy documented in T001; source files retained. |
| hardware/data contract | OBSERVED_MONGODB_SCHEMA_V0 | NOT_FROZEN | — | — | B or C by impact | wearable ingestion, synchronization, quality | Shape observed; semantics unverified. |
| dataset versions | — | NOT_FROZEN | — | — | C | splits, training, evaluation | Existing local data is preserved but not accepted or processed in T001. |
| label mapping | AAMI_SVF_MAP_V1 | NOT_FROZEN | — | — | C | labels, training, evaluation | Identifier locked; mapping implementation deferred. |
| patient split | — | NOT_FROZEN | — | — | C | training, evaluation | Deferred. |
| preprocessing | — | NOT_FROZEN | — | — | C | features, models, evaluation | Deferred. |
| baseline configuration | — | NOT_FROZEN | — | — | C | model comparisons | Deferred. |
| MODEL_V1 | — | NOT_FROZEN | — | — | C | calibration, deployment | Deferred. |
| calibration | — | NOT_FROZEN | — | — | C | thresholds, evaluation | Deferred. |
| internal evaluation | — | NOT_FROZEN | — | — | C | reporting | Deferred. |
| external evaluation | — | NOT_FROZEN | — | — | C | reporting | Deferred. |
| federated configuration | — | NOT_FROZEN | — | — | C | federated experiments | Synthetic research partitions only; implementation deferred. |
| privacy configuration | — | NOT_FROZEN | — | — | B or C by impact | federated/release evidence | Deferred. |
| deployment artifact | — | NOT_FROZEN | — | — | B or C by impact | gateway release | Gateway is mandatory target; implementation deferred. |
| final release | — | NOT_FROZEN | — | — | C | all consumers | Research prototype only. |

