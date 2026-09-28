import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from simulation.fixtures import (
    MANIFEST_FIXTURE_PATH,
    OBSERVED_FIXTURE_PATH,
    TRUTH_FIXTURE_PATH,
    build_smoke_session,
    render_fixture_files,
)
from simulation.types import SimulationTruth
from simulation.wearable import generate_participant, iter_observed_records

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_SCHEMA = json.loads((ROOT / "contracts/sample_schema_v1.json").read_text(encoding="utf-8"))


def _sample_validator() -> Draft202012Validator:
    Draft202012Validator.check_schema(SAMPLE_SCHEMA)
    return Draft202012Validator(SAMPLE_SCHEMA, format_checker=FormatChecker())


def test_same_seed_produces_identical_participant() -> None:
    first = generate_participant(1, 20260927)
    second = generate_participant(1, 20260927)
    assert first == second


def test_different_seed_can_produce_different_participant() -> None:
    a = generate_participant(1, 20260927)
    b = generate_participant(1, 1)
    assert a != b


def test_same_seed_produces_identical_session_records() -> None:
    session_a = build_smoke_session()
    session_b = build_smoke_session()
    records_a = [r.to_canonical_dict() for r in iter_observed_records(session_a)]
    records_b = [r.to_canonical_dict() for r in iter_observed_records(session_b)]
    assert records_a == records_b


def test_fixture_regeneration_matches_checked_in_files() -> None:
    observed_lines, truth_lines, manifest = render_fixture_files()
    checked_in_observed = (
        (ROOT / OBSERVED_FIXTURE_PATH).read_text(encoding="utf-8").strip().splitlines()
    )
    checked_in_truth = (ROOT / TRUTH_FIXTURE_PATH).read_text(encoding="utf-8").strip().splitlines()
    checked_in_manifest = json.loads((ROOT / MANIFEST_FIXTURE_PATH).read_text(encoding="utf-8"))
    assert observed_lines == checked_in_observed
    assert truth_lines == checked_in_truth
    assert manifest == checked_in_manifest


def _load_observed() -> list[dict]:
    lines = (ROOT / OBSERVED_FIXTURE_PATH).read_text(encoding="utf-8").strip().splitlines()
    return [json.loads(line) for line in lines]


def test_every_observed_record_is_schema_valid() -> None:
    validator = _sample_validator()
    for record in _load_observed():
        errors = list(validator.iter_errors(record))
        assert errors == [], (record, errors)


def test_observed_records_carry_synthetic_provenance() -> None:
    for record in _load_observed():
        assert record["source"] == "SYNTHETIC_PHYSIOLOGY"
        assert record["participant_id"].startswith("SIM_P")
        assert record["contract_version"] == "SAMPLE_SCHEMA_V1"


def test_no_real_hardware_provenance_appears() -> None:
    for record in _load_observed():
        assert record["source"] != "WEARABLE_V1"
        assert "WEARABLE_V1" not in record["participant_id"]

    manifest = json.loads((ROOT / MANIFEST_FIXTURE_PATH).read_text(encoding="utf-8"))
    assert manifest["dataset_id"] == "WEARABLE_SIM_V1"
    assert manifest["dataset_id"] != "WEARABLE_V1"


def test_observed_records_have_no_truth_only_fields() -> None:
    truth_only_fields = {
        "true_activity",
        "latent_hr",
        "latent_spo2",
        "scheduled_fault",
        "actual_fault_active",
        "true_signal_quality",
        "expected_monitoring_state",
        "segment_name",
        "segment_kind",
    }
    for record in _load_observed():
        assert not (truth_only_fields & set(record)), record


def test_timestamps_and_indexes_are_monotonic_and_valid() -> None:
    records = _load_observed()
    indexes = [record["sample_index"] for record in records]
    timestamps = [record["timestamp_us"] for record in records]
    assert indexes == sorted(indexes)
    assert indexes == list(range(len(records)))
    assert timestamps == sorted(timestamps)
    assert len(set(timestamps)) == len(timestamps)
    assert all(index >= 0 for index in indexes)
    assert all(timestamp >= 0 for timestamp in timestamps)


def test_truth_fixture_covers_every_observed_record_in_order() -> None:
    observed = _load_observed()
    truth_lines = (ROOT / TRUTH_FIXTURE_PATH).read_text(encoding="utf-8").strip().splitlines()
    truth = [json.loads(line) for line in truth_lines]
    assert len(truth) == len(observed)
    for observed_record, truth_record in zip(observed, truth, strict=True):
        assert truth_record["sample_index"] == observed_record["sample_index"]
        assert truth_record["participant_id"] == observed_record["participant_id"]
        assert truth_record["session_id"] == observed_record["session_id"]
        assert set(truth_record) == set(SimulationTruth.__dataclass_fields__)
