# ruff: noqa: E501
"""Imported federated research checkpoints (V2-FL-001, 50 rounds) in the candidate library: a third cohort value (REAL_ECG, no synthetic cohort) that only occurs with its own source kind."""

from __future__ import annotations

import pytest

from scripts import register_research_candidates as rr
from studio import candidates as cand
from studio.candidates import CandidateError, CandidateLibrary, audit_of, cohort_label


@pytest.fixture(scope="module")
def r50_state():
    from scripts.fl50_cohort_runs import load_fl50_state

    return load_fl50_state()


def _args(state, **over):
    base = dict(owner="user-a", candidate_id="RESEARCH_X", source_run_id="V2-FL-001", source_kind=cand.RESEARCH_KIND, source_detail={}, cohort=cand.REAL_ECG, evaluation_cohort_id="E", run_length=50,
                algorithm="FEDAVG", secagg_mode="PLAIN", base_model={"model_id": "FL_INIT_V2"}, state=state, metrics={"AUPRC": 0.8, "AUROC": 0.9, "F1": 0.7, "windows": 10})
    return base | over


def test_the_real_ecg_cohort_and_the_research_kind_only_occur_together(tmp_path, r50_state):
    lib = CandidateLibrary(tmp_path)
    with pytest.raises(CandidateError, match="COHORT_AND_SOURCE_KIND_INCONSISTENT"):
        lib.register(**_args(r50_state, cohort="REALISTIC"))                                  # a research checkpoint cannot claim a synthetic cohort
    with pytest.raises(CandidateError, match="COHORT_AND_SOURCE_KIND_INCONSISTENT"):
        lib.register(**_args(r50_state, source_kind="SYNTHETIC_COHORT"))                      # a synthetic run cannot claim the real-ECG cohort
    with pytest.raises(CandidateError, match="UNKNOWN_COHORT"):
        lib.register(**_args(r50_state, cohort="MADE_UP"))
    assert lib.list("user-a") == []                                                           # nothing was stored by the refusals


def test_a_research_candidate_is_labelled_for_what_it_was_trained_on_and_is_never_promoted(tmp_path, r50_state):
    lib = CandidateLibrary(tmp_path)
    entry = lib.register(**_args(r50_state))
    assert entry["cohort"] == "REAL_ECG" and entry["promoted"] is False and entry["deployed"] is False and entry["used_for_monitoring"] is False
    assert "no synthetic cohort" in cohort_label("REAL_ECG") and "Realistic" in cohort_label("REALISTIC")
    audit = audit_of(entry)
    assert "real MIT-BIH" in audit["label"] and "REAL MIT-BIH AAMI_SVF_WINDOW_V1" in audit["training_target_of_checkpoint"] and "SYNTHETIC" not in audit["training_target_of_checkpoint"]
    state, start = lib.load_for_start("user-a", "RESEARCH_X")                                 # it can start a run: digest and layout verified
    assert start["candidate_cohort"] == "REAL_ECG" and start["strict_load_round_trip_equal"] is True and list(state) == list(r50_state)


def test_registering_the_two_v2_fl_001_checkpoints_is_idempotent_and_records_their_provenance(tmp_path, monkeypatch):
    monkeypatch.setattr(rr, "metrics_on_real_validation", lambda state: {"AUPRC": 0.8, "AUROC": 0.9, "F1": 0.7, "windows": 2880})      # the real-window scoring is exercised by the live registration
    first = rr.register_all("user-a", tmp_path)
    second = rr.register_all("user-a", tmp_path)
    assert [e["candidate_id"] for e in first] == ["RESEARCH_FL_V2_FL001_R50", "RESEARCH_FL_V2_FL001_R38_BEST"] == [e["candidate_id"] for e in second]
    assert [e["round_id"] for e in first] == [50, 38] and {e["state_sha256"] for e in first} == {e["state_sha256"] for e in second} and len({e["state_sha256"] for e in first}) == 2
    for e in first:
        assert e["cohort"] == "REAL_ECG" and e["source_kind"] == "RESEARCH_FEDERATED_CHECKPOINT" and e["base_model"]["model_id"] == "FL_INIT_V2" and "NOT used" in e["base_model"]["label"]
        assert e["source_detail"]["checkpoint_sha256"] in (rr.FL50_SHA256, rr.FL50_BEST_SHA256) and e["source_detail"]["experiment_id"] == "FL_IID_MODEL_V2_V1"
    assert len(list(tmp_path.rglob("candidate.json"))) == 2
    assert CandidateLibrary(tmp_path).list("user-b") == []                                    # owner-scoped like every candidate


def test_a_candidate_of_the_recorded_noise_cohort_is_accepted_labelled_and_never_confused_with_real_ecg(tmp_path, r50_state):
    lib = CandidateLibrary(tmp_path)
    entry = lib.register(**_args(r50_state, source_kind="SYNTHETIC_COHORT", cohort="REALISTIC_NSTDB", candidate_id="FL10_CANDIDATE_X"))
    assert entry["cohort"] == "REALISTIC_NSTDB" and "recorded noise" in cohort_label("REALISTIC_NSTDB").lower()
    assert audit_of(entry)["candidate_cohort"] == "REALISTIC_NSTDB" and "SYNTHETIC" in audit_of(entry)["training_target_of_checkpoint"]
    with pytest.raises(CandidateError, match="COHORT_AND_SOURCE_KIND_INCONSISTENT"):           # the real-ECG marker still only goes with the research kind
        lib.register(**_args(r50_state, source_kind="SYNTHETIC_COHORT", cohort=cand.REAL_ECG, candidate_id="OTHER"))

