from __future__ import annotations

import numpy as np

from federated.feature_noise import mix_noise, noise_offset


def test_snr_formula_and_deterministic_offset() -> None:
    clean = np.linspace(-1, 1, 2500)
    noise = np.cos(np.linspace(0, 20, 2500))
    for target in (24, 18, 12, 6, 0, -6):
        noisy, achieved = mix_noise(clean, noise, target)
        assert noisy.shape == clean.shape
        assert abs(achieved - target) <= 1e-12
    assert noise_offset("SITE_00", "example", "bw", 10000) == noise_offset(
        "SITE_00", "example", "bw", 10000
    )


def test_noise_does_not_touch_labels_or_counts() -> None:
    labels = np.array([0, 1, 1])
    copy = labels.copy()
    mix_noise(np.ones(2500), np.linspace(1, 2, 2500), 6)
    assert np.array_equal(labels, copy)
