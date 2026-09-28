import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "contracts/HARDWARE_DATA_CONTRACT_V1.md"

EXPECTED_VERIFICATION_REQUIRED_ITEMS = [
    "Exact ESP32 variant",
    "ADC resolution",
    "ADC attenuation/reference voltage",
    "AD8232 actual gain",
    "AD8232 analog filtering",
    "Electrode placement",
    "MAX30102 register configuration",
    "Actual achieved ECG sample rate",
    "Actual achieved PPG sample rate",
    "Timer/sampling jitter",
    "Timestamp producer/origin (device vs. gateway/API vs. MongoDB)",
    "Transport packet format",
    "CRC/checksum behavior",
    "BPM derivation algorithm",
    "SpO2 derivation algorithm",
    "Algorithm/firmware versions",
    "Raw-count-to-physical-unit scaling",
]


def _text() -> str:
    return CONTRACT.read_text(encoding="utf-8")


def _registry_rows() -> list[tuple[str, str]]:
    text = _text()
    return re.findall(r"\|\s*\d+\s*\|\s*(.+?)\s*\|\s*(\S+)\s*\|", text)


def test_contract_identity_is_not_prematurely_frozen() -> None:
    text = _text()
    assert "contract_id: HARDWARE_DATA_CONTRACT_V1" in text
    assert "spec_version: 2.2" in text
    assert "status: DRAFT_FOR_G1_VERIFICATION" in text
    assert "status: FROZEN" not in text


def test_every_critical_physical_fact_is_marked_verification_required() -> None:
    rows = {item: status for item, status in _registry_rows()}
    for item in EXPECTED_VERIFICATION_REQUIRED_ITEMS:
        assert item in rows, f"missing hardware registry row: {item}"
        assert rows[item] == "VERIFICATION_REQUIRED", (
            f"{item} must remain VERIFICATION_REQUIRED, got {rows[item]!r}"
        )
    assert len(rows) == len(EXPECTED_VERIFICATION_REQUIRED_ITEMS)


def test_target_sampling_rates_are_locked_by_spec_not_measured() -> None:
    text = _text()
    assert "canonical project sampling target: 250 Hz" in text
    assert "canonical target: 100 Hz red + IR" in text
    assert "[LOCKED_BY_SPEC]" in text
    for forbidden in ("device has been measured at 250 Hz", "confirmed 250 Hz", "achieved 250 Hz"):
        assert forbidden not in text


def test_observed_mongodb_v0_is_documented_as_incompatible() -> None:
    text = _text()
    assert "does **not** satisfy the canonical V1 contract" in text
    for field in ("bpm", "spo2", "ecg", "timestamp"):
        assert field in text
    for missing_field in (
        "participant_id",
        "session_id",
        "device_id",
        "firmware_version",
        "sample_index",
        "sensor_config_hash",
    ):
        assert missing_field in text


def test_gap_policy_is_referenced_but_not_implemented() -> None:
    text = _text()
    assert "GAP_POLICY_V1" in text
    assert "is **not implemented** at T003" in text or "not implemented" in text.casefold()


def test_contract_identifiers_are_present() -> None:
    text = _text()
    for identifier in (
        "SPEC_VERSION = 2.2",
        "HARDWARE_DATA_CONTRACT_V1",
        "SAMPLE_SCHEMA_V1",
        "LABEL_SCHEMA_V1",
        "AAMI_SVF_WINDOW_V1",
        "AAMI_SVF_MAP_V1",
        "API_SCHEMA_V1",
    ):
        assert identifier in text
