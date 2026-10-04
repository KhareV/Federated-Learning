"""V2-FL-005 pre-training tests: cohort determinism/isolation/coverage, truth isolation, label
logic, quality exclusions, normalization, envelope + router rejection codes, canonical ordering,
exactly-once commit, restart serialization, SecAgg compatibility binding and the real-data
firewall. Immutable engineering facts only."""

from __future__ import annotations

import ast
import copy
from collections import OrderedDict
from pathlib import Path

import numpy as np
import pytest
import yaml

from federated import wearable_fl_system_v1 as sysm
from federated.virtual_client_source_v1 import (
    dataset_semantic_sha,
    is_trainable,
    normalize_windows,
)
from federated.wearable_fl_secagg_shadow_v1 import derive_max_weight, load_compat
from federated.wearable_sim_local_labels import SyntheticEventLabelProvider
from nhm.hashing import hash_file
from simulation.fl_cohort_v1 import (
    ObservedRecord,
    cohort_profiles,
    iter_observed_records,
)

ROOT = Path(__file__).resolve().parents[1]
CLIENTS = [f"SIM_FL_SITE_{i:02d}" for i in range(8)]


def _imports(path: Path) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


# ---------------------------------------------------------------- cohort
def test_cohort_identity_isolation_and_seeds() -> None:
    profiles = cohort_profiles()
    assert [p.client_id for p in profiles] == CLIENTS
    assert [p.participant_id for p in profiles] == [f"SIM_P{n:06d}" for n in range(101, 109)]
    assert len({p.participant_id for p in profiles}) == 8
    assert len({p.session_id for p in profiles}) == 8
    assert [p.seed for p in profiles] == list(range(20260927, 20260935))
    assert all(len(p.events) == 10 for p in profiles)


def test_cohort_generation_is_deterministic_and_observed_only() -> None:
    profile = cohort_profiles()[1]
    first = [r.to_canonical_dict() for _, r in zip(range(2000), iter_observed_records(profile),
                                                   strict=False)]
    second = [r.to_canonical_dict() for _, r in zip(range(2000), iter_observed_records(profile),
                                                    strict=False)]
    assert first == second
    record = next(iter(iter_observed_records(profile)))
    assert isinstance(record, ObservedRecord)
    assert record.source == "SYNTHETIC_PHYSIOLOGY" and record.participant_id == "SIM_P000102"
    assert set(record.to_canonical_dict()) == set(ObservedRecord.__dataclass_fields__)


def test_fault_and_context_coverage_across_cohort() -> None:
    kinds = {f.kind for p in cohort_profiles() for f in p.faults}
    modes = {c.mode for p in cohort_profiles() for c in p.context}
    assert {"ECG_SHORT_GAP", "ECG_LONG_GAP", "ECG_SENSOR_DROPOUT", "ECG_CLIPPING"} <= kinds
    assert {"VALID", "MISSING_PPG", "INVALID_SPO2", "RATE_DISAGREEMENT"} <= modes
    assert any(len(p.faults) >= 4 for p in cohort_profiles())  # mixed fault/context session


# ---------------------------------------------------------------- truth isolation
TRUTH = {"simulation.fl_cohort_truth_v1", "simulation.truth_v2013", "simulation.types"}


def test_truth_modules_are_imported_only_by_the_client_local_label_adapter() -> None:
    allowed = {"federated/wearable_sim_local_labels.py"}
    scanned = list((ROOT / "federated").glob("*.py")) + list((ROOT / "simulation").glob("*.py")) \
        + list((ROOT / "api").glob("*.py")) + list((ROOT / "fusion").glob("*.py")) \
        + list((ROOT / "deployment").glob("*.py")) + list((ROOT / "privacy").glob("*.py"))
    for path in scanned:
        rel = path.relative_to(ROOT).as_posix()
        if "fl_cohort_truth_v1" in "".join(_imports(path)) and rel not in allowed:
            assert rel == "simulation/fl_cohort_truth_v1.py", rel
    server_side = ["federated/wearable_fl_system_v1.py", "federated/wearable_fl_runner_v1.py",
                   "federated/wearable_fl_secagg_shadow_v1.py",
                   "federated/virtual_client_source_v1.py"]
    for rel in server_side:
        imports = _imports(ROOT / rel)
        assert "simulation.fl_cohort_truth_v1" not in imports, rel
        assert "federated.wearable_sim_local_labels" not in imports or rel.endswith(
            "wearable_fl_runner_v1.py"), rel


def test_server_and_runtime_do_not_import_truth_or_generator() -> None:
    for rel in ("federated/wearable_fl_system_v1.py", "federated/wearable_fl_secagg_shadow_v1.py"):
        imports = _imports(ROOT / rel)
        assert not any(i.startswith(("simulation.fl_cohort", "simulation.profile_v2013",
                                     "simulation.wearable", "federated.wearable_sim_local_labels"))
                       for i in imports), rel
    runtime = _imports(ROOT / "simulation/stream_runtime_v2013.py")
    assert not any("truth" in i or "profile" in i or "fl_cohort" in i for i in runtime)


def test_behavioral_truth_leakage_runtime_and_router_never_touch_truth(monkeypatch) -> None:
    import simulation.fl_cohort_truth_v1 as truth

    def poisoned(*_a, **_k):
        raise AssertionError("TRUTH ACCESSED")

    monkeypatch.setattr(truth, "scheduled_event_times_us", poisoned)
    # streaming a short prefix and routing an envelope must not touch the truth module
    from simulation.stream_runtime_v2013 import WearableStreamRuntime

    runtime = WearableStreamRuntime(session_id="S", model_id="NONE", replay_id="R")
    records = [r for _, r in zip(range(360 * 16), iter_observed_records(cohort_profiles()[0]),
                                 strict=False)]
    assert runtime.ingest(records)
    state, manifest = _tiny_state(), _manifest()
    coord = sysm.Coordinator(manifest, sysm.state_spec_sha(state))
    coord.open(1, "b" * 64)
    assert coord.submit(_envelope(state, "SIM_FL_SITE_00"), state)["decision"] == "ACCEPTED"


# ---------------------------------------------------------------- label / window logic
def test_event_window_label_contract() -> None:
    profile = cohort_profiles()[0]
    provider = SyntheticEventLabelProvider(profile)
    event_us = round(profile.events[0].time_s * 1_000_000)
    others = [round(e.time_s * 1_000_000) for e in profile.events[1:]]
    edges = [event_us - 1, event_us, event_us + 10_000_000, event_us + 10_000_001]
    labels = provider.labels_for_windows(edges)
    assert labels[1] == 1.0 and labels[2] == 1.0
    for edge, label in zip(edges, labels, strict=True):
        inside = event_us <= edge <= event_us + 10_000_000 or any(
            edge - 10_000_000 <= o <= edge for o in others)
        assert label == float(inside)
    assert labels[0] == float(any(edge - 10_000_000 <= o <= edge for edge in [edges[0]]
                                  for o in others))


def test_trainable_policy_excludes_degraded_unusable_incomplete_and_nonfinite() -> None:
    base = {"ecg_quality": "VALID", "ecg": {"samples": [0.1] * 2500},
            "diagnostics": {"missing_slots": 0}}
    assert is_trainable(base)
    assert not is_trainable({**base, "ecg_quality": "DEGRADED"})
    assert not is_trainable({**base, "ecg_quality": "UNUSABLE"})
    assert not is_trainable({**base, "diagnostics": {"missing_slots": 3}})
    assert not is_trainable({**base, "ecg": {"samples": [0.1] * 2499}})
    assert not is_trainable({**base, "ecg": {"samples": [float("nan")] + [0.1] * 2499}})


def test_normalization_exact_and_dataset_hash_stable() -> None:
    rng = np.random.default_rng(0)
    windows = rng.normal(size=(5, 2500))
    out = normalize_windows(windows)
    assert out.dtype == np.float32 and out.shape == (5, 1, 2500)
    expected = (windows - windows.mean(1, keepdims=True)) / (windows.std(1, keepdims=True) + 1e-8)
    np.testing.assert_allclose(out[:, 0, :], expected.astype(np.float32), atol=1e-6)
    labels = np.array([0, 1, 0, 1, 0], dtype=np.float32)
    first = dataset_semantic_sha(out, labels, [1, 2, 3, 4, 5])
    assert first == dataset_semantic_sha(out.copy(), labels.copy(), [1, 2, 3, 4, 5])
    assert first != dataset_semantic_sha(out, 1 - labels, [1, 2, 3, 4, 5])


# ---------------------------------------------------------------- envelope / router
def _tiny_state() -> OrderedDict[str, np.ndarray]:
    return OrderedDict([("w", np.zeros((2, 3), dtype=np.float32)),
                        ("bn.running_mean", np.zeros(3, dtype=np.float32)),
                        ("bn.num_batches_tracked", np.zeros((), dtype=np.int64))])


def _manifest() -> dict[str, dict[str, str]]:
    return {c: {"participant_id": f"SIM_P{101 + i:06d}", "session_id": f"S{i}",
                "dataset_sha": f"{i:064d}"} for i, c in enumerate(CLIENTS)}


def _envelope(state, client: str, round_id: int = 1, base: str = "b" * 64,
              examples: int = 50, value: float = 0.01) -> dict:
    i = CLIENTS.index(client)
    delta = OrderedDict((k, np.full_like(v, value if np.issubdtype(v.dtype, np.floating) else 0))
                        for k, v in state.items())
    meta = _manifest()[client]
    return sysm.make_envelope(
        round_id=round_id, client_id=client, participant_id=meta["participant_id"],
        session_id=meta["session_id"], base_sha=base, dataset_sha=meta["dataset_sha"],
        spec_sha=sysm.state_spec_sha(state), examples=examples + i, delta=delta)


def _coord():
    state = _tiny_state()
    coord = sysm.Coordinator(_manifest(), sysm.state_spec_sha(state))
    coord.open(1, "b" * 64)
    return coord, state


def _code(mutator, client: str = "SIM_FL_SITE_00") -> str | None:
    coord, state = _coord()
    envelope = mutator(copy.copy(_envelope(state, client)))
    return coord.submit(envelope, state)["code"]


def test_valid_envelope_is_accepted() -> None:
    assert _code(lambda e: e) is None


@pytest.mark.parametrize(("mutator", "code"), [
    (lambda e: {**e, "raw_ecg": [1.0]}, "RAW_DATA_FIELD_PRESENT"),
    (lambda e: {**e, "labels": [1]}, "LABEL_FIELD_PRESENT"),
    (lambda e: {**e, "simulation_truth": {}}, "TRUTH_FIELD_PRESENT"),
    (lambda e: {**e, "extra": 1}, "SCHEMA_MISMATCH"),
    (lambda e: {**e, "protocol_version": "X"}, "PROTOCOL_MISMATCH"),
    (lambda e: {**e, "engineering_only": False}, "PROVENANCE_MISMATCH"),
    (lambda e: {**e, "source_dataset": "WEARABLE_V1"}, "PROVENANCE_MISMATCH"),
    (lambda e: {**e, "client_id": "SIM_FL_SITE_99"}, "UNKNOWN_CLIENT"),
    (lambda e: {**e, "participant_id": "SIM_P000999"}, "PARTICIPANT_MISMATCH"),
    (lambda e: {**e, "session_id": "OTHER"}, "SESSION_MISMATCH"),
    (lambda e: {**e, "round_id": 0}, "STALE_ROUND"),
    (lambda e: {**e, "round_id": 2}, "FUTURE_ROUND"),
    (lambda e: {**e, "base_global_state_sha256": "c" * 64}, "BASE_STATE_MISMATCH"),
    (lambda e: {**e, "client_dataset_sha256": "d" * 64}, "DATASET_SHA_MISMATCH"),
    (lambda e: {**e, "examples_seen": 0}, "NONPOSITIVE_EXAMPLES"),
    (lambda e: {**e, "examples_seen": -3}, "NONPOSITIVE_EXAMPLES"),
    (lambda e: {**e, "state_transport_id": "OTHER"}, "TRANSPORT_MISMATCH"),
    (lambda e: {**e, "state_spec_sha256": "e" * 64}, "STATE_SPEC_MISMATCH"),
    (lambda e: {**e, "payload": {"delta": {"w": np.zeros((2, 3), dtype=np.float32)}}},
     "STATE_SPEC_MISMATCH"),
    (lambda e: {**e, "update_sha256": "f" * 64}, "UPDATE_SHA_MISMATCH"),
])
def test_every_rejection_code(mutator, code) -> None:
    assert _code(mutator) == code


def test_wrong_dtype_and_nonfinite_rejected() -> None:
    coord, state = _coord()
    envelope = _envelope(state, "SIM_FL_SITE_00")
    bad = {**envelope, "payload": {"delta": OrderedDict(
        (k, v.astype(np.float64) if k == "w" else v) for k, v in envelope["payload"][
            "delta"].items())}}
    assert coord.submit(bad, state)["code"] == "DTYPE_POLICY_MISMATCH"
    coord, state = _coord()
    delta = OrderedDict(envelope["payload"]["delta"])
    delta["w"] = delta["w"].copy()
    delta["w"][0, 0] = np.nan
    assert coord.submit({**envelope, "payload": {"delta": delta}}, state)["code"] == (
        "NONFINITE_UPDATE")


def test_duplicate_and_stale_future_and_no_effect_on_state() -> None:
    coord, state = _coord()
    first = _envelope(state, "SIM_FL_SITE_00")
    assert coord.submit(first, state)["decision"] == "ACCEPTED"
    before = coord.identity()
    assert coord.submit(first, state)["code"] == "DUPLICATE_UPDATE"
    assert list(coord.accepted) == ["SIM_FL_SITE_00"] and len(coord.deltas) == 1
    assert coord.identity() != before  # the rejection is recorded, accepted set unchanged


def test_unopened_round_rejected() -> None:
    state = _tiny_state()
    coord = sysm.Coordinator(_manifest(), sysm.state_spec_sha(state))
    assert coord.submit(_envelope(state, "SIM_FL_SITE_00"), state)["code"] == "ROUND_NOT_OPEN"


def test_canonical_ordering_and_exactly_once_commit() -> None:
    state = _tiny_state()
    shas = set()
    for order in (CLIENTS, list(reversed(CLIENTS)), [CLIENTS[i] for i in (3, 0, 6, 1, 7, 4, 2, 5)]):
        coord = sysm.Coordinator(_manifest(), sysm.state_spec_sha(state))
        coord.open(1, "b" * 64)
        for client in order:
            assert coord.submit(_envelope(state, client, value=0.001 * (CLIENTS.index(client) + 1)),
                                state)["decision"] == "ACCEPTED"
        new = coord.aggregate(state)
        sha = sysm.hash_bytes(sysm.serialize_state(new))
        shas.add(sha)
        coord.commit(1, sha)
        with pytest.raises(sysm.CoordinatorError, match="ROUND_ALREADY_COMMITTED"):
            coord.commit(1, sha)
    assert len(shas) == 1


def test_no_partial_aggregation_or_commit() -> None:
    coord, state = _coord()
    coord.submit(_envelope(state, "SIM_FL_SITE_00"), state)
    with pytest.raises(sysm.CoordinatorError, match="INCOMPLETE_ROUND"):
        coord.aggregate(state)
    with pytest.raises(sysm.CoordinatorError, match="INCOMPLETE_ROUND"):
        coord.commit(1, "x")


def test_control_plane_replay_matches_live_decisions() -> None:
    coord, state = _coord()
    events = [{"type": "ROUND_OPENED", "round_id": 1, "base_global_state_sha256": "b" * 64}]
    for client in CLIENTS:
        envelope = _envelope(state, client)
        meta = sysm.extract_meta(envelope, state)
        decision = coord.submit_meta(meta)
        events.append({"type": "CLIENT_UPDATE_ACCEPTED", "update_id": decision["update_id"],
                       "decision": decision["decision"], "code": decision["code"], "meta": meta})
    dup_meta = sysm.extract_meta(_envelope(state, "SIM_FL_SITE_00"), state)
    decision = coord.submit_meta(dup_meta)
    events.append({"type": "CLIENT_UPDATE_REJECTED", "update_id": decision["update_id"],
                   "decision": decision["decision"], "code": decision["code"], "meta": dup_meta})
    events.append({"type": "ROUND_COMMITTED", "round_id": 1, "global_state_sha256": "g" * 64})
    coord.commit(1, "g" * 64)
    replay = sysm.replay_control_plane(events, _manifest(), sysm.state_spec_sha(state))
    assert replay["identity"] == coord.identity() and replay["mismatches"] == []


def test_server_boundary_scan_detects_forbidden_content() -> None:
    assert sysm.scan_forbidden({"a": {"labels": [1]}})
    assert sysm.scan_forbidden({"x": np.zeros((4, 1, 2500), dtype=np.float32)})
    assert not sysm.scan_forbidden(_envelope(_tiny_state(), "SIM_FL_SITE_00"))


# ---------------------------------------------------------------- restart serialization
def test_resume_artifact_round_trip(tmp_path: Path) -> None:
    from federated.model_v2_fl import state_sha
    from federated.wearable_fl_runner_v1 import save_resume

    state = _tiny_state()
    coord = sysm.Coordinator(_manifest(), sysm.state_spec_sha(state))
    coord.committed[1] = "a" * 64
    saved = save_resume(tmp_path, state, coord, "c" * 64)
    from federated.model_adapter import deserialize_state

    restored = deserialize_state((tmp_path / "state.bin").read_bytes())
    assert state_sha(restored) == state_sha(state)
    assert saved["state_file_sha256"]


# ---------------------------------------------------------------- SecAgg compatibility binding
def test_secagg_compat_inherits_all_but_the_declared_max_weight() -> None:
    compat = load_compat()
    base = yaml.safe_load((ROOT / "configs/model_v2/secagg_v2.yaml").read_text())
    for key in ("num_shares", "reconstruction_threshold", "clipping_range", "quantization_range",
                "modulus_range", "timeout", "correctness"):
        assert compat[key] == base[key], key
    assert compat["flower_version"] == "1.39.0" and compat["clients"] == 8
    assert base["max_weight"] == 4096.0 and compat["max_weight"] == 256.0
    assert derive_max_weight(93) == 256.0 and derive_max_weight(128) == 256.0
    assert derive_max_weight(129) == 512.0
    assert compat["rounds_with_secagg"] == [1]


def test_secagg_v2_and_historical_artifacts_unchanged() -> None:
    lock = yaml.safe_load((ROOT / "configs/model_v2/secagg_v2.yaml").read_text())
    assert lock["max_weight"] == 4096.0
    method = __import__("json").loads((ROOT / "artifacts/SECAGG_METHOD_V2.lock.json").read_text())
    for path, digest in method["bound_artifacts"].items():
        assert hash_file(ROOT / path) == digest, path


# ---------------------------------------------------------------- real-data firewall
def test_v2_fl_005_modules_never_import_real_data_loaders() -> None:
    forbidden = ("training.train_central", "preprocessing.mitdb_windows", "datasets",
                 "nhm.model_v2_partition_guard", "federated.fedavg_runner",
                 "privacy.model_v2_secagg_fixture")
    for rel in ("federated/wearable_fl_system_v1.py", "federated/wearable_fl_runner_v1.py",
                "federated/virtual_client_source_v1.py", "federated/wearable_sim_local_labels.py",
                "federated/wearable_fl_secagg_shadow_v1.py", "simulation/fl_cohort_v1.py",
                "simulation/fl_cohort_truth_v1.py", "scripts/run_v2_fl_005_system_demo.py"):
        imports = _imports(ROOT / rel)
        assert not any(i == f or i.startswith(f + ".") for i in imports for f in forbidden), rel


def test_no_metric_code_in_the_phase_modules() -> None:
    banned = ("roc_auc", "average_precision", "f1_score", "precision_recall", "sklearn.metrics")
    for rel in ("federated/wearable_fl_system_v1.py", "federated/wearable_fl_runner_v1.py",
                "federated/wearable_fl_secagg_shadow_v1.py",
                "scripts/run_v2_fl_005_system_demo.py"):
        text = (ROOT / rel).read_text()
        assert not any(b in text for b in banned), rel


def test_protocol_pins_training_semantics() -> None:
    protocol = yaml.safe_load(
        (ROOT / "configs/model_v2/v2_fl_wearable_system_protocol_v1.yaml").read_text())
    real = yaml.safe_load((ROOT / "configs/model_v2/fl_iid_model_v2_v1.yaml").read_text())
    assert protocol["local_optimizer"]["learning_rate"] == real["optimizer"]["learning_rate"]
    assert protocol["local_optimizer"]["weight_decay"] == real["optimizer"]["weight_decay"]
    assert protocol["local_optimizer"]["batch_size"] == real["training"]["batch_size"]
    assert protocol["rounds"] == 3 and protocol["clients_per_round"] == 8
    assert protocol["initialization"] == "FL_INIT_V2"
    assert protocol["access"]["TRAIN"] == "FORBIDDEN"
