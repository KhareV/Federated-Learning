from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from evaluation.quality_aware_alerts import sha256
from scripts.verify_t023 import verify, verify_method_lock

ROOT = Path(__file__).resolve().parents[1]


def test_frozen_trace_and_metrics_verify() -> None:
    result = verify()
    assert result["status"] == "PASS_WITH_WARNINGS"
    assert result["arm_pairing"] == "PASS"
    assert result["metric_traceability"] == "PASS"
    assert result["healthy_context_preservation"] == 1.0


def test_reproducibility_hashes_are_identical() -> None:
    report = json.loads((ROOT / "reports/t023/reproducibility.json").read_text())
    assert report["scenario_manifest_sha_run1"] == report["scenario_manifest_sha_run2"]
    assert report["event_trace_sha_run1"] == report["event_trace_sha_run2"]
    assert report["BIDMC_metric_sha_run1"] == report["BIDMC_metric_sha_run2"]
    assert report["WEARABLE_SIM_metric_sha_run1"] == report["WEARABLE_SIM_metric_sha_run2"]
    assert report["identical"] is True


def test_method_lock_detects_bound_artifact_tamper(tmp_path: Path) -> None:
    lock = json.loads((ROOT / "artifacts/QUALITY_AWARE_EXPERIMENT_V1.lock.json").read_text())
    for relative in lock["paths"].values():
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    lock_path = tmp_path / "artifacts/QUALITY_AWARE_EXPERIMENT_V1.lock.json"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / "artifacts/QUALITY_AWARE_EXPERIMENT_V1.lock.json", lock_path)
    verify_method_lock(tmp_path)
    config = tmp_path / "configs/quality_aware_experiment_v1.yaml"
    config.write_text(config.read_text() + "\n# mutation\n")
    with pytest.raises(RuntimeError, match="METHOD_LOCK_MISMATCH"):
        verify_method_lock(tmp_path)


def test_event_trace_mutation_changes_identity(tmp_path: Path) -> None:
    source = ROOT / "reports/t023/episode_event_trace.csv"
    copy = tmp_path / "trace.csv"
    shutil.copyfile(source, copy)
    assert sha256(copy) == sha256(source)
    copy.write_text(copy.read_text().replace("NORMAL_MONITORED_PATTERN", "MUTATED", 1))
    assert sha256(copy) != sha256(source)
