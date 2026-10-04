#!/usr/bin/env python3
"""V2-FL-003 method freeze + preflight (before any positive-mu outcome). Verifies the committed
V2-FL-002 development family, proves MODEL_V2 FedProx at mu=0 collapses EXACTLY to FedAvg at three
levels (objective/gradient, all eight LABEL clients' round-1 updates, full round-1 aggregate vs the
stored V2-FL-002 LABEL round-1 state SHA), records the guardrail arithmetic, and writes the
MODEL_V2_FL_PROTOCOL_V2 lock and method_freeze.json. Reads only MIT-BIH TRAIN (allowed)."""

from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import torch
import yaml
from torch import nn

from federated.aggregation import aggregate_weighted_deltas
from federated.client_manifest import SITE_IDS
from federated.fedavg_runner import normalized_population
from federated.model_adapter import restore_state
from federated.model_v2_fedprox import (
    CANDIDATES,
    GUARDRAIL_DEGRADATION,
    local_objective,
    proximal_penalty,
    train_local_fedprox_epoch_v2,
)
from federated.model_v2_fedprox_runner import CONFIG_RELATIVE, guarded_population
from federated.model_v2_fl import (
    fresh_initial_state_v2,
    fresh_model_v2,
    set_determinism,
    state_sha,
    train_local_epoch_v2,
)
from federated.model_v2_non_iid_runner import verify_entry as verify_v2_fl_001_entry
from federated.non_iid_runner import load_sites
from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/model_v2/v2_fl_003"
CONFIG = yaml.safe_load((ROOT / CONFIG_RELATIVE).read_text())
V2FL002 = ROOT / "reports/model_v2/v2_fl_002"
METHOD_FILES = [
    CONFIG_RELATIVE, "configs/model_v2/fl_protocol_v2.yaml", "federated/model_v2_fedprox.py",
    "federated/model_v2_fedprox_runner.py", "scripts/freeze_v2_fl_003_method.py",
    "scripts/run_v2_fl_003.py", "scripts/select_v2_fedprox_mu.py",
    "scripts/verify_v2_fl_003_replay.py", "scripts/finalize_v2_fl_003_evidence.py",
    "tests/test_v2_fl_003_method.py",
    "federated/model_v2_fl.py", "federated/model_v2_non_iid_runner.py",
    "federated/aggregation.py", "federated/model_adapter.py", "federated/local_training.py",
    "federated/evaluation.py", "federated/fedavg_runner.py", "federated/feature_noise.py",
    "federated/non_iid_runner.py", "federated/client_manifest.py",
    "models/model_v2_architectures.py", "evaluation/bootstrap.py",
    "configs/model_v2/fl_protocol_v1.yaml", "configs/model_v2/fl_init_v2.yaml",
    "configs/model_v2/fl_iid_model_v2_v1.yaml", "configs/model_v2/fl_non_iid_model_v2_v1.yaml",
    "manifests/model_v2/MODEL_V2_FL_PROTOCOL_V1.lock.json",
    "manifests/model_v2/FL_NON_IID_MODEL_V2_V1.lock.json",
    "configs/fl_feature_noise_v1.yaml", "configs/fedprox_selection_semantics_v1.yaml",
    "manifests/clients/CLIENTS_IID_V1.csv", "manifests/clients/NONIID_LABEL_V1.csv",
    "manifests/clients/NONIID_QUANTITY_V1.csv", "manifests/clients/NONIID_FEATURE_V1.csv",
    "manifests/clients/NONIID_COMBINED_V1.csv", "artifacts/FL_CONFIG_V1.lock.json",
]
PROTECTED = [
    "checkpoints/MODEL_V1.pt", "artifacts/CAL_V1.json", "artifacts/GATEWAY_ARTIFACT_V1.lock.json",
    "manifests/preprocessing/PREPROC_V1.lock.json", "configs/quality_v1.yaml",
    "preprocessing/quality.py", "checkpoints/MODEL_V2_FINAL.pt", "artifacts/CAL_V2.json",
    "artifacts/deployment/MODEL_V2_GATEWAY_FP32.ts",
    "artifacts/deployment/GATEWAY_ARTIFACT_V2.manifest.json",
    "artifacts/API_RUNTIME_V2.lock.json", "artifacts/API_RUNTIME_V2_1.lock.json",
    "artifacts/FL_IID_V1.lock.json", "artifacts/FEDPROX_METHOD_V1.lock.json",
    "artifacts/FEDPROX_MU_V1.lock.json", "artifacts/SECAGG_CONFIG_V1.lock.json",
    "reports/t027/mu_selection.json", "configs/fedprox_v1.yaml",
    "federated/fedprox_training.py", "federated/fedprox_runner.py",
    "federated/fedprox_selection.py", "reports/t026/artifact_hashes.json",
    "reports/model_v2/v2_fl_001/artifact_hashes.json",
    "reports/model_v2/v2_fl_002/artifact_hashes.json",
    "manifests/model_v2/MODEL_V2_FL_PROTOCOL_V1.lock.json",
    "manifests/model_v2/FL_NON_IID_MODEL_V2_V1.lock.json",
    *[f"checkpoints/model_v2/v2_fl_002/{n}" for n in sorted(
        p.name for p in (ROOT / "checkpoints/model_v2/v2_fl_002").glob("*.pt"))],
    *[f"checkpoints/model_v2/v2_fl_001/{n}" for n in sorted(
        p.name for p in (ROOT / "checkpoints/model_v2/v2_fl_001").glob("*.pt"))],
    "manifests/splits/MITDB_SPLIT_V1.csv", "manifests/labels/AAMI_SVF_MAP_V1.yaml",
    "reports/model_v2/v2_013/artifact_hashes.json",
    "reports/model_v2/c_v2_013_quality_flatline/artifact_hashes.json",
]


def _write(name: str, data: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def verify_v2_fl_002() -> dict:
    problems = []
    baseline = CONFIG["label_fedavg_baseline"]
    label = json.loads((V2FL002 / "label_result.json").read_text())
    patient = json.loads((V2FL002 / "label_validation_patient_metrics.json").read_text())
    checks = {
        "label_best_round": label["best_round"] == baseline["best_round"],
        "label_best_auprc": label["best_validation"]["AUPRC"] == baseline[
            "best_validation_AUPRC"],
        "label_ckpt": label["best_checkpoint_sha256"] == baseline["best_checkpoint_sha256"],
        "macro": patient["VALIDATION_PATIENT_MACRO_AUPRC_V2"] == baseline[
            "VALIDATION_PATIENT_MACRO_AUPRC_V2"],
        "worst": patient["VALIDATION_PATIENT_WORST_AUPRC_V2"] == baseline[
            "VALIDATION_PATIENT_WORST_AUPRC_V2"]}
    problems += [k for k, ok in checks.items() if not ok]
    for name in ("label", "quantity", "feature", "combined"):
        result = json.loads((V2FL002 / f"{name}_result.json").read_text())
        for key in ("best_checkpoint", "round_50_checkpoint"):
            if hash_file(ROOT / result[key]) != result[f"{key}_sha256"]:
                problems.append(f"{name}:{key}")
    for run in ("run_1", "run_2"):
        if json.loads((V2FL002 / f"replay_verification_{run}.json").read_text())[
                "status"] != "PASS":
            problems.append(f"replay_{run}")
    freeze = json.loads((V2FL002 / "method_freeze.json").read_text())
    problems += [f"v2_fl_002_method:{p}" for p, d in freeze["method_file_sha256"].items()
                 if hash_file(ROOT / p) != d]
    for key, ref in CONFIG["conditions"].items():
        if hash_file(ROOT / "manifests/clients" / ref["path"]) != ref["sha256"]:
            problems.append(f"manifest:{key}")
    rounds = list(csv.DictReader((V2FL002 / "label_round_log.csv").open(newline="")))
    if rounds[1]["global_state_sha256"] != baseline["round_1_state_sha256"]:
        problems.append("label_round1_sha")
    first = verify_v2_fl_001_entry(ROOT)
    problems += [f"v2_fl_001:{p}" for p in first["problems"]]
    return {"problems": problems, "status": "PASS" if not problems else "FAIL"}


def mu0_equivalence() -> dict:
    # A. objective / gradient on deterministic synthetic input.
    set_determinism(20260927)
    state = fresh_initial_state_v2(20260927)
    rng = np.random.default_rng(5)
    x = torch.from_numpy(rng.normal(size=(64, 1, 2500)).astype(np.float32))
    y = torch.from_numpy((np.arange(64) % 3 == 0).astype(np.float32)).unsqueeze(1)
    criterion = nn.BCEWithLogitsLoss(pos_weight=torch.tensor([1.7157717177396683]))

    def losses_and_grads(mu: float):
        model = fresh_model_v2()
        restore_state(model, state)
        model.train()
        reference = {n: p.detach().clone() for n, p in model.named_parameters()}
        torch.manual_seed(1)
        base = criterion(model(x), y)
        objective = local_objective(base, model, reference, mu)
        objective.backward()
        return float(base.item()), float(objective.item()), {
            n: p.grad.clone() for n, p in model.named_parameters()}

    _, objective_loss, grads_prox = losses_and_grads(0.0)
    model = fresh_model_v2()
    restore_state(model, state)
    model.train()
    torch.manual_seed(1)
    plain = criterion(model(x), y)
    plain.backward()
    grads_avg = {n: p.grad.clone() for n, p in model.named_parameters()}
    max_grad = max(float((grads_avg[n] - grads_prox[n]).abs().max()) for n in grads_avg)
    # Sanity: at mu > 0 the penalty is zero at w == w_global and the gradient is unchanged there.
    _, _, grads_pos = losses_and_grads(0.1)
    penalty_zero_at_start = float(proximal_penalty(
        model, {n: p.detach().clone() for n, p in model.named_parameters()}).item()) == 0.0
    level_a = {"fedavg_loss": float(plain.item()), "fedprox_mu0_loss": objective_loss,
               "loss_delta": abs(float(plain.item()) - objective_loss),
               "max_abs_gradient_delta": max_grad, "trainable_parameters_compared": len(grads_avg),
               "penalty_is_zero_at_round_start": penalty_zero_at_start,
               "gradient_unchanged_at_round_start_for_mu_0_1": all(
                   torch.equal(grads_pos[n], grads_avg[n]) for n in grads_avg),
               "status": "PASS" if (float(plain.item()) == objective_loss and max_grad == 0.0)
               else "FAIL"}
    # B + C. Real LABEL client setup, round 1, all eight clients.
    train = guarded_population(ROOT, "TRAIN", "preflight_mu0_equivalence")
    inputs = normalized_population(train)
    sites = load_sites(ROOT / "manifests/clients/NONIID_LABEL_V1.csv")
    pos_weight = float(np.sum(train.labels == 0) / np.sum(train.labels == 1))
    set_determinism(20260927)
    initial = fresh_initial_state_v2(20260927)
    kwargs = {"global_state": initial, "round_number": 1,
              "experiment_id": CONFIG["shuffle_seed_namespace"], "base_seed": 20260927,
              "batch_size": 64, "learning_rate": 0.001, "weight_decay": 0.0001,
              "pos_weight": pos_weight}
    clients, avg_updates, prox_updates = [], [], []
    for site in SITE_IDS:
        idx = np.flatnonzero(np.isin(train.participant_group_ids, sites[site]))
        a = train_local_epoch_v2(inputs=inputs[idx], labels=train.labels[idx], site_id=site,
                                 **kwargs)
        b = train_local_fedprox_epoch_v2(inputs=inputs[idx], labels=train.labels[idx],
                                         site_id=site, mu=0.0, **kwargs)
        deltas = [float(np.max(np.abs(np.asarray(a.update.delta[k], dtype=np.float64)
                                      - np.asarray(b.update.delta[k], dtype=np.float64))))
                  if np.issubdtype(initial[k].dtype, np.floating)
                  else float(not np.array_equal(a.update.delta[k], b.update.delta[k]))
                  for k in initial]
        clients.append({
            "site_id": site, "examples": a.examples_seen,
            "same_examples": a.examples_seen == b.examples_seen,
            "same_shuffle_seed": a.shuffle_seed == b.shuffle_seed,
            "same_batches": a.batch_count == b.batch_count,
            "same_mean_loss": a.mean_loss == b.mean_loss,
            "max_abs_delta_difference": max(deltas),
            "non_floating_policy_identical": all(
                np.array_equal(a.update.delta[k], b.update.delta[k])
                for k in initial if not np.issubdtype(initial[k].dtype, np.floating))})
        avg_updates.append(a.update)
        prox_updates.append(b.update)
    level_b = {"clients": clients, "max_abs_delta_difference_all_clients": max(
        c["max_abs_delta_difference"] for c in clients),
        "status": "PASS" if all(
            c["same_examples"] and c["same_shuffle_seed"] and c["same_batches"]
            and c["same_mean_loss"] and c["max_abs_delta_difference"] == 0.0
            and c["non_floating_policy_identical"] for c in clients) else "FAIL"}
    aggregate_prox, _ = aggregate_weighted_deltas(initial, prox_updates)
    aggregate_avg, _ = aggregate_weighted_deltas(initial, avg_updates)
    stored = CONFIG["label_fedavg_baseline"]["round_1_state_sha256"]
    level_c = {"stored_V2_FL_002_LABEL_round_1_sha256": stored,
               "fedavg_recomputed_round_1_sha256": state_sha(aggregate_avg),
               "fedprox_mu0_round_1_sha256": state_sha(aggregate_prox),
               "exact_match": state_sha(aggregate_prox) == stored == state_sha(aggregate_avg)}
    level_c["status"] = "PASS" if level_c["exact_match"] else "FAIL"
    data = {"A_objective_gradient": level_a, "B_local_updates": level_b,
            "C_round_1_aggregate": level_c,
            "status": "PASS" if all(x["status"] == "PASS" for x in (level_a, level_b, level_c))
            else "FAIL"}
    _write("mu0_equivalence.json", data)
    return data


def guardrail() -> dict:
    baseline_worst = CONFIG["label_fedavg_baseline"]["VALIDATION_PATIENT_WORST_AUPRC_V2"]
    threshold = baseline_worst - GUARDRAIL_DEGRADATION
    data = {"baseline_label_fedavg_worst_patient_AUPRC": baseline_worst,
            "absolute_degradation": GUARDRAIL_DEGRADATION, "threshold": threshold,
            "threshold_is_negative": threshold < 0,
            "nonbinding_for_any_valid_candidate": threshold < 0,
            "explanation": "finite AUPRC >= 0 > threshold: the source-defined absolute five-point "
            "guardrail cannot exclude a candidate when the baseline worst-patient AUPRC is 0.0381. "
            "Documented before results; not repaired; no tighter V2 guardrail is invented.",
            "candidates": list(CANDIDATES)}
    _write("guardrail_arithmetic.json", data)
    return data


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    entry = verify_v2_fl_002()
    _write("entry_verification.json", entry)
    if entry["status"] != "PASS":
        sys.exit(f"V2_FL_003_ENTRY_FAILED:{entry['problems']}")
    mu0 = mu0_equivalence()
    guard = guardrail()
    if mu0["status"] != "PASS":
        sys.exit("V2_FL_003_MU0_EQUIVALENCE_FAILED: do not run mu candidates")
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True,
                          check=True).stdout.strip()
    (OUT / "protected_baseline.json").write_text(json.dumps(
        {"artifacts": {p: hash_file(ROOT / p) for p in PROTECTED}}, indent=2,
        sort_keys=True) + "\n", encoding="utf-8")
    protocol_v1 = ROOT / "manifests/model_v2/MODEL_V2_FL_PROTOCOL_V1.lock.json"
    lock = {
        "lock_id": "MODEL_V2_FL_PROTOCOL_V2", "status": "FROZEN_RESEARCH_PROTOCOL_SUCCESSOR",
        "predecessor_id": "MODEL_V2_FL_PROTOCOL_V1", "predecessor_sha256": hash_file(protocol_v1),
        "predecessor_unchanged": True, "owner_task": "V2-FL-003",
        "roadmap": ["V2-FL-003", "V2-FL-EVAL-001", "V2-FL-004", "V2-FL-005", "V2-014"],
        "created_before_any_fedprox_outcome": True,
        "bound_artifacts": {p: hash_file(ROOT / p) for p in (
            "configs/model_v2/fl_protocol_v2.yaml", CONFIG_RELATIVE)},
        "change_control": "Any change requires a successor; not a response to FedProx results."}
    lock_path = ROOT / "manifests/model_v2/MODEL_V2_FL_PROTOCOL_V2.lock.json"
    lock_path.write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write("method_freeze.json", {
        "owner_task": "V2-FL-003", "gate": "V2FLG2", "entry_head": head,
        "protocol_v2_lock_sha256": hash_file(lock_path),
        "method_file_sha256": {p: hash_file(ROOT / p) for p in METHOD_FILES},
        "positive_mu_outcome_exists_at_method_freeze": False,
        "mu0_equivalence": mu0["status"], "guardrail_threshold": guard["threshold"],
        "candidate_set": list(CANDIDATES), "status": "PASS"})
    print("V2-FL-003 method frozen at", head)


if __name__ == "__main__":
    main()
