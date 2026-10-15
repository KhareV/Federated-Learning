# UI tour evidence

Level: `VERIFIED_LOCAL_RENDER_REPLICA` (ESP32 emulator → local ingestion replica → isolated Atlas database; real Chrome; real Clerk test users). Physical ESP32 and deployed Render are **not** verified. All labels in recorded-hardware runs are synthetic.

* `unified_final/` — the acceptance tour against the final frontend build: 29 routes × 4 viewports (1440/1024/768/390 px), paired synthetic live run (`FL10RUN-…`), recorded-hardware run (`HDFLRUN-…`) and recorded historical evidence. `tour.json.tour.json` holds page text, headings, overflow, console/network, HTTP status and keyboard-focus data; `tour_shots/` is a **representative subset** of the screenshots (the full set was ~58 MB).
* `audit_interim/` — metrics JSON of the mid-pass audit tour (an earlier build); kept as the record of what the audit found, not as acceptance evidence.
* `../live_page_hardware/unified_final/` — lifecycle gate (leave Monitor for 10 s, return, Stop, History, federation) against the same build: PASS.
* `../live_page_hardware/unified_switch/` — real-browser run-switch gate (selector switches without reload, back/forward, reload): PASS, 9/9 steps.
* Superseded tours of the earlier pass were removed; two earlier failed attempts of this pass (a tooling syntax error in the in-page metrics expression, and a wrong back-button assumption in the switch scenario) are described in `docs/ui/UI_CONSISTENCY_AUDIT.md` §4 and were corrected in the tooling, not in the product.
