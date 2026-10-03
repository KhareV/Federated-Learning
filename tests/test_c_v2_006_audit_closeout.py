"""C-V2-006-AUDIT-CLOSEOUT tests (Section 25): exact, non-tolerant current-state locks.

Unlike the historical relaxed tests from earlier checkpoints (which tolerate a status moving
from NOT_STARTED to PASS because a later phase legitimately ran), every assertion here pins
the CURRENT value exactly, with no ambiguity: V2-006/V2G5 must be PASS now, V2-007/V2G6 must
still be NOT_STARTED now, the optimizer decision and finalist shortlist must match the frozen
V2-006 result exactly, and no MODEL_V2_FINAL/CAL_V2/official-VALIDATION access may have
occurred. This file also locks this checkpoint's own independent-reverification and chunked-
regression evidence.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
AUDIT_DIR = ROOT / "reports/model_v2/c_v2_006_audit_closeout"


def _load(name: str) -> dict:
    return json.loads((AUDIT_DIR / name).read_text(encoding="utf-8"))


def _registry() -> tuple[dict, dict]:
    with (ROOT / "manifests/model_v2/task_registry_v1.csv").open(newline="") as handle:
        tasks = {row["task_id"]: row for row in csv.DictReader(handle)}
    with (ROOT / "manifests/model_v2/gate_registry_v1.csv").open(newline="") as handle:
        gates = {row["gate_id"]: row["status"] for row in csv.DictReader(handle)}
    return tasks, gates


def test_v2_006_and_v2g5_exactly_pass() -> None:
    tasks, gates = _registry()
    assert tasks["V2-006"]["status"] == "PASS"
    assert gates["V2G5"] == "PASS"


def test_v2_007_and_v2g6_exactly_not_started() -> None:
    tasks, gates = _registry()
    assert tasks["V2-007"]["status"] == "NOT_STARTED"
    assert gates["V2G6"] == "NOT_STARTED"


def test_optimizer_decision_exact() -> None:
    data = _load("adoption_decision_reverification.json")
    assert data["status"] == "PASS"
    assert data["frozen_decision"] == "ORIGINAL_SCHEDULE_RETAINED_BOTH_CRITERIA_FAILED"
    assert data["replayed_decision"] == data["frozen_decision"]
    assert all(data["matches_frozen"].values())


def test_finalist_shortlist_exact() -> None:
    lock = json.loads(
        (ROOT / "manifests/model_v2/MODEL_V2_FINALIST_SHORTLIST_V1.lock.json").read_text(
            encoding="utf-8"
        )
    )
    assert lock["status"] == "FROZEN_FINALIST_SHORTLIST"
    assert lock["shortlist_count"] == 2
    assert lock["model_v2_final_selected"] is False
    finalist_a = next(f for f in lock["finalists"] if f["finalist"] == "A")
    finalist_b = next(f for f in lock["finalists"] if f["finalist"] == "B")
    assert finalist_a["architecture_id"] == "MODEL_V2_TCN_MEAN"
    assert finalist_a["schedule_id"] == "CONFIG_V2_TCN_MEAN_ORIGINAL_V1"
    assert finalist_a["optimizer_challenged"] is False
    assert finalist_b["architecture_id"] == "MODEL_V2_TCN_MEANMAX"
    assert finalist_b["schedule_id"] == "CONFIG_V2_TCN_MEANMAX_ORIGINAL_V1"
    assert finalist_b["optimizer_challenged"] is True
    assert finalist_b["adoption_decision"] == "ORIGINAL_SCHEDULE_RETAINED_BOTH_CRITERIA_FAILED"


def test_model_v2_final_and_cal_v2_still_absent() -> None:
    with (ROOT / "manifests/model_v2/component_registry_v1.csv").open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    for component_id in ("MODEL_V2_FINAL", "CAL_V2"):
        row = next(r for r in rows if r["component_id"] == component_id)
        assert row["status"] == "NOT_STARTED"


def test_official_validation_still_unopened() -> None:
    data = _load("data_scope_audit.json")
    assert data["status"] == "PASS"
    for key in [
        "official_validation_accessed", "calibration_accessed", "internal_test_accessed",
        "incart_accessed", "nstdb_accessed", "bidmc_accessed",
    ]:
        assert data[key] is False
    assert data["new_neural_fits"] == 0
    assert data["new_classical_fits"] == 0
    assert data["waveform_reads"] == 0


def test_protocol_v3_unchanged_and_no_v4_created() -> None:
    assert (
        hash_file(ROOT / "manifests/model_v2/MODEL_V2_RESEARCH_PROTOCOL_V3.lock.json")
        == "287aff4ff3fcf583524f06e6af51f23bd65949a75abef14cde80ff0936873db8"
    )
    assert not (ROOT / "manifests/model_v2/MODEL_V2_RESEARCH_PROTOCOL_V4.lock.json").exists()


def test_search_budget_unchanged_65_of_90() -> None:
    data = _load("search_budget_audit.json")
    assert data["status"] == "PASS"
    assert data["cumulative"] == 65
    assert data["protocol_v3_d0_d5_cap"] == 90
    assert data["closeout_fits"] == 0
    assert data["control_reruns"] == 0


def test_independent_metric_reverification_exact_match() -> None:
    data = _load("independent_metric_reverification.json")
    assert data["status"] == "PASS"
    assert all(data["matches_frozen"].values())
    assert data["control_mean_AUPRC"] == data["frozen_control_mean_AUPRC"]
    assert data["challenger_mean_AUPRC"] == data["frozen_challenger_mean_AUPRC"]


def test_independent_bootstrap_reverification_exact_match() -> None:
    data = _load("independent_bootstrap_reverification.json")
    assert data["status"] == "PASS"
    assert all(data["matches_frozen"].values())
    assert data["BOOTSTRAP_SE_DELTA"] == data["frozen_BOOTSTRAP_SE_DELTA"]


def test_packaging_audit_classified_packaging_only() -> None:
    data = _load("component_freeze_packaging_audit.json")
    assert data["status"] == "PASS"
    assert data["classification"] == "PACKAGING_ONLY"
    assert data["replay_exit_code"] == 0
    assert data["forbidden_scientific_calls_found"] == []


def test_prefit_regression_disclosure_recorded() -> None:
    data = _load("prefit_regression_disclosure.json")
    assert data["classification"] == "PREFIT_REGRESSION_EVIDENCE_PROTOCOL_BREACH"
    assert data["status"] == "DISCLOSED"


def test_chunked_regression_proof_exhaustive() -> None:
    data = _load("chunked_regression_proof_core.json")
    assert data["status"] == "PASS"
    assert data["collected_equals_executed"] is True
    assert data["missing"] == 0
    assert data["duplicates"] == 0
    assert data["unexpected"] == 0
    assert data["failed_chunks"] == 0
    assert data["failed_tests"] == 0
    assert data["collected_node_count"] == data["executed_unique_count"]


def test_all_fit_integrity_full_15_of_15() -> None:
    data = _load("all_fit_integrity_summary.json")
    assert data["status"] == "PASS"
    assert data["all_15_pass"] is True
    assert data["pass_count"] == 15
    assert data["total_rows"] == 15
    assert data["extra_fit_directories"] == []


def test_run_manifest_and_artifact_hashes_valid() -> None:
    manifest = _load("run_manifest.json")
    assert manifest["checkpoint_id"] == "C-V2-006-AUDIT-CLOSEOUT"
    assert manifest["v2_006_rerun"] is False
    assert manifest["control_retrained"] is False
    assert manifest["sixteenth_fit_added"] is False
    hashes = _load("artifact_hashes.json")
    for rel_path, expected in hashes["artifacts"].items():
        assert hash_file(ROOT / rel_path) == expected
