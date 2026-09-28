"""api/app.py — minimal in-process T005 vertical-slice adapter.

This is NOT the production FastAPI application; T032 owns that. There is no HTTP server,
no WebSocket, no authentication, no CORS, no database access, and no MongoDB here. This
module only assembles a serializable `FixtureApiResponseV0` from an `ObservedRecord`, proving
the fixture -> MOCK_INFERENCE_V0 -> FIXTURE_STATE_POLICY_V0 -> API-facing-result architecture.

`contracts/API_SCHEMA_V1.json` defines the future production `/v1/infer-window` contract,
which requires fields (calibration domain/id/patient count, source-domain calibrated
probability, frozen threshold, alert_policy_id, ...) that do not exist yet (no MODEL_V1,
CAL_V1, PREPROC_V1, or ALERT_POLICY_V1 at T005). `FixtureApiResponseV0` is therefore a
separate, clearly-named structure — it does not claim to satisfy API_SCHEMA_V1, and the
production schema is not weakened to accommodate it.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Protocol

from deployment.mock_inference import run as run_mock_inference
from fusion.state_machine import FIXTURE_STATE_POLICY_ID, classify_safe

FIXTURE_API_RESPONSE_VERSION = "FixtureApiResponseV0"
FUTURE_PRODUCTION_CONTRACT = "API_SCHEMA_V1"


@dataclass(frozen=True)
class FixtureApiResponseV0:
    fixture_response_version: str
    timestamp_us: int
    participant_id: str
    session_id: str
    model_id: str
    raw_score: float | None
    ecg_quality: str
    monitoring_state: str
    fixture_state_policy_id: str
    source: str
    future_production_contract: str
    provenance_note: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ObservedApiInput(Protocol):
    """Structural type for the observed fields this adapter is allowed to read."""

    timestamp_us: int
    ecg_raw: int | None
    ecg_quality: str
    source: str
    participant_id: str
    session_id: str


def process_observed_record(record: ObservedApiInput) -> FixtureApiResponseV0:
    """fixture -> MOCK_INFERENCE_V0 -> FIXTURE_STATE_POLICY_V0 -> serializable slice result."""
    inference = run_mock_inference(record)
    monitoring_state = classify_safe(record, inference)
    return FixtureApiResponseV0(
        fixture_response_version=FIXTURE_API_RESPONSE_VERSION,
        timestamp_us=record.timestamp_us,
        participant_id=record.participant_id,
        session_id=record.session_id,
        model_id=inference.model_id,
        raw_score=inference.raw_score,
        ecg_quality=inference.ecg_quality,
        monitoring_state=monitoring_state,
        fixture_state_policy_id=FIXTURE_STATE_POLICY_ID,
        source=record.source,
        future_production_contract=FUTURE_PRODUCTION_CONTRACT,
        provenance_note=(
            "T005 mock vertical-slice response (MOCK_INFERENCE_V0 / FIXTURE_STATE_POLICY_V0). "
            "Not MODEL_V1, not CAL_V1, not ALERT_POLICY_V1, not a calibrated probability, "
            "and not a disease diagnosis. The production API_SCHEMA_V1 contract "
            "implementation belongs to T032."
        ),
    )
