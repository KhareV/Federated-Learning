#!/usr/bin/env python3
"""V2-011 prediction-table error analysis (patient/Brier, class composition, quality, HR,
dataset, threshold region, NSTDB SNR). Frozen V2-010 tables only; no model inference and no
waveform access (annotation files are read only for the TRAIN-binned HR join).
"""

from __future__ import annotations

import json

import scripts._v2_011_analysis as analysis
import scripts._v2_011_cases as cases

ROOT = cases.ROOT
OUT = cases.OUT


TABLE_FILES = {
    "patient_internal": "patient_slice_internal.csv",
    "patient_incart": "patient_slice_incart.csv",
    "class_composition": "class_composition_slice.csv",
    "quality": "quality_slice.csv",
    "heart_rate": "heart_rate_slice.csv",
    "dataset": "dataset_slice.csv",
    "threshold_region": "threshold_region_slice.csv",
    "nstdb_snr": "nstdb_snr_slice.csv",
}


def render(tables: dict, out_dir) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for key, name in TABLE_FILES.items():
        rows = tables[key]
        fields = list(rows[0])
        for row in rows:
            for field in row:
                if field not in fields:
                    fields.append(field)
        cases.write_csv(out_dir / name, rows, fields)


def main() -> None:
    tables = analysis.compute_error_tables(ROOT)
    render(tables, OUT)
    report = {
        "id": "ERROR_ANALYSIS_V2",
        "posthoc_only": True,
        "no_tuning": True,
        "threshold_changed": False,
        "model_inference_performed": False,
        "patient_ranking": {
            "id": "PATIENT_ERROR_RANKING_V2",
            "metric": "BRIER",
            "direction": "LOWER_IS_BETTER",
            "internal_best": tables["patient_internal"][0]["patient"],
            "internal_worst": tables["patient_internal"][-1]["patient"],
            "incart_best": tables["patient_incart"][0]["patient"],
            "incart_worst": tables["patient_incart"][-1]["patient"],
            "single_class_f1_caveat": True,
        },
        "tables": {k: f"reports/model_v2/v2_011/{n}" for k, n in TABLE_FILES.items()},
        "dataset_slice": tables["dataset"],
        "threshold_region": tables["threshold_region"],
        "quality_states_present": sorted({r["quality_group"] for r in tables["quality"]}),
        "prevalence_caveat": (
            "different prevalence means raw AUPRC magnitudes are not directly exchangeable "
            "across datasets; INCART remains un-recalibrated and its Brier is the error of the "
            "transferred MIT-BIH source-domain probability, not an external calibration validation"
        ),
        "claim_boundary": "descriptive associations only; no tuning, no clinical claim",
        "status": "PASS",
    }
    # noise-type results are attached by the noise-type session once complete
    cases.write_json(OUT / "error_analysis_v2.json", report)
    print(json.dumps({"status": "PASS", "tables": len(tables)}))


if __name__ == "__main__":
    main()
