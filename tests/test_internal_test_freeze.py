from __future__ import annotations

import json
from pathlib import Path

import pytest

from evaluation.internal_test import InternalTestError, verify_internal_test_freeze
from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]


def test_canonical_internal_test_freeze_verifies() -> None:
    assert verify_internal_test_freeze(ROOT)["status"] == "PASS"


def test_guard_binds_prediction_and_statistical_outputs() -> None:
    guard = json.loads((ROOT / "artifacts/internal_test_access_v1.json").read_text())
    assert guard["status"] == "COMPLETED"
    assert guard["model_inference_passes"] == 1
    for relative, expected in guard["result_sha256"].items():
        assert hash_file(ROOT / relative) == expected


def test_prediction_mutation_is_detected(monkeypatch: pytest.MonkeyPatch) -> None:
    original = hash_file

    def changed(path: str | Path) -> str:
        value = Path(path)
        if value.name == "internal_test_predictions.csv":
            return "0" * 64
        return original(value)

    monkeypatch.setattr("evaluation.internal_test.hash_file", changed)
    with pytest.raises(InternalTestError, match="INTERNAL_TEST_RESULT_HASH_MISMATCH"):
        verify_internal_test_freeze(ROOT)


def test_method_mutation_is_detected(monkeypatch: pytest.MonkeyPatch) -> None:
    original = hash_file

    def changed(path: str | Path) -> str:
        value = Path(path)
        if value.name == "bootstrap.py":
            return "f" * 64
        return original(value)

    monkeypatch.setattr("evaluation.internal_test.hash_file", changed)
    with pytest.raises(InternalTestError, match="POST_TEST_METHOD_MUTATION"):
        verify_internal_test_freeze(ROOT)


def test_cal_v1_and_model_remain_hash_bound() -> None:
    report = json.loads((ROOT / "reports/internal_test.json").read_text())
    assert report["model_sha256"] == hash_file(ROOT / "checkpoints/MODEL_V1.pt")
    assert report["calibration_sha256"] == hash_file(ROOT / "artifacts/CAL_V1.json")
    assert report["threshold_comparator"] == ">="
    assert report["no_post_test_tuning"] is True
    assert "patient_macro_AUPRC" not in json.dumps(report)

