"""V2-011 post-access results tests: guard completion, IG integrity, error-analysis semantics,
controlled noise-type run, the fail-closed verifier, tamper suite, immutability and scope."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np
import pytest

from models.explainability_v2_verify import verify_explainability_v2
from nhm.hashing import hash_file
from nhm.model_v2_explainability_guard import GUARDS, read_guard_state

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/model_v2/v2_011"


def _load(name: str) -> dict:
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def _csv(name: str) -> list[dict[str, str]]:
    with (OUT / name).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_both_guards_completed() -> None:
    for guard in GUARDS:
        assert read_guard_state(ROOT, guard)["state"] == "COMPLETED"


def test_case_access_limited_to_four_frozen_windows() -> None:
    audit = _load("case_access_audit.json")
    manifest = {r["case_type"]: r["example_id"] for r in _csv("explainability_case_manifest.csv")}
    assert audit["frozen_case_ids"] == manifest
    assert audit["materialized_windows"] == 4
    assert audit["windows_materialized_outside_frozen_manifest"] == 0
    assert audit["bulk_internal_test_scoring"] is False
    assert audit["new_internal_test_performance_table"] is False
    assert audit["model_mutated"] is False
    assert audit["all_logits_consistent_with_v2_010"] is True


def test_completeness_residuals_recorded_as_diagnostic_not_gate() -> None:
    rows = _csv("ig_completeness_diagnostic.csv")
    assert [r["case_type"] for r in rows] == ["TP", "TN", "FP", "FN"]
    for r in rows:
        assert float(r["completeness_absolute_delta"]) >= 0.0
        assert r["locked_v2_2_explainability_status"] == "DIAGNOSTIC_RECORDED"
        assert r["numerical_completeness_gate"] == "NONE"
    labels = {r["case_type"]: r["historical_heuristic_label"] for r in rows}
    assert labels == {"TP": "EXCEEDS_HISTORICAL_1E3_HEURISTIC",
                      "TN": "WITHIN_HISTORICAL_1E3_HEURISTIC",
                      "FP": "EXCEEDS_HISTORICAL_1E3_HEURISTIC",
                      "FN": "EXCEEDS_HISTORICAL_1E3_HEURISTIC"}
    repro = _load("ig_reproducibility.json")
    assert repro["status"] == "PASS" and repro["runs_per_case"] == 2
    assert repro["better_looking_run_selected"] is False
    assert repro["maximum_absolute_attribution_difference"] <= 1e-9
    report = _load("explainability_v2.json")
    sem = report["completeness_semantics"]
    assert sem["numerical_completeness_gate"] == "NONE" and sem["gates_v2g10"] is False
    assert sem["largest_observed_absolute_residual"] == pytest.approx(0.024670866165749317)
    assert sem["cases_exceeding_historical_heuristic"] == ["FN", "FP", "TP"]
    assert "No quadrature step count, baseline, model, or case was changed" in (
        sem["report_statement"])
    assert report["locked_method_compliance"]["status"] == "PASS"


def test_each_case_has_signed_attribution_raw_ecg_and_annotations() -> None:
    for case in ("TP", "TN", "FP", "FN"):
        attr = _csv(f"cases/{case}_attribution.csv")
        assert len(attr) == 2500 and "signed_ig" in attr[0]
        signed = np.array([float(r["signed_ig"]) for r in attr])
        overlay = np.array([float(r["normalized_absolute_ig"]) for r in attr])
        assert overlay.max() == pytest.approx(1.0) and overlay.min() >= 0.0
        assert np.allclose(overlay, np.abs(signed) / np.abs(signed).max(), atol=1e-12)
        assert len(_csv(f"cases/{case}_raw_ecg.csv")) == 3600
        assert len(_csv(f"cases/{case}_annotations.csv")) > 0
        assert (OUT / f"cases/{case}_figure.svg").read_text().startswith("<svg")


def test_explainability_report_status_and_claim_boundary() -> None:
    report = _load("explainability_v2.json")
    assert report["status"] == "FROZEN_EXPLAINABILITY"
    assert report["target"] == "MODEL_V2_FINAL_PRE_SIGMOID_LOGIT"
    assert report["steps"] == 64 and report["integration"] == "GAUSS_LEGENDRE"
    assert not any(report["claim_boundary_fields"].values())
    assert report["MODEL_V2_RUNTIME_ACCEPTED"] == "ACCEPTED"
    assert report["runtime_acceptance_changed_by_this_phase"] is False
    assert report["operational_lineage"] == "MODEL_V1"


def test_verifier_passes_on_canonical_artifacts() -> None:
    assert verify_explainability_v2(ROOT)["status"] == "PASS"


def test_patient_slices_rank_by_brier_with_pseudonyms() -> None:
    internal, incart = _csv("patient_slice_internal.csv"), _csv("patient_slice_incart.csv")
    assert len(internal) == 6 and len(incart) == 32
    for table in (internal, incart):
        briers = [float(r["brier_score"]) for r in table]
        best = next(r for r in table if r["ranking_status"] == "BEST_BY_BRIER")
        worst = next(r for r in table if r["ranking_status"] == "WORST_BY_BRIER")
        assert float(best["brier_score"]) == min(briers)
        assert float(worst["brier_score"]) == max(briers)
        assert not any(r["patient"].startswith("MITDB") for r in table)
    single_class = [
        r for r in incart + internal if r["F1_status"] == "SINGLE_CLASS_NO_POSITIVE_WINDOWS"
    ]
    assert all(r["F1"] == "NOT_INTERPRETABLE_FOR_OVERALL_PATIENT_RANKING" for r in single_class)


def test_quality_slice_does_not_invent_degraded() -> None:
    states = {r["quality_group"] for r in _csv("quality_slice.csv")}
    assert states == {"VALID"}


def test_hr_slice_uses_frozen_train_bins() -> None:
    frozen = json.loads((ROOT / "reports/t031/hr_bins.json").read_text())
    mine = _load("hr_bins.json")
    assert (mine["Q1_bpm"], mine["Q2_bpm"], mine["Q3_bpm"]) == (
        frozen["Q1_bpm"], frozen["Q2_bpm"], frozen["Q3_bpm"])
    rows = _csv("heart_rate_slice.csv")
    assert {r["dataset"] for r in rows} == {"INTERNAL_TEST", "INCART"}
    assert sum(int(r["support"]) for r in rows if r["dataset"] == "INTERNAL_TEST") == 2157
    assert sum(int(r["support"]) for r in rows if r["dataset"] == "INCART") == 26864


def test_dataset_and_threshold_slices() -> None:
    dataset = {r["dataset"]: r for r in _csv("dataset_slice.csv")}
    assert int(dataset["INTERNAL_TEST"]["patient_count"]) == 6
    assert int(dataset["INCART"]["patient_count"]) == 32
    assert "not directly exchangeable" in dataset["INCART"]["prevalence_note"]
    for row in _csv("threshold_region_slice.csv"):
        assert float(row["threshold"]) == 0.5101937262006424
        assert float(row["band_upper"]) - float(row["band_lower"]) == pytest.approx(0.1)
    report = _load("error_analysis_v2.json")
    assert report["threshold_changed"] is False and report["no_tuning"] is True


def test_class_composition_support_and_exploratory_flags() -> None:
    rows = _csv("class_composition_slice.csv")
    assert {r["composition"] for r in rows} == {"S_DOMINANT", "V_DOMINANT", "F_CONTAINING",
                                                "S_V_TIE"}
    for r in rows:
        assert (int(r["support"]) < 30) == (r["exploratory_small_support"] == "True")


def test_nstdb_slice_flags_electrode_motion_only() -> None:
    rows = _csv("nstdb_snr_slice.csv")
    assert len(rows) == 6
    assert all("ELECTRODE_MOTION_ONLY" in r["noise_type_coverage"] for r in rows)


def test_noise_type_run_complete_and_unfabricated() -> None:
    audit = _load("noise_type_access_audit.json")
    assert audit["prediction_rows"] == 12960 and audit["cells"] == 18
    assert audit["source_windows"] == 720
    assert audit["v1_inference_rerun"] is False
    assert audit["standalone_noise_labels_fabricated"] is False
    assert audit["model_mutated"] is False and audit["fixtures_all_pass"] is True
    metrics = _csv("noise_type_metrics.csv")
    pooled = [m for m in metrics if m["scope"] == "POOLED_BOTH_SOURCE_RECORDS"]
    assert len(pooled) == 18
    assert all(int(m["windows"]) == 720 and int(m["positive"]) == 469 for m in pooled)
    comparison = _csv("noise_type_comparison_v1_v2.csv")
    assert len(comparison) == 18 and all(c["descriptive_only"] == "True" for c in comparison)
    report = _load("error_analysis_v2.json")
    assert report["noise_type"]["new_acceptance_gate"] is False
    assert len(report["noise_type"]["limitations"]) >= 4


def test_v1_noise_comparator_unchanged() -> None:
    cfg_sha = "e671d42f3ed80eaea5446d1d642d477466152989e75c1097dd29b92dbb2fb861"
    assert hash_file(ROOT / "reports/t031/noise_type_snr_slice_v2.csv") == cfg_sha


def test_integrity_audits_pass() -> None:
    for name in ("reproducibility", "method_immutability_audit", "protected_artifact_audit",
                 "scope_audit", "tamper_test_results"):
        assert _load(f"{name}.json")["status"] == "PASS"
    tamper = _load("tamper_test_results.json")
    assert tamper["all_detected"] is True and tamper["canonical_artifacts_unmodified"] is True
    assert tamper["mutation_count"] >= 26


def test_scope_audit_no_forbidden_work() -> None:
    scope = _load("scope_audit.json")
    for key in ("retraining", "cal_v2_refit", "threshold_refit_or_changed",
                "official_validation_access", "calibration_access",
                "full_internal_test_reevaluation", "incart_reevaluation",
                "nstdb_second_look_rerun", "v1_inference_rerun", "hardware_or_wearable",
                "deployment_api_frontend_changes", "gateway_artifact_v2_created",
                "runtime_acceptance_changed"):
        assert scope[key] is False
    assert scope["new_neural_fits"] == 0 and scope["cumulative_neural_fits"] == 71


def test_runtime_decision_file_unchanged_since_entry() -> None:
    baseline = _load("protected_baseline.json")["artifacts"]
    rel = "reports/model_v2/v2_010/runtime_acceptance_decision.json"
    assert hash_file(ROOT / rel) == baseline[rel]
    assert json.loads((ROOT / rel).read_text())["MODEL_V2_RUNTIME_ACCEPTED"] == "ACCEPTED"


def test_registry_transition_and_preserved_statuses() -> None:
    def rows(path: str, key: str) -> dict[str, dict[str, str]]:
        with (ROOT / path).open(newline="", encoding="utf-8") as handle:
            return {r[key]: r for r in csv.DictReader(handle)}

    tasks = rows("manifests/model_v2/task_registry_v1.csv", "task_id")
    gates = rows("manifests/model_v2/gate_registry_v1.csv", "gate_id")
    comps = rows("manifests/model_v2/component_registry_v1.csv", "component_id")
    assert tasks["V2-011"]["status"] == "PASS" and gates["V2G10"]["status"] == "PASS"
    assert tasks["V2-012"]["status"] == "NOT_STARTED" and gates["V2G11"]["status"] == "NOT_STARTED"
    assert comps["EXPLAINABILITY_V2"]["status"] == "FROZEN_EXPLAINABILITY"
    assert comps["MODEL_V2_RUNTIME_ACCEPTED"]["status"] == "ACCEPTED"
    assert comps["MODEL_V2_FINAL"]["status"] == "FROZEN" and comps["CAL_V2"]["status"] == "FROZEN"
    assert comps["GATEWAY_ARTIFACT_V2"]["status"] == "NOT_STARTED"


def test_artifact_hashes_self_consistent() -> None:
    pins = _load("artifact_hashes.json")["artifacts"]
    for rel, digest in pins.items():
        assert hash_file(ROOT / rel) == digest
