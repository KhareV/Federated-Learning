# ruff: noqa: E501
"""CAP-006: canonical eight-client local FedAvg training vs the frozen V2-FL-005 round-1 evidence."""

from __future__ import annotations

import asyncio

import numpy as np
import pytest

import federated.aggregation as aggregation_module
import federated.wearable_fl_system_v1 as system_module
from product.federation.local_cohort import reference_evidence
from product.federation.update_bridge import export_envelope
from tests.capstone_local_support import base_state, fresh_client

CLIENTS = [f"SIM_FL_SITE_0{i}" for i in range(8)]


@pytest.fixture(scope="module")
def trained(request):
    mp = pytest.MonkeyPatch()
    trips = {"aggregate": 0}

    def trip(*_a, **_k):
        trips["aggregate"] += 1
        raise AssertionError("aggregation/coordinator must not run in CAP-006")
    mp.setattr(aggregation_module, "aggregate_weighted_deltas", trip)
    mp.setattr(system_module, "aggregate_weighted_deltas", trip)
    for name in ("submit", "submit_meta", "aggregate", "commit", "open"):
        mp.setattr(system_module.Coordinator, name, trip)
    out = {}
    for i in range(8):
        c = fresh_client(i)
        c.prepare()
        asyncio.run(c.local_train(1, c.base_state_sha))
        envelope, report = export_envelope(c, base_state())
        out[c.identity.client_id] = (c, envelope, report, asyncio.run(c.produce_update()))
    request.addfinalizer(mp.undo)
    return out, trips


def test_eight_local_trainings_from_fl_init_v2_with_no_aggregation_or_coordinator_call(trained) -> None:
    out, trips = trained
    assert sorted(out) == CLIENTS and trips["aggregate"] == 0
    for client, _env, _rep, _sub in out.values():
        assert client.identity.base_model_id == "FL_INIT_V2" and client.identity.client_state.value == "UPDATE_READY"


def test_round_one_examples_shuffle_seeds_and_update_shas_equal_the_frozen_v2_fl_005_evidence(trained) -> None:
    out, _ = trained
    ref = reference_evidence()["round1"]
    assert {c: s.examples_seen for c, (_c, _e, _r, s) in out.items()} == ref["examples_seen"]
    assert {c: str(client._result.shuffle_seed) for c, (client, _e, _r, _s) in out.items()} == ref["shuffle_seeds"]
    assert {c: s.update_digest for c, (_c, _e, _r, s) in out.items()} == ref["update_sha256"]
    assert {s.base_state_digest for (_c, _e, _r, s) in out.values()} == {ref["base_global_state_sha256"]}
    for client, _env, _rep, _sub in out.values():
        assert client._result.update_bytes == ref["diagnostics_not_in_digest"][client.identity.client_id]["payload_bytes"]


def test_every_update_is_finite_valid_and_contains_no_forbidden_data(trained) -> None:
    for _client, envelope, report, submission in trained[0].values():
        assert report["forbidden_findings"] == [] and report["all_floating_finite"] and report["update_digest_matches_payload"]
        assert envelope["update_sha256"] == submission.update_digest and envelope["examples_seen"] == submission.examples_seen > 0
        assert all(np.isfinite(v).all() for v in envelope["payload"]["delta"].values() if np.issubdtype(v.dtype, np.floating))
