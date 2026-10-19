"""The upgrade shortlist is a read-only evidence checklist: it explains and ranks stored candidates and never promotes, registers or deploys anything."""

from __future__ import annotations

import pytest

from studio import upgrade_shortlist as u


def _entry(candidate_id: str, *, cohort: str = "REALISTIC", source_kind: str = "SYNTHETIC_COHORT", f1: float | None = 0.7) -> dict:
    return {"candidate_id": candidate_id, "label": "ENGINEERING CANDIDATE - NOT PROMOTED - NOT CLINICAL", "cohort": cohort, "source_kind": source_kind, "run_length": 10, "round_id": 10,
            "evaluation_cohort_id": "E", "metrics": {"F1": f1} if f1 is not None else None, "promoted": False, "deployed": False}


def test_the_real_external_check_gives_the_research_checkpoints_a_comparable_but_not_better_verdict():
    shortlist = u.build([_entry("RESEARCH_FL_V2_FL001_R50", cohort="REAL_ECG", source_kind="RESEARCH_FEDERATED_CHECKPOINT", f1=0.696), _entry("RESEARCH_FL_V2_FL001_R38_BEST", cohort="REAL_ECG", source_kind="RESEARCH_FEDERATED_CHECKPOINT", f1=0.69)])
    assert shortlist["policy_id"] == "UPGRADE_SHORTLIST_POLICY_V1" and shortlist["released_model"]["model_id"] == "MODEL_V2_FINAL"
    for row in shortlist["entries"]:
        by = {c["id"]: c["status"] for c in row["checks"]}
        assert by["S1"] == "PASS" and by["S2"] == "PASS" and by["S4"] == "PASS" and by["S5"] == "PASS"
        assert by["S3"] == "FAIL"                                                      # the federated model matches the central one on real ECG; it does not beat it
        assert by["S6"] == "NOT_EVIDENCED" and by["S7"] == "NOT_EVIDENCED"             # no calibration and no release decision exist for any candidate
        assert row["tier"] == "COMPARABLE_NOT_BETTER" and row["promoted"] is False and row["deployed"] is False


def test_synthetic_cohort_and_assigned_label_candidates_are_never_shortlisted_whatever_their_synthetic_score():
    shortlist = u.build([_entry("FL10_CANDIDATE_FL10RUN-A", f1=0.99), _entry("FL10_CANDIDATE_HDFLRUN-B", cohort="REALISTIC_NSTDB", source_kind="RECORDED_HARDWARE", f1=0.99)])
    assert [r["tier"] for r in shortlist["entries"]] == ["NOT_SHORTLISTED", "NOT_SHORTLISTED"]
    for row in shortlist["entries"]:
        by = {c["id"]: c["status"] for c in row["checks"]}
        assert by["S1"] == "NOT_EVIDENCED" and by["S4"] == "FAIL" and by["S5"] == "PASS"       # a perfect synthetic score cannot make up for missing real-ECG evidence
    assert "assigned labels" in shortlist["entries"][1]["checks"][3]["detail"] or "assigned labels" in shortlist["entries"][0]["checks"][3]["detail"]


def test_a_degenerate_fixed_threshold_fails_and_a_missing_snapshot_is_not_evidenced():
    degenerate = u.evaluate(_entry("X", f1=0.35), None)
    missing = u.evaluate(_entry("Y", f1=None), None)
    assert {c["id"]: c["status"] for c in degenerate["checks"]}["S5"] == "FAIL"
    assert {c["id"]: c["status"] for c in missing["checks"]}["S5"] == "NOT_EVIDENCED"


def test_ranking_orders_by_evidence_and_the_note_says_a_shortlist_is_not_an_upgrade():
    shortlist = u.build([_entry("FL10_CANDIDATE_Z"), _entry("RESEARCH_FL_V2_FL001_R50", cohort="REAL_ECG", source_kind="RESEARCH_FEDERATED_CHECKPOINT", f1=0.696)])
    assert [r["candidate_id"] for r in shortlist["entries"]] == ["RESEARCH_FL_V2_FL001_R50", "FL10_CANDIDATE_Z"] and [r["rank"] for r in shortlist["entries"]] == [1, 2]
    assert "not an upgrade" in shortlist["note"].lower() and "never" not in shortlist["note"].lower() or "Nothing here promotes" in shortlist["note"]
    assert u.build([])["entries"] == []


FL10 = "WEARABLE_SIM_FL10_EVAL_HOLDOUT_V1"


def _synthetic(candidate_id: str, *, auroc: float, auprc: float, f1: float, cohort_id: str = FL10, source_kind: str = "SYNTHETIC_COHORT", cohort: str = "ORIGINAL") -> dict:
    return _entry(candidate_id, cohort=cohort, source_kind=source_kind, f1=f1) | {"evaluation_cohort_id": cohort_id, "metrics": {"AUROC": auroc, "AUPRC": auprc, "F1": f1}}


def test_a_synthetic_candidate_that_beats_the_released_model_on_its_own_cohort_is_shortlisted_for_sandbox_reuse_with_its_risks():
    shortlist = u.build([_synthetic("FL10_CANDIDATE_GOOD", auroc=0.999, auprc=0.997, f1=0.96), _synthetic("FL10_CANDIDATE_HW", auroc=0.99, auprc=0.98, f1=0.9, source_kind="RECORDED_HARDWARE")])
    assert shortlist["references"][FL10]["AUROC"] == pytest.approx(0.930841, abs=1e-5)                    # the released V2 scored on the same cohort (independently recomputed round-0 metrics)
    for row in shortlist["entries"]:
        assert row["tier"] == "SHORTLISTED_FOR_SANDBOX_REUSE" and {c["id"]: c["status"] for c in row["engineering"]} == {"E1": "PASS", "E2": "PASS", "E3": "PASS"}
        assert row["promoted"] is False and row["deployed"] is False
        assert {r["id"] for r in row["risks"]} >= {"R1", "R3"}                                           # the caveats travel with the shortlisting
    assert "R2" in {r["id"] for r in shortlist["entries"][1]["risks"]} or "R2" in {r["id"] for r in shortlist["entries"][0]["risks"]}   # assigned labels are named for the hardware one
    assert "never a case for deployment" in shortlist["note"] or "never a case for deployment" in u.__doc__


def test_the_engineering_track_needs_a_real_gain_on_both_metrics_a_usable_threshold_and_a_reference():
    weak = u.evaluate(_synthetic("X", auroc=0.94, auprc=0.95, f1=0.9), None, u._reference(u.ROOT))                # AUROC gain 0.009 < 0.02
    flat = u.evaluate(_synthetic("Y", auroc=0.99, auprc=0.99, f1=0.3), None, u._reference(u.ROOT))               # beats the reference but degenerate at 0.5
    none = u.evaluate(_synthetic("Z", auroc=0.99, auprc=0.99, f1=0.9, cohort_id="UNKNOWN_COHORT"), None, u._reference(u.ROOT))
    assert {c["id"]: c["status"] for c in weak["engineering"]}["E1"] == "FAIL" and weak["tier"] == "NOT_SHORTLISTED"
    assert {c["id"]: c["status"] for c in flat["engineering"]}["E2"] == "FAIL" and flat["tier"] == "NOT_SHORTLISTED"
    assert {c["id"]: c["status"] for c in none["engineering"]}["E3"] == "NOT_EVIDENCED" and none["tier"] == "NOT_SHORTLISTED"


def test_the_real_ecg_track_still_outranks_and_a_shortlist_is_still_not_an_upgrade():
    shortlist = u.build([_synthetic("FL10_CANDIDATE_GOOD", auroc=0.999, auprc=0.997, f1=0.96)])
    assert shortlist["entries"][0]["checks"][0]["status"] == "NOT_EVIDENCED" and shortlist["entries"][0]["tier"] != "SHORTLISTED_FOR_REVIEW"     # no synthetic score can reach the review tier
