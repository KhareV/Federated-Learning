# CAPSTONE_FEDERATION_FRONTEND_V1 (CAP-008)

The federation dashboard and model-governance UX inside the EXISTING SvelteKit frontend (successor lock `CAPSTONE_UI_V1_1`; `CAPSTONE_UI_V1` is preserved as the historical predecessor). No backend, FL, scientific or monitoring change.

* **Pages** (`frontend/src/routes/app/`): `federation` (overview + run configuration), `federation/clients`, `federation/rounds`, `federation/live`, `federation/privacy`, `models`. `/app` now reads the real federation status. `research/*` stay CAP-009 placeholders.
* **Product client** (`CAPSTONE_FEDERATION_PRODUCT_CLIENT_V1`, `lib/product/api.ts` + `federation/types.ts`): the nine CAP-007 methods; `createFederationRun` sends exactly `run_type, algorithm, secagg_mode, planned_rounds=3, scenario_id=FL_SINGLE_RUN`.
* **Events + live model** (`CAPSTONE_FEDERATION_LIVE_MODEL_V1`, `federation/events.ts`, `live-model.ts`): strict parser for exactly the 12 federation kinds; strict per-run sequence; reconnect = reset then rebuild from sequence 0; progress is only the real 0/1 milestones; REPLAY candidate events are historical.
* **Store** (`CAPSTONE_FEDERATION_STORE_UI_V1`, `federation/state.svelte.ts`): separate from the monitoring store; create -> WebSocket -> start; the dashboard is an observer (closing it never stops a run).
* **Governance UI** (`CAPSTONE_MODEL_GOVERNANCE_UI_V1`, `CandidateCard.svelte`): two separate model namespaces; ACCEPTED TO ENGINEERING SANDBOX REGISTRY is never deployment; `production_deployed = FALSE` always shown; the five checks are structural only; no deploy/promote/default/inference control exists.
* **Claims:** engineering federation demo, simulated logical clients on one laptop, round-1 SecAgg+ shadow (authoritative aggregation PLAIN, no DP/anonymity claim), not clinical, not deployed.
