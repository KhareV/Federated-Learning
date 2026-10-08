# OBS-DIAG-001 — Research Observatory diagnostic completeness and verification

Starting point `7e91690e21ba4bde71ac5391d0843844ca71ef11` (pushed). The accepted `NHM_RESEARCH_OBSERVATORY_V1` lock file is unchanged and keeps status `FROZEN_IMPLEMENTED_SCOPE_NOT_FULL_MASTER_PROMPT_ACCEPTANCE`. This is a bounded additive successor; its own lock is `artifacts/observatory/NHM_OBS_DIAG_001.lock.json` (`FROZEN_DELIVERED_CAPABILITIES_ONLY`), verified by `scripts/verify_obs_diag_001.py`. Proposed successor status: **accept the delivered capabilities listed here; everything under "Not delivered" stays open.**

## 1. Per-batch FL training observability — DELIVERED (opt-in, newly executed runs only)
- Feasible without touching a protected surface: `api/observatory_batch_capture.py` uses torch's documented *global* observer hooks (BCE-loss module forward post-hook, optimizer step post-hook). Hooks return nothing, read detached values, are active only for the capturing thread and only inside the context, and are removed afterwards (tested). `federated/model_v2_fl.py`, the optimizer, loss, seeds and states are untouched.
- Enabled with `NHM_OBSERVATORY_BATCH_CAPTURE=1` (or `batch_capture=True`); bounded to 64 batches per client-round. Each row: batch index, batch size, BCE batch loss, learning rate, gradient L2 norm, optimizer step. Rows are stored only if they reproduce the end-of-epoch summary exactly (batch count, example count, example-weighted mean loss).
- Parity (`scripts/observatory_fl_parity.py`, `reports/observatory/obs_diag_001/fl_batch_parity.json`): same 8-client/3-round FedAvg run with capture OFF vs sidecar+per-batch ON. Identical: update digests, examples, shuffle seeds, round base and committed digests, candidate digest `3f0b7762ae7e05f21eb1709521404ed4d7968cae34f89e1797a0cbabd47c70e4` and governance, accepted contributions, and the semantic event stream (203 events). 48 batch rows, all consistent. PASS.
- UI: the existing client-round evidence panel shows the table, or "not enabled for this run"; end-of-epoch summaries are preserved. Batch loss is a training signal on synthetic engineering labels, not accuracy.

## 2. Forward-activation inspection — DELIVERED (opt-in, server-side, synthetic window only)
- `GET /product/v1/observatory/model/activations/{scenario}/{window}`: a fresh eager copy of the checksum-verified MODEL_V2_FINAL checkpoint (never the served gateway, never FL state) runs one explicitly selected *synthetic* scenario window with read-only forward hooks on leaf layers. Output: per-layer statistics and a mean-pooled heatmap bounded to 24 channels × 64 bins.
- Gates: the logit with hooks must be bit-identical to the logit without hooks and no hooks may remain, otherwise the API result and the UI parser refuse to show it (tested). Raw probability agrees with `ResearchRuntimeV2` to 1e-6. Unusable windows are rejected. Labelled "not an explanation method", never applied to research recordings, held-out data or candidates.

## 3. Federation sidecar overhead — MEASURED (`sidecar_benchmark.json`)
Five interleaved trials per configuration (OFF / sidecar / sidecar + per-batch), one backend process each, same synthetic cohort and protocol. Median wall-clock 27.67 s / 27.86 s / 28.07 s (+0.66% and +1.44%), within trial-to-trial noise (baseline stdev 0.53 s). Every trial produced the identical candidate digest, committed digests, update digests, accepted examples (723 per round) and governance outcome. Peak RSS varied by about 250 MB between trials of the same configuration, so **no memory effect can be resolved**. One machine, loopback HTTP: no network or deployment claim.

## 4. Browser and accessibility assessment — DOCUMENTED (not certification)
- Engines actually tested: Chrome 154 (stable) and Chrome for Testing 153, both Chromium, headless, via CDP. Firefox: not installed. WebKit/Safari: remote automation disabled (requires a manual Safari setting) — **not tested**.
- 11 Observatory routes. Criteria tested (observations in `a11y_*.json`): 1.1.1, 1.3.1, 1.4.3 (computed contrast, with a negative control), 1.4.10 (320 px reflow), 1.4.12 (text spacing, overflow only), 2.1.1/2.1.2 (real Tab walk), 2.4.2, 2.4.3 (heuristic), 2.4.7, 2.4.11, 2.5.8, 3.1.1, 3.3.2, 4.1.2, reduced motion. After fixes there were no failures. Fixed during the assessment: eight sub-24 px client links and lost focus after client-side navigation (focus now moves to the page heading).
- Not tested: 1.4.11 non-text contrast, real screen readers, Firefox/WebKit.

## 5. Preserved unavailable capabilities
No held-out recordings or raw WFDB data accessed; no annotation positions invented; no historical trace reconstructed as captured evidence; CAL_V2 never applied to a candidate; no AAMI-SVF efficacy metric for the synthetic-label candidate; no hardware, no new experiment, no promotion, released runtime unchanged.

## Not delivered / blocked
Raw WFDB annotation positions (data absent); per-batch data for runs that predate this capture; Firefox and WebKit verification; screen-reader and non-text-contrast assessment; sidecar memory conclusions; network performance claims.
