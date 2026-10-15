# Source / run / session state contract

The UI never has one overloaded "recorded" or "hardware" flag. It keeps **independent axes**, each read from a backend-validated descriptor
(`StudioRun`, hardware session, evaluation record). Implementation: `frontend/src/lib/product/federation/run-context.ts` (typed, fail-closed, unit-tested).

## 1. Axes of a federation run

| Axis | Values | Read from | Notes |
|---|---|---|---|
| Data provenance | `SYNTHETIC_COHORT`, `SIMULATED_MONITORED_SITE_00`, `RECORDED_HARDWARE`, `UNKNOWN` | `engine` + `source_mode` | an id prefix is never the classifier (it only yields a *provisional*, capability-closed context before the descriptor arrives) |
| Execution mode | `LIVE_TRAINING`, `EVENT_REPLAY`, `RECORDED_EVIDENCE`, `UNKNOWN` | `origin`, `run_type` | a recorded-hardware run is live training, not replay; a historical recorded *synthetic* run is recorded evidence, not hardware |
| Label provenance | `SYNTHETIC_ENGINEERING_EVENTS`, `SYNTHETIC_ASSIGNED_FOR_DEMO`, `UNKNOWN` | data provenance | no label in the product is clinical |
| Model lineage | `FL_INIT_V2`, `MODEL_V2_FINAL`, `HARDWARE_DEMO_FRESH`, `HARDWARE_DEMO_WARM_START`, `UNKNOWN` | `base_model.model_id`, `base_model.initialisation` | `MODEL_V2_FINAL` cannot initialise the tabular hardware model |
| Client namespace | `SIM_FL_SITE`, `RECORDED_DEMO_CLIENT` | data provenance | eight logical clients on one machine, never eight devices |
| Evaluation status | `COMPLETED`, `QUEUED`, `EVALUATING`, `FAILED`, `NOT_SUBMITTED` | evaluation record | pending/failed/undefined is never rendered as 0 or NaN |
| Capabilities | owner-bound client, generalisation, paired intervals, historical V2 reference, SecAgg+ shadow, exports, replay | run context | each is `{available, reason}`; unavailable ones are shown as **Not applicable** with the reason |

## 2. Capability matrix

| | Synthetic live | Simulated SITE_00 | Replay of a run | Recorded synthetic evidence | **Recorded hardware** |
|---|---|---|---|---|---|
| Owner-bound client | yes (Clerk + live) | yes | no | no | **no** (all eight hold your windows) |
| Unseen-cohort generalisation | yes | yes | yes (source run) | no (own recorded evaluation) | **no** |
| Paired participant-cluster intervals | yes | yes | yes | yes | **no** (sessions are not independent clusters) |
| Frozen V2 historical reference | yes | yes | yes | yes | **no** |
| Pretrained V2 start | 3/10 rounds | 3/10 rounds | n/a | n/a | **no** (fresh seed or earlier hardware run) |
| SecAgg+ shadow | optional | optional | as recorded | as recorded | optional (round 1; authoritative aggregation stays plain) |
| Figures / tables / exports | yes | yes | yes | yes | yes (same builders) |

## 3. Run-selection transaction
* `FederationStore.selectRun` increments a selection sequence, closes the previous socket and **clears** descriptor, rounds, journal, counters and per-round view cache *before* the next descriptor is requested. A late response of a previously selected run is discarded (`run-switch.test.ts`).
* `StudioStore.track(runId)` already clears every run-scoped cache (evaluation, figures, tables, exports, overview, generalisation, selected round/client) and ignores responses of an older sequence.
* The Live page derives all source-dependent content from `runContext(studio.run, selectedRunId)`; a descriptor of another run is treated as absent.
* While following live and a round is not yet evaluated, the evaluation card shows the latest evaluated round **with its round label**; there is no unlabeled fallback.

## 4. Hardware session lifecycle (unchanged)
Start is explicit. Leaving Monitor stops frontend polling only; the session stays `ACTIVE`. There is **no background collector**: readings are ingested during authenticated polls and caught up from MongoDB on return (500 documents per poll). Only explicit Stop, or a backend restart (`INTERRUPTED`), ends a session. Stale telemetry (no accepted record for 5 s) is not an ended session.

## 5. Metric comparability
The same metric name on a different task is not comparable. Synthetic-cohort metrics, recorded-hardware demo metrics (synthetic assigned labels, window-level holdout from the same sessions) and the scientific real-ECG results are three separate lanes; no screen compares across them.
