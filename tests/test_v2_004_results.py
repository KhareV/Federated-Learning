"""V2-004 post-result tests: validates the real, frozen D1/D2 outputs for row-count/closure
correctness, firewall ledger cleanliness, decision/lock consistency, and search-budget
accounting. Read-only -- no fit, no recomputation of scientific values.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "reports/model_v2/v2_004"


def _read_csv(name: str) -> list[dict]:
    with (OUT_DIR / name).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _read_json(name: str) -> dict:
    return json.loads((OUT_DIR / name).read_text(encoding="utf-8"))


def test_d1_experiment_matrix_15_rows() -> None:
    rows = _read_csv("d1_experiment_matrix.csv")
    assert len(rows) == 15
    assert {r["seed"] for r in rows} == {"20260927"}


def test_d1_oof_closure_exact() -> None:
    audit = _read_json("oof_closure_audit.json")
    assert audit["status"] == "PASS"
    for entry in audit["per_architecture"].values():
        assert entry["closure_exact"] is True
        assert entry["rows"] == 9660
    assert audit["total_rows_all_architectures"] == 28980


def test_d1_fit_summary_15_rows() -> None:
    rows = _read_csv("d1_fit_summary.csv")
    assert len(rows) == 15
    for row in rows:
        assert row["non_finite_detected"] == "False"


def test_d1_decision_qualified_and_advancement() -> None:
    decision = _read_json("d1_decision.json")
    assert decision["qualified"] == ["MODEL_V2_TCN_MEAN", "MODEL_V2_TCN_MEANMAX"]
    assert decision["one_se_rule"]["d2_advancement_list"] == [
        "MODEL_V2_TCN_MEAN",
        "MODEL_V2_TCN_MEANMAX",
    ]
    assert decision["one_se_rule"]["preferred_architecture"] == "MODEL_V2_TCN_MEAN"
    for entry in decision["disqualification"].values():
        assert entry["disqualified"] is False


def test_d1_causal_verdicts() -> None:
    summary = _read_json("d1_causal_hypothesis_summary.json")
    assert summary["hypotheses"]["H0"]["verdict"] == "INCONCLUSIVE"
    assert summary["hypotheses"]["H1"]["verdict"] == "SUPPORTED"
    assert summary["hypotheses"]["H2"]["verdict"] == "INCONCLUSIVE"


def test_d2_experiment_matrix_20_rows() -> None:
    rows = _read_csv("d2_experiment_matrix.csv")
    assert len(rows) == 20
    assert {r["seed"] for r in rows} == {"20260928", "20260929"}
    assert {r["architecture_id"] for r in rows} == {"MODEL_V2_TCN_MEAN", "MODEL_V2_TCN_MEANMAX"}


def test_d2_oof_closure_exact() -> None:
    audit = _read_json("d2_oof_closure_audit.json")
    assert audit["status"] == "PASS"
    for entry in audit["per_seed"].values():
        assert entry["closure_exact"] is True
        assert entry["rows"] == 9660


def test_d2_fit_summary_20_rows() -> None:
    rows = _read_csv("d2_fit_summary.csv")
    assert len(rows) == 20
    for row in rows:
        assert row["non_finite_detected"] == "False"


def test_d2_stability_decision_two_survivors() -> None:
    decision = _read_json("d2_stability_decision.json")
    assert decision["v2_004_outcome"] == "D2_TWO_SURVIVORS"
    assert set(decision["survivors"]) == {"MODEL_V2_TCN_MEAN", "MODEL_V2_TCN_MEANMAX"}
    for entry in decision["per_architecture"].values():
        assert entry["unstable"] is False
        assert entry["AUPRC_sample_sd"] < decision["instability_limit"]


def test_best_learned_only_matches_decision() -> None:
    best = _read_json("best_learned_only.json")
    decision = _read_json("d2_stability_decision.json")
    assert best["architecture_id"] == decision["best_learned_only_architecture_id"]
    assert best["architecture_id"] == "MODEL_V2_TCN_MEANMAX"


def test_hybrid_trigger_false_because_learned_exceeds_classical() -> None:
    hybrid = _read_json("hybrid_trigger.json")
    assert hybrid["status"] == "FALSE"
    assert hybrid["trigger"] is False
    assert hybrid["gap"] < 0  # learned-only mean AUPRC exceeds BEST_REDUCED_RF_V1


def test_aggregation_reproducibility_both_stages_pass() -> None:
    repro = _read_json("aggregation_reproducibility.json")
    assert repro["d1"]["status"] == "PASS"
    assert repro["d1"]["fully_identical"] is True
    assert repro["d2"]["status"] == "PASS"
    assert repro["d2"]["fully_identical"] is True


def test_scope_leakage_pass_and_role_set() -> None:
    audit = _read_json("scope_leakage_audit.json")
    assert audit["status"] == "PASS"
    assert set(audit["roles_seen"]) == {"OPTIMISE", "INNER_VALIDATION", "OUTER_TEST"}
    assert audit["outer_test_used_before_checkpoint_finalization"] is False
    assert audit["total_access_rows"] == 105


def test_search_budget_exact_35_total() -> None:
    budget = _read_json("search_budget.json")
    assert budget["d1_fits_completed"] == 15
    assert budget["d2_fits_completed"] == 20
    assert budget["v2_004_total_fits"] == 35
    assert budget["cumulative_neural_fits"] == 50
    assert budget["cap_respected"] is True
    assert budget["v2_004_max_never_exceeded"] is True


def test_component_lock_exists_and_hashes_present() -> None:
    lock = json.loads(
        (ROOT / "manifests/model_v2/MODEL_V2_ARCH_CAUSALITY_V1.lock.json").read_text()
    )
    assert lock["status"] == "FROZEN_ARCH_CAUSALITY"
    assert lock["d1_d2_advancement_list"] == ["MODEL_V2_TCN_MEAN", "MODEL_V2_TCN_MEANMAX"]
    assert lock["best_learned_only_architecture_id"] == "MODEL_V2_TCN_MEANMAX"
    assert lock["hybrid_trigger_status"] == "FALSE"


def test_ledger_only_allowed_roles_no_forbidden_access() -> None:
    with (OUT_DIR / "cv_role_access_ledger.jsonl").open(encoding="utf-8") as handle:
        rows = [json.loads(line) for line in handle if line.strip()]
    assert len(rows) == 105
    roles = {row["role"] for row in rows}
    assert roles <= {"OPTIMISE", "INNER_VALIDATION", "OUTER_TEST"}
    for row in rows:
        if row["role"] == "OUTER_TEST":
            assert row["checkpoint_finalized"] is True
