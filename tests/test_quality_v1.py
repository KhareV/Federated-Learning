from __future__ import annotations

import ast
from pathlib import Path

import numpy as np

from preprocessing.quality import QualityReason, QualityState, evaluate_ecg_quality, is_flatline

ROOT = Path(__file__).resolve().parents[1]


def clean_signal() -> np.ndarray:
    return np.sin(np.linspace(0.0, 20.0 * np.pi, 2500))


def test_quality_precedence_and_required_states() -> None:
    clean = clean_signal()
    assert evaluate_ecg_quality(clean).state == QualityState.VALID
    short = evaluate_ecg_quality(clean, short_gap_intersects=True)
    assert short.state == QualityState.DEGRADED
    assert QualityReason.SHORT_GAP_FILL in short.reasons

    cases = [
        evaluate_ecg_quality(clean[:-1]),
        evaluate_ecg_quality(np.where(np.arange(2500) == 4, np.nan, clean)),
        evaluate_ecg_quality(np.ones(2500)),
        evaluate_ecg_quality(clean, long_gap_spans=True),
        evaluate_ecg_quality(clean, clipping_mask=np.arange(2500) == 7),
        evaluate_ecg_quality(clean, detector_consistency_failure=True),
    ]
    assert all(result.state == QualityState.UNUSABLE for result in cases)
    both = evaluate_ecg_quality(clean, short_gap_intersects=True, long_gap_spans=True)
    assert both.state == QualityState.UNUSABLE
    assert set(both.reasons) == {QualityReason.LONG_GAP_SPAN, QualityReason.SHORT_GAP_FILL}


def test_flatline_check_is_scale_safe_for_near_constant_signal() -> None:
    tiny_variation = np.linspace(-1e-14, 1e-14, 2500)
    signal = 2.0 + tiny_variation
    assert is_flatline(signal)
    assert is_flatline(signal * 1e6)


def test_quality_is_future_invariant_and_has_no_label_dependency() -> None:
    prefix = clean_signal()
    before = evaluate_ecg_quality(prefix)
    session = np.concatenate([prefix, np.full(500, np.nan)])
    after = evaluate_ecg_quality(session[:2500])
    assert before == after
    source = (ROOT / "preprocessing/quality.py").read_text(encoding="utf-8")
    imports = {
        node.module
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.ImportFrom)
    }
    assert "datasets.labels" not in imports
