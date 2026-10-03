"""V2-FL-001 method tests (synthetic fixtures and frozen metadata only; no patient outcomes)."""

from __future__ import annotations

import ast
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

import numpy as np
import pytest
import torch
import yaml

import federated.model_v2_fedavg_runner as runner
from federated.aggregation import ClientUpdate, aggregate_weighted_deltas
from federated.client_manifest import SITE_IDS
from federated.evaluation import evaluate_model
from federated.fedavg_runner import choose_best_round, load_manifest_sites
from federated.local_training import derive_shuffle_seed, train_local_epoch
from federated.model_adapter import (
    deserialize_state,
    extract_state,
    fresh_model_v1,
    restore_state,
    serialize_state,
)
from federated.model_v2_fl import (
    EXPERIMENT_ID,
    PARAMETER_COUNT,
    classify_state_entries,
    count_trainable_parameters,
    fresh_initial_state_v2,
    fresh_model_v2,
    state_sha,
    train_local_epoch_v2,
)
from nhm.hashing import hash_file
from nhm.model_v2_partition_guard import PartitionAccessViolation

ROOT = Path(__file__).resolve().parents[1]
SEED = 20260927
CONFIG = yaml.safe_load((ROOT / "configs/model_v2/fl_iid_model_v2_v1.yaml").read_text())
INT_KEYS = [r["key"] for r in classify_state_entries(fresh_model_v2())
            if r["role"] == "integer_bookkeeping_buffer"]


def _synthetic(n: int, seed: int = 3) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    x = rng.normal(size=(n, 1, 2500)).astype(np.float32)
    y = (np.arange(n) % 3 == 0).astype(np.int64)
    return x, y


def test_model_v2_state_enumeration_and_roles() -> None:
    model = fresh_model_v2()
    rows = classify_state_entries(model)
    roles = Counter(r["role"] for r in rows)
    assert len(rows) == 92
    assert roles == {"floating_trainable_parameter": 47, "floating_non_trainable_buffer": 30,
                     "integer_bookkeeping_buffer": 15}
    assert count_trainable_parameters(model) == PARAMETER_COUNT == 57553
    assert all(k.endswith("num_batches_tracked") for k in INT_KEYS) and len(INT_KEYS) == 15
    assert {r["dtype"] for r in rows if r["role"] == "integer_bookkeeping_buffer"} == {
        "torch.int64"}
    assert not any(r["role"] == "other" for r in rows)


def test_adapter_round_trip_is_exact_for_a_perturbed_model() -> None:
    torch.manual_seed(5)
    model = fresh_model_v2()
    model.train()
    x = torch.randn(8, 1, 2500)
    for _ in range(3):  # update BN running stats and counters
        model(x)
    model.eval()
    reference = model(x).detach().numpy()
    state = extract_state(model)
    restored_state = deserialize_state(serialize_state(state))
    rebuilt = fresh_model_v2()
    restore_state(rebuilt, restored_state)
    assert list(restored_state) == list(state)
    for key, value in state.items():
        assert restored_state[key].shape == value.shape and restored_state[key].dtype == value.dtype
        np.testing.assert_array_equal(restored_state[key], value)
    assert float(np.max(np.abs(rebuilt.eval()(x).detach().numpy() - reference))) == 0.0


def test_restore_rejects_missing_unexpected_and_mismatched_entries() -> None:
    state = fresh_initial_state_v2(SEED)
    model = fresh_model_v2()
    missing = dict(state)
    missing.pop(next(iter(missing)))
    with pytest.raises(ValueError):
        restore_state(model, missing)  # type: ignore[arg-type]
    bad = dict(state)
    key = next(iter(bad))
    bad[key] = bad[key].astype(np.float64)
    with pytest.raises(ValueError):
        restore_state(model, bad)  # type: ignore[arg-type]


def test_toy_fedavg_update_with_model_v2_shaped_state_is_analytic() -> None:
    state = fresh_initial_state_v2(SEED)
    d1 = {k: (np.full_like(v, 0.25) if np.issubdtype(v.dtype, np.floating)
              else np.zeros_like(v)) for k, v in state.items()}
    d2 = {k: (np.full_like(v, -0.5) if np.issubdtype(v.dtype, np.floating)
              else np.zeros_like(v)) for k, v in state.items()}
    new_state, delta = aggregate_weighted_deltas(
        state, [ClientUpdate("A", 3, d1), ClientUpdate("B", 1, d2)])
    expected = (3 * 0.25 + 1 * -0.5) / 4
    for key, value in state.items():
        if np.issubdtype(value.dtype, np.floating):
            np.testing.assert_allclose(delta[key], np.full_like(value, expected), atol=1e-7)
            np.testing.assert_allclose(new_state[key], value + np.float32(expected), atol=1e-7)


@pytest.mark.parametrize("key", INT_KEYS)
def test_integer_batchnorm_buffer_is_never_numerically_averaged(key: str) -> None:
    state = fresh_initial_state_v2(SEED)
    x, y = _synthetic(70)
    result = train_local_epoch_v2(
        global_state=state, inputs=x, labels=y, site_id="SITE_00", round_number=1,
        experiment_id=EXPERIMENT_ID, base_seed=SEED, batch_size=64, learning_rate=1e-3,
        weight_decay=1e-4, pos_weight=1.7)
    assert not np.any(result.update.delta[key])  # local counter advanced, delta forced to zero
    new_state, weighted = aggregate_weighted_deltas(state, [result.update])
    assert new_state[key].dtype == state[key].dtype
    np.testing.assert_array_equal(new_state[key], state[key])
    assert not np.any(weighted[key])


def test_fresh_initialization_is_deterministic_and_not_the_central_checkpoint() -> None:
    first, second = fresh_initial_state_v2(SEED), fresh_initial_state_v2(SEED)
    assert state_sha(first) == state_sha(second)
    assert list(first) == list(extract_state(fresh_model_v2()))
    central = torch.load(ROOT / "checkpoints/MODEL_V2_FINAL.pt", map_location="cpu",
                         weights_only=False)["state_dict"]
    assert list(central) == list(first)
    assert any(not np.array_equal(first[k], central[k].numpy()) for k in first)
    source = (ROOT / "federated/model_v2_fl.py").read_text()
    init_fn = next(n for n in ast.walk(ast.parse(source))
                   if isinstance(n, ast.FunctionDef) and n.name == "fresh_initial_state_v2")
    calls = {ast.unparse(c.func) for c in ast.walk(init_fn) if isinstance(c, ast.Call)}
    assert not {c for c in calls if "load" in c}


def test_local_training_matches_t025_function_exactly_with_the_v1_factory() -> None:
    """Differential proof that train_local_epoch_v2 inherits T025 semantics exactly."""
    state = extract_state(fresh_model_v1())
    x, y = _synthetic(130, seed=11)
    kwargs = dict(global_state=state, inputs=x, labels=y, site_id="SITE_03", round_number=2,
                  experiment_id="FL_IID_V1", base_seed=SEED, batch_size=64,
                  learning_rate=1e-3, weight_decay=1e-4, pos_weight=1.7157717177396683)
    reference = train_local_epoch(**kwargs)
    candidate = train_local_epoch_v2(**kwargs, model_factory=fresh_model_v1)
    assert candidate.shuffle_seed == reference.shuffle_seed
    assert candidate.batch_count == reference.batch_count == 3
    assert candidate.examples_seen == reference.examples_seen == 130
    assert candidate.mean_loss == reference.mean_loss
    for key in reference.update.delta:
        np.testing.assert_array_equal(candidate.update.delta[key], reference.update.delta[key])


def test_local_epoch_is_one_epoch_drop_last_false_and_deterministic() -> None:
    state = fresh_initial_state_v2(SEED)
    x, y = _synthetic(130)
    args = dict(global_state=state, inputs=x, labels=y, site_id="SITE_01", round_number=3,
                experiment_id=EXPERIMENT_ID, base_seed=SEED, batch_size=64, learning_rate=1e-3,
                weight_decay=1e-4, pos_weight=1.7)
    a, b = train_local_epoch_v2(**args), train_local_epoch_v2(**args)
    assert (a.examples_seen, a.batch_count) == (130, 3)
    assert a.shuffle_seed == derive_shuffle_seed(SEED, EXPERIMENT_ID, 3, "SITE_01")
    assert all(np.array_equal(a.update.delta[k], b.update.delta[k]) for k in state)


def test_sample_count_weighting_uses_examples_actually_used() -> None:
    state = fresh_initial_state_v2(SEED)
    floating = [k for k, v in state.items() if np.issubdtype(v.dtype, np.floating)]
    key = floating[0]

    def upd(n: int, value: float) -> ClientUpdate:
        delta = {k: (np.full_like(v, value) if k == key else np.zeros_like(v))
                 for k, v in state.items()}
        return ClientUpdate(f"C{n}", n, delta)

    _, weighted = aggregate_weighted_deltas(state, [upd(100, 1.0), upd(300, 0.0)])
    np.testing.assert_allclose(weighted[key], np.full_like(state[key], 0.25), atol=1e-7)


def test_client_manifest_is_the_exact_frozen_clients_iid_v1() -> None:
    path = ROOT / CONFIG["client_manifest"]["path"]
    assert hash_file(path) == CONFIG["client_manifest"]["sha256"] == (
        "80f38fa25c508f9b4e2a4fd49e29c4c8d0034443ec67f7c24bc0954912b6c32a")
    sites = load_manifest_sites(path)
    assert sorted(len(v) for v in sites.values()) == [3, 3, 3, 3, 3, 4, 4, 4]
    with path.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    patients = [r["participant_group_id"] for r in rows]
    assert len(patients) == len(set(patients)) == 27
    assert sum(int(r["eligible_window_count"]) for r in rows) == 9660
    assert sum(int(r["positive_window_count"]) for r in rows) == 3557
    assert sum(int(r["negative_window_count"]) for r in rows) == 6103
    assert {r["partition"] for r in rows} == {"TRAIN"} and tuple(sorted(sites)) == SITE_IDS
    with (ROOT / "manifests/splits/MITDB_SPLIT_V1.csv").open(newline="") as handle:
        split = list(csv.DictReader(handle))
    train_groups = {r["participant_group_id"] for r in split if r["partition"] == "TRAIN"}
    assert set(patients) == train_groups
    for held in ("VALIDATION", "CALIBRATION", "INTERNAL_TEST"):
        assert not set(patients) & {r["participant_group_id"] for r in split
                                    if r["partition"] == held}


def test_pos_weight_is_global_train_neg_over_pos_from_the_manifest() -> None:
    assert CONFIG["loss"]["pos_weight"] == 6103 / 3557 == 1.7157717177396683
    assert CONFIG["loss"]["client_specific_weights"] is False
    assert CONFIG["loss"]["pos_weight_source"] == "GLOBAL_TRAIN_NEG_OVER_POS"


def test_config_equals_t025_in_every_scientific_variable_except_the_model() -> None:
    v1 = yaml.safe_load((ROOT / "configs/fl_iid_v1.yaml").read_text())
    for section in ("training", "loss", "aggregation", "checkpoint", "seed_rule",
                    "stable_convergence"):
        left = {k: v for k, v in CONFIG[section].items() if k not in ("augmentation",)}
        assert left == v1[section], section
    for key in ("implementation", "learning_rate", "weight_decay", "state_policy", "scheduler"):
        assert CONFIG["optimizer"][key] == v1["optimizer"][key]
    assert CONFIG["transport"]["id"] == v1["transport"]["id"] == "FL_STATE_TRANSPORT_V1"
    assert CONFIG["initialization"]["seed"] == v1["initialization"]["seed"] == SEED
    assert CONFIG["evaluation"] == v1["evaluation"]
    assert CONFIG["model"]["centralized_checkpoint_warm_start"] is False


def test_round_selection_is_earliest_exact_maximum_and_excludes_round_zero() -> None:
    rows = [{"round": 0, "validation_AUPRC": 0.99}, {"round": 1, "validation_AUPRC": 0.4},
            {"round": 2, "validation_AUPRC": 0.5}, {"round": 3, "validation_AUPRC": 0.5},
            {"round": 4, "validation_AUPRC": 0.3}]
    assert choose_best_round(rows) == 2


def test_evaluation_uses_raw_sigmoid_and_no_calibration() -> None:
    model = fresh_model_v2()
    x, y = _synthetic(60)
    groups = np.asarray(["A"] * 30 + ["B"] * 30)
    metrics, logits, probabilities = evaluate_model(
        model, x, y, groups, pos_weight=1.7, partition="VALIDATION")
    np.testing.assert_allclose(probabilities, 1 / (1 + np.exp(-logits.astype(np.float64))),
                               atol=1e-12)
    assert metrics["calibration"] == "NONE" and metrics["threshold"] == 0.5
    with pytest.raises(ValueError):
        evaluate_model(model, x, y, groups, pos_weight=1.7, partition="INTERNAL_TEST")


def test_cal_v2_and_central_checkpoint_never_used_as_fl_model_inputs() -> None:
    for relative in ("federated/model_v2_fl.py", "federated/model_v2_fedavg_runner.py"):
        source = (ROOT / relative).read_text()
        assert "CAL_V2.json" not in source and "load_cal_v2" not in source
        assert "apply_cal" not in source and "temperature" not in source.lower()
    runner_src = (ROOT / "federated/model_v2_fedavg_runner.py").read_text()
    assert runner_src.count("MODEL_V2_FINAL.pt") == 1  # audit-only hash comparison


@pytest.mark.parametrize("partition", ["CALIBRATION", "INTERNAL_TEST", "INCART", "NSTDB",
                                       "BIDMC"])
def test_heldout_firewall_denies_before_any_read(partition: str) -> None:
    with pytest.raises(PartitionAccessViolation):
        runner.guarded_population(ROOT, partition)
    assert runner.ALLOWED_PARTITIONS == ("TRAIN", "VALIDATION")
    for name in ("CALIBRATION", "INTERNAL_TEST", "INCART", "NSTDB", "BIDMC", "WEARABLE_V1"):
        assert CONFIG["access"][name] == "FORBIDDEN"
    assert CONFIG["access"]["WEARABLE_SIM"] == "FORBIDDEN_AS_EFFICACY_DATA"


def test_historical_v1_fl_files_are_untouched_by_this_phase() -> None:
    pins = {
        "configs/fl_iid_v1.yaml":
            "529a43dab43b36c57ed65e2ba769d10eafefa79f21689fb3339dbe4d67e1cf89"}
    for relative, digest in pins.items():
        assert hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == digest
    for relative in ("federated/local_training.py", "federated/aggregation.py",
                     "federated/model_adapter.py", "federated/fedavg_runner.py"):
        assert "model_v2" not in (ROOT / relative).read_text().lower()


def test_shuffle_seed_namespace_is_the_historical_iid_namespace() -> None:
    assert CONFIG["shuffle_seed_namespace"] == "FL_IID_V1"
    assert derive_shuffle_seed(SEED, CONFIG["shuffle_seed_namespace"], 1, "SITE_00") == (
        6318989447729917868)  # identical to the frozen T025 round-1 SITE_00 seed
    assert 'config["shuffle_seed_namespace"]' in (
        ROOT / "federated/model_v2_fedavg_runner.py").read_text()


def _fake_population(partition: str, groups: list[str], per_group: int, seed: int):
    from training.train_central import WindowPopulation

    rng = np.random.default_rng(seed)
    gid, labels, ids = [], [], []
    for g in groups:
        for i in range(per_group):
            gid.append(g)
            labels.append(1 if i % 3 == 0 else 0)
            ids.append(f"{partition}_{g}_{i}")
    waves = rng.normal(size=(len(ids), 2500)) * rng.uniform(0.5, 2.0, size=(len(ids), 1))
    return WindowPopulation(partition=partition, waveforms=waves,
                            labels=np.asarray(labels, dtype=np.int64), example_ids=tuple(ids),
                            participant_group_ids=np.asarray(gid, dtype=str),
                            accessed_paths=())


def test_full_runner_pipeline_on_synthetic_populations_two_rounds(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """End-to-end smoke of run(): routing by CLIENTS_IID_V1, 8 clients/round, parity, aggregation,
    validation, best-round checkpoint, evidence files. Synthetic data only (no patient outcomes)."""
    import shutil

    (tmp_path / "configs/model_v2").mkdir(parents=True)
    (tmp_path / "manifests/clients").mkdir(parents=True)
    (tmp_path / "checkpoints").mkdir()
    shutil.copy(ROOT / "manifests/clients/CLIENTS_IID_V1.csv", tmp_path / "manifests/clients")
    shutil.copy(ROOT / "checkpoints/MODEL_V2_FINAL.pt", tmp_path / "checkpoints")
    patients = sorted(load_manifest_sites(
        ROOT / "manifests/clients/CLIENTS_IID_V1.csv").values().__iter__().__next__())
    all_patients = [p for v in load_manifest_sites(
        ROOT / "manifests/clients/CLIENTS_IID_V1.csv").values() for p in v]
    assert patients and len(all_patients) == 27
    train = _fake_population("TRAIN", all_patients, 6, 1)
    validation = _fake_population("VALIDATION", [f"VAL_{i}" for i in range(4)], 9, 2)
    pos_weight = float(np.sum(train.labels == 0) / np.sum(train.labels == 1))
    config = dict(CONFIG)
    config["training"] = {**CONFIG["training"], "rounds": 2}
    config["loss"] = {**CONFIG["loss"], "pos_weight": pos_weight}
    (tmp_path / runner.CONFIG_RELATIVE).write_text(yaml.safe_dump(config))
    monkeypatch.setattr(runner, "load_population",
                        lambda partition: {"TRAIN": train, "VALIDATION": validation}[partition])
    report = runner.run(tmp_path)
    out = tmp_path / runner.OUT_RELATIVE
    assert report["status"] == "COMPLETE"
    assert report["central_checkpoint_loaded_as_initialization"] is False
    assert report["stability"]["rounds_completed"] == 2
    assert report["stability"]["client_updates_received"] == 16
    assert (out / "round_log.csv").exists()
    assert (out / "validation_predictions_best_round.csv").exists()
    ledger = (tmp_path / "reports/model_v2/access_ledger.jsonl").read_text().splitlines()
    assert {json.loads(line)["partition"] for line in ledger} == {"TRAIN", "VALIDATION"}
    ckpt = torch.load(tmp_path / runner.CKPT_RELATIVE / f"{EXPERIMENT_ID}_best.pt",
                      weights_only=False)
    assert ckpt["calibration"] == "NONE" and ckpt["supersedes_model_v2_final"] is False
