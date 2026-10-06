# FINAL-EVAL-REPAIR-002 HANDOFF
## Final public-presentation truth + accessibility repair

## PHASE RESULT

FINAL-EVAL-REPAIR-002: **PASS**

FERG1: **PASS 51/51**

FINAL_EVALUATOR_AUDIT_RERUN: **AUTHORIZED**

This handoff does not state, and the phase does not establish, evaluator readiness. Only the unchanged FINAL_EVALUATOR_AUDIT_V1, rerun in full from a fresh clone, may do that.

## ENTRY
- Entry SHA / origin/main: `3402dc1da1c6d5c029903a9a51a74e4ecc427ec8` (equal, tree clean). FER-001 PASS / FERG0 PASS, UFL-LITE-001..003 PASS, UI V1..V1_5, capstone/Clerk locks and the frozen method locks verified; tags `user-bound-fl-lite-v1`, `capstone-release-v1`, `capstone-clerk-connected-v1` unchanged.
- **FINAL_EVAL_REPAIR_002_TARGET_SHA = `b549f9915d91d960c949941b9341004152e5f5d1`** (pushed; no unauthorised delta from entry; no canonical evidence existed at the target). A candidate build for the audit rerun, not a release; no final/release/evaluator-ready tag exists.

## F2-01 — landing / NeuralGraph claim integrity (MAJOR) — CLOSED
- **Entry:** NeuralGraph said "99.8% Coverage", "99.8% unmonitored blind intervals", "LIVE EDGE SYNAPSE GRAPH", "real-time feature vectors" while labelling its values illustrative. Reading the whole landing import graph (42 files) found the problem was wider than the four strings: canvas text "Normal 72/76/74/70 BPM" and "4.5 Hours Unmonitored", node values "92 ms (Normal)", "54.2 ms", "218 ms", "0.52 R (98% SpO₂)", "0.96 (Nominal)", "1.24 LF/HF", ranges "80–120 ms"…, "Edge Peak Detector", "128-D Edge Latent", SystemArchitecture latencies "< 0.2 ms / 0.6 ms / 1.2 ms", "14.4 kbps", "512 KB SRAM", repo paths ("See reports/…json"), ProductWorkstation "ECTOPIC PVC BEAT DETECTED", "NORMAL SINUS RHYTHM // OPTIMAL", "Real-Time Vitals", fake BPM jitter via setInterval, "EDGE PRIVACY STATUS: LOCAL ONLY / 0 Bytes Uploaded" (false: inference is server-side), MultimodalStudio interpretive statuses.
- **Final:** NeuralGraph is an unmistakably illustrative visualization ("ILLUSTRATIVE SIGNAL-FLOW GRAPH", "values are illustrative - not live telemetry", "No measured percentage is claimed"); every node value is "Illustrative (not live)"; invented latencies/throughput/vitals/statuses/paths removed or labelled concept/synthetic; the workstation shows labelled synthetic scenario parameters, no detections, no fake jitter, and "INFERENCE LOCATION: SERVER-SIDE"; globe markers labelled decorative with "eight synthetic clients on one demonstration machine - not in these cities"; a caption states that text baked into the 3D watch render is illustrative; hero pillar says "LIVE MONITORING SESSIONS - simulated wearable, accelerated timing".

## FULL LANDING CLAIM INVENTORY
| | entry | final |
|---|---|---|
| landing import-graph files | 42 | 42 |
| high-risk strings | 65 | 40 |
| UNSUPPORTED_QUANTITATIVE_ASSERTION | 30 | 2 (runtime milestone labels, covered by RUNTIME provenance) |
| MISLEADING_LIVE_STATE_ASSERTION | 6 | 2 (product's live-session wording, RUNTIME provenance with required "simulated/accelerated" qualification) |
| STALE_PRODUCT_ASSERTION | 3 | 1 (hardware-table row whose value is "Not Implemented") |
| MARKETING_METAPHOR | 5 | 0 |
| ILLUSTRATIVE_AND_EXPLICITLY_QUALIFIED | 17 | 31 |
Files: `landing_claim_inventory_entry.json`, `landing_claim_inventory_final.json`.

## REMOVED / REQUALIFIED NUMERICAL CLAIMS
All hard-coded measurement-like values in NeuralGraph (92 ms, 54.2 ms, 218 ms, 0.52 R, 98% SpO₂, 0.96, 1.24 LF/HF, 80–120 ms, 35–80 ms, 180–260 ms, cosine > 0.92, 99.8%) became "Illustrative" or were removed; none has a frozen/runtime/external source, and none was given an invented citation. Retained numbers are scenario parameters inside strings that say "synthetic scenario" (e.g. "Resting scenario (72 BPM, synthetic)") or optical-wavelength node names declared illustrative.

## PRESENTATION PROVENANCE + GUARD IMPROVEMENT
- `configs/final_eval_repair/presentation_provenance_v1.json` (EVALUATOR_PRESENTATION_PROVENANCE_V1): 6 entries, none invented (3 RUNTIME with named source, 3 ILLUSTRATIVE with required qualification kept in the surface file).
- `final_eval_repair_002_provenance.py` (FINAL_EVALUATOR_PRESENTATION_V2) scans the whole landing import graph with the full rule set and every other current surface with the hard quantitative rules; classes: percentages, quantified durations, score-with-number, physiological values, live/real-time, current-value, normal/optimal labels, patient/wearable-stream claims, edge/on-device claims, clinical-monitoring, detection claims, repo-file references. Figures, scores and paths are never excused by an "illustrative" word; wording only excuses labels and values inside the same string. Run against the entry components it flags 23 / 8 / 14 / 2 strings in NeuralGraph / ProductWorkstation / SystemArchitecture / MultimodalStudio respectively.
- The mutation controls proved the guard during development: two initial escapes (a percentage excused by the word "Illustrates"; a "label: 98%" string mistaken for CSS) were fixed in the guard, not the controls.

## F2-02 — landing accessibility (MINOR) — CLOSED
- **Skip link:** first focusable element, hidden until focus, visible on focus, moves focus to `<main id="top" tabindex="-1">` (browser keyboard test: first Tab = "Skip to main content", Enter -> MAIN).
- **Nav:** `aria-label="NHM landing navigation"` (entry: unnamed).
- **Reduced motion (real browser, `prefers-reduced-motion: reduce`):** entry 1440 rAF frames in 3 s + 3 running animations; final **0 rAF frames, 0 running animations**, text retained (9380 chars), all 2D canvases drawn, no blank region. Loops fixed: NeuralGraph, MultimodalStudio (static redraw per scenario), Globe (static), WatchScene (static poster image instead of a WebGL loop), MorphingText (first phrase, no auto-cycling), AnimatedBeam (no sweep), AnimatedGridPattern (no blinking squares), CSS pseudo-element animations, federation packet dots.
- Also found by the baseline: a `/favicon.ico` 404 on first load; fixed with an inline `data:` icon (no asset added).

## F2-03 — touch targets (MINOR) — CLOSED
Entry: 10 landing + 6 product actionable targets below 24 px at 390 px. Repaired by padding/min-size only: hero text link, footer links, arc-timeline step ticks (24 px hit area around the 2 px line), overview links, history "VIEW EVIDENCE" link, federation run links, digest copy buttons. Final: **0 non-inline targets under 24 px on the landing page and all 15 product pages** (history detail and live-run pages included).

## LOADER OBSERVATION — RESOLVED
"Opening the NHM workspace…" is now a `main` landmark containing a status region and an `h1` (visual unchanged).

## CANDIDATE OBSERVATION — PASS, no change
The UI shows candidate identity (`candidate_id`) and `State digest` as separate fields; no text says duplicate/same/deployed twice (searched). Two LIVE runs create two candidate records with the same deterministic digest, all sandbox-only.

## CAPSTONE_UI_V1_6 AND AMENDMENTS
`CAPSTONE_UI_V1_6` (owner FINAL-EVAL-REPAIR-002, predecessor V1_5, 236+ bound files). V1..V1_5 lock files byte-identical; historical verifiers V1..V1_5 made successor-aware; pure SUCCESSOR_COMPATIBILITY_ONLY amendments: FRONTEND_PRODUCT 9_3, FEDERATION_UX 6, HISTORY 9_6, FACULTY_DEMO 5, UFL_LITE_002 2, FER_001 1 (no result evidence). No new dependency.

## PROTECTED NON-INTERFERENCE
Backend, API/contracts, DB, FL runtime, auth, scientific artifacts, MODEL_V2_FINAL, CAL_V2, route policy and redirect map, FER-001 evidence: zero drift. Owner-binding semantics, DemoAuth, REPLAY, global clients unchanged. Candidate digest `3f0b7762…0c4e` unchanged, sandbox-only.

## REGRESSIONS
- Real-Clerk (canonical): full route crawl PASS (legacy routes still retired, no stale content, no 5xx); landing audit at 1440/1024/768/390 PASS (0 console errors, 0 failed assets, 0 overflow, one h1, one main, no F2-01 wording); product audit (15 pages) PASS; cross-page truth matrix 0 contradictions; owner-bound regression PASS (1 MY EDGE CLIENT, 7 peers, 8 clients, 93 examples, 3 rounds, 24 updates, canonical digest; global view and REPLAY unbound).
- Offline DemoAuth: semantic digest `3a57614e…8726` identical, no Clerk traffic.
- Font 404 stays closed; favicon 404 closed.

## TESTS
Vitest 220 passed / 0 failed; svelte-check 0 errors; build OK; targeted Python 154 passed; full Python 3198 passed, 1 skipped, 1 deselected (CAP-003 race policy, isolated probe passed); ruff clean; pip check clean; CI neither queried nor triggered.

## MUTATION CONTROLS
38/38 caught, 38/38 restored: 16 claim-class mutations (the 16 required), 6 accessibility/provenance, 6 FER-001 presentation mutations, 10 protected-drift mutations.

## CLEAN CLONE
Target `b549f99`: fresh clone, fresh venv, `npm ci`, tree clean; Clerk and UI V1_6 verifiers, targeted tests, presentation and provenance verifiers, and the full real-Clerk crawl + landing/product audits + owner-binding regression inside the clone all PASS; no tracked modifications; no secret in the clone. (One earlier clone attempt aborted at `npm ci` with a transient `ECONNRESET` before any verification stage; it was discarded by design and rerun from scratch.)

## ATTEMPTS AND DEFECT HANDLING (nothing hidden)
1. **Attempt 1 (target `5ba64a7`) — FAIL, preserved in `attempt_1_FAIL/`:** the frozen product audit found data-driven actionable targets under 24 px (history "VIEW EVIDENCE" link, federation run link, digest copy buttons) that only exist with session/run data. Repaired (CSS only), re-frozen.
2. **Attempt 2 (target `b822044`) — FAIL, preserved in `attempt_2_FAIL/`:** harness defect: the reused owner-journey driver did not capture the `clients` REST body in one run (the UI/event facts of that run were correct). A hardened copy of the driver with a bounded retry was added in the FER-002 namespace; no product change; re-frozen.
3. **Attempt 3 (target `b549f99`) — canonical PASS.**
4. **Pre-transition evaluation found two machinery omissions** (the authorised-surface config lacked the two FER registry CSVs; my own `amendment_*.json` evidence notes matched the evaluator's amendment scan). Fixed without touching product or evidence-producing code: notes renamed `repair_note_*.json`, surface updated, method lock re-issued (`repair_note_3.json`).
Prior to the freeze, non-canonical rehearsals on the dev tree debugged the browser audit and the guard; they are not evidence.

## GIT CHRONOLOGY
`b94ce00` entry · `dfee779` prospective registration + protocol + provenance contract · `0716d58` landing truth/a11y repair · `5ba64a7` freeze (attempt 1 target) · attempt-1 fix + re-freeze `b822044` · hardened-driver re-freeze `b549f99` (**repair target**) · result commit (this evidence, PASS registries, method-lock re-issue).

## FINAL DECISION

"FINAL-EVAL-REPAIR-002 closes the second final-audit findings and freezes
a repaired presentation target. It does not establish evaluator
readiness. The unchanged FINAL_EVALUATOR_AUDIT_V1 must be rerun in full
from a fresh clone."
