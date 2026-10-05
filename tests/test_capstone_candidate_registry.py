# ruff: noqa: E501
"""CAP-007: CAPSTONE_MODEL_REGISTRY_V1 (namespaces, atomic IDs, artifacts, tamper, SQL hygiene)."""

from __future__ import annotations

import json
import sqlite3
import threading

import pytest

from capstone_persistence.federation_store import FederationStore
from capstone_persistence.store import CapstoneSqliteStore
from federated.model_v2_fl import state_sha
from federated.wearable_fl_runner_v1 import new_session
from product.auth.base import AuthIdentity, AuthProviderType
from product.federation.base import Algorithm
from product.models.candidate_artifacts import CandidateArtifactError, CandidateArtifactStore
from product.models.registry import ModelRegistry
from tests.capstone_federation_support import completed_run


def _registry(tmp_path):
    store = CapstoneSqliteStore(tmp_path / "p.sqlite3")
    store.upsert_user(AuthIdentity(user_id="demo:r", display_name="r", auth_provider=AuthProviderType.DEMO,
                                   auth_session_id="s", demo_mode=True))
    fed = FederationStore(tmp_path / "p.sqlite3")
    fed.insert_run(run_id="RUN-1", user_id="demo:r", run_type="LIVE_RUN", base_model_id="FL_INIT_V2",
                   protocol_id="V2_FL_WEARABLE_SYSTEM_PROTOCOL_V1", algorithm="FEDAVG",
                   secagg_mode="PLAIN", planned_rounds=3)
    return fed, ModelRegistry(fed, CandidateArtifactStore(tmp_path / "cands"))


def _make(registry, run="RUN-1"):
    state, _ = new_session()
    return registry.create_candidate(federation_run_id=run, parent_model_id="FL_INIT_V2", round_id=3,
                                     algorithm=Algorithm.FEDAVG, client_count=8, state=state,
                                     extra_metadata={})


def test_first_candidate_is_0001_with_fl_init_parent_and_sandbox_unreachable_defaults(tmp_path) -> None:
    _fed, registry = _registry(tmp_path)
    candidate = _make(registry)
    assert candidate.candidate_id == "CAPSTONE_FL_CANDIDATE_0001" and candidate.parent_model_id == "FL_INIT_V2"
    assert candidate.governance_status.value == "CREATED" and candidate.validation_status.value == "PENDING"
    assert candidate.sandbox_status.value == "NOT_IN_SANDBOX" and candidate.production_deployed is False
    assert candidate.claim_boundary == "CAPSTONE_ENGINEERING_SANDBOX_CANDIDATE_NOT_SCIENTIFIC_RELEASE"
    state, _ = new_session()
    assert candidate.state_digest == state_sha(state)


def test_ids_are_allocated_atomically_across_concurrent_creators(tmp_path) -> None:
    fed, registry = _registry(tmp_path)
    for n in range(2, 6):
        fed.insert_run(run_id=f"RUN-{n}", user_id="demo:r", run_type="LIVE_RUN", base_model_id="FL_INIT_V2",
                       protocol_id="V2_FL_WEARABLE_SYSTEM_PROTOCOL_V1", algorithm="FEDAVG",
                       secagg_mode="PLAIN", planned_rounds=3)
    ids: list[str] = []
    threads = [threading.Thread(target=lambda n=n: ids.append(_make(registry, f"RUN-{n}").candidate_id))
               for n in range(2, 6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(ids) == [f"CAPSTONE_FL_CANDIDATE_{n:04d}" for n in range(1, 5)]


def test_an_existing_artifact_directory_forces_the_next_number(tmp_path) -> None:
    _fed, registry = _registry(tmp_path)
    (tmp_path / "cands" / "CAPSTONE_FL_CANDIDATE_0001").mkdir()
    (tmp_path / "cands" / "CAPSTONE_FL_CANDIDATE_0001" / "x").write_text("squatter")
    assert _make(registry).candidate_id == "CAPSTONE_FL_CANDIDATE_0002"


def test_artifact_is_written_then_verified_and_tampering_is_detected(tmp_path) -> None:
    _fed, registry = _registry(tmp_path)
    candidate = _make(registry)
    store = registry.artifacts
    assert state_sha(store.load_verified(candidate.candidate_id, candidate.state_digest)) == candidate.state_digest
    assert sorted(p.name for p in (tmp_path / "cands" / candidate.candidate_id).iterdir()) == ["metadata.json", "state.bin"]
    assert not list((tmp_path / "cands").glob(".*"))  # no temp directory left behind
    blob = tmp_path / "cands" / candidate.candidate_id / "state.bin"
    data = bytearray(blob.read_bytes())
    data[len(data) // 2] ^= 0xFF
    blob.write_bytes(bytes(data))
    with pytest.raises(CandidateArtifactError) as error:
        store.load_verified(candidate.candidate_id, candidate.state_digest)
    assert error.value.code == "CANDIDATE_FILE_HASH_MISMATCH"


def test_released_namespace_is_frozen_and_candidates_never_enter_it(tmp_path) -> None:
    _fed, registry = _registry(tmp_path)
    _make(registry)
    released = {m.model_id: m.role for m in registry.released()}
    assert released == {"MODEL_V2_FINAL": "RELEASED_DEFAULT", "MODEL_V1": "ROLLBACK_REFERENCE"}
    view = registry.view()
    assert view["released_default_model_id"] == "MODEL_V2_FINAL"
    assert [c.candidate_id for c in view["capstone_fl_candidates"]] == ["CAPSTONE_FL_CANDIDATE_0001"]
    assert all(not m.model_id.startswith("CAPSTONE_FL_CANDIDATE") for m in view["released_scientific"])


def test_candidate_weights_never_enter_sqlite_and_only_the_five_policy_tables_are_used() -> None:
    done = completed_run()
    connection = sqlite3.connect(done.root / "product.sqlite3")
    blobs = connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    assert not any("event" in n[0] and "federation" in n[0] for n in blobs)
    for (table,) in blobs:
        columns = [r[1] for r in connection.execute(f"PRAGMA table_info({table})")]
        for column in columns:
            kinds = {r[0] for r in connection.execute(f"SELECT DISTINCT typeof({column}) FROM {table}")}
            if table in ("candidate_models", "federation_runs", "federation_rounds", "fl_client_statuses",
                         "governance_decisions"):
                assert "blob" not in kinds, (table, column)
    counts = {t: connection.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in (
        "federation_runs", "federation_rounds", "fl_client_statuses", "candidate_models", "governance_decisions")}
    assert counts == {"federation_runs": 1, "federation_rounds": 3, "fl_client_statuses": 24,
                      "candidate_models": 1, "governance_decisions": 1}
    row = connection.execute("SELECT production_deployed, claim_boundary, parent_model_id FROM candidate_models").fetchone()
    assert row == (0, "CAPSTONE_ENGINEERING_SANDBOX_CANDIDATE_NOT_SCIENTIFIC_RELEASE", "FL_INIT_V2")
    assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    assert json.loads(connection.execute("SELECT candidate_ids_json FROM federation_runs").fetchone()[0]) == [
        "CAPSTONE_FL_CANDIDATE_0001"]
