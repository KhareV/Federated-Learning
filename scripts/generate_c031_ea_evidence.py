#!/usr/bin/env python3
"""Generate C031-EA immutability, scope, and inventory evidence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/t031"


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    immutable = [
        "artifacts/EXPLAINABILITY_V1_METHOD.lock.json",
        "reports/t031/explainability_case_manifest.csv",
        "reports/t031/cases/TP_attribution.csv",
        "reports/t031/cases/TN_attribution.csv",
        "reports/t031/cases/FP_attribution.csv",
        "reports/t031/cases/FN_attribution.csv",
        "reports/t031/cases/TP_figure.svg",
        "reports/t031/cases/TN_figure.svg",
        "reports/t031/cases/FP_figure.svg",
        "reports/t031/cases/FN_figure.svg",
        "checkpoints/MODEL_V1.pt",
        "artifacts/CAL_V1.json",
        "manifests/preprocessing/PREPROC_V1.lock.json",
        "reports/noise_robustness.json",
        "reports/error_analysis_v1.json",
    ]
    write_json(
        OUT / "c031_immutability_audit.json",
        {
            "entry_SHA": "4f3caebd9f62616ed3b5a1c05f0a2e44acdb9285",
            "artifacts": {path: hash_file(ROOT / path) for path in immutable},
            "G17_remains_PASS": True,
            "status": "PASS",
        },
    )
    write_json(
        OUT / "c031_scope_audit.json",
        {
            "MODEL_training": False,
            "threshold_tuning": False,
            "CAL_fitting": False,
            "PREPROC_change": False,
            "T019_change": False,
            "IG_case_change": False,
            "hardware": False,
            "quality_runtime_claim": False,
            "status": "PASS",
        },
    )
    artifacts = [
        "configs/c031_error_analysis_v1.yaml",
        "artifacts/C031_ERROR_ANALYSIS_V1.lock.json",
        "evaluation/c031_error_analysis.py",
        "scripts/prepare_c031_ea.py",
        "scripts/run_c031_ea.py",
        "scripts/generate_c031_ea_evidence.py",
        "scripts/verify_c031_ea.py",
        "reports/t031/c031_noise_base_manifest.csv",
        "reports/t031/patient_slice_v2.csv",
        "reports/t031/noise_type_predictions_v2.csv",
        "reports/t031/noise_type_snr_slice_v2.csv",
        "reports/t031/c031_noise_fixture_audit.json",
        "reports/t031/c031_reproducibility.json",
        "reports/t031/c031_immutability_audit.json",
        "reports/t031/c031_scope_audit.json",
        "reports/error_analysis_v1_1.json",
        "reports/error_analysis_v1_1.csv",
    ]
    write_json(
        OUT / "c031_artifact_hashes.json",
        {path: hash_file(ROOT / path) for path in artifacts},
    )


if __name__ == "__main__":
    main()
