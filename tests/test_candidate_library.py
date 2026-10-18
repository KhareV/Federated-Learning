# ruff: noqa: E501
"""The candidate library: durable, owner-scoped, digest-verified engineering candidates."""

from __future__ import annotations

from collections import OrderedDict

import numpy as np
import pytest

from federated.model_adapter import serialize_state
from studio import v2_init
from studio.candidates import CandidateError, CandidateLibrary, default_root


@pytest.fixture(scope="module")
def v2_state():
    return v2_init.load_v2_final()[0]


def _register(lib, state, owner="user-a", cid="FL10_CANDIDATE_FL10RUN-A", cohort="REALISTIC", **over):
    args = dict(owner=owner, candidate_id=cid, source_run_id="FL10RUN-A", source_kind="SYNTHETIC_COHORT", source_detail={"source_mode": "CANONICAL_SYNTHETIC"}, cohort=cohort, evaluation_cohort_id="E",
                run_length=10, algorithm="FEDAVG", secagg_mode="PLAIN", base_model={"model_id": "MODEL_V2_FINAL"}, state=state, metrics={"AUPRC": 0.8, "AUROC": 0.9, "junk": 1})
    return lib.register(**(args | over))


def _nudged(state):
    out = OrderedDict((k, v.copy()) for k, v in state.items())
    first = next(k for k, v in out.items() if np.issubdtype(v.dtype, np.floating) and v.ndim >= 1)
    out[first] = out[first] + np.float32(1e-3)
    return out


def test_a_registered_candidate_is_stored_listed_and_survives_a_new_library_instance(tmp_path, v2_state):
    entry = _register(CandidateLibrary(tmp_path), v2_state)
    assert entry["promoted"] is False and entry["deployed"] is False and entry["registered_in_product_registry"] is False and entry["used_for_monitoring"] is False
    assert entry["metrics"] == {"AUPRC": 0.8, "AUROC": 0.9}                              # only the known metric keys are kept
    again = CandidateLibrary(tmp_path)                                                    # a new process / restart
    assert [e["candidate_id"] for e in again.list("user-a")] == ["FL10_CANDIDATE_FL10RUN-A"]
    assert again.get("user-a", "FL10_CANDIDATE_FL10RUN-A")["cohort"] == "REALISTIC"


def test_a_candidate_belongs_to_its_owner(tmp_path, v2_state):
    lib = CandidateLibrary(tmp_path)
    _register(lib, v2_state)
    assert lib.list("user-b") == []
    with pytest.raises(LookupError):
        lib.get("user-b", "FL10_CANDIDATE_FL10RUN-A")
    with pytest.raises(LookupError):
        lib.load_for_start("user-b", "FL10_CANDIDATE_FL10RUN-A")


def test_registering_twice_is_idempotent_and_a_different_state_under_the_same_id_is_refused(tmp_path, v2_state):
    lib = CandidateLibrary(tmp_path)
    first = _register(lib, v2_state)
    assert _register(lib, v2_state) == first and len(lib.list("user-a")) == 1
    with pytest.raises(CandidateError) as error:
        _register(lib, _nudged(v2_state))
    assert error.value.code == "CANDIDATE_ID_REUSED_WITH_DIFFERENT_STATE"


def test_loading_for_a_start_returns_the_exact_state_with_an_audit(tmp_path, v2_state):
    lib = CandidateLibrary(tmp_path)
    _register(lib, _nudged(v2_state))
    state, audit = lib.load_for_start("user-a", "FL10_CANDIDATE_FL10RUN-A")
    assert audit["kind"] == "CANDIDATE" and audit["model_id"] == "FL10_CANDIDATE_FL10RUN-A" and audit["candidate_cohort"] == "REALISTIC" and audit["parent_model_id"] == "MODEL_V2_FINAL"
    assert audit["state_sha256"] == lib.get("user-a", "FL10_CANDIDATE_FL10RUN-A")["state_sha256"] and list(state) == list(v2_state)
    assert audit["state_sha256"] != v2_init.load_v2_final()[1]["state_sha256"]


def test_a_tampered_state_file_fails_closed(tmp_path, v2_state):
    lib = CandidateLibrary(tmp_path)
    _register(lib, v2_state)
    next(tmp_path.rglob("state.bin")).write_bytes(serialize_state(_nudged(v2_state)))
    with pytest.raises(CandidateError) as error:
        lib.load_for_start("user-a", "FL10_CANDIDATE_FL10RUN-A")
    assert error.value.code == "CANDIDATE_STATE_DIGEST_MISMATCH"


def test_a_state_with_the_wrong_layout_cannot_be_registered(tmp_path, v2_state):
    broken = OrderedDict(v2_state)
    broken.popitem()
    with pytest.raises(CandidateError) as error:
        _register(CandidateLibrary(tmp_path), broken)
    assert error.value.code == "STATE_KEYS_OR_ORDER_DIFFER"


def test_an_incomplete_entry_is_never_listed_and_ids_cannot_escape_the_library(tmp_path, v2_state):
    lib = CandidateLibrary(tmp_path)
    _register(lib, v2_state)
    next(tmp_path.rglob("candidate.json")).unlink()                                       # the metadata file is written last: without it the entry does not exist
    assert lib.list("user-a") == []
    for bad in ("../x", "a/b", ".hidden", ""):
        with pytest.raises(CandidateError):
            lib.get("user-a", bad)


def test_the_default_location_is_stable_and_configurable(monkeypatch, tmp_path):
    monkeypatch.delenv("NHM_CANDIDATE_LIBRARY_DIR", raising=False)
    assert default_root().as_posix().endswith("data/studio_candidates")
    assert default_root({"NHM_CANDIDATE_LIBRARY_DIR": str(tmp_path)}) == tmp_path
