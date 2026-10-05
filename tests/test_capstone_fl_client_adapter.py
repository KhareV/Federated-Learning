# ruff: noqa: E501
"""CAP-006: CAPSTONE_FL_CLIENT_ADAPTER_V1 (FLClient protocol, lifecycle, FedAvg/FedProx mapping, failures)."""

from __future__ import annotations

import asyncio
import inspect
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

import product.federation.client as client_module
from product.edge.local_training_buffer import BufferError, LocalTrainingBufferV1
from product.edge.virtual import edge_identity_for_site
from product.federation.base import Algorithm, ClientState, FLClient, UpdateSubmission
from product.federation.client import (
    CapstoneFlClientAdapterV1,
    ClientError,
    frozen_fedprox_mu,
    frozen_fl_init_sha,
)
from tests.capstone_local_support import base_state, cohort_buffers, fresh_client, tiny_buffer

ROOT = Path(__file__).resolve().parents[1]


def run(coro):
    return asyncio.run(coro)


def test_the_adapter_satisfies_the_frozen_flclient_protocol_without_altering_it() -> None:
    c = fresh_client(0, tiny_buffer())
    assert isinstance(c, FLClient)
    for name in ("local_train", "produce_update"):
        assert inspect.iscoroutinefunction(getattr(CapstoneFlClientAdapterV1, name))
    assert list(inspect.signature(CapstoneFlClientAdapterV1.local_train).parameters) == ["self", "round_id", "base_state_digest"]
    assert list(inspect.signature(FLClient.local_train).parameters) == ["self", "round_id", "base_state_digest"]
    contract = json.loads((ROOT / "contracts/capstone/fl_client_v1.json").read_text())
    assert contract["methods"]["local_train"]["args"] == ["round_id", "base_state_digest"]


def test_edge_identities_come_from_the_frozen_mapping_for_all_eight_clients() -> None:
    mapping = json.loads((ROOT / "contracts/capstone/edge_node_v1.json").read_text())["simulated_cohort_mapping"]["mapping"]
    for i, buffer in enumerate(cohort_buffers()):
        c = fresh_client(i)
        assert c.identity.edge_node_id == mapping[i]["edge_node_id"] == edge_identity_for_site(i).edge_node_id
        assert c.identity.client_id == mapping[i]["fl_client_id"] == buffer.client_id
        assert buffer.participant_id == mapping[i]["participant_id"]


def test_identity_fields_before_and_after_training() -> None:
    c = fresh_client(0, tiny_buffer())
    ident = c.identity
    assert (ident.client_state, ident.base_model_id, ident.global_round, ident.local_example_count, ident.eligible, ident.update_digest) == (ClientState.IDLE, "FL_INIT_V2", 0, 40, True, None)
    c.prepare()
    run(c.local_train(1, c.base_state_sha))
    ident = c.identity
    assert ident.client_state is ClientState.UPDATE_READY and ident.global_round == 1 and ident.update_digest
    sub = run(c.produce_update())
    assert sub.update_digest == ident.update_digest and sub.examples_seen == 40


def test_lifecycle_idle_dataready_training_updateready_submitted_and_illegal_moves() -> None:
    c = fresh_client(0, tiny_buffer())
    with pytest.raises(ClientError, match="CLIENT_NOT_DATA_READY"):
        run(c.local_train(1, c.base_state_sha))
    with pytest.raises(ClientError, match="NO_UPDATE_READY"):
        run(c.produce_update())
    c.prepare()
    assert c.identity.client_state is ClientState.DATA_READY
    with pytest.raises(Exception, match=r"IDLE|DATA_READY|transition|TRANSITION"):
        c.prepare()  # DATA_READY -> DATA_READY is not a legal transition
    run(c.local_train(1, c.base_state_sha))
    c.mark_submitted()
    assert c.identity.client_state is ClientState.SUBMITTED


def test_zero_example_buffer_stays_ineligible_and_fails_closed() -> None:
    empty = LocalTrainingBufferV1("SIM_FL_SITE_00", "SIM_P000101")
    c = fresh_client(0, empty)
    assert c.identity.eligible is False and c.identity.ineligible_reason == "NONPOSITIVE_EXAMPLES"
    with pytest.raises(ClientError, match="NO_ELIGIBLE_EXAMPLES"):
        c.prepare()
    assert c.identity.client_state is ClientState.IDLE


def test_wrong_base_digest_and_wrong_round_are_rejected_without_changing_state() -> None:
    c = fresh_client(0, tiny_buffer())
    c.prepare()
    with pytest.raises(ClientError, match="BASE_STATE_MISMATCH"):
        run(c.local_train(1, "0" * 64))
    for bad in (0, -1, True, "1", None):
        with pytest.raises(ClientError, match="ROUND_INVALID"):
            run(c.local_train(bad, c.base_state_sha))  # type: ignore[arg-type]
    assert c.identity.client_state is ClientState.DATA_READY


def test_only_fl_init_v2_is_accepted_as_the_base_never_model_v2_final() -> None:
    buf = tiny_buffer()
    identity = edge_identity_for_site(0)
    with pytest.raises(ClientError, match="BASE_MODEL_NOT_ALLOWED"):
        CapstoneFlClientAdapterV1(buf, edge_node_id=identity.edge_node_id, participant_id="SIM_P000101", session_id="s", base_state=base_state(), base_model_id="MODEL_V2_FINAL")
    tampered = type(base_state())(base_state())
    key = next(k for k, v in tampered.items() if np.issubdtype(v.dtype, np.floating))
    tampered[key] = tampered[key] + np.float32(1e-3)
    with pytest.raises(ClientError, match="BASE_STATE_NOT_FL_INIT_V2"):
        CapstoneFlClientAdapterV1(buf, edge_node_id=identity.edge_node_id, participant_id="SIM_P000101", session_id="s", base_state=tampered)
    assert client_module.ALLOWED_BASE_MODEL_IDS == ("FL_INIT_V2",)
    assert frozen_fl_init_sha() == "6a2923ca87793fb78571b4cffad4026f8b4ce99d9dfcb3abe885e259c68a572f"


def test_a_nonfinite_local_input_is_rejected_before_training() -> None:
    buf = tiny_buffer()
    ref = buf.records()[0].model_input_ref
    buf._private[ref][0, 0] = np.nan  # simulate corruption of the private store
    c = fresh_client(0, buf)
    c.prepare()
    with pytest.raises(ClientError, match="NONFINITE_LOCAL_INPUT"):
        run(c.local_train(1, c.base_state_sha))
    assert c.identity.client_state is ClientState.DATA_READY


def test_a_cross_client_buffer_read_is_refused_by_the_buffer() -> None:
    with pytest.raises(BufferError, match="CROSS_CLIENT_INPUT_ACCESS"):
        tiny_buffer().training_arrays(requester_client_id="SIM_FL_SITE_05")


def test_a_genuine_training_failure_moves_the_client_to_failed_never_stuck_in_training(monkeypatch) -> None:
    def boom(**_kwargs):
        raise RuntimeError("nonfinite local loss")
    monkeypatch.setattr(client_module, "train_local_epoch_v2", boom)
    c = fresh_client(0, tiny_buffer())
    c.prepare()
    with pytest.raises(RuntimeError):
        run(c.local_train(1, c.base_state_sha))
    assert c.identity.client_state is ClientState.FAILED


def test_an_update_digest_mismatch_is_detected_before_the_update_is_exposed(monkeypatch) -> None:
    monkeypatch.setattr(client_module, "delta_sha", lambda _delta: "f" * 64)
    c = fresh_client(0, tiny_buffer())
    c.prepare()
    with pytest.raises(ClientError, match="UPDATE_DIGEST_MISMATCH"):
        run(c.local_train(1, c.base_state_sha))
    assert c.identity.client_state is ClientState.FAILED


def test_fedavg_mode_calls_the_existing_fedavg_epoch_and_never_the_fedprox_one(monkeypatch) -> None:
    calls = {"avg": 0, "prox": 0}
    real_avg = client_module.train_local_epoch_v2
    monkeypatch.setattr(client_module, "train_local_epoch_v2", lambda **kw: calls.__setitem__("avg", calls["avg"] + 1) or real_avg(**kw))
    monkeypatch.setattr(client_module, "train_local_fedprox_epoch_v2", lambda **kw: calls.__setitem__("prox", calls["prox"] + 1))
    c = fresh_client(0, tiny_buffer())
    c.prepare()
    run(c.local_train(1, c.base_state_sha))
    assert calls == {"avg": 1, "prox": 0}


def test_fedprox_mode_calls_the_existing_fedprox_epoch_once_with_the_frozen_mu_only(monkeypatch) -> None:
    seen: list[float] = []
    real_prox = client_module.train_local_fedprox_epoch_v2

    def spy(**kw):
        seen.append(kw["mu"])
        return real_prox(**kw)
    monkeypatch.setattr(client_module, "train_local_fedprox_epoch_v2", spy)
    monkeypatch.setattr(client_module, "train_local_epoch_v2", lambda **kw: pytest.fail("FedAvg epoch called in FedProx mode"))
    c = fresh_client(0, tiny_buffer(), Algorithm.FEDPROX)
    c.prepare()
    run(c.local_train(1, c.base_state_sha))
    assert seen == [frozen_fedprox_mu()] == [0.1]  # one call, no mu search
    assert c.identity.client_state is ClientState.UPDATE_READY


def test_local_training_hyperparameters_are_the_frozen_v2_fl_005_constants() -> None:
    from federated import wearable_fl_runner_v1 as runner
    assert (client_module.BASE_SEED, client_module.BATCH_SIZE, client_module.LEARNING_RATE, client_module.WEIGHT_DECAY, client_module.POS_WEIGHT) == (runner.BASE_SEED, runner.BATCH_SIZE, runner.LEARNING_RATE, runner.WEIGHT_DECAY, runner.POS_WEIGHT) == (20260927, 64, 0.001, 0.0001, 1.7157717177396683)
    assert not hasattr(client_module, "torch") and "AdamW" not in Path(client_module.__file__).read_text()


def test_the_submission_projection_has_exactly_the_five_frozen_fields_and_cannot_carry_labels() -> None:
    assert set(UpdateSubmission.model_fields) == {"client_id", "round_id", "base_state_digest", "update_digest", "examples_seen"}
    with pytest.raises(ValueError):
        UpdateSubmission(client_id="c", round_id=1, base_state_digest="a", update_digest="b", examples_seen=1, labels=[1])  # type: ignore[call-arg]


def test_local_fl_code_does_not_import_or_touch_the_monitoring_product() -> None:
    code = ("import sys, product.federation.client, product.federation.update_bridge, product.federation.local_cohort;"
            "bad=[m for m in sys.modules if m.startswith(('product.monitoring','product.inference','product.auth','product.sessions','product.persistence','capstone_persistence','api.','fastapi','starlette','sqlite3'))];"
            "print(bad)")
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, env={"PYTHONPATH": "src:.", "PATH": ""}).stdout.strip()
    assert out.endswith("[]"), out


def test_local_training_has_zero_effect_on_an_existing_monitoring_state_object() -> None:
    from product.devices.manager import DeviceManager
    from product.monitoring.runtime_state import RuntimeState

    state = RuntimeState()
    manager = DeviceManager(state)
    descriptor = manager.create_simulated("demo:faculty", None, "NORMAL_MONITORING")
    snapshot = (descriptor.model_dump_json(), sorted(state.devices), dict(state.sessions), state.device_counter,
                {k: v.source.connection_state.value for k, v in state.devices.items()})
    c = fresh_client(0, tiny_buffer())
    c.prepare()
    run(c.local_train(1, c.base_state_sha))
    after = (descriptor.model_dump_json(), sorted(state.devices), dict(state.sessions), state.device_counter,
             {k: v.source.connection_state.value for k, v in state.devices.items()})
    assert after == snapshot
