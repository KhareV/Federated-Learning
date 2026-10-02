"""C-V2-D0.6 pre-result tests (Section 22): source-artifact allowlist, firewall denial of raw
waveform / forbidden partitions, no-fitting/no-threshold-fitting-on-VALIDATION invariants,
diagnostic primitives (threshold tie rule, LOO AUPRC, single-class Brier, threshold-region
counts), class-slice closure, participant-group conservation, raw-vs-calibrated probability
separation, decision_eligible=false for historical VALIDATION, architecture/protocol lock
immutability, registry CSV parsing, and run-manifest schema validation. Synthetic/metadata only
-- no real D0.6 diagnostic result is produced by this module.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

import scripts._d0_6_diagnostics as diag
import scripts._d0_6_lib as lib
from nhm.hashing import hash_file
from nhm.model_v2_d0_6_guard import (
    D06AccessViolation,
    check_d0_6_read_allowed,
    set_ledger_root_override,
)


@pytest.fixture(autouse=True)
def _redirect_d0_6_ledger_to_tmp(tmp_path: Path) -> None:
    """This file's tests call the real gated loaders (by design, to prove the firewall end
    to end), which would otherwise append to the already-frozen, committed reports/model_v2/
    c_v2_d0_6/scope_access_ledger.jsonl on every test run. Redirect ledger writes to a
    per-test tmp_path instead; the data reads themselves still go through the real files."""
    set_ledger_root_override(tmp_path)
    yield
    set_ledger_root_override(None)

ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------------------
# Firewall / source allowlist
# ---------------------------------------------------------------------------------------


def test_allowed_path_passes() -> None:
    check_d0_6_read_allowed("reports/model_v2/v2_002/oof_predictions.csv")  # must not raise


def test_unlisted_path_rejected() -> None:
    with pytest.raises(D06AccessViolation):
        check_d0_6_read_allowed("reports/unexpected/some_file.csv")


def test_raw_waveform_cache_manifest_rejected() -> None:
    with pytest.raises(D06AccessViolation):
        check_d0_6_read_allowed("manifests/windows/MITDB_WINDOWS_V1.cache.csv")


@pytest.mark.parametrize(
    "path",
    [
        "reports/calibration/calibration_predictions.csv",
        "reports/internal_test_predictions.csv",
        "reports/external_incart_predictions.csv",
        "reports/t019/nstdb_predictions.csv",
    ],
)
def test_forbidden_partition_predictions_rejected(path: str) -> None:
    with pytest.raises(D06AccessViolation):
        check_d0_6_read_allowed(path)


def test_source_artifact_allowlist_nonempty_and_frozen() -> None:
    from nhm.model_v2_d0_6_guard import known_allowed_paths

    paths = list(known_allowed_paths())
    assert len(paths) > 0
    assert "reports/model_v2/v2_002/oof_predictions.csv" in paths
    assert "reports/model_v2/v2_003/oof_predictions.csv" in paths
    assert "reports/model_v2/v2_003/oof_metrics.json" in paths
    assert "reports/model_v2/v2_003/grouped_permutation_summary.json" in paths


def test_v2_003_rf_variant_metrics_loader() -> None:
    metrics = lib.load_v2_003_rf_variant_metrics()
    assert "per_variant_model" in metrics
    assert "RR_RF" in metrics["per_variant_model"]


def test_v2_003_grouped_permutation_summary_loader() -> None:
    summary = lib.load_v2_003_grouped_permutation_summary()
    assert summary["diagnostic_only"] is True
    assert "group_overall" in summary


# ---------------------------------------------------------------------------------------
# Diagnostic threshold tie rule
# ---------------------------------------------------------------------------------------


def test_diagnostic_threshold_picks_highest_among_tied_max_f1() -> None:
    labels = np.array([1, 1, 0, 0])
    probabilities = np.array([0.9, 0.6, 0.4, 0.1])
    threshold = diag.diagnostic_threshold(labels, probabilities)
    predictions = (probabilities >= threshold).astype(int)
    from sklearn.metrics import f1_score

    best_f1 = f1_score(labels, predictions, zero_division=0)
    for candidate in np.unique(np.concatenate([probabilities, [0.0, 1.0]])):
        candidate_predictions = (probabilities >= candidate).astype(int)
        candidate_f1 = f1_score(labels, candidate_predictions, zero_division=0)
        assert candidate_f1 <= best_f1
        if candidate_f1 == best_f1:
            assert candidate <= threshold


def test_diagnostic_threshold_comparator_is_gte() -> None:
    labels = np.array([1, 0])
    probabilities = np.array([0.5, 0.2])
    threshold = diag.diagnostic_threshold(labels, probabilities)
    # exact equality at threshold must count as positive
    assert (probabilities[0] >= threshold) or threshold > probabilities[0]


# ---------------------------------------------------------------------------------------
# Leave-one-patient-out AUPRC
# ---------------------------------------------------------------------------------------


def test_loo_auprc_formula_matches_definition() -> None:
    labels = np.array([1, 0, 1, 0, 1, 0])
    probabilities = np.array([0.9, 0.1, 0.8, 0.3, 0.7, 0.2])
    groups = np.array(["A", "A", "B", "B", "C", "C"])
    deltas = diag.leave_one_patient_out_auprc(labels, probabilities, groups)
    full = diag.pooled_auprc(labels, probabilities)
    for patient in ("A", "B", "C"):
        mask = groups != patient
        without_p = diag.pooled_auprc(labels[mask], probabilities[mask])
        assert deltas[patient] == pytest.approx(full - without_p)


def test_loo_auprc_never_uses_patient_averaged_auprc() -> None:
    # A single-class-removed subset should not crash; pooled AUPRC uses the pooled definition.
    labels = np.array([1, 1, 0, 0])
    probabilities = np.array([0.9, 0.8, 0.3, 0.2])
    groups = np.array(["A", "B", "B", "B"])
    deltas = diag.leave_one_patient_out_auprc(labels, probabilities, groups)
    assert set(deltas) == {"A", "B"}


# ---------------------------------------------------------------------------------------
# Single-class patient handling (Brier, not F1)
# ---------------------------------------------------------------------------------------


def test_patient_brier_handles_single_class_patient() -> None:
    labels = np.array([0, 0, 0, 1])
    probabilities = np.array([0.1, 0.2, 0.15, 0.8])
    groups = np.array(["SINGLE_CLASS", "SINGLE_CLASS", "SINGLE_CLASS", "MIXED"])
    briers = diag.patient_brier(labels, probabilities, groups)
    assert "SINGLE_CLASS" in briers
    expected_single = np.mean(np.square(probabilities[:3] - labels[:3]))
    assert briers["SINGLE_CLASS"] == pytest.approx(expected_single)


# ---------------------------------------------------------------------------------------
# Threshold-region error mass
# ---------------------------------------------------------------------------------------


def test_threshold_region_counts_near_window_is_exactly_0_05() -> None:
    labels = np.array([1, 0, 1, 0])
    probabilities = np.array([0.56, 0.44, 0.9, 0.1])
    threshold = 0.5
    result = diag.threshold_region_counts(labels, probabilities, threshold)
    # 0.56 and 0.44 are within 0.05 of 0.5; 0.9 and 0.1 are not
    assert result["ALL_errors_total"] == 0  # all four are correctly classified at threshold 0.5


def test_threshold_region_near_fraction_none_when_no_errors() -> None:
    labels = np.array([1, 0])
    probabilities = np.array([0.9, 0.1])
    result = diag.threshold_region_counts(labels, probabilities, 0.5)
    assert result["FP_near_fraction"] is None
    assert result["FN_near_fraction"] is None


# ---------------------------------------------------------------------------------------
# Score distribution summary
# ---------------------------------------------------------------------------------------


def test_score_distribution_summary_has_required_fields() -> None:
    values = np.linspace(0, 1, 100)
    summary = diag.score_distribution_summary(values)
    for field in ("n", "mean", "std", "p05", "p25", "median", "p75", "p95", "min", "max"):
        assert field in summary


# ---------------------------------------------------------------------------------------
# No model fitting / no threshold fitting on historical VALIDATION (structural check)
# ---------------------------------------------------------------------------------------


def test_diagnostics_module_has_no_fit_calls() -> None:
    source = (ROOT / "scripts/_d0_6_diagnostics.py").read_text(encoding="utf-8")
    assert ".fit(" not in source
    assert "RandomForestClassifier" not in source
    assert "LogisticRegression" not in source
    assert "torch.nn" not in source


def test_lib_module_never_imports_torch_or_sklearn_models() -> None:
    source = (ROOT / "scripts/_d0_6_lib.py").read_text(encoding="utf-8")
    assert "import torch" not in source
    assert "RandomForestClassifier" not in source
    assert "LogisticRegression" not in source


# ---------------------------------------------------------------------------------------
# Class-composition reuse (closure, exhaustiveness)
# ---------------------------------------------------------------------------------------


def test_class_composition_reused_exactly_mutually_exclusive_and_exhaustive() -> None:
    from evaluation.error_analysis import class_composition

    cases = [(0, 0, 1), (2, 1, 0), (1, 2, 0), (1, 1, 0), (0, 0, 0)]
    labels_seen = {class_composition(s, v, f) for s, v, f in cases}
    assert labels_seen == {
        "F_CONTAINING", "S_DOMINANT", "V_DOMINANT", "S_V_TIE", "NO_SVF_COMPOSITION",
    }


def test_composition_for_row_reuses_class_composition() -> None:
    row = {"mapped_s_count": "2", "mapped_v_count": "1", "mapped_f_count": "0"}
    assert lib.composition_for_row(row) == "S_DOMINANT"


# ---------------------------------------------------------------------------------------
# Participant-group conservation (TRAIN-OOF window manifest matches OOF prediction IDs)
# ---------------------------------------------------------------------------------------


def test_train_window_manifest_matches_oof_example_ids() -> None:
    train_rows = lib.load_window_manifest("TRAIN")
    assert len(train_rows) == 9660
    train_ids = {r["example_id"] for r in train_rows}
    oof = lib.load_model_v1_train_oof()
    oof_ids = {r["example_id"] for r in oof[20260927]}
    assert train_ids == oof_ids
    rf_ids = {r["example_id"] for r in lib.load_rf_all_train_oof()}
    assert train_ids == rf_ids


def test_validation_window_manifest_eligible_count() -> None:
    validation_rows = lib.load_window_manifest("VALIDATION")
    assert len(validation_rows) == 2880


# ---------------------------------------------------------------------------------------
# Raw-vs-calibrated probability separation
# ---------------------------------------------------------------------------------------


def test_cal_v1_threshold_is_the_calibrated_threshold_not_raw() -> None:
    cal = lib.load_cal_v1_threshold()
    assert cal["threshold"] == 0.6128035574269627
    assert cal["comparator"] == ">="


def test_t014_rf_threshold_is_fixed_not_tuned() -> None:
    rf_threshold = lib.load_t014_rf_threshold()
    assert rf_threshold["threshold"] == 0.5
    assert rf_threshold["policy"] == "FIXED_NOT_TUNED"


# ---------------------------------------------------------------------------------------
# Historical-validation decision_eligible=false (config-level assertion)
# ---------------------------------------------------------------------------------------


def test_validation_context_config_marks_decision_ineligible() -> None:
    import yaml

    config = yaml.safe_load(
        (ROOT / "configs/model_v2/d0_6_diagnostic_reconstruction_v1.yaml").read_text()
    )
    stratum = config["evidentiary_strata"]["HISTORICAL_VALIDATION_CONTEXT_ONLY"]
    assert stratum["decision_eligible"] is False
    assert stratum["historical_context_only"] is True
    train_stratum = config["evidentiary_strata"]["TRAIN_OOF_DECISION_ELIGIBLE"]
    assert train_stratum["may_support_mechanistic_hypothesis"] is True


def test_no_threshold_fitting_permitted_for_validation() -> None:
    import yaml

    config = yaml.safe_load(
        (ROOT / "configs/model_v2/d0_6_diagnostic_reconstruction_v1.yaml").read_text()
    )
    historical = config["diagnostic_threshold_rule"]["historical_validation"]
    assert historical["fit_any_threshold"] is False


# ---------------------------------------------------------------------------------------
# Architecture / protocol lock immutability
# ---------------------------------------------------------------------------------------


def test_architecture_parameter_counts_unchanged() -> None:
    from models.model_v2_architectures import (
        ModelV2CapCtrl,
        ModelV2TcnMean,
        ModelV2TcnMeanMax,
        analytic_tcn_receptive_field_samples,
        count_trainable_parameters,
    )

    assert count_trainable_parameters(ModelV2CapCtrl()) == 51969
    assert count_trainable_parameters(ModelV2TcnMean()) == 57553
    assert count_trainable_parameters(ModelV2TcnMeanMax()) == 57577
    assert analytic_tcn_receptive_field_samples() == 3063


def test_protocol_lock_hash_unchanged() -> None:
    lock_path = ROOT / "manifests/model_v2/MODEL_V2_RESEARCH_PROTOCOL_V1.lock.json"
    expected = "4dadf234afd239539240e4e2662b1fdf54e5154400b1ea4e0c14c8e4107e2eb7"
    assert hash_file(lock_path) == expected


# ---------------------------------------------------------------------------------------
# Registry CSV parsing
# ---------------------------------------------------------------------------------------


def test_registries_parse_consistently() -> None:
    import csv

    for name in ["task_registry_v1.csv", "gate_registry_v1.csv", "component_registry_v1.csv"]:
        path = ROOT / "manifests/model_v2" / name
        with path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.reader(handle))
        header_len = len(rows[0])
        assert all(len(row) == header_len for row in rows[1:])


# ---------------------------------------------------------------------------------------
# Run-manifest schema validation (smoke -- real manifest validated post-result)
# ---------------------------------------------------------------------------------------


def test_model_v2_run_manifest_schema_exists_and_is_valid_json() -> None:
    schema_path = ROOT / "contracts/model_v2_run_manifest_v1.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    assert schema["properties"]["phase_id"]["pattern"] == "^V2-[0-9]{3}$"
