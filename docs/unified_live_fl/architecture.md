# Unified Live Federation Studio: architecture

One frontend experience, two unchanged execution engines, one evaluation path.

```
 /app/federation  (3 | 10 rounds)                       /app/federation/live?run=…   (same page for both)
        │                                                          ▲  events (PRODUCT_LIVE_EVENT_V1, strict parser)  ▲ REST (evaluation, figures, tables, exports)
 3 rounds ─► POST /product/v1/federation/runs  (frozen contract, planned_rounds==3 enforced)
        │         product.federation.service.FederationService ──events──► journal ──WS /federation/runs/{id}/live
        │               │ read-only instance wrappers (studio/capture3.py): committed state, per-client diagnostics, per-batch hooks
 10 rounds ► POST /product/v1/studio/runs  → studio/runner10.py ─► fl10.runner.run_training  (same Coordinator + train_local_epoch_v2)
                       progress callbacks ─► studio/events10.py ─► typed journal ──WS /studio/runs/{id}/live
                       committed R_k ──────────────────────────┐
 3-round committed R_k ──────────────────────────────────────►│  studio/observer.py: ONE worker, private state copy, digest re-verified,
                                                               │  studio/isolated_eval.py (RNG-free) + fl10 metric engine, fixed 0.5, no CAL_V2
                                                               ▼
                                   eval/Rxx/{record.json,predictions.csv,curves.json}, paired.json  (full precision, hashed)
                                   studio/bundle.py → studio/specs.py + studio/tables.py (20 figures, 12 tables; parity-tested against fl10.charts/tables)
                                   studio/exports.py → run-specific SVG / PNG 300 dpi / CSV / JSON provenance, tables CSV/JSON/MD, evidence files
```
- **Ownership:** every run-scoped route and the WebSocket check the run owner (`403` for another user); recorded FL10 evidence is a global read-only reference (also served as a labelled REPLAY journal reconstructed from the recorded run report).
- **One live run at a time** across both engines and routes (the product `POST /federation/runs` and the old FL10 route return `409` while a Studio run executes).
- **Shared selected-round state** (`StudioStore`): `followLive`, `selectedRound`, `selectedClientId`, `analysisTab`; historical views are rebuilt only from the current run's validated events (`FederationStore.viewAtRound`). Switching runs clears every run-scoped cache first and drops late responses of the previous run.
- **Launchers:** the default Clerk launcher (`run_observatory_clerk_connected`) and the Observatory product launcher serve the Studio routes. The offline `--demo` faculty launcher serves the older product app (no Observatory/Studio routes, as before); the Studio entry page then disables the 10-round option with an explanation and the 3-round default is unaffected.
