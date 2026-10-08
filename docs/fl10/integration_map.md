# NHM-FL10-001 — integration map (written before any result)

**Baseline:** `2743237` (= `origin/main`), clean tree. Predecessor lock `NHM_FINAL_SHOWCASE_001` (sha256 recorded in `reports/fl10/baseline_hashes.json`). The `NHM_OBS_DIAG_001` in-place re-freeze incident is not repeated: **no accepted lock is edited**; a new lock chains to the exact predecessor bytes.

## Reused unchanged
| Need | Existing component |
|---|---|
| Local training | `federated.model_v2_fl.train_local_epoch_v2` (frozen AdamW/seeds/pos_weight constants from `federated.wearable_fl_runner_v1`) |
| Round protocol, validation, FedAvg | `federated.wearable_fl_system_v1.Coordinator` (-> `aggregate_weighted_deltas`), `make_envelope`, `extract_meta`, `scan_forbidden` |
| Cohort and labels | `build_cohort`, `SyntheticEventLabelProvider`, `build_local_dataset` |
| Per-batch diagnostics | `api.observatory_batch_capture.BatchCapture` (read-only hooks, parity-verified in OBS-DIAG-001) |
| Metrics | `final_showcase.metrics` (AUPRC, AUROC, confusion, BCE, curves, macro-F1) |
| Live SITE_00 | `final_showcase.live_link` (monitor_site00, dataset_from_windows, parity) + `final_showcase.link_trace` |
| Frontend | existing Svelte shell, Observatory routes, `downloadExport` |

## Added (all new files)
`fl10/` (holdout, metrics extensions, runner, evaluate, figures, bundle), `api/observatory_fl10.py` (opt-in routes), `scripts/*fl10*`, `configs/fl10`, `docs/fl10`, `reports/fl10`, `artifacts/fl10`, one Svelte route family, tests.

## Why a separate runner
The public 3-round federation contract (`check_public_request`, `planned_rounds == 3`) is frozen; it is neither changed nor bypassed. The FL10 runner drives the **same Coordinator and trainer** for ten rounds in a separately named, owner-scoped, opt-in job. It does not register a candidate in the product registry and cannot promote or deploy.

## Small edits to existing files (to be listed in the lock)
Route registration in `api/product_app_observatory_v1.py`, client methods in `frontend/src/lib/product/api.ts` (+ test fakes), one link on the Observatory home page, route-policy entries; successor-aware lock verifiers/resolver. Any file bound by an earlier lock that changes is re-pinned **only** through the new lock (additive), never by editing an earlier lock.
