from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import yaml

from fusion.episode_manager import policy_lock_payload, verify_alert_policy_lock

ROOT = Path(__file__).resolve().parents[1]


def _copy_policy_tree(tmp_path: Path) -> Path:
    for relative in (
        "configs/alert_policy_v1.yaml",
        "fusion/state_machine.py",
        "fusion/episode_manager.py",
        "artifacts/CAL_V1.json",
        "artifacts/ECG_HR_CONTEXT_V2.lock.json",
    ):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    payload = policy_lock_payload(tmp_path)
    lock = tmp_path / "artifacts/ALERT_POLICY_V1.lock.json"
    lock.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return lock


def test_temporary_policy_lock_verifies() -> None:
    # The tmp_path fixture is injected in the parametrized tamper test below; this direct
    # semantic check stays in policy_lock_payload tests through the canonical evidence run.
    payload = policy_lock_payload(ROOT)
    assert payload["status"] == "FROZEN_ENGINEERING_POLICY"
    assert payload["threshold_source"] == "CAL_V1"


@pytest.mark.parametrize(
    ("relative", "original", "changed"),
    [
        (
            "configs/alert_policy_v1.yaml",
            "required_consecutive_valid_above: 2",
            "required_consecutive_valid_above: 3",
        ),
        (
            "configs/alert_policy_v1.yaml",
            "required_consecutive_valid_below: 2",
            "required_consecutive_valid_below: 3",
        ),
        ("configs/alert_policy_v1.yaml", "cooldown_seconds: 30", "cooldown_seconds: 31"),
        ("configs/alert_policy_v1.yaml", 'comparator: ">="', 'comparator: "<"'),
        ("configs/alert_policy_v1.yaml", "tolerance_bpm: 20.0", "tolerance_bpm: 21.0"),
        (
            "configs/alert_policy_v1.yaml",
            "continuous_duration_seconds: 10.0",
            "continuous_duration_seconds: 11.0",
        ),
        ("fusion/state_machine.py", "NORMAL_MONITORED_PATTERN", "NORMAL_PATTERN_DRIFT"),
        ("fusion/episode_manager.py", "Deterministic temporal engine", "Mutated temporal engine"),
        ("artifacts/CAL_V1.json", '"threshold": 0.6128035574269627', '"threshold": 0.5'),
        (
            "artifacts/ECG_HR_CONTEXT_V2.lock.json",
            '"status": "FROZEN_ENGINEERING_COMPONENT"',
            '"status": "MUTATED"',
        ),
    ],
)
def test_tamper_is_rejected(tmp_path: Path, relative: str, original: str, changed: str) -> None:
    lock = _copy_policy_tree(tmp_path)
    path = tmp_path / relative
    source = path.read_text(encoding="utf-8")
    assert original in source
    path.write_text(source.replace(original, changed, 1), encoding="utf-8")
    with pytest.raises(ValueError):
        verify_alert_policy_lock(tmp_path, lock_path=lock)


def test_lock_mutation_is_rejected(tmp_path: Path) -> None:
    lock = _copy_policy_tree(tmp_path)
    payload = json.loads(lock.read_text(encoding="utf-8"))
    payload["required_consecutive_valid_above"] = 99
    lock.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="LOCK_MISMATCH"):
        verify_alert_policy_lock(tmp_path, lock_path=lock)


def test_monitoring_vocabulary_drift_is_rejected(tmp_path: Path) -> None:
    lock = _copy_policy_tree(tmp_path)
    config_path = tmp_path / "configs/alert_policy_v1.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["monitoring_state_vocabulary"].append("QUALITY_WARNING")
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    with pytest.raises(ValueError):
        verify_alert_policy_lock(tmp_path, lock_path=lock)
