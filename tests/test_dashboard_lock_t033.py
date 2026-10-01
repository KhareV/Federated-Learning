"""T033 DASHBOARD_UI_V1 component lock: creation is reproducible, verification passes against
the current repository state, and tampering with any bound file is detected."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

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


def test_verify_passes_against_current_repository_state() -> None:
    result = verify()
    assert result["status"] == "PASS"
    assert result["bound_artifacts"] > 0


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
