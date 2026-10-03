"""V2-009 CAL_V2 shared primitives. Reuses evaluation.calibration's generic, partition-driven
numerical helpers (binary_nll, fit_temperature, raw_probability_from_logit, apply_temperature,
source_domain_calibrated_probability, apply_operating_threshold, brier_score,
reliability_bins, select_f1_threshold, reliability_svg, load_calibration_population) exactly
unchanged -- none of that math is model-specific, so CAL_V1's already-tested implementation is
reused rather than re-derived. Only logit extraction is CAL_V2-specific (MODEL_V2_FINAL
instead of MODEL_V1), plus the additive MODEL_V2 partition-firewall wrapper this lineage uses
everywhere else.
"""

from __future__ import annotations

import copy
from pathlib import Path

import numpy as np
import torch

from evaluation.calibration import (
    CalibrationError,
    CalibrationPopulation,
    apply_operating_threshold,
    apply_temperature,
    binary_nll,
    brier_score,
    fit_temperature,
    load_calibration_population,
    raw_probability_from_logit,
    reliability_bins,
    reliability_svg,
    select_f1_threshold,
    source_domain_calibrated_probability,
)
from models.model_v2_final_freeze import load_model_v2_final
from nhm.model_v2_partition_guard import check_partition_allowed

ROOT = Path(__file__).resolve().parents[1]
TASK_ID = "V2-009"
CALIBRATION_ID = "CAL_V2"
CALIBRATION_DOMAIN = "MIT-BIH-v1.0.0"
FIT_PARTITION = "CALIBRATION"


def load_calibration_population_v2(root: Path = ROOT) -> CalibrationPopulation:
    """Fail-closed CALIBRATION-only waveform load for CAL_V2 -- additive partition-firewall
    check wrapped around the unmodified CAL_V1 population loader (that loader only ever reads
    the CALIBRATION partition internally; this wrapper makes the MODEL_V2-lineage firewall
    check explicit and independently testable)."""
    check_partition_allowed(FIT_PARTITION, f"{TASK_ID}_CALIBRATION", {FIT_PARTITION})
    return load_calibration_population(root)


def extract_frozen_logits_v2(
    population: CalibrationPopulation, root: Path = ROOT, batch_size: int = 64
) -> np.ndarray:
    """Run the immutable MODEL_V2_FINAL in eval mode on canonical normalized windows."""
    from preprocessing.windowing import NORMALIZATION_EPSILON, normalize_window_zscore

    model, _metadata = load_model_v2_final(root)
    before = copy.deepcopy(model.state_dict())
    normalized = np.stack(
        [
            normalize_window_zscore(row, epsilon=NORMALIZATION_EPSILON)
            for row in population.waveforms
        ]
    ).astype(np.float32)
    outputs: list[np.ndarray] = []
    model.eval()
    with torch.inference_mode():
        for start in range(0, normalized.shape[0], batch_size):
            tensor = torch.from_numpy(normalized[start : start + batch_size, None, :])
            outputs.append(model(tensor).cpu().numpy()[:, 0])
    after = model.state_dict()
    if any(not torch.equal(before[key], after[key]) for key in before):
        raise CalibrationError("MODEL_V2_FINAL_STATE_MUTATED_DURING_CALIBRATION")
    logits = np.concatenate(outputs).astype(np.float64)
    if not np.all(np.isfinite(logits)):
        raise CalibrationError("CALIBRATION_NONFINITE_LOGITS")
    return logits


__all__ = [
    "CALIBRATION_DOMAIN",
    "CALIBRATION_ID",
    "FIT_PARTITION",
    "ROOT",
    "TASK_ID",
    "CalibrationError",
    "CalibrationPopulation",
    "apply_operating_threshold",
    "apply_temperature",
    "binary_nll",
    "brier_score",
    "extract_frozen_logits_v2",
    "fit_temperature",
    "load_calibration_population_v2",
    "raw_probability_from_logit",
    "reliability_bins",
    "reliability_svg",
    "select_f1_threshold",
    "source_domain_calibrated_probability",
]
