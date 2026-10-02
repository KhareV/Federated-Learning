"""C032-NORM-RUNTIME successor-lock tests: API_RUNTIME_V1_1 is an additive successor that
preserves its predecessor byte-identical, restores PREPROC_V1 PER_WINDOW_ZSCORE_V1
normalization ownership, and never claims an API contract change."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from nhm.hashing import hash_file
from scripts.verify_api_runtime_v1_1_c032 import verify as verify_api_runtime_v1_1

ROOT = Path(__file__).resolve().parents[1]


def test_api_runtime_v1_1_exists_and_preserves_predecessor() -> None:
    lock = json.loads((ROOT / "artifacts/API_RUNTIME_V1_1.lock.json").read_text(encoding="utf-8"))
    assert lock["predecessor_id"] == "API_RUNTIME_V1"
    assert lock["normalization_id"] == "PER_WINDOW_ZSCORE_V1"
    assert lock["normalization_owner"] == "api.runtime.ProductionRuntime.infer"
    assert lock["normalization_epsilon"] == 1e-8
    assert lock["hr_branch_receives_normalized_input"] is False
    assert lock["api_contract_byte_identical_to_predecessor"] is True
    assert "freeze_id" not in lock

    predecessor = (ROOT / "artifacts/API_RUNTIME_V1.lock.json").read_text(encoding="utf-8")
    predecessor_lock = json.loads(predecessor)
    assert predecessor_lock["lock_id"] == "API_RUNTIME_V1"
    assert predecessor_lock["status"] == "FROZEN_ENGINEERING_INTERFACE"
    assert hash_file(ROOT / "artifacts/API_RUNTIME_V1.lock.json") == lock["predecessor_sha256"]


def test_api_runtime_v1_1_verify_passes() -> None:
    result = verify_api_runtime_v1_1()
    assert result["status"] == "PASS"
    assert result["predecessor_preserved"] is True


def test_api_runtime_v1_1_equivalence_is_exact() -> None:
    lock = json.loads((ROOT / "artifacts/API_RUNTIME_V1_1.lock.json").read_text(encoding="utf-8"))
    assert lock["runtime_equivalence_decision_agreement_fraction"] == 1.0
    assert lock["runtime_equivalence_rows_compared"] > 0


def test_api_runtime_v1_1_detects_tamper(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    lock = json.loads((ROOT / "artifacts/API_RUNTIME_V1_1.lock.json").read_text(encoding="utf-8"))
    shadow_root = tmp_path / "repo"
    (shadow_root / "artifacts").mkdir(parents=True)
    (shadow_root / "artifacts/API_RUNTIME_V1_1.lock.json").write_text(
        (ROOT / "artifacts/API_RUNTIME_V1_1.lock.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    for relative_path in lock["bound_artifacts"]:
        destination = shadow_root / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative_path, destination)
    predecessor_destination = shadow_root / "artifacts/API_RUNTIME_V1.lock.json"
    predecessor_destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / "artifacts/API_RUNTIME_V1.lock.json", predecessor_destination)

    monkeypatch.setattr("scripts.verify_api_runtime_v1_1_c032.ROOT", shadow_root)
    tampered = shadow_root / "api/runtime.py"
    tampered.write_text(tampered.read_text(encoding="utf-8") + "\n# tamper\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="API_RUNTIME_V1_1_TAMPER"):
        verify_api_runtime_v1_1()


def test_predecessor_lock_is_byte_identical_to_its_frozen_sha() -> None:
    successor = json.loads(
        (ROOT / "artifacts/API_RUNTIME_V1_1.lock.json").read_text(encoding="utf-8")
    )
    assert (
        hash_file(ROOT / "artifacts/API_RUNTIME_V1.lock.json") == successor["predecessor_sha256"]
    )
