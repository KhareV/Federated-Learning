# ruff: noqa: E501
"""Audit item 4: the executed SITE_00 monitored windows are the tensors the FL trainer consumed; an unrelated regenerated dataset is rejected."""

from __future__ import annotations

import asyncio
import dataclasses

import pytest

from federated.virtual_client_source_v1 import build_local_dataset, stream_windows
from federated.wearable_fl_runner_v1 import new_session
from federated.wearable_sim_local_labels import SyntheticObservedSource
from final_showcase import link_trace as lt
from final_showcase import live_link as ll
from product.edge.label_adapter import SimulationLabelAdapterV1
from product.edge.local_training_buffer import LocalTrainingBufferV1
from product.federation.client import CapstoneFlClientAdapterV1
from product.federation.service import get_cohort
from simulation.fl_cohort_v1 import cohort_profiles


def _train_once(buffer: LocalTrainingBufferV1, tap: lt.TrainerTap) -> CapstoneFlClientAdapterV1:
    base, _ = new_session()
    first = get_cohort().clients[0]
    adapter = CapstoneFlClientAdapterV1(buffer, edge_node_id=first.edge_node_id, participant_id=first.participant_id, session_id=first.session_id, base_state=base)
    adapter.prepare()
    with tap:
        asyncio.run(adapter.local_train(1, adapter.base_state_sha))
    return adapter


def _monitored_dataset():
    profile = cohort_profiles()[0]
    return ll.dataset_from_windows(stream_windows(SyntheticObservedSource(profile)), profile)


def _buffer_for(dataset) -> LocalTrainingBufferV1:
    first = get_cohort().clients[0]
    buffer = LocalTrainingBufferV1(first.client_id, first.participant_id)
    buffer.ingest_dataset(dataset)
    return buffer


def _unrelated():
    other = cohort_profiles()[3]
    first = get_cohort().clients[0]
    dataset = build_local_dataset(SyntheticObservedSource(other), SimulationLabelAdapterV1(other))
    return dataclasses.replace(dataset, client_id=first.client_id, participant_id=first.participant_id, session_id=first.session_id)


def test_trainer_consumes_exactly_the_monitored_window_tensors():
    dataset = _monitored_dataset()
    buffer, tap = _buffer_for(dataset), lt.TrainerTap()
    _train_once(buffer, tap)
    trace = lt.verify_trace(lt.expected_trace(dataset), lt.buffer_trace(buffer), tap.calls, client_id=buffer.client_id, rounds=1)
    assert trace["verified"] and trace["windows"] == len(dataset.labels) and trace["trainer_calls"][0]["examples_seen"] == len(dataset.labels)
    assert trace["trainer_calls"][0]["inputs_sha256"] == lt.expected_trace(dataset)["inputs_sha256"]


def test_link_that_trains_from_an_unrelated_regenerated_dataset_is_rejected():
    monitored = _monitored_dataset()
    unrelated = _unrelated()
    assert unrelated.dataset_sha256 != monitored.dataset_sha256
    # (a) the buffer itself is not the monitored windows
    buffer, tap = _buffer_for(unrelated), lt.TrainerTap()
    _train_once(buffer, tap)
    with pytest.raises(lt.LinkTraceError) as info:
        lt.verify_trace(lt.expected_trace(monitored), lt.buffer_trace(buffer), tap.calls, client_id=buffer.client_id, rounds=1)
    assert info.value.code == "BUFFER_NOT_FROM_MONITORED_WINDOWS"
    # (b) a spoofed buffer report (claims the monitored windows) cannot hide what the trainer was actually handed
    with pytest.raises(lt.LinkTraceError) as info:
        lt.verify_trace(lt.expected_trace(monitored), lt.buffer_trace(_buffer_for(monitored)), tap.calls, client_id=buffer.client_id, rounds=1)
    assert info.value.code == "TRAINER_INPUT_NOT_THE_MONITORED_WINDOWS"


def test_missing_round_or_altered_label_is_rejected():
    dataset = _monitored_dataset()
    buffer, tap = _buffer_for(dataset), lt.TrainerTap()
    _train_once(buffer, tap)
    with pytest.raises(lt.LinkTraceError, match="SITE_NOT_TRAINED_EVERY_ROUND"):
        lt.verify_trace(lt.expected_trace(dataset), lt.buffer_trace(buffer), tap.calls, client_id=buffer.client_id, rounds=3)
    flipped = lt.expected_trace(dataclasses.replace(dataset, labels=1 - dataset.labels))
    with pytest.raises(lt.LinkTraceError):
        lt.verify_trace(flipped, lt.buffer_trace(buffer), tap.calls, client_id=buffer.client_id, rounds=1)


def test_tap_is_removed_after_use_and_does_not_alter_training():
    import product.federation.client as client_module

    original = client_module.train_local_epoch_v2
    dataset = _monitored_dataset()
    tapped_buffer, tap = _buffer_for(dataset), lt.TrainerTap()
    tapped_adapter = _train_once(tapped_buffer, tap)
    assert client_module.train_local_epoch_v2 is original
    plain = _buffer_for(dataset)
    base, _ = new_session()
    first = get_cohort().clients[0]
    adapter = CapstoneFlClientAdapterV1(plain, edge_node_id=first.edge_node_id, participant_id=first.participant_id, session_id=first.session_id, base_state=base)
    adapter.prepare()
    asyncio.run(adapter.local_train(1, adapter.base_state_sha))
    assert adapter.identity.update_digest == tapped_adapter.identity.update_digest is not None   # observation changed nothing
