# MODEL_V2_RESEARCH_PROTOCOL_V2

Additive successor to MODEL_V2_RESEARCH_PROTOCOL_V1, created by C-V2-PRE004-CONTROL before V2-004 begins. V1 is never mutated in place (see its own `change_control` clause); this document and `configs/model_v2/research_protocol_v2.yaml` are the only authoritative sources for the two corrections below. All other V1 content (fixed scientific constants, architectures and parameter counts, feature ablation contract, hybrid trigger, loss/sampling rules, optimizer experiment, calibration policy, post-freeze second look, runtime acceptance guardrails, downstream impact) is carried forward unchanged.

## Correction 1: staged architecture search (replaces the flat 45-fit design)

V1's `architecture_search_policy` required `all_primary_comparisons_use_all_three_seeds: true` and `elimination_after_single_seed_forbidden: true` -- i.e. all three architectures receive all three seeds (45 total fits) before any elimination. V2 replaces this with:

- **Stage D1**: 3 architectures x 5 folds x seed 20260927 only = 15 fits. Disqualify any non-finite candidate, any candidate with pooled OOF AUROC below the frozen MODEL_V1_CV_REFERENCE_V1 mean AUROC, or any candidate with more than 120,000 trainable parameters. Rank survivors by pooled OOF AUPRC. A candidate advances only if its paired patient-cluster-bootstrap delta-AUPRC vs MODEL_V1_CV_REFERENCE_V1 has a lower 95% CI bound greater than 0. At most 2 advance, using the one-bootstrap-SE simplicity tie rule. If zero candidates advance, the neural architecture search stops per protocol: no D2 fits are manufactured, official VALIDATION is not accessed.
- **Stage D2**: at most 2 D1-advanced architectures x 5 folds x the remaining two seeds (20260928, 20260929) = at most 20 additional fits.
- **Maximum V2-004 fits: 35** (15 + 20), never 45.

## Correction 2: D5 promotion rule (replaces the 0.5628608 hard gate)

V1's hard D5 gate was `release_seed_validation_auprc_min = 0.5628607838787021` (V1 release AUPRC 0.5328608 + 0.03), with the historical classical LR/RF VALIDATION AUPRC values (0.645879, 0.799672) marked interpretation-benchmarks-only (`hard_promotion_gates: false`). V2's rule instead requires BOTH:

1. mean three-seed official VALIDATION AUPRC > 0.646 (the frozen historical LOGISTIC_BASELINE_V1 VALIDATION AUPRC, 0.645879, rounded); and
2. the paired patient-cluster-bootstrap delta-AUPRC vs MODEL_V1 has a lower 95% CI bound > 0, for the required release-seed / three-seed comparisons.

`three_seed_confirmation_required` and `auroc_material_regression_forbidden` are carried forward unchanged from V1.

## What is unchanged

Target, split, PREPROC_V1, architecture identities and parameter counts (MODEL_V2_CAPCTRL=51969, MODEL_V2_TCN_MEAN=57553, MODEL_V2_TCN_MEANMAX=57577, TCN analytic receptive field=3063), CV manifests, the feature-information audit, MODEL_V1_CV_REFERENCE_V1, V2-002/V2-003/D0.6 results, the patient-cluster bootstrap unit and procedure, the CAL_V2 method, and the post-freeze external-evaluation policy are all carried forward byte-for-byte from V1 and are not altered by this successor.
