"""V2-FL-003 method tests: FedProx objective/scope, exact mu=0 equivalence, candidate set,
guardrail arithmetic, selection rule (differential against the historical selector), matched
configuration, firewall/NSTDB role, runner smoke and chronology guards. Synthetic fixtures and
frozen metadata only."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import numpy as np
import pytest
import torch
import yaml
from torch import nn

import federated.model_v2_fedprox_runner as runner
from federated.fedprox_selection import select_mu as historical_select
from federated.model_adapter import restore_state
from federated.model_v2_fedprox import (
    CANDIDATES,
    GUARDRAIL_DEGRADATION,
    MACRO_ID,
    WORST_ID,
    local_objective,
    proximal_penalty,
    select_mu,
    train_local_fedprox_epoch_v2,
)
from federated.model_v2_fl import fresh_initial_state_v2, fresh_model_v2, train_local_epoch_v2
from nhm.hashing import hash_file
from nhm.model_v2_partition_guard import PartitionAccessViolation

ROOT = Path(__file__).resolve().parents[1]
CONFIG = yaml.safe_load((ROOT / "configs/model_v2/fedprox_v2.yaml").read_text())
FL002 = yaml.safe_load((ROOT / "configs/model_v2/fl_non_iid_model_v2_v1.yaml").read_text())
SEED = 20260927
BASELINE_WORST = 0.03809523809523809


def _rows(macros, worsts, globals_):
    return [{"mu": mu, MACRO_ID: m, WORST_ID: w, "best_global_validation_AUPRC": g}
            for mu, m, w, g in zip(CANDIDATES, macros, worsts, globals_, strict=True)]


def test_penalty_scope_trainable_only_and_round_start_reference() -> None:
    model = fresh_model_v2()
    reference = {n: p.detach().clone() for n, p in model.named_parameters()}
    assert float(proximal_penalty(model, reference)) == 0.0
    with torch.no_grad():
        for p in model.parameters():
            p.add_(0.01)
    expected = 0.5 * sum(float(torch.sum((p - reference[n]) ** 2))
                         for n, p in model.named_parameters())
    assert float(proximal_penalty(model, reference)) == pytest.approx(expected, rel=1e-6)
    before = float(proximal_penalty(model, reference))
    with torch.no_grad():  # buffers (BatchNorm stats and counters) must not affect the penalty
        for _name, buffer in model.named_buffers():
            if buffer.is_floating_point():
                buffer.add_(5.0)
            else:
                buffer.add_(3)
    assert float(proximal_penalty(model, reference)) == before
    assert len(reference) == 47  # trainable parameters only (no buffers)


def test_mu_validation_and_objective_form() -> None:
    model = fresh_model_v2()
    reference = {n: p.detach().clone() for n, p in model.named_parameters()}
    base = torch.tensor(0.7)
    for bad in (-0.1, float("inf"), float("nan")):
        with pytest.raises(ValueError):
            local_objective(base, model, reference, bad)
    with torch.no_grad():
        for p in model.parameters():
            p.add_(0.02)
    penalty = proximal_penalty(model, reference)  # = 1/2 ||w - w_global||^2
    assert float(local_objective(base, model, reference, 0.1)) == pytest.approx(
        0.7 + 0.1 * float(penalty), rel=1e-6)


def test_mu_zero_loss_and_gradient_are_exactly_fedavg() -> None:
    state = fresh_initial_state_v2(SEED)
    rng = np.random.default_rng(1)
    x = torch.from_numpy(rng.normal(size=(32, 1, 2500)).astype(np.float32))
    y = torch.from_numpy((np.arange(32) % 3 == 0).astype(np.float32)).unsqueeze(1)
    criterion = nn.BCEWithLogitsLoss(pos_weight=torch.tensor([1.7157717177396683]))
    grads, losses = [], []
    for mu in (None, 0.0):
        model = fresh_model_v2()
        restore_state(model, state)
        model.train()
        reference = {n: p.detach().clone() for n, p in model.named_parameters()}
        torch.manual_seed(2)
        base = criterion(model(x), y)
        loss = base if mu is None else local_objective(base, model, reference, mu)
        loss.backward()
        losses.append(float(loss))
        grads.append({n: p.grad.clone() for n, p in model.named_parameters()})
    assert losses[0] == losses[1]
    assert all(torch.equal(grads[0][n], grads[1][n]) for n in grads[0])


def test_mu_zero_local_update_is_bit_identical_to_v2_fedavg() -> None:
    state = fresh_initial_state_v2(SEED)
    rng = np.random.default_rng(3)
    x = rng.normal(size=(130, 1, 2500)).astype(np.float32)
    y = (np.arange(130) % 3 == 0).astype(np.int64)
    kwargs = {"global_state": state, "inputs": x, "labels": y, "site_id": "SITE_02",
              "round_number": 1, "experiment_id": "FL_IID_V1", "base_seed": SEED,
              "batch_size": 64, "learning_rate": 1e-3, "weight_decay": 1e-4, "pos_weight": 1.7}
    avg = train_local_epoch_v2(**kwargs)
    prox = train_local_fedprox_epoch_v2(**kwargs, mu=0.0)
    assert (avg.examples_seen, avg.batch_count, avg.shuffle_seed) == (
        prox.examples_seen, prox.batch_count, prox.shuffle_seed)
    assert avg.mean_loss == prox.mean_loss
    for key in state:
        assert np.array_equal(avg.update.delta[key], prox.update.delta[key])


def test_positive_mu_changes_the_update_and_keeps_integer_buffers_untouched() -> None:
    state = fresh_initial_state_v2(SEED)
    rng = np.random.default_rng(4)
    x = rng.normal(size=(70, 1, 2500)).astype(np.float32)
    y = (np.arange(70) % 3 == 0).astype(np.int64)
    kwargs = {"global_state": state, "inputs": x, "labels": y, "site_id": "SITE_00",
              "round_number": 1, "experiment_id": "FL_IID_V1", "base_seed": SEED,
              "batch_size": 64, "learning_rate": 1e-3, "weight_decay": 1e-4, "pos_weight": 1.7}
    zero = train_local_fedprox_epoch_v2(**kwargs, mu=0.0)
    big = train_local_fedprox_epoch_v2(**kwargs, mu=0.1)
    floating = [k for k, v in state.items() if np.issubdtype(v.dtype, np.floating)]
    assert any(not np.array_equal(zero.update.delta[k], big.update.delta[k]) for k in floating)
    for key, value in state.items():
        if not np.issubdtype(value.dtype, np.floating):
            assert not np.any(big.update.delta[key])  # num_batches_tracked policy unchanged


def test_candidate_set_order_and_config() -> None:
    assert CANDIDATES == (0.001, 0.01, 0.1) == tuple(CONFIG["mu_candidates"])
    assert 0.0 not in CANDIDATES and CONFIG["mu_zero_role"].startswith("IMPLEMENTATION")
    assert CONFIG["tuning_condition"] == "label"
    with pytest.raises(ValueError):
        select_mu(_rows([0.5] * 3, [0.1] * 3, [0.6] * 3)[::-1], BASELINE_WORST)


def test_guardrail_arithmetic_and_nonbinding_disclosure() -> None:
    threshold = BASELINE_WORST - GUARDRAIL_DEGRADATION
    assert threshold == pytest.approx(-0.01190476190476191, abs=1e-15)
    assert CONFIG["guardrail"]["threshold"] == pytest.approx(threshold, abs=1e-15)
    assert "never exclude" in CONFIG["guardrail"]["nonbinding_disclosure"]
    result = select_mu(_rows([0.7, 0.8, 0.6], [0.0, 0.0, 0.0], [0.8, 0.8, 0.8]), BASELINE_WORST)
    assert all(c["guardrail_pass"] for c in result["evaluated_candidates"])  # even worst == 0
    assert result["guardrail_nonbinding_because"]


def test_selection_is_macro_primary_with_the_tie_hierarchy() -> None:
    assert select_mu(_rows([0.70, 0.80, 0.75], [0.1, 0.1, 0.9], [0.9, 0.5, 0.5]),
                     BASELINE_WORST)["selected_mu"] == 0.01  # macro beats worst/global
    assert select_mu(_rows([0.8, 0.8, 0.7], [0.2, 0.3, 0.9], [0.5, 0.5, 0.5]),
                     BASELINE_WORST)["selected_mu"] == 0.01  # tie -> higher worst
    assert select_mu(_rows([0.8, 0.8, 0.7], [0.3, 0.3, 0.9], [0.5, 0.6, 0.5]),
                     BASELINE_WORST)["selected_mu"] == 0.01  # tie -> higher pooled
    assert select_mu(_rows([0.8, 0.8, 0.7], [0.3, 0.3, 0.9], [0.6, 0.6, 0.5]),
                     BASELINE_WORST)["selected_mu"] == 0.001  # tie -> smaller mu
    assert select_mu(_rows([0.8 + 1e-14, 0.8, 0.7], [0.3, 0.9, 0.9], [0.5, 0.5, 0.5]),
                     BASELINE_WORST)["selected_mu"] == 0.01  # 12-decimal macro comparison
    rows = _rows([0.7, 0.8, 0.75], [0.1, 0.2, 0.3], [0.9, 0.5, 0.6])
    assert select_mu(rows, BASELINE_WORST) == select_mu(rows, BASELINE_WORST)


def test_selection_matches_the_historical_selector_on_identical_inputs() -> None:
    for macros, worsts, globals_ in (([0.7, 0.8, 0.75], [0.1, 0.2, 0.3], [0.9, 0.5, 0.6]),
                                     ([0.8, 0.8, 0.7], [0.3, 0.3, 0.9], [0.6, 0.6, 0.5])):
        new = select_mu(_rows(macros, worsts, globals_), BASELINE_WORST)
        old_rows = [{"mu": mu, "validation_patient_macro_AUPRC": m,
                     "validation_patient_worst_AUPRC": w, "best_global_validation_AUPRC": g}
                    for mu, m, w, g in zip(CANDIDATES, macros, worsts, globals_, strict=True)]
        old = historical_select(old_rows, BASELINE_WORST)
        assert new["selected_mu"] == old["selected_mu"] and new["ranking"] == old["ranking"]


def test_matched_budget_manifests_init_and_noise_references() -> None:
    for section in ("training", "optimizer", "aggregation", "transport"):
        assert CONFIG[section] == FL002[section], section
    for key in ("metric", "eligible_rounds", "tie_policy"):
        assert CONFIG["checkpoint"][key] == FL002["checkpoint"][key], key
    assert CONFIG["loss"]["base"] == FL002["loss"]["implementation"] == "BCEWithLogitsLoss"
    for key in ("pos_weight", "pos_weight_source", "client_specific_weights"):
        assert CONFIG["loss"][key] == FL002["loss"][key], key
    assert CONFIG["shuffle_seed_namespace"] == FL002["shuffle_seed_namespace"] == "FL_IID_V1"
    assert CONFIG["initialization"]["round_0_state_sha256"] == FL002["initialization"][
        "round_0_state_sha256"]
    for key, ref in CONFIG["conditions"].items():
        assert hash_file(ROOT / "manifests/clients" / ref["path"]) == ref["sha256"], key
    assert CONFIG["transfer_order"] == ["iid", "quantity", "feature", "combined"]
    assert CONFIG["feature_noise"]["nstdb_role"] == "NSTDB_PURE_NOISE_TRAINING_RESOURCE"
    assert CONFIG["evaluation"]["calibration"] == "NONE"
    assert CONFIG["access"]["INTERNAL_TEST"].startswith("FORBIDDEN")
    assert CONFIG["expected_accounting"] == {
        "candidate_rounds": 150, "candidate_updates": 1200, "transfer_rounds": 200,
        "transfer_updates": 1600, "total_positive_mu_updates": 2800}


def test_label_baseline_references_match_committed_v2_fl_002() -> None:
    baseline = CONFIG["label_fedavg_baseline"]
    result = json.loads((ROOT / baseline["result"]).read_text())
    patient = json.loads((ROOT / "reports/model_v2/v2_fl_002/"
                          "label_validation_patient_metrics.json").read_text())
    assert result["best_validation"]["AUPRC"] == baseline["best_validation_AUPRC"]
    assert patient["VALIDATION_PATIENT_MACRO_AUPRC_V2"] == baseline[MACRO_ID]
    assert patient["VALIDATION_PATIENT_WORST_AUPRC_V2"] == baseline[WORST_ID]
    assert result["best_checkpoint_sha256"] == baseline["best_checkpoint_sha256"]


def test_cal_v2_and_internal_test_never_inputs() -> None:
    for relative in ("federated/model_v2_fedprox.py", "federated/model_v2_fedprox_runner.py"):
        source = (ROOT / relative).read_text()
        assert "CAL_V2.json" not in source and "temperature" not in source
        assert "INTERNAL_TEST" not in source.replace("check_partition_allowed", "")
        assert "MODEL_V2_FINAL.pt" not in source
    for partition in ("CALIBRATION", "INTERNAL_TEST", "INCART", "BIDMC"):
        with pytest.raises(PartitionAccessViolation):
            runner.guarded_population(ROOT, partition, "x")


def test_historical_v1_fedprox_files_are_untouched() -> None:
    for relative in ("federated/fedprox_training.py", "federated/fedprox_runner.py",
                     "federated/fedprox_selection.py"):
        assert "model_v2" not in (ROOT / relative).read_text().lower()
    lock = json.loads((ROOT / "artifacts/FEDPROX_MU_V1.lock.json").read_text())
    assert lock["selected_mu"] == 0.01 and lock["lock_id"] == "FEDPROX_MU_V1"
    assert hashlib.sha256((ROOT / "configs/fedprox_v1.yaml").read_bytes()).hexdigest()


def test_protocol_v2_is_additive_and_roadmap_inserts_eval_phase() -> None:
    protocol = yaml.safe_load((ROOT / "configs/model_v2/fl_protocol_v2.yaml").read_text())
    assert protocol["change"]["new_roadmap"] == [
        "V2-FL-003", "V2-FL-EVAL-001", "V2-FL-004", "V2-FL-005", "V2-014"]
    lock = json.loads((ROOT / "manifests/model_v2/MODEL_V2_FL_PROTOCOL_V2.lock.json").read_text())
    v1 = ROOT / "manifests/model_v2/MODEL_V2_FL_PROTOCOL_V1.lock.json"
    assert hash_file(v1) == lock["predecessor_sha256"]
    assert lock["created_before_any_fedprox_outcome"]
    import csv

    with (ROOT / "manifests/model_v2/task_registry_v1.csv").open(newline="") as handle:
        tasks = {r["task_id"]: r for r in csv.DictReader(handle)}
    with (ROOT / "manifests/model_v2/gate_registry_v1.csv").open(newline="") as handle:
        gates = {r["gate_id"]: r for r in csv.DictReader(handle)}
    assert tasks["V2-FL-EVAL-001"]["prerequisites"] == "V2-FL-003"
    assert tasks["V2-FL-004"]["prerequisites"] == "V2-FL-EVAL-001"
    assert gates["V2FLG2"]["blocks_tasks"] == "V2-FL-EVAL-001"
    assert "does not require FedProx improvement" in gates["V2FLG2"]["purpose"]
    assert tasks["V2-FL-EVAL-001"]["status"] in {"NOT_STARTED", "PASS"}  # forward lifecycle


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
                            participant_group_ids=np.asarray(gid, dtype=str), accessed_paths=())


@pytest.mark.parametrize(("condition", "role", "mu"), [("label", "candidate", 0.1),
                                                       ("feature", "transfer", 0.01)])
def test_runner_smoke_two_rounds(condition: str, role: str, mu: float, tmp_path: Path,
                                 monkeypatch: pytest.MonkeyPatch) -> None:
    import csv

    (tmp_path / "configs/model_v2").mkdir(parents=True)
    (tmp_path / "manifests/clients").mkdir(parents=True)
    path = ROOT / "manifests/clients" / CONFIG["conditions"][condition]["path"]
    shutil.copy(path, tmp_path / "manifests/clients")
    with path.open(newline="") as handle:
        patients = [r["participant_group_id"] for r in csv.DictReader(handle)]
    train = _fake_population("TRAIN", patients, 6, 1)
    validation = _fake_population("VALIDATION", [f"VAL_{i}" for i in range(3)], 9, 2)
    config = yaml.safe_load((ROOT / runner.CONFIG_RELATIVE).read_text())
    config["training"]["rounds"] = 2
    config["loss"]["pos_weight"] = float(np.sum(train.labels == 0) / np.sum(train.labels == 1))
    probe = fresh_model_v2()
    restore_state(probe, fresh_initial_state_v2(SEED))
    from federated.evaluation import evaluate_model
    from federated.fedavg_runner import normalized_population

    metrics0, _, _ = evaluate_model(probe, normalized_population(validation), validation.labels,
                                    validation.participant_group_ids, pos_weight=1.7,
                                    partition="VALIDATION")
    config["initialization"]["round_0_validation_AUPRC"] = metrics0["AUPRC"]
    (tmp_path / runner.CONFIG_RELATIVE).write_text(yaml.safe_dump(config))
    monkeypatch.setattr(runner, "load_population",
                        lambda p: {"TRAIN": train, "VALIDATION": validation}[p])
    monkeypatch.setattr(runner, "build_noise_bank", lambda root: (
        {k: np.random.default_rng(7).normal(size=6000) for k in ("bw", "em", "ma")}, {}))
    seen = {}
    original = runner.evaluate_model

    def spy(model, inputs, labels, groups, **kwargs):  # type: ignore[no-untyped-def]
        if kwargs["partition"] == "VALIDATION":
            seen["val"] = np.array(inputs)
        return original(model, inputs, labels, groups, **kwargs)

    monkeypatch.setattr(runner, "evaluate_model", spy)
    report = runner.run_fedprox(tmp_path, condition, mu, role)
    assert report["status"] == "COMPLETE" and report["mu"] == mu
    assert report["round_0_state_sha256"] == CONFIG["initialization"]["round_0_state_sha256"]
    assert report["stability"]["client_updates_received"] == 16
    _, sub, _ = runner.run_key(condition, mu, role)
    out = tmp_path / runner.OUT_RELATIVE / sub
    assert all((out / n).exists() for n in ("round_log.csv", "client_rounds.csv", "result.json",
                                            "validation_predictions.csv"))
    np.testing.assert_array_equal(seen["val"], normalized_population(validation))  # clean
    ledger = [json.loads(x) for x in (tmp_path / "reports/model_v2/access_ledger.jsonl"
                                      ).read_text().splitlines()]
    assert {r["partition"] for r in ledger} <= {"TRAIN", "VALIDATION", "NSTDB"}
    assert all(r["access_type"] == runner.NSTDB_ROLE for r in ledger if r["partition"] == "NSTDB")


def test_run_script_guards_transfer_until_mu_frozen_and_committed() -> None:
    source = (ROOT / "scripts/run_v2_fl_003.py").read_text()
    assert "V2_FL_003_MU_NOT_FROZEN_AND_COMMITTED_BEFORE_TRANSFER" in source
    assert "V2_FL_003_MU_NOT_IN_PREDECLARED_SET" in source
    assert "V2_FL_003_MU0_EQUIVALENCE_NOT_PASS" in source
    assert "label reuses the selected candidate" in source
