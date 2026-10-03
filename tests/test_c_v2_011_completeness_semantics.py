"""C-V2-011-COMPLETENESS-SEMANTICS tests: the unsupported hard completeness gate is removed as a
source-authority correction, the failed diagnostic run is preserved verbatim, and nothing about
the Integrated-Gradients method, cases or attribution arrays changed."""

from __future__ import annotations

import csv
import json
import subprocess
from pathlib import Path

import pytest
import yaml

import scripts._v2_011_cases as cases
from evaluation.explain_v2 import gauss_legendre_rule
from evaluation.explain_v2_semantics import (
    EXCEEDS,
    LOCKED_STATUS,
    WITHIN,
    completeness_diagnostic,
    gates_v2g10,
)
from nhm.hashing import hash_file
from nhm.model_v2_explainability_guard import read_guard_state

ROOT = Path(__file__).resolve().parents[1]
V2_011 = ROOT / "reports/model_v2/v2_011"
METHOD_COMMIT = "1bb81d52876ff70dbc1eba742a2b1f1909b8523d"
FAILED_RUN_COMMIT = "ce1d055f37d7ddcb4a7c0c6117ba8c4e20450b51"


def _json(rel: str) -> dict:
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


def _csv(rel: str) -> list[dict[str, str]]:
    with (ROOT / rel).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=False)


def test_authority_audit_finds_no_hard_threshold() -> None:
    audit = _json("reports/model_v2/v2_011/completeness_semantics_authority_audit.json")
    assert audit["status"] == "PASS"
    assert audit["OLD_PROMPT_RULE"] == "ABS_LT_1E-3_OR_REL_LT_1E-3"
    assert audit["OLD_RULE_SOURCE"] == "V2_011_ASSISTANT_PROMPT / V1_IMPLEMENTATION_HEURISTIC"
    assert audit["LOCKED_V2_2_REQUIREMENT"] == (
        "RECORD_COMPLETENESS_CONVERGENCE_DELTA_AS_DIAGNOSTIC_METADATA")
    assert audit["HARD_NUMERICAL_THRESHOLD_IN_V2_2"] == "NONE"
    assert audit["CORRECTIVE_CLASSIFICATION"] == "UNSUPPORTED_HARD_GATE_REMOVED"
    assert audit["g17_blocking_criterion_absolute_or_relative_1e-3_present"] is False
    assert audit["g17_gate_text_requires_convergence_delta_saved"] is True
    assert all(audit["locked_v2_2_explainability_contract_requires"].values())
    for doc in audit["documents"].values():
        assert doc["explainability_paragraphs_containing_a_numeric_1e-3_threshold"] == []
        assert doc["sha256"] == hash_file(ROOT / doc["document"])
    assert "NOT a favorable result-driven" in audit["nature_of_correction"]


def test_failed_diagnostic_run_preserved_verbatim() -> None:
    manifest = _json("reports/model_v2/v2_011/failed_diagnostic_run_manifest.json")
    assert manifest["guard_state"] == "COMPLETED"
    for rel, digest in manifest["artifact_sha256"].items():
        if rel.endswith("case_access_guard.json"):
            continue  # guard file is expected to stay COMPLETED; state asserted separately
        assert hash_file(ROOT / rel) == digest, rel
    summary = _json("reports/model_v2/v2_011/failed_diagnostic_run_summary.json")
    assert summary["cases_exceeding_prompt_rule"] == ["FN", "FP", "TP"]
    assert summary["v2_011_status_marked_pass"] is False
    assert summary["explainability_v2_frozen"] is False
    assert read_guard_state(ROOT, "CASE_ACCESS")["state"] == "COMPLETED"
    for commit in (METHOD_COMMIT, FAILED_RUN_COMMIT):
        assert _git("merge-base", "--is-ancestor", commit, "HEAD").returncode == 0


def test_original_residuals_preserved_not_relabelled() -> None:
    rows = {r["case_type"]: r for r in _csv("reports/model_v2/v2_011/ig_completeness.csv")}
    assert float(rows["TP"]["absolute_delta"]) == pytest.approx(2.467e-2, rel=1e-3)
    assert float(rows["TN"]["absolute_delta"]) == pytest.approx(5.72e-4, rel=1e-2)
    assert float(rows["FP"]["absolute_delta"]) == pytest.approx(8.33e-3, rel=1e-2)
    assert float(rows["FN"]["absolute_delta"]) == pytest.approx(3.20e-3, rel=1e-2)
    assert [rows[c]["pass"] for c in ("TP", "TN", "FP", "FN")] == ["False", "True", "False",
                                                                  "False"]
    diag_rows = _csv("reports/model_v2/v2_011/ig_completeness_diagnostic.csv")
    diag = {r["case_type"]: r for r in diag_rows}
    for case, row in rows.items():
        assert float(diag[case]["completeness_absolute_delta"]) == pytest.approx(
            float(row["absolute_delta"]), abs=1e-12)
        assert float(diag[case]["completeness_relative_delta"]) == pytest.approx(
            float(row["relative_delta"]), abs=1e-9)
    assert {c: diag[c]["historical_heuristic_label"] for c in diag} == {
        "TP": EXCEEDS, "TN": WITHIN, "FP": EXCEEDS, "FN": EXCEEDS}
    assert {diag[c]["historical_v1_style_1e3_heuristic"] for c in ("TP", "FP", "FN")} == {
        "EXCEEDS_HEURISTIC"}
    assert diag["TN"]["historical_v1_style_1e3_heuristic"] == "PASS"
    assert all(d["locked_v2_2_explainability_status"] == LOCKED_STATUS for d in diag.values())


def test_diagnostic_never_gates_even_for_huge_residuals() -> None:
    huge = completeness_diagnostic(output=1.0, baseline_output=0.0, attribution_sum=50.0)
    assert huge["completeness_absolute_delta"] == 49.0
    assert huge["historical_heuristic_label"] == EXCEEDS
    assert huge["locked_v2_2_explainability_status"] == LOCKED_STATUS
    assert huge["numerical_completeness_gate"] == "NONE"
    assert gates_v2g10() is False
    zero = completeness_diagnostic(output=0.0, baseline_output=0.0, attribution_sum=0.0)
    assert zero["historical_heuristic_label"] == WITHIN


def test_successor_config_changes_only_completeness_semantics() -> None:
    sem = yaml.safe_load((ROOT / "configs/model_v2/explainability_v2_completeness_semantics_v2.yaml"
                          ).read_text())
    base = cases.load_config(ROOT)
    assert sem["id"] == "EXPLAINABILITY_V2_COMPLETENESS_SEMANTICS_V2"
    assert sem["original_method_commit"] == METHOD_COMMIT
    assert sem["failed_diagnostic_run_commit"] == FAILED_RUN_COMMIT
    unchanged = sem["unchanged_from_original_method"]
    for key in ("target", "baseline", "integration", "steps", "attribution", "tie_rule"):
        assert unchanged[key] == base[key]
    assert unchanged["visual_overlay"] == base["visual_overlay"]
    assert unchanged["steps"] == 64
    assert unchanged["ig_rerun_required_or_permitted_for_completeness"] is False
    comp = sem["completeness"]
    assert comp["numerical_completeness_gate"] == "NONE" and comp["gates_v2g10"] is False
    assert comp["historical_heuristic"]["role"] == "DESCRIPTIVE_ONLY_NEVER_A_GATE"
    assert {"more_ig_steps", "case_substitution"} <= set(comp["forbidden_responses"])
    assert "No quadrature step count, baseline, model, or case was changed" in " ".join(
        sem["required_report_wording"].split())


def test_gauss_legendre_remains_exactly_64_points() -> None:
    nodes, weights = gauss_legendre_rule()
    assert nodes.size == 64 and weights.sum() == pytest.approx(1.0, abs=1e-12)
    for steps in (63, 65, 128):
        with pytest.raises(ValueError):
            gauss_legendre_rule(steps)


@pytest.mark.parametrize("rel", [
    "evaluation/explain.py", "evaluation/explain_v2.py", "scripts/_v2_011_cases.py",
    "scripts/_v2_011_analysis.py", "configs/model_v2/explainability_v2.yaml",
    "configs/model_v2/error_analysis_v2.yaml",
    "reports/model_v2/v2_011/explainability_case_manifest.csv",
])
def test_ig_method_and_cases_byte_identical_to_method_commit(rel: str) -> None:
    assert _git("diff", "--quiet", METHOD_COMMIT, "HEAD", "--", rel).returncode == 0


def test_case_ids_and_attribution_arrays_unchanged() -> None:
    manifest = {r["case_type"]: r["example_id"]
                for r in _csv("reports/model_v2/v2_011/explainability_case_manifest.csv")}
    freeze = _json("reports/model_v2/v2_011/method_freeze.json")
    assert manifest == freeze["case_ids"]
    failed = _json("reports/model_v2/v2_011/failed_diagnostic_run_manifest.json")
    assert failed["frozen_case_ids"] == manifest
    for case in ("TP", "TN", "FP", "FN"):
        rel = f"reports/model_v2/v2_011/cases/{case}_attribution.csv"
        assert hash_file(ROOT / rel) == failed["artifact_sha256"][rel]


def test_semantics_lock_binds_everything_it_claims() -> None:
    lock = _json("artifacts/EXPLAINABILITY_V2_COMPLETENESS_SEMANTICS_V2.lock.json")
    assert lock["status"] == "FROZEN_SEMANTICS_CORRECTION"
    assert lock["numerical_completeness_gate"] == "NONE"
    assert lock["original_method_commit"] == METHOD_COMMIT
    assert lock["failed_diagnostic_run_commit"] == FAILED_RUN_COMMIT
    assert lock["case_ids_unchanged"] == _json(
        "reports/model_v2/v2_011/method_freeze.json")["case_ids"]
    for rel, digest in lock["bound_artifacts"].items():
        assert hash_file(ROOT / rel) == digest, rel
    assert len(lock["bound_artifacts"]) >= 15


def test_verifier_has_no_hard_completeness_failure_path() -> None:
    source = (ROOT / "models/explainability_v2_verify.py").read_text()
    assert "COMPLETENESS_FAILED" not in source
    assert "EXPLAINABILITY_V2_COMPLETENESS_FLAG" not in source
    assert "all_completeness_pass" not in source
    assert "completeness_diagnostic" in source


def test_model_and_calibration_unchanged() -> None:
    baseline = _json("reports/model_v2/v2_011/protected_baseline.json")["artifacts"]
    for rel in ("checkpoints/MODEL_V2_FINAL.pt", "artifacts/CAL_V2.json",
                "reports/model_v2/v2_010/runtime_acceptance_decision.json",
                "reports/model_v2/v2_010/internal_v2_predictions.csv"):
        assert hash_file(ROOT / rel) == baseline[rel]


def test_noise_guard_still_armed_and_preconditions_intact() -> None:
    state = read_guard_state(ROOT, "NOISE_TYPE")
    assert state["state"] in {"ARMED", "COMPLETED"}
    if state["state"] == "ARMED":
        assert state["preconditions"] == cases.observed_preconditions(ROOT, "NOISE_TYPE")
