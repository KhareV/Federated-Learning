# UI consistency audit — whole site, synthetic and recorded-hardware workflows

Method and evidence: real Chrome + real Clerk test users + ESP32 emulator → local ingestion replica → isolated Atlas database
(`VERIFIED_LOCAL_RENDER_REPLICA`; never `health_db`). Routes were **discovered from the file system** (`frontend/src/routes/app/**/+page.svelte`:
27 static routes) plus the dynamic ones exercised with real data (`/app/history/<session>`, `/app/federation/live?run=<id>` for a
synthetic live run, a recorded-hardware run and recorded historical evidence). Each route was measured at 1440, 1024, 768 and 390 px.
Machine-readable: `reports/hardware/ui_tour/unified_final/tour.json.tour.json` (page text, headings, overflow, console, network, keyboard).
Generated tables: [`UI_AUDIT_MEASUREMENTS.md`](UI_AUDIT_MEASUREMENTS.md). Contract: [`SOURCE_STATE_CONTRACT.md`](SOURCE_STATE_CONTRACT.md).
The Unified UI Consistency Implementation Blueprint named in the brief was **not present on disk**; this ledger is derived from code and browser only.

## 1. Defect ledger

Class: (1) factual/state, (2) stale-state/cross-route, (3) accessibility/responsive, (4) density, (5) intentional difference, (6) out of scope / residual.

| # | Route(s) / mode | Class | Sev | Observed → expected | Source of truth / root cause | Fix | Test / evidence | Status |
|---|---|---|---|---|---|---|---|---|
| S1 | Live, any run with `SECAGG_SHADOW` on the extended engine | 1 | High | shadow status never shown ("NOT YET REPORTED") → `SHADOW_RUNNING` then `SHADOW_VERIFIED` | `Fl10EventTranslator` emitted `SecAggStatus.VERIFIED`, which does not exist | emit `SHADOW_RUNNING`/`SHADOW_VERIFIED` | `tests/test_hardware_studio_run.py::…journal…`; browser `secagg` field | fixed |
| S2 | Live, hardware run | 1 | High | synthetic peer/owner wording, `SIM_FL_SITE_xx` ids → "your recorded windows", `RECORDED_DEMO_CLIENT_xx`, no owner/peers | UI hard-coded the synthetic cohort | typed run context + `dataSource` provision | `run-context.test.ts`, `data-source.test.ts`; paired browser text | fixed |
| S3 | Live, hardware run | 1 | High | "REUSED SYNTHETIC DIAGNOSTIC EVALUATION", "16 participants" → hardware evaluation wording | synthetic-cohort constants in `evaluation_summary` and two components | per-run labels from the bundle | `test_hardware_studio_run.py`; browser text | fixed |
| S4 | Federation (start) | 1 | Med | "synthetic clients/lane" copy while *Recorded hardware* chosen → follows the chosen source | static copy | source-aware pipeline, lanes, banner, clients panel | `data-source.test.ts` | fixed |
| S5 | Overview, System | 1 | Med | no mention of the MongoDB hardware source; "SIMULATED_ONLY / physical hardware: NO" read as "no hardware path" → states the optional telemetry source and what it is not | static copy | clarified | page text in tour | fixed |
| S6 | Federation runs list / selectors, Rounds, Privacy, Clients | 1 | Med | no provenance on runs; generic "10-ROUND / RECORDED RUN"; clients page silent about hardware clients → provenance badge, run-scoped copy, scope note | descriptor not surfaced | `runBadges`, copy | `RunList`/`RunSelector` text in tour | fixed |
| X1 | any run switch | 2 | High | previous run's descriptor/journal visible while the next loads; a late response could overwrite the current run → cleared at once, stale responses discarded | `FederationStore.loadRun` had no generation guard | selection transaction + sequence | `run-switch.test.ts`; browser `reports/hardware/live_page_hardware/unified_switch/run_switch_verdict.json` (9/9 steps) | fixed |
| X2 | Rounds / Live / Privacy opened without `?run=` | 2 | Med | selection lost → re-attaches to the run selected in the session and writes it to the URL | `bootRun` ignored session state | persistence | `run-persistence.test.ts` | fixed |
| X3 | Live, unloadable run id | 2 | Med | looked like the empty "Pick a run" page → explicit error (with retry) vs loading vs empty | single fallback branch | three states | `components.test.ts` | fixed |
| X4 | History → Federation | 2 | Low | "Use in FL" opened the generic form → opens Recorded hardware with that session selected | link had no context | deep link `?source=hardware&session=` | `hardware-starter.test.ts` | fixed |
| A1 | Federation start form | 3 | High | "Fixed configuration" tiles drawn over the form → in flow | Tailwind global `.fixed{position:fixed}` collided with a component class | class renamed / neutralised | `reports/.../form_*.png` | fixed |
| A2 | History (hardware table), 1440 px | 3 | High | "View evidence" clipped off-screen → both actions always visible | 10 nowrap columns | 7 columns, stacked cells | tour screenshots, `UI_AUDIT_MEASUREMENTS.md` | fixed |
| A3 | site-wide | 3 | Med | 7–10 px micro-labels → ≥10.5/11 px in shared and page components; frozen components lifted from the page | per-component sizes | see §3 | measurements | partly fixed (see R2) |
| A4 | all routes | 3 | – | keyboard, landmarks, skip link, focus ring, reduced motion verified | – | none needed | `keyboard` block per route; 0 stops without a focus ring | verified |
| D1 | History detail (hardware) | 4 | High | 8,366 words → 91 primary words (summary tiles, collapsed list, next action) | full reading dump | progressive disclosure | tour | fixed |
| D2 | Federation | 4 | Med | two long explainers before the Start card → collapsed (kept in the DOM) | – | `<details>` | tour | fixed |
| D3 | Live | 4 | Med | no first-screen summary → "at a glance" (source, status, latest *labelled* result, jump links, N/A reasons); timeline collapsed | – | `RunAtAGlance`, anchors | tour, `components.test.ts` | fixed |
| D4 | Model, Storyboard | 4 | Low | ≥45-word paragraphs → collapsed behind a plain label | – | `ReadMore` | measurements | fixed |
| I1 | Live (hardware) | 5 | – | generalisation, paired intervals, frozen V2 reference shown as **Not applicable** with the reason | task has no unseen cohort / independent clusters / reference | context capabilities | `run-context.test.ts` | intentional |
| I2 | Live (synthetic) | 5 | – | canonical design unchanged; `ClientGrid`/`ClientDetailPanel` gained one optional prop, digest-pinned | – | preservation test allowance | `preservation.test.ts` | intentional |
| R1 | `/app/history/<id>` direct HTTP | 6 | Low | `vite preview` answers the SPA shell with **HTTP 404** (page renders, reload works) | dynamic route is not prerendered; the hosting layer decides the fallback status | **not changed** (launcher/hosting) | `httpStatus` per route in the tour | residual |
| R2 | Live and Observatory pages | 6 | Low | still long (≈6.5–8.1 k px) and ~80 small-text elements (mostly SVG chart text and tables in frozen components) | frozen original components | mitigated from the page only | measurements | residual |
| R3 | physical ESP32, deployed Render | 6 | – | not verified | no device / no deploy | – | – | open |

## 2. Preserved on purpose
Monitoring lifecycle (leaving Monitor never stops a session; catch-up on return; no background collector), experimental-V2 "not valid" boundary,
hardware lock/successor chain, FL Studio semantics (FedAvg/FedProx, plain vs round-1 SecAgg+ shadow, warm start, label seed), all historical
frozen artifacts, the synthetic Live design.

## 3. Before / after (desktop, from the tour)
First pass baseline (earlier in this work): Federation 567 words / 66 small-text elements; hardware Live 1,864 words / 219 small-text / 6,658 px; hardware
session detail 8,366 words. After this pass: see the generated table. Honest note: the Live page gained a ~25-word summary, so its word count did
not fall; its small-text count did (219 → 79), the timeline is collapsed by default and its first screen now answers "what is this / how far /
what result / where next".

## 4. Verification honesty notes
* Two of my own verification attempts failed and were fixed in the **tooling**, not the product: (a) a template-literal escape error made the in-page metrics expression invalid, so one whole tour produced 112 tool errors (now covered by a test that evaluates the expression against a DOM); (b) the first run-switch scenario assumed Back steps through runs, but run selection deliberately uses `replaceState`, so Back leaves the page (the scenario now asserts that).
* Keyboard probe: 25 Tab presses per route at desktop and phone width; every focus stop had a visible indicator (0 without). "Offscreen" focus stops were observed on dense pages and were not investigated further; treat as a manual-review item.
* No screen-reader run was performed.
* Direct HTTP load of `/app/history/<id>` returns 404 with a working SPA shell from `vite preview`; it was measured on every run and left unchanged (hosting layer).
