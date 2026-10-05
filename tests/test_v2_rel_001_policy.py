"""V2-REL-001 policy tests: policy content, evaluator discipline (frozen-evidence only, no
hard-coded ACCEPT, no data access), lock integrity and historical-disposition preservation."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
POLICY = yaml.safe_load((ROOT / "configs/model_v2/system_v2_release_policy_v1.yaml").read_text())
EVALUATOR = (ROOT / "scripts/evaluate_system_v2_release.py").read_text()


def test_policy_declares_late_creation_and_no_preregistration() -> None:
    assert POLICY["release_level"] == "RESEARCH_SOFTWARE_OPERATIONAL_DEFAULT"
    assert POLICY["scientific_preregistration_claim"] is False
    assert "AFTER" in POLICY["evidence_timing_disclosure"]
    assert "CLINICAL_RELEASE" in POLICY["not_release_levels"]


def test_policy_blockers_and_limitations_are_complete() -> None:
    assert [b["id"] for b in POLICY["hard_blockers"]] == [f"H{n:02d}" for n in range(1, 25)]
    assert [x["id"] for x in POLICY["non_blocking_known_limitations"]] == [
        f"L{n:02d}" for n in range(1, 10)]
    target = POLICY["default_target"]
    assert target["model"] == "MODEL_V2_FINAL"
    assert "any V2 FL checkpoint" in target["not_deployed"]
    assert POLICY["api_policy"]["new_schema_version"] == "forbidden"


def test_claim_rules_forbid_overstatement() -> None:
    forbidden = " | ".join(POLICY["claim_rules"]["forbidden_claims"])
    for phrase in ("differential privacy", "hospital deployment", "real wearable validation",
                   "trained federatively", "retroactive MODEL_V2 scientific promotion"):
        assert phrase in forbidden


def test_evaluator_derives_decision_and_touches_no_waveform_data() -> None:
    assert 'decision = "ACCEPT" if not failed' in EVALUATOR
    assert '"manual_override": False' in EVALUATOR
    for banned in ("load_population", "guarded_population", "train_local_epoch", "fit_cal",
                   "data/raw", "data/processed", "torch.load", "check_partition_allowed"):
        assert banned not in EVALUATOR, banned
    assert "ACCEPT\"\n" not in EVALUATOR.split("def evaluate")[0]


def test_historical_disposition_is_untouched() -> None:
    decision = json.loads(
        (ROOT / "reports/model_v2/v2_007/promotion_decision.json").read_text())
    lock = json.loads(
        (ROOT / "manifests/model_v2/MODEL_V2_VALIDATION_DECISION_V1.lock.json").read_text())
    assert decision["decision"] == "MODEL_V2_NOT_PROMOTED_RELEASE_CI"
    assert decision["promotion_eligible"] is False
    assert hash_file(ROOT / "reports/model_v2/v2_007/promotion_decision.json") == lock[
        "promotion_decision_sha256"]


def test_lock_binds_policy_files_and_excludes_lifecycle_test() -> None:
    lock = json.loads((ROOT / "artifacts/SYSTEM_V2_RELEASE_POLICY_V1.lock.json").read_text())
    assert lock["frozen_before_decision_evaluation"] is True
    assert lock["operational_default_at_freeze"] == "MODEL_V1"
    assert not any("current_lifecycle" in p for p in lock["bound_artifacts"])
    for path, digest in lock["bound_artifacts"].items():
        assert hash_file(ROOT / path) == digest, path
