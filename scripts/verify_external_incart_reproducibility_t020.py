#!/usr/bin/env python3
"""Reproduce T020 metrics/bootstrap twice from frozen predictions, never model inference."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from evaluation.bootstrap import bootstrap_replicates, percentile_summary  # noqa: E402
from evaluation.external_incart import (  # noqa: E402
    PREDICTION_PATH,
    _prediction_arrays,
    _write_bootstrap_csv,
    verify_external_freeze,
)
from evaluation.metrics import pooled_binary_metrics  # noqa: E402
from nhm.hashing import hash_file  # noqa: E402
from scripts.generate_model_v1_test_vector_t016 import write_deterministic_npz  # noqa: E402


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def recalculate(output: Path) -> dict:
    patients, labels, probabilities, predictions, _ = _prediction_arrays(ROOT / PREDICTION_PATH)
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
    write_deterministic_npz(
        draw_path,
        {
            "draws_int64": draws,
            "patient_ids_utf8": np.asarray(sorted(set(patients.tolist())), dtype="S32"),
        },
    )
    _write_bootstrap_csv(replicate_path, rows)
    summary = percentile_summary(point, rows)
    return {
        "draw_sha256": hash_file(draw_path),
        "replicate_sha256": hash_file(replicate_path),
        "summary": summary,
        "point_metrics": point,
    }


def main() -> None:
    freeze = verify_external_freeze(ROOT)
    with tempfile.TemporaryDirectory() as first_dir, tempfile.TemporaryDirectory() as second_dir:
        first = recalculate(Path(first_dir))
        second = recalculate(Path(second_dir))
    if first != second:
        raise RuntimeError("EXTERNAL_PREDICTION_ONLY_REPRODUCIBILITY_FAILURE")
    canonical_draw = hash_file(ROOT / "reports/t020/bootstrap_draws.npz")
    canonical_replicate = hash_file(ROOT / "reports/t020/bootstrap_replicates.csv")
    if first["draw_sha256"] != canonical_draw:
        raise RuntimeError("EXTERNAL_BOOTSTRAP_DRAW_REPRODUCIBILITY_FAILURE")
    if first["replicate_sha256"] != canonical_replicate:
        raise RuntimeError("EXTERNAL_BOOTSTRAP_REPLICATE_REPRODUCIBILITY_FAILURE")
    canonical_summary = json.loads(
        (ROOT / "reports/t020/bootstrap_summary.json").read_text(encoding="utf-8")
    )["metrics"]
    if first["summary"] != canonical_summary:
        raise RuntimeError("EXTERNAL_BOOTSTRAP_SUMMARY_REPRODUCIBILITY_FAILURE")
    report = {
        "evaluation_id": "EXTERNAL_INCART_V1",
        "prediction_source": str(PREDICTION_PATH),
        "MODEL_V1_rerun_for_reproducibility": False,
        "point_metrics_run_1": first["point_metrics"],
        "point_metrics_run_2": second["point_metrics"],
        "point_metrics_identical": True,
        "draw_matrix_run_1_sha256": first["draw_sha256"],
        "draw_matrix_run_2_sha256": second["draw_sha256"],
        "draw_matrices_identical": True,
        "replicate_table_run_1_sha256": first["replicate_sha256"],
        "replicate_table_run_2_sha256": second["replicate_sha256"],
        "replicate_tables_identical": True,
        "CI_summary_run_1": first["summary"],
        "CI_summary_run_2": second["summary"],
        "CI_summaries_identical": True,
        "freeze_verification": freeze,
        "overall_status": "PASS",
    }
    write_json(ROOT / "reports/t020/reproducibility.json", report)
    print("T020 prediction-only reproducibility: PASS")


if __name__ == "__main__":
    main()
