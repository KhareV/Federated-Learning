# ruff: noqa: E501
"""CAP-007: multi-round lineage, CAPSTONE_FEDERATION_CONTRACT_V2, checkpoints, FedProx full run."""

from __future__ import annotations

import json

import numpy as np
import pytest

from product.contracts import ROOT, IllegalTransitionError, load_contract
from product.federation.base import RoundState, validate_round_transition
from product.federation.execution_binding import (
    load_binding,
    load_contract_v2,
    round_transitions_v2,
    validate_round_transition_v2,
)
from product.federation.service import RoundTracker
from tests.capstone_federation_support import completed_run, reference


def test_contract_v2_is_an_additive_successor_with_exactly_one_transition_delta() -> None:
    v1, v2 = load_contract("federation"), load_contract_v2()
    assert v2["contract_id"] == "CAPSTONE_FEDERATION_CONTRACT_V2"
    assert v1["contract_id"] == "CAPSTONE_FEDERATION_CONTRACT_V1"  # the V1 file is unchanged
    changed = {s for s in v1["round_transitions"]
               if v1["round_transitions"][s] != v2["round_transitions"][s]}
    assert changed == {"AGGREGATING"}
    assert set(v2["round_transitions"]["AGGREGATING"]) - set(v1["round_transitions"]["AGGREGATING"]) == {"COMPLETED"}
    assert v2["round_states"] == v1["round_states"] and v2["vocabulary_changes"] == []
    assert v2["algorithm_changes"] == []


def test_non_final_round_may_complete_after_aggregating_and_only_the_final_round_creates_a_candidate() -> None:
    non_final, final = RoundTracker(final=False), RoundTracker(final=True)
    for state in ("COLLECTING", "LOCAL_TRAINING", "UPDATES_READY", "AGGREGATING"):
        non_final.move(RoundState(state))
        final.move(RoundState(state))
    non_final.move(RoundState.COMPLETED)
    with pytest.raises(IllegalTransitionError):
        validate_round_transition_v2(RoundState.AGGREGATING, RoundState.COMPLETED, final_round=True)
    with pytest.raises(IllegalTransitionError):
        validate_round_transition_v2(RoundState.AGGREGATING, RoundState.CANDIDATE_CREATED, final_round=False)
    for state in ("CANDIDATE_CREATED", "VALIDATING", "ACCEPTED_TO_SANDBOX", "COMPLETED"):
        final.move(RoundState(state))
    with pytest.raises(IllegalTransitionError):  # the V1 table stays strict
        validate_round_transition(RoundState.AGGREGATING, RoundState.COMPLETED)
    assert round_transitions_v2()["COMPLETED"] == ()


def test_execution_binding_freezes_one_candidate_and_the_lineage_rules() -> None:
    binding = load_binding()
    assert binding["one_candidate_per_run"] is True and binding["intermediate_aggregates_are_round_states"] is True
    assert binding["run_level_base"].startswith("FL_INIT_V2")
    assert binding["candidate_parent"].startswith("FL_INIT_V2")
    assert binding["single_run_shape"]["accepted_updates"] == 24 and binding["normal_run_injected_updates"] == 0


def test_each_round_starts_from_the_previous_committed_state_and_the_candidate_is_the_round_3_state() -> None:
    done, ref = completed_run(), reference()
    bases = done.meta["round_base_digests"]
    committed = done.meta["committed_digests"]
    assert bases["1"] == ref["state_progression"]["0"]["sha256"]
    assert bases["2"] == committed["1"] and bases["3"] == committed["2"]
    candidate = json.loads((done.root / "candidates" / done.run["candidate_ids"][0] / "metadata.json").read_text())
    assert candidate["state_digest"] == committed["3"] == done.meta["final_global_state_sha256"]
    assert candidate["parent_model_id"] == "FL_INIT_V2" and candidate["round"] == 3
    assert len(list((done.root / "candidates").iterdir())) == 1  # exactly one candidate


def test_round_checkpoints_exist_for_non_final_rounds_only() -> None:
    done = completed_run()
    base = done.root / "federation" / "runs" / done.run_id / "checkpoints"
    assert sorted(p.name for p in base.iterdir()) == ["round_1", "round_2"]
    record = json.loads((base / "round_2" / "checkpoint.json").read_text())
    for key in ("run_id", "protocol_id", "cohort_manifest_sha256", "algorithm", "last_committed_round",
                "global_state_sha256", "state_file_sha256", "event_count"):
        assert key in record
    assert record["last_committed_round"] == 2


def test_full_fedprox_run_uses_the_frozen_mu_and_creates_one_finite_candidate() -> None:
    done = completed_run("FEDPROX", "PLAIN")
    assert done.run["status"] == "COMPLETED" and done.run["algorithm"] == "FEDPROX"
    assert len(done.run["candidate_ids"]) == 1
    record = done.meta["training_record"]
    assert sum(len(v) for v in record.values()) == 24
    assert [r["accepted_update_count"] for r in done.rounds] == [8, 8, 8]
    plain = completed_run()
    assert done.meta["final_global_state_sha256"] != plain.meta["final_global_state_sha256"]
    from federated.model_adapter import deserialize_state

    state = deserialize_state((done.root / "candidates" / done.run["candidate_ids"][0] / "state.bin").read_bytes())
    assert all(np.isfinite(v).all() for v in state.values() if np.issubdtype(np.asarray(v).dtype, np.floating))
    mu = json.loads((ROOT / "artifacts/FEDPROX_MU_V2.lock.json").read_text())["selected_mu"]
    assert mu == 0.1
    keys = {key for e in done.events for key in e["payload"]}
    assert not keys & {"accuracy", "auprc", "auroc", "f1", "loss", "metric", "metrics", "score"}
