# UFL-LITE-001 HANDOFF — Identity-bound federated participation contract + zero-drift freeze

## PHASE RESULT
UFL-LITE-001: **PASS** · UFLG0: **PASS** (43/43 frozen criteria, `uflg0_criteria.json`).

## ENTRY
Entry SHA `af1df702c1881ef4f0e52616680c6b2c54044eaf` == origin/main, tree clean. Historical tags unchanged: `capstone-release-v1` -> `3ad1b07…`, `capstone-clerk-connected-v1` -> `4cb20ec…` (verified at entry and final). CAP-001..011 and CLERK-LIVE-001 locks verified.

## CURRENT FL
8 clients `SIM_FL_SITE_00..07`; 3 rounds; 24 updates (8/8/8); FedAvg default (FedProx supported); SecAgg SHADOW (round-1 shadow, authoritative PLAIN, protected-aggregation-interface-only claim); canonical candidate digest `3f0b7762ae7e05f21eb1709521404ed4d7968cae34f89e1797a0cbabd47c70e4`.

## OWNER BINDING DESIGN
Owner-bound slot `SIM_FL_SITE_00`; peers `SIM_FL_SITE_01..07`; qualifying auth mode CLERK; qualifying run type LIVE_RUN; scope: run-scoped presentation only. DERIVED at presentation time (option A), NOT persisted: role = f(backend auth_provider, run.run_type, client_id), the owner being implied by run ownership scoping. Why: fewest changes (FLClientIdentity and FederationRun are frozen `extra="forbid"` contracts, so a serialised field would force contract/API amendments), restart-correct, replay-correct, no DB migration, cannot reach any digest. DEMO: no binding (offline demo preserved). REPLAY: no owner binding (historical engineering replay). `GET /federation/clients` is a GLOBAL cohort view and never shows a binding.

## SITE_00
Technical client id `SIM_FL_SITE_00`; participant `SIM_P000101`; edge node `VIRTUAL_EDGE_NODE_00`; session `SIM_S_FL_00_000001`; dataset SHA `fca4470983fef23dc5b90e760bd881325206c506e1518d266bba4fcd1bcdaf1a`; 93 local examples; buffer `LocalTrainingBufferV1`; client adapter `CapstoneFlClientAdapterV2`; data origin SYNTHETIC_ENGINEERING; label source simulation truth via `SimulationLabelAdapterV1` (equal to the frozen V2-FL-005 reference).

## REUSE
Unchanged: service/local_cohort/client/client_v2/update_bridge/replay/secagg_shadow, LocalTrainingBufferV1, label adapter, federation store, Coordinator + aggregation, FedAvg/FedProx, governance/registry, API V1_2/V1_3, Clerk auth (hash-frozen in the baseline). Future minimal insertion points: a pure frontend role helper, an optional display-only `ClientGrid` prop wired on the federation live/rounds pages, tests (plus the UI successor-lock governance for any frontend edit). New FL pipeline required: NO. New client class: NO. New buffer: NO. DB migration: NO (also no API field).

## CLAIM BOUNDARY
"MY EDGE CLIENT" = the signed-in owner of the run is shown the existing SIM_FL_SITE_00 as their edge participation client. Everything stays synthetic (dataset is an engineering fixture, not the user's physiology). Real monitoring data used for FL: NO. Personal model: NO. Personalized-FL claim: NO.

## NON-INTERFERENCE
MODEL_V2_FINAL, CAL_V2, FL_INIT_V2, FedAvg, FedProx, SecAgg, the canonical candidate digest and candidate sandbox-only status are all unchanged (hash-frozen reused modules, scientific artifacts and auth files; a completed 8-client SECAGG_SHADOW run reproduces 24 updates and the canonical digest; candidate ACCEPTED_TO_SANDBOX / IN_SANDBOX / production_deployed=false).

## PHASE-2 CHANGE SURFACE
Minimum backend change: none. Minimum API/view change: none. Minimum frontend change: pure helper + optional ClientGrid prop + two page wirings (CLERK && LIVE_RUN only). Tests: frontend unit tests + Python non-interference tests reusing this phase's baseline; new UI successor lock and generalised successor-aware UI verifiers (a governance cost of any frontend edit).

## TESTS
Targeted 96 passed (10 new contract/current-behaviour tests); full Python regression 3092 passed, 1 skipped, 1 deselected (inherited CAP-003 race; isolated probe passed); ruff clean; pip check clean; 15/15 static mutation controls caught and restored; CI queried NO; CI triggered NO.

## GIT
Entry `a6e0726`; control `b1c92a7`; freeze `d04f0c6`; contract-path correction `98b322c` (contract lives in `configs/ufl_lite/` because historical capstone guards forbid new files under `contracts/`); result commit = the commit carrying this file; no runtime change in any commit.

## FINAL DECISION
Can UFL-LITE-002 be implemented as a thin identity/presentation layer without changing FL computation? **YES.**
