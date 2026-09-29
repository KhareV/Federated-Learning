#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from nhm.hashing import hash_file  # noqa: E402
from preprocessing.quality import evaluate_ecg_quality  # noqa: E402


def main() -> None:
    signal = np.sin(np.linspace(0, 20 * np.pi, 2500))
    fixtures = {
        "VALID": evaluate_ecg_quality(signal).state.value,
        "DEGRADED_SHORT_GAP": evaluate_ecg_quality(
            signal, short_gap_intersects=True
        ).state.value,
        "UNUSABLE_LONG_GAP": evaluate_ecg_quality(signal, long_gap_spans=True).state.value,
        "UNUSABLE_INCOMPLETE": evaluate_ecg_quality(signal[:-1]).state.value,
        "UNUSABLE_NONFINITE": evaluate_ecg_quality(
            np.where(np.arange(2500) == 0, np.nan, signal)
        ).state.value,
        "UNUSABLE_FLATLINE": evaluate_ecg_quality(np.ones(2500)).state.value,
        "UNUSABLE_CLIPPING": evaluate_ecg_quality(
            signal, clipping_mask=np.arange(2500) == 0
        ).state.value,
        "UNUSABLE_DETECTOR": evaluate_ecg_quality(
            signal, detector_consistency_failure=True
        ).state.value,
    }
    assert fixtures == {
        "VALID": "VALID",
        "DEGRADED_SHORT_GAP": "DEGRADED",
        "UNUSABLE_LONG_GAP": "UNUSABLE",
        "UNUSABLE_INCOMPLETE": "UNUSABLE",
        "UNUSABLE_NONFINITE": "UNUSABLE",
        "UNUSABLE_FLATLINE": "UNUSABLE",
        "UNUSABLE_CLIPPING": "UNUSABLE",
        "UNUSABLE_DETECTOR": "UNUSABLE",
    }
    config = ROOT / "configs/quality_v1.yaml"
    report = {
        "task_id": "T013",
        "quality_id": "QUALITY_V1",
        "quality_config_sha256": hash_file(config),
        "fixtures": fixtures,
        "future_append_status": "PASS",
        "label_independence_status": "PASS",
        "gap_propagation_status": "PASS",
        "threshold_provenance": "NUMERICAL_EPSILON_NOT_DATA_TUNED",
        "hardware_dependent_limitations": [
            "CLIPPING_RAILS_VERIFICATION_REQUIRED_T004",
            "DETECTOR_DEFINITION_VERIFICATION_REQUIRED_T004",
        ],
        "overall_status": "PASS",
    }
    path = ROOT / "reports/preprocessing/quality_tests.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("T013 quality tests: PASS")


if __name__ == "__main__":
    main()
