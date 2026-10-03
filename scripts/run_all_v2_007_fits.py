#!/usr/bin/env python3
"""V2-007: run exactly six canonical finalist fits, in the predeclared deterministic order
(TCN_MEAN seeds 27/28/29, then TCN_MEANMAX seeds 27/28/29). Each fit runs as its own fresh
subprocess (matching V2-004/V2-006 precedent) so no state leaks between fits. No official
VALIDATION access occurs here.
"""

from __future__ import annotations

import csv
import json
import os
import subprocess
import sys

import scripts._v2_007_lib as lib

OUT_DIR = lib.ROOT / "reports/model_v2/v2_007"

ORDER = [
    ("MODEL_V2_TCN_MEAN", 20260927),
    ("MODEL_V2_TCN_MEAN", 20260928),
    ("MODEL_V2_TCN_MEAN", 20260929),
    ("MODEL_V2_TCN_MEANMAX", 20260927),
    ("MODEL_V2_TCN_MEANMAX", 20260928),
    ("MODEL_V2_TCN_MEANMAX", 20260929),
]


def main() -> None:
    results = []
    for architecture_id, seed in ORDER:
        exp_id = lib.experiment_id(architecture_id, seed)
        print(f"=== running {exp_id} ===", flush=True)
        env = dict(os.environ)
        env["PYTHONPATH"] = "src:."
        result = subprocess.run(
            [
                sys.executable, "scripts/run_v2_007_fit.py",
                "--architecture", architecture_id, "--seed", str(seed),
            ],
            cwd=lib.ROOT, env=env,
        )
        if result.returncode != 0:
            raise RuntimeError(f"{exp_id} FAILED with exit code {result.returncode}")
        summary_path = OUT_DIR / "runs" / exp_id / "fit_summary.json"
        results.append(json.loads(summary_path.read_text(encoding="utf-8")))

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    with (OUT_DIR / "fit_summary.csv").open("w", newline="", encoding="utf-8") as handle:
        rows = [
            {
                "experiment_id": r["experiment_id"],
                "architecture_id": r["architecture_id"],
                "schedule_id": r["schedule_id"],
                "seed": r["seed"],
                "selected_epoch": r["selected_epoch"],
                "best_final_inner_validation_auprc": r["best_final_inner_validation_auprc"],
                "checkpoint_sha256": r["checkpoint_sha256"],
                "parameter_count": r["parameter_count"],
                "epochs_completed": r["epochs_completed"],
                "stop_reason": r["stop_reason"],
                "source_train_auprc": r["source_train_diagnostic"]["source_train_auprc"],
                "source_train_auroc": r["source_train_diagnostic"]["source_train_auroc"],
            }
            for r in results
        ]
        writer = csv.DictWriter(handle, lineterminator="\n", fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    with (OUT_DIR / "source_train_metrics.csv").open("w", newline="", encoding="utf-8") as handle:
        rows = [
            {
                "experiment_id": r["experiment_id"],
                "architecture_id": r["architecture_id"],
                "seed": r["seed"],
                "windows": r["source_train_diagnostic"]["windows"],
                "source_train_auprc": r["source_train_diagnostic"]["source_train_auprc"],
                "source_train_auroc": r["source_train_diagnostic"]["source_train_auroc"],
            }
            for r in results
        ]
        writer = csv.DictWriter(handle, lineterminator="\n", fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    combined_rows = []
    for r in results:
        curve_path = OUT_DIR / "runs" / r["experiment_id"] / "training_curve.csv"
        with curve_path.open(newline="", encoding="utf-8") as handle:
            combined_rows.extend(csv.DictReader(handle))
    with (OUT_DIR / "training_curves.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle, lineterminator="\n", fieldnames=list(combined_rows[0].keys())
        )
        writer.writeheader()
        writer.writerows(combined_rows)

    print(f"All {len(results)} V2-007 fits completed.")


if __name__ == "__main__":
    main()
