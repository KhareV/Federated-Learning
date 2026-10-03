"""V2-006 post-run result tests: validates the real 15-fit challenger result, the matched
read-only CONTROL extraction, the paired bootstrap, the adoption decision, and the finalist
shortlist. Read-only against the frozen evidence tree; never retrains, never recomputes a
decision inline (always reads the frozen artifacts the pipeline scripts already produced).
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "reports/model_v2/v2_006"


def _load(name: str) -> dict:
    return json.loads((OUT_DIR / name).read_text(encoding="utf-8"))


def test_challenger_oof_closure_exact() -> None:
    data = _load("oof_closure_audit.json")
    assert data["status"] == "PASS"
    assert data["total_challenger_rows"] == 28980
    for seed_closure in data["challenger"].values():
        assert seed_closure["closure_exact"] is True
        assert seed_closure["rows"] == 9660
    for seed_closure in data["control"].values():
        assert seed_closure["closure_exact"] is True
        assert seed_closure["rows"] == 9660


def test_all_15_fits_integrity() -> None:
    with (OUT_DIR / "fit_summary.csv").open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 15
    for row in rows:
        assert row["checkpoint_reload_consistency"] == "PASS"
        assert row["non_finite_detected"] == "False"
        assert row["architecture_id"] == "MODEL_V2_TCN_MEANMAX"
        assert row["schedule_id"] == "MODEL_V2_OPTIMIZER_CORRECTED_V1"
        assert int(row["parameter_count"]) == 57577


def test_control_matches_frozen_v2_004_value_exactly() -> None:
    control = _load("control_seed_metrics.json")
    assert control["three_seed_summary"]["AUPRC_mean"] == 0.8558768456473372
    assert control["source"].startswith("reports/model_v2/v2_004")


def test_control_never_retrained() -> None:
    inventory = _load("control_reference_inventory.json")
    assert inventory["control_retrained"] is False
    assert len(inventory["source_experiment_ids"]) == 15


def test_bootstrap_draws_reused_exact_identity() -> None:
    summary = _load("paired_bootstrap_summary.json")
    assert summary["bootstrap_id"] == "MODEL_V2_BOOTSTRAP_DRAWS_V1"
    assert summary["bootstrap_seed"] == 20261002
    assert summary["B"] == 2000
    assert summary["valid_B"] == 2000


def test_bootstrap_se_delta_matches_definition() -> None:
    summary = _load("paired_bootstrap_summary.json")
    assert summary["BOOTSTRAP_SE_DELTA"] is not None
    assert summary["BOOTSTRAP_SE_DELTA"] > 0


def test_adoption_decision_applied_exactly() -> None:
    decision = _load("adoption_decision.json")
    comparison = _load("optimizer_comparison.json")

    point_delta = comparison["challenger_mean_AUPRC"] - comparison["control_mean_AUPRC"]
    assert abs(point_delta - decision["point_delta"]) < 1e-12

    expected_improvement = (
        decision["sufficient_valid_bootstrap_replicates"]
        and point_delta > decision["bootstrap_se_delta"]
    )
    assert decision["improvement_gt_one_se"] == expected_improvement

    expected_seed_sd_ok = comparison["challenger_seed_SD"] <= comparison["control_seed_SD"]
    assert decision["seed_sd_not_worse"] == expected_seed_sd_ok

    assert decision["auroc_used_as_adoption_gate"] is False
    assert decision["p_value_used"] is False
    assert decision["ci_alone_used_for_decision"] is False

    assert decision["decision"] in {
        "CORRECTED_SCHEDULE_ADOPTED",
        "ORIGINAL_SCHEDULE_RETAINED_INSUFFICIENT_IMPROVEMENT",
        "ORIGINAL_SCHEDULE_RETAINED_SEED_VARIANCE_WORSE",
        "ORIGINAL_SCHEDULE_RETAINED_BOTH_CRITERIA_FAILED",
        "ORIGINAL_SCHEDULE_RETAINED_INVALID_CHALLENGER",
    }


def test_decision_matches_actual_result() -> None:
    # This repository's actual V2-006 run: point delta (~0.00027) did not exceed the
    # bootstrap SE (~0.016), and challenger seed SD (~0.0248) exceeded control seed SD
    # (~0.0191) -- both criteria failed, so the original schedule is retained.
    decision = _load("adoption_decision.json")
    assert decision["corrected_schedule_adopted"] is False
    assert decision["decision"] == "ORIGINAL_SCHEDULE_RETAINED_BOTH_CRITERIA_FAILED"
    assert decision["improvement_gt_one_se"] is False
    assert decision["seed_sd_not_worse"] is False


def test_finalist_shortlist_exactly_two_entries() -> None:
    shortlist = _load("finalist_shortlist.json")
    assert shortlist["shortlist_count"] == 2
    assert len(shortlist["finalists"]) == 2
    finalist_a = next(f for f in shortlist["finalists"] if f["finalist"] == "A")
    finalist_b = next(f for f in shortlist["finalists"] if f["finalist"] == "B")
    assert finalist_a["architecture_id"] == "MODEL_V2_TCN_MEAN"
    assert finalist_a["optimizer_challenged"] is False
    assert finalist_b["architecture_id"] == "MODEL_V2_TCN_MEANMAX"
    assert finalist_b["schedule_id"] == "CONFIG_V2_TCN_MEANMAX_ORIGINAL_V1"
    assert shortlist["model_v2_final_selected"] is False
    assert shortlist["rejected_schedule_variant_excluded"] is True


def test_no_waveform_leakage_or_official_validation_access() -> None:
    data = _load("scope_leakage_audit.json")
    assert data["status"] == "PASS"
    assert data["official_validation_touched"] is False
    assert data["calibration_touched"] is False
    assert data["final_inner_manifest_touched_by_v2_006"] is False
    assert data["outer_test_used_before_checkpoint_finalization"] is False
    assert data["total_access_rows"] == 45


def test_search_budget_65_of_90() -> None:
    data = _load("search_budget.json")
    assert data["status"] == "PASS"
    assert data["cumulative_neural_fits"] == 65
    assert data["v2_006_new_canonical_fits"] == 15
    assert data["v2_006_control_reruns"] == 0
    assert data["cap_respected"] is True


def test_aggregation_reproducible() -> None:
    data = _load("aggregation_reproducibility.json")
    assert data["status"] == "PASS"
    assert data["all_identical"] is True


def test_run_manifest_and_artifact_hashes_valid() -> None:
    manifest = _load("run_manifest.json")
    assert manifest["checkpoint_id"] == "V2-006"
    assert manifest["control_reused_not_retrained"] is True
    assert manifest["challenger_new_fits"] == 15
    hashes = _load("artifact_hashes.json")
    for rel_path, expected in hashes["artifacts"].items():
        assert hash_file(ROOT / rel_path) == expected


def test_mechanism_diagnostics_present() -> None:
    summary = _load("optimizer_mechanism_summary.json")
    assert "CONTROL" in summary
    assert "CHALLENGER" in summary
    for role in ("CONTROL", "CHALLENGER"):
        assert 0.0 <= summary[role]["fraction_fits_with_ge_1_lr_reduction"] <= 1.0

    with (OUT_DIR / "optimizer_mechanism_diagnostics.csv").open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 30
    assert sum(1 for r in rows if r["role"] == "CHALLENGER") == 15
    assert sum(1 for r in rows if r["role"] == "CONTROL") == 15
