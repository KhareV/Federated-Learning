# CAP-011 HANDOFF — One-Laptop Clean Capstone Release (gate CAPG10)

## PHASE RESULT
CAP-011: **PASS** · CAPG10: **PASS** (136/136 frozen criteria, 23/23 hard blockers, `capg10_criteria.json`) · CAPSTONE_RELEASE_V1: **ACCEPT** (`release_decision.json`, manual_override=false).

## ENTRY
Actual entry SHA `af60c1e2bc6a645852d0826815ff16a678c9d0d1` == origin/main, clean. The expected `f0bcc1693a75155b41ec9a3cd2abd994c5e88029` was followed by exactly two user-authorised, pure compatibility amendments (`7360cee` CAP-010 faculty preflight phase-state predicate — CAP-011 may be NOT_STARTED/IN_PROGRESS/PASS only once CAP-010 and CAPG9 are PASS; `af60c1e` historical lifecycle guard amendment 9_2). CAP-001..010 PASS, CAPG0..9 PASS. Entry audit commit `c8461b1` (immutable; no correction file).

## HISTORICAL SCOPE
Historical RELEASE_V1 touched? NO · T036 NO · G22 NO · F15 NO (root registry rows and RELEASE_V1 files hashed at entry and unchanged at final).

## UPSTREAM PROTECTION
Scientific drift NO · runtime drift NO · FL drift NO · frontend drift NO · product API/backend drift NO · CAP-010 launcher/runbook/runner drift NO (apart from the authorised preflight predicate amendment made before entry). `protected_artifact_final.json`: protected_artifact_drift=false.

## RELEASE PROTOCOL
CAPSTONE_RELEASE_PROTOCOL_V1, CAPSTONE_RELEASE_POLICY_V1 (manual_override_allowed=false, waivers none, 23 hard blockers), CAPSTONE_CLEAN_CLONE_PROTOCOL_V1, frozen together with the harness, verifier and the CAPG10 evaluator in the release-target commit `3ad1b07408a0c3556fbc5039f1a7a4fee824db96`. Criteria: 136 (the 132 required + portability, case-collision, harness no-rescue static audit, mutation log). Post-freeze amendments: none.

## RELEASE TARGET
RELEASE_TARGET_SHA `3ad1b07408a0c3556fbc5039f1a7a4fee824db96`; origin/main == local HEAD == target when recorded; working tree clean; pushed before both clones (`release_target.json`). Release vehicle: the exact Git repository state (no archive, no installer). Tag `capstone-release-v1` is created on the target after this result commit (see GIT).

## RELEASE MANIFEST
`artifacts/capstone/CAPSTONE_RELEASE_MANIFEST_V1.json`: 26 key artifact hashes (MODEL_V2_FINAL, CAL_V2, GATEWAY_ARTIFACT_V2, DEFAULT/ROLLBACK runtime bindings, SOFTWARE_SYSTEM_V2, FL_INIT_V2/FEDPROX_MU_V2, API V1_3 source, UI V1_2 lock, research catalog + lock, faculty protocol lock, launcher, runbook, …) and 7 dependency-lock hashes. Launch command `python -m scripts.run_capstone_faculty_demo --acknowledge-demo-auth --build --prewarm-federation --workspace <outside repo>`. Claim: clean-clone reproducible, one-laptop research-software/faculty-demonstration release (exact text frozen). 21 limitations carried.

## CLEAN CLONE A
Source: remote git clone at the exact SHA (checkout verified). Manual copies NO. Fresh Python 3.11.16 venv inside the clone, created by the run. Node v26.5.0 / npm 11.17.0; `npm ci` for frontend and clerk-sdk from committed locks. Raw data copied NO; hidden `.env` NONE. Release verifier PASS. Python tests: targeted 38 passed; full regression 3038 passed, 20 skipped (18 data-gated, 1 untracked-T015-artifact gate, 1 documented inherited post-exposure skip, 0 unexpected), 1 deselected. CAP-003 race: deselected in the full run; isolated attempts 1–2 failed with the known signature, attempt 3 passed (policy satisfied). vitest 193 passed/3 skipped; svelte-check 0 errors (112 warnings, pre-existing); build OK. Faculty preflight PASS. Full browser demo PASS. Restart/resume PASS. Offline: 0 external requests. Tracked drift NONE. Result PASS.

## CLEAN CLONE A DEMO
Monitoring MODEL_V2_FINAL; calibration CAL_V2; session COMPLETED; history loaded (summary/timeline/bounded preview); 8 logical clients; 3 rounds; 24 genuine updates; aggregation PLAIN; SecAgg round-1 shadow verified; one candidate CAPSTONE_FL_CANDIDATE_0001 (structural validation PASSED); governance ACCEPTED_TO_SANDBOX / IN_SANDBOX; production_deployed=false; research ML/FL pages valid against the catalog; hardware SIMULATED_ONLY.

## CLEAN CLONE B
Distinct fresh remote clone, distinct directory, venv, npm installs and runtime workspace; same target SHA; manual copies NO; release verifier PASS; tests identical (3038 passed, 20 skipped, 0 unexpected; CAP-003 isolated attempt passed first time); frontend 193 passed, 0 svelte errors, build OK; full faculty demo PASS; offline 0 external requests; tracked drift NONE. Result PASS.

## CLEAN-CLONE REPRODUCIBILITY
Clone A semantic digest == Clone B semantic digest == `3a57614e15264f3cd7661a016a30d033aab78647d57be04273c386cc9d048726` (also equal to the CAP-010 canonical digest); full projections equal; identical=true. Approved exclusions: session/run ids, timestamps, latencies, PIDs, temporary paths, machine-time telemetry, logs, screenshots.

## DEPENDENCY / INSTALLATION
Python: `pip install -r requirements-dev.lock` then `-r requirements-capstone-auth.lock` (public PyPI); frontend: `npm ci` (public npm); ClerkJS: `npm ci --prefix frontend/clerk-sdk`. Network required for installation: YES. Network required for the demo runtime: NO (loopback only, verified). Developer environment reused: NO. No new dependency pin.

## CLEAN-CLONE BOUNDARY
Raw biomedical data required: NO. Full raw scientific re-execution claimed: NO. Developer .env/DB/candidate artifacts required: NO. Manual rescue performed: NO.

## RELEASE DECISION
All 23 policy hard blockers evaluated by the frozen evaluator: all passed. Decision ACCEPT, manual override false. Scope: one-laptop clean software/faculty-demo release on the tested platform (macOS 27.0.1 arm64, Python 3.11.16, Node v26.5.0, npm 11.17.0, Chrome 154.0.8037.98). No other OS is claimed.

## RELEASED MONITORING
SOFTWARE_SYSTEM_V2 → MODEL_V2_FINAL → GATEWAY_ARTIFACT_V2 → CAL_V2 → ALERT_POLICY_V1_MODEL_V2_BINDING → API_SCHEMA_V1 via DEFAULT_RUNTIME_BINDING_V2, unchanged. Candidate used for monitoring NO; candidate inference NO; candidate deployment NO. MODEL_V2_NOT_PROMOTED_RELEASE_CI and SYSTEM_V2_RESEARCH_DEFAULT_ACCEPTED are preserved; the release decision answers a third question and promotes nothing.

## LIMITATIONS
Non-diagnostic research prototype; physical wearable absent; WEARABLE_V1 validation absent; simulation-only device path; accelerated demo timing; MODEL_V2 promotion CI crossed zero; only six eligible INTERNAL_TEST groups; CAL_V2 source-domain only; V2-010/INCART second-look caveats; QUALITY_V1 stuck-nonzero limitation; SecAgg narrow protected-aggregation-interface claim; no differential privacy; logical one-laptop FL clients; candidate sandbox has no inference runtime; candidate not deployed; Clerk real-account WebSocket path not verified; one-active-run is not distributed locking; CAP-003 inherited race; npm advisories disclosed; installation may need registry network access; clean release is not raw-data scientific re-execution. Not security audited, not penetration tested, not HIPAA compliant, not privacy certified, not production hardened.

## FINAL MAIN VS RELEASE TARGET
RELEASE_TARGET_SHA = `3ad1b07408a0c3556fbc5039f1a7a4fee824db96` (the actual CAPSTONE_RELEASE_V1 product verified from fresh clones). FINAL_MAIN_SHA = the later evidence-only result commit that records this verification (its SHA is reported in the final answer; a file cannot contain its own commit SHA). `release_target_final_diff.json` and the evaluator check that the target→final diff contains only `reports/capstone/cap_011/**` and the CAP-011/CAPG10 registry rows; no product/release executable changed after the target. The clean-clone target is NOT the final main commit.

## MUTATION CONTROLS
20 controls (claims ×4, candidate-deployed, default-model swap, MODEL_V2_FINAL/CAL_V2/UI_V1_2/catalog hash changes, wrong SHA, manual source file, developer venv/node_modules/build/.env/SQLite+candidate/raw data, wrong-target result, executable change in the final commit): 20/20 caught by a named check, all restored (applied to temporary copies / synthetic repositories; working tree byte-identical).

## TESTS
Development targeted: 70 passed; development regression 3057 passed, 1 skipped, 1 deselected (CAP-003 policy; isolated probe passed). Clone A tests 3038 passed/20 skipped; Clone A frontend 193 passed, 0 svelte errors, build OK; Clone A demo PASS. Clone B tests 3038/20; frontend 193, 0 errors, build OK; demo PASS. ruff clean; pip check clean (dev and both clones). CI queried NO; CI triggered NO.

## CONTROL PLANE
CAP-001..CAP-011 PASS; CAPG0..CAPG10 PASS; no CAP-012.

## GIT
Compatibility amendments `7360cee`, `af60c1e`; entry audit `c8461b1`; control commit `966893c`; release freeze/target `3ad1b07408a0c3556fbc5039f1a7a4fee824db96`; amendments after freeze: none; result commit = the commit carrying this file; release target `3ad1b07…`; tag `capstone-release-v1` → release target (annotated, created after the result commit and verified on the remote).

## DISCLOSURES
- All inherited disclosures carried: accelerated timing; logical clients; round-1 SecAgg shadow; candidate not deployed / no inference runtime; physical wearable absent; Clerk limitation; CAP-003 race; machine-specific timings; CAP-008 amendment `85fe0b3` unrelated evidence; commit `2022329` bulk-add; one-active-run not a distributed lock; npm advisories.
- Authorised release-enabling amendments before entry: CAP-010 preflight predicate (`7360cee`) and lifecycle guard 9_2 (`af60c1e`).
- Failed clone attempts: none canonical. Preparation: three local dry runs of the harness (against a local, unpushed freeze candidate, label DRY, scratch evidence not committed) found release-layer defects before the freeze, all fixed before the target: portability audit self-matching literals; a missing third data-gate skip category (`tests/test_model_v1_freeze.py` CANDIDATE_CHECKPOINT_NOT_TRACKED, an existing repository gate) added to the frozen policy; skip-line and svelte-check output parsers; preflight run with `--build` because the launcher-written build stamp is checked by a bare preflight. A dev-checkout preparation regression was run before the target.
- Clean-clone installation needs public package-registry network access (pip dev was slow on one run).
- Data-gated skips in the clones: 18 raw/processed/checkpoint inputs, 1 untracked T015 artifact, 1 inherited post-exposure skip.
- Tested OS/toolchain: macOS 27.0.1 arm64, Python 3.11.16, Node v26.5.0, npm 11.17.0, Git 2.54.0, Chrome 154.0.8037.98.
- Release-target vs final-main distinction as above; no release-layer repair was needed after the freeze.
- The dev checkout regression report was produced at the release-target code state and imported unchanged (later commits are evidence-only).

## FINAL DECISION
CAP-011 accepted: YES · CAPG10 accepted: YES · CAPSTONE_RELEASE_V1 accepted: YES. Capstone software lineage closed: YES. Scientific/runtime/FL/product reopening required: NO.
