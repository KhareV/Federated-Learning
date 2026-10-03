# MODEL_V2_RESEARCH_PROTOCOL_V3

Additive successor to MODEL_V2_RESEARCH_PROTOCOL_V2, created by C-V2-PRE006-AUTHORITY-REPAIR before V2-006 begins. V1 and V2 are never mutated in place (see their own `change_control` clauses); this document and `configs/model_v2/research_protocol_v3.yaml` are the only authoritative sources for the corrections below. All other V2 content (fixed scientific constants, architectures and parameter counts, outer-CV manifests, feature audit, MODEL_V1_CV_REFERENCE_V1, V2-002/V2-003/V2-004/V2-005 results, the hybrid trigger, the two hard AUPRC promotion criteria, the patient-cluster bootstrap unit, the CAL_V2 method, and the post-freeze second-look policy) is carried forward unchanged.

## Correction 1: final TRAIN-only inner split replaces official-VALIDATION checkpoint selection

V2 carried forward V1's `early_stopping_checkpoint_selection = OFFICIAL_VALIDATION_LOCKED_V2.2_ROLE` field unchanged, which assigned early-stopping/scheduler/checkpoint-selection to official VALIDATION itself for the V2-007 finalists. V3 replaces this with a dedicated additive component, `MITDB_TRAIN_FINAL_INNER_V2_V1`, covering all 27 TRAIN groups split once into approximately 22 `OPTIMISE` groups and approximately 5 `FINAL_INNER_VALIDATION` groups:

- **OPTIMISE**: receives gradient updates, determines pos_weight (`negative_OPTIMISE_windows / positive_OPTIMISE_windows`), receives TRAIN augmentation.
- **FINAL_INNER_VALIDATION**: no gradient updates, no augmentation; controls the scheduler metric, the early-stopping metric, and checkpoint selection.
- **Official VALIDATION**: never provides gradient updates, never determines pos_weight, never drives the scheduler or early stopping, never selects the epoch or checkpoint, never modifies architecture/hyperparameters. It is accessed only after each finalist's checkpoint is already fixed, for the predeclared finalist comparison and promotion evaluation.

This is a documented, deliberate methodological difference from historical MODEL_V1 (which used official VALIDATION for early stopping/checkpoint selection). V1 is never retroactively retrained because of this difference.

## Correction 2: AUROC is a secondary D5 diagnostic, not an additional hard gate

V2 carried forward V1's `auroc_material_regression_forbidden = true` as an active hard D5 promotion gate. V3 supersedes it (`false`, with `auroc_role = SECONDARY_DIAGNOSTIC_REPORTED_NOT_A_D5_HARD_GATE`). The two hard D5 promotion criteria remain exactly:

1. mean three-seed official VALIDATION AUPRC > 0.646; and
2. the paired patient-cluster-bootstrap delta-AUPRC vs MODEL_V1 has a lower 95% CI bound > 0, for the required release-seed/three-seed comparisons.

AUROC remains reported. The separate runtime-acceptance/INCART AUROC guardrail (`runtime_acceptance_guardrails`) is unchanged and remains distinct from scientific promotion.

## Correction 3: explicit MODEL_V2 D0-D5 search budget

V3 adds an explicit `search_budget` section: the MODEL_V2 D0-D5 neural-fit ceiling is **90** (not the 100 figure used as an unauthoritative control-plane convention in prior V2-002..V2-005 evidence, and never actually defined in Protocol V1 or V2). Completed neural fits before V2-006: 50 (V2-002=15, V2-004=35, V2-005=0). V2-006's local maximum is 15 (max cumulative 65); V2-007's maximum is 6 finalist seed-fits (max cumulative through official VALIDATION: 71). The 90-fit ceiling is not currently restrictive but remains a frozen search-control rule. No historical fit count changes.

## Correction 4: explicit CAL_V2 ordering and MODEL_V2_FINAL/runtime-acceptance separation

V3 adds explicit `cal_v2_ordering` and `model_v2_final_vs_runtime_acceptance` sections making already-implied chronology and separation machine-explicit: official VALIDATION -> MODEL_V2_FINAL freeze -> CAL_V2 fit/freeze -> post-freeze INTERNAL_TEST/INCART/NSTDB second look -> runtime-acceptance decision -> gateway/API/frontend integration only if accepted. CAL_V2 is never contingent on runtime acceptance. MODEL_V2_FINAL (scientific freeze) and runtime acceptance (operational) remain separate decisions; MODEL_V1 stays operational if V2 is not runtime-accepted.

## What is unchanged

Target, split, PREPROC_V1, architecture identities and parameter counts, outer-CV manifests (MITDB_TRAIN_CV_V2_V1, MITDB_TRAIN_INNER_V2_V1 -- both byte-unchanged), the feature-information audit, MODEL_V1_CV_REFERENCE_V1, V2-002/V2-003/V2-004/V2-005 results (including the hybrid trigger and BEST_LEARNED_ONLY_V2_CV_V1 selection), the mean-three-seed-AUPRC and paired-bootstrap-CI hard promotion criteria, the release-seed=20260927 rule, the patient-cluster bootstrap unit and procedure, the CAL_V2 method, and the post-freeze second-look policy are all carried forward byte-for-byte from V2 and are not altered by this successor.
