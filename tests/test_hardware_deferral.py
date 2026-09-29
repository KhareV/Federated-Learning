import re
from pathlib import Path

from nhm.coverage import read_csv

ROOT = Path(__file__).resolve().parents[1]
HARDWARE_CONTRACT = ROOT / "contracts/HARDWARE_DATA_CONTRACT_V1.md"
DEFERRAL_PLAN = ROOT / "docs/HARDWARE_DEFERRED_EXECUTION_PLAN.md"
LEGACY_FINDINGS = ROOT / "docs/LEGACY_FIRMWARE_V0_FINDINGS.md"


def test_t004_is_blocked_not_pass() -> None:
    rows = {row["task_id"]: row for row in read_csv(ROOT / "manifests/task_registry_v1.csv")}
    assert rows["T004"]["status"] == "BLOCKED"
    assert rows["T001"]["status"] == "PASS"
    assert rows["T002"]["status"] == "PASS"
    assert rows["T003"]["status"] == "PASS"
    assert rows["T005"]["status"] == "PASS"
    assert rows["T006"]["status"] == "PASS"
    assert rows["T007"]["status"] == "PASS"
    assert rows["T008"]["status"] == "PASS"
    assert rows["T009"]["status"] == "PASS"
    assert rows["T010"]["status"] == "PASS"
    assert rows["T011"]["status"] == "PASS"
    assert rows["T012"]["status"] == "PASS"
    assert rows["T013"]["status"] == "PASS"
    assert rows["T014"]["status"] == "PASS"
    assert rows["T015"]["status"] == "PASS"
    assert rows["T016"]["status"] == "NOT_STARTED"


def test_g1_and_g16_are_not_passed() -> None:
    gates = {row["gate_id"]: row for row in read_csv(ROOT / "manifests/gate_registry_v1.csv")}
    assert gates["G1"]["status"] != "PASS"
    assert gates["G16"]["status"] != "PASS"
    assert gates["G0"]["status"] == "PASS"


def test_hardware_data_contract_freeze_remains_not_frozen() -> None:
    freezes = {
        row["freeze_id"]: row for row in read_csv(ROOT / "manifests/freeze_registry_v1.csv")
    }
    assert freezes["F02"]["current_status"] == "NOT_FROZEN"


def test_block_reason_is_recorded_in_task_notes() -> None:
    rows = {row["task_id"]: row for row in read_csv(ROOT / "manifests/task_registry_v1.csv")}
    assert "BLOCKED_HARDWARE" in rows["T004"]["notes"]


def test_deferral_plan_documents_required_facts() -> None:
    text = DEFERRAL_PLAN.read_text(encoding="utf-8")
    assert "BLOCKED_HARDWARE" in text
    assert "hardware_available: false" in text
    assert "continue software with fixtures; block wearable evidence" in text
    assert "G1 hardware verification" in text
    assert "real WEARABLE_V1 evidence" in text
    assert "G16 wearable validation" in text
    assert (
        "resume_condition: Physical ESP32/AD8232/MAX30102 system available for bench testing"
        in text
    )


def test_legacy_firmware_findings_have_no_credentials() -> None:
    text = LEGACY_FINDINGS.read_text(encoding="utf-8")
    assert "LEGACY_FIRMWARE_V0" in text
    assert "OBSERVED_FROM_SOURCE" in text
    assert "PROTOTYPE_HEURISTIC_ONLY" in text
    # A credential value would appear as key=value/key: "value" assignment syntax next to a
    # password-like keyword; the document may discuss rotating a password without ever
    # printing one, so only flag lines with an actual assignment operator.
    assignment = re.compile(r"(password|ssid|wifi_pass|secret)\s*[:=]\s*\S", re.IGNORECASE)
    assert assignment.search(text) is None
    credential_uri = re.compile(r"[A-Za-z0-9_\-]{6,}:[^\s/@]{4,}@")
    assert credential_uri.search(text) is None


def test_legacy_firmware_source_not_fabricated() -> None:
    text = LEGACY_FINDINGS.read_text(encoding="utf-8")
    assert "exact source archive: UNAVAILABLE_IN_REPOSITORY" in text
    assert not (ROOT / "firmware/legacy/LEGACY_FIRMWARE_V0.ino").exists()


def test_legacy_firmware_field_mapping_boundaries() -> None:
    text = LEGACY_FINDINGS.read_text(encoding="utf-8")
    assert "2048" in text
    assert "must never be interpreted as a physiological ECG reading" in text
    assert "must not be mapped to the canonical `hr_ecg_bpm` field" in text


def test_hardware_verification_required_registry_is_unchanged_by_deferral() -> None:
    contract = HARDWARE_CONTRACT.read_text(encoding="utf-8")
    rows = re.findall(r"\|\s*\d+\s*\|\s*(.+?)\s*\|\s*VERIFICATION_REQUIRED\s*\|", contract)
    assert len(rows) == 17
    assert "status: FROZEN" not in contract
    assert "status: DRAFT_FOR_G1_VERIFICATION" in contract
