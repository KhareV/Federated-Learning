# Residual repair audit (non-hardware): direct loads, keyboard journeys, semantics, console/network

Scope: everything left open by the unified-UI phase that is **not** hardware. No hardware functionality was changed, no hardware experiment was run,
and no hardware dependency was added: the audit stack ran with the MongoDB hardware source **disabled** and nothing was seeded.
Predecessor: `NHM_HARDWARE_LIVE_UNIFIED_001` @ `21a5fad`. Successor lock: `artifacts/ui/NHM_UI_RESIDUAL_REPAIR_001.lock.json`.
Generated numbers: [`A11Y_MEASUREMENTS.md`](A11Y_MEASUREMENTS.md). Raw data: `reports/ui/a11y/{baseline,final}/a11y.json` (and `probe1_unsettled`, the first, superseded probe kept as the record of the smooth-scroll artefact), `reports/ui/direct_routes_{before.txt,final.json}`.
The attached `NHM_Post_Unified_UI_Residual_Repair_Execution_Prompt.md` was **not present on disk**; this work followed the scope stated in the task message.

## 1. Defect ledger

| # | Area | Observed (before) | Root cause | Fix | Evidence | Status |
|---|---|---|---|---|---|---|
| R1 | `/app/history/<id>`, `/app/observatory/federation/<client>` direct load / reload | HTTP **404** (working SPA shell) on every direct load of a parameterised route | root layout `prerender = true` makes SvelteKit **drop un-prerendered dynamic routes from the server manifest**, so the request matched no route | `export const prerender = 'auto'` in each dynamic route's `+page.ts` (keeps the route in the manifest; SPA shell served with 200). The `[...path]` catch-all still answers unknown paths with 404 | before: `reports/ui/direct_routes_before.txt` (404 for both routes); after: `scripts.check_direct_routes` 10/10 → `reports/ui/direct_routes_final.json`; `direct-routes.test.ts`; every route's `httpStatus` in the final a11y audit is 200 | **fixed** |
| R2 | Keyboard, phone width (≤ 860 px), every page | 11–15 focus stops per page were links of the **closed, off-canvas navigation drawer** (invisible; screen readers also read them) | drawer only translated off-screen | closed drawer is `visibility: hidden` (delayed so the slide animation still plays); opening moves focus into the navigation; navigating closes it; Esc still restores focus | phone: stops outside the viewport 230 → 0 | **fixed** |
| R3 | Keyboard, Live page and Observatory charts | every plotted point/bar was its own tab stop (dozens per chart; ≥ 90 stops in the first screens) | `tabindex="0"` on each SVG mark | chart keyboard model: **one tab stop per chart**, arrow keys / Home / End move between points (roving tabindex), spoken instruction, chart is a named `role="group"` | `chart-nav.test.ts`; audit: 4 charts → 4 tab stops, 129 points reachable by arrows | **fixed** |
| R4 | Keyboard, all `/app` pages | a focused control could be scrolled under the 58 px sticky header | no scroll padding | `scroll-padding-top` (WCAG 2.4.11) | obscured stops → 0 | **fixed** |
| R5 | Observatory "off-screen focus" | 8–13 stops per page reported outside the viewport | **measurement artefact**: `html` uses smooth scrolling and the probe sampled mid-animation. Re-measured after the scroll settles: 0 on desktop for every Observatory page | probe corrected (settled scroll) | `reports/ui/a11y/probe1_unsettled` (44 stops reported outside on Observatory pages, desktop) vs `baseline` (0) | **not a product defect on desktop; the real defect was R2 at phone width** |
| R6 | Heading structure | h2 → h4 on Live/replay panels (`LiveVsReplay`, `RoundProgress`), h1 → h3 on Research ML | levels hard-coded in components | `LiveVsReplay` h4 → h3; `RoundProgress` keeps its element and CSS and states `aria-level="3"` (pinned, no visual change); Research ML gets its missing h2 | skips 6 → 0 | **fixed** |
| R7 | Table semantics (Observatory evidence/outcomes/model/federation, studio comparison/bridge/client history, chart data table) | 20 tables with no name; 49 header cells without `scope` | missing caption/`aria-label`/scope | named every table; `scope="col"`; hidden "Aspect" label for the empty corner cell | tables unnamed 20 → 0, `th` without scope 49 → 0 | **fixed** (the hardware window table in `HardwareMonitor` was deliberately not touched) |
| R8 | Console/network, History with the hardware source disabled | `GET /product/v1/hardware/sessions` → 404 (console error on every visit) | History always asked for the hardware routes | asks only when the backend capability flag says the hardware source exists | failed requests on `/app/history` 1 → 0 | **fixed** |
| R9 | Console/network | Clerk "development keys" warning on every route | the app uses a Clerk **development** instance | none (environment, not application) | `A11Y_MEASUREMENTS.md` excludes it explicitly | **explained / left** |
| R10 | Console/network | `404 /product/v1/sessions/NO-SUCH-SESSION` when opening an unknown session id | correct backend answer to an unknown id; the page shows its error state | none | audit route `/app/history/NO-SUCH-SESSION` | **intentional** |
| R11 | Document titles | `/app/observatory/fl10` and Live share a title | `fl10` is a redirect shim to the Live page | none | – | **intentional** |

## 2. Preserved
Synthetic and recorded-hardware Live design and behaviour, hardware lifecycle and ingestion, scientific/backend code, historical locks and frozen artifacts,
the accepted `NHM_HARDWARE_LIVE_UNIFIED_001` successor (not edited; this work is a new additive successor).

## 3. Remaining limitations (not resolved)
* **Dense Live page:** about 115–130 tab stops end to end (legend toggles, view switches, export buttons, tabs). Chart points no longer add to it and the page has jump links, but a keyboard user still tabs through many real controls.
* **Small text:** HTML text below 10.5 px remains in frozen original components (see the generated table); chart axis labels are SVG text and scale with the chart.
* **Screen readers:** no screen-reader (NVDA/VoiceOver/JAWS) session was run; semantics were verified structurally (landmarks, names, levels, scopes, live regions) and by keyboard, not by listening.
* **Hosting:** the 404 fix is verified on `vite preview` (the launcher's frontend server). A different static host must also serve the SPA fallback with 200 for dynamic paths; that cannot be verified from this repository.
* **Static build warning:** the adapter's `fallback: 'index.html'` overwrites the prerendered root `index.html`; the landing page still renders (client-side) and was not changed.
* **Not verified:** physical ESP32, deployed Render (out of scope for this phase by instruction).
