from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from models.baseline_freeze import BaselineFreezeError, verify_baseline_freeze

ROOT = Path(__file__).resolve().parents[1]


def test_committed_f07_lock_verifies() -> None:
    assert verify_baseline_freeze(ROOT)["status"] == "PASS"


@pytest.mark.parametrize(
    "relative_path",
    [
        "manifests/features/BASELINE_FEATURES_V1.schema.json",
        "configs/baseline_v1.yaml",
        "artifacts/baselines/BASELINE_V1/feature_transform.joblib",
        "artifacts/baselines/BASELINE_V1/majority.json",
        "artifacts/baselines/BASELINE_V1/logistic.joblib",
        "artifacts/baselines/BASELINE_V1/random_forest.joblib",
        "manifests/preprocessing/PREPROC_V1.lock.json",
    ],
)
def test_f07_tamper_detection(tmp_path: Path, relative_path: str) -> None:
    lock = json.loads((ROOT / "manifests/baselines/BASELINE_V1.lock.json").read_text())
    paths = set(lock["artifact_sha256"]) | set(lock["upstream_frozen_sha256"])
    for bound in paths:
        target = tmp_path / bound
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / bound, target)
    lock_target = tmp_path / "manifests/baselines/BASELINE_V1.lock.json"
    lock_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "manifests/baselines/BASELINE_V1.lock.json", lock_target)
    target = tmp_path / relative_path
    data = bytearray(target.read_bytes())
    data[-1] ^= 1
    target.write_bytes(data)
    with pytest.raises(BaselineFreezeError, match=r"F07_(HASH|UPSTREAM)_MISMATCH"):
        verify_baseline_freeze(tmp_path)
