# MODEL_V2_COMPLETE_REPRO_PROTOCOL_V1 (V2-014, gate V2G13)

Machine-readable protocol: `configs/model_v2/complete_repro_protocol_v1.yaml`. Harness:
`scripts/run_v2_014_clean_repro.py` (orchestrator), `scripts/v2_014_clone_checks.py` (in-clone
checks), `scripts/v2_014_fl_dev_reconstruct.py`, `scripts/run_v2_014_replay.py`,
`scripts/verify_v2_014_evidence.py`, `scripts/import_v2_014_evidence.py`.

## Four evidence categories (never conflated)
* **A. Tracked artifact identity** -- component lock inventory, checkpoint and prediction-table
  inventories, one-shot guard states, protected-artifact drift versus the entry commit.
* **B. Data-free stored-evidence reconstruction** -- FL development statistics from committed round
  logs / VALIDATION prediction tables / result files; held-out statistics from the frozen prediction
  tables. This is statistics reproducibility, not retraining and not inference repetition.
* **C. Executable software / synthetic reproduction** -- MODEL_V2 load + fixed vectors (two fresh
  processes), fixed-vector regeneration, CAL_V2 helpers, canonical gateway identity + semantic
  re-export, V2-013 software replay and flatline replay, FL_INIT_V2 regeneration (two fresh
  processes), data-free SecAgg checks, and the complete WEARABLE_SIM_FL system (cohort regeneration,
  three rounds, restart/resume, SecAgg shadow, event replay, finite logits).
* **D. Full repository regression** -- chunked + monolithic pytest, ruff, pip check, frontend
  `npm ci`/test/check/build, strict lifecycle test.

## Clean-clone discipline
A brand-new `git clone` of the remote into a new temporary root at the exact commit; fresh Python
3.11 venv from `requirements-dev.lock`; `npm ci` from `package-lock.json`; isolated HOME; ambient
PYTHONPATH/NODE_PATH unset. No worktree, copied tree, symlink, bind mount, raw-data copy or rescue
install. Evidence is written outside the clone. A failing clone is never repaired: correct the
repository prospectively, commit, and start a NEW clone.

## CLEAN_CLONE_GATING_V1 (disclosed prospective correction)
A dry mechanics run showed that 18 historical tests need inputs a clean clone deliberately lacks
(raw PhysioNet datasets, gitignored processed window caches, untracked candidate checkpoints, the
developer `.venv-t032` interpreter path). `tests/conftest.py` skips exactly those tests, with an
explicit reason, only when the input is absent. They are reported as DATA_GATED_SKIPPED and are
excluded from the clean SOFTWARE claim; they are not force-passed and run unchanged where the
inputs exist.

## Not claimed
No new AUPRC, generalization, clinical, real-wearable or promotion evidence. MODEL_V1 remains the
operational default; `MODEL_V2_NOT_PROMOTED_RELEASE_CI` is untouched. A prospective system-level
release/default decision is a separate, not-yet-started phase.
