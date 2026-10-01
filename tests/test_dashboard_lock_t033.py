"""T033 DASHBOARD_UI_V1 component lock: creation is reproducible, tampering with any bound
file is detected, and -- as of the C034-UI-E2E successor (DASHBOARD_UI_V1_1) -- the
predecessor lock file itself remains preserved byte-identical even though live verify() now
correctly reports drift for the files that moved to the successor."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from nhm.hashing import hash_file
from scripts.verify_dashboard_ui_t033 import verify

ROOT = Path(__file__).resolve().parents[1]
LOCK_PATH = ROOT / "artifacts/DASHBOARD_UI_V1.lock.json"


def test_lock_file_exists_with_correct_status() -> None:
    assert LOCK_PATH.exists(), "run scripts/freeze_dashboard_ui_t033.py"
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    assert lock["lock_id"] == "DASHBOARD_UI_V1"
    assert lock["status"] == "FROZEN_ENGINEERING_INTERFACE"


def test_lock_does_not_introduce_a_new_canonical_freeze_registry_id() -> None:
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    assert "freeze_id" not in lock
    assert lock["no_new_canonical_freeze_row"] is True


def test_lock_records_the_locked_frontend_path_mapping() -> None:
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    assert lock["logical_subsystem"] == "dashboard"
    assert lock["repository_path"] == "frontend/"
    assert lock["source_plan_path"] == "dashboard/"


def test_lock_file_itself_is_preserved_byte_identical_after_c034_supersession() -> None:
    """DASHBOARD_UI_V1 was superseded by DASHBOARD_UI_V1_1 at C034-UI-E2E (Section 26): the
    predecessor LOCK FILE must never be mutated in place, even though some of the files it
    bound (e.g. the monitoring route, the API client, vite.config.ts) have since legitimately
    moved on to the successor. See tests/test_c034_lock_versioning.py for the successor's own
    checks, and scripts/freeze_dashboard_ui_c034.py for the predecessor-SHA pin."""
    expected_sha = "a8f7c557001503017a392f8703260ee589f4453e413e09498482b018ca8ef1b6"
    assert hash_file(LOCK_PATH) == expected_sha


def test_verify_now_correctly_reports_the_expected_post_supersession_drift() -> None:
    """A component that has moved to its successor must make the PREDECESSOR's own live-state
    verify() fail -- silently continuing to pass here would mean the "tamper" check is not
    actually sensitive to real file changes."""
    with pytest.raises(RuntimeError, match="DASHBOARD_UI_V1_TAMPER"):
        verify()


def test_verify_detects_tamper_on_any_bound_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    shadow_root = tmp_path / "repo"
    (shadow_root / "artifacts").mkdir(parents=True)
    (shadow_root / "artifacts/DASHBOARD_UI_V1.lock.json").write_text(
        LOCK_PATH.read_text(encoding="utf-8"), encoding="utf-8"
    )
    for relative_path in lock["bound_artifacts"]:
        destination = shadow_root / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative_path, destination)
    # verify() also reads artifacts/API_RUNTIME_V1.lock.json directly (not just its hash).
    api_runtime_destination = shadow_root / "artifacts/API_RUNTIME_V1.lock.json"
    api_runtime_destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / "artifacts/API_RUNTIME_V1.lock.json", api_runtime_destination)

    monkeypatch.setattr("scripts.verify_dashboard_ui_t033.ROOT", shadow_root)

    tampered = shadow_root / "frontend/src/lib/dashboard/state-presentation.ts"
    tampered.write_text(tampered.read_text(encoding="utf-8") + "\n// tamper\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="DASHBOARD_UI_V1_TAMPER"):
        verify()


def test_bound_artifacts_cover_the_core_dashboard_source_files() -> None:
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    bound = set(lock["bound_artifacts"])
    for required in (
        "frontend/src/lib/api/nhm-v1.ts",
        "frontend/src/lib/dashboard/state-presentation.ts",
        "frontend/src/lib/dashboard/session.svelte.ts",
        "frontend/src/routes/monitoring/+page.svelte",
    ):
        assert required in bound
