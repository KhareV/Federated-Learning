# CAP-007 FINAL HANDOFF - Live federation orchestrator + candidate model registry (gate CAPG6)

## PHASE RESULT

CAP-007: **PASS**   CAPG6: **PASS** (125/125 criteria, frozen in `configs/capstone/cap_007_federation_protocol_v1.json` before any canonical result). Evidence: `reports/capstone/cap_007/capg6_criteria.json`. A real, authenticated, persisted, deterministic federation orchestrator now runs the frozen eight-client V2 cohort for three rounds (24 genuine local updates) through the unchanged `Coordinator` / `aggregate_weighted_deltas`, reproduces V2-FL-005 exactly, and registers exactly one engineering candidate `CAPSTONE_FL_CANDIDATE_0001` per FL_SINGLE_RUN. Nothing is served, deployed or promoted.

## ENTRY

Entry SHA `651bfa61022cf699a43c0a91cbc43a6486943bcb` (HEAD == origin/main, no intervening commits, tree clean at the start of CAP-007). CAP-001..006 PASS / CAPG0..5 PASS; CAP-007..011 NOT_STARTED. Entry commit with the prospective control plane (CAP-007 IN_PROGRESS, CAPG6 NOT_STARTED, no implementation present): `b7be753`.

## UPSTREAM PROTECTION

Every prior lock and amendment chain verified link by link at entry and at final: CAP-001 (+1), CAP-002 (+4), CAP-003 (+1), CAP-004 (+6, now +7), CAP-005 (+6), CAP-006 (+3), CAPSTONE_UI_V1, V2_FL_WEARABLE_SYSTEM_PROTOCOL_V1, FEDPROX_MU_V2, FL_INIT_V2, and the new CAP-007 lock (+2). Scientific/runtime drift: NO. V2-FL-005 evidence and FL_INIT_V2 (`6a2923ca...`) unchanged. Frontend: 203 files byte-identical (Federation pages still "NOT YET ENABLED"). The strict `scripts/cap_007_protected_audit.py final`: no modified file except the control-plane registries, the lifecycle test and one amended guard test; no removed file; every new file under an explicit CAP-007 namespace (`protected_artifact_final.json`).

## CONTRACT RECONCILIATION

Written prospectively (`federation_contract_reconciliation.json`, committed before any result). (A) CAP-006's client V1 is FL_INIT-only, so rounds 2-3 need an additive successor. (B) `federation_v1` maps every aggregation to a candidate (three candidates per run) while the V2-FL-005 lineage carries the round-1/2 aggregates forward as the next base. Resolution: additive `CAPSTONE_FEDERATION_CONTRACT_V2` (`contracts/capstone/federation_v2.json`); the exact delta is **AGGREGATING -> COMPLETED for non-final rounds**, nothing else; no vocabulary or algorithm change; `federation_v1.json` unchanged.

## PROTOCOL

`CAPSTONE_FEDERATION_PROTOCOL_V1`, freeze commit `772b178` (before every canonical result), lock `artifacts/capstone/CAPSTONE_FEDERATION_PROTOCOL_V1.lock.json`, 12 registered components, `CAPSTONE_FEDERATION_EXECUTION_BINDING_V1` frozen (one candidate per run, round states vs candidates, run-level base, round-level base digests, SecAgg shadow, replay, restart/resume, one-laptop concurrency). Two recorded amendments (audit allow-list; evaluator key) - see DISCLOSURES.

## FEDERATION SERVICE

`product/federation/service.py` (`CAPSTONE_FEDERATION_SERVICE_V1`): glue only - lineage verification, one V2 client per client per round over the CAP-006 buffers, genuine envelopes into the unchanged Coordinator, persistence, round checkpoints, the single final-round candidate and governance, events, replay, recovery. No training, aggregation or inference mathematics. Blocking work (local epoch, aggregation, SecAgg shadow) runs in worker threads; `POST start` returns in ~5 ms. Public policy: only FL_SINGLE_RUN, exactly 3 rounds; the five request fields only; ten forbidden fields (mu, learning_rate, optimizer, batch_size, model_id, checkpoint, calibration, threshold, base_model_id, candidate_id) are rejected 400.

## MULTI-ROUND CLIENT

`CAPSTONE_FL_CLIENT_ADAPTER_V2` subclasses CAP-006's V1 (unchanged; `local_train` is inherited, no training loop copied) and accepts a round base only after lineage verification: round 1 = FL_INIT_V2 digest; round N>1 = digest of the immediately preceding committed round state. MODEL_V2_FINAL and `CAPSTONE_FL_CANDIDATE_*` are refused as a base (tests + mutation controls).

## CANONICAL FEDAVG LIVE RUN

Real `CAPSTONE_PRODUCT_API_V1_2` process, explicit DEMO auth, temporary SQLite + artifact roots, HTTP + two WebSocket subscribers: COMPLETED, 3 rounds x 8 clients, **24 local training calls, 24 accepted, 0 rejected**, one candidate. 203 events (federation.status 6, round.status 18, client.status 96, client.training_progress 48 [only 0.0 and 1.0], client.update_ready 24, aggregation.status 3, secagg.status 3 [PLAIN: NOT_USED each round], candidate.created/validation x2/governance, federation.completed). Round paths: rounds 1-2 COLLECTING..AGGREGATING..COMPLETED; round 3 ..CANDIDATE_CREATED, VALIDATING, ACCEPTED_TO_SANDBOX, COMPLETED. Both subscribers and a late reconnect received the identical stream, closed 1000.

## V2-FL-005 FULL PARITY

State lineage reproduced exactly: FL_INIT `6a2923ca...` -> round 1 `40cee065...` -> round 2 `6237c0b1...` -> round 3 `3f0b7762...` (the candidate digest). All 24 updates equal the frozen evidence on client set, `examples_seen`, **shuffle seeds** and **update SHA-256**, plus per-round base/committed digests (`v2_fl_005_full_parity.json`; compared fields read from the frozen file, not copied; diagnostics-only fields intentionally not compared). Holds in both canonical runs, the restart run and (digests) the REPLAY source.

## CANDIDATE

Exactly one: `CAPSTONE_FL_CANDIDATE_0001` in an empty registry, parent `FL_INIT_V2`, round 3, FEDAVG, 8 clients, `claim_boundary CAPSTONE_ENGINEERING_SANDBOX_CANDIDATE_NOT_SCIENTIFIC_RELEASE`, `production_deployed false`. Intermediate aggregates are round global states, not registry candidates. Artifact `data/capstone/fl_candidates/<id>/{state.bin,metadata.json}` (240,828-byte state; serialise -> verify -> temp dir -> atomic rename -> then the SQL row); weights never in SQL; never committed.

## MODEL REGISTRY

`CAPSTONE_MODEL_REGISTRY_V1`: released namespace (MODEL_V1 ROLLBACK_REFERENCE, MODEL_V2_FINAL RELEASED_DEFAULT) separate from the candidate namespace; atomic ID allocation (in-process lock + atomic directory rename; a pre-existing directory forces the next number); tamper detection on load. `GET /models`, `GET /models/{id}` read-only (GLOBAL_READ); no promote/deploy/set-default route. Governance `CAPSTONE_MODEL_GOVERNANCE_RUNTIME_V1`: the five frozen structural checks only (STATE_FINITE, STATE_SPEC_MATCHES_BASE, UPDATE_DIGESTS_RECONCILE, ROUND_ACCEPTED_UPDATE_COUNT_COMPLETE, BASE_STATE_LINEAGE_VERIFIED); CREATED -> VALIDATION_PENDING -> VALIDATING -> ACCEPTED_TO_SANDBOX|REJECTED; all pass -> validation PASSED, sandbox IN_SANDBOX; `scientific_promotion=false`, `production_deployed=false` always. No inference on candidates, no `CAPSTONE_FL_SANDBOX_RUNTIME`.

## FEDPROX

Full temporary 3-round product run: FEDPROX, frozen mu 0.1 (never request-supplied), 24 calls, 24 accepted, one finite candidate, final digest `060b5d6f...` != the FedAvg digest; no metrics, no tuning, no deployment.

## SECAGG

`SECAGG_SHADOW` run: round-1 shadow VERIFIED (`SHADOW_RUNNING` -> `SHADOW_VERIFIED`); 8 clients, max_weight 256, 8 plain clear updates, 0 protected clear updates, protected aggregate visible, max abs diff 6.3e-06 / rel-L2 1.35e-05 against frozen tolerances 1e-4 (unchanged, never widened). Authoritative aggregation stayed PLAIN (final digest equals the plain run's). Claim scope `PROTECTED_AGGREGATION_INTERFACE_ONLY`; no DP/anonymity claim. A failed shadow fails the run loudly with no candidate (test).

## INVALID UPDATES

Separate harness scenario (no run/round/candidate/DB row created): one genuine client-0 envelope and four mutated submissions through the existing Coordinator rejection logic: DUPLICATE_UPDATE, STALE_ROUND, BASE_STATE_MISMATCH, UNKNOWN_CLIENT rejected as expected; the valid one accepted; round not complete. Normal runs inject nothing.

## PERSISTENCE

`capstone_persistence/federation_store.py` (`CAPSTONE_FEDERATION_STORE_V1`): own connection to the same SQLite file (foreign_keys ON, WAL); only the five policy tables (1 run, 3 rounds, 24 client statuses, 1 candidate, 1 decision after a canonical run); integrity_check `ok`, foreign_key_check empty; no schema change, no per-event table, no data/labels/truth/tensors/candidate bytes in SQL. Run events live in a JSONL file and round checkpoints in the federation artifact store (`CAPSTONE_FEDERATION_ARTIFACT_STORE_V1`), both outside git.

## RESTART / RESUME

A real server process was killed (`os._exit(86)` through the explicit TEST-ONLY fault hook) right after the round-2 checkpoint: run RUNNING, rounds 1-2 COMPLETED, 130 events, no candidate. A FRESH process on the same database/artifacts resumed round 3 at startup and produced the identical final digest and the identical 203-event stream (24 unique round/client updates, one candidate, one decision, no duplicates). A RUNNING run without a valid checkpoint, or with corrupt/mismatched checkpoint metadata, is marked FAILED, never fabricated; orphan candidate artifacts of the run are removed before resume (tests). Arbitrary mid-round resume is not supported.

## REPLAY

A REPLAY run (visible `run_type=REPLAY`) replays the persisted events of the most recent COMPLETED LIVE_RUN of the same owner/config (source recorded in artifact metadata, no new request field): 203 events in 0.04 s, semantic parity with the source (excluding run id, event ids, times and the REPLAY run_type), zero training/submit/aggregate/SecAgg/candidate/governance (no new candidate or decision; tripwire test on the training functions). No source -> 409 `NO_COMPLETED_SOURCE_RUN_FOR_REPLAY`.

## PRODUCT API

`api/product_app_v1_2.py` (`CAPSTONE_PRODUCT_API_V1_2`) composes the untouched `create_product_app_v1_1` and adds exactly the ten CAP-007 routes; only `GET /system` is re-published (`federation_runtime ENABLED_ENGINEERING`, hardware SIMULATED_ONLY, model MODEL_V2_FINAL, SOFTWARE_SYSTEM_V2, no candidate mentioned). Ownership: runs OWN (cross-user -> 403/4403, unknown -> 404/4404, unauthenticated 401/4401); overview, clients, models authenticated GLOBAL_READ. At most one active LIVE run globally: a second start (same user, and another process on the same database) -> 409 `FEDERATION_RUN_ALREADY_ACTIVE`; released again after completion. Launcher `scripts/run_capstone_product_v1_2.py`.

## FEDERATION WEBSOCKET

`WS /product/v1/federation/runs/{id}/live`: separate `CAPSTONE_FEDERATION_EVENT_JOURNAL_V1`, one contiguous sequence per run, 12 federation kinds only (`PRODUCT_LIVE_EVENT_V1`), deterministic ids `<run_id>-FEV000000`, replay from 0 then tail, zero/multiple subscribers and reconnect, server-to-client only (client frames -> 1008). Canonical DEMO auth authenticates every connection, so 4401 is evidenced by the targeted test with the test resolver; 4403/4404 also in the two-process canonical ownership run.

## RELEASED MONITORING ISOLATION

MODEL_V2_FINAL / SOFTWARE_SYSTEM_V2 / DEFAULT_RUNTIME_BINDING_V2 unchanged; no `CAPSTONE_FL_CANDIDATE` string in the default runtime, CAP-003 client, monitoring/session/persistence/device code, the frontend or the inference service sources; no monitoring or user data used by FL; no held-out data loaded; no inference or metric in the new code.

## LOCALITY / CLAIMS

Eight logically isolated local client datasets on one demonstration machine; the server-side objects are model updates and metadata, not raw examples (every submitted envelope passes `scan_forbidden`; the central database has no data/label/truth/tensor columns). Not claimed: hospital deployment, separate machines, VM/enclave/network isolation, privacy guarantees, efficacy, clinical meaning, scientific promotion.

## REPRODUCIBILITY

Two canonical runs in fresh server processes (different pids) have identical semantic digests (`8ffa1865...`) and identical projected event streams (`9063772a...`); projection drops only run id, run-derived event id and emission time. The restart run equals the canonical stream; the REPLAY equals its source. Local epochs run in worker threads and are still bit-identical to the V2-FL-005 reference.

## OUT OF SCOPE

Not done (and not started): CAP-008 / any UX, frontend change, serving a candidate for inference, `CAPSTONE_FL_SANDBOX_RUNTIME`, deploying/promoting a candidate or changing DEFAULT_RUNTIME_BINDING_V2, MODEL_V2_FINAL changes, held-out scientific evaluation, synthetic accuracy/AUPRC/F1, FL_NEW_LOCAL_BATCH, multi-run continual sandbox / candidate history, training on website monitoring data, personalised models, physical hardware.

## TESTS

CAP-007 targeted: 107 passed (10 files). CAP-001..006 capstone tests: 436 passed. Full local regression: 2942 passed, 1 skipped (the inherited CAP-003 flaky test passed in this run). Frontend: `npm test` 145 passed / 2 skipped, `npm run check` 0 errors (112 pre-existing warnings), `npm run build` OK. `ruff check .` clean; `pip check` clean. Twelve mutation controls (round 2 from FL_INIT, three candidates, MODEL_V2_FINAL as base, omitted update, label in envelope, production_deployed=true, candidate in the default runtime, accept despite failed check, SecAgg tolerance widened, REPLAY trains, cross-user access, second simultaneous LIVE run) were each caught by a real test failure (first failing test recorded) and every file restored byte-identically. CI neither queried nor triggered.

## CONTROL PLANE

CAP-007 -> PASS and CAPG6 -> PASS at the result commit (`manifests/capstone/{task,gate}_registry_v1.csv`, `tests/test_capstone_lifecycle.py` updated; lifecycle test re-run after the flip). CAP-006 and earlier unchanged PASS; CAP-008..011 NOT_STARTED. Components registered in `manifests/capstone/component_registry_cap_007_v1.csv`.

## GIT

Entry `b7be753` (on `651bfa6`), method freeze `772b178`, result commit = the commit containing this file. No state file, checkpoint, tensor, SQLite database, event journal or candidate artifact is committed (`data/capstone/` stays untracked via the existing local-only exclude).

## DISCLOSURES

Carried forward: CAP-001 gate-row wording discrepancy; CAP-002 code drafted before entry; CAP-003 LIVE_SPEED bounded-settle limitation, manual-stop-mid-outage limitation, context projection, pre-freeze smoke; CAP-004 additive Clerk pin file, SQLite store outside `product/`, six-amendment chain, inherited CAP-003 flaky test (`test_monitoring_completes_with_zero_subscribers`, evidence `reports/capstone/cap_004/preexisting_cap003_flake.json`), local-only SQLite git exclude, Clerk local-fixture-only; CAP-005 Clerk WebSocket cookie path unverified, no live Clerk-account E2E, accessibility audit not formal WCAG, ACCELERATED UI evidence; CAP-006 logical one-laptop locality, synthetic engineering labels, FedProx smoke classification.

New in CAP-007:
- **Chronology:** the implementation and its targeted tests were written before the freeze commit; before the freeze the harness and evidence builder were dry-run into a scratch directory outside the repository, and one canonical live run was briefly written to `reports/capstone/cap_007` and deleted. None of that is committed; all recorded results come after `772b178`.
- **Amendments:** `CAPSTONE_AUTH_PERSISTENCE_PROTOCOL_V1` amendment 7 (the frozen CAP-004 FL-token scan test now skips only `capstone_persistence/federation_store.py`, which must name the frozen `secagg_mode` column; found by the full regression); `CAPSTONE_FEDERATION_PROTOCOL_V1` amendment 1 (audit allow-list for that test) and amendment 2 (evaluator read the V1->V2 delta from the wrong key; found by the first criteria run). No criterion text changed.
- **Entry-audit correction:** the entry commit's `entry_audit.json` recorded `working_tree_clean=false` because it was computed after the entry evidence files existed; the file now records `true` with a note (the tree was clean at the start of CAP-007).
- **Concurrency guard:** the one-active-run rule is an in-process flag plus a database RUNNING check; two server processes starting a run in the exact same instant could in principle both pass it (not claimed as a distributed lock).
- **Replay persistence:** a REPLAY run mirrors round and client-status rows (candidate id null, `candidate_ids` empty) while its events reference the source's candidate id verbatim; its `federation.status` events carry `run_type=REPLAY`.
- **Event semantics:** `aggregation.status.aggregation_mode` is always PLAIN (authoritative); PLAIN runs emit `secagg.status NOT_USED` per round, shadow runs only the round-1 pair; `candidate.validation.checks` lists the ids of the checks that passed.
- **Restart evidence** uses a hard process exit through a TEST-ONLY hook, not a real power loss; the canonical runs start no inference service (the released monitoring path is unchanged and was not exercised by CAP-007's canonical runs; its tests are part of the regression).
- **Tests:** the Starlette TestClient raises a spurious cancellation if a test closes an idle WebSocket client-side; the WebSocket tests therefore only close sockets that have events pending or are closed by the server.
- The first call of `GET /federation/clients` (or the first run) in a process builds the eight client datasets (~14 s).

## FINAL DECISION

CAP-007 **PASS**, CAPG6 **PASS**. DO NOT START CAP-008. DO NOT MODIFY FRONTEND. DO NOT SERVE A CANDIDATE FOR INFERENCE. DO NOT IMPLEMENT CAPSTONE_FL_SANDBOX_RUNTIME. DO NOT DEPLOY A CANDIDATE. DO NOT MODIFY MODEL_V2_FINAL. DO NOT CHANGE DEFAULT_RUNTIME_BINDING_V2. DO NOT RUN HELD-OUT SCIENTIFIC EVALUATION. DO NOT COMPUTE SYNTHETIC ACCURACY/AUPRC/F1. DO NOT IMPLEMENT FL_NEW_LOCAL_BATCH YET. DO NOT IMPLEMENT MULTIRUN CONTINUAL SANDBOX YET. DO NOT TRAIN ON WEBSITE USER MONITORING DATA. DO NOT IMPLEMENT PERSONALIZED MODELS. DO NOT IMPLEMENT PHYSICAL HARDWARE. RETURN CAP-007 HANDOFF ONLY.
