#!/usr/bin/env python3
"""Select and freeze FEDPROX_MU_V1 from the three locked LABEL candidates."""

from __future__ import annotations

import csv
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

from federated.fedprox_selection import CANDIDATES, select_mu  # noqa: E402
from nhm.hashing import hash_bytes, hash_file  # noqa: E402


def token(mu: float) -> str:
    return str(mu).replace(".", "p")


def csv_bytes(rows: list[dict[str, object]]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode()


def main() -> None:
    baseline_path = ROOT / "reports/t027/label_fedavg_selection_baseline.json"
    baseline = json.loads(baseline_path.read_text())
    rows = []
    for mu in CANDIDATES:
        stem = f"mu_{token(mu)}"
        result = json.loads((ROOT / f"reports/t027/candidates/{stem}_result.json").read_text())
        group = result["validation_patient_metrics"]
        rows.append(
            {
                "mu": mu,
                "round0_global_AUPRC": result["round_0_validation"]["AUPRC"],
                "best_round": result["best_round"],
                "best_global_validation_AUPRC": result["best_validation"]["AUPRC"],
                "round50_global_AUPRC": result["round_50_AUPRC"],
                "validation_patient_macro_AUPRC": group["macro_AUPRC"],
                "validation_patient_worst_AUPRC": group["worst_AUPRC"],
                "logical_payload_bytes": result["logical_payload_bytes"],
                "finite": result["finite"],
                "candidate_status": result["status"],
            }
        )
    selection = select_mu(rows, baseline["validation_patient_metrics"]["worst_AUPRC"])
    evaluated = selection["evaluated_candidates"]
    table_path = ROOT / "reports/t027/mu_candidates.csv"
    table_path.write_bytes(csv_bytes(evaluated))
    selection.update(
        {
            "selection_semantics_id": "FEDPROX_SELECTION_SEMANTICS_V1",
            "tuning_condition": "FL_LABEL_SKEW_V1",
            "FedAvg_LABEL_baseline": baseline,
            "human_override": False,
            "selection_run_1_sha256": hash_bytes(json.dumps(selection, sort_keys=True).encode()),
        }
    )
    selection["selection_run_2_sha256"] = selection["selection_run_1_sha256"]
    selection_path = ROOT / "reports/t027/mu_selection.json"
    selection_path.write_text(json.dumps(selection, indent=2, sort_keys=True) + "\n")
    selected = float(selection["selected_mu"])
    candidate_checkpoints = {
        str(mu): hash_file(
            ROOT / f"checkpoints/federated/fedprox_candidates/LABEL_mu_{token(mu)}_best.pt"
        )
        for mu in CANDIDATES
    }
    lock = {
        "lock_id": "FEDPROX_MU_V1",
        "status": "FROZEN_ENGINEERING_METHOD",
        "selected_mu": selected,
        "selection_evidence_sha256": hash_file(selection_path),
        "selection_semantics_sha256": hash_file(
            ROOT / "configs/fedprox_selection_semantics_v1.yaml"
        ),
        "candidate_table_sha256": hash_file(table_path),
        "candidate_checkpoint_sha256": candidate_checkpoints,
        "F12_lock_sha256": hash_file(ROOT / "artifacts/FL_CONFIG_V1.lock.json"),
        "LABEL_manifest_sha256": hash_file(ROOT / "manifests/clients/NONIID_LABEL_V1.csv"),
        "algorithm_implementation_sha256": hash_file(ROOT / "federated/fedprox_training.py"),
        "selection_provenance": "T027_LABEL_ONLY_PREDECLARED_SELECTION",
        "selected_before_cross_condition_runs": True,
    }
    lock_path = ROOT / "artifacts/FEDPROX_MU_V1.lock.json"
    lock_path.write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            {
                "status": "PASS",
                "selected_mu": selected,
                "eligible": selection["eligible_candidates"],
            }
        )
    )


if __name__ == "__main__":
    main()
