# C-V2-013-QUALITY-FLATLINE-AUDIT — handoff

**Result: PASS. Classification: Branch A (no quality change). Scientific downstream: VALID. V2-013 and V2G12: PASS (unchanged).**

## Entry
Entry/origin HEAD `65fddd4` (V2-013 result), method commit `108973c`, tree clean, no amend/rewrite. V2-013 evidence preserved (93 windows, 80x200 / 13x422, digest `7ef39ae9…`, live/accelerated, 300-window equivalence, locks): `preservation_audit.json` = PASS.

## Frozen contract (`frozen_contract_audit.json`)
QUALITY_V1 spec 2.2. Flatline: `POPULATION_STD_DIVIDED_BY_RMS`, epsilon `1e-12` (numerical epsilon, not data-derived). Condition: complete 2500-sample window, all finite, and `rms == 0.0` or `std(ddof=0)/rms <= 1e-12`. Reason `FLATLINE`, state `UNUSABLE` (precedence UNUSABLE > DEGRADED > VALID). **Evaluated on the FILTERED 250 Hz window** — every production caller (MITDB windows, INCART, NSTDB, V2-013 stream) passes `filtered[start:end]`.

## F06
`verify_preproc_freeze` PASS; `configs/quality_v1.yaml` and `preprocessing/quality.py` match the PREPROC_V1 pins; no drift.

## Direct test (`direct_quality_flatline_test.json`, 11/11 PASS, no threshold tuned)
exact zero, +0.37, −1.9, 1e-9/1e3/1e9 constants, relative perturbations 1e-13 and 0.5e-12 (flagged), 1e-10 and 1e-6 (not flagged), normal ECG control (VALID).

## Historical tests (`historical_t013_test_audit.json`)
They call the real `evaluate_ecg_quality(np.ones(2500))` and assert UNUSABLE; the near-flat test exercises only the `is_flatline` helper. They do not assert the FLATLINE reason through the evaluator, have no above-criterion control, and never pass a constant *source* through the frozen resampler/band-pass. So "flatline implemented, tested, frozen" is true as stated, but the tests could not expose the filtered-representation behavior below. No mocking.

## Full-pipeline reproduction (cause)
- Constant **nonzero** source (0.12 mV, up to 1400 s): 0 of 42 complete flat-source windows flagged. The stateful 360→250 Hz resampler leaves a persistent ripple (std ≈ 1e-5 of level; 13 distinct values) that the causal band-pass keeps after removing DC, so filtered `std/rms ≈ 1.0` ≫ 1e-12 (`pipeline_filtered_flatline_decay.json`, `full_pipeline_flatline_reproduction.json`).
- **Exact-zero** source stays exactly zero: from stream start, 6/6 complete windows → UNUSABLE + FLATLINE; zero injected mid-stream is flagged only after the band-pass transient underflows (first flagged window ends at 375 s for zeros from 50 s) (`zero_source_flatline_scenarios.json`).

## Classification
Branch A. QUALITY_V1 matches F06 and its written contract; the V2 runtime invokes it exactly as every production caller does (not Branch B/C/D). The V2-013 sentence "QUALITY_V1 doesn't flag a flatline fault" overstated the finding: it does not flag a stuck **nonzero** source. This is a frozen-composition limitation: closing it would be a Class C quality/preprocessing change (e.g. a pre-filter flatline guard), deliberately **not** made; flagged for independent scientific replanning. Because nothing scientific changed, no scientific-example impact audit was required.

## Separate defect found and fixed
`simulation/stream_runtime_v2013.py` crashed (`zero-size array … maximum`) when a chunk yielded no resampler output (e.g. a 1-sample tail with chunk size 97). Guarded additively; the original 93-window bundle is reproduced byte-for-byte (test). Because API_RUNTIME_V2 binds that file, a successor lock **API_RUNTIME_V2_1** was created; API_RUNTIME_V2 is preserved byte-identical (its old verifier now reports drift only on that file).

## Revalidation (`replay/`)
Additive bundle `WEARABLE_SIM_V2_REPLAY_V2_FLATLINE` (100 s; exact-zero source 0–40 s): 17 windows, 6 flatline windows (UNUSABLE + FLATLINE at the quality layer) → all 6 HTTP 422 `UNUSABLE_OR_INCOMPLETE_SIGNAL_WINDOW` (frontend RECHECK_SENSOR), no MODEL_V2 inference (spy-tested), 11×200. Two fresh-process runs, real frontend path and direct HTTP all share digest `0a2c5e6c…aa99e`; live-speed equals accelerated. The old digest is not expected to match (new scenario). Note the API response itself carries the generic UNUSABLE error; the FLATLINE reason code lives in the stream diagnostics.

## Items not reopened
No natural episode in 93 windows (CAL_V2 not manipulated); no browser framework added; V1-isolation verifier scope correction audited (`--diff-filter=MDRT` still flags modified/deleted/renamed V1 files — temp-repo test; added files only are ignored; the protected-hash audit independently covers V1 files); registry CRLF preserved (new row appended with CRLF).

## Regression
ruff, `pip check`, chunked pytest (0 missing/duplicate/unexpected/failed), frontend unit/check/build — see `regression_audit.json`. CI never queried/triggered.

## Decision
V2-013 accepted as clean (with the corrected wording above); V2G12 clean; scientific downstream valid; **V2-FL-001 is allowed to start — but not started here.** Open item for independent replanning: whether a stuck-nonzero ECG source should become a hard failure (Class C change).
