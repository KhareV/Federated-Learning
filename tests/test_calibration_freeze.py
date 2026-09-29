from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from evaluation.calibration import CalibrationError, verify_cal_v1

ROOT = Path(__file__).resolve().parents[1]
CANONICAL = json.loads((ROOT / "artifacts/CAL_V1.json").read_text())


def write_artifact(tmp_path: Path, value: dict) -> Path:
    path = tmp_path / "CAL_V1.json"
    path.write_text(json.dumps(value, allow_nan=True))
    return path


def test_committed_cal_v1_verifies() -> None:
    result = verify_cal_v1(ROOT)
    assert result["status"] == "PASS"
    assert result["freeze_id"] == "F09"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("temperature", 0.0),
        ("temperature", float("nan")),
        ("threshold", -0.1),
        ("threshold", 1.1),
        ("fit_partition", "VALIDATION"),
        ("calibration_domain", "INCART"),
        ("calibration_patient_count", None),
        ("threshold_comparator", ">"),
        ("internal_test_accessed", True),
        ("external_data_accessed", True),
    ],
)
def test_semantic_tamper_detection(tmp_path: Path, field: str, value: object) -> None:
    artifact = copy.deepcopy(CANONICAL)
    artifact[field] = value
    with pytest.raises((CalibrationError, TypeError, ValueError)):
        verify_cal_v1(ROOT, write_artifact(tmp_path, artifact))


@pytest.mark.parametrize(
    "relative",
    [
        "checkpoints/MODEL_V1.pt",
        "checkpoints/MODEL_V1.manifest.json",
        "manifests/splits/MITDB_SPLIT_V1.csv",
        "manifests/preprocessing/PREPROC_V1.lock.json",
    ],
)
def test_upstream_hash_tamper_detection(tmp_path: Path, relative: str) -> None:
    artifact = copy.deepcopy(CANONICAL)
    artifact["upstream_sha256"][relative] = "0" * 64
    with pytest.raises(CalibrationError, match="CAL_V1_UPSTREAM_HASH_MISMATCH"):
        verify_cal_v1(ROOT, write_artifact(tmp_path, artifact))


def test_top_level_model_binding_tamper_detection(tmp_path: Path) -> None:
    artifact = copy.deepcopy(CANONICAL)
    artifact["model_checkpoint_sha256"] = "0" * 64
    with pytest.raises(CalibrationError, match="CAL_V1_SEMANTIC_MISMATCH"):
        verify_cal_v1(ROOT, write_artifact(tmp_path, artifact))
