# CAP-005 FINAL HANDOFF - Existing SvelteKit frontend productization (CAPSTONE_UI_V1, gate CAPG4)

----------------------------------------------------------------------
PHASE RESULT
----------------------------------------------------------------------
CAP-005: **PASS**   CAPG4: **PASS** (96/96 criteria: the 88 prompt-mandated + 8 implementation-specific, frozen before evaluation).
Evidence: `reports/capstone/cap_005/capg4_criteria.json`.

----------------------------------------------------------------------
ENTRY
----------------------------------------------------------------------
Entry SHA `9db76b482678114ac5c22f3f91a3f55ccb159e17`; origin/main identical; tree clean. Prior phases: CAP-001..004 PASS / CAPG0..3 PASS; CAP-005..011 NOT_STARTED.
All prior locks verified: CAP-001, CAP-002 (+4 amendments incl. amendment 4 below), CAP-003 (+1), CAP-004 (+6).

----------------------------------------------------------------------
UPSTREAM PROTECTION
----------------------------------------------------------------------
Scientific/runtime drift: NO. CAP-001 drift: NO (one guard test retired by recorded amendment, see DISCLOSURES). CAP-002/003/004 drift: NO. Backend drift: NO
(`api/`, `product/`, `capstone_persistence/`, `simulation/`, `src/`, `checkpoints/`, `contracts/` byte-identical; `backend_dirs_untouched = true`).
Non-frontend files modified since entry: the two capstone registries, `tests/test_capstone_lifecycle.py`, `tests/test_t035_lock_versioning.py`,
`tests/test_v2_rel_001_results.py`, `tests/test_capstone_federation_contracts.py` and `scripts/cap_002_protected_audit.py` (last two via recorded amendments).

----------------------------------------------------------------------
FRONTEND FOUNDATION
----------------------------------------------------------------------
Framework: SvelteKit 2 / Svelte 5 / adapter-static (`frontend/`). Original frontend reused: YES. New frontend created: NO (the only package.json files are
`frontend/package.json` and the additive `frontend/clerk-sdk/package.json`). Baseline frontend files: 162 (hashed at entry); changed existing frontend files: 8
(landing page, root layout, /monitor, app.html, app.css, vite/vitest config, one legacy claim test); 41 files added.
CAPSTONE_UI_V1: successor lock of DASHBOARD_UI_V1_5 (`artifacts/capstone/CAPSTONE_UI_V1.lock.json`, 200 bound files); the V1_5 lock file is preserved byte-identical and reports drift by design.
Reused unchanged: Panel, MetricTile, STATE_PRESENTATION texts, design tokens, landing visual components, the research /monitoring tool.

----------------------------------------------------------------------
AUTH FRONTEND
----------------------------------------------------------------------
Clerk package/version: `@clerk/clerk-js` **6.37.0** (latest at implementation time; npm registry; exact pin, no range), in the additive `frontend/clerk-sdk` package (user-approved:
the frozen V2-014 lock binds `frontend/package.json`/`package-lock.json` byte-for-byte). Official ClerkJS: YES. `clerk-sveltekit`: NOT used.
Demo behaviour: backend `/product/v1/system` decides; DEMO never imports/initialises Clerk (0 Clerk requests, no `window.Clerk`); `/me` supplies `demo:faculty`; no password.
Clerk behaviour: lazy dynamic import, `VITE_CLERK_PUBLISHABLE_KEY` required, REST sends `Authorization: Bearer <session token>` taken from the live Clerk session per request.
Silent fallback: NO (`AUTHENTICATION UNAVAILABLE` on a missing key or SDK failure). Secret exposure: NO (source and production bundle scanned; names-only `frontend/.env.example`).
Token persistence: NO (no localStorage/sessionStorage/IndexedDB; tested). Persistent Demo banner on every `/app` route: YES (`OFFLINE DEMO IDENTITY / NOT CLERK AUTHENTICATION`; absent in CLERK mode).

----------------------------------------------------------------------
ROUTES
----------------------------------------------------------------------
`/` landing evolved (primary CTA OPEN NHM -> `/sign-in`); `/sign-in`; `/app` (overview); `/app/device`; `/app/monitoring` - all implemented and built.
Operational list: `/app/history` (GET /sessions table only). Future-phase placeholders (clearly "NOT YET ENABLED", no data): `/app/federation` (+ clients, rounds, live, privacy),
`/app/models`, `/app/research/ml`, `/app/research/fl`; informational: `/app/system`, `/app/about`.
Legacy `/monitor`: redirect/notice to `/app/monitoring` (the fake "Authentication disabled" shell is gone). Legacy `/monitoring`: retained, labelled **RESEARCH RUNTIME TOOL**, logic untouched.

----------------------------------------------------------------------
PRODUCT CLIENT
----------------------------------------------------------------------
Typed `ProductClient` (`lib/product/api.ts`) for exactly: system, me, devices, create simulated device, scan, connect, disconnect, create/list/get session, start, stop.
WebSocket: same-origin `/product/v1/sessions/{id}/live` (no token, no query). Auth headers: Bearer only in CLERK mode, never stored. Proxy: Vite `/product` -> `127.0.0.1:${NHM_PRODUCT_API_PORT:-8002}` (HTTP+WS),
`/v1` still -> research runtime on 8001 (unchanged). The browser made zero `/v1/infer-window` requests.

----------------------------------------------------------------------
DEVICE UX
----------------------------------------------------------------------
Attach NHM Virtual Wearable (frozen scenarios only: NORMAL_MONITORING, CONTEXT_LOSS, POOR_SIGNAL, DISCONNECT_RECONNECT, MIXED_MONITORING_SESSION; MIXED is the *preselected recommendation*, not forced) ->
DETACHED -> scan -> FOUND -> pair/connect -> CONNECTED (states come from the backend); disconnect available. Simulation labels (SIMULATED badge, WEARABLE_SIM_V1, technical scenario ID) and the four-part
banner (SIMULATED WEARABLE / NO PHYSICAL HARDWARE CONNECTED / RESEARCH PROTOTYPE / NOT DIAGNOSTIC) appear on device and monitor pages. Physical hardware is always "NOT CONNECTED / NOT IMPLEMENTED".

----------------------------------------------------------------------
MONITORING UX
----------------------------------------------------------------------
Create (DEVICE_READY) -> open socket -> start -> MONITORING -> natural completion or stop -> COMPLETED with persistent session id and "View sessions". Waveform: SIMULATED SOURCE ECG, 360 Hz ADC_COUNTS, bounded 10 s buffer,
null gaps drawn as shaded gaps (never zero/interpolated). Context only from `context.snapshot` (PENDING / CURRENT / UNAVAILABLE per window; stale values never shown as current). Quality only from `quality.status`
(technical state + frozen label, explicitly "not a monitoring state"). Monitoring state only from `monitoring.state`. Inference metadata from `inference.result`; probabilities live in a collapsed
"RESEARCH / TECHNICAL - not a risk score" section. A device disconnect does not end the session; `system.error` is a technical panel.

----------------------------------------------------------------------
LIVE EVENT INTEGRITY
----------------------------------------------------------------------
Typed discriminated union (8 monitoring kinds); strict field-level parser (federation/unknown kinds, foreign sessions and malformed payloads are rejected visibly as PRODUCT STREAM ERROR). Sequence: next = previous + 1;
gap/duplicate -> error, stop, explicit reconnect. Reconnect: bounded (3 retries, 500/1000/2000 ms), each (re)connect resets derived state and rebuilds from sequence 0 (no double counting; tested incl. the real 3157-event stream).
422/UNUSABLE: never creates a monitoring state (dedicated tests + mutation control). Gap policy: gaps stay gaps. Fake states: NONE.

----------------------------------------------------------------------
OFFLINE FACULTY MODE
----------------------------------------------------------------------
Works without Internet: YES. Chrome ran with a host resolver that blocks every non-loopback name; both canonical runs recorded **zero** external requests and zero failed requests (product pages and landing page).
Clerk initialised in DEMO: NO. Local services required: the frontend, the product API (8002), SOFTWARE_SYSTEM_V2 (8001), SQLite. Remote Google Fonts/Unsplash assets were removed (local font fallbacks, CSS gradients).

----------------------------------------------------------------------
CLAIM AUDIT
----------------------------------------------------------------------
Before (entry tree) vs after (source + rendered text): attached-hardware status lines ("ECG STREAM / CONNECTED"...), ESP32 edge-processing flow, "titanium unibody / dual-core edge ML" copy, real-city FL markers, "Authentication disabled",
"QUALITY / EXCELLENT"-style static values and remote assets were removed or corrected. Physical-hardware claims: none remain. Diagnostic claims: none (every "diagnos*"/"medical device" occurrence is a disclaimer; reviewed, not substring-only).
FL institution claims: none; the federation visual is now a logical topology SIM_FL_SITE_00..07 labelled "ILLUSTRATIVE NETWORK TOPOLOGY - NOT PARTICIPATING INSTITUTIONS". PPG waveform claims: none (unavailable is stated).
Federation status: "FEDERATION PRODUCT RUNTIME NOT YET ENABLED IN THIS PHASE". Fake-metric audit: clear.

----------------------------------------------------------------------
CANONICAL E2E
----------------------------------------------------------------------
Auth mode: explicit DEMO (`demo:faculty`). Stack: production frontend build (identical in both runs, sha256 `b225223c...`) via `vite preview` + headless Chrome (CDP) + real CAP-004 product process + temporary SQLite + fresh SOFTWARE_SYSTEM_V2.
Scenario: MIXED_MONITORING_SESSION. Device states: DETACHED -> FOUND -> CONNECTED (REST); live link: STREAMING -> DISCONNECTED(LINK_LOST) -> RECONNECTING -> CONNECTED(LINK_RESTORED) -> STREAMING -> STOPPED.
Session states: DEVICE_READY -> MONITORING -> COMPLETED. Event count 3157 (2880 waveform chunks, 93 quality, 86 context, 86 inference, 6 device, 3 session, 3 monitoring.state), sequence contiguous.
Quality 86 VALID / 0 DEGRADED / 7 UNUSABLE (93 windows). Waveform gap rendered: [118800, 124199]. Monitoring states: NORMAL_MONITORED_PATTERN -> CONTEXT_UNAVAILABLE -> NORMAL_MONITORED_PATTERN (no RECHECK_SENSOR, no ectopy).
Model IDs: MODEL_V2_FINAL only; calibration: CAL_V2 only. Completed: YES. Persisted after reload and after a product-process restart: YES (history table row, GET /sessions/{id}, SQLite rows: 86 inference, 3 state, 8 change-only quality, 1 preview, FL tables empty).
Two runs reproduce the same facts. A separate real-backend integration test (actual frontend client + parser + LiveModel, no fake JSON) also passed in both runs.

----------------------------------------------------------------------
RESPONSIVE / ACCESSIBILITY
----------------------------------------------------------------------
Responsive (1440 / 1024 / 768 / 390): no horizontal overflow on any audited page (monitor with live data, sign-in, overview, device, history, federation, landing); nav collapses to a menu <= 860 px; waveform stays readable (screenshots in `screenshots/`).
Accessibility: one h1 + one main per page, labelled nav landmarks, skip link on /app pages, every control named/labelled, live regions on device/monitor, keyboard Tab reaches focusables with a visible focus ring,
`prefers-reduced-motion`: zero running animations on product pages; state is never colour-only (always text). Not tested with a real screen reader.

----------------------------------------------------------------------
OUT OF SCOPE
----------------------------------------------------------------------
Local FL training? NO. FedAvg? NO. FedProx? NO. SecAgg? NO. Candidate? NO. Full history analytics? NO (a plain session list only). Physical hardware? NO. CAP-006 started? NO.

----------------------------------------------------------------------
TESTS
----------------------------------------------------------------------
Frontend: 145 passed / 2 skipped (the real-backend test is skipped unless a backend URL is provided; it was executed in both canonical runs); of these 77 are new (live model on the real stream, API/auth, socket/store, 15 rendered-component, 23 static guards).
Mutation controls: 10/10 caught and restored. Python regression: 2819 passed, 1 skipped, 0 failed. svelte-check: 0 errors (112 warnings, baseline 118). Build: ok. ruff: clean. pip check: clean. CI queried? NO. CI triggered? NO.

----------------------------------------------------------------------
CONTROL PLANE
----------------------------------------------------------------------
CAP-001/CAPG0 PASS; CAP-002/CAPG1 PASS; CAP-003/CAPG2 PASS; CAP-004/CAPG3 PASS; CAP-005/CAPG4 PASS; CAP-006 NOT_STARTED.
Components (`component_registry_cap_005_v1.csv`): CAPSTONE_FRONTEND_PRODUCT_PROTOCOL_V1 (FROZEN_ENGINEERING_PROTOCOL), CAPSTONE_UI_V1 (FROZEN_ENGINEERING_INTERFACE), CAPSTONE_FRONTEND_AUTH_V1, CAPSTONE_PRODUCT_CLIENT_V1,
CAPSTONE_MONITORING_STORE_V1, CAPSTONE_DEVICE_UI_V1, CAPSTONE_MONITORING_UI_V1 (all FROZEN_ENGINEERING_IMPLEMENTATION).

----------------------------------------------------------------------
GIT
----------------------------------------------------------------------
Entry/control commit `a3b9ec5`; UI/method freeze `5cf83da`; amendments `c7441f2` (CAP-001 amendment 1 + CAP-002 amendment 4 + CAP-005 amendment 1), `23ff485` (CAP-005 amendment 2), `1892218` (3), `89353cc` (4), `8f47676` (5);
result commit = HEAD after this file; origin/main synchronized after push.

----------------------------------------------------------------------
DISCLOSURES
----------------------------------------------------------------------
Preserved: CAP-001 33-vs-50; CAP-002 code-drafted-before-entry and amendment chain; CAP-003 LIVE_SPEED bounded-settle/fail-loud, manual-stop-mid-outage, context-withholding projection, pre-freeze smoke;
CAP-004 additive Clerk Python pin file, SQLite store outside product/, six-amendment chain, inherited CAP-003 flaky test, local-only SQLite git exclude, Clerk local-fixture-only verification.
New in CAP-005:
1. **Clerk frontend not live-account tested.** ClerkJS was tested only through a mocked official boundary; the Clerk WebSocket session-cookie path was NOT verified (no live account). The Vite proxy forwards cookies same-origin, but this is unproven.
2. **User-approved:** `@clerk/clerk-js` 6.37.0 is pinned in the additive `frontend/clerk-sdk` package, not `frontend/package.json` (the frozen V2-014 lock binds it). Install with `npm ci --prefix clerk-sdk`; the build needs it installed.
3. **User-approved:** the CAP-001 guard `test_existing_sveltekit_frontend_is_unchanged_and_the_only_frontend` was retired via recorded amendments (CAPSTONE_PRODUCT_PROTOCOL_V1 amendment 1; `verify_cap001_lock` now honours CAP-001 amendments through CAPSTONE_DEVICE_EDGE_PROTOCOL_V1 amendment 4). Its replacement asserts "unchanged or accounted for by CAPSTONE_UI_V1". This reopens two frozen older-phase files (disclosed sha chains).
4. DASHBOARD_UI_V1_5 was superseded by CAPSTONE_UI_V1 (repository precedent); two older tests (`test_t035...`, `test_v2_rel_001_results`) were updated to expect V1_5 drift and verify the successor. One legacy test (`legacy-claims.test.ts`) allows the simulated-source "360 Hz" label in exactly three product files, with its own qualification test.
5. Legacy frontend routes retained: `/monitoring` (research replay tool, labelled), the other legacy workbench routes (`/overview`, `/fl/*`, `/research/*`, `/signals/*`, ...) are untouched and still contain old placeholder content; they are not linked from the product shell except two research "see also" links.
6. External landing assets: none remain (Google Fonts and four Unsplash images removed). Typography falls back to local system fonts unless the NHM families are installed; a real browser with WebGL renders the 3D hero (headless Chrome needed SwiftShader).
7. Inherited CAP-003 flake: it failed in the prior-phase subset runs (every time that subset ran, ~50% base rate); the full regression on the final state was clean twice (2819 passed). Evidence: `reports/capstone/cap_004/preexisting_cap003_flake.json`.
8. **Method repairs (all before the recorded evaluation, criteria text unchanged):** CAP-005 amendments 1-5 (audit allow-lists, a formatting wrap, and evaluator defects: duplicate list entry, over-broad regex, comment URLs counted as requests, `</summary>` matching `/summary`, UNUSABLE rendering relying on a transient DOM frame). The product code and the canonical runs were not changed by any amendment.
9. **Chronology disclosure:** the frontend baseline inventory, reuse audit and `claim_audit_before.json` were generated from the entry commit tree *after* implementation had begun (my inspection happened before coding, but the evidence files were written later); they derive from `git show 9db76b4:...`, so their content is unaffected.
10. Two UX defects found and fixed during implementation (before the freeze): a real bug where the CLERK path never recorded the auth mode (so no bearer token would have been sent) and a per-window "no inference/context" flicker (now the PENDING semantics). Landing hero layout was also fixed after reviewing screenshots.
11. The canonical runs use ACCELERATED timing (as CAP-003/004); a real-time LIVE_SPEED faculty run exists but was not the canonical evidence. Screen-reader testing and contrast measurement were not performed.

----------------------------------------------------------------------
FINAL DECISION
----------------------------------------------------------------------
CAP-005 accepted? Awaiting audit - result: PASS. CAPG4 accepted? Awaiting audit - result: PASS. CAP-006 allowed next? Yes, after audit; it was NOT started.
Backend/scientific reopening required? NO. (Reopened frozen items, all disclosed: two CAP-001/CAP-002 files via recorded amendments, and the DASHBOARD_UI_V1_5 supersession.)
