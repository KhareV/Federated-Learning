# FL-SBX-EVAL-001 — proposal only

Status: **NOT STARTED**. This document does not authorize an experiment, data access, training, held-out inference, calibration, or candidate promotion.

The current three-round product candidate was trained on `WEARABLE_SIM_EVENT_WINDOW_V1` scheduled synthetic events. Its target is not `AAMI_SVF_WINDOW_V1`; therefore existing scientific AUPRC, AUROC, F1, or calibrated-threshold evidence cannot be inherited from `MODEL_V2_FINAL` or the frozen V2-FL checkpoints.

A future target-compatible evaluation would first need a separately approved, prospective protocol that freezes:

1. The precise scientific target and label/quality rules, including the existing AAMI-SVF mapping and window interval semantics.
2. The candidate's training population and patient-disjoint split manifest, with access permission and one-shot guards verified before any read.
3. Initial model-state identity, architecture, optimizer, FL algorithm, client partitioning, random seeds, round selection, and candidate-state hash.
4. Baselines and comparison population, with identical eligibility and prediction definitions for a valid paired contrast.
5. Threshold semantics and whether the candidate is uncalibrated or receives a separately fitted, source-domain calibration under an approved protocol. `CAL_V2` must not be applied to an FL candidate by assumption.
6. Predeclared AUPRC, AUROC, thresholded metrics only where justified, patient-group uncertainty, missing/undefined replicate handling, and the precise decision criterion.
7. Frozen prediction evidence, source hashes, reproducibility commands, negative findings, and an explicit no-automatic-promotion decision boundary.

No existing held-out dataset or current synthetic candidate is accessed by this proposal. Until an approved experiment produces compatible evidence, the product must say **efficacy not established under this engineering contract** and **sandbox only; not deployed**.
