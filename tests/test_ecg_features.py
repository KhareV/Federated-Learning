from __future__ import annotations

import ast
from pathlib import Path

import numpy as np

from features.ecg import (
    BASELINE_FEATURE_NAMES_V1,
    extract_baseline_features,
    feature_schema_sha256,
)

ROOT = Path(__file__).resolve().parents[1]


def synthetic_peaks(spacing: int = 250, amplitude: float = 2.0) -> np.ndarray:
    signal = 0.02 * np.sin(2 * np.pi * np.arange(2500) / 250)
    signal[np.arange(100, 2500, spacing)] += amplitude
    return signal.astype(np.float64)


def test_feature_schema_order_and_determinism() -> None:
    waveform = synthetic_peaks()
    first = extract_baseline_features(waveform)
    second = extract_baseline_features(waveform)
    assert len(BASELINE_FEATURE_NAMES_V1) == 29
    assert np.array_equal(first.values, second.values, equal_nan=True)
    assert feature_schema_sha256() == feature_schema_sha256()


def test_regular_and_irregular_rr_features_change() -> None:
    regular = extract_baseline_features(synthetic_peaks()).values
    irregular_signal = synthetic_peaks()
    irregular_signal[:] = 0.0
    irregular_signal[[100, 300, 620, 850, 1220, 1500, 1900, 2300]] = 2.0
    irregular = extract_baseline_features(irregular_signal).values
    rr_std = BASELINE_FEATURE_NAMES_V1.index("rr_std_seconds")
    assert regular[rr_std] < irregular[rr_std]


def test_constant_missing_rr_is_safe_and_fixed_shape() -> None:
    result = extract_baseline_features(np.zeros(2500, dtype=np.float64))
    assert result.values.shape == (29,)
    assert result.values[BASELINE_FEATURE_NAMES_V1.index("rr_available")] == 0.0
    assert np.isnan(result.values[BASELINE_FEATURE_NAMES_V1.index("rr_mean_seconds")])


def test_amplitude_scaling_and_polarity_are_deterministic() -> None:
    waveform = synthetic_peaks()
    original = extract_baseline_features(waveform)
    inverted = extract_baseline_features(-waveform)
    scaled = extract_baseline_features(2.0 * waveform)
    peak_to_peak = BASELINE_FEATURE_NAMES_V1.index("ecg_peak_to_peak")
    assert np.array_equal(original.detected_peak_indices, inverted.detected_peak_indices)
    assert np.isclose(scaled.values[peak_to_peak], 2.0 * original.values[peak_to_peak])


def test_feature_module_has_no_label_annotation_or_quality_dependency() -> None:
    source = (ROOT / "features/ecg.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = {
        node.module or ""
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    } | {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    forbidden = ("labels", "annotation", "quality", "aami")
    assert not any(any(word in name.lower() for word in forbidden) for name in imports)
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "extract_baseline_features"
    )
    assert [argument.arg for argument in function.args.args] == ["signal", "sample_rate_hz"]
