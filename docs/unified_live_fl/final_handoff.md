# NHM-UNIFIED-LIVE-FEDERATION-STUDIO-001 — final handoff

Local work only; **nothing was pushed**. Everything below is reproducible from the committed evidence in `reports/unified_live_fl/`.

## 1–3. Repository state
- Starting HEAD: `06bd9a0` (clean; 7 commits ahead of `origin/main` = `274323730d1c7355f688ad4c9ff01ecbfb746501`; FL10 baseline `e129a76` present locally).
- Final local commit and git status: the local commit titled `NHM-UNIFIED-LIVE-FEDERATION-STUDIO-001: …` at the tip of `main` (a file cannot contain its own commit hash; read it with `git log -1`). Working tree clean after the commit; nothing pushed.

## 4. Preserved Federation Studio components (byte-identical to `06bd9a0`, asserted by `studio/__tests__/preservation.test.ts`)
`ClientGrid` (eight-client network, coordinator hub, ★ MY EDGE CLIENT card), `ProcessStepper`, `RoundProgress`, `ModelStateTransition`, `CandidateLifecycle`, `FederationTimeline`, `ClientDetailPanel`, `RunConfigForm`, `TechnicalEvidence`, plus the live model, strict event parser, owner-binding rule (`participation.ts`) and presentation helpers. The live page keeps every original test id, panel (in the original order), import and style rule; the Studio only adds sections. ★ MY EDGE CLIENT still appears only for connected Clerk + LIVE_RUN (DemoAuth shows no owner; component tests cover CLERK/DEMO × LIVE/REPLAY).

## 5–6. Execution routes
- **3 rounds:** `POST /product/v1/federation/runs` → `…/{id}/start` → `FederationService` (frozen contract, `planned_rounds==3`; unchanged). The Studio only observes it (read-only instance wrappers: committed state, per-client optimizer diagnostics, per-batch hooks).
- **10 rounds:** `POST /product/v1/studio/runs` `{run_length:10, source_mode}` → `studio/runner10.py` → `fl10.runner.run_training` (same `Coordinator` and `train_local_epoch_v2`; three additive progress emits only). FedAvg/plain only; FedProx and SecAgg shadow are disabled in the UI with the reason and refused by the API (never reinterpreted).

## 7. New genuine 3-round run — `FEDRUN-FC8010F1CB54`
24 accepted updates, 4 evaluated states, candidate not promoted/deployed. Full evidence: `run_evidence_3round.json/.md`.

## 8. New genuine 10-round runs — canonical `FL10RUN-506306E748B3`, live-monitored SITE_00 `FL10RUN-A6B027257A1B`
80 accepted updates each, 11 evaluated states each. Evidence: `run_evidence_10round.json/.md`, `run_evidence_10round_modeB.json/.md`.

## 9. Evaluation cohort and protocol
Frozen FL10 holdout `WEARABLE_SIM_FL10_EVAL_HOLDOUT_V1` (16 participants, 1 446 windows), protocol `NHM_FL10_SYNTHETIC_EVALUATION_V1`, observer `NHM_STUDIO_LIVE_EVALUATION_OBSERVER_V1`, fixed threshold 0.5, `CAL_V2` not applied, no round selection. Label on every metric: **REUSED SYNTHETIC DIAGNOSTIC EVALUATION — NOT A NEW UNTOUCHED FINAL TEST** (`evaluation_policy.md`).

## 10. Full R0–R3 metric table (new 3-round run, measured per checkpoint)
| round | AUPRC | AUROC | F1 | specificity | recall | accuracy | BCE | Brier | TP | FP | TN | FN |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 | 0.628671 | 0.726971 | 0.000000 | 1.000000 | 0.000000 | 0.787690 | 0.650140 | 0.228541 | 0 | 0 | 1139 | 307 |
| 1 | 0.650689 | 0.753869 | 0.000000 | 1.000000 | 0.000000 | 0.787690 | 0.651131 | 0.229032 | 0 | 0 | 1139 | 307 |
| 2 | 0.653923 | 0.768804 | 0.006494 | 1.000000 | 0.003257 | 0.788382 | 0.640362 | 0.223684 | 1 | 0 | 1139 | 306 |
| 3 | 0.676186 | 0.802847 | 0.350257 | 0.000000 | 1.000000 | 0.212310 | 0.724338 | 0.265607 | 307 | 1139 | 0 | 0 |

## 11. Full R0–R10 metric table (new 10-round run, measured per checkpoint)
| round | AUPRC | AUROC | F1 | specificity | recall | accuracy | BCE | Brier | TP | FP | TN | FN |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 | 0.628671 | 0.726971 | 0.000000 | 1.000000 | 0.000000 | 0.787690 | 0.650140 | 0.228541 | 0 | 0 | 1139 | 307 |
| 1 | 0.650689 | 0.753869 | 0.000000 | 1.000000 | 0.000000 | 0.787690 | 0.651131 | 0.229032 | 0 | 0 | 1139 | 307 |
| 2 | 0.653923 | 0.768804 | 0.006494 | 1.000000 | 0.003257 | 0.788382 | 0.640362 | 0.223684 | 1 | 0 | 1139 | 306 |
| 3 | 0.676186 | 0.802847 | 0.350257 | 0.000000 | 1.000000 | 0.212310 | 0.724338 | 0.265607 | 307 | 1139 | 0 | 0 |
| 4 | 0.687019 | 0.820901 | 0.350257 | 0.000000 | 1.000000 | 0.212310 | 1.115110 | 0.441847 | 307 | 1139 | 0 | 0 |
| 5 | 0.776581 | 0.876662 | 0.350257 | 0.000000 | 1.000000 | 0.212310 | 1.751684 | 0.624151 | 307 | 1139 | 0 | 0 |
| 6 | 0.865008 | 0.933801 | 0.350257 | 0.000000 | 1.000000 | 0.212310 | 2.483803 | 0.721445 | 307 | 1139 | 0 | 0 |
| 7 | 0.915194 | 0.963609 | 0.350257 | 0.000000 | 1.000000 | 0.212310 | 3.110792 | 0.757527 | 307 | 1139 | 0 | 0 |
| 8 | 0.893162 | 0.952967 | 0.350257 | 0.000000 | 1.000000 | 0.212310 | 3.702153 | 0.773344 | 307 | 1139 | 0 | 0 |
| 9 | 0.878712 | 0.945603 | 0.350257 | 0.000000 | 1.000000 | 0.212310 | 4.001971 | 0.777798 | 307 | 1139 | 0 | 0 |
| 10 | 0.911570 | 0.966171 | 0.350257 | 0.000000 | 1.000000 | 0.212310 | 3.499216 | 0.768504 | 307 | 1139 | 0 | 0 |

These values equal the recorded NHM_FL10_001 evidence **because training is deterministic**: each state digest and each metric of the new runs was measured on the new run's own committed checkpoint and compared afterwards (11/11 and 4/4 equal for the canonical source; 11/11 for the live-monitored source). Nothing was preloaded. The unfavorable results stay visible: R03 and R10 predict every holdout window positive at the fixed 0.5 rule (specificity 0), R10 BCE 3.499216, Brier 0.768504, while ranking metrics improve (AUPRC 0.911570, AUROC 0.966171).

## 12. Live metric availability and timing
Each round's evaluation is queued the moment its state is committed and scored by one background worker on a private copy; training never waits. Measured in this environment (`evaluation_timing` in the evidence): 4–7 s per state for the 3-round run and 5–11 s for 10 rounds (the evaluation runs while the next round trains, so metrics for round k appear roughly one evaluation after it commits). When evaluation lags, the round shows `QUEUED`/`EVALUATING`, graphs mark it pending, and the metric cards state that they show the latest evaluated round. No real-time guarantee is claimed. The first evaluation of a process also builds the frozen holdout (≈ 40–60 s once).

## 13. Interactive graph inventory
Key graphs under the metric cards (FIG04 AUPRC/AUROC, FIG05 threshold metrics, FIG06 BCE/Brier, FIG02 training loss) with selected-round marker, click-to-select and pending markers; all other figures in the analysis tabs. Heatmaps/weights highlight the selected round.

## 14. Confusion-matrix verification
Per round TP+FN = positives and TN+FP = negatives (browser check for R0–R3 and R0/R3/R6/R10; backend table check TAB12); matrices shown for the comparison pair and every evaluated round (FIG09).

## 15. The 20 figures / 16. the 12 tables
All 20 (`FL10_FIG01–20`) and all 12 (`FL10_TAB01–12`) are reachable from the tabs for every run (`all 20 figures are reachable from the tabs`, `all 12 tables …`, and the parity test proving the live builders reproduce the delivered FL10 figures/tables exactly for the recorded run). Availability per run is in the evidence files (`figures`, `tables`).

## 17. Run-specific export verification
Each run exports 20×(SVG, PNG 300 dpi, CSV, JSON provenance), 12×(CSV, JSON, Markdown) and full-precision evidence data under its own run id; every download is re-hashed against the manifest in the browser and server-side (`X-Content-SHA256`); provenance names the run and a live source (never the recorded FL10 figure).

## 18. Screenshots
`reports/unified_live_fl/browser/` at 1440/1024/768/390 px for the entry page, the completed 3-round and 10-round runs and the recorded run; baseline originals in `docs/unified_live_fl/baseline/`.

## 19–25. Dependency audits and pages
`dependency_audit_before.md`, `dependency_audit_after.md`. Retained (KEEP): all federation pages and every Observatory research page; **redirected:** `/app/observatory/fl10` (→ Studio, `?run=` preserved); **removed:** none; **protected:** `/app/observatory/outcomes`, `/app/observatory/federation/[client_id]`; storyboard retained (unique content) and cross-linked. Links/tests migrated as listed in the audit.

## 26. Authentication
DemoAuth browser journey (281 checks, one explicit SKIP for a fixture run that existed only in an earlier workspace). Two-identity isolation tested at API and WebSocket level (another user receives 403 / close 4403 on every run-scoped route; recorded evidence is global read-only). **Connected Clerk two-user E2E: NOT EXECUTED** (two Clerk TEST user credentials are not available); DemoAuth never shows an authenticated owner.

## 27. Regression output
Full gates (`python -m scripts.run_studio_local_gates`, evidence `reports/unified_live_fl/local_test_report.json`):
- Backend: **3364 passed, 0 failed, 1 skipped** (10 chunks); `tests/test_studio_successor.py` validates the final lock separately.
- Frontend: vitest **343 passed, 0 failed, 3 skipped**; production build + stamp OK; svelte-check **0 errors**, 121 warnings (baseline 123).
- Launcher: `run_nhm --demo --preflight-only` passes. Real-browser journey: **281/281**.
- **Pre-existing monitoring race flake (reported separately):** `tests/test_capstone_monitoring_websocket.py::test_monitoring_completes_with_zero_subscribers` is intermittent on the pristine baseline `06bd9a0` as well (measured 8/12 isolated failures there, 4/12 at the Studio tip). It failed in several earlier full runs and in the first attempt of the final one (it passed on the recorded isolated retry); the gate runner retries only that named test in isolation and records every attempt (`flaky_retries`); no other failure is tolerated.
- Earlier-run failures that were caused by this work (route count 66→67, amendment/lock accounting, reconciliation link) were fixed through the governed additive mechanism, not by weakening tests.

## 28. Historical preservation
Every older verifier passes against the current tree through the additive chain (`CAPSTONE_UI_V1…V1_9`, `NHM_RESEARCH_OBSERVATORY_V1`, `NHM_OBS_DIAG_001`, `NHM_FINAL_SHOWCASE_001`, `NHM_FL10_001`, and the CAP-001…010 amended-lock audits); no historical lock or amendment was modified (only new compatibility amendments added); frozen scientific evidence, the recorded FL10 runs and the 3-round backend are byte-identical (`verify_unified_studio_001`). Pre-existing defects found and corrected additively are listed in the lock (`pre_existing_defects_corrected`) and `governance_repair.md`.

## 29. Successor lock
`artifacts/unified_studio/NHM_UNIFIED_LIVE_FEDERATION_STUDIO_001.lock.json` — additive successor of `NHM_FL10_001` (status PASS, non-provisional); binds 506 files incl. 312 frontend files; verified by `python -m scripts.verify_unified_studio_001 --lock` and `tests/test_studio_successor.py`. No historical lock was edited; nothing pushed.

## 31. Addendum — V2-initialised federated fine-tuning and the Generalisation tab
Delivered after first acceptance, inside the same Studio (`generalisation_protocol.md` has the design, decisions, measured results and limits):
- **Pretrained start** (`MODEL_V2_FINAL`, now the UI default for 3 and 10 rounds; the untrained `FL_INIT_V2` start is an explicit choice that restores the original frozen 3-round form): strict compatibility audit (digest pin, 92 state entries, 57 553 elements, strict load round trip, logits parity), additive `initial_state` option in `fl10/runner.py`; frozen-FL_INIT parity claims are not made for this mode.
- **Unseen cohort G1** (16 new synthetic participants, pinned manifest, zero overlap with training, showcase holdout and FL10 holdout) and a **second evaluation lane** that scores every committed round and the unchanged frozen V2 on it, with paired participant-cluster differences (round − V2).
- **UI/API/exports**: Analysis ▸ GENERALISATION, three read-only owner-scoped routes, hash-verified generalisation exports; browser journey now 281 checks including genuine pretrained-start 3-round and 10-round runs.
- **Measured (synthetic, unseen participants):** pretrained start R0 = frozen V2 exactly (AUPRC 0.8902) → R10 0.9915 with specificity 0.997 and BCE/Brier not improved reliably; untrained start reaches AUPRC 0.943 at R10 but specificity is 0 from R3 and BCE 3.47 (the earlier negative finding reproduced on a never-used cohort).
- **3 rounds from the pretrained start** run on the extended engine (FedAvg, plain; the frozen 3-round product contract only accepts the untrained start, so FedProx and the protected-aggregation shadow exist only on the untrained 3-round path).
- **Not done:** real-ECG AAMI-SVF retention (G2) is NOT EXECUTED; nothing here is clinical or a significance claim.

## 30. Undelivered / residual risks
See `known_limitations` in the lock. In short: connected Clerk two-user E2E not executed; the 16-participant cohort is reused (diagnostic only); 10-round supports FedAvg/plain only; runs started before the observer carry no metrics; the offline `--demo` launcher serves the older app (10-round disabled there with an explanation); an interrupted 10-round run fails closed and restarts from R0; the pre-existing monitoring race flake is untouched (see §27). Not claimed: any clinical validity, hardware, or an untouched final test.
