#!/usr/bin/env python3
"""Build configs/model_v2/fl_test_family_v1.yaml (V2_FL_TEST_FAMILY_V1): the exact 20 frozen,
development-selected checkpoints, their SHA-256 and their DEVELOPMENT (clean VALIDATION) metrics
read from committed reports. Metadata only: no checkpoint is run, no held-out data is read."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
COND = ["iid", "label", "quantity", "feature", "combined"]
V1_FEDAVG = {"iid": ("checkpoints/federated/FL_IID_V1_best.pt", "reports/fl_iid.json"),
             "label": ("checkpoints/federated/FL_LABEL_SKEW_V1_best.pt",
                       "reports/t026/label_result.json"),
             "quantity": ("checkpoints/federated/FL_QUANTITY_SKEW_V1_best.pt",
                          "reports/t026/quantity_result.json"),
             "feature": ("checkpoints/federated/FL_FEATURE_NOISE_V1_best.pt",
                         "reports/t026/feature_result.json"),
             "combined": ("checkpoints/federated/FL_COMBINED_SKEW_V1_best.pt",
                          "reports/t026/combined_result.json")}
V1_FEDPROX = {"iid": ("checkpoints/federated/FL_IID_FEDPROX_V1_best.pt",
                      "reports/t027/comparisons/iid_result.json"),
              "label": ("checkpoints/federated/fedprox_candidates/LABEL_mu_0p01_best.pt",
                        "reports/t027/candidates/mu_0p01_result.json"),
              "quantity": ("checkpoints/federated/FL_QUANTITY_FEDPROX_V1_best.pt",
                           "reports/t027/comparisons/quantity_result.json"),
              "feature": ("checkpoints/federated/FL_FEATURE_FEDPROX_V1_best.pt",
                          "reports/t027/comparisons/feature_result.json"),
              "combined": ("checkpoints/federated/FL_COMBINED_FEDPROX_V1_best.pt",
                           "reports/t027/comparisons/combined_result.json")}
V2_FEDAVG = {"iid": ("checkpoints/model_v2/v2_fl_001/FL_IID_MODEL_V2_V1_best.pt",
                     "reports/model_v2/v2_fl_001/fl_iid_model_v2_result.json"),
             **{c: (f"checkpoints/model_v2/v2_fl_002/FL_{n}_MODEL_V2_V1_best.pt",
                    f"reports/model_v2/v2_fl_002/{c}_result.json")
                for c, n in (("label", "LABEL_SKEW"), ("quantity", "QUANTITY_SKEW"),
                             ("feature", "FEATURE_NOISE"), ("combined", "COMBINED_SKEW"))}}
V2_FEDPROX = {
    "iid": ("checkpoints/model_v2/v2_fl_003/transfer/FL_IID_FEDPROX_MODEL_V2_MU_0p1_best.pt",
            "reports/model_v2/v2_fl_003/transfer/iid/result.json"),
    "label": ("checkpoints/model_v2/v2_fl_003/candidates/"
              "FL_LABEL_FEDPROX_MODEL_V2_MU_0p1_best.pt",
              "reports/model_v2/v2_fl_003/candidates/mu_0p1/result.json"),
    **{c: ("checkpoints/model_v2/v2_fl_003/transfer/"
           f"FL_{c.upper()}_FEDPROX_MODEL_V2_MU_0p1_best.pt",
           f"reports/model_v2/v2_fl_003/transfer/{c}/result.json")
       for c in ("quantity", "feature", "combined")}}


def entry(generation: str, algorithm: str, condition: str, mu: float | None,
          checkpoint: str, result_path: str) -> dict:
    result = json.loads((ROOT / result_path).read_text())
    best = result["best_validation"]
    return {
        "id": f"{generation}_{algorithm.upper()}_{condition.upper()}",
        "generation": generation, "algorithm": algorithm, "condition": condition, "mu": mu,
        "architecture": "MODEL_V1_ARCHITECTURE_V1" if generation == "V1" else "MODEL_V2_TCN_MEAN",
        "checkpoint": checkpoint, "checkpoint_sha256": hash_file(ROOT / checkpoint),
        "development_round": int(result["best_round"]),
        "development_validation_AUPRC": float(best["AUPRC"]),
        "development_validation_patient_macro_F1": float(best["patient_macro_F1"]),
        "development_result": result_path}


def main() -> None:
    models = []
    for generation, algorithm, table, mu in (
            ("V1", "FedAvg", V1_FEDAVG, None), ("V1", "FedProx", V1_FEDPROX, 0.01),
            ("V2", "FedAvg", V2_FEDAVG, None), ("V2", "FedProx", V2_FEDPROX, 0.1)):
        for condition in COND:
            models.append(entry(generation, algorithm, condition, mu, *table[condition]))
    family = {
        "family_id": "V2_FL_TEST_FAMILY_V1", "task_id": "V2-FL-EVAL-001",
        "selection_basis": "development-selected best-VALIDATION checkpoints only; no held-out "
        "information was used",
        "model_count": len(models), "models": models,
        "excluded": [
            "V2 FedProx mu=0.001 candidate", "V2 FedProx mu=0.01 candidate",
            "historical rejected V1 FedProx candidates (mu 0.001 / 0.1)",
            "any round-50 checkpoint", "any intermediate-round checkpoint",
            "MODEL_V2_FINAL (centralized; historical evidence only)",
            "MODEL_V1 centralized checkpoint (historical evidence only)"],
        "no_retraining": True}
    path = ROOT / "configs/model_v2/fl_test_family_v1.yaml"
    header = "# V2_FL_TEST_FAMILY_V1 -- frozen BEFORE any INTERNAL_TEST/INCART FL inference.\n"
    path.write_text(header + yaml.safe_dump(family, sort_keys=False), encoding="utf-8")
    print(len(models), "models;", hash_file(path))


if __name__ == "__main__":
    main()
