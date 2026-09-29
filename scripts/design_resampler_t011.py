#!/usr/bin/env python3
"""T011: deterministically (re)generate the committed PREPROC_V1_RESAMPLER_V1 FIR coefficient
package for both required conversions (360->250, 257->250).

Design is fixed by rate/math requirements only (FIR_KAISER_POLYPHASE_V1, v2.2 Section 8.2 /
T011 execution instructions Section 6) -- never tuned against TRAIN/VALIDATION/INTERNAL_TEST
or INCART performance. Coefficients are committed as versioned artifacts
(preprocessing/coefficients/); production code loads them from disk, it never designs a
filter at runtime. Re-running this script must reproduce the committed coefficients exactly
(scripts/generate_t011_evidence.py's regeneration check enforces this).
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any

import numpy as np
import scipy
import scipy.signal as sig

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from nhm.hashing import hash_bytes  # noqa: E402

COEFFICIENT_DIR = ROOT / "preprocessing/coefficients"

DESIGN_ID = "FIR_KAISER_POLYPHASE_V1"
KAISER_BETA = 5.0

CONVERSIONS = {
    "MITDB_360_TO_250_V1": {"input_rate_hz": 360, "output_rate_hz": 250},
    "INCART_257_TO_250_V1": {"input_rate_hz": 257, "output_rate_hz": 250},
}


def _reduced_ratio(input_rate_hz: int, output_rate_hz: int) -> tuple[int, int]:
    divisor = math.gcd(input_rate_hz, output_rate_hz)
    return output_rate_hz // divisor, input_rate_hz // divisor


def design_coefficients(up: int, down: int) -> np.ndarray:
    """FIR_KAISER_POLYPHASE_V1: fixed deterministic design, not tuned on any data."""
    max_rate = max(up, down)
    half_len = 10 * max_rate
    num_taps = 2 * half_len + 1
    normalized_cutoff = 1.0 / max_rate
    coefficients = sig.firwin(num_taps, normalized_cutoff, window=("kaiser", KAISER_BETA))
    coefficients = (coefficients * up).astype(np.float64)
    return coefficients


def build_manifest() -> dict[str, Any]:
    conversions: dict[str, Any] = {}
    for resampler_id, rates in CONVERSIONS.items():
        up, down = _reduced_ratio(rates["input_rate_hz"], rates["output_rate_hz"])
        coefficients = design_coefficients(up, down)
        num_taps = len(coefficients)
        max_rate = max(up, down)
        half_len = 10 * max_rate
        assert num_taps == 2 * half_len + 1
        assert half_len % down == 0, f"{resampler_id}: half_len not divisible by down"
        group_delay_output_samples = half_len // down
        assert (num_taps - 1) % down == 0, f"{resampler_id}: startup span not exact"
        startup_transient_output_span = (num_taps - 1) // down

        coefficient_path = COEFFICIENT_DIR / f"{resampler_id}.npy"
        COEFFICIENT_DIR.mkdir(parents=True, exist_ok=True)
        np.save(coefficient_path, coefficients, allow_pickle=False)
        coefficient_bytes = coefficient_path.read_bytes()

        conversions[resampler_id] = {
            "input_rate_hz": rates["input_rate_hz"],
            "output_rate_hz": rates["output_rate_hz"],
            "up": up,
            "down": down,
            "num_taps": num_taps,
            "half_len": half_len,
            "design_id": DESIGN_ID,
            "window": "kaiser",
            "kaiser_beta": KAISER_BETA,
            "dtype": "float64",
            "dc_scaling": "up",
            "coefficient_path": str(coefficient_path.relative_to(ROOT)),
            "coefficient_sha256": hash_bytes(coefficient_bytes),
            "group_delay_output_samples": group_delay_output_samples,
            "group_delay_seconds": group_delay_output_samples / rates["output_rate_hz"],
            "startup_transient_output_span": startup_transient_output_span,
        }

    return {
        "preproc_id": "PREPROC_V1",
        "resampler_id": "PREPROC_V1_RESAMPLER_V1",
        "design_id": DESIGN_ID,
        "scipy_version": scipy.__version__,
        "numpy_version": np.__version__,
        "conversions": conversions,
    }


def main() -> None:
    manifest = build_manifest()
    output_path = COEFFICIENT_DIR / "manifest.json"
    if output_path.exists():
        # Preserve sibling top-level keys this script does not own (e.g. T012's "filters"
        # entry) -- this script only ever overwrites the resampler-owned keys it just built.
        existing = json.loads(output_path.read_text(encoding="utf-8"))
        for key, value in existing.items():
            manifest.setdefault(key, value)
    temporary = output_path.with_suffix(f"{output_path.suffix}.tmp")
    temporary.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(output_path)
    print(f"resampler coefficients designed: {list(manifest['conversions'])}")


if __name__ == "__main__":
    main()
