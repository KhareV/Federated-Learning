# Entry state (Gate A) — unified UI / source-state consistency pass

Recorded before any edit of this pass (2026-10-16, local time).

| Item | Value |
|---|---|
| Working directory | `/Users/Home/Downloads/miniproject` |
| Branch | `main` |
| `HEAD` | `49855ec9da7b349852a7dac34525de5ccb5160fb` |
| `origin/main` (after `git fetch`) | `49855ec9da7b349852a7dac34525de5ccb5160fb` — identical (ahead 0 / behind 0) |
| `git diff --check` | clean |
| Tracked modifications | 45 files (436 insertions, 179 deletions) |
| Untracked paths | 159 (new modules, docs, tests, lock, evidence) |
| Stash | none |
| Pre-edit snapshot | tracked patch + tar of untracked files saved **outside the repository** (session scratchpad); no secrets copied. `.env` is git-ignored and was not touched. |

## Last pushed lineage (unchanged bytes)
- 49855ec Monitor lifecycle: leaving the page no longer stops the hardware session; catch-up on return; additive successor lock
- 89b8904 NHM-ESP32-REHEARSAL: WebSocket ESP32 emulator, local ingestion replica, fault/soak rehearsal, preflight; reader look-back fix; interrupted/idempotent sessions
- 0f5a568 Monitor: experimental resampled V2 panels for live hardware; Federation: recorded hardware merged into the run starter with starting-model choice; History: hardware session table
- acaaaed NHM-RECORDED-HARDWARE-FL-001: recorded-hardware demo FL, FedProx + SecAgg+ shadow on the extended engine (software/Atlas-injection verified; physical ESP32 NOT verified)
- e2377ad NHM-HARDWARE-MONGO-001: verify Atlas telemetry and Clerk UI
- 1501c9d NHM-UNIFIED-LIVE-FEDERATION-STUDIO-001: collapsible sidebar (icon rail, Ctrl/Cmd+B, remembered preference); re-pinned additive successor lock

## Local, uncommitted, authored work found and preserved
* Successor lock `artifacts/hardware_demo/NHM_HARDWARE_LIVE_UNIFIED_001.lock.json` (predecessor `NHM_HARDWARE_MONITOR_LIFECYCLE_001`, commit `49855ec`); not accepted/pushed, so it is regenerated (not forked) when this pass changes bound files.
* Recorded hardware as a first-class Studio run: `studio/hardware_runs.py`, `studio/hardware_bundle.py`, `studio/service.py` dispatch, `api/observatory_studio.py`, journal translator fix in `studio/events10.py`.
* Frontend: shared Live page for `HDFLRUN-*`, `data-source.ts`, `ReadMore.svelte`, History table/detail compaction, Federation explainers collapse, micro-label sizes.
* Tests: `tests/test_hardware_studio_run.py`, `data-source.test.ts`, preservation-test digest allowances, UI tour driver (`scripts/ui_tour_lib.mjs`).
* The execution prompt itself (`NHM_Final_Unified_UI_Self_Sustaining_Execution_Prompt.md`) is an untracked user document in the repository root and is **not** part of any commit unless the user asks.

## Authority and protected surfaces
Current working tree + generated evidence → later user decisions / accepted successors → v2.2 foundation → solo plans → older history.
Not touched by this pass: model, calibration, inference, federated computation, persistence/auth semantics, labels/datasets, frozen evidence bytes, historical lock bytes, deployment configuration.
`NHM_Unified_UI_Consistency_Implementation_Blueprint.md` was **not found** on disk; the audit below is therefore derived from the code and the browser, not from that file.

## Runtime
Launch: `PYTHONPATH=src:. .venv-studio311/bin/python -m scripts.run_nhm`. Browser verification: `scripts.verify_hardware_connected_browser --producer ws --users-file <clerk users json> [--ui-tour | --away-seconds N]` (real Chrome + Clerk test users + ESP32 emulator + local replica + isolated Atlas database; never `health_db`).
Evidence level of all hardware results: `VERIFIED_LOCAL_RENDER_REPLICA`. Physical ESP32 and deployed Render are not verified.
