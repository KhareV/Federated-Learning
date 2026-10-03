"""V2-011 pre-access tests: continuity/entry evidence, first-principles V2-010 reverification,
Integrated Gradients analytic correctness, deterministic case selection, both one-shot guards,
the case-access boundary, and every prediction-table slice rule on synthetic data -- all without
any real IG case access or V2 noise-type output.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import numpy as np
import pytest
import torch
import yaml

import scripts._v2_011_analysis as analysis
import scripts._v2_011_cases as cases
from evaluation.error_analysis import select_explainability_cases
from evaluation.explain_v2 import (
    IG_STEPS,
    completeness,
    explain_window,
    gauss_legendre_rule,
    model_state_unchanged,
    normalize_absolute_attribution,
    snapshot_model_state,
)
from models.explainability_v2_verify import (
    ExplainabilityV2VerifyError,
    verify_explainability_v2,
)
from models.model_v2_final_freeze import load_model_v2_final
from nhm.hashing import hash_file
from nhm.model_v2_explainability_guard import (
    GUARD_NAMES,
    GUARDS,
    ExplainabilityGuardViolation,
    arm_guard,
    check_and_begin_session,
    complete_session,
    mark_partially_consumed,
    read_guard_state,
)

ROOT = Path(__file__).resolve().parents[1]
V2_011 = ROOT / "reports/model_v2/v2_011"


def _load(name: str) -> dict:
    return json.loads((V2_011 / name).read_text(encoding="utf-8"))


# ---- entry / continuity / reverification ------------------------------------


def test_entry_audit_pass() -> None:
    data = _load("entry_audit.json")
    assert data["status"] == "PASS"
    assert data["head"] == data["origin_main"]
    assert data["head"].startswith("883d9c9")


def test_continuity_records_all_four_clarifications() -> None:
    data = _load("v2_010_entry_continuity.json")
    a = data["A_v2_008_timeout_provenance"]
    assert a["V2_008_outer_timeout_annotations_observed"] is True
    assert a["earlier_no_timeout_or_not_substantiated_wording"] == "SUPERSEDED_PROVENANCE_WORDING"
    assert a["scientific_MODEL_V2_FINAL_affected"] is False
    assert a["old_evidence_rewritten"] is False
    state = data["B_v2_010_handoff_formatting"]["mechanically_reconstructed_state"]
    assert state["MODEL_V2_RUNTIME_ACCEPTED"] == "ACCEPTED"
    assert state["cumulative_neural_fits"] == 71
    c = data["C_v2_010_registry_chronology"]
    assert c["classification"] == "POST_RESULT_CONTROL_PLANE_BOOKKEEPING"
    assert c["scientific_result_affected"] is False
    assert data["v2_010_scientific_result_changed"] is False


def test_first_principles_reverification_agrees() -> None:
    data = _load("v2_010_statistical_reverification.json")
    assert data["status"] == "PASS"
    assert data["historical_replicate_csvs_used_as_numerical_source"] is False
    assert data["waveform_access"] is False and data["model_inference"] is False
    assert data["INCART"]["multiplicity_preserved"] is True
    assert data["INCART"]["slots_per_replicate"] == 32
    assert data["INTERNAL_TEST_descriptive"]["slots_per_replicate"] == 6
    assert data["INCART_AUROC_delta_ci_lower_95"] == pytest.approx(0.0837960746924609, abs=1e-9)
    assert data["INCART_AUROC_RUNTIME_GUARD_PASS"] is True
    assert data["NSTDB_NO_COLLAPSE_PASS"] is True
    assert len(data["NSTDB"]["delta_auprc_v2_minus_v1"]) == 6
    assert data["reevaluated_runtime_decision"] == "ACCEPTED"


def test_upstream_identity_pass() -> None:
    data = _load("upstream_identity_audit.json")
    assert data["status"] == "PASS"
    assert all(data["identity_checks"].values())
    preds = data["v2_010_predictions"]
    assert preds["internal_v2_predictions.csv"]["rows"] == 2157
    assert preds["incart_v2_predictions.csv"]["rows"] == 26864
    assert preds["incart_v2_predictions.csv"]["patient_clusters"] == 32
    assert preds["nstdb_v2_predictions.csv"]["pair_ids"] == 720


# ---- Integrated Gradients analytics -----------------------------------------


class _Linear(torch.nn.Module):
    def __init__(self, weights: np.ndarray, bias: float = 0.0):
        super().__init__()
        self.weight = torch.nn.Parameter(torch.tensor(weights, dtype=torch.float32))
        self.bias = torch.nn.Parameter(torch.tensor(float(bias)))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return (x.reshape(x.shape[0], -1) * self.weight).sum(dim=1, keepdim=True) + self.bias


class _Quadratic(torch.nn.Module):
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return (x.reshape(x.shape[0], -1) ** 2).sum(dim=1, keepdim=True)


def _window(seed: int = 0) -> torch.Tensor:
    return torch.from_numpy(
        np.random.default_rng(seed).standard_normal(2500).astype(np.float32)
    ).reshape(1, 1, 2500)


def test_gauss_legendre_nodes_weights() -> None:
    nodes, weights = gauss_legendre_rule()
    assert nodes.size == weights.size == IG_STEPS == 64
    assert weights.sum() == pytest.approx(1.0, abs=1e-12)
    assert nodes.min() > 0.0 and nodes.max() < 1.0
    assert float(np.sum(weights * nodes)) == pytest.approx(0.5, abs=1e-12)
    assert float(np.sum(weights * nodes**2)) == pytest.approx(1 / 3, abs=1e-12)


def test_gauss_legendre_rejects_other_step_counts() -> None:
    for steps in (63, 65):
        with pytest.raises(ValueError):
            gauss_legendre_rule(steps)


def test_ig_linear_model_exact_attribution_positive_and_negative_coefficients() -> None:
    weights = np.where(np.arange(2500) % 2 == 0, 0.7, -1.3)
    model = _Linear(weights, bias=0.25)
    x = _window()
    result = explain_window(model, x)
    expected = x.numpy().reshape(-1) * weights.astype(np.float32)
    assert np.allclose(result.signed, expected, atol=1e-6)
    assert result.passed
    assert result.absolute_delta < 1e-3
    assert result.baseline_output == pytest.approx(0.25, abs=1e-6)
    assert (result.signed < 0).any() and (result.signed > 0).any()


def test_ig_constant_gradient_attribution_equals_input() -> None:
    model = _Linear(np.ones(2500), bias=0.0)
    x = _window(1)
    result = explain_window(model, x)
    assert np.allclose(result.signed, x.numpy().reshape(-1), atol=1e-6)


def test_ig_zero_input_gives_zero_attribution_and_safe_overlay() -> None:
    model = _Linear(np.ones(2500), bias=0.5)
    result = explain_window(model, torch.zeros(1, 1, 2500))
    assert np.count_nonzero(result.signed) == 0
    assert np.count_nonzero(result.normalized_absolute) == 0
    assert result.output_difference == 0.0
    assert result.passed


def test_ig_quadratic_model_is_exactly_integrated() -> None:
    result = explain_window(_Quadratic(), _window(2))
    assert result.attribution_sum == pytest.approx(result.output_difference, rel=1e-5)
    assert result.passed


def test_ig_rejects_wrong_shape() -> None:
    with pytest.raises(ValueError):
        explain_window(_Linear(np.ones(2500)), torch.zeros(1, 1, 2499))


def test_signed_attribution_retained_and_overlay_normalized_per_window() -> None:
    signed = np.array([-4.0, 2.0, 1.0, 0.0])
    absolute, overlay = normalize_absolute_attribution(signed)
    assert list(absolute) == [4.0, 2.0, 1.0, 0.0]
    assert list(overlay) == [1.0, 0.5, 0.25, 0.0]
    _, zero_overlay = normalize_absolute_attribution(np.zeros(5))
    assert not zero_overlay.any()


def test_completeness_formula_and_strict_thresholds() -> None:
    verdict = completeness(attribution_sum=1.0005, output=1.0, baseline_output=0.0)
    assert verdict["signed_delta"] == pytest.approx(0.0005)
    assert verdict["output_difference"] == 1.0
    assert verdict["passed"] is True
    assert completeness(attribution_sum=1.5, output=1.0, baseline_output=0.0)["passed"] is False
    # strict '<': a delta exactly equal to both thresholds is NOT a pass
    edge = completeness(1.5, 1.0, 0.0, absolute_threshold=0.5, relative_threshold=0.5)
    assert edge["absolute_delta"] == 0.5 and edge["relative_delta"] == 0.5
    assert edge["passed"] is False
    # OR semantics with the 1e-12 relative-denominator floor
    near_zero = completeness(0.0005, 0.0, 0.0)
    assert near_zero["relative_delta"] == pytest.approx(0.0005 / 1e-12)
    assert near_zero["passed"] is True


def test_model_state_snapshot_detects_mutation_including_buffers() -> None:
    model = torch.nn.Sequential(torch.nn.Linear(4, 4), torch.nn.BatchNorm1d(4))
    before = snapshot_model_state(model)
    assert model_state_unchanged(model, before)
    model.train()
    model(torch.randn(8, 4))  # updates BatchNorm running statistics
    assert not model_state_unchanged(model, before)


def test_real_model_v2_final_ig_on_synthetic_input_leaves_model_unchanged() -> None:
    torch.set_num_threads(1)
    model, _ = load_model_v2_final(ROOT)
    model.eval()
    before = snapshot_model_state(model)
    t = np.linspace(0, 10, 2500, dtype=np.float32)
    x = torch.from_numpy(np.sin(2 * np.pi * 1.2 * t)).reshape(1, 1, 2500)
    first = explain_window(model, x)
    second = explain_window(model, x)
    assert model_state_unchanged(model, before)
    assert not model.training
    assert np.array_equal(first.signed, second.signed)
    assert first.signed.shape == (2500,)


# ---- case selection -----------------------------------------------------------


def _row(example_id: str, label: int, pred: int, p: float) -> dict[str, str]:
    return {"example_id": example_id, "label": str(label), "thresholded_prediction": str(pred),
            "source_domain_calibrated_probability": repr(p)}


def test_case_selection_rules_and_lexicographic_tie_break() -> None:
    rows = [
        _row("b", 1, 1, 0.9), _row("a", 1, 1, 0.9), _row("c", 1, 1, 0.8),
        _row("d", 0, 0, 0.1), _row("e", 0, 0, 0.1), _row("f", 0, 0, 0.2),
        _row("g", 0, 1, 0.7), _row("h", 0, 1, 0.7), _row("i", 0, 1, 0.6),
        _row("k", 1, 0, 0.3), _row("j", 1, 0, 0.3), _row("l", 1, 0, 0.4),
    ]
    selected, counts = cases.select_cases(rows)
    assert selected["TP"]["example_id"] == "a"
    assert selected["TN"]["example_id"] == "d"
    assert selected["FP"]["example_id"] == "g"
    assert selected["FN"]["example_id"] == "j"
    assert counts == {"TP": 3, "TN": 3, "FP": 3, "FN": 3}


def test_case_selection_stops_on_empty_category() -> None:
    rows = [_row("a", 1, 1, 0.9), _row("b", 0, 0, 0.1), _row("c", 0, 1, 0.7)]
    with pytest.raises(cases.V2011Error, match="EMPTY_CASE_CATEGORY"):
        cases.select_cases(rows)


def test_case_selection_matches_frozen_v1_rule_on_real_v2_table() -> None:
    table = cases.read_csv(cases.PREDICTIONS_PATH)
    selected, counts = cases.select_cases(table)
    v1_rule = select_explainability_cases(table)
    assert all(selected[k]["example_id"] == v1_rule[k]["example_id"] for k in cases.CASE_TYPES)
    assert counts == {"TP": 1131, "TN": 994, "FP": 7, "FN": 25}


def test_frozen_case_manifest_matches_recomputation() -> None:
    manifest = cases.read_csv(cases.CASE_MANIFEST_PATH)
    rows, _ = cases.build_case_manifest_rows(ROOT)
    assert [dict(r) for r in manifest] == [{k: str(v) for k, v in r.items()} for r in rows]
    assert [r["case_type"] for r in manifest] == ["TP", "TN", "FP", "FN"]
    audit = _load("case_selection_audit.json")
    assert audit["manual_selection"] is False
    assert audit["model_rerun_for_selection"] is False
    assert audit["waveform_access_for_selection"] is False
    assert audit["case_manifest_sha256"] == hash_file(cases.CASE_MANIFEST_PATH)


def test_case_access_firewall_rejects_non_frozen_example() -> None:
    allowed = {r["example_id"] for r in cases.read_csv(cases.CASE_MANIFEST_PATH)}
    other = next(
        r["example_id"] for r in cases.read_csv(cases.PREDICTIONS_PATH)
        if r["example_id"] not in allowed
    )
    with pytest.raises(cases.V2011Error, match="NON_FROZEN_CASE_ACCESS_FORBIDDEN"):
        cases.load_case_window(ROOT, other, "100", allowed)


# ---- guards -------------------------------------------------------------------


@pytest.mark.parametrize("guard", GUARDS)
def test_guard_lifecycle_and_blocking(guard: str) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        pre = {"a": 1}
        arm_guard(root, guard, preconditions=pre)
        with pytest.raises(ExplainabilityGuardViolation, match="GUARD_ALREADY_EXISTS"):
            arm_guard(root, guard, preconditions=pre)
        with pytest.raises(ExplainabilityGuardViolation, match="PRECONDITION_MISMATCH"):
            check_and_begin_session(root, guard, observed_preconditions={"a": 2})
        started = check_and_begin_session(root, guard, observed_preconditions=pre)
        assert started["state"] == "RUNNING"
        with pytest.raises(ExplainabilityGuardViolation, match="PARTIALLY_CONSUMED"):
            check_and_begin_session(root, guard, observed_preconditions=pre)
        assert complete_session(root, guard, completion_summary={})["state"] == "COMPLETED"
        with pytest.raises(ExplainabilityGuardViolation, match="ALREADY_CONSUMED"):
            check_and_begin_session(root, guard, observed_preconditions=pre)


@pytest.mark.parametrize("guard", GUARDS)
def test_guard_partial_consumption_needs_review(guard: str) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        arm_guard(root, guard, preconditions={"a": 1})
        check_and_begin_session(root, guard, observed_preconditions={"a": 1})
        state = mark_partially_consumed(root, guard, failure_summary={"error": "x"})
        assert state["requires_human_review"] is True


def test_guard_names_and_independence() -> None:
    assert GUARD_NAMES == {
        "CASE_ACCESS": "V2_EXPLAINABILITY_CASE_ACCESS_ONCE",
        "NOISE_TYPE": "V2_NOISE_TYPE_ERROR_ANALYSIS_ONCE",
    }
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for guard in GUARDS:
            arm_guard(root, guard, preconditions={"g": guard})
        check_and_begin_session(root, "CASE_ACCESS", observed_preconditions={"g": "CASE_ACCESS"})
        complete_session(root, "CASE_ACCESS", completion_summary={})
        assert read_guard_state(root, "NOISE_TYPE")["state"] == "ARMED"
        with pytest.raises(ExplainabilityGuardViolation, match="UNKNOWN_V2_011_GUARD"):
            arm_guard(root, "OTHER", preconditions={})


@pytest.mark.parametrize("guard", GUARDS)
def test_real_guards_armed_at_or_after_method_freeze(guard: str) -> None:
    state = read_guard_state(ROOT, guard)
    assert state is not None and state["state"] in {"ARMED", "RUNNING", "COMPLETED"}


# ---- configs ------------------------------------------------------------------


def test_explainability_config_frozen_values() -> None:
    cfg = yaml.safe_load((ROOT / "configs/model_v2/explainability_v2.yaml").read_text())
    assert cfg["target"] == "MODEL_V2_FINAL_PRE_SIGMOID_LOGIT"
    assert cfg["baseline"] == "ALL_ZERO_NORMALIZED_INPUT"
    assert cfg["integration"] == "GAUSS_LEGENDRE" and cfg["steps"] == 64
    assert cfg["attribution"] == "SIGNED_INTEGRATED_GRADIENTS"
    assert cfg["tie_rule"] == "lexicographically_smallest_example_id"
    assert cfg["manual_selection"] is False and cfg["case_count"] == 4
    assert cfg["MODEL_V2_FINAL_sha256"] == hash_file(ROOT / "checkpoints/MODEL_V2_FINAL.pt")
    assert cfg["CAL_V2_sha256"] == hash_file(ROOT / "artifacts/CAL_V2.json")
    assert cfg["case_source_sha256"] == hash_file(cases.PREDICTIONS_PATH)
    assert "not a causal physiological explanation" in cfg["claim_boundary"]


def test_error_config_matches_frozen_boundaries() -> None:
    cfg = analysis.load_error_config(ROOT)
    hr = json.loads((ROOT / "reports/t031/hr_bins.json").read_text())
    h = cfg["heart_rate_slice"]
    assert (h["Q1_bpm"], h["Q2_bpm"], h["Q3_bpm"]) == (hr["Q1_bpm"], hr["Q2_bpm"], hr["Q3_bpm"])
    assert h["bins_source_sha256"] == hash_file(ROOT / "reports/t031/hr_bins.json")
    assert h["recompute_bins"] is False and h["derivation_partition"] == "TRAIN_ONLY"
    cal = json.loads((ROOT / "artifacts/CAL_V2.json").read_text())
    assert cfg["cal_v2_threshold"] == cal["threshold"]
    assert cfg["threshold_region"]["margin"] == 0.05
    assert cfg["patient_slice"]["ranking_metric"] == "BRIER"
    assert cfg["patient_slice"]["positive_class_f1_for_ranking"] is False


# ---- slice rules on synthetic data --------------------------------------------


def _pred(group: str, label: int, pred: int, p: float, ex: str) -> dict[str, str]:
    return {"example_id": ex, "participant_group_id": group, "label": str(label),
            "thresholded_prediction": str(pred), analysis.PROB: repr(p)}


def test_patient_ranking_uses_brier_not_f1() -> None:
    rows = []
    # P_A: only negatives, confident & correct: F1 would be 0 (single class), Brier tiny -> BEST
    rows += [_pred("A", 0, 0, 0.01, f"a{i}") for i in range(4)]
    # P_B: mixed, poor probabilities -> highest Brier -> WORST even though it has F1 > 0
    rows += [_pred("B", 1, 1, 0.55, "b1"), _pred("B", 0, 1, 0.9, "b2"),
             _pred("B", 1, 0, 0.1, "b3"), _pred("B", 0, 0, 0.45, "b4")]
    table = analysis.patient_slice(rows, "T")
    by = {r["patient"]: r for r in table}
    assert by["T_001"]["ranking_status"] == "BEST_BY_BRIER"
    assert by["T_002"]["ranking_status"] == "WORST_BY_BRIER"
    assert by["T_001"]["F1"] == "NOT_INTERPRETABLE_FOR_OVERALL_PATIENT_RANKING"
    assert by["T_001"]["F1_status"] == "SINGLE_CLASS_NO_POSITIVE_WINDOWS"
    assert by["T_001"]["brier_score"] < by["T_002"]["brier_score"]


def test_class_composition_semantics_and_exploratory_flag() -> None:
    rows = [_pred("A", 1, 1, 0.6, f"e{i}") for i in range(4)]
    manifest = {
        "e0": {"mapped_s_count": "3", "mapped_v_count": "1", "mapped_f_count": "0"},
        "e1": {"mapped_s_count": "1", "mapped_v_count": "3", "mapped_f_count": "0"},
        "e2": {"mapped_s_count": "5", "mapped_v_count": "0", "mapped_f_count": "1"},
        "e3": {"mapped_s_count": "2", "mapped_v_count": "2", "mapped_f_count": "0"},
    }
    table = {r["composition"]: r for r in analysis.class_composition_slice("D", rows, manifest, 30)}
    assert table["S_DOMINANT"]["support"] == 1 and table["V_DOMINANT"]["support"] == 1
    assert table["F_CONTAINING"]["support"] == 1 and table["S_V_TIE"]["support"] == 1
    assert all(r["exploratory_small_support"] for r in table.values())


def test_threshold_region_band_is_exactly_plus_minus_0_05() -> None:
    thr = 0.5101937262006424
    rows = [
        _pred("A", 0, 1, thr + 0.05, "fp_in"), _pred("A", 0, 1, thr + 0.0501, "fp_out"),
        _pred("A", 1, 0, thr - 0.05, "fn_in"), _pred("A", 1, 0, thr - 0.0501, "fn_out"),
        _pred("A", 1, 1, 0.9, "tp"),
    ]
    out = analysis.threshold_region_slice("D", rows, thr, 0.05)
    assert (out["FP"], out["FN"], out["FP_within_band"], out["FN_within_band"]) == (2, 2, 1, 1)
    assert out["share_FP_within_band"] == 0.5 and out["share_FN_within_band"] == 0.5
    with pytest.raises(ValueError):
        analysis.threshold_region_slice("D", rows, thr, 0.1)


def test_hr_bins_not_recomputed_and_assignment_uses_frozen_edges() -> None:
    edges = analysis.hr_edges(analysis.load_error_config(ROOT))
    assert edges == (65.4545454545441, 76.19047619046849, 88.70636550307518)
    from evaluation.error_analysis import assign_hr_bin

    assert assign_hr_bin(60.0, edges) == "HR_BIN_1"
    assert assign_hr_bin(70.0, edges) == "HR_BIN_2"
    assert assign_hr_bin(None, edges) == "HR_UNDEFINED"


def test_dataset_slice_reports_lift_and_prevalence() -> None:
    rows = [_pred("A", 1, 1, 0.9, "p1"), _pred("A", 1, 1, 0.8, "p2"),
            _pred("B", 0, 0, 0.1, "n1"), _pred("B", 0, 0, 0.2, "n2")]
    out = analysis.dataset_slice("X", rows)
    assert out["prevalence"] == 0.5
    assert out["AUPRC_lift_over_prevalence"] == pytest.approx(out["AUPRC"] / 0.5)
    assert out["patient_count"] == 2


def _noise_rows() -> list[dict]:
    rng = np.random.default_rng(3)
    rows = []
    for noise_type, source in analysis.NOISE_TYPES.items():
        for snr in analysis.SNR_LEVELS:
            for record in ("118", "119"):
                for i in range(20):
                    label = i % 2
                    p = float(np.clip(0.5 + (0.3 if label else -0.3) + rng.normal(0, 0.1), 0, 1))
                    rows.append({
                        "base_window_id": f"{record}_{i}", "base_record_id": record,
                        "label": label, "noise_type": noise_type, "noise_source": source,
                        "snr_db": snr, "calibrated_probability": p,
                        "thresholded_prediction": int(p >= 0.5),
                        "clean_calibrated_probability": 0.5 + (0.3 if label else -0.3),
                        "clean_thresholded_prediction": label,
                    })
    return rows


def test_noise_aggregation_has_18_pooled_cells_and_per_record_rows() -> None:
    metrics = analysis.aggregate_noise(_noise_rows())
    pooled = [m for m in metrics if m["scope"] == "POOLED_BOTH_SOURCE_RECORDS"]
    assert len(pooled) == 18
    assert {(m["noise_type"], m["snr_db"]) for m in pooled} == {
        (n, s) for n in analysis.NOISE_TYPES for s in analysis.SNR_LEVELS}
    assert len(metrics) == 18 * 3
    assert all(m["windows"] == 40 for m in pooled)
    assert analysis.aggregate_noise(_noise_rows()) == metrics


def test_noise_protocol_audit_matches_frozen_c031() -> None:
    audit = _load("noise_type_protocol_audit.json")
    assert audit["status"] == "PASS" and all(audit["checks"].values())
    assert audit["source_windows"] == 720
    assert (audit["positive"], audit["negative"]) == (469, 251)
    assert audit["analysis_cells"] == 18
    assert audit["pure_noise_labels_fabricated"] is False
    assert analysis.verify_noise_protocol(ROOT)["status"] == "PASS"


def test_noise_labels_originate_only_from_clean_base_windows() -> None:
    base = cases.read_csv(ROOT / "reports/t031/c031_noise_base_manifest.csv")
    assert "label_source" in base[0]
    assert all("clean MIT-BIH annotation" in r["label_source"] for r in base)


# ---- method freeze evidence ---------------------------------------------------


def test_method_freeze_pass_with_no_result_files_at_freeze() -> None:
    data = _load("method_freeze.json")
    assert data["status"] == "PASS"
    assert len(data["case_ids"]) == 4
    assert data["real_ig_result_exists"] is False
    assert data["v2_noise_type_result_exists"] is False
    assert set(data["method_artifact_sha256"]) == set(cases.METHOD_PATHS)


def test_verifier_fails_closed_on_empty_root() -> None:
    with tempfile.TemporaryDirectory() as tmp, pytest.raises(Exception) as info:
        verify_explainability_v2(Path(tmp))
    assert isinstance(info.value, (ExplainabilityV2VerifyError, Exception))


def test_hr_bins_v2_copy_matches_frozen_source() -> None:
    data = _load("hr_bins.json")
    frozen = json.loads((ROOT / "reports/t031/hr_bins.json").read_text())
    assert (data["Q1_bpm"], data["Q2_bpm"], data["Q3_bpm"]) == (
        frozen["Q1_bpm"], frozen["Q2_bpm"], frozen["Q3_bpm"])
    assert data["recomputed_from_internal_incart_or_v2_predictions"] is False


# ---- code-path dry runs with stubs (no real waveform access, no real V2 output) -------


def test_run_case_code_path_with_stubbed_io(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(cases, "CASES_DIR", tmp_path)
    window = np.random.default_rng(5).standard_normal(2500)
    monkeypatch.setattr(cases, "load_case_window",
                        lambda root, ex, rec, allowed: (window, ["stub_cache.npy", "stub_ids.txt"]))
    raw = np.random.default_rng(6).standard_normal(3600)
    monkeypatch.setattr(cases, "raw_ecg_segment", lambda root, rec, s, e: (1000, raw))
    monkeypatch.setattr(cases, "mapped_annotation_rows", lambda root, rec, s, e: [
        {"source_sample": 1500, "relative_time_s": 1.0, "source_symbol": "N",
         "mapped_AAMI_class": "N", "position": "INSIDE_MODEL_WINDOW"}])
    manifest, _ = cases.build_case_manifest_rows(ROOT)
    manifest = [{k: str(v) for k, v in r.items()} for r in manifest]
    case = manifest[0]
    model = _Linear(np.linspace(-1, 1, 2500), bias=0.1)
    config = cases.load_config(ROOT)
    out = cases.run_case(ROOT, model, case, {c["example_id"] for c in manifest}, config)
    assert out["case_type"] == "TP" and out["pass"] is True
    assert out["reproducibility"]["within_tolerance"] is True
    assert out["reproducibility"]["signed_max_abs_difference"] == 0.0
    attr = cases.read_csv(tmp_path / "TP_attribution.csv")
    assert len(attr) == 2500 and "signed_ig" in attr[0]
    assert len(cases.read_csv(tmp_path / "TP_raw_ecg.csv")) == 3600
    svg = (tmp_path / "TP_figure.svg").read_text()
    assert "engineering model-contribution diagnostic" in svg
    assert "not a causal physiological explanation" in svg.lower()
    assert "timestamp" not in svg.lower() and "<metadata" not in svg


def test_run_noise_matrix_code_path_with_stubbed_model(monkeypatch) -> None:
    rng = np.random.default_rng(7)
    base = cases.read_csv(ROOT / "reports/t031/c031_noise_base_manifest.csv")
    labels = np.asarray([int(r["label"]) for r in base])
    monkeypatch.setattr(analysis, "reconstruct_base_windows",
                        lambda root, rows: (rng.standard_normal((len(rows), 2500)), labels))
    monkeypatch.setattr(analysis, "build_noise_bank", lambda root: (
        {s: rng.standard_normal(50_000) for s in ("bw", "em", "ma")},
        {s: {"stub": True} for s in ("bw", "em", "ma")}))
    stub = _Linear(rng.standard_normal(2500) * 0.01, bias=0.0)
    monkeypatch.setattr(analysis, "load_model_v2_final", lambda root: (stub, {}))
    rows, fixtures, mutated = analysis.run_noise_matrix_v2(ROOT)
    assert mutated is False
    assert len(rows) == 18 * 720 and len(fixtures) == 18
    assert set(rows[0]) == set(analysis.NOISE_PRED_FIELDS)
    base_labels = {r["base_window_id"]: int(r["label"]) for r in base}
    assert all(r["label"] == base_labels[r["base_window_id"]] for r in rows)
    assert {r["noise_type"] for r in rows} == set(analysis.NOISE_TYPES)
    assert {r["snr_db"] for r in rows} == set(analysis.SNR_LEVELS)
    metrics = analysis.aggregate_noise(rows)
    assert len([m for m in metrics if m["scope"] == "POOLED_BOTH_SOURCE_RECORDS"]) == 18
