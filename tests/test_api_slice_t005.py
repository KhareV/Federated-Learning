import json
from dataclasses import dataclass

from api.app import (
    FIXTURE_API_RESPONSE_VERSION,
    FUTURE_PRODUCTION_CONTRACT,
    process_observed_record,
)

PROHIBITED_WORDS = ("ARRHYTHMIA", "DISEASE", "DIAGNOSIS", "CARDIAC_EMERGENCY")


@dataclass(frozen=True)
class _Record:
    timestamp_us: int
    ecg_raw: int | None
    ecg_quality: str
    source: str
    participant_id: str
    session_id: str
    ppg_quality: str | None = "VALID"
    ppg_red_raw: int | None = 100
    ppg_ir_raw: int | None = 100
    spo2_pct: float | None = 98.0


def _normal_record() -> _Record:
    return _Record(
        timestamp_us=1000,
        ecg_raw=2300,
        ecg_quality="VALID",
        source="SYNTHETIC_PHYSIOLOGY",
        participant_id="SIM_P000001",
        session_id="SIM_S000001",
    )


def test_response_is_json_serializable() -> None:
    response = process_observed_record(_normal_record())
    serialized = json.dumps(response.to_dict())
    reloaded = json.loads(serialized)
    assert reloaded["monitoring_state"] == response.monitoring_state


def test_response_reports_correct_monitoring_state() -> None:
    response = process_observed_record(_normal_record())
    assert response.monitoring_state == "NORMAL_MONITORED_PATTERN"

    unusable = _Record(
        timestamp_us=2000,
        ecg_raw=None,
        ecg_quality="UNUSABLE",
        source="SYNTHETIC_PHYSIOLOGY",
        participant_id="SIM_P000001",
        session_id="SIM_S000001",
    )
    assert process_observed_record(unusable).monitoring_state == "RECHECK_SENSOR"


def test_response_makes_mock_provenance_explicit() -> None:
    response = process_observed_record(_normal_record())
    assert response.model_id == "MOCK_INFERENCE_V0"
    assert response.fixture_state_policy_id == "FIXTURE_STATE_POLICY_V0"
    assert response.fixture_response_version == FIXTURE_API_RESPONSE_VERSION
    assert "MOCK_INFERENCE_V0" in response.provenance_note
    assert "FIXTURE_STATE_POLICY_V0" in response.provenance_note


def test_no_fake_calibration_or_model_evidence() -> None:
    response = process_observed_record(_normal_record())
    fields = set(response.to_dict())
    for forbidden_field in (
        "calibration_domain",
        "calibration_id",
        "calibration_patient_count",
        "source_domain_calibrated_probability",
        "threshold",
        "alert_policy_id",
    ):
        assert forbidden_field not in fields
    assert "MODEL_V1" not in response.to_dict().values()
    assert "CAL_V1" not in response.to_dict().values()


def test_no_disease_diagnosis_wording() -> None:
    response = process_observed_record(_normal_record())
    text = json.dumps(response.to_dict())
    for word in PROHIBITED_WORDS:
        assert word not in text


def test_does_not_claim_to_satisfy_production_api_schema() -> None:
    response = process_observed_record(_normal_record())
    assert response.future_production_contract == FUTURE_PRODUCTION_CONTRACT
    assert "contract_version" not in response.to_dict()
    assert "target" not in response.to_dict()
    assert "raw_probability" not in response.to_dict()
