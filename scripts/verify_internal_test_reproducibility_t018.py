#!/usr/bin/env python3
"""Recompute T018 statistics twice from frozen predictions, never model inference."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from evaluation.bootstrap import bootstrap_replicates, percentile_summary  # noqa: E402
from evaluation.internal_test import (  # noqa: E402
    _read_predictions,
    _write_bootstrap_csv,
    verify_internal_test_freeze,
)
from evaluation.metrics import pooled_binary_metrics  # noqa: E402
from nhm.hashing import hash_file  # noqa: E402
from scripts.generate_model_v1_test_vector_t016 import write_deterministic_npz  # noqa: E402


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def one_recalculation(output: Path) -> dict:
    patients, labels, probabilities, predictions = _read_predictions(
        ROOT / "reports/internal_test_predictions.csv"
    )
    point = pooled_binary_metrics(labels, probabilities, predictions, patients)
    draws, rows = bootstrap_replicates(
        patients,
        labels,
        probabilities,
        predictions,
        replicates=2000,
        seed=20260927,
    )
    draw_path = output / "bootstrap_draws.npz"
    replicate_path = output / "bootstrap_replicates.csv"
    summary_path = output / "bootstrap_summary.json"
    write_deterministic_npz(
        draw_path,
        {
            "draws_int64": draws,
            "patient_ids_utf8": np.asarray(sorted(set(patients.tolist())), dtype="S32"),
        },
    )
    _write_bootstrap_csv(replicate_path, rows)
    summary = percentile_summary(point, rows)
    write_json(summary_path, summary)
    return {
        "draw_sha256": hash_file(draw_path),
        "replicate_sha256": hash_file(replicate_path),
        "summary_sha256": hash_file(summary_path),
        "summary": summary,
    }


def main() -> None:
    verification = verify_internal_test_freeze(ROOT)
    with tempfile.TemporaryDirectory() as first_dir, tempfile.TemporaryDirectory() as second_dir:
        first = one_recalculation(Path(first_dir))
        second = one_recalculation(Path(second_dir))
    canonical_draw_sha = hash_file(ROOT / "reports/t018/bootstrap_draws.npz")
    canonical_replicate_sha = hash_file(ROOT / "reports/t018/bootstrap_replicates.csv")
    if first != second:
        raise RuntimeError("BOOTSTRAP_REPRODUCIBILITY_FAILURE")
    if first["draw_sha256"] != canonical_draw_sha:
        raise RuntimeError("BOOTSTRAP_DRAW_REPRODUCIBILITY_FAILURE")
    if first["replicate_sha256"] != canonical_replicate_sha:
        raise RuntimeError("BOOTSTRAP_REPLICATE_REPRODUCIBILITY_FAILURE")
    report = {
        "evaluation_id": "INTERNAL_EVAL_V1",
        "prediction_source": "reports/internal_test_predictions.csv",
        "model_inference_repeated": False,
        "point_metric_recalculation": "PASS",
        "draw_matrix_run_1_sha256": first["draw_sha256"],
        "draw_matrix_run_2_sha256": second["draw_sha256"],
        "draw_matrices_identical": True,
        "replicate_table_run_1_sha256": first["replicate_sha256"],
        "replicate_table_run_2_sha256": second["replicate_sha256"],
        "replicate_tables_identical": True,
        "ci_summary_run_1": first["summary"],
        "ci_summary_run_2": second["summary"],
        "ci_summaries_identical": True,
        "freeze_verification": verification,
        "overall_status": "PASS",
    }
    output = ROOT / "reports/t018/reproducibility.json"
    write_json(output, report)
    print("T018 prediction-only reproducibility: PASS")


if __name__ == "__main__":
    main()
