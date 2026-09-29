#!/usr/bin/env python3
"""Build deterministic TRAIN/VALIDATION BASELINE_FEATURES_V1 caches only."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from evaluation.leakage_audit import verify_frozen_split  # noqa: E402
from preprocessing.freeze import verify_preproc_freeze  # noqa: E402
from training.train_baselines import (  # noqa: E402
    _write_feature_cache,
    build_feature_population,
)


def main() -> None:
    verify_frozen_split(ROOT)
    verify_preproc_freeze(ROOT)
    train = build_feature_population("TRAIN")
    validation = build_feature_population("VALIDATION")
    _write_feature_cache((train, validation))
    print(
        "BASELINE_FEATURES_V1: PASS "
        f"(TRAIN={train.labels.size}, VALIDATION={validation.labels.size})"
    )


if __name__ == "__main__":
    main()
