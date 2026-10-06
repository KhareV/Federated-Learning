# UFL-LITE-003 — Real Clerk end-to-end verification + final acceptance (UFLG2)

**Result: UFL-LITE-003 = PASS · UFLG2 = PASS (65/65) · USER_BOUND_FL_LITE_V1 = ACCEPT.** Verification-only; zero product-feature delta.

## Chronology
1. Entry audit: HEAD == origin/main == `9324ef4`; UFLG0 and UFLG1 PASS, locks verified; tags `capstone-release-v1` / `capstone-clerk-connected-v1` unchanged.
2. Prospective registration (`14ea7c3`): UFL-LITE-003 IN_PROGRESS, UFLG2 NOT_STARTED.
3. Method freeze (`cf18cba`): protocol (65 criteria, 35 mutation controls), real-Clerk CDP driver, analyzers, E2E orchestrator, clean-clone harness, frozen evaluator, lock — all before any canonical evidence.
4. **UFL_LITE_ACCEPTANCE_TARGET_SHA = `cf18cba4d7891c514553a1702e227f28dbe26f7c`** (pushed; protected-tree delta from entry: none; no canonical evidence existed at the target).
5. Canonical evidence: real-Clerk E2E, offline DemoAuth regression, tests, clean clone of the target, 35 mutation controls, protected final audit, frozen evaluator (pre-transition then FINAL).

## What was verified (real Clerk TEST instance, real headless Chrome, fresh profiles, no mocks, no DemoAuth fallback)
- Owner card: exactly one `MY EDGE CLIENT` = SIM_FL_SITE_00; 7 synthetic peers; exactly 8 clients, no ninth; technical ids unchanged; synthetic-engineering / not-your-physiology wording.
- Live run `FEDRUN-D1340DC2BDFD`: 3 rounds, 24 updates (8/8/8), SITE_00 93 examples (event-derived), owner state/rounds/updates derived from state/milestones/updateDigests, raw examples sent 0, locality wording; no contribution %, personalization or consent UI.
- Candidate digest `3f0b7762…0c4e` (canonical), ACCEPTED_TO_SANDBOX / IN_SANDBOX / not deployed; MODEL_V2_FINAL, CAL_V2.
- Refresh mid-run and WebSocket reconnect (cookie transport, no token in URL); backend restart on the same SQLite with a fresh browser profile: identical update and round-state digests.
- Two-user isolation: user B gets REST 403 on A's run (controls: 404 nonexistent, 200 global) and WebSocket 4403; no owner card on A's run.
- Global clients view and REPLAY run (`FEDRUN-7BC8C18412F1`) show no owner binding; candidate set unchanged.
- Offline DemoAuth regression: semantic digest `3a57614e…8726` identical, no Clerk traffic.
- Secrets: exact-value and `sk_test_` scans of evidence, logs, build, frontend source, SQLite and repo are clean; owner binding is not persisted.

## Clean clone (two distinct proofs)
- **Proof A (clean clone):** fresh `git clone` at the target SHA, fresh venv, `npm ci`, clean tree, frozen verifiers and targeted tests pass.
- **Proof B (connected):** the frozen real-Clerk E2E run inside that clone with fresh Clerk sessions; all analyzer checks pass. Needs Internet access to Clerk.

## Test counts
Vitest 210/0; svelte-check 0 errors; build OK; targeted Python 88 passed; full Python 3132 passed, 1 skipped, 1 deselected (CAP-003 race policy: deselected `test_monitoring_completes_with_zero_subscribers`, isolated probe passed); ruff and pip check clean; 35/35 mutation controls caught and restored. CI neither queried nor triggered.

## Notes
- Non-canonical scratch rehearsals (not committed) debugged two harness defects before the freeze (restart read before event replay; WebSocket aborted-by-navigation handling). No post-freeze repair was needed.
- Clean-clone harness was first invoked without `PYTHONPATH` (import error before any stage ran); re-invoked with the file unchanged.
- Test keys are untracked in a git-ignored `.env`; not rotated or revoked.

## Acceptance
USER_BOUND_FL_LITE_V1 accepted at `cf18cba`; tag `user-bound-fl-lite-v1` created at that SHA. No further phase is proposed.
