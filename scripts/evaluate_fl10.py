# ruff: noqa: E501
"""Evaluate R0-R10 of a COMPLETED FL10 run on the frozen fresh holdout.   python -m scripts.evaluate_fl10 --method-commit SHA --run reports/fl10/runs/modeA --out reports/fl10/eval/modeA"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from federated.wearable_fl_runner_v1 import build_cohort
from fl10 import evaluate as ev


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--method-commit", required=True)
    ap.add_argument("--run", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    run_dir, out = Path(a.run), Path(a.out)
    if (out / "evaluation_results.json").exists():
        raise SystemExit("REFUSING_TO_OVERWRITE_EXISTING_EVALUATION")
    _, training, _ = build_cohort()
    link = run_dir / "monitoring_link.json"
    if link.exists() and not json.loads(link.read_text())["parity"]["dataset_identical_to_canonical"]:
        raise SystemExit("MODE_B_LIVE_WINDOWS_DIFFER_FROM_TRAINING_SET_SCREENING_REQUIRES_THEIR_TENSORS")   # screening relies on the measured equality recorded by the run
    res = ev.evaluate_run(run_dir, out, method_commit=a.method_commit, training_datasets=training)
    r = res["result"]
    for s in ev.STATES:
        p = r["states"][s]["pooled"]
        print(s, {m: (round(p[m], 4) if p[m] is not None else None) for m in ("AUPRC", "AUROC", "F1", "accuracy", "recall", "specificity", "BCE", "Brier")}, p["TP"], p["FP"], p["TN"], p["FN"])
    print("hashes", res["hashes"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
