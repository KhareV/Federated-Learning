# NHM-UNIFIED-LIVE-FEDERATION-STUDIO-001 — dependency audit (BEFORE any change)

**Audited tree:** `main` @ `06bd9a0` (clean), 7 commits ahead of `origin/main` = `274323730d1c7355f688ad4c9ff01ecbfb746501` (`git rev-list --left-right --count origin/main...HEAD` → `0 7`). The FL10 baseline `e129a76` and the Clerk-default launch commit `06bd9a0` are local only. Nothing in this document was produced by running a new experiment.

Predecessor locks that bind files this work will touch: `CAPSTONE_UI_V1…V1_9`, `CAPSTONE_FEDERATION_PROTOCOL_V1.amendment_3`, `UFL_LITE_002_PROTOCOL_V1` (+amendment 3), `NHM_RESEARCH_OBSERVATORY_V1`, `NHM_OBS_DIAG_001`, `NHM_FINAL_SHOWCASE_001`, `NHM_FL10_001`. They are never edited; changed files are re-pinned only by a new additive successor (the `NHM_FL10_001` precedent: `repins_predecessor_files` + `scripts/fl10_successor_compat.py`).

## 1. Two engines, two contracts

| | 3-round (product) | 10-round (FL10) |
|---|---|---|
| Entry | `POST /product/v1/federation/runs` → `…/{id}/start`; `FederationService` (`product/federation/service.py`) | `POST /product/v1/observatory/fl10/runs` `{mode: "A"|"B"}`; thread job in `api/observatory_fl10.py` → `fl10.runner.run_training` |
| Round math | `Coordinator` + client adapter V2 | the **same** `Coordinator` + `train_local_epoch_v2` (no second FedAvg) |
| Contract guard | `check_public_request`, `planned_rounds == 3` (frozen) | owner-scoped, opt-in, one job at a time, no registry candidate |
| Events | 12 `PRODUCT_LIVE_EVENT_V1` federation kinds on `FederationEventJournal`, WS `/federation/runs/{id}/live`, replay from seq 0 | free-form `progress` dicts (ROUND_OPENED, CLIENT_TRAINING_STARTED/FINISHED, ROUND_COMMITTED) — **not** product events |
| Committed states | `FederationArtifactStore.write_checkpoint` per round | `states/R00..R10.bin` atomically, digest-verified by `load_state` |
| Evaluation | none per round | `fl10.evaluate.evaluate_run` **only after all 10 rounds** (and requires `rounds_committed == 10`) |
| Candidate | `CAPSTONE_FL_CANDIDATE_dddd` in sandbox registry | `FL10_CANDIDATE_<job>`; **not** registered; event schema pattern would reject it |

Gaps this work must close without touching either contract: (1) 10-round has no product-event stream; (2) neither engine has a per-round evaluation; (3) candidate ids differ.

## 2. Frontend routes

`OLD PAGE → UNIQUE FEATURES → NEW LOCATION → VERIFIED PARITY → DEPENDENCIES → SAFE TO RETIRE?` (parity column is "pending" until Phase 8).

| Route | Unique functionality | New location | Parity | Dependencies | Retire? |
|---|---|---|---|---|---|
| `/app/federation` | heading, pipeline, lanes, `RunConfigForm`, run list, client prep, backend overview tiles | same route (adds 3/10 selector) | pending | `useFederation`, ProductShell nav, `routes/app/+page.svelte` CTA, `route-policy.ts` aliases | **No – entry point** |
| `/app/federation/live` | the original live visualization (ClientGrid, ★ owner binding, ProcessStepper, RoundProgress, ModelStateTransition, CandidateLifecycle, Timeline, SecAgg panel) | same route, shared by 3 and 10 | pending | `RunList` deep link `?run=`, ProductShell "Live", `useRunParam`, `rounds`/`privacy` pages | **No – primary** |
| `/app/federation/rounds` | per-round state timeline + lineage list | stays (distinct) | n/a | `bootRun`, RunSelector | No |
| `/app/federation/clients` | eight client identity cards | stays | n/a | `fed.loadClients` | No |
| `/app/federation/privacy` | aggregation/SecAgg explanation per run | stays | n/a | `bootRun` | No |
| `/app/observatory/fl10` | overview cards, R3-vs-R10 headline, 8 tabs, 20 figures, 12 tables, export controls, recorded **and** live start (Mode A/B), 3-round baseline panel | Studio "Analysis" tabs + run selector (recorded runs become selectable historical runs) | pending | `Fl10Chart`, `Fl10Table`, `observatory/fl10.ts` parsers, `api.fl10*`, `tests/test_fl10_*`, `NHM_FL10_001.lock.json`, Observatory home link | Decide in Phase 9 (lock-bound) |
| `/app/observatory/storyboard` | 8 guided steps, lane labels, SITE_00 live-link start/status, parity list | Studio guided strip + source-mode option | pending | `observatoryLiveLinkStart/Status`, `observatoryShowcase`, links from outcomes/federation | Decide in Phase 9 |
| `/app/observatory/outcomes` | frozen scientific comparisons (V1/V2, FedAvg/FedProx, IID/non-IID, INTERNAL_TEST, INCART, CIs, centralized vs federated), synthetic eval panel | — | n/a | `observatoryShowcase`, exports | **PROTECTED** |
| `/app/observatory/federation` | cohort, source windows, fault schedules, eligibility, labels, per-round contributions, FedAvg arithmetic, per-batch, lineage | stays; duplicates (lineage) may link to Studio | n/a | `observatoryCohort`, `observatoryRunContributions`, `[client_id]` deep link | Keep |
| `/app/observatory/federation/[client_id]` | window-level signal-stage inspection | stays | n/a | `observatoryFlClientWindow` | **PROTECTED** |
| `/app/observatory/federation-replay` | event-journal replay with step controls (`buildSnapshots`) over ClientGrid/ProcessStepper/RoundProgress/CandidateLifecycle | **reuse `buildSnapshots` for the Studio round explorer**; page itself stays | pending | `federationSocketUrl`, `LiveSocket`, `replay.svelte` | Keep (distinct: event stepping) |
| `/app/observatory/evidence`, `/research`, `/model`, `/provenance`, `/replay`, `/scenarios`, `/tour` | frozen scientific evidence, signal/model inspection, tour | — | n/a | various `observatory*` API | Keep (default) |

### Cross-route links to the above (from `grep`)
`ProductShell.svelte` (nav: Federation → Clients/Rounds/Live/Privacy), `routes/app/+page.svelte` (CTA → `/app/federation`), `RunList.svelte` (→ `/live?run=`), `observatory/+page.svelte` (links to federation, tour, scenarios, fl10), `research/fl/+page.svelte` (bridge text), `storyboard`/`outcomes`/`federation`/`model`/`tour` internal cross-links, `route-policy.ts` (`/fl/overview|clients|rounds|privacy|aggregation|personal-models` → federation routes).

### API consumers
Frontend client `lib/product/api.ts`: `federation*`, `createFederationRun`, `startFederationRun`, `federationSocketUrl`, `observatoryCohort|RunContributions|FlClientWindow|Showcase|LiveLink*`, `fl10Recorded|RecordedBundle|Start|Status|JobBundle|ExportFile`. WebSocket: only `/federation/runs/{id}/live` (store + federation-replay).

### Shared stores / parsers
`FederationStore` (`state.svelte.ts`, singleton via `useFederation`), `FederationLiveModel` (generic in round count — verified), `parseFederationEvent` (strict; `candidate_id` must match `CAPSTONE_FL_CANDIDATE_\d{4}`), `observatory/fl10.ts` (`parseFl10*`), `observatory/export.ts` (`downloadExport`).

### Tests that reference these routes/APIs
Frontend: `product/federation/__tests__/{components,participation,store-api,static-audit}.test.ts`, `product/__tests__/{components,route-policy}.test.ts`, `product/observatory/__tests__/fl10.test.ts`, `__tests__/support.ts`. Backend: `tests/test_capstone_{contracts,federation_ui,federation_isolation}.py`, `tests/test_fl10_{api,training,evaluation,successor}.py`, `tests/test_observatory_pipeline.py`, `tests/test_final_eval_repair_presentation.py`.

### Frozen artifact / lock bindings
UI locks `CAPSTONE_UI_V1…V1_9`, UX amendments, `NHM_RESEARCH_OBSERVATORY_V1`, `NHM_OBS_DIAG_001`, `NHM_FINAL_SHOWCASE_001` and `NHM_FL10_001` hash frontend files and `contracts/capstone/product_api_v{1,2}.json`. Any edit to `federation/*` pages, `api.ts`, `api/product_app_observatory_v1.py` or those contracts needs successor re-pinning.

### Potential redirect conflicts
`route-policy.ts` already aliases legacy `/fl/*` to the federation routes (kept). A redirect for `/app/observatory/fl10` would break `tests/test_fl10_api.py` expectations and the FL10 lock's browser evidence unless done as an additive redirect; the page is therefore only retired from **navigation**, not deleted, unless Phase 9 proves safe.

### Duplicated vs. only-similar
- Duplicated: FL10 page's live job controls vs the Studio's start; storyboard's SITE_00 start vs the Studio source-mode option; lineage list in `observatory/federation` vs Studio ModelStateTransition.
- Similar but **different scientific meaning (do not merge):** `outcomes`/`evidence` (frozen real-ECG FL research, lane B) vs Studio (synthetic engineering FL, lane C); recorded FL10 R0–R10 (frozen holdout evidence) vs a new run's live metrics.

## 3. Reusable components (inspected)
`ClientGrid`, `ClientDetailPanel`, `RunConfigForm`, `RoundProgress`, `ProcessStepper`, `FederationTimeline`, `ModelStateTransition`, `CandidateLifecycle`, `FederationPipeline`, `RunSelector`, `TechnicalEvidence`, `LiveVsReplay`, `DigestText`, `FederationBanner`, `Panel`, `MetricTile`; FL10: `Fl10Chart`, `Fl10Table`; `SignalStageChart`; `downloadExport`.

## 4. Backend facts that shape the design
- `FederationEventJournal` + `FederationEmitter` are reusable as-is for any run id; the 10-round job can emit the **same 12 typed events** (no `candidate.*` – id pattern/registry are 3-round-only; candidate is surfaced through the additive studio API).
- 3-round checkpoints (`write_checkpoint`) and a post-checkpoint `_hook` already exist (precedent: `install_acceptance_capture`), so an observer can read committed states without altering the engine.
- FL10 evaluator primitives (`evaluate_states`, `metrics.full_metrics`, `participant_metrics`, `base_metrics.curves`, `logits_for`) are state-wise and reusable per round; only `evaluate_run` is whole-run.
- The FL10 holdout (16 participants, 1 446 windows) and the 8-participant showcase holdout are **already exposed**: every live metric must carry `REUSED SYNTHETIC DIAGNOSTIC EVALUATION — NOT A NEW UNTOUCHED FINAL TEST`.

## 5. Known pre-existing issue (reported separately, not fixed here)
The master prompt names a known pre-existing monitoring race in the backend suite. It is reported separately when observed and not modified here.

## 6. Decisions recorded before implementation
1. New additive backend module and route family `…/studio/*`; the frozen 3-round route/contract and the FL10 job routes stay untouched.
2. 10-round runs publish genuine `PRODUCT_LIVE_EVENT_V1` events (federation.status, round.status, client.*, aggregation.status, federation.completed/error) from the FL10 `progress` callback into a `FederationEventJournal`; the existing `FederationLiveModel` consumes them unmodified.
3. A run-scoped **evaluation observer** (one serialized worker per run) scores each committed, digest-verified state on the frozen holdout and serves results over an authenticated REST endpoint with ETag-style revision; the UI polls only while evaluations are pending.
4. No deletion before Phase 9/10.
