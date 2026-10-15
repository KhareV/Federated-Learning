# Recorded hardware on the Live federation page

A recorded-hardware federation run is a **first-class Studio run**. It is not a separate page: it is observed on the
same Live federation page, with the same panels, as a synthetic-cohort run (`/app/federation/live?run=HDFLRUN-…`).

## What is the same
| Part of the page | Source for a hardware run |
|---|---|
| Header, stages, client network, round progress, model-state transition, timeline | the run's own PRODUCT_LIVE_EVENT_V1 federation journal (same translator as FL10 runs), streamed over the same WebSocket and replayable from sequence 0 |
| Evaluation cards, interactive graphs, analysis tabs, tables | the same figure/table builders (`studio/specs.py`, `studio/tables.py`) fed with a `STUDIO_LIVE_BUNDLE_V1`-compatible bundle (`studio/hardware_bundle.py`) |
| Metrics (AUPRC, AUROC, F1, BCE, Brier, confusion, curves, per-session metrics) | the **same metric functions** the synthetic evaluator uses (`fl10.metrics`, `final_showcase.metrics`), computed from the stored checkpoints on the stored held-out windows |
| Exports (figures CSV/SVG/PNG, tables CSV/JSON/MD) | the same exporter, written when the run completes |

## What differs (data source only)
* Eight logical clients are named `RECORDED_DEMO_CLIENT_00…07`; each holds a contiguous block of **your recorded 1 s windows**.
* There is no single "owner-bound" client and no "synthetic peer": every card says **YOUR RECORDED WINDOWS**.
* Labels are deterministic and **synthetic** (assigned for the demonstration). No clinical or diagnostic meaning.
* The model is a small tabular classifier (`HARDWARE_DEMO_MODEL_V1`); `MODEL_V2_FINAL` weights cannot be loaded into it.
* The held-out windows are a window-level split of the *same* recording sessions: a diagnostic, not an independent test.
* Not applicable and shown as such: the unseen-cohort Generalisation lane, paired participant-cluster intervals, the
  historical centralized reference.

## Lifecycle
`POST /product/v1/studio/hardware-demo/runs` validates and prepares synchronously (any data problem is an immediate 4xx), returns the run
descriptor and trains in one worker thread. A run interrupted by a restart is reported `FAILED` (never a result). Only one
hardware run is active at a time. The Federation form navigates to the Live page right after Start.

## Findings fixed while integrating
* `Fl10EventTranslator` emitted `SecAggStatus.VERIFIED`, which does not exist (`SHADOW_VERIFIED`), so the round-1 shadow status never
  reached the page for any 10-round run. Fixed (and `SHADOW_RUNNING` is now emitted first, like the 3-round engine).
* The Tailwind utility `.fixed{position:fixed}` collided with a component class named `fixed` and pulled the "Fixed configuration"
  tiles over the run form. Fixed.
