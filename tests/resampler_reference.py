"""Slow, direct causal rational-FIR reference implementation -- test-only ground truth.

Implements y[m] = sum_n x[n] * h[m*down - n*up] directly (not the polyphase decomposition
used by the production streaming implementation), treating any source index outside the
supplied array as absent (zero contribution), never as a future sample. Used only to
cross-check preprocessing.resample.StatefulRationalResampler; never imported by production
code (see tests/test_resampler_forbidden_apis.py, which also checks this module is not
imported from preprocessing/).
"""

from __future__ import annotations

import numpy as np


def direct_causal_reference(
    x: np.ndarray, up: int, down: int, h: np.ndarray, num_outputs: int
) -> np.ndarray:
    n_samples = len(x)
    num_taps = len(h)
    outputs = np.zeros(num_outputs, dtype=np.float64)
    for m in range(num_outputs):
        total = 0.0
        base = m * down
        for k in range(num_taps):
            j = base - k
            if j < 0 or j % up != 0:
                continue
            n = j // up
            if 0 <= n < n_samples:
                total += x[n] * h[k]
        outputs[m] = total
    return outputs
