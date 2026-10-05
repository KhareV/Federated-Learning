# CAP-004 FINAL HANDOFF - Authentication + SQLite persistence + public session lifecycle (gate CAPG3)

## PHASE RESULT
CAP-004 = PASS, CAPG3 = PASS (97/97 criteria: the 80 prompt-mandated + 17 implementation-specific, all frozen before evaluation).
Evidence: `reports/capstone/cap_004/capg3_criteria.json`. CAP-005 remains NOT_STARTED.

## ENTRY
Entry HEAD == origin/main == `56fc19f69566fd9ead6b509292449d5cd7540adb` (CAP-003 result). Entry audit commit `c1b9b1a`
(CAP-004 IN_PROGRESS, CAPG3 NOT_STARTED recorded prospectively). Working tree clean at entry.

## UPSTREAM PROTECTION
CAP-001 lock, CAP-002 lock (3 amendments) and CAP-003 lock (1 amendment) all verify; zero protected-artifact drift over 3302
baseline files (58 named components); zero frontend drift (162 files). Tracked files modified since entry: only
`manifests/capstone/{task,gate}_registry_v1.csv`, `tests/test_capstone_lifecycle.py` and `.env.example` (names only, purely additive).
`pyproject.toml` and `requirements-dev.lock` are byte-identical to entry. Every added file is in an additive namespace.

## CONTRACT SUCCESSORS
`CAPSTONE_STORAGE_POLICY_V2` (`contracts/capstone/storage_policy_v2.json`): adds `devices.scenario_id`, `PRAGMA user_version`
schema versioning, lifecycle clock, restart semantics, immutability, preview policy; records the V1 sha256.
`PRODUCT_API_CONTRACT_V2` (`product_api_v2.json`): system `auth_provider`, `demo_mode`, `persistence_mode=SQLITE`; `/me` + session routes.
Both V1 contracts are untouched (protected files).

## PROTOCOL
`CAPSTONE_AUTH_PERSISTENCE_PROTOCOL_V1` frozen at `1fb3023` BEFORE any canonical result. Six pre-evaluation amendments
(`artifacts/capstone/CAPSTONE_AUTH_PERSISTENCE_PROTOCOL_V1.amendment_1..6.json`, sha chains verified by the lifecycle test), none changing criteria text:
1 mutation control FL_TABLE_RECEIVES_TRUTH_LABELS rebuilt (the frozen text was a SyntaxError, "caught" only by a collection error);
2 Clerk pins moved to `requirements-capstone-auth.lock` and the SQLite store moved to `capstone_persistence/` (both user-approved, see DISCLOSURES);
3 evaluator accepts exactly one named, evidenced pre-existing CAP-003 intermittent test failure (not needed in the final run);
4 audit allow-list includes `.env.example`; 5 `.env.example` made purely additive (restored 3 deleted MONGODB_* names);
6 `@no_hardware_code` scans implementation paths with word boundaries (false positives on its own text and `import serialization`).

## AUTH
`NHM_PRODUCT_AUTH_MODE` is CLERK|DEMO with no default; unset/invalid refuses to start (exit 2). DEMO needs the exact ack
`I_UNDERSTAND_THIS_IS_NOT_CLERK`, ids prefixed `demo:`, `demo_mode=true`. CLERK uses the official `clerk-backend-api==7.0.0`
(`authenticate_request_async`, `accepts_token=["session_token"]`, explicit authorized parties, never `*`); no custom JWT/crypto code,
no decode-and-trust, no fallback to Demo. Verified in tests with real RS256 verification through the official SDK using a local
keypair (unsigned, tampered, wrong-key, expired, wrong-azp and machine/API tokens rejected). No real Clerk account, secret or network was used.
No credential is stored or logged (DB scan and `.env.example` names-only test).

## DATABASE
stdlib `sqlite3`, `data/capstone/product.sqlite3` (override `NHM_PRODUCT_DB_PATH`), `foreign_keys=ON`, WAL, `user_version=1`,
all 15 policy tables, `integrity_check=ok`, `foreign_key_check` empty after every canonical stage. No raw 360 Hz table; canonical row
total is 197 rows for a ~173k-source-sample session (preview: 3928 points x decimation 44). The six FL/candidate/governance/summary tables stay empty. The .sqlite3 file is not committed.

## USER/DEVICE PERSISTENCE
Users upserted on authentication; devices persisted with `scenario_id` and owner (immutable by trigger); 10 connection-history rows
in the canonical run; reconstructed devices come back DETACHED and must be scanned/connected again; device ids do not collide after restart.

## SESSION SERVICE
`GET /me`, `POST/GET /sessions`, `GET /sessions/{id}`; all 9 CAP-003 routes preserved (route parity exact; no CAP-007/009 route). start/stop delegate
to the unchanged CAP-003 `MonitoringService`. Ownership enforced on REST and WebSocket (403 / close 4403; unknown 404). Runtime identity
(MODEL_V2_FINAL, CAL_V2, ...) fixed at creation and immutable in SQL. Lifecycle timestamps use a UTC-microsecond clock separate from source time.
A storage failure fails the session loudly.

## EVENT PERSISTENCE
device.status -> device_connections; session.status -> sessions.state/started/ended; inference.result -> 86 rows; monitoring.state -> 3 rows;
quality.status -> change-only (8 rows for 93 windows); context.snapshot -> 86 normalized rows; waveform.chunk -> folded into one bounded preview.
The persistence bridge observes the unchanged stream (`PersistingJournal` + `ObservingInferenceClient`); `event_adapter.py` is untouched.

## CONTEXT DUAL REPRESENTATION
Raw typed response context is stored in `inference_events.context_json`; the CAP-003 normalized projection in `context_snapshots`.
8 context-withheld windows (`context_available=false` with PPG-derived raw values) are auditable: raw keeps the values, product snapshot has them null.

## WAVEFORM PREVIEW
One ECG preview per session: 3928 points (<= 4000), decimation factor 44, 122 null points where the outage left a gap (never 0), JSON_ZLIB_V1, 6579 bytes.
Not read by the scientific runtime; no raw waveform is persisted.

## RESTART/CRASH RECOVERY
Two-process restart on the same DB: the COMPLETED session, device, user and runtime identity survive unchanged; a late start returns 409; the past-process
session socket closes cleanly (1000) without events. Crash run: a real product process was `kill -9`'d mid-session; the DB was unchanged while it was down;
on restart the stale MONITORING session became FAILED (never resumed), devices were DETACHED, no fake post-crash inference or context rows.

## PRODUCT API SUCCESSOR
`api/product_app_v1_1.py` (+ `product/sessions`, `product/auth`, `product/persistence`, `capstone_persistence/`) reuses the frozen CAP-003 services; `api/product_app.py` untouched.
CORS uses an explicit allow-list (`NHM_PRODUCT_ALLOWED_ORIGINS`), never `*` with credentials. Launcher: `scripts/run_capstone_product.py`.

## CANONICAL PERSISTENT E2E
Separate product process in explicit DEMO mode, temporary real SQLite, fresh real `SOFTWARE_SYSTEM_V2` process (`scripts.run_nhm_default`), MIXED scenario, 2 runs.
93 windows, 86 VALID / 7 UNUSABLE, 86 inference results / 7 withheld (HTTP 200/422 equivalence; MODEL_V2_FINAL only, CAL_V2 only), 3157 events, contiguous sequence,
terminal COMPLETED. Under `PROJECTION_V1` (defined before execution; drops only session id, session-derived event id, and wall-clock latency) the stream is IDENTICAL to the CAP-003
canonical stream; both runs have the same projected sha256 `96d741b9...c1d26e`.

## OUT OF SCOPE
No frontend change, Clerk UI, sign-in UI, session-history UI, local training buffer, FedAvg/FedProx/SecAgg, FL candidates, physical hardware, CAP-005.

## TESTS
87 CAP-004 tests; 322 prior-phase + lifecycle tests; full regression 2808 passed, 1 skipped, 0 failed; ruff clean; `pip check` clean;
frontend 68 tests / `svelte-check` 0 errors / build ok; 10/10 mutation controls caught behaviourally and restored.

## CONTROL PLANE
CAP-004 -> PASS, CAPG3 -> PASS; CAP-005..011 NOT_STARTED. Component registry `manifests/capstone/component_registry_cap_004_v1.csv` (11 components).

## GIT
Commits: entry `c1b9b1a`; freeze `1fb3023`; amendments `959292f`, `ab02aaa`, `c47522a`, `4669da0`, `f3c9344`, `5b65cff`; result commit = HEAD after this file. CI was neither queried nor triggered.

## DISCLOSURES
Preserved: CAP-001 gate-row 33 vs 50; CAP-002 code-drafted-before-entry; CAP-002 amendment chain; CAP-002 intermediate added-file-count discrepancy;
CAP-003 ACCELERATED-only determinism (LIVE_SPEED bounded-settle/fail-loud); CAP-003 manual stop mid-outage leaves the device in its link state;
CAP-003 `context_available=false` withholding; CAP-003 pre-freeze smoke. New in CAP-004:
1. **User-approved deviation:** the Clerk pin lives in `requirements-capstone-auth.lock`, not `pyproject.toml`/`requirements-dev.lock`, because the frozen V2-014 lock binds those two files byte-for-byte (editing them failed 2 V2-014 tests). Install with `pip install -r requirements-capstone-auth.lock` after `requirements-dev.lock`.
2. **User-approved:** the SQLite store is `capstone_persistence/store.py`, not under `product/`, because the frozen CAP-001 guard test forbids `sqlite3` under `product/`.
3. The first canonical/crash/mutation/test results (on the pre-amendment freeze) were discarded and fully re-run after amendment 2. All first-pass canonical invariants had already held, and nothing from them tuned code.
4. Frozen mutation control 10 was defective (see amendment 1); it was found only after the freeze (an empty first-failure line in the rehearsal was not investigated earlier).
5. `.env.example` was first edited by replacing the file (deleting 3 MONGODB_* names); caught in the final audit review and fixed additively (amendment 5).
6. **Pre-existing flake:** the frozen CAP-003 test `test_monitoring_completes_with_zero_subscribers` is intermittent (4/12 isolated runs fail at the CAP-003 result commit `56fc19f` itself and in this tree, identical signature; the frozen coordinator sets COMPLETED before closing the journal). CAP-003's recorded 2718-test pass was a run where it did not trigger. Two earlier full CAP-004 runs hit it; the final regression run did not. Evidence: `preexisting_cap003_flake.json`. Fixing it requires amending frozen CAP-003 artifacts, which was not done.
7. Real HTTP statuses are not visible on the WebSocket; the 86x200 / 7x422 result is shown through event equivalence plus the identical-to-CAP-003 stream (whose real statuses were recorded in CAP-003) and the 86 DB inference rows.
8. The crash run uses LIVE_SPEED (engineering evidence only, one run). Clerk was exercised only against local fixtures; no real Clerk token, account or network call.
9. The prospective CAPG3 registry row listed `tests/test_capstone_product_app_v1_1.py`, which was never created; the successor app is covered by `test_capstone_session_service.py`.
10. The database ignore rule is local only (`.git/info/exclude`); the tracked `.gitignore` was not modified (protected-file rule). Add `data/capstone/` and `*.sqlite3*` there if wanted.

## FINAL DECISION
CAP-004 / CAPG3: PASS. Awaiting audit. CAP-005 is NOT started.
