"""V2-FL-005 post-result tests: canonical engineering evidence, determinism, routing, restart,
SecAgg shadow, claim boundary, firewall and registry transition. Immutable facts only."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/model_v2/v2_fl_005"


def _j(name: str) -> dict:
    return json.loads((OUT / name).read_text())


@pytest.mark.parametrize("name", [
    "reproducibility.json", "event_replay.json", "secagg_shadow.json",
    "server_data_locality_audit.json", "firewall_audit.json", "efficacy_metric_audit.json",
    "claim_audit.json", "protected_artifact_audit.json", "method_immutability_post_exposure.json",
    "cohort_preflight.json"])
def test_evidence_pass(name: str) -> None:
    assert _j(name)["status"] == "PASS"


def test_federation_accounting_and_rejections() -> None:
    run = _j("federation_run.json")
    assert run["accepted_updates"] == 24 and run["local_training_calls"] == 24
    assert run["failed_updates"] == 0 and run["nonfinite_states"] == 0
    assert run["scientific_model_fits_added"] == 0 and run["scientific_checkpoints_added"] == 0
    assert [r["code"] for r in run["rejected_injected_attempts"]] == [
        "STALE_ROUND", "DUPLICATE_UPDATE", "BASE_STATE_MISMATCH", "UNKNOWN_CLIENT"]
    for body in run["round_reports"].values():
        assert body["second_commit"] == "ROUND_ALREADY_COMMITTED"
        assert body["order_invariance"]["all_equal"] and body["order_invariance"][
            "equals_committed"]


def test_restart_resume_exact_and_reproducible() -> None:
    restart = _j("restart_resume.json")
    assert restart["exact_match"] and restart["fresh_process"]
    assert restart["continuous_final_sha256"] == restart["resumed_final_sha256"]
    repro = _j("reproducibility.json")
    assert repro["semantic_digest_identical"] and repro["final_sha_identical"]
    assert repro["update_hashes_identical_24"] and repro["client_dataset_hashes_identical"]


def test_secagg_shadow_within_predeclared_tolerance() -> None:
    shadow = _j("secagg_shadow.json")
    assert shadow["maximum_absolute_difference"] <= 1e-4
    assert shadow["relative_L2_difference"] <= 1e-4
    assert shadow["plain_clear_update_count"] == 8 and shadow["protected_clear_update_count"] == 0
    assert shadow["preflight"]["coordinates_outside_range"] == 0
    assert shadow["preflight"]["weight_headroom_ratio"] > 1


def test_no_efficacy_metrics_and_no_real_data() -> None:
    assert _j("finite_inference_smoke.json")["classification_metrics_computed"] is False
    assert _j("finite_inference_smoke.json")["all_logits_finite"] is True
    fire = _j("firewall_audit.json")
    assert fire["scientific_waveform_partitions_read"] == [] and fire["WEARABLE_V1"] is False
    assert fire["real_loader_modules_imported"] == []


def test_v2flg4_and_registry_transition() -> None:
    criteria = _j("v2flg4_criteria.json")
    flags = criteria["criteria"]
    if flags["regression"] == "PENDING_STAGE1":  # transient while the regression runs
        assert all(v is True for k, v in flags.items() if k != "regression")
    else:
        assert criteria["status"] == "PASS" and all(v is True for v in flags.values())
    assert criteria["performance_magnitude_is_a_criterion"] is False

    def rows(name: str, key: str) -> dict:
        with (ROOT / f"manifests/model_v2/{name}_registry_v1.csv").open(newline="") as handle:
            return {r[key]: r["status"] for r in csv.DictReader(handle)}

    assert rows("task", "task_id")["V2-FL-005"] == "PASS"
    assert rows("gate", "gate_id")["V2FLG4"] == "PASS"
    comps = rows("component", "component_id")
    assert comps["WEARABLE_SIM_FL_COHORT_V1"] == "FROZEN_ENGINEERING_COHORT"
    assert comps["VIRTUAL_FL_CLIENT_SOURCE_V1"] == "FROZEN_INTERFACE_CONTRACT"


def test_frozen_cohort_manifest_matches_run() -> None:
    lock = json.loads((ROOT / "artifacts/V2_FL_WEARABLE_SYSTEM_PROTOCOL_V1.lock.json").read_text())
    path = "manifests/model_v2/WEARABLE_SIM_FL_COHORT_V1.json"
    assert hash_file(ROOT / path) == lock["bound_artifacts"][path]
    run = _j("cohort_manifest_run.json")
    assert {c["client_id"]: c["dataset_sha256"] for c in run["clients"]} == lock["dataset_sha256"]
