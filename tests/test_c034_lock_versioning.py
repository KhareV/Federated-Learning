"""C034-UI-E2E successor-lock tests: DASHBOARD_UI_V1_1 and E2E_REPLAY_SOFTWARE_V1_1 are
additive successors that preserve their predecessors byte-identical, never claim G21 PASS, and
never claim a scientific/wording/contract change.

As of the C032-NORM-RUNTIME successor (DASHBOARD_UI_V1_2), the DASHBOARD_UI_V1_1 lock FILE
itself remains preserved byte-identical even though live verify() now correctly reports drift
for contracts/openapi_v1.json, which moved to DASHBOARD_UI_V1_2 (see
tests/test_c032_e2e_lock_versioning.py for the successor's own checks). E2E_REPLAY_SOFTWARE_V1_1
binds no file that changed at C032-NORM-RUNTIME, so its own verify() is unaffected and still
passes."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from nhm.hashing import hash_file
from scripts.verify_dashboard_ui_c034 import verify as verify_dashboard_ui_c034
from scripts.verify_e2e_replay_c034 import verify as verify_e2e_replay_c034

ROOT = Path(__file__).resolve().parents[1]


def test_dashboard_ui_v1_1_exists_and_preserves_predecessor() -> None:
    lock = json.loads(
        (ROOT / "artifacts/DASHBOARD_UI_V1_1.lock.json").read_text(encoding="utf-8")
    )
    assert lock["predecessor_id"] == "DASHBOARD_UI_V1"
    assert lock["scientific_state_semantics_changed"] is False
    assert lock["state_wording_changed"] is False
    assert lock["api_contract_changed"] is False
    assert "freeze_id" not in lock

    predecessor = (ROOT / "artifacts/DASHBOARD_UI_V1.lock.json").read_text(encoding="utf-8")
    predecessor_lock = json.loads(predecessor)
    assert predecessor_lock["lock_id"] == "DASHBOARD_UI_V1"
    assert predecessor_lock["status"] == "FROZEN_ENGINEERING_INTERFACE"


def test_dashboard_ui_v1_1_lock_file_preserved_byte_identical_after_c032_supersession() -> None:
    expected_sha = "39066bdaa7b54a11b1895ae659991ba441c7511d19822ad492fb744d7a903e19"
    assert hash_file(ROOT / "artifacts/DASHBOARD_UI_V1_1.lock.json") == expected_sha


def test_dashboard_ui_v1_1_verify_now_correctly_reports_post_c032_drift() -> None:
    with pytest.raises(RuntimeError, match="DASHBOARD_UI_V1_1_TAMPER"):
        verify_dashboard_ui_c034()


def test_e2e_replay_software_v1_1_exists_and_never_claims_g21_pass() -> None:
    lock = json.loads(
        (ROOT / "artifacts/E2E_REPLAY_SOFTWARE_V1_1.lock.json").read_text(encoding="utf-8")
    )
    assert lock["predecessor_id"] == "E2E_REPLAY_SOFTWARE_V1"
    assert lock["is_final_g21_lock"] is False
    assert lock["g21_status"] == "NON_PASS_PENDING_T030_REAL_WEARABLE"
    assert lock["public_semantic_digest"] == (
        "e3f8607617d3fc7cce7be58752340047d120815653cce36acfac5e8b8bc099b3"
    )
    assert lock["public_semantic_digest_unchanged_from_predecessor"] is True


def test_e2e_replay_software_v1_1_verify_passes() -> None:
    result = verify_e2e_replay_c034()
    assert result["status"] == "PASS"
    assert result["predecessor_preserved"] is True
    assert result["g21_status"] == "NON_PASS_PENDING_T030_REAL_WEARABLE"


def test_dashboard_ui_v1_1_detects_tamper(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    lock = json.loads(
        (ROOT / "artifacts/DASHBOARD_UI_V1_1.lock.json").read_text(encoding="utf-8")
    )
    shadow_root = tmp_path / "repo"
    (shadow_root / "artifacts").mkdir(parents=True)
    (shadow_root / "artifacts/DASHBOARD_UI_V1_1.lock.json").write_text(
        (ROOT / "artifacts/DASHBOARD_UI_V1_1.lock.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    for relative_path in lock["bound_artifacts"]:
        destination = shadow_root / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative_path, destination)
    predecessor_destination = shadow_root / "artifacts/DASHBOARD_UI_V1.lock.json"
    predecessor_destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / "artifacts/DASHBOARD_UI_V1.lock.json", predecessor_destination)

    monkeypatch.setattr("scripts.verify_dashboard_ui_c034.ROOT", shadow_root)
    tampered = shadow_root / "frontend/src/lib/dashboard/replay.ts"
    tampered.write_text(tampered.read_text(encoding="utf-8") + "\n// tamper\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="DASHBOARD_UI_V1_1_TAMPER"):
        verify_dashboard_ui_c034()


def test_predecessor_locks_are_byte_identical_to_their_frozen_shas() -> None:
    dashboard_successor = json.loads(
        (ROOT / "artifacts/DASHBOARD_UI_V1_1.lock.json").read_text(encoding="utf-8")
    )
    from nhm.hashing import hash_file

    assert (
        hash_file(ROOT / "artifacts/DASHBOARD_UI_V1.lock.json")
        == dashboard_successor["predecessor_sha256"]
    )

    e2e_successor = json.loads(
        (ROOT / "artifacts/E2E_REPLAY_SOFTWARE_V1_1.lock.json").read_text(encoding="utf-8")
    )
    assert (
        hash_file(ROOT / "artifacts/E2E_REPLAY_SOFTWARE_V1.lock.json")
        == e2e_successor["predecessor_sha256"]
    )
