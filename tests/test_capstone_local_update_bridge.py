# ruff: noqa: E501
"""CAP-006: CAPSTONE_FL_UPDATE_BRIDGE_V1 - the existing V2 envelope, data-locality and delta validity."""

from __future__ import annotations

import asyncio
import copy

import numpy as np
import pytest

from federated.wearable_fl_system_v1 import ENVELOPE_FIELDS, PAYLOAD_FIELD, scan_forbidden
from product.federation.client import ClientError
from product.federation.update_bridge import (
    SUBMISSION_FIELD_MAP,
    export_envelope,
    submission_from_envelope,
    validate_envelope,
)
from tests.capstone_local_support import base_state, fresh_client, tiny_buffer


def _trained(n: int = 40):
    c = fresh_client(0, tiny_buffer(n))
    c.prepare()
    asyncio.run(c.local_train(1, c.base_state_sha))
    return c


def test_the_bridge_exposes_exactly_the_existing_v2_envelope_with_zero_forbidden_findings() -> None:
    c = _trained()
    envelope, report = export_envelope(c, base_state())
    assert sorted(k for k in envelope if k != PAYLOAD_FIELD) == sorted(ENVELOPE_FIELDS)
    assert envelope["protocol_version"] == "V2_FL_WEARABLE_SYSTEM_PROTOCOL_V1" and envelope["engineering_only"] is True
    assert envelope["base_global_state_sha256"] == c.base_state_sha
    assert scan_forbidden(envelope) == [] and report["forbidden_findings"] == []
    assert list(envelope[PAYLOAD_FIELD]) == ["delta"]


def test_delta_validity_keys_shapes_dtypes_finiteness_and_integer_buffers() -> None:
    envelope, report = export_envelope(_trained(), base_state())
    assert report["keys_match_base"] and report["shapes_match_base"] and report["dtypes_match_base"]
    assert report["all_floating_finite"] and report["integer_buffers_zero_delta"] and report["update_digest_matches_payload"]
    assert report["floating_tensors"] == 77 and report["integer_buffers"] == 15
    assert envelope["examples_seen"] == 40 > 0


def test_the_server_visible_projection_equals_the_frozen_field_mapping_and_the_client_projection() -> None:
    c = _trained()
    envelope, _ = export_envelope(c, base_state())
    projection = submission_from_envelope(envelope)
    assert projection == asyncio.run(c.produce_update())
    assert SUBMISSION_FIELD_MAP == {"client_id": "client_id", "round_id": "round_id", "base_state_digest": "base_global_state_sha256", "update_digest": "update_sha256", "examples_seen": "examples_seen"}
    assert set(projection.model_dump()) == set(SUBMISSION_FIELD_MAP)


def test_object_structure_contains_no_raw_samples_labels_truth_or_minibatches() -> None:
    envelope, _ = export_envelope(_trained(), base_state())

    def walk(obj, path=""):
        if isinstance(obj, dict):
            for k, v in obj.items():
                yield from walk(v, f"{path}/{k}")
        elif isinstance(obj, np.ndarray):
            yield path, obj
        else:
            yield path, obj
    leaves = list(walk(envelope))
    assert all(isinstance(v, str | int | bool | np.ndarray) for _p, v in leaves)
    arrays = [v for _p, v in leaves if isinstance(v, np.ndarray)]
    assert arrays and all(not (a.ndim >= 2 and a.shape[-1] == 2500) for a in arrays)  # no window-shaped array
    names = {p.split("/")[-1].lower() for p, _ in leaves}
    for forbidden in ("ecg", "ppg", "spo2", "samples", "label", "labels", "target", "truth", "simulationtruth", "minibatch", "inputs", "windows"):
        assert forbidden not in names
    assert {type(v).__name__ for _p, v in leaves} <= {"str", "int", "bool", "ndarray"}


def test_forbidden_fields_added_to_an_envelope_are_detected_and_refused_by_the_bridge() -> None:
    c = _trained()
    envelope, _ = export_envelope(c, base_state())
    for key, value in (("raw_ecg", [1, 2]), ("labels", [0, 1]), ("simulation_truth", {"t": 1}), ("minibatch", 1)):
        bad = copy.copy(envelope)
        bad[key] = value
        assert scan_forbidden(bad)
        assert validate_envelope(bad, base_state())["forbidden_findings"]
    windowed = copy.copy(envelope)
    windowed[PAYLOAD_FIELD] = {"delta": dict(envelope[PAYLOAD_FIELD]["delta"]), "x": np.zeros((4, 2500), np.float32)}
    assert scan_forbidden(windowed)


def test_a_tampered_payload_or_digest_makes_the_bridge_refuse_the_update() -> None:
    c = _trained()
    envelope = c._envelope_for_bridge()
    first = next(iter(envelope[PAYLOAD_FIELD]["delta"]))
    original = envelope[PAYLOAD_FIELD]["delta"][first].copy()
    envelope[PAYLOAD_FIELD]["delta"][first] = original + np.float32(1.0)
    try:
        assert validate_envelope(envelope, base_state())["update_digest_matches_payload"] is False
        with pytest.raises(ClientError, match="UPDATE_ENVELOPE_INVALID"):
            export_envelope(c, base_state())
    finally:
        envelope[PAYLOAD_FIELD]["delta"][first] = original
    nonfinite = envelope[PAYLOAD_FIELD]["delta"][first].copy()
    envelope[PAYLOAD_FIELD]["delta"][first] = np.full_like(nonfinite, np.nan)
    try:
        assert validate_envelope(envelope, base_state())["all_floating_finite"] is False
    finally:
        envelope[PAYLOAD_FIELD]["delta"][first] = nonfinite
    assert export_envelope(c, base_state())[1]["update_digest_matches_payload"]


def test_the_bridge_and_client_never_call_any_coordinator_or_aggregation_or_secagg_function() -> None:
    import ast
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    banned_calls = {"aggregate", "aggregate_weighted_deltas", "execute_round", "run_full", "run_part1", "run_part2", "submit", "submit_meta", "commit", "open", "Coordinator", "FederationRun"}
    for rel in ("product/federation/client.py", "product/federation/update_bridge.py", "product/federation/local_cohort.py", "product/edge/local_training_buffer.py", "product/edge/label_adapter.py"):
        tree = ast.parse((root / rel).read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                fn = node.func
                name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
                assert name not in banned_calls - {"open"}, (rel, name)
            if isinstance(node, ast.ImportFrom | ast.Import):
                text = ast.unparse(node)
                assert "secagg" not in text.lower() and "Coordinator" not in text and "aggregate" not in text, (rel, text)
