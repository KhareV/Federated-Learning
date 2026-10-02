"""T035-REPRO successor-lock tests: DASHBOARD_UI_V1_3 is an additive successor that preserves
its predecessor byte-identical, declares the @types/node devDependency fix, and never claims a
frontend application source / scientific / state / contract change."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from nhm.hashing import hash_file
from scripts.verify_dashboard_ui_v1_3_t035 import verify as verify_dashboard_ui_v1_3

ROOT = Path(__file__).resolve().parents[1]


def test_dashboard_ui_v1_3_exists_and_preserves_predecessor() -> None:
    lock = json.loads((ROOT / "artifacts/DASHBOARD_UI_V1_3.lock.json").read_text(encoding="utf-8"))
    assert lock["predecessor_id"] == "DASHBOARD_UI_V1_2"
    assert lock["scientific_state_semantics_changed"] is False
    assert lock["state_wording_changed"] is False
    assert lock["api_contract_changed"] is False
    assert lock["frontend_application_source_changed"] is False
    assert lock["frontend_dependency_declaration_changed"] is True
    assert lock["types_node_added"]["package"] == "@types/node"
    assert "freeze_id" not in lock

    predecessor = json.loads(
        (ROOT / "artifacts/DASHBOARD_UI_V1_2.lock.json").read_text(encoding="utf-8")
    )
    assert predecessor["lock_id"] == "DASHBOARD_UI_V1_2"
    assert predecessor["status"] == "FROZEN_ENGINEERING_INTERFACE"
    assert hash_file(ROOT / "artifacts/DASHBOARD_UI_V1_2.lock.json") == lock["predecessor_sha256"]


def test_dashboard_ui_v1_3_verify_passes() -> None:
    result = verify_dashboard_ui_v1_3()
    assert result["status"] == "PASS"
    assert result["predecessor_preserved"] is True


def test_dashboard_ui_v1_3_proves_svelte_check_fix() -> None:
    lock = json.loads((ROOT / "artifacts/DASHBOARD_UI_V1_3.lock.json").read_text(encoding="utf-8"))
    assert lock["clean_checkout_svelte_check_errors_before_fix"] == 13
    assert lock["clean_checkout_svelte_check_errors_after_fix"] == 0


def test_types_node_declared_in_frontend_package_json() -> None:
    package_json = json.loads(
        (ROOT / "frontend/package.json").read_text(encoding="utf-8")
    )
    assert package_json["devDependencies"]["@types/node"] == "26.6.4"


def test_dashboard_ui_v1_3_detects_tamper(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    lock = json.loads((ROOT / "artifacts/DASHBOARD_UI_V1_3.lock.json").read_text(encoding="utf-8"))
    shadow_root = tmp_path / "repo"
    (shadow_root / "artifacts").mkdir(parents=True)
    (shadow_root / "artifacts/DASHBOARD_UI_V1_3.lock.json").write_text(
        (ROOT / "artifacts/DASHBOARD_UI_V1_3.lock.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    for relative_path in lock["bound_artifacts"]:
        destination = shadow_root / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative_path, destination)
    predecessor_destination = shadow_root / "artifacts/DASHBOARD_UI_V1_2.lock.json"
    predecessor_destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / "artifacts/DASHBOARD_UI_V1_2.lock.json", predecessor_destination)

    monkeypatch.setattr("scripts.verify_dashboard_ui_v1_3_t035.ROOT", shadow_root)
    tampered = shadow_root / "frontend/package.json"
    tampered.write_text(tampered.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="DASHBOARD_UI_V1_3_TAMPER"):
        verify_dashboard_ui_v1_3()


def test_predecessor_lock_is_byte_identical_to_its_frozen_sha() -> None:
    successor = json.loads(
        (ROOT / "artifacts/DASHBOARD_UI_V1_3.lock.json").read_text(encoding="utf-8")
    )
    assert (
        hash_file(ROOT / "artifacts/DASHBOARD_UI_V1_2.lock.json")
        == successor["predecessor_sha256"]
    )
