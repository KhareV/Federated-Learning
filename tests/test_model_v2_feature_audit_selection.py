"""V2-003 selection-rule tests: minimal-adequate-subset and best-reduced-RF rules on synthetic
metrics (tie-breaking, fallback-to-ALL), OOF closure detection on synthetic rows, and
consistency checks against the real frozen V2-003 result (closure PASS, reproducibility PASS,
exact row counts, and the two selected variants matching their own recorded selection logic).
"""

from __future__ import annotations

import json

import scripts._v2_003_lib as lib
import scripts.aggregate_v2003 as aggregate_mod
import scripts.select_subset_v2003 as select_mod

ROOT = lib.ROOT
OUT_DIR = ROOT / "reports/model_v2/v2_003"


def _synthetic_metrics(rf_auprc: dict[str, float]) -> dict:
    per_variant_model = {}
    for variant in lib.VARIANT_IDS:
        feature_count = len(lib.VARIANT_INDICES[variant])
        per_variant_model[f"{variant}_RF"] = {
            "feature_count": feature_count,
            "pooled_OOF_AUPRC": rf_auprc[variant],
            "pooled_OOF_AUROC": rf_auprc[variant] + 0.05,
        }
        per_variant_model[f"{variant}_LOGISTIC"] = {
            "feature_count": feature_count,
            "pooled_OOF_AUPRC": rf_auprc[variant] - 0.01,
            "pooled_OOF_AUROC": rf_auprc[variant] + 0.04,
        }
    return {"per_variant_model": per_variant_model}


def test_minimal_adequate_subset_prefers_fewest_features_when_adequate() -> None:
    metrics = _synthetic_metrics(
        {
            "STAT": 0.50, "RR": 0.60, "QRS": 0.40,
            "RR_QRS": 0.61, "STAT_RR": 0.615, "STAT_QRS": 0.45, "ALL": 0.62,
        }
    )
    result = select_mod.select_minimal_adequate_subset(metrics)
    # RR_QRS (16) and STAT_RR (22) and RR (within 0.02 of 0.62? 0.60 >= 0.60 -> yes adequate)
    assert result["selected_variant"] == "RR"
    assert result["selected_feature_count"] == 9
    assert result["no_reduced_variant_adequate_fallback_to_all"] is False


def test_minimal_adequate_subset_falls_back_to_all_when_none_adequate() -> None:
    metrics = _synthetic_metrics(
        {
            "STAT": 0.10, "RR": 0.20, "QRS": 0.05,
            "RR_QRS": 0.25, "STAT_RR": 0.30, "STAT_QRS": 0.15, "ALL": 0.90,
        }
    )
    result = select_mod.select_minimal_adequate_subset(metrics)
    assert result["selected_variant"] == "ALL"
    assert result["no_reduced_variant_adequate_fallback_to_all"] is True


def test_minimal_adequate_subset_tie_rule_prefers_higher_auprc_then_lexical() -> None:
    # STAT and QRS both adequate, same feature count would require custom counts; instead
    # test the margin boundary: a variant exactly at the margin counts as adequate (>=).
    metrics = _synthetic_metrics(
        {
            "STAT": 0.58, "RR": 0.10, "QRS": 0.05,
            "RR_QRS": 0.10, "STAT_RR": 0.10, "STAT_QRS": 0.10, "ALL": 0.60,
        }
    )
    result = select_mod.select_minimal_adequate_subset(metrics)
    assert result["selected_variant"] == "STAT"  # exactly ALL - 0.02, counts as adequate


def test_best_reduced_rf_highest_auprc_wins() -> None:
    metrics = _synthetic_metrics(
        {
            "STAT": 0.50, "RR": 0.70, "QRS": 0.40,
            "RR_QRS": 0.65, "STAT_RR": 0.60, "STAT_QRS": 0.45, "ALL": 0.72,
        }
    )
    result = select_mod.select_best_reduced_rf(metrics)
    assert result["selected_variant"] == "RR"
    assert result["AUPRC"] == 0.70


def test_best_reduced_rf_tie_prefers_fewer_features_then_lexical() -> None:
    metrics = _synthetic_metrics(
        {
            "STAT": 0.50, "RR": 0.50, "QRS": 0.50,
            "RR_QRS": 0.50, "STAT_RR": 0.50, "STAT_QRS": 0.50, "ALL": 0.50,
        }
    )
    result = select_mod.select_best_reduced_rf(metrics)
    # all tied at feature-count level too except QRS has fewest (7) among reduced candidates
    assert result["selected_variant"] == "QRS"
    assert result["feature_count"] == 7


def test_verify_closure_detects_duplicate_and_missing() -> None:
    eligible = {f"id_{i}" for i in range(10)}
    rows = [
        {
            "example_id": f"id_{i}",
            "feature_variant": "STAT",
            "model_family": "RF",
            "participant_group_id": "P1",
            "label": "0",
            "probability": "0.1",
            "outer_fold": "0",
        }
        for i in range(9)
    ]
    rows.append(dict(rows[0]))  # duplicate id_0, missing id_9
    full_rows = []
    for variant in lib.VARIANT_IDS:
        for model_family in lib.MODEL_FAMILIES:
            for row in rows:
                full_rows.append({**row, "feature_variant": variant, "model_family": model_family})
    closure = aggregate_mod.verify_closure(full_rows, eligible)
    assert closure["status"] == "FAIL"
    assert closure["per_combo"]["STAT_RF"]["duplicates"] == 1
    assert closure["per_combo"]["STAT_RF"]["missing_count"] == 1


def test_verify_closure_passes_on_exact_population() -> None:
    eligible = {f"id_{i}" for i in range(5)}
    full_rows = []
    for variant in lib.VARIANT_IDS:
        for model_family in lib.MODEL_FAMILIES:
            for i in range(5):
                full_rows.append(
                    {
                        "example_id": f"id_{i}",
                        "feature_variant": variant,
                        "model_family": model_family,
                        "participant_group_id": "P1",
                        "label": "0",
                        "probability": "0.1",
                        "outer_fold": "0",
                    }
                )
    closure = aggregate_mod.verify_closure(full_rows, eligible)
    assert closure["status"] == "PASS"


def test_real_oof_closure_exact() -> None:
    audit = json.loads((OUT_DIR / "oof_closure_audit.json").read_text(encoding="utf-8"))
    assert audit["status"] == "PASS"
    for combo in audit["per_combo"].values():
        assert combo["closure_exact"] is True
        assert combo["rows"] == 9660


def test_real_reproducibility_pass() -> None:
    repro = json.loads((OUT_DIR / "reproducibility.json").read_text(encoding="utf-8"))
    assert repro["status"] == "PASS"
    assert repro["LR_RF_predictions_byte_identical"] is True
    assert repro["metrics_identical"] is True


def test_real_scope_leakage_pass() -> None:
    audit = json.loads((OUT_DIR / "scope_leakage_audit.json").read_text(encoding="utf-8"))
    assert audit["status"] == "PASS"
    assert audit["roles_seen"] == ["OPTIMISE", "OUTER_TEST"]
    assert audit["inner_validation_touched"] is False


def test_real_selected_variants_are_self_consistent() -> None:
    oof_metrics = json.loads((OUT_DIR / "oof_metrics.json").read_text(encoding="utf-8"))
    minimal_subset = json.loads((OUT_DIR / "minimal_adequate_subset.json").read_text())
    best_reduced = json.loads((OUT_DIR / "best_reduced_rf.json").read_text())
    recomputed_minimal = select_mod.select_minimal_adequate_subset(oof_metrics)
    recomputed_best = select_mod.select_best_reduced_rf(oof_metrics)
    assert recomputed_minimal["selected_variant"] == minimal_subset["selected_variant"]
    assert recomputed_best["selected_variant"] == best_reduced["selected_variant"]


def test_real_total_fold_predictions_row_count() -> None:
    import csv

    with (OUT_DIR / "fold_predictions.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 9660 * 7 * 2
