"""C032-NORM-RUNTIME regression suite: proves the restored PREPROC_V1 PER_WINDOW_ZSCORE_V1
normalization at the API -> gateway boundary (api/runtime.py::ProductionRuntime.infer,
API_RUNTIME_V1_1), proves the MODEL/HR branch separation, and proves equivalence with the
T029 deployment-equivalence reference path -- all without reading any target label.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from api.runtime import InputValidationError, ProductionRuntime
from deployment.runtime import GatewayModelRuntime
from evaluation.internal_test import load_internal_population
from preprocessing.ecg_hr_context import estimate_hr
from preprocessing.windowing import NORMALIZATION_EPSILON, WINDOW_SAMPLES, normalize_window_zscore

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def runtime() -> ProductionRuntime:
    if not (ROOT / "artifacts/deployment/MODEL_V1_GATEWAY_FP32.ts").exists():
        pytest.skip("gateway artifact not built yet")
    return ProductionRuntime(ROOT)


@pytest.fixture(scope="module")
def gateway() -> GatewayModelRuntime:
    return GatewayModelRuntime(ROOT, ROOT / "artifacts/deployment/MODEL_V1_GATEWAY_FP32.ts")


def test_infer_normalizes_before_gateway_call(runtime: ProductionRuntime) -> None:
    """A non-trivial (non-zero-mean/unit-variance) raw window must produce a *different*
    raw_logit than the pre-fix defect (raw window handed straight to the gateway) -- proves
    the gateway input array is no longer the unnormalized window."""
    rng = np.random.default_rng(32)
    raw = (rng.standard_normal(WINDOW_SAMPLES) * 5.0 + 3.0).tolist()

    corrected = runtime.infer(raw)
    old_invalid_array = np.asarray(raw, dtype=np.float32).reshape(1, 1, -1)
    old_invalid = runtime.gateway.infer(old_invalid_array)

    corrected_logit = -np.log(1.0 / corrected.raw_probability - 1.0)
    assert corrected_logit != pytest.approx(old_invalid.raw_logit, abs=1e-3)


def test_infer_matches_manual_normalization_exactly(
    runtime: ProductionRuntime, gateway: GatewayModelRuntime
) -> None:
    """ProductionRuntime.infer(raw) must be exactly (bit-identical) equivalent to
    normalize_window_zscore(raw) followed by GatewayModelRuntime.infer -- the same
    composition T015-T031 and T029 already use."""
    rng = np.random.default_rng(7)
    raw = rng.standard_normal(WINDOW_SAMPLES) * 2.0 - 0.5

    corrected = runtime.infer(raw.tolist())
    normalized = normalize_window_zscore(raw, epsilon=NORMALIZATION_EPSILON)
    reference = gateway.infer(normalized.astype(np.float32).reshape(1, 1, -1))

    assert corrected.raw_probability == pytest.approx(
        1.0 / (1.0 + np.exp(-reference.raw_logit)), abs=1e-12
    )
    assert corrected.source_domain_calibrated_probability == reference.calibrated_probability
    assert corrected.above_threshold == reference.above_threshold


def test_infer_rejects_wrong_length() -> None:
    runtime_local = ProductionRuntime(ROOT)
    with pytest.raises(InputValidationError, match="INFER_INPUT_LENGTH_MISMATCH"):
        runtime_local.infer([0.0] * (WINDOW_SAMPLES - 1))


def test_infer_rejects_nonfinite_input() -> None:
    runtime_local = ProductionRuntime(ROOT)
    bad = [0.0] * WINDOW_SAMPLES
    bad[10] = float("nan")
    with pytest.raises(InputValidationError, match="INFER_INPUT_NONFINITE"):
        runtime_local.infer(bad)


def test_estimate_ecg_hr_receives_unnormalized_amplitude_preserving_window(
    runtime: ProductionRuntime,
) -> None:
    """Section 14 branch-separation guarantee: `estimate_ecg_hr` must see the SAME raw
    filtered samples passed in -- never the z-scored MODEL branch array."""
    rng = np.random.default_rng(11)
    raw = (rng.standard_normal(WINDOW_SAMPLES) * 0.3).tolist()

    direct = estimate_hr(
        np.asarray(raw, dtype=np.float64), timestamp_us=10_000_000, candidate_id="WFDB_XQRS_V1"
    )
    via_runtime = runtime.estimate_ecg_hr(raw, timestamp_us=10_000_000)

    assert via_runtime.hr_ecg_bpm == direct.hr_ecg_bpm
    assert via_runtime.valid == direct.valid


def test_runtime_equivalence_against_t029_internal_population(
    runtime: ProductionRuntime, gateway: GatewayModelRuntime
) -> None:
    """Corrected ProductionRuntime.infer() must match the T029 deployment-equivalence
    reference path (normalize_window_zscore then GatewayModelRuntime.infer) on every row of
    the same INTERNAL_TEST population T029 benchmarked against, with the same required
    decision_agreement_fraction == 1.0 used at T029 (see reports/t029/deployment_equivalence.
    json). No target label is read."""
    population = load_internal_population(ROOT)
    max_abs_logit_delta = 0.0
    disagreements = 0
    for row in population.waveforms:
        normalized = normalize_window_zscore(row, epsilon=NORMALIZATION_EPSILON)
        reference = gateway.infer(normalized.astype(np.float32).reshape(1, 1, -1))
        corrected = runtime.infer(row.tolist())
        delta = abs(
            corrected.source_domain_calibrated_probability - reference.calibrated_probability
        )
        max_abs_logit_delta = max(max_abs_logit_delta, delta)
        if corrected.above_threshold != reference.above_threshold:
            disagreements += 1

    assert disagreements == 0
    assert max_abs_logit_delta < 1e-6

    out = ROOT / "reports/c032_norm_runtime/runtime_equivalence.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(
            {
                "rows_compared": int(population.waveforms.shape[0]),
                "max_abs_calibrated_probability_delta": max_abs_logit_delta,
                "threshold_decision_disagreements": disagreements,
                "decision_agreement_fraction": (
                    1.0 - (disagreements / population.waveforms.shape[0])
                ),
                "required_decision_agreement": 1.0,
                "reference_path": (
                    "preprocessing.windowing.normalize_window_zscore -> "
                    "deployment.runtime.GatewayModelRuntime.infer (same composition as "
                    "scripts/run_gateway_t029.py::canonical())"
                ),
                "corrected_path": "api.runtime.ProductionRuntime.infer (API_RUNTIME_V1_1)",
                "labels_used": False,
                "status": "PASS",
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
