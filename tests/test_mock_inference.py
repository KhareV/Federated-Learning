from dataclasses import dataclass

from deployment.mock_inference import MOCK_INFERENCE_MODEL_ID, run


@dataclass(frozen=True)
class _FakeObserved:
    timestamp_us: int
    ecg_raw: int | None
    ecg_quality: str
    source: str = "SYNTHETIC_PHYSIOLOGY"


def test_model_id_is_not_model_v1() -> None:
    assert MOCK_INFERENCE_MODEL_ID == "MOCK_INFERENCE_V0"
    assert MOCK_INFERENCE_MODEL_ID != "MODEL_V1"


def test_deterministic_for_identical_input() -> None:
    record = _FakeObserved(timestamp_us=1000, ecg_raw=2300, ecg_quality="VALID")
    first = run(record)
    second = run(record)
    assert first == second


def test_none_ecg_raw_produces_none_score() -> None:
    record = _FakeObserved(timestamp_us=1000, ecg_raw=None, ecg_quality="UNUSABLE")
    result = run(record)
    assert result.raw_score is None


def test_score_is_within_structural_bounds() -> None:
    for ecg_raw in (0, 1, 2200, 10_000, 100_000):
        record = _FakeObserved(timestamp_us=0, ecg_raw=ecg_raw, ecg_quality="VALID")
        result = run(record)
        assert result.raw_score is not None
        assert 0.0 <= result.raw_score <= 1.0


def test_result_carries_no_calibration_claim() -> None:
    record = _FakeObserved(timestamp_us=0, ecg_raw=2300, ecg_quality="VALID")
    result = run(record)
    fields = {f for f in vars(result)}
    assert "calibration_domain" not in fields
    assert "calibration_id" not in fields
    assert "source_domain_calibrated_probability" not in fields


def test_output_only_depends_on_observed_fields() -> None:
    """The score must be a pure function of the declared observed input fields."""
    a = _FakeObserved(
        timestamp_us=5, ecg_raw=2300, ecg_quality="VALID", source="SYNTHETIC_PHYSIOLOGY"
    )
    b = _FakeObserved(timestamp_us=5, ecg_raw=2300, ecg_quality="VALID", source="MITDB_REPLAY")
    result_a = run(a)
    result_b = run(b)
    assert result_a.raw_score == result_b.raw_score
