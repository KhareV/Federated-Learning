import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/mongodb_observed_v0.json"


def test_observed_fixture_shape_and_timestamp_serialization() -> None:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert fixture["fixture_origin"] == "example_observed_hardware_document"
    assert fixture["physiological_validity"] == "UNVERIFIED"
    assert set(fixture["document"]) == {"_id", "bpm", "spo2", "ecg", "timestamp"}

    timestamp = fixture["document"]["timestamp"]
    parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    assert parsed.isoformat(timespec="milliseconds") == "2026-09-14T08:08:33.011+00:00"

