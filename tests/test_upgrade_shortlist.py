"""The upgrade shortlist is a read-only evidence checklist: it explains and ranks stored candidates and never promotes, registers or deploys anything."""

from __future__ import annotations

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
