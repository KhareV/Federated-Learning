# V2-FL-003 — MODEL_V2 FedProx (μ=0 equivalence, LABEL-only μ selection, matched FedAvg-vs-FedProx)

**Result: PASS** (V2FLG2 = PASS; FedProx improvement is not a criterion). Entry `0fdc185`; method commit `dd9d9df`; selection-freeze commit `89accff`; result commit follows. INTERNAL_TEST was **not accessed**.

## Roadmap successor
`MODEL_V2_FL_PROTOCOL_V2` (additive; V1 protocol byte-unchanged, created before any FedProx outcome) inserts **V2-FL-EVAL-001** (held-out evaluation of the frozen FL family) before V2-FL-004; V2-FL-004 prerequisite re-pointed accordingly. V2FLG2 defined in the method commit (blocks V2-FL-EVAL-001).

## Objective and μ=0 equivalence
Loss = BCEWithLogits + μ/2·‖w−w_global‖² over **trainable** parameters (47 tensors; BatchNorm running stats and `num_batches_tracked` excluded; w_global = round-start global). At μ=0 the penalty is not added.
μ=0 vs V2 FedAvg: loss delta 0.0, max gradient delta 0.0, all 8 LABEL clients' round-1 update delta 0.0, round-1 aggregate sha `3f57e799f19a…` = stored V2-FL-002 LABEL round-1 sha (exact; repeated in both fresh-process verifications).

## LABEL-only candidates (FL_INIT_V2, 50 rounds x 8 clients each)
| μ | best round | best AUPRC | round-50 | patient-macro AUPRC | patient-worst AUPRC | guardrail |
|---|---|---|---|---|---|---|
| 0.001 | 39 | 0.8183 | 0.8119 | 0.7588 | 0.1131 | True |
| 0.01 | 41 | 0.8285 | 0.8274 | 0.7303 | 0.0850 | True |
| 0.1 | 41 | 0.8199 | 0.8180 | 0.8574 | 0.4390 | True |

LABEL FedAvg baseline: macro 0.7247, worst 0.0381. Guardrail threshold = 0.0381 − 0.05 = **−0.0119**: non-binding by arithmetic (AUPRC ≥ 0), documented before results and not repaired.
**Selected μ = 0.1** (ranking [0.1, 0.001, 0.01]; primary = patient-macro AUPRC; selection run twice, identical; no human override). Frozen in `FEDPROX_MU_V2` (sha `a95e44cdef92…`) and committed (`89accff`) before any transfer run. The selected candidate is the canonical LABEL FedProx result (alias, not retrained). Historical MODEL_V1 `FEDPROX_MU_V1` (μ=0.01) was not reused.

## Matched FedAvg vs FedProx (μ=0.1; clean VALIDATION, development only)
| condition | best AUPRC FedAvg → FedProx (Δ) | round-50 Δ | AUROC Δ | patient-macro F1 | patient AUPRC mean/median/worst FedAvg → FedProx | best round |
|---|---|---|---|---|---|---|
| IID | 0.8669 → 0.8793 (+0.0123) | +0.0495 | +0.0111 | 0.4443 → 0.5536 | 0.871/0.945/0.622 → 0.904/0.967/0.632 | 38 → 49 |
| LABEL | 0.8066 → 0.8199 (+0.0133) | +0.0114 | +0.0046 | 0.4206 → 0.3884 | 0.725/0.941/0.038 → 0.857/0.925/0.439 | 50 → 41 |
| QUANTITY | 0.8874 → 0.8325 (-0.0548) | -0.0709 | -0.0350 | 0.6622 → 0.5838 | 0.905/0.964/0.702 → 0.882/0.950/0.648 | 47 → 48 |
| FEATURE | 0.8502 → 0.8325 (-0.0176) | -0.0191 | -0.0051 | 0.6625 → 0.6543 | 0.918/0.982/0.714 → 0.914/0.976/0.733 | 50 → 43 |
| COMBINED | 0.8202 → 0.8003 (-0.0200) | -0.0242 | -0.0065 | 0.4598 → 0.5524 | 0.922/0.950/0.749 → 0.815/0.918/0.190 | 42 → 48 |

Paired bootstrap, FedProx − FedAvg pooled AUPRC (B=2000, seed 20260927, 7 VALIDATION groups, identical deterministic draws). **DEVELOPMENT DIAGNOSTICS ONLY** — both methods select checkpoints and μ was selected on this VALIDATION set; not untouched-generalization intervals; not a criterion.
| condition | mean Δ [95% CI] |
|---|---|
| IID | +0.020 [+0.002, +0.070] |
| LABEL | +0.019 [-0.049, +0.121] |
| QUANTITY | -0.047 [-0.123, +0.044] |
| FEATURE | -0.031 [-0.182, +0.013] |
| COMBINED | -0.021 [-0.123, +0.041] |

## Observations (not claims)
- FedProx (μ=0.1) is **selective**: slightly better on IID and LABEL, worse on QUANTITY (−0.055), FEATURE (−0.018) and COMBINED (−0.020) pooled AUPRC. μ was tuned on LABEL only and transferred unchanged.
- The clearest LABEL effect is on the worst-served patient (worst-patient AUPRC 0.038 → 0.439; macro 0.725 → 0.857) while pooled AUPRC changes little (+0.013) — exactly what pooled metrics hide.
- Most paired intervals include 0 (only IID excludes it); 7 validation patients; best-round values optimistic. FedProx does **not** replace FedAvg as the primary FL method; no held-out claim.
- Logical payload unchanged (192,662,400 B per run; 1,926,624 B per direction per round). Wall time: ~3400–3840 s per transfer run; the three LABEL candidates ran concurrently on one machine, so their (and the LABEL alias) wall times (up to ~6980 s) are contention-inflated and not comparable.

## Accounting
Candidates 150 rounds / 1200 updates; transfer 200 rounds / 1600 updates; **total 2800/2800**, 0 failed clients, 0 nonfinite tensors, 0 aggregation failures, 0 loader failures, 0 infrastructure retries. All 7 runs start from FL_INIT_V2 (`6a2923ca…`, AUPRC 0.25769…).

## Firewall / protected / reproducibility
Accessed: TRAIN, VALIDATION, NSTDB pure-noise records (FEATURE/COMBINED only; ledger role `NSTDB_PURE_NOISE_TRAINING_RESOURCE`). **INTERNAL_TEST, CALIBRATION, INCART, BIDMC, WEARABLE, WEARABLE_SIM: not accessed.** CAL_V2 absent. No protected artifact drifted (V2-FL-001/002 evidence and checkpoints, manifests, V1 FedProx, MODEL_V1/V2_FINAL, CALs, gateways, runtimes). Two fresh-process verifications x 7 runs: round-1 replay from FL_INIT_V2, best-round reconstruction, checkpoint hashes, exact VALIDATION-prediction replay, selection recomputed twice, μ=0 aggregate re-run — all PASS.

## Checkpoints (14 files force-added; `*.pt` is gitignored)
- LABEL μ=0.001: best `dedd10dca3f1e4b79328e2e82ca3386504bd5091c9839a28336fda415c6be863`, round-50 `4c1dd5daa9ce9d8b25228834ee6f8efb146d07d1f20efa682c7f30d9cfdf7ccb`
- LABEL μ=0.01: best `e6ae62859209a98766a71cab412e76a0525c544a4fc4bc365cc53bcf6130cebc`, round-50 `087d242b7af46ecba932ddb7058bd1fb8458adf18dbd17af160c5f9d9ebff90a`
- LABEL μ=0.1: best `6c319b53ff5310b5319487f246c523178bed0df99678614ccf59d6cc951418d9`, round-50 `14f6d26ef97eaa259d419727e5e18525916fbfb71afda650e481c1887e55ff70`
- IID: best `e9adcb6457dd0e9c4bdb85a00df12ebab0d33be1a8712321bb027300d39dbee7`, round-50 `d76728d52b8e0e7989e3e0cfdf45c4ac3c06931cc35e8f9f715c929e30202a1e`
- QUANTITY: best `1323aa3f22de5d2cd2b359d912cc48e00ccb07f6c41838f7872299665edab874`, round-50 `0c897e793df7b6e392079a8c68a9d4991c31114c4cd6ab7fa5d566946276efaa`
- FEATURE: best `41894e4dfdf008136dc4c599c670df5cefbdefd460c6a84efc6399edc3d3c1b6`, round-50 `b0745bb322d5d1b14c94d99923e73570adff223bfde0f30442c99913ba200709`
- COMBINED: best `ee6f2620262ad097a557313c1c03c242bbe26821f603b5132a5a651c2dc46568`, round-50 `651aa013b2bf34321a374aa1d36d1618cd8392ac7f15e5a6af7efd7e75332769`

## Disclosures
- `scripts/finalize_v2_fl_003_evidence.py` (hash-pinned) was amended after the freeze to fix an evidence-assembly KeyError (eager dict default on V2-FL-002 communication records); disclosed with its diff in `method_immutability_audit.json`; no training/selection/metric value affected.
- Historical lifecycle tests (`test_v2_fl_001_results`, `test_v2_fl_002_results`, `test_v2_fl_002_method`) were relaxed to accept V2-FL-003 PASS (forward lifecycle). `tests/test_v2_fl_002_method.py` is hash-pinned by the V2-FL-002 method freeze, so a re-run of its method-drift check would now report that one file (disclosed; the V2-FL-002 evidence is unchanged).
- ruff, `pip check`, chunked pytest: 0 missing / duplicate / unexpected / failed. CI never queried or triggered.

## Decision
V2-FL-003 accepted; V2FLG2 PASS; FEDPROX_MU_V2 frozen; V2-FL-EVAL-001 may start (not started).
