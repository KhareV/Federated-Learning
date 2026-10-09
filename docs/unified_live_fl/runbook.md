# Federation Studio runbook (3- and 10-round runs)

## Start
- Default (connected Clerk TEST authentication): `python -m scripts.run_nhm` — serves the Observatory product API, therefore the Studio routes. Open the printed `/sign-in` URL → **Federation**.
- Offline faculty launcher: `python -m scripts.run_nhm --demo` (explicit DemoAuth acknowledgement). It serves the older product app (as before) without Observatory/Studio routes: the 3-round default works, the 10-round option is disabled with an explanation. For an offline 10-round demo start the Observatory product API with DemoAuth (`python -m scripts.run_observatory_product`, same environment as the faculty launcher) behind the frontend.
- The `--demo` preflight now passes (`docs/unified_live_fl/governance_repair.md`).

## Use
1. **Federation Studio** → *Communication rounds*: **3 rounds · default** (original run form: LIVE/REPLAY, FedAvg/FedProx, plain/SecAgg shadow) or **10 rounds · extended** (LIVE, FedAvg, plain; source mode *canonical synthetic cohort* or *live-monitored simulated SITE_00*). The table shows *expected* accepted updates (24 / 80); the running page shows only updates the coordinator actually accepted.
2. **Start** → the live page opens (same page for both lengths). RUN STATUS strip (state, round, accepted/expected updates, round dots with evaluation badges), the original eight-client network (★ MY EDGE CLIENT only under connected Clerk), round explorer, evaluation of the selected round, key graphs, analysis tabs, model state / candidate / timeline.
3. **Follow live** (default) tracks the actual round. Click any committed round (strip, explorer, or a chart point) to inspect it; new events no longer move your selection until **RETURN TO LIVE**. Historical panels are rebuilt only from this run's validated events.
4. A round that is committed but not yet evaluated is shown as `QUEUED` / `EVALUATING`; its metric cards say so and the metrics shown are explicitly the latest *evaluated* round. Graphs mark pending rounds and never draw a value for them.
5. **Analysis tabs**: OVERVIEW · PERFORMANCE · TRAINING · CLIENTS · MATRICES · COMPARISON · FIGURES & EXPORTS. All 20 figures and 12 tables, plus per-round client contributions, client history, compare-any-two-rounds, the research bridge and the verification manifest.
6. **Exports** (after the run completes and every evaluation settles): SVG, 300-dpi PNG, CSV and JSON provenance per figure; CSV/JSON/Markdown per table; full-precision evaluation records, predictions and the run report. Each download is re-hashed in the browser against the manifest.
7. **Historical runs**: pick any run in the run selector. Recorded NHM_FL10_001 runs open as labelled read-only evidence (a replay reconstructed from the recorded run report). A product REPLAY shows the source run's recorded evaluation. Runs that predate the observer say `RUN_PREDATES_LIVE_EVALUATION` and show no metrics.

## Verify
- `python -m scripts.verify_unified_studio_001 --lock` — the additive successor lock, the whole older verifier chain and the evidence.
- `python -m scripts.run_studio_local_gates` — full backend suite (chunked), frontend tests, svelte-check, build and launcher preflight.
- Real browser journey against a running isolated stack: `python -m scripts.run_studio_browser scripts/studio_browser_verify.mjs <origin> reports/unified_live_fl/browser` (starts a genuine 3-round and a genuine 10-round run; DemoAuth).
- Evidence of the executed runs: `python -m scripts.studio_collect_evidence --run3 <id> --run10 <id>`.

## What this does not claim
Synthetic engineering data only; no clinical or AAMI-SVF claim; the 16-participant cohort is reused (diagnostic, not an untouched final test); eight logical clients on one machine; connected Clerk two-user E2E not executed; no hardware.
