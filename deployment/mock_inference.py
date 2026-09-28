"""MOCK_INFERENCE_V0 — a deterministic architectural placeholder for the T005 vertical slice.

This is explicitly NOT MODEL_V1. It has no learned parameters, is not trained, is not
physiologically meaningful, and reports no accuracy. It exists only to prove the
observed-fixture -> inference -> state -> API architecture before MODEL_V1 exists.

Consumes only `ObservedRecord`-shaped input (see simulation/types.py /
contracts/sample_schema_v1.json). Must never import from `simulation.wearable` or otherwise
gain access to `SimulationTruth` — see contracts/WEARABLE_SIM_V1.md Section 10.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

MOCK_INFERENCE_MODEL_ID = "MOCK_INFERENCE_V0"

# Arbitrary fixture-only scaling constant for the deterministic score below. It is not
# derived from, and does not assert, any real ADC resolution, gain, or calibration fact —
# those remain VERIFICATION_REQUIRED per contracts/HARDWARE_DATA_CONTRACT_V1.md.
_SCORE_REFERENCE = 5000.0


class ObservedInput(Protocol):
    """Structural type for the observed fields this module is allowed to read."""

    timestamp_us: int
    ecg_raw: int | None
    ecg_quality: str
    source: str


@dataclass(frozen=True)
class MockInferenceResult:
    timestamp_us: int
    model_id: str
    raw_score: float | None
    ecg_quality: str
    source: str


def run(record: ObservedInput) -> MockInferenceResult:
    """Produce a deterministic fixture/test score from observed fields only.

    The score is a stable, reviewable transformation of `ecg_raw` — not a physiological
    inference. It must never be labeled MODEL_V1, CAL_V1, or a calibrated probability.
    """
    if record.ecg_raw is None:
        raw_score = None
    else:
        raw_score = max(0.0, min(1.0, record.ecg_raw / _SCORE_REFERENCE))
    return MockInferenceResult(
        timestamp_us=record.timestamp_us,
        model_id=MOCK_INFERENCE_MODEL_ID,
        raw_score=raw_score,
        ecg_quality=record.ecg_quality,
        source="MOCK_INFERENCE_V0_FIXTURE_SCORE",
    )
