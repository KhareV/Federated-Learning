from __future__ import annotations

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
