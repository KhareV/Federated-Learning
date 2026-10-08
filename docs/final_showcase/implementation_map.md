# NHM-FINAL-SHOWCASE-001 — implementation map and preservation inventory

**Starting reference.** The prompt names `7d8a90a` as the accepted starting commit. The actual `HEAD` at start was `aa36f53`, two later commits of this same line of work (Clerk-launcher integrity fix; console FL log lines), both already pushed. Both only touched Observatory/launcher files; the starting scientific, federation and lock surfaces are identical. The protected-surface diff in the verifier is taken against `aa36f53`.

## What was built (all additive)
| Workstream | New files | Reused unchanged |
|---|---|---|
| A live-monitored SITE_00 | `final_showcase/live_link.py`, `api/observatory_showcase.py` (`register_live_link`), `scripts/run_live_link.py` | `SimulatedWearableSource`, `VirtualEdgeNode`, `MonitoringService`/`MonitoringCoordinator`, `WearableStreamRuntime`, `is_trainable`, `normalize_windows`, `dataset_semantic_sha`, `SimulationLabelAdapterV1`, `LocalTrainingBufferV1`, `FederationService` via its existing `cohort_provider` seam |
| B synthetic evaluation | `final_showcase/{holdout,metrics,evaluate}.py`, `configs/final_showcase/*`, `scripts/{freeze_synth_fl_eval_protocol,run_synth_fl_eval}.py` | `simulation.fl_cohort_v1` generator, `build_local_dataset`, checkpoints and candidate store, `evaluation.metrics` (cross-check) |
| C scientific outcomes | `final_showcase/research.py`, route `/showcase/bundle`, `/app/observatory/outcomes` | `product.observatory.evidence` (hash-verified frozen artifacts), frozen `round_log.csv` files |
| D exports | `final_showcase/figures.py` (`ResearchFigure`, `ResearchComparison`, `ResearchMetricTable`) | the single bundle |
| E storyboard | `/app/observatory/storyboard`, `frontend/src/lib/product/observatory/showcase.ts` | — |
| F/G | `docs/final_showcase/*`, `scripts/build_final_showcase_docs.py`, `reports/final_showcase/recorded_run` | — |

## Small edits to existing files (listed so nothing is hidden)
- `api/product_app_observatory_v1.py`: wraps the cohort provider in `LiveLinkCohortProvider` (disarmed = canonical `get_cohort`, tested) and registers the new routes.
- `frontend/src/lib/product/api.ts`, `__tests__/support.ts`: three typed client methods and fakes; Observatory home page: two links.
- Historical locks are **not** edited; successor-compatibility amendments are added the same way as for the Observatory (`scripts/observatory_amend.py`).

## Preservation inventory (verified, not assumed)
Unchanged vs `aa36f53`: `federated/`, `product/federation`, `product/monitoring`, `product/models`, `simulation/`, `evaluation/`, `preprocessing/`, `src/`, `models/`, `checkpoints/`, `capstone_persistence/`, `api/product_app_v1_{1,2,3}.py`, `api/runtime_v2.py`, `deployment/`, `fusion/`, all frozen reports under `reports/model_v2`, `MODEL_V2_FINAL`, `FL_INIT_V2`, `CAL_V2`, `PREPROC_V1`, AAMI-SVF labels/splits, canonical run and candidate `3f0b7762…`. `scripts/verify_final_showcase.py` re-checks the protected paths and the canonical digest.

## Stop rule
Workstream A did **not** hit the stop rule: captured windows reach the FL boundary through the existing `cohort_provider` seam without modifying frozen code. One disclosed limitation: the monitored session is hosted by the Observatory with in-memory session/device entries (the frozen scenario registry would reject a persisted product session with an unknown scenario id on restart), so it is not written to SQLite history.

## Bibliography status
The bibliography is **unverified** and the manuscript is **not reference-complete**: every citation slot is marked `REFERENCE_REQUIRED` and no reference was invented or checked.
