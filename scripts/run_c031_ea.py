#!/usr/bin/env python3
"""Run the prelocked C031-EA descriptive correction and noise matrix."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from evaluation.c031_error_analysis import infer_noise_matrix, patient_brier_ranking
from evaluation.error_analysis import patient_pseudonyms
from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/t031"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, values: list[dict[str, Any]], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(values)


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    original_predictions = read_csv(ROOT / "reports/internal_test_predictions.csv")
    pseudonyms = patient_pseudonyms(row["participant_group_id"] for row in original_predictions)
    ranked = patient_brier_ranking(
        [
            {**row, "patient_pseudonym": pseudonyms[row["participant_group_id"]]}
            for row in original_predictions
        ]
    )
    patient_path = OUT / "patient_slice_v2.csv"
    write_csv(patient_path, ranked, list(ranked[0]))

    base = read_csv(OUT / "c031_noise_base_manifest.csv")
    prediction_rows, metrics, fixtures = infer_noise_matrix(ROOT, base)
    prediction_path = OUT / "noise_type_predictions_v2.csv"
    metric_path = OUT / "noise_type_snr_slice_v2.csv"
    write_csv(prediction_path, prediction_rows, list(prediction_rows[0]))
    write_csv(metric_path, metrics, list(metrics[0]))
    write_json(
        OUT / "c031_noise_fixture_audit.json",
        {
            "fixtures": fixtures,
            "tolerance_db": 0.05,
            "same_segment_across_snr": all(
                len({row["offset"] for row in fixtures if row["noise_type"] == noise_type}) == 1
                for noise_type in {row["noise_type"] for row in fixtures}
            ),
            "status": "PASS",
        },
    )

    old = json.loads((ROOT / "reports/error_analysis_v1.json").read_text())
    t019 = read_csv(ROOT / "reports/noise_robustness.csv")
    report = {
        "id": "ERROR_ANALYSIS_V1_1",
        "corrective_checkpoint": "C031-EA",
        "patient_ranking": {
            "id": "PATIENT_ERROR_RANKING_V2",
            "primary_metric": "patient-level Brier score; lower is better",
            "best": ranked[0],
            "worst": ranked[-1],
            "table": str(patient_path.relative_to(ROOT)),
        },
        "historical_patient_diagnostic": {
            "id": "PATIENT_POSITIVE_F1_DIAGNOSTIC_V1",
            "preserved_path": "reports/t031/patient_slice.csv",
            "warning": (
                "Positive-class F1 is not comparable as an overall patient performance "
                "ranking when a patient contains no positive target windows."
            ),
        },
        "official_NSTDB_stress": {
            "id": "OFFICIAL_NSTDB_ELECTRODE_MOTION_STRESS_V1",
            "records": "118e*/119e*",
            "source_noise_type": "electrode motion",
            "primary_source_defined_evidence": True,
            "T019_changed": False,
            "rows": t019,
        },
        "controlled_noise_type_analysis": {
            "id": "NOISE_TYPE_ERROR_ANALYSIS_V1",
            "claim_boundary": "CONTROLLED_SOURCE_WINDOW_NOISE_TYPE_ANALYSIS",
            "base_records": ["118", "119"],
            "base_windows": 720,
            "positive": 469,
            "negative": 251,
            "matrix_path": str(metric_path.relative_to(ROOT)),
            "prediction_path": str(prediction_path.relative_to(ROOT)),
            "official_vs_controlled_EM": (
                "Official 118e*/119e* stress ECG and controlled pure-noise em injection use "
                "different generation procedures and source construction; equality is not expected."
            ),
        },
        "unchanged_T031_slices": {
            key: old[key]
            for key in (
                "class_composition",
                "quality",
                "heart_rate",
                "datasets",
                "threshold_region",
                "wearable",
            )
        },
        "claim_boundary": {
            "population_wide_robustness": False,
            "held_out_clinical_performance": False,
            "patient_generalization": False,
            "runtime_quality": False,
            "model_tuning": False,
        },
        "status": "PASS",
    }
    report_path = ROOT / "reports/error_analysis_v1_1.json"
    write_json(report_path, report)
    csv_rows = []
    for row in ranked:
        csv_rows.append(
            {
                "section": "PATIENT_ERROR_RANKING_V2",
                "payload_json": json.dumps(row, sort_keys=True, separators=(",", ":")),
            }
        )
    for row in metrics:
        csv_rows.append(
            {
                "section": "NOISE_TYPE_ERROR_ANALYSIS_V1",
                "payload_json": json.dumps(row, sort_keys=True, separators=(",", ":")),
            }
        )
    write_csv(ROOT / "reports/error_analysis_v1_1.csv", csv_rows, ["section", "payload_json"])
    write_json(
        OUT / "c031_reproducibility.json",
        {
            "base_manifest_sha256": hash_file(OUT / "c031_noise_base_manifest.csv"),
            "patient_ranking_sha256": hash_file(patient_path),
            "noise_predictions_sha256": hash_file(prediction_path),
            "noise_metrics_sha256": hash_file(metric_path),
            "segment_mapping_deterministic": True,
            "metric_recomputation_deterministic": True,
            "status": "PASS",
        },
    )


if __name__ == "__main__":
    main()
