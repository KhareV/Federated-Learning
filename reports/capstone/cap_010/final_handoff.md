# CAP-010 HANDOFF — Complete Faculty End-to-End Demonstration (gate CAPG9)

## 1. PHASE RESULT
CAP-010 / CAPG9: **PASS** — 104/104 prospectively frozen (consolidated) criteria (`capg9_criteria.json`). Integration/demonstration phase only. Readiness claim, limited exactly to: *the NHM capstone product is ready for an offline one-laptop faculty demonstration using simulated device input, released research monitoring, genuine engineering federation, persistent history, and frozen research-evidence views.* No clean-machine release, physical-wearable, clinical, production-deployment, security or scientific-efficacy claim is made.

## 2. ENTRY
Entry HEAD == origin/main == `be778d4ced186639155064e94516ff096751a81f` (CAP-009 result). Immutable entry audit commit `a7bd1a7` (`entry_audit.json` byte-unchanged since; no correction file needed). CAP-001..009 locks and amendment chains, UI V1/V1_1/V1_2, research catalog, FL_INIT_V2, FEDPROX_MU_V2, V2-FL protocol all verified (`prior_lock_verification.json`: 17 chains verified incl. the new CAP-010 lock).

## 3. UPSTREAM PROTECTION
Zero drift vs entry in api/, product/, capstone_persistence/, frontend/ (incl. CAPSTONE_UI_V1_2, 230 files), federated/, reports/model_v2, checkpoints, contracts, MODEL_V1/V2_FINAL, calibrations, SOFTWARE_SYSTEM_V2, DEFAULT/ROLLBACK runtime bindings, CAPSTONE_PRODUCT_API_V1_3, CAP-006/007 implementation and the research catalog (`protected_artifact_final.json`: protected_artifact_drift=false; only registries and the lifecycle test modified; every added file in a CAP-010 additive namespace). No new Python/npm dependency, no new API route.

## 4. PROTOCOL
`CAPSTONE_FACULTY_DEMO_PROTOCOL_V1` (104 criteria, 16 mutation controls) frozen in commit `1cf39e9` BEFORE any canonical result, with lock `artifacts/capstone/CAPSTONE_FACULTY_DEMO_PROTOCOL_V1.lock.json` and `component_registry_cap_010_v1.csv` (7 components). Zero post-freeze amendments to the protocol. The frozen criteria text labels one test title with a `T:` prefix although it lives in the preflight test file; the evaluator resolves titles uniquely across CAP-010 files (disclosed, not an edit of frozen text).

## 5. DEMO LAUNCHER
One governed command `python -m scripts.run_capstone_faculty_demo --acknowledge-demo-auth …` manages exactly three services: inference `run_nhm_default --profile default` (8001), product `run_capstone_product_v1_3` (8002), frontend `npm run preview` after `npm run build` (4173). Explicit DemoAuth acknowledgement required (nothing starts without it); no rollback-v1 exposure; ports occupied → `PORT_IN_USE`, occupant never touched; no automatic pip/npm install; the launcher issues no write request (`launcher_audit.json`, `launcher_negative_tests.json`).

## 6. WORKSPACE
`CAPSTONE_DEMO_WORKSPACE_V1`: outside Git, sentinel `CAPSTONE_DEMO_WORKSPACE_V1.json`, FRESH never silently erases, RESUME requires a valid sentinel, safe reset refuses `/`, home, repo root/ancestors/descendants and sentinel-less directories (`workspace_safety_audit.json`).

## 7. PREFLIGHT
Identity/artifact checks only (locks, phase state, runtime binding, product import, UI successor, catalog, Python/imports, frontend deps and build stamp, ports); executes no science (AST-tested). Real environment passes the real preflight CLI (`preflight_audit.json`).

## 8. SERVICE SUPERVISION
READY only after all three readiness probes; child death/timeout stops the stack; Ctrl+C = graceful reverse-order shutdown; own process groups only (`killpg`), no orphans, per-service logs (`inference.log`, `product.log`, `frontend.log`) in the workspace; secret scan clean in both canonical runs (`process_supervision_audit.json`).

## 9. PREWARM
Optional `--prewarm-federation` performs `GET /federation/clients` only: 8 clients, 0 runs, 0 candidates, 0 training calls, binding unchanged, before/after audit equal (`prewarm_audit.json`; 12.4 s machine-specific).

## 10. RUNBOOK
`docs/capstone/FACULTY_DEMO_RUNBOOK_V1.md`: short (~5–7 min) and full (~10–15 min, planning range only) paths, talk tracks, personalization answer NO, MODEL_V2_NOT_PROMOTED_RELEASE_CI vs SYSTEM_V2_RESEARCH_DEFAULT_ACCEPTED, hardware VERIFICATION_REQUIRED, recovery guidance. Claim audit: no unnegated overclaim; overclaim mutations rejected (`faculty_runbook_audit.json`, `claim_audit.json`).

## 11. FULL DEMO SCENARIO COVERAGE
NORMAL_MONITORING, CONTEXT_LOSS, POOR_SIGNAL, DISCONNECT_RECONNECT, FL_SINGLE_RUN, FL_SECAGG_SHADOW all PASS on the real stack (headless, separate temporary workspace, no mocks, no outcome tuning, no model output asserted) plus MIXED_MONITORING_SESSION as hero (`scenario_coverage.json`, `full_demo_scenario_coverage.json`).

## 12. CANONICAL FULL DEMO RUN 1
Fresh workspace, real headless Chrome through the loopback-only launcher stack: sign-in (DEMO, Clerk not initialised) → overview → device → MIXED_MONITORING_SESSION (ACCELERATED; MODEL_V2_FINAL/CAL_V2; quality VALID+UNUSABLE; disconnect/reconnect gap; COMPLETED; 86 inference events) → history → LIVE_RUN FEDAVG SECAGG_SHADOW (8 clients, 3 rounds, 24 updates, one candidate) → models → research ML/FL → system → about. Zero console errors; clean shutdown (`full_browser_demo_run_1.json`).

## 13. CANONICAL FULL DEMO RUN 2
Second fresh workspace, same journey, same outcome (`full_browser_demo_run_2.json`).

## 14. REPRODUCIBILITY
Semantic digests equal: `3a57614e15264f3cd7661a016a30d033aab78647d57be04273c386cc9d048726` (both runs; projections equal). Exclusions (ids, times, latency, pids, log text, paths, screenshots, wall-clock) documented in `full_demo_reproducibility.json`.

## 15. MONITORING
Real SimulatedWearableSource → device/product API → SOFTWARE_SYSTEM_V2 (MODEL_V2_FINAL, CAL_V2); persisted summary/timeline/bounded preview with CAP-009 count-basis, time-domain and probability-label semantics intact.

## 16. FEDERATION
LIVE_RUN, FEDAVG, SECAGG_SHADOW; eight logical synthetic clients, 3 rounds × 8 accepted = 24 genuine updates; authoritative aggregation PLAIN, round-1 shadow SHADOW_VERIFIED; exactly one candidate `CAPSTONE_FL_CANDIDATE_0001` (parent FL_INIT_V2, state digest `3f0b7762…70e4`), validation PASSED, ACCEPTED_TO_SANDBOX, IN_SANDBOX, production_deployed=false.

## 17. RESEARCH
ML page: frozen evidence, promotion-vs-release distinction, MIT-BIH source-domain calibration caveat; FL page: V2-FL-001..004 evidence, FedProx/SecAgg limits, V2-FL-005 shown as engineering only; catalog sha `2c3d2d15…c983f` unchanged.

## 18. RESTART / RESUME
Same workspace stopped and RESUMEd (`demo_restart.json`): session/history/run/candidate/governance preserved, DB counts equal, no new run or candidate, no monitoring or FL rerun, API payloads byte-equal, catalog unchanged, identical semantic digest.

## 19. OFFLINE
Browser requests intercepted at CDP level (loopback continue, all else failed): 0 external requests, 0 blocked attempts in both runs and the restart; Clerk global absent. Claim limited to NHM demo processes and the demo browser journey (`offline_network_audit.json`).

## 20. RELEASED DEFAULT ISOLATION
MODEL_V2_FINAL remains RELEASED_DEFAULT; the candidate has no inference runtime, no promote/deploy control (models page controls = []), no monitoring role.

## 21. OUT OF SCOPE
Not done: CAP-011/clean-machine release; frontend, API, backend, FL, scientific changes; candidate inference/sandbox runtime/deployment; held-out evaluation, retraining, recalibration; FL_NEW_LOCAL_BATCH/FL_MULTIRUN; training on user data/personal models; physical hardware; new dependencies.

## 22. TESTS
Targeted CAP-010: 79 passed. Full Python regression: 3016 passed, 1 skipped, 1 deselected (inherited CAP-003 race; isolated probe 6/12 passes, only the known failure signature otherwise). Frontend: vitest 193 passed / 3 skipped; svelte-check 0 errors (112 warnings, pre-existing); build OK. ruff clean; `pip check` clean. 16/16 mutation controls caught and restored (`mutation_controls.json`). CI neither queried nor triggered. Recorder defect: `cap_010_test_report.py` first judged svelte-check FAIL by a case-sensitive string compare ("0 ERRORS"); fields were recomputed from the saved logs and the script fixed (note inside `test_report.json`).

## 23. CONTROL PLANE
Registry: CAP-010 PASS, CAPG9 PASS, CAP-011 NOT_STARTED (no CAP-011 artifact exists).

## 24. GIT
Entry `be778d4`; entry audit `a7bd1a7`; lifecycle amendment 9 `45e8fc7`; prospective registration `42d235d`; `a023e40` (amendment, renamed to `9_1`); `2022329` (see disclosures); freeze `1cf39e9`; result commit = the commit carrying this file (pushed to origin/main).

## 25. DISCLOSURES
- Accelerated simulation timing: the hero session runs ACCELERATED for presentation.
- Federation clients are logical one-laptop synthetic partitions, not hospitals/sites.
- SecAgg is a round-1 shadow only; authoritative aggregation is PLAIN; not differential privacy.
- The candidate is not deployed (sandbox only); the candidate sandbox has no inference runtime.
- Physical wearable absent; hardware status VERIFICATION_REQUIRED.
- Clerk live WebSocket limitation inherited from CAP-005; demo uses DemoAuth with explicit acknowledgement.
- CAP-003 inherited timing race (one test deselected under the documented policy).
- Timings are machine-specific telemetry, not requirements.
- CAP-008 amendment `85fe0b3` included unrelated result evidence (carried forward).
- CAP-007 one-active-run is not a distributed lock.
- CAP-009 `npm ci` reported seven dependency advisories (no dependency change here).
- Commit `2022329` is titled as a pure test re-name but, by a `git add -A` mistake, also bulk-committed the whole CAP-010 implementation (launcher, workspace, preflight, runbook, driver, runner, tests); this happened BEFORE the freeze commit, so no result is affected.
- Before the freeze: one manual launcher start/stop and one full dry run of coverage + journey + restart into a scratch directory outside the repository found defects (fake-service helper, wrong argv slice, missing federation-page capture); none of that output is committed.
- After the freeze, new pure tooling (`cap_010_build_evidence.py`, `cap_010_evaluate_gate.py`, `cap_010_test_report.py`) was added; criteria text and the protocol lock are unchanged. The mutation-control dry run found one weak test (repo-root reset) fixed before the freeze.

## 26. FINAL DECISION
CAPG9 PASS. CAP-010 complete. CAP-011 NOT STARTED. Returning CAP-010 handoff only.
