# CLERK-LIVE-001 HANDOFF — Real Clerk TEST-instance integration (gate CLERKG0)

## PHASE RESULT
CLERK-LIVE-001: **PASS** · CLERKG0: **PASS** (88/88 frozen criteria, `clerk_g0_criteria.json`) · CAPSTONE_CLERK_CONNECTED_V1: **ACCEPT** (`connected_decision.json`).

## ENTRY
Entry SHA `be2e4473223876699e74b64adc72672453ebc34b` == origin/main, clean. CAPSTONE_RELEASE_V1 preserved: YES. Tag `capstone-release-v1` still -> `3ad1b07408a0c3556fbc5039f1a7a4fee824db96`: YES (verified on the remote at entry and final). CAP-001..011 / CAPG0..10 PASS, no CAP-012.

## KEY HANDLING
Publishable key source: untracked, git-ignored root `.env` (operator-authorised; also supplied as an external file path to the clean clone). Secret source: the same. Key rotation performed: NO. Secret committed: NO (exact-value scans of tracked/untracked files, staged diffs and all commits since entry: zero). Secret logged: NO. Frontend contains secret: NO (source, build and `sk_`-prefix scans: zero; the publishable key is in the build, as expected). SQLite contains secret/token/password: NO. The literal secret is not recorded anywhere.

## CURRENT IMPLEMENTATION BASELINE
Existing Clerk implementation tested against the real instance BEFORE any auth change: YES (`current_implementation_baseline.json`). Backend: PASS (system CLERK/demo_mode=false; no token and garbage bearer 401; a real session token minted by the official backend SDK verifies as signed-in, and is correctly refused by authorized parties because it carries no `azp`). Browser sign-in: FAILED — `mountSignIn` threw "Clerk was not loaded with Ui components" (ClerkJS 6.x ships without prebuilt UI), so REST, monitoring WebSocket and federation WebSocket were unreachable. Code change required: YES (frontend only).

## AUTH CONFIGURATION
Frontend variable `VITE_CLERK_PUBLISHABLE_KEY`; operator-supplied `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` is mapped to it by the launcher for the Vite build/preview only (the frontend never reads NEXT_PUBLIC_*). Backend secret variable `CLERK_SECRET_KEY` (product API process only; never passed to the frontend build/preview or inference). Auth mode `NHM_PRODUCT_AUTH_MODE=CLERK`. Authorized parties `NHM_CLERK_AUTHORIZED_PARTIES=http://127.0.0.1:4173` (explicit); wildcard NO (refused; a wrong authorized party rejects the real session). SDK versions: @clerk/clerk-js 6.37.0 (unchanged), clerk-backend-api 7.0.0 (unchanged).

## IMPLEMENTATION
Authorised successor change (official Clerk JavaScript quickstart, https://clerk.com/docs/js-frontend/getting-started/quickstart): `frontend/src/lib/product/auth.ts` loads the `@clerk/ui` browser bundle from the instance Frontend API domain (derived from the publishable key, crossorigin anonymous) and calls `clerk.load({ ui: { ClerkUI } })`; CLERK mode only. New: CAPSTONE_UI_V1_3 (whole-frontend successor lock), `clerk-ui-loader.test.ts`, the additive connected launcher `scripts/run_capstone_clerk_connected.py`, the real-browser E2E orchestrator/driver, the frozen CLERKG0 evaluator, mutation controls, clean-connected-clone harness and `docs/capstone/CLERK_CONNECTED_RUNBOOK_V1.md`. Existing auth code modified: only `auth.ts` (the loader); backend provider, resolver, API, FL and science untouched. Pure amendments (successor-awareness only): FRONTEND_PRODUCT 9, FEDERATION_UX 3, HISTORY 9_3, FACULTY_DEMO 2 + successor-aware UI verifiers V1/V1_1/V1_2; V1/V1_1/V1_2 lock files byte-identical. Dependency change: NONE.

## REAL CLERK SIGN-IN
Real Clerk TEST (development) instance: YES. Real browser: headless Google Chrome via CDP, fresh profile per run. Test-user strategy: two clearly labelled users created through the official Clerk Backend SDK (TEST_USER_A, TEST_USER_B; `+clerk_test` email + `+1 201 555 01xx` phone, because the instance requires a phone). Sign-in success: YES, fully automated through the real Clerk UI; the instance's client-trust step was satisfied with Clerk's documented fixed test code (424242) — no bypass, no forged token, no human step. `/system`: auth_provider CLERK, demo_mode false. `/me`: real Clerk-shaped user id, CLERK, demo_mode false. Demo fallback: NO (no demo button in Clerk mode).

## REST AUTH
Bearer obtained from the active Clerk session by the app (observed as request headers, JWT-shaped; value never recorded). Verified by the official `authenticate_request_async`. Missing token 401; garbage bearer 401; JWT-shaped garbage 401; DemoAuth acknowledgement as bearer/header 401. After logout: protected REST 401, protected sockets 4401.

## MONITORING WEBSOCKET
Real Clerk browser session, same-origin Vite proxy, session-cookie transport (`__session`), no token in the URL, handshake 101, 3157 frames, session COMPLETED (MODEL_V2_FINAL, CAL_V2). Owner enforced (user B -> 4403).

## FEDERATION WEBSOCKET
Real Clerk session, same-origin, no token in URL, handshake 101, 202 frames; run COMPLETED (LIVE_RUN FEDAVG SECAGG_SHADOW; 8 clients, 3 rounds, 24 updates). Owner enforced (user B -> 4403).

## CROSS-USER ISOLATION
User A owns the device/session/run/candidate. User B (a second real Clerk user): read session 403; summary/timeline/run/rounds 403; start run and start/stop session (control) 403 (probes rewrite one of B's own app requests, keeping B's real bearer, with controls proving the rewrite reaches the target: nonexistent id 404, global research 200); monitoring WS 4403; federation WS 4403; B's own session list excludes A's. All correctly blocked: YES.

## PERSISTENCE
Backend restarted on the same SQLite workspace; user A signed in again with a FRESH browser profile: same Clerk owner, same completed session/history/timeline, same federation run (3 round cards, COMPLETED), same candidate (ACCEPTED_TO_SANDBOX, IN_SANDBOX, production_deployed=false), governance retained. Browser refresh restores the Clerk session; logout then re-login restores identity.

## DEMO MODE REGRESSION
The unchanged offline faculty journey re-ran with the new frontend: DemoAuth works YES; Clerk initialised NO; external/Clerk requests 0; semantic digest `3a57614e15264f3cd7661a016a30d033aab78647d57be04273c386cc9d048726` identical to the CAP-010 canonical digest.

## SCIENTIFIC / FL ISOLATION
MODEL_V2_FINAL, CAL_V2 and the runtime binding unchanged; the candidate state digest in Clerk mode equals the offline demo's byte for byte; identity selects model NO; session data enters FL NO (no federation module imports history/monitoring/auth); personal model NO; candidate deployed NO.

## SECRET AUDIT
Tracked files, frontend source, frontend build, launcher/service logs, SQLite, runtime workspace/federation/candidate artifacts, raw driver output and committed evidence: all clean (exact-value and `sk_`-prefix scans). NHM stores no JWT-shaped value in localStorage, sessionStorage or IndexedDB (users A and B).

## CLEAN CONNECTED CLONE
Target `4cb20ec1093f3a8697827abfffc1e5c1fd787055`; fresh remote clone; fresh Python 3.11 venv; fresh `npm ci` (frontend/clerk-sdk and frontend); fresh Chrome profile for every browser run; keys and test users supplied as external file paths only; developer env/browser session/DB copied NO; real sign-in, monitoring WS, federation WS, ownership, logout, refresh, restart, wrong-authorized-party: all PASS (`clean_connected_clone.json`, `clean_connected_clone_e2e/`). Result PASS.

## TESTS
Auth backend/monitoring WS/federation WS/ownership/lifecycle targeted: 97 passed. Full Python: 3082 passed, 1 skipped, 1 deselected (inherited CAP-003 race; isolated probe passed). Frontend vitest 197 passed; svelte-check 0 errors; build OK; ruff clean; pip check clean. Mutation controls 20/20 caught and restored. CI queried NO; CI triggered NO.

## FINAL SYSTEM
Offline profile DEMO: preserved. Connected profile CLERK: verified (TEST instance). Released monitoring MODEL_V2_FINAL. Federation engineering-only (8 logical synthetic clients). Candidate deployed: No. Physical hardware: No.

## GIT
Entry commit `6475280`; control + baseline `69e9983`; compatibility commit (UI_V1_3 + amendments) `3518265`; protocol freeze / connected target `4cb20ec1093f3a8697827abfffc1e5c1fd787055`; post-freeze amendment (audit allow-list only) `c8c1e1c` + correction `b4076fb`; result commit = the commit carrying this file; tag `capstone-clerk-connected-v1` -> connected target; `capstone-release-v1` unchanged.

## DISCLOSURES
- Clerk TEST/development instance with TEST keys; this verifies integration behaviour, not production-account operation. No production Clerk deployment claim, no security certification, no penetration test, no compliance claim.
- Connected mode requires Internet access to Clerk-owned origins (observed: the instance's `*.clerk.accounts.dev`, `clerk-telemetry.com`, `img.clerk.com`); offline DemoAuth is a separate mode with zero Clerk traffic.
- Client trust: a new browser on this instance asks for a verification code; Clerk's documented fixed test code was used (automated, no manual step).
- The first full test recording failed vitest because `VITE_CLERK_PUBLISHABLE_KEY` was exported in the shell (a pre-existing sign-in component test assumes no key); preserved as `test_report_attempt_1_FAIL_vitest_with_vite_clerk_key_in_environment.json`; rerun in a clean shell passed.
- A post-freeze, audit-allow-list-only amendment (`c8c1e1c`, corrected in `b4076fb`) was needed because the first final audit flagged three additive scripts; criteria and canonical runs were unchanged.
- After sign-in Clerk lands on `/` (its default redirect), not `/app`; the app restores the session on `/app` (no defect).
- The authorised successor edits touched shared verifier infrastructure (three historical UI verifiers, two historical guard tests) with recorded old/new SHA amendments; historical lock files are unchanged.
- Test users A and B remain in the Clerk test instance; keys were not rotated or revoked (per operator instruction).
- All inherited scientific, FL, hardware and capstone limitations carry forward.

## FINAL DECISION
Real Clerk browser authentication verified: YES. Real monitoring WebSocket authentication verified: YES. Real federation WebSocket authentication verified: YES. Cross-user ownership verified: YES. Offline DemoAuth preserved: YES. Scientific/runtime/FL state unchanged: YES. CAPSTONE_CLERK_CONNECTED_V1 accepted: YES.
