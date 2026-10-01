from __future__ import annotations

import csv
import json
from pathlib import Path

from evaluation.c031_error_analysis import (
    NOISE_TYPES,
    SNR_LEVELS,
    noise_offset,
    patient_brier_ranking,
)

ROOT = Path(__file__).resolve().parents[1]


def _row(patient: str, label: int, probability: float, prediction: int) -> dict[str, object]:
    return {
        "patient_pseudonym": patient,
        "label": label,
        "source_domain_calibrated_probability": probability,
        "thresholded_prediction": prediction,
    }


def test_brier_ranking_handles_all_negative_and_all_positive_patients() -> None:
    ranked = patient_brier_ranking(
        [
            _row("P_NEG", 0, 0.1, 0),
            _row("P_NEG", 0, 0.2, 0),
            _row("P_POS", 1, 0.4, 0),
            _row("P_POS", 1, 0.5, 0),
        ]
    )
    assert ranked[0]["patient_pseudonym"] == "P_NEG"
    assert ranked[0]["ranking_status"] == "BEST_BY_BRIER"
    assert ranked[-1]["patient_pseudonym"] == "P_POS"
    assert ranked[-1]["ranking_status"] == "WORST_BY_BRIER"
    assert ranked[0]["positive_F1"] == "NOT_INTERPRETABLE_FOR_OVERALL_PATIENT_RANKING"
    assert ranked[-1]["specificity"] == "UNDEFINED_SINGLE_CLASS"


def test_exact_noise_types_snrs_and_deterministic_segment_identity() -> None:
    assert NOISE_TYPES == {
        "BASELINE_WANDER": "bw",
        "ELECTRODE_MOTION": "em",
        "MUSCLE_ARTIFACT": "ma",
    }
    assert SNR_LEVELS == (24, 18, 12, 6, 0, -6)
    first = noise_offset("window", "BASELINE_WANDER", 451389)
    assert first == noise_offset("window", "BASELINE_WANDER", 451389)
    # SNR is intentionally absent from the function: the same segment is reused across SNR.
    assert 0 <= first <= 451389 - 2500


def test_corrective_code_has_no_training_quality_or_tuning_path() -> None:
    text = (ROOT / "evaluation/c031_error_analysis.py").read_text()
    assert "AdamW" not in text
    assert "evaluate_ecg_quality" not in text
    assert "fit_temperature" not in text


def test_canonical_base_closure_matrix_and_labels() -> None:
    with (ROOT / "reports/t031/c031_noise_base_manifest.csv").open(newline="") as handle:
        base = list(csv.DictReader(handle))
    with (ROOT / "reports/t031/noise_type_snr_slice_v2.csv").open(newline="") as handle:
        metrics = list(csv.DictReader(handle))
    with (ROOT / "reports/t031/noise_type_predictions_v2.csv").open(newline="") as handle:
        predictions = list(csv.DictReader(handle))
    assert len(base) == 720
    assert sum(int(row["label"]) for row in base) == 469
    assert len(metrics) == 18
    assert len(predictions) == 720 * 18
    assert {row["noise_type"] for row in metrics} == set(NOISE_TYPES)
    assert {int(row["snr_db"]) for row in metrics} == set(SNR_LEVELS)
    base_labels = {row["base_window_id"]: row["label"] for row in base}
    assert all(base_labels[row["base_window_id"]] == row["label"] for row in predictions)
    for key in {(row["base_window_id"], row["noise_type"]) for row in predictions}:
        offsets = {
            row["noise_offset"]
            for row in predictions
            if (row["base_window_id"], row["noise_type"]) == key
        }
        assert len(offsets) == 1


def test_original_ig_and_t019_hashes_remain_locked() -> None:
    expected = {
        "artifacts/EXPLAINABILITY_V1_METHOD.lock.json": (
            "c5ec8bbfa7329a72f9cfad066837bc6a0740019d0141a78a70633a1458403a4a"
        ),
        "reports/t031/explainability_case_manifest.csv": (
            "4e5dedcd4524362dea6ec59b77b7bcd53816c2035372e54625e705cde60be071"
        ),
        "reports/noise_robustness.json": (
            "fae1d2720dd92987689f9c4421ad23b4b1c279c7b26aedc19e26bbd3169d6829"
        ),
    }
    from nhm.hashing import hash_file

    assert {path: hash_file(ROOT / path) for path in expected} == expected
    report = json.loads((ROOT / "reports/error_analysis_v1_1.json").read_text())
    assert report["official_NSTDB_stress"]["id"] == "OFFICIAL_NSTDB_ELECTRODE_MOTION_STRESS_V1"
    assert report["controlled_noise_type_analysis"]["id"] == "NOISE_TYPE_ERROR_ANALYSIS_V1"
