# V2-FL-001 — MODEL_V2 IID FedAvg on real MIT-BIH TRAIN patients

**Result: PASS** (gate V2FLG0 = PASS). Method commit `2ce8108` (pre-result); result commit follows it.

## Method (frozen before the first real outcome)
MODEL_V2_FL_PROTOCOL_V1 (predeclares V2-FL-001..005, reuse of NONIID_LABEL/QUANTITY/FEATURE/COMBINED manifests by SHA, synthetic-wearable = engineering evidence only), FL_INIT_V2, FL_IID_MODEL_V2_V1. T025 budget and local-training semantics verbatim (8 clients x 8/round x 50 rounds, 1 local epoch, batch 64, drop_last false, AdamW 1e-3/1e-4 reset each round, BCEWithLogits pos_weight 6103/3557=1.7157717177396683, SAMPLE_COUNT_WEIGHTED_MODEL_DELTA_V1). Shuffle-seed namespace = historical `FL_IID_V1` (T026 precedent), so V1 and V2 clients share per-client per-round seeds; the architecture is the variable. `train_local_epoch_v2` is bit-identical to T025's function when given the MODEL_V1 factory (differential test).

## State transport
FL_STATE_TRANSPORT_V1 reused UNCHANGED (policy and code are dtype-generic; no V1 key/count logic). MODEL_V2 state = 92 entries: 47 floating trainable + 30 floating BatchNorm buffers + 15 int64 `num_batches_tracked` (never averaged; tested per key). Adapter round-trip max |raw-logit delta| = 0.0. No FL_STATE_TRANSPORT_V2.

## Clients / initialization
CLIENTS_IID_V1 reused (sha 80f38fa25c508f9b…b32a, not regenerated): 27 TRAIN patients, 9660 windows (3557 pos / 6103 neg), 8 sites (4/4/4/3/3/3/3/3), zero overlap with VALIDATION/CALIBRATION/INTERNAL_TEST. FL_INIT_V2 = fresh untrained MODEL_V2_TCN_MEAN, seed 20260927, round-0 sha `6a2923ca…a572f` identical in-process and in a fresh process; MODEL_V2_FINAL was read only to confirm the states differ, never loaded as initialization.

## Training
50/50 rounds, 400/400 client updates, 0 failed clients, 0 nonfinite tensors, 0 aggregation failures; Flower-serde parity check PASS (round 1). ~74 s/round, 3690 s total (CPU). Logical payload 1,926,624 B per direction per round (MODEL_V1: 434,912).

## Validation (development only; raw sigmoid, no calibration, threshold 0.5 descriptive)
| | MODEL_V1 FL_IID_V1 | MODEL_V2 FL_IID_MODEL_V2_V1 |
|---|---|---|
| parameters | 13,185 | 57,553 |
| round-0 AUPRC | 0.1923 | 0.2577 |
| best round / AUPRC | 1 / 0.5062 | 38 / 0.8669 |
| round-50 AUPRC | 0.4002 | 0.8268 |
| best AUROC | 0.7354 | 0.9299 |
| F1@0.5 / patient-macro F1 | 0.3802 / 0.3081 | 0.7057 / 0.4443 |
| BCE | 0.8209 | 0.4589 |
| sensitivity / specificity@0.5 | 1.000 / 0.000 | 0.837 / 0.836 |

Paired patient-cluster bootstrap (existing 2000-draw framework, seed 20260927, 7 VALIDATION patient groups, each model at its own selected round): delta AUPRC mean +0.332, 95% CI [+0.175, +0.456]. Descriptive development evidence, not a promotion criterion.

## Scientific caveats (not warnings that change the outcome)
- Round 38 was selected on VALIDATION; late-round AUPRC fluctuates (0.76–0.87 over rounds 21–50), so the best-round figure is optimistic as an estimate. Round-50 (0.827) is the fairer single-number.
- Patient-macro F1 (0.444) is far below pooled F1 (0.706); patient-level AUPRC ranges 0.62–1.00 (worst MITDB_P108 0.622, P109 0.663; P112 and P231 have only 4 and 2 positive windows).
- Only 7 VALIDATION patients: wide uncertainty. V1 selected a degenerate round-1 model (sensitivity 1.0 / specificity 0.0), which inflates the V2-V1 contrast.
- Site-local TRAIN diagnostics (mean AUPRC 0.995) are TRAIN diagnostics, not held-out client validation.
- No CAL_V2, no threshold derivation; controlled simulated sites, no privacy claim.

## Checkpoint / reproducibility
`checkpoints/model_v2/v2_fl_001/FL_IID_MODEL_V2_V1_best.pt` sha `e90749ee…3ca5` (264,559 B) and `..._round50.pt`. Two fresh-process replays: best round recomputed from the log = 38, checkpoint sha stable, validation predictions replayed identically, init sha reproduced.

## Firewall / protected
Ledger rows for V2-FL-001: TRAIN and VALIDATION only; CALIBRATION, INTERNAL_TEST, INCART, NSTDB, BIDMC, WEARABLE: not accessed; WEARABLE_SIM not used. Protected audit (MODEL_V1, CAL_V1, MODEL_V2_FINAL, CAL_V2, gateways, runtimes, FL locks, CLIENTS_IID_V1, V1 FL evidence, V2-012/013/C-V2-013 evidence): no drift. Method files unchanged since freeze. QUALITY_V1 flatline limitation carried forward, not repaired.

## Tests / decision
ruff, pip check, chunked pytest: 0 missing / duplicate / unexpected / failed. CI never queried/triggered.
V2-FL-001 accepted; V2FLG0 PASS; V2-FL-002 may start but was NOT started.
