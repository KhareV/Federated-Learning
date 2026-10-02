"""T032 API_RUNTIME_V1 component lock: creation is reproducible and tampering with any bound
file is detected. Mirrors the tamper-test style of tests/test_t029_* for GATEWAY_ARTIFACT_V1.

As of the C032-NORM-RUNTIME successor (API_RUNTIME_V1_1), the predecessor lock file itself
remains preserved byte-identical even though live verify() now correctly reports drift for
api/runtime.py and api/schemas.py, which moved to the successor (see
tests/test_c032_lock_versioning.py for the successor's own checks)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nhm.hashing import hash_file
from scripts.verify_api_runtime_t032 import verify

ROOT = Path(__file__).resolve().parents[1]
LOCK_PATH = ROOT / "artifacts/API_RUNTIME_V1.lock.json"


def test_lock_file_exists_with_correct_status() -> None:
    assert LOCK_PATH.exists(), "run scripts/freeze_api_runtime_t032.py"
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    assert lock["lock_id"] == "API_RUNTIME_V1"
    assert lock["status"] == "FROZEN_ENGINEERING_INTERFACE"


def test_lock_does_not_introduce_a_new_canonical_freeze_registry_id() -> None:
    """Section 5/98: API_RUNTIME_V1 is a component lock, not a new Fxx row -- F15 remains
    reserved for RELEASE_V1 / G22."""
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    assert "freeze_id" not in lock


def test_lock_file_itself_is_preserved_byte_identical_after_c032_supersession() -> None:
    """API_RUNTIME_V1 was superseded by API_RUNTIME_V1_1 at C032-NORM-RUNTIME: the
    predecessor LOCK FILE must never be mutated in place, even though api/runtime.py and
    api/schemas.py (files it bound) have since legitimately moved on to the successor."""
    expected_sha = "a6bfedc258977cdf27ecb36e7b326f69800c4897d4cacb09c796b280eebff971"
    assert hash_file(LOCK_PATH) == expected_sha


def test_verify_now_correctly_reports_the_expected_post_supersession_drift() -> None:
    """A component that has moved to its successor must make the PREDECESSOR's own live-state
    verify() fail -- silently continuing to pass here would mean the "tamper" check is not
    actually sensitive to real file changes."""
    with pytest.raises(RuntimeError, match="API_RUNTIME_V1_TAMPER"):
        verify()


def test_verify_detects_tamper_on_any_bound_file(tmp_path, monkeypatch) -> None:
    """Materializes only the files verify() actually reads (the lock plus its bound
    artifacts) into a throwaway shadow root -- the real repo includes multi-GB raw dataset
    directories that must never be copied just to run a unit test."""
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    shadow_root = tmp_path / "repo"
    (shadow_root / "artifacts").mkdir(parents=True)
    (shadow_root / "artifacts/API_RUNTIME_V1.lock.json").write_text(
        LOCK_PATH.read_text(encoding="utf-8"), encoding="utf-8"
    )
    for relative_path in lock["bound_artifacts"]:
        destination = shadow_root / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes((ROOT / relative_path).read_bytes())

    monkeypatch.setattr("scripts.verify_api_runtime_t032.ROOT", shadow_root)

    tampered = shadow_root / "api/app.py"
    tampered.write_text(tampered.read_text(encoding="utf-8") + "\n# tamper\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="API_RUNTIME_V1_TAMPER"):
        verify()


def test_bound_artifacts_cover_every_production_api_source_file() -> None:
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    bound = set(lock["bound_artifacts"])
    for required in ("api/app.py", "api/schemas.py", "api/runtime.py", "api/session.py"):
        assert required in bound


def test_calibration_and_policy_identifiers_match_upstream_frozen_artifacts() -> None:
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    cal = json.loads((ROOT / "artifacts/CAL_V1.json").read_text(encoding="utf-8"))
    assert lock["model_id"] == cal["model_id"] == "MODEL_V1"
    assert lock["calibration_id"] == cal["calibration_id"] == "CAL_V1"
    assert lock["calibration_patient_count"] == cal["calibration_patient_count"]
