# CAP-008 FINAL HANDOFF - Federation dashboard + model governance UX (gate CAPG7)

## PHASE RESULT

CAP-008: **PASS**   CAPG7: **PASS** (114/114 criteria, frozen in `configs/capstone/cap_008_federation_ux_protocol_v1.json` at `65fdf6f` before any canonical result). Evidence: `reports/capstone/cap_008/capg7_criteria.json`. The existing SvelteKit frontend (successor lock `CAPSTONE_UI_V1_1`) now drives the real CAP-007 backend end to end in a real headless Chrome, offline, in DEMO mode. No backend, FL, scientific or monitoring file changed.

## ENTRY

Entry SHA `711a4a0a1233765d6f1200fc2b6d8f3aa62d4743`; origin/main identical; tree clean at the start. CAP-001..007 PASS / CAPG0..6 PASS; CAP-008..011 NOT_STARTED. All prior locks and amendment chains verified at entry and at final (CAP-001 +1, CAP-002 +4, CAP-003 +1, CAP-004 +7, CAP-005 +7, CAP-006 +3, CAP-007 +3, CAPSTONE_UI_V1, FL_INIT_V2, FEDPROX_MU_V2, V2-FL system). Entry audit modified after creation: **NO** (no correction file was needed). Entry/control commit `4d38204`.

## UPSTREAM PROTECTION

Scientific/runtime drift NO; CAP-006 drift NO; CAP-007 drift NO; backend drift NO (`api/`, `product/`, `capstone_persistence/`, `contracts/`, `federated/`, `privacy/`, `simulation/`, `src/` byte-identical to entry); monitoring drift NO (monitoring client/store/events/socket/page byte-identical to entry; the CAP-005 monitoring frontend tests pass unchanged). `protected_artifact_final.json`: no drift, every new non-frontend file under an explicit CAP-008 namespace, every frontend change bound by the successor.

## UI SUCCESSOR

Predecessor `CAPSTONE_UI_V1` (lock file byte-identical to entry); successor `CAPSTONE_UI_V1_1` (`artifacts/capstone/CAPSTONE_UI_V1_1.lock.json`) binds all 223 frontend files, 34 changed/added versus the predecessor. `scripts/verify_capstone_ui_v1_1.py` fails on any unbound or tampered frontend file; the historical `verify_capstone_ui_v1.py` accepts a changed file ONLY if the successor binds the current bytes. Unaccounted drift: **none**. No new npm dependency (package manifests and lock files byte-identical). Historical guards were reconciled through `CAPSTONE_FRONTEND_PRODUCT_PROTOCOL_V1` amendment 7 (commit `aa33a6b`), not disabled.

## PROTOCOL

`CAPSTONE_FEDERATION_UX_PROTOCOL_V1`, freeze commit `65fdf6f`, lock `artifacts/capstone/CAPSTONE_FEDERATION_UX_PROTOCOL_V1.lock.json`, 7 components, 114 criteria (the 120 prompt items are covered, several consolidated into one criterion). Post-freeze amendments: CAPSTONE_FEDERATION_PROTOCOL_V1 amendment 3 (CAP-007 frontend candidate-scan skips the CAP-008 UX paths) and CAPSTONE_FEDERATION_UX_PROTOCOL_V1 amendment 1 (audit allow-list) - see DISCLOSURES.

## FEDERATION OVERVIEW

`/app/federation` is real: runtime ENABLED_ENGINEERING (read from `/system`; an older backend shows "FEDERATION BACKEND NOT ENABLED" and floods no routes), 8 logical clients (cohort WEARABLE_SIM_FL_COHORT_V1), active-run flag, backend candidate count, released monitoring model MODEL_V2_FINAL, run list, and a two-lane architecture (Lane A released monitoring, Lane B federated development; no arrow from a candidate to MODEL_V2_FINAL or monitoring). Cold start: overview loads first; clients load independently with "PREPARING 8 SYNTHETIC LOCAL CLIENT DATASETS" and are requested exactly once (observed in the browser run).

## RUN CONFIGURATION

User-controlled: run mode LIVE_RUN | REPLAY; algorithm FEDAVG | FEDPROX; protection PLAIN | SECAGG_SHADOW (exactly three selects, zero inputs, verified in the browser DOM). Read-only facts: FL_SINGLE_RUN, 8 clients, 3 rounds, base FL_INIT_V2. Request body exactly `run_type, algorithm, secagg_mode, planned_rounds=3, scenario_id=FL_SINGLE_RUN`. Forbidden controls present: **NO** (model, base, checkpoint, candidate, mu, learning rate, batch size, optimizer, epochs, client/round count).

## CLIENT UX

SIM_FL_SITE_00..07 with edge node, global round, local example count, eligibility, state, update digest (short + copy). Persistent "SYNTHETIC RESEARCH PARTITIONS - NOT HOSPITALS OR INSTITUTIONS" and "all eight logical clients currently execute on one demonstration machine". Raw data shown: NO. Labels/participants shown: NO. Hospital claim: NO.

## ROUNDS UX

Persisted round cards from the backend (state, base digest, algorithm, accepted n/8, candidate). Canonical run: round 1 COMPLETED 8/8 candidate NONE (base 6a2923ca…); round 2 COMPLETED 8/8 NONE; round 3 COMPLETED 8/8 `CAPSTONE_FL_CANDIDATE_0001`. Lineage FL_INIT_V2 -> round 1 -> round 2 -> final -> candidate, never connected to MODEL_V2_FINAL. Run selection via `?run=<id>`; nothing in localStorage.

## LIVE UX

Same-origin `ws://…/product/v1/federation/runs/{id}/live` (no token in the URL; one socket per run view). Strict parser for exactly the 12 federation kinds (every monitoring kind, unknown kinds, malformed payloads and foreign run ids rejected); strict per-run sequence (gap/duplicate/foreign/malformed => FEDERATION STREAM ERROR, state frozen); reconnect = reset then rebuild from sequence 0. Training progress is only the real 0/1 milestones (nothing interpolated; no random/timers in source). Shows aggregation PLAIN per round, SecAgg status, candidate/validation/governance, engineering errors; the dashboard is an observer.

## PRIVACY UX

Round-1 protected-aggregation shadow only; authoritative aggregate PLAIN (including SECAGG_SHADOW runs); scope PROTECTED_AGGREGATION_INTERFACE_ONLY; round shadowed: 1; status shown only from real events (SHADOW_RUNNING -> SHADOW_VERIFIED observed live; PLAIN runs show "NOT USED"). Differential privacy claimed: NO ("No differential privacy." stated). Anonymity claimed: NO ("No anonymity guarantee." stated). One-laptop/logical-locality limitation stated.

## MODEL REGISTRY UX

Two separated namespaces: RELEASED SCIENTIFIC (MODEL_V2_FINAL RELEASED_DEFAULT, MODEL_V1 ROLLBACK_REFERENCE) and ENGINEERING FEDERATED CANDIDATES. Candidate card: id, parent FL_INIT_V2, run, round, algorithm, client count, digest, validation PASSED, governance ACCEPTED_TO_SANDBOX, sandbox IN_SANDBOX, `production_deployed = FALSE`, claim boundary; wording "ACCEPTED TO ENGINEERING SANDBOX REGISTRY / STRUCTURAL CHECKS PASSED / NOT A SCIENTIFIC RELEASE / NOT DEPLOYED / NO CANDIDATE INFERENCE RUNTIME ENABLED". The five frozen checks are shown as structural; per-check results only when an event reports them. Deploy/promote/default/inference controls: **none** (DOM and source audited).

## CANONICAL LIVE BROWSER RUN

Production CAPSTONE_UI_V1_1 build (199 build files) via `vite preview`, headless Chrome with every non-loopback host blocked, real `CAPSTONE_PRODUCT_API_V1_2` process, DEMO auth (Clerk not initialised), fresh SQLite + federation + candidate roots, real training. LIVE_RUN FEDAVG + SECAGG_SHADOW, FL_SINGLE_RUN: 8 clients (all 8 observed SUBMITTED at once), 3 rounds, **24 update-ready events, 24 SUBMITTED completions**, aggregation PLAIN in every round, SHADOW_RUNNING then SHADOW_VERIFIED (round 1 only), one candidate `CAPSTONE_FL_CANDIDATE_0001` (parent FL_INIT_V2, digest `3f0b7762…` = V2-FL-005 round-3 state), validation PASSED, ACCEPTED_TO_SANDBOX, IN_SANDBOX, production_deployed false, completed (202 events). After browser reload the run, rounds and candidate reload from the backend; after a backend process restart the registry and runs persist. The real-backend frontend integration test (actual client + parser + live model, no fixtures) passed with the same invariants.

## CANONICAL REPLAY

A REPLAY run (FEDAVG, SECAGG_SHADOW) was created through the UI against the completed LIVE_RUN as source (source exists: YES). UI showed "REPLAY · NO TRAINING IS EXECUTING"; no "training in progress" copy; client cards say "REPLAYED EVENT: …"; candidate events were labelled "HISTORICAL EVENT REPLAY - NO NEW CANDIDATE CREATED". Backend candidate count before 1, after 1 (overview 1 -> 1); the replay run has no candidate ids. Semantic stream: the UI received 202 events, the same count as its source run; payload-level REPLAY-vs-source parity is the CAP-007 backend evidence (not re-proved here), and the UI-derived state counted no new candidate.

## REFRESH / RECONNECT

A second genuine LIVE_RUN (FEDAVG PLAIN) was refreshed in the browser at round 2 (9 update-ready events seen): auth restored, run and `?run=` recovered, a new WebSocket opened, state reset and rebuilt from sequence 0, the run **continued** and completed with exactly 24 update-ready events (max observed 24, no double counting, no sequence error). By design this run created `CAPSTONE_FL_CANDIDATE_0002` (backend registry now 2 candidates).

## RELEASED MONITORING ISOLATION

MODEL_V2_FINAL / SOFTWARE_SYSTEM_V2 still the released default (reported by `/system` and `/models`). Candidate referenced by monitoring: NO (static + Python test over monitoring client/store/page and the released runtime). Monitoring frontend regression: all pre-existing product frontend tests pass unchanged and the monitoring files are byte-identical to entry. Candidate inference: NO.

## OFFLINE / AUTH

DEMO works fully offline: 2,065 browser requests, one origin (`http://127.0.0.1:<port>`), external origins **none**, no console errors. Clerk initialised in DEMO: NO. The Clerk-authenticated WebSocket path remains unverified with a real Clerk account.

## RESPONSIVE / ACCESSIBILITY

1440, 1024, 768 and 390 px: all six federation/model pages fit the viewport with no horizontal overflow (a first dry run found overflow at 390 px; fixed before the freeze). Checks: one h1, main landmark, skip link, aria-live/status regions, labelled selects, named buttons, labelled client grid, state shown as text (not colour only), visible focus rule + keyboard-focusable controls, 0 running animations. Formal WCAG certification claimed: **NO**.

## OUT OF SCOPE

Backend modified NO; FL mathematics modified NO; `CAPSTONE_FL_SANDBOX_RUNTIME` NO; candidate inference NO; candidate deployment NO; FL_NEW_LOCAL_BATCH NO; FL_MULTIRUN NO; CAP-009 history/science UX NO (research pages remain placeholders); physical hardware NO; CAP-009 started NO.

## TESTS

Frontend: 187 unit/component/static tests passed (3 skipped real-backend/e2e files that run only under the E2E harness); real-backend integration passed; canonical browser LIVE E2E, REPLAY E2E and refresh E2E passed; monitoring regression passed; 14/14 mutation controls caught by a failing test and restored byte-identically; `npm run check` 0 errors (112 pre-existing warnings); `npm run build` OK. Python: CAP-008 guards 9 passed; prior capstone tests 543 passed; full regression 2951 passed, 1 skipped (the inherited flaky test passed). ruff clean; pip check clean. CI queried: NO; CI triggered: NO.

## CONTROL PLANE

CAP-001..007 PASS / CAPG0..6 PASS (unchanged); CAP-008 PASS / CAPG7 PASS at the result commit (registries and lifecycle test updated; lifecycle test re-run); CAP-009..011 NOT_STARTED. Components registered in `manifests/capstone/component_registry_cap_008_v1.csv`: CAPSTONE_FEDERATION_UX_PROTOCOL_V1, CAPSTONE_UI_V1_1, CAPSTONE_FEDERATION_FRONTEND_V1, CAPSTONE_FEDERATION_PRODUCT_CLIENT_V1, CAPSTONE_FEDERATION_LIVE_MODEL_V1, CAPSTONE_FEDERATION_STORE_UI_V1, CAPSTONE_MODEL_GOVERNANCE_UI_V1.

## GIT

Entry/control `4d38204` (on `711a4a0`); UI successor + guard amendment `aa33a6b`; method freeze `65fdf6f`; post-freeze amendment commits `85fe0b3` and `5b51a2f`; result commit = the commit containing this file; final HEAD = origin/main after push; tree clean.

## DISCLOSURES

Carried forward: CAP-001 gate-row wording; CAP-002 code-drafted-before-entry; CAP-003 LIVE_SPEED bounded-settle, manual-stop-mid-outage, context projection, pre-freeze smoke; CAP-004 additive Clerk pin file, SQLite store outside `product/`, amendment chain (now seven), inherited CAP-003 flaky test (`test_monitoring_completes_with_zero_subscribers`), local-only SQLite git exclude, Clerk local-fixture-only; CAP-005 Clerk WebSocket cookie path unverified, no live Clerk-account E2E, accessibility audit not formal WCAG, ACCELERATED UI evidence; CAP-006 logical one-laptop locality, synthetic engineering labels, FedProx smoke classification; CAP-007 one-active-run is a process flag plus a database RUNNING check, not an atomic distributed lock (the UI says "one live federation run at a time in this one-laptop demonstration" and never claims a lock); eight logical clients on one laptop; SecAgg+ is a round-1 shadow with PROTECTED_AGGREGATION_INTERFACE_ONLY scope (authoritative aggregation PLAIN); the candidate sandbox has no inference runtime.

New in CAP-008:
- **Chronology:** the frontend, its tests and the E2E harness were written before the freeze commit, and the harness was dry-run end to end into a scratch directory outside the repository twice (the first run exposed 390 px overflow and a redundant WebSocket on first load; both fixed before the freeze). None of that output is committed.
- **Amendments:** `CAPSTONE_FRONTEND_PRODUCT_PROTOCOL_V1` amendment 7 (successor-aware historical frontend verifier/tests + the `api.ts` extension); `CAPSTONE_FEDERATION_PROTOCOL_V1` amendment 3 (the CAP-007 frontend candidate-scan skips the CAP-008 UX paths; found by the first full regression); `CAPSTONE_FEDERATION_UX_PROTOCOL_V1` amendment 1 (audit allow-list; found by the first final audit). No criterion text changed.
- **Commit hygiene (disclosed mistake):** amendment 3's commit `85fe0b3` also swept in the canonical E2E evidence, mutation log and frontend logs that had just been produced (bulk `git add`), so it is not a pure amendment commit; the amendment itself is separable (the amendment JSON plus one test file) and the interim `pytest_full` log in that commit was superseded by the re-run recorded here. The evidence files were produced after the freeze commit as required.
- **Second candidate:** the refresh-during-run scenario deliberately runs a second genuine LIVE_RUN, so the temporary backend ends with two candidates (0001 from the canonical run, 0002 from the refreshed run); the "exactly one new candidate in an empty database" invariant is evidenced for the canonical run, and REPLAY created none.
- **Event count:** the UI counts 202 events for a SECAGG_SHADOW run and 203 for a PLAIN run (the backend emits two shadow events instead of three NOT_USED events).
- **Criteria count:** 114 criteria; some of the 120 prompt items are consolidated into one criterion.
- Client states during a REPLAY are labelled "REPLAYED EVENT: …"; the UI does not slow replay for animation.

## FINAL DECISION

CAP-008 **accepted** (PASS). CAPG7 **accepted** (PASS). CAP-009 allowed: **only on a new explicit instruction** (not started here). No scientific, runtime or backend reopening is required.

DO NOT START CAP-009. DO NOT MODIFY CAP-007 BACKEND. DO NOT MODIFY FL TRAINING OR AGGREGATION. DO NOT IMPLEMENT CAPSTONE_FL_SANDBOX_RUNTIME. DO NOT RUN CANDIDATE INFERENCE. DO NOT DEPLOY A CANDIDATE. DO NOT ADD A DEPLOY/PROMOTE CONTROL. DO NOT CHANGE MODEL_V2_FINAL. DO NOT CHANGE DEFAULT_RUNTIME_BINDING_V2. DO NOT RUN HELD-OUT SCIENTIFIC EVALUATION. DO NOT COMPUTE CANDIDATE ACCURACY/AUPRC/AUROC/F1. DO NOT IMPLEMENT FL_NEW_LOCAL_BATCH. DO NOT IMPLEMENT FL_MULTIRUN_CANDIDATE_HISTORY. DO NOT TRAIN ON WEBSITE MONITORING SESSIONS. DO NOT IMPLEMENT PERSONALISED MODELS. DO NOT IMPLEMENT PHYSICAL HARDWARE. RETURN CAP-008 HANDOFF ONLY.
