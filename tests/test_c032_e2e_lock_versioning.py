"""C032-NORM-RUNTIME E2E/dashboard successor-lock tests: DASHBOARD_UI_V1_2 and
E2E_REPLAY_SOFTWARE_V1_2 are additive successors that preserve their predecessors
byte-identical, never claim G21 PASS, and correctly record (without requiring equality to) the
superseded unnormalized runtime digest.

As of the T035-REPRO successor (DASHBOARD_UI_V1_3), the DASHBOARD_UI_V1_2 lock FILE itself
remains preserved byte-identical even though live verify() now correctly reports drift for
frontend/package.json & frontend/package-lock.json, which moved to DASHBOARD_UI_V1_3 (see
tests/test_t035_lock_versioning.py for the successor's own checks)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nhm.hashing import hash_file
from scripts.verify_dashboard_ui_v1_2_c032 import verify as verify_dashboard_ui_v1_2
from scripts.verify_e2e_replay_v1_2_c032 import verify as verify_e2e_replay_v1_2

ROOT = Path(__file__).resolve().parents[1]


def test_dashboard_ui_v1_2_exists_and_preserves_predecessor() -> None:
    lock = json.loads((ROOT / "artifacts/DASHBOARD_UI_V1_2.lock.json").read_text(encoding="utf-8"))
    assert lock["predecessor_id"] == "DASHBOARD_UI_V1_1"
    assert lock["scientific_state_semantics_changed"] is False
    assert lock["state_wording_changed"] is False
    assert lock["api_contract_changed"] is False
    assert lock["frontend_source_changed"] is False
    assert "freeze_id" not in lock


def test_dashboard_ui_v1_2_lock_file_preserved_byte_identical_after_t035_supersession() -> None:
    expected_sha = "62341027cf4723e221ea58facc66bf2dca65b34fe1e513209bf887c407393382"
    assert hash_file(ROOT / "artifacts/DASHBOARD_UI_V1_2.lock.json") == expected_sha


def test_dashboard_ui_v1_2_verify_now_correctly_reports_post_t035_drift() -> None:
    with pytest.raises(RuntimeError, match="DASHBOARD_UI_V1_2_TAMPER"):
        verify_dashboard_ui_v1_2()


def test_e2e_replay_software_v1_2_never_claims_g21_pass() -> None:
    lock = json.loads(
        (ROOT / "artifacts/E2E_REPLAY_SOFTWARE_V1_2.lock.json").read_text(encoding="utf-8")
    )
    assert lock["predecessor_id"] == "E2E_REPLAY_SOFTWARE_V1_1"
    assert lock["is_final_g21_lock"] is False
    assert lock["g21_status"] == "NON_PASS_PENDING_T030_REAL_WEARABLE"


def test_e2e_replay_software_v1_2_digest_is_new_and_superseded_digest_is_preserved() -> None:
    lock = json.loads(
        (ROOT / "artifacts/E2E_REPLAY_SOFTWARE_V1_2.lock.json").read_text(encoding="utf-8")
    )
    predecessor = json.loads(
        (ROOT / "artifacts/E2E_REPLAY_SOFTWARE_V1_1.lock.json").read_text(encoding="utf-8")
    )
    assert lock["superseded_unnormalized_runtime_digest"] == predecessor["public_semantic_digest"]
    assert lock["public_semantic_digest"] != lock["superseded_unnormalized_runtime_digest"]
    assert lock["public_semantic_digest_unchanged_from_predecessor"] is False
    assert lock["run_1_equals_run_2"] is True


def test_e2e_replay_software_v1_2_superseded_by_v1_3_with_preserved_lock() -> None:
    """V2-013 legitimately changed the route source bound by V1_2 (model-identity fix), so the
    V1_2 live verifier now reports drift on that file. The lock file itself is preserved
    byte-identical and the V1_3 successor verifies."""
    successor = json.loads(
        (ROOT / "artifacts/E2E_REPLAY_SOFTWARE_V1_3.lock.json").read_text(encoding="utf-8")
    )
    assert hash_file(ROOT / "artifacts/E2E_REPLAY_SOFTWARE_V1_2.lock.json") == (
        successor["predecessor_sha256"]
    )
    with pytest.raises(RuntimeError, match="E2E_REPLAY_SOFTWARE_V1_2_TAMPER"):
        verify_e2e_replay_v1_2()
    from scripts.verify_e2e_replay_v1_3_v2013 import verify as verify_v1_3

    result = verify_v1_3()
    assert result["status"] == "PASS"
    assert result["g21_status"] == "NON_PASS_PENDING_T030_REAL_WEARABLE"
