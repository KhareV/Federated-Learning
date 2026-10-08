# NHM-FL10-001 local runbook

This is an opt-in synthetic engineering experiment. It does not replace the three-round product federation or released monitoring model. Never point a demo at the repository-default SQLite database; use an isolated workspace. Do not change the frozen protocol or run a fresh ECG scientific experiment.

## Inspect the committed evidence

```sh
git rev-parse HEAD
.venv-t032/bin/python -m pytest -q tests/test_fl10_training.py tests/test_fl10_evaluation.py tests/test_fl10_api.py
PYTHONPATH=src:. .venv-t032/bin/python -m fl10.figures --run reports/fl10/runs/modeA --eval reports/fl10/eval/modeA --out /tmp/nhm-fl10-export-check
```

The last command regenerates presentation files from the recorded run into a **new** temporary path. Compare its export manifest and files to the committed publication manifest before claiming byte-level reproducibility; timestamps/renderer versions may affect images even when numerical CSV values agree. The 28 targeted tests include full owner-scoped opt-in API execution and recorded-prediction reconciliation. They do not constitute clinical validation.

## Execute a new, separately named run

Use a fresh output directory. `run_fl10` refuses to overwrite a non-empty run directory; a failed run is preserved as failed evidence and must restart from R0.

```sh
PYTHONPATH=src:. .venv-t032/bin/python -m scripts.run_fl10 --mode A --run-id FL10_LOCAL_A_01 --out /tmp/nhm-fl10-local-A-01
PYTHONPATH=src:. .venv-t032/bin/python -m scripts.run_fl10 --mode B --run-id FL10_LOCAL_B_01 --out /tmp/nhm-fl10-local-B-01
```

Mode A uses the canonical eight-client synthetic cohort and must match the frozen R0–R3 prefix before continuing. Mode B performs one actual simulated monitoring session for SITE_00, traces the optimizer inputs to the monitored windows, and reuses that buffer across ten rounds. Both modes use the existing trainer and coordinator. New runs do not inherit a new independent-evaluation claim: the 16-participant evaluation holdout has now been examined. A future independently governed evaluation needs a different predeclared holdout.

## Application demonstration

The route is `/app/observatory/fl10`. The default selection is **RECORDED VERIFIED RUN**, with separate Mode A and Mode B selections. Starting a new run is opt-in and owner-scoped; a full ten-round run can be inspected when completed. An interrupted run is `FAILED_NOT_A_CANDIDATE`, and no completed result bundle is served. Recorded and live export routes authenticate; live exports require the same owner as the run. The old three-round route remains the default product behavior.

For the isolated offline UI smoke, start the accepted inference runtime, the additive Observatory API, and the frontend with an isolated SQLite/artifact workspace, then run:

```sh
NHM_FL10_FRONTEND_URL=http://127.0.0.1:5185 PYTHONPATH=src:. .venv-t032/bin/python -m scripts.run_fl10_browser_smoke
```

The smoke uses DemoAuth **only for local UI verification**. It does not claim a Clerk-connected two-user ownership check. For a connected evaluator journey, use the accepted Clerk TEST launcher with keys from ignored environment files, never source control. Do not paste keys into reports or chat.

## Evidence map

- Method: `configs/fl10/protocol_v1.json` and `configs/fl10/holdout_manifest_v1.json` (method freeze `f91a96a`).
- Training: `reports/fl10/runs/modeA` and `modeB`, including `run_report.json`, R0–R10 state files, client-round and batch CSVs, and Mode B monitoring-link trace.
- Evaluation: `reports/fl10/eval/modeA` and `modeB`, including exact logits in `holdout_predictions.csv`, pooled/per-participant results, and paired intervals.
- Figures/tables: `reports/fl10/publication/modeA` and `modeB`; `export_manifest.json` binds every export hash.
- Browser: `reports/fl10/browser/fl10_browser_smoke.json` and named screenshots.
- Baseline protection: `reports/fl10/baseline_hashes.json` and `fl10.audit.baseline_unchanged()`.

No CI was queried or triggered for this task.
