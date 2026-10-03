"""V2-010 Section 12 pre-access config tests: guard mechanics, the pure statistical core
(paired-bootstrap delta/CI, both predeclared zero-margin runtime guards, the final decision
rule), and Section 3/4/5/6/7 entry evidence -- all synthetic or read-only, never touching
INTERNAL_TEST/INCART/NSTDB waveform data.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import numpy as np
import pytest

from models.cal_v2_verify import verify_cal_v2
from models.model_v2_final_freeze import verify_model_v2_final
from nhm.model_v2_second_look_guard import (
    DATASETS,
    GUARD_NAMES,
    SecondLookGuardViolation,
    arm_guard,
    check_and_begin_session,
    complete_session,
    mark_partially_consumed,
    read_guard_state,
)
from scripts._v2_010_stats import (
    SNR_LEVELS_DB,
    V2010StatsError,
    incart_auroc_runtime_guard_pass,
    nstdb_no_collapse_pass,
    paired_bootstrap_delta,
    paired_bootstrap_summary,
    runtime_acceptance_decision,
)

ROOT = Path(__file__).resolve().parents[1]
V2_010_DIR = ROOT / "reports/model_v2/v2_010"


def _load(name: str) -> dict:
    return json.loads((V2_010_DIR / name).read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# Section 3: carry-forward provenance correction
# --------------------------------------------------------------------------


def test_fact_a_disclosed_without_corroboration_hidden() -> None:
    data = _load("v2_009_entry_continuity_audit_fact_a.json")
    assert data["status"] == "DISCLOSED"
    assert data["re_investigation_performed"] is True
    assert data["scientific_impact"] == "NONE_DETECTED"


def test_fact_b_confirmed_true_via_git() -> None:
    data = _load("v2_009_entry_continuity_audit_fact_b.json")
    assert data["finding"] == "CONFIRMED_TRUE"
    assert data["all_scientific_files_unchanged"] is True


def test_carryforward_audit_combined() -> None:
    data = _load("v2_009_entry_continuity_audit.json")
    assert data["status"] == "DISCLOSED"
    assert data["model_v2_final_unchanged"] is True
    assert data["cal_v2_fitted_temperature_unchanged"] is True


# --------------------------------------------------------------------------
# Section 4: pre-access exhaustive chunked regression
# --------------------------------------------------------------------------


def test_pre_access_regression_proof_pass() -> None:
    data = _load("v2_009_final_regression_continuity.json")
    assert data["status"] == "PASS"
    assert data["collected_equals_executed"] is True
    assert data["missing"] == 0
    assert data["duplicates"] == 0
    assert data["unexpected"] == 0
    assert data["failed_chunks"] == 0
    assert data["failed_tests"] == 0


# --------------------------------------------------------------------------
# Sections 5/6: upstream re-verification (no mutation)
# --------------------------------------------------------------------------


def test_model_v2_final_reverifies_pass() -> None:
    result = verify_model_v2_final(ROOT)
    assert result["status"] == "PASS"
    assert result["maximum_absolute_error"] == 0.0


def test_cal_v2_reverifies_pass() -> None:
    result = verify_cal_v2(ROOT)
    assert result["status"] == "PASS"


# --------------------------------------------------------------------------
# Section 7: V1 comparator freezes (hash/guard only, never rerun)
# --------------------------------------------------------------------------


def test_internal_test_v1_freeze_pass() -> None:
    from evaluation.internal_test import verify_internal_test_freeze

    assert verify_internal_test_freeze(ROOT)["status"] == "PASS"


def test_incart_v1_freeze_pass() -> None:
    from evaluation.external_incart import verify_external_freeze

    assert verify_external_freeze(ROOT)["status"] == "PASS"


def test_nstdb_v1_freeze_pass_without_model_inference() -> None:
    import subprocess

    result = subprocess.run(
        [str(ROOT / ".venv-t032/bin/python"), "scripts/verify_noise_robustness_t019.py"],
        cwd=ROOT, capture_output=True, text=True, check=True,
    )
    data = json.loads(result.stdout)
    assert data["status"] == "PASS"
    assert data["model_inference_repeated"] is False


def test_upstream_identity_audit_pass() -> None:
    data = _load("upstream_identity_audit.json")
    assert data["status"] == "PASS"
    assert data["model_v2_final"]["mutated"] is False
    assert data["cal_v2"]["mutated"] is False
    assert data["fresh_process_runs"] == 2


def test_historical_population_expectations_mechanically_verified() -> None:
    import scripts.freeze_v2_010_method as freeze_method

    population = freeze_method._historical_population_expectations()
    assert all(population["matches_phase_prompt_expectations"].values())
    assert population["INTERNAL_TEST"]["frozen_group_count"] == 7
    assert population["INTERNAL_TEST"]["contributing_group_count"] == 6
    assert population["INCART"]["record_count"] == 75
    assert population["INCART"]["patient_cluster_count"] == 32
    assert population["NSTDB"]["base_record_ids"] == ["118", "119"]


def test_v1_comparator_inventory_no_rerun() -> None:
    data = _load("v1_comparator_inventory.json")
    assert data["status"] == "PASS"
    assert data["INTERNAL_TEST_V1"]["rerun_v1_inference"] is False
    assert data["INCART_EXT_V1"]["rerun_v1_inference"] is False
    assert data["NSTDB_T019"]["model_inference_repeated"] is False


# --------------------------------------------------------------------------
# Guard mechanics: all three datasets, fully independent
# --------------------------------------------------------------------------


@pytest.mark.parametrize("dataset", DATASETS)
def test_guard_arm_then_begin_then_complete(dataset: str) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        preconditions = {"a": 1}
        arm_guard(root, dataset, preconditions=preconditions)
        state = check_and_begin_session(root, dataset, observed_preconditions=preconditions)
        assert state["state"] == "RUNNING"
        completed = complete_session(root, dataset, completion_summary={"rows": 1})
        assert completed["state"] == "COMPLETED"


@pytest.mark.parametrize("dataset", DATASETS)
def test_guard_second_invocation_blocked(dataset: str) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        preconditions = {"a": 1}
        arm_guard(root, dataset, preconditions=preconditions)
        check_and_begin_session(root, dataset, observed_preconditions=preconditions)
        complete_session(root, dataset, completion_summary={"rows": 1})
        with pytest.raises(SecondLookGuardViolation, match="ALREADY_CONSUMED"):
            check_and_begin_session(root, dataset, observed_preconditions=preconditions)


@pytest.mark.parametrize("dataset", DATASETS)
def test_guard_precondition_mismatch_rejected(dataset: str) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        arm_guard(root, dataset, preconditions={"a": 1})
        with pytest.raises(SecondLookGuardViolation, match="PRECONDITION_MISMATCH"):
            check_and_begin_session(root, dataset, observed_preconditions={"a": 2})


@pytest.mark.parametrize("dataset", DATASETS)
def test_guard_partial_consumption_blocks_further_access(dataset: str) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        preconditions = {"a": 1}
        arm_guard(root, dataset, preconditions=preconditions)
        check_and_begin_session(root, dataset, observed_preconditions=preconditions)
        mark_partially_consumed(root, dataset, failure_summary={"error": "crash"})
        state = read_guard_state(root, dataset)
        assert state["requires_human_review"] is True
        with pytest.raises(SecondLookGuardViolation, match="PARTIALLY_CONSUMED"):
            check_and_begin_session(root, dataset, observed_preconditions=preconditions)


@pytest.mark.parametrize("dataset", DATASETS)
def test_guard_cannot_double_arm(dataset: str) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        arm_guard(root, dataset, preconditions={"a": 1})
        with pytest.raises(SecondLookGuardViolation, match="GUARD_ALREADY_EXISTS"):
            arm_guard(root, dataset, preconditions={"a": 1})


def test_unknown_dataset_rejected() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        with pytest.raises(SecondLookGuardViolation, match="UNKNOWN_SECOND_LOOK_DATASET"):
            arm_guard(root, "BIDMC", preconditions={})


def test_three_guards_fully_independent() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for dataset in DATASETS:
            arm_guard(root, dataset, preconditions={"d": dataset})
        check_and_begin_session(
            root, "INTERNAL_TEST", observed_preconditions={"d": "INTERNAL_TEST"}
        )
        complete_session(root, "INTERNAL_TEST", completion_summary={})
        # INCART and NSTDB must remain untouched (still ARMED) by INTERNAL_TEST's completion.
        assert read_guard_state(root, "INCART")["state"] == "ARMED"
        assert read_guard_state(root, "NSTDB")["state"] == "ARMED"


@pytest.mark.parametrize("dataset", DATASETS)
def test_real_guard_armed_before_any_second_look_access(dataset: str) -> None:
    state = read_guard_state(ROOT, dataset)
    assert state is not None
    assert state["state"] in {"ARMED", "RUNNING", "COMPLETED"}


def test_real_method_freeze_evidence_pass() -> None:
    data = _load("method_freeze.json")
    assert data["status"] == "PASS"
    assert set(data["datasets"]) == set(DATASETS)
    assert all(entry["guard_armed"] for entry in data["datasets"].values())
    assert all(
        entry["second_look_result_exists_at_method_commit"] is False
        for entry in data["datasets"].values()
    )
    population = data["historical_population_expectations"]
    assert all(population["matches_phase_prompt_expectations"].values())


def test_guard_names_distinct_from_v1_and_prior_v2_guards() -> None:
    assert GUARD_NAMES == {
        "INTERNAL_TEST": "V2_INTERNAL_TEST_SECOND_LOOK",
        "INCART": "V2_INCART_SECOND_LOOK",
        "NSTDB": "V2_NSTDB_SECOND_LOOK",
    }


# --------------------------------------------------------------------------
# Pure statistical core (Section 29): synthetic only
# --------------------------------------------------------------------------


def test_paired_bootstrap_delta_basic() -> None:
    v1 = [{"replicate_index": i, "AUROC": 0.80} for i in range(10)]
    v2 = [{"replicate_index": i, "AUROC": 0.82} for i in range(10)]
    deltas = paired_bootstrap_delta(v1, v2, "AUROC")
    assert np.allclose(deltas, 0.02)


def test_paired_bootstrap_delta_requires_aligned_replicate_index() -> None:
    v1 = [{"replicate_index": 0, "AUROC": 0.8}]
    v2 = [{"replicate_index": 1, "AUROC": 0.8}]
    with pytest.raises(V2010StatsError, match="MISALIGNED"):
        paired_bootstrap_delta(v1, v2, "AUROC")


def test_paired_bootstrap_delta_requires_equal_length() -> None:
    v1 = [{"replicate_index": 0, "AUROC": 0.8}]
    v2 = [{"replicate_index": 0, "AUROC": 0.8}, {"replicate_index": 1, "AUROC": 0.8}]
    with pytest.raises(V2010StatsError, match="COUNT_MISMATCH"):
        paired_bootstrap_delta(v1, v2, "AUROC")


def test_paired_bootstrap_delta_handles_undefined_metric_as_nan() -> None:
    v1 = [{"replicate_index": 0, "AUROC": ""}, {"replicate_index": 1, "AUROC": 0.8}]
    v2 = [{"replicate_index": 0, "AUROC": 0.9}, {"replicate_index": 1, "AUROC": 0.85}]
    deltas = paired_bootstrap_delta(v1, v2, "AUROC")
    assert np.isnan(deltas[0])
    assert deltas[1] == pytest.approx(0.05)


def test_paired_bootstrap_summary_ci_bounds() -> None:
    deltas = np.linspace(-0.01, 0.03, 2000)
    summary = paired_bootstrap_summary(0.01, deltas)
    assert summary["point_delta"] == 0.01
    assert summary["ci_lower_95"] < summary["point_delta"] < summary["ci_upper_95"]
    assert summary["valid_replicates"] == 2000


def test_paired_bootstrap_summary_degenerate_raises() -> None:
    with pytest.raises(V2010StatsError, match="DEGENERATE"):
        paired_bootstrap_summary(0.0, np.array([np.nan, np.nan]))


def test_incart_guard_boundary_exactly_zero_passes() -> None:
    assert incart_auroc_runtime_guard_pass(0.0) is True


def test_incart_guard_tiny_negative_within_tolerance_passes() -> None:
    assert incart_auroc_runtime_guard_pass(-1e-13) is True


def test_incart_guard_negative_beyond_tolerance_fails() -> None:
    assert incart_auroc_runtime_guard_pass(-0.001) is False


def test_incart_guard_positive_passes() -> None:
    assert incart_auroc_runtime_guard_pass(0.05) is True


def test_nstdb_no_collapse_all_six_pass() -> None:
    deltas = {snr: 0.01 for snr in SNR_LEVELS_DB}
    assert nstdb_no_collapse_pass(deltas) is True


def test_nstdb_no_collapse_one_negative_fails() -> None:
    deltas = {snr: 0.01 for snr in SNR_LEVELS_DB}
    deltas[-6] = -0.05
    assert nstdb_no_collapse_pass(deltas) is False


def test_nstdb_no_collapse_missing_snr_raises() -> None:
    deltas = {snr: 0.01 for snr in SNR_LEVELS_DB if snr != -6}
    with pytest.raises(V2010StatsError, match="SNR_SET_INCOMPLETE"):
        nstdb_no_collapse_pass(deltas)


def test_nstdb_no_collapse_extra_snr_raises() -> None:
    deltas = {snr: 0.01 for snr in SNR_LEVELS_DB}
    deltas[99] = 0.01
    with pytest.raises(V2010StatsError, match="SNR_SET_INCOMPLETE"):
        nstdb_no_collapse_pass(deltas)


def test_nstdb_no_collapse_boundary_exactly_zero_passes() -> None:
    deltas = {snr: 0.0 for snr in SNR_LEVELS_DB}
    assert nstdb_no_collapse_pass(deltas) is True


@pytest.mark.parametrize(
    ("method_ok", "incart_ok", "nstdb_ok", "expected"),
    [
        (True, True, True, "ACCEPTED"),
        (True, True, False, "NOT_ACCEPTED"),
        (True, False, True, "NOT_ACCEPTED"),
        (False, True, True, "NOT_ACCEPTED"),
        (False, False, False, "NOT_ACCEPTED"),
    ],
)
def test_runtime_acceptance_decision_truth_table(
    method_ok: bool, incart_ok: bool, nstdb_ok: bool, expected: str
) -> None:
    decision = runtime_acceptance_decision(
        method_integrity_pass=method_ok,
        incart_guard_pass=incart_ok,
        nstdb_guard_pass=nstdb_ok,
    )
    assert decision == expected


def test_internal_test_never_participates_in_runtime_decision_signature() -> None:
    import inspect

    parameters = set(inspect.signature(runtime_acceptance_decision).parameters)
    assert "internal_test" not in " ".join(parameters).lower()
