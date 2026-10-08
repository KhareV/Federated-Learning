# Manuscript material (draft, for supervisor review)

**Suggested title:** Reproducible Federated ECG Classification Under Controlled Data Heterogeneity: A Comparative Study of FedAvg, FedProx, and V2 Model Architectures

> Boundary: scientific results (lane B) concern AAMI-SVF window classification on research ECG. The synthetic engineering results (lane C) are labelled "SYNTHETIC ENGINEERING-EVENT CLASSIFICATION — NOT AAMI-SVF OR CLINICAL VALIDATION" and are never pooled with lane B. No clinical, regulatory or hardware claim is made.

## Abstract (draft)
We study federated learning of a V2 temporal-convolutional ECG window classifier under five controlled data-heterogeneity conditions (IID, label, feature, quantity, combined) with FedAvg and FedProx, against a V1 architecture. All 20 models were evaluated once, under a frozen protocol, on two populations with patient-cluster bootstrap intervals. V2 federated models reach AUPRC 0.9989 (INTERNAL_TEST, 6 clusters) and 0.9766 (INCART, 32 clusters) under IID partitioning, descriptively comparable to a historical centralized V2 reference (0.9995 and 0.9700). No superiority claim is made. A separate engineering demonstration of a three-round, eight-client sandbox federation on synthetic wearable events (SYNTHETIC ENGINEERING-EVENT CLASSIFICATION — NOT AAMI-SVF OR CLINICAL VALIDATION) is reported with its own frozen protocol and honest operating-point failure.

## Methods (outline)
1. Data and partitions: AAMI_SVF_WINDOW_V1 research ECG, patient-disjoint train/validation/test; controlled non-IID partitions. REFERENCE_REQUIRED: dataset citations (MIT-BIH, INCART, NSTDB) must be added from verified sources.
2. Models: V1 and V2 (TCN-mean) architectures. REFERENCE_REQUIRED: TCN reference.
3. Federation: 8 clients, 50 rounds, FedAvg and FedProx (mu = 0.1 for V2). REFERENCE_REQUIRED: FedAvg and FedProx primary references.
4. Evaluation: one-shot frozen inference, raw sigmoid 0.5 rule for threshold metrics, nominal 95% patient-cluster percentile bootstrap, no p-values.
5. Synthetic engineering evaluation: protocol `NHM_SYNTH_FL_EVAL_PROTOCOL_V1` frozen before results (method-freeze commit `6d79274c0c`), independent holdout of 8 unseen simulated participants.

## Results
**Controlled heterogeneity (V2 FedAvg AUPRC, INTERNAL_TEST / INCART):** IID 0.9989 / 0.9766; label 0.9989 / 0.9750; feature 0.9997 / 0.9885; quantity 0.9988 / 0.9866; combined 0.9987 / 0.9452. Full table: TAB1_ALL_MODELS.

**FedAvg vs FedProx (V2, label skew):** 0.9989 vs 0.9928 (INTERNAL_TEST); 0.9750 vs 0.9678 (INCART). Interpretation is descriptive; intervals are nominal.

**Centralized vs federated (V2, IID, point values, no paired interval):** INTERNAL_TEST 0.999473 vs 0.998931 (difference -0.000542); INCART 0.970004 vs 0.976604 (difference +0.006600). Four admissible readings are listed in the comparability audit; none supports a superiority claim.

**Synthetic engineering demonstration (SYNTHETIC ENGINEERING-EVENT CLASSIFICATION — NOT AAMI-SVF OR CLINICAL VALIDATION):** on 723 holdout windows, AUPRC rises from 0.6355 (round 0) to 0.6953 (round 3 candidate; nominal 95% interval [0.6621, 0.7620], 8 clusters) and AUROC from 0.7382 to 0.8135. At the predeclared 0.5 threshold the round-3 candidate predicts every window positive (recall 1.0000, specificity 0.0000, F1 0.3493); earlier rounds predict none. Ranking improves; the operating point does not separate classes.

**Live-monitored SITE_00:** a new simulated monitoring session streamed 172800 records through the monitoring runtime (93 real inference responses); its 93 emitted windows formed SITE_00's buffer. Observed: dataset identical to canonical = True; candidate digest equals canonical = True.

## Limitations (must appear in the paper)
- INTERNAL_TEST is held out from the V2 federated development lineage but is not project-globally unseen.
- INTERNAL_TEST has 6 contributing patient clusters; intervals are wide and unstable.
- INCART is a post-freeze external second look on a project-exposed dataset, not untouched validation.
- Confidence intervals are nominal 95% patient-cluster percentile intervals; no p-values or significance tests were computed.
- These results belong to the scientific FL experiments (AAMI_SVF_WINDOW_V1), not to the product engineering candidate.
- Synthetic lane: simulated participants and events; not clinical. No hardware was used.
- Historical centralized values were not re-run; no paired interval exists for them.
- The synthetic holdout has 8 clusters; intervals are nominal.

## Reproduction
`python -m scripts.freeze_synth_fl_eval_protocol`, `python -m scripts.run_synth_fl_eval --method-commit 6d79274c0ca4f159d210c69411a68238be3d2112 --out reports/final_showcase/synth_fl_eval`, `python -m final_showcase.figures`, `python -m scripts.run_live_link --out reports/final_showcase/live_link`.
