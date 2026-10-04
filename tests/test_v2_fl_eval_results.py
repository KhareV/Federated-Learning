"""V2-FL-EVAL-001 post-exposure tests: one-shot accounting, prediction-table integrity, claim
wording, prediction-only statistics reproducibility, firewall, method immutability, protected
artifacts, registry transition and the absence of selection/promotion."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np
import pytest
import yaml

import evaluation.model_v2_fl_eval as ev
from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/model_v2/v2_fl_eval_001"
ROSTER = yaml.safe_load((ROOT / ev.FAMILY_RELATIVE).read_text())["models"]


def _j(name: str) -> dict:
    return json.loads((OUT / name).read_text())


def test_guards_completed_one_invocation_and_second_attempt_blocked() -> None:
    audit = _j("one_shot_guard_audit.json")
    assert audit["status"] == "PASS"
    assert audit["states"] == {"INTERNAL_TEST": "COMPLETED", "INCART": "COMPLETED"}
    assert audit["family_invocations"] == {"INTERNAL_TEST": 1, "INCART": 1}
    assert audit["second_attempt_blocked_deterministically"] is True
    assert audit["excluded_checkpoints_evaluated"] is False
    with pytest.raises(ev.FamilyEvalError, match="ALREADY_CONSUMED"):
        ev.begin_guard(ROOT, "INTERNAL_TEST", {})
    with pytest.raises(ev.FamilyEvalError, match="ALREADY_CONSUMED"):
        ev.begin_guard(ROOT, "INCART", {})
    assert audit["historical_guards"] == {"internal": "COMPLETED", "incart": "COMPLETED"}


@pytest.mark.parametrize(("dataset", "rows"), [("INTERNAL_TEST", 2157), ("INCART", 26864)])
def test_prediction_tables_complete_aligned_and_threshold_consistent(dataset: str,
                                                                      rows: int) -> None:
    expected = (ev.internal_expectations(ROOT) if dataset == "INTERNAL_TEST"
                else ev.incart_expectations(ROOT))
    manifest = _j("inference_manifest.json")
    key = "internal_test" if dataset == "INTERNAL_TEST" else "incart"
    assert len(manifest[key]) == 20
    for binding in manifest[key]:
        path = OUT / "predictions" / dataset / f"{binding['checkpoint_id']}.csv.gz"
        assert hash_file(path) == binding["table_sha256"] and binding["rows"] == rows
        table = ev.read_prediction_table(path)
        ev.validate_prediction_table(table, expected["ids"])
        assert table["label"].tolist() == expected["labels"]
        np.testing.assert_allclose(table["probability"],
                                   1 / (1 + np.exp(-table["raw_logit"])), atol=1e-6)
    assert {b["checkpoint_id"] for b in manifest[key]} == {m["id"] for m in ROSTER}
    assert {b["checkpoint_sha256"] for b in manifest[key]} == {
        m["checkpoint_sha256"] for m in ROSTER}


def test_populations_match_frozen_expectations_and_claim_wording() -> None:
    report = _j("population_report.json")
    internal, incart = report["INTERNAL_TEST"], report["INCART"]
    assert (internal["candidate_windows"], internal["eligible_windows"], internal["positive"],
            internal["negative"], internal["frozen_groups"],
            internal["contributing_clusters"]) == (2520, 2157, 1156, 1001, 7, 6)
    assert internal["zero_eligible_groups"] == ["MITDB_P107"]
    assert (incart["records"], incart["clusters"], incart["eligible_windows"]) == (75, 32, 26864)
    assert internal["all_20_models_identical_ordered_example_ids_equal_frozen_expectation"]
    assert incart["all_20_models_identical_ordered_example_ids_equal_frozen_expectation"]
    assert "NOT project-globally unseen" in internal["claim"]
    assert "NOT project-blind" in incart["claim"]
    summary = (OUT / "tables/results_tables.md").read_text()
    assert "POST-FREEZE EXTERNAL FL SECOND-LOOK -- NOT PROJECT-BLIND" in summary
    assert "FL-LINEAGE HELD-OUT" in summary
    assert "never previously seen" not in summary.lower()


def test_statistics_follow_the_frozen_bootstrap_contract() -> None:
    for name, clusters in (("internal_test_statistics.json", 6), ("incart_statistics.json", 32)):
        data = _j(name)
        boot = data["bootstrap"]
        assert boot["B"] == 2000 and boot["seed"] == 20260927 and boot["multiplicity_preserved"]
        assert boot["slots_per_replicate"] == clusters == data["clusters"]
        assert boot["rejection_or_redraw"] is False and boot["p_values"] == "NOT_COMPUTED"
        assert len(data["models"]) == 20 and len(data["comparisons"]) == 23
        for model in data["models"].values():
            ci = model["bootstrap_95"]["AUPRC"]
            assert ci["valid_replicates"] + ci["invalid_replicates"] == 2000
            assert ci["ci_lower_95"] <= ci["ci_upper_95"]
            for patient in model["patients"]:
                assert {"windows", "positives", "negatives", "AUPRC", "AUROC",
                        "F1_at_0_5"} <= set(patient)
    assert _j("internal_test_statistics.json")["windows"] == 2157
    assert _j("incart_statistics.json")["windows"] == 26864


def test_predeclared_estimands_are_reported() -> None:
    internal = _j("internal_test_statistics.json")
    primary = internal["comparisons"]["V2_FEDAVG_IID_minus_V1_FEDAVG_IID"]
    assert primary["family"] == "architecture_effect"
    assert {"AUPRC", "patient_macro_F1"} <= set(primary["delta"])
    secondary = internal["comparisons"]["V2_FEDPROX_IID_minus_V2_FEDAVG_IID"]
    assert secondary["family"] == "fedprox_effect"
    point = internal["models"]["V2_FEDAVG_IID"]
    assert "AUPRC" in point["bootstrap_95"] and "patient_macro_F1" in point["bootstrap_95"]
    rows = list(csv.DictReader((OUT / "tables/paired_effects.csv").open()))
    assert {r["dataset"] for r in rows} == {"INTERNAL_TEST", "INCART"}
    assert len(rows) == 2 * 23 * 2
    shifts = list(csv.DictReader((OUT / "tables/shift_v2_models.csv").open()))
    assert {r["model"] for r in shifts} == {m["id"] for m in ROSTER if m["generation"] == "V2"}


@pytest.mark.parametrize("label", ["run_1", "run_2"])
def test_fresh_process_prediction_only_reproduction(label: str) -> None:
    data = json.loads((OUT / f"verification/reproduction_{label}.json").read_text())
    assert data["status"] == "PASS" and data["all_identical"] is True
    assert data["checkpoints_loaded"] is False and data["source_data_opened"] is False


def test_no_calibration_no_selection_no_promotion_and_immutable_method() -> None:
    firewall = _j("firewall_audit.json")
    assert firewall["status"] == "PASS"
    assert set(firewall["partitions_accessed"]) <= {"INTERNAL_TEST", "INCART"}
    assert not (firewall["CALIBRATION_accessed"] or firewall["NSTDB_accessed"]
                or firewall["BIDMC_accessed"] or firewall["WEARABLE_accessed"]
                or firewall["CAL_V1_used"] or firewall["CAL_V2_used"]
                or firewall["threshold_tuned"])
    assert _j("method_immutability_post_exposure.json")["status"] == "PASS"
    assert _j("protected_artifact_audit.json")["status"] == "PASS"
    protocol = yaml.safe_load((ROOT / "configs/model_v2/fl_eval_protocol_v1.yaml").read_text())
    assert protocol["pass_rule"] == "performance_independent"
    references = _j("historical_frozen_centralized_references.json")
    assert references["rerun_in_this_phase"] is False
    assert "HISTORICAL FROZEN REFERENCE" in references["label"]


def test_v2fleg0_criteria_and_registry_transition() -> None:
    criteria = _j("v2fleg0_criteria.json")
    flags = criteria["criteria"]
    if flags["regression"] == "PENDING_STAGE1":  # transient while the regression runs
        assert all(v is True for k, v in flags.items() if k != "regression")
    else:
        assert criteria["status"] == "PASS" and all(v is True for v in flags.values())
    assert criteria["performance_magnitude_is_a_criterion"] is False

    def rows(name: str) -> list[dict]:
        with (ROOT / f"manifests/model_v2/{name}_registry_v1.csv").open(newline="") as handle:
            return list(csv.DictReader(handle))

    tasks = {r["task_id"]: r["status"] for r in rows("task")}
    gates = {r["gate_id"]: r["status"] for r in rows("gate")}
    if flags["regression"] != "PENDING_STAGE1":
        assert tasks["V2-FL-EVAL-001"] == "PASS" and gates["V2FLEG0"] == "PASS"
