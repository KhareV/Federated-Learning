# V2-013 final handoff — API_RUNTIME_V2 + WEARABLE_SIM_V1 software vertical integration

Entry SHA 40e1273 (V2-012 PASS). Method commit 108973c, then result commit (see `git log`).

## Final state
- V2-013 = PASS, V2G12 = PASS
- API_RUNTIME_V2 = FROZEN_RESEARCH_RUNTIME (`artifacts/API_RUNTIME_V2.lock.json`)
- ALERT_POLICY_V1_MODEL_V2_BINDING = FROZEN_RESEARCH_BINDING (ALERT_POLICY_V1 unchanged)
- V2 software replay WEARABLE_SIM_V2_REPLAY_V1 = FROZEN_COMPLETE; WEARABLE_SIM_V1 -> V2 software path = VERIFIED_ENGINEERING_INTEGRATION
- MODEL_V2_FINAL / CAL_V2 / GATEWAY_ARTIFACT_V2 / EXPLAINABILITY_V2 unchanged; operational default = MODEL_V1
- Cumulative V2 neural fits = 71 (0 in this phase); no protected partition accessed; V2-014 NOT_STARTED/RESERVED; next = V2-FL-001 (not started)

## What was built
- `api/app_v2.py`, `api/runtime_v2.py`: parallel research runtime, unchanged API_SCHEMA_V1, bound_model_id check, no public model/threshold/checkpoint selector, factory (no import-time construction), V1 files untouched.
- `fusion/alert_policy_v2_binding.py`: additive binding; K=2/M=2/cooldown 30 s unchanged; threshold read from CAL_V2.
- `simulation/{profile,truth,stream_runtime}_v2013.py`: 360 Hz ObservedRecord stream; truth side verification-only; streaming runtime reuses the existing causal preprocessing, QUALITY_V1 and context alignment. Import guard + behavioral leakage test.
- Frontend: one genuine defect (hard-coded `MODEL_V1` request id and MODEL_V1 copy). Fixed with a build-time `VITE_NHM_REQUEST_MODEL_ID` (default MODEL_V1; not a runtime selector). DASHBOARD_UI_V1_4 and E2E_REPLAY_SOFTWARE_V1_3 successor locks; predecessor locks byte-identical; three historical tests now assert preserved-lock + drift.
- Demo: `python -m scripts.run_research_v2_demo [--serve]`.

## Results (engineering only; no AUPRC/AUROC/F1 or clinical claim)
- Equivalence vs independent reference, 300 synthetic windows over HTTP: max raw/calibrated probability delta 0.0 (tol 1e-12); state and threshold agreement 1.0.
- Replay: 93 windows (80x HTTP 200, 13x 422 UNUSABLE, no inference on 422). Two fresh-process runs, the real-HTTP frontend path and a direct HTTP replay all share semantic digest 7ef39ae9…01c7.
- LIVE_SPEED (44.1 s wall) vs ACCELERATED (0.07 s) and chunk sizes 97/360/1000: identical ordered semantic outcomes.
- State machine audit (DEGRADED cannot advance open; UNUSABLE -> RECHECK_SENSOR, does not close an active episode, clears open counter) PASS. V1 default regression and V1/V2 isolation PASS.
- Regression: ruff, pip check, chunked pytest (0 missing/duplicate/unexpected/failed), vitest, svelte-check (0 errors), build.

## Disclosures
- Observation: with CAL_V2 squeezing probabilities toward 0.5, the sim replay opened no episode; episode logic is covered by the state-sequence audit on constructed sequences.
- QUALITY_V1 does not flag a flatline source fault (frozen rule not changed); the sim uses sensor dropout instead.
- Component-level browser test: the SvelteKit route is verified built/reachable and its composed components rendered from real session state; the repository has no browser-automation stack.
- Harness dry runs went to a scratch dir while debugging mechanics (port launch, JS number spelling in the digest, a test assertion); no method behavior changed in response to outcomes.
- Post-method amendment: `scripts/run_v2_013_v1_isolation.py` git pathspec scoped to `--diff-filter=MDRT` because it counted the new additive binding file as a modified V1 file (see method_immutability_audit.json).
- `frontend/build` is gitignored; the finalizer leaves it built with the default (V1) request id.
- CI deferred; Actions never triggered/queried.
