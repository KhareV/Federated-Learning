from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from preprocessing.freeze import PreprocFreezeError, verify_preproc_freeze

ROOT = Path(__file__).resolve().parents[1]


def test_committed_f06_lock_verifies() -> None:
    assert verify_preproc_freeze(ROOT)["status"] == "PASS"


@pytest.mark.parametrize(
    ("relative_path", "old", "new"),
    [
        ("configs/preproc_v1.yaml", "window_samples: 2500", "window_samples: 2000"),
        ("configs/preproc_v1.yaml", "stride_samples: 1250", "stride_samples: 1000"),
        ("configs/preproc_v1.yaml", "short_gap_max_ms: 100.0", "short_gap_max_ms: 90.0"),
        ("configs/preproc_v1.yaml", 'signal_interval: "[t-10s,t)"', 'signal_interval: "[t-8s,t)"'),
        ("configs/preproc_v1.yaml", "timestamp_backdating: false", "timestamp_backdating: true"),
        ("configs/quality_v1.yaml", "short_gap: DEGRADED_UNLESS_HARD_FAILURE", "short_gap: VALID"),
        ("manifests/labels/AAMI_SVF_MAP_V1.yaml", "AAMI_SVF_MAP_V1", "AAMI_SVF_MAP_V2"),
        ("manifests/splits/MITDB_SPLIT_V1.csv", "MITDB_SPLIT_V1", "MITDB_SPLIT_V2"),
    ],
)
def test_f06_tamper_detection(
    tmp_path: Path, relative_path: str, old: str, new: str
) -> None:
    lock = json.loads(
        (ROOT / "manifests/preprocessing/PREPROC_V1.lock.json").read_text(encoding="utf-8")
    )
    for bound in lock["artifact_sha256"]:
        target = tmp_path / bound
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / bound, target)
    lock_target = tmp_path / "manifests/preprocessing/PREPROC_V1.lock.json"
    lock_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "manifests/preprocessing/PREPROC_V1.lock.json", lock_target)
    target = tmp_path / relative_path
    text = target.read_text(encoding="utf-8")
    assert old in text
    target.write_text(text.replace(old, new, 1), encoding="utf-8")
    with pytest.raises(PreprocFreezeError, match="F06_HASH_MISMATCH"):
        verify_preproc_freeze(tmp_path)


@pytest.mark.parametrize(
    "relative_path",
    [
        "preprocessing/coefficients/MITDB_360_TO_250_V1.npy",
        "preprocessing/coefficients/PREPROC_V1_ECG_FILTER_V1.npy",
    ],
)
def test_f06_coefficient_tamper_detection(tmp_path: Path, relative_path: str) -> None:
    lock = json.loads(
        (ROOT / "manifests/preprocessing/PREPROC_V1.lock.json").read_text(encoding="utf-8")
    )
    for bound in lock["artifact_sha256"]:
        target = tmp_path / bound
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / bound, target)
    lock_target = tmp_path / "manifests/preprocessing/PREPROC_V1.lock.json"
    lock_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "manifests/preprocessing/PREPROC_V1.lock.json", lock_target)
    target = tmp_path / relative_path
    data = bytearray(target.read_bytes())
    data[-1] ^= 1
    target.write_bytes(data)
    with pytest.raises(PreprocFreezeError, match="F06_HASH_MISMATCH"):
        verify_preproc_freeze(tmp_path)
