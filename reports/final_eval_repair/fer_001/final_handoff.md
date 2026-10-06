# FINAL-EVAL-REPAIR-001 HANDOFF
## Evaluator-readiness presentation repair

## PHASE RESULT

FINAL-EVAL-REPAIR-001: **PASS**

FERG0: **PASS 51/51**

FINAL_EVALUATOR_AUDIT_RERUN: **AUTHORIZED**

This handoff does not state, and the phase does not establish, evaluator readiness. Only the unchanged FINAL_EVALUATOR_AUDIT_V1, rerun in full from a fresh clone, may do that.

## ENTRY

- Entry SHA / origin/main: `5d40752442fd1a05dd2459dd216aff51fe4c022c` (equal, tree clean).
- Tags unchanged: `user-bound-fl-lite-v1` -> `cf18cba…`, `capstone-release-v1` -> `3ad1b07…`, `capstone-clerk-connected-v1` -> `4cb20ec…`.
- UFL acceptance target `cf18cba` reachable; UFL-LITE-001..003 / UFLG0..2 PASS; UI predecessor CAPSTONE_UI_V1_4.
- **FINAL_EVAL_REPAIR_TARGET_SHA = `ce6fe2b10b13fbe494f5f531a8ac953a7b958f73`** (pushed; unauthorised delta from entry: none; no canonical evidence existed at the target). Candidate build for the audit rerun, not a release; no final/release/evaluator-ready tag created.

## FAILED AUDIT INPUT

F-01 About stale federation status (BLOCKER); F-02 landing stale federation status (BLOCKER); F-03 ~33 reachable legacy routes (MAJOR); F-04 connected runbook stale (MAJOR); F-05 no presentation guard (MAJOR); F-06 missing font request (MINOR); F-07 deep-link HTTP 404 (OBSERVATION). All reproduced from the entry tree (`failed_findings_reproduction.json`).

## F-01 ABOUT
- Old: "The federation product runtime is not yet enabled."
- New: states the engineering federation runtime is enabled; eight logical synthetic clients on one demonstration machine, not hospitals; connected LIVE_RUN may present SIM_FL_SITE_00 as MY EDGE CLIENT (presentation only; physiology does not train any model; no personal model); candidates are sandbox-only and never replace MODEL_V2_FINAL.
- Truth source: `configs/final_eval_repair/evaluator_truth_v1.json` + `/system` (`federation_runtime=ENABLED_ENGINEERING`). Tests: `test_about_*`; mutation `ABOUT_RESTORED_NOT_YET_ENABLED`.

## F-02 LANDING
- Old: preloader "FEDERATION RUNTIME / NOT YET ENABLED" and a paragraph saying the runtime is not yet enabled.
- New: "FEDERATION RUNTIME / ENGINEERING ENABLED" with qualified federation copy (synthetic clients, one machine, genuine local optimisation, sandbox candidate, not hospitals, not personalized FL, SecAgg not differential privacy or anonymity). Also qualified the over-broad "privacy-preserving" headings and the "RAW DATA STAYS LOCAL" box; hero/meta copy updated. No owner-binding language on the public page.
- Tests: `test_landing_*`; mutations for preloader, paragraph, owner-binding overreach.

## F-03 LEGACY ROUTES
- Route files discovered dynamically: 53. Classified: 53/53 (0 unclassified). 33 `LEGACY_REDIRECT`, 1 `LEGACY_RETAINED_RESEARCH_TOOL` (`/monitoring`), remainder current/public/research/compat/dynamic/catch-all (`configs/final_eval_repair/legacy_route_policy_v1.json`).
- Mechanism: one pure module (`route-policy.ts`) + `+layout.ts` load that redirects exact legacy paths (307) to canonical `/app/...` targets; legacy page files are unmodified but never render. Same-origin, no loops, no substring matching, query/hash dropped.
- Known examples: `/fl/overview`, `/fl/personal-models` -> `/app/federation`; `/ai/insights` -> `/app/research/ml`; `/overview` -> `/app`.
- `/monitoring` retained: labelled RESEARCH RUNTIME TOOL banner, linked from `/monitor`, non-diagnostic, no federation/personalization claim.
- Real-browser crawl (real Clerk, fresh profile, 4 widths): every route lands where the policy says; 0 stale or fabricated content rendered, 0 console errors, 0 5xx, one h1 everywhere, no horizontal overflow.

## F-04 CONNECTED RUNBOOK
- `CLERK_CONNECTED_RUNBOOK_V1.md` is bound by the CLERK-LIVE-001 lock, so it is untouched. New current runbook `CLERK_CONNECTED_RUNBOOK_V1_1.md` (supersedes it for evaluator use) corrects "behave exactly as in the offline mode" and adds section 4a: CLERK+LIVE_RUN owner-bound presentation, synthetic data, no personal model, no personalized FL, not persisted; DEMO, REPLAY and global clients unbound.

## F-05 GUARDS
- `evaluator_truth_v1.json` (machine-readable truth contract), `FINAL_EVALUATOR_PRESENTATION_V1` (`final_eval_repair_presentation.py`: About/landing/stale-copy/claims/route-policy/runbook/truth/unbound/pages/font checks over the import graph of current routes, with clause-level negation handling), `final_eval_repair_crawl_analysis.py` (browser crawl + cross-page truth matrix), 35 mutation controls (all caught, all restored), permanent tests.
- Final cross-page truth matrix (landing, overview, About, System, federation pages, models, research): 0 contradictions.

## F-06 FONT
- Initiator: `Signature` component `fetch("/LastoriaBoldRegular.otf")` used twice on the landing page (decorative animation; the font never existed). Repair: removed the two usages and import (no font added, no dependency). Final landing network: 0 failed/404 requests.

## F-07 DEEP LINKS
- Root cause: adapter-static `fallback: index.html` + `vite preview` answers non-prerendered dynamic paths with the SvelteKit bootstrap shell and HTTP 404; the client router then renders the page. Disposition: KNOWN STATIC-HOST FALLBACK SEMANTIC, no routing change. Proven evaluator-safe: `/app`, `/app/about`, `/app/history`, `/app/history/<id>`, `/app/federation/live?run=`, `/app/research/ml` navigate and reload with identity, correct page, no visible error, no console error.

## UI GOVERNANCE
- `CAPSTONE_UI_V1_5` (owner FINAL-EVAL-REPAIR-001, predecessor V1_4, 235 files, 5 changed). V1..V1_4 lock files byte-identical; historical verifiers V1..V1_4 made successor-aware.
- Pure SUCCESSOR_COMPATIBILITY_ONLY amendments with exact old/new SHA: FRONTEND_PRODUCT 9_2, FEDERATION_UX 5, HISTORY 9_5, FACULTY_DEMO 4, UFL_LITE_002 1. No result evidence in any amendment. No new dependency.

## NON-INTERFERENCE
Backend, API/contracts, DB, FL runtime, auth, scientific artifacts, MODEL_V2_FINAL, CAL_V2: zero drift against the entry baseline hashes and `git diff`. Canonical candidate digest `3f0b7762…0c4e` unchanged; candidates ACCEPTED_TO_SANDBOX, not deployed.

## REGRESSIONS
- Connected real-Clerk owner binding: 1 MY EDGE CLIENT, 7 peers, 8 clients, 93 examples, 3 rounds, 24 updates, canonical digest, refresh/WS OK; global view and REPLAY unbound.
- Offline DemoAuth: semantic digest `3a57614e…8726` identical, no Clerk traffic, no owner binding.

## TESTS
Vitest 214 passed / 0 failed; svelte-check 0 errors; build OK; targeted Python 117 passed; full Python 3161 passed, 1 skipped, 1 deselected (CAP-003 policy, isolated probe passed); ruff clean; pip check clean; CI neither queried nor triggered. A pre-freeze exploratory full run exposed one guard (a V1_4 shadow-verifier test) that needed the V1_5 lock registered in its shadow; fixed in the test and its amendment before the freeze.

## MUTATION CONTROLS
35/35 caught, 35/35 restored (names frozen in the protocol).

## CLEAN CLONE
Target `ce6fe2b`; fresh clone, fresh venv and `npm ci`, tree clean; Clerk and UI V1_5 verifiers, targeted tests, presentation verifier, and the real-Clerk crawl + owner-binding regression inside the clone all PASS; no tracked modifications; no secret in the clone.

## NOTES
- Two harness defects found by a non-canonical rehearsal were fixed before the freeze: an authenticated user is correctly redirected from `/sign-in` to `/app`, and the "visible error" regex matched ordinary words. No post-freeze repair was needed.
- Test Clerk keys remain in the untracked, git-ignored `.env`; not rotated.

## GIT
`def8464` entry · `820ddf1` prospective registration + protocol · `9bb810b` About/landing/font · `e2228e2` legacy-route policy · `5326e7c` runbook V1_1 · `ce6fe2b` freeze (repair target) · result commit (this evidence + PASS registries).

## FINAL DECISION

"FINAL-EVAL-REPAIR-001 repairs the known evaluator-readiness findings
and freezes the repaired presentation target. It does NOT itself
establish evaluator readiness. The unchanged
FINAL_EVALUATOR_AUDIT_V1 must now be rerun in full from a fresh clone."
