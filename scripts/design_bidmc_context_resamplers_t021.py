#!/usr/bin/env python3
"""Generate deterministic BIDMC_CONTEXT_V1 FIR coefficient artifacts."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import scipy
from scipy.signal import firwin

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from nhm.hashing import hash_bytes  # noqa: E402

OUTPUT = ROOT / "preprocessing/context_coefficients"
DESIGN_ID = "FIR_KAISER_POLYPHASE_V1"
CONVERSIONS = {
    "BIDMC_PPG_125_TO_100_V1": (125, 100),
    "BIDMC_ECG_HR_125_TO_250_V1": (125, 250),
}


def design(up: int, down: int) -> np.ndarray:
    maximum = max(up, down)
    half_len = 10 * maximum
    return (firwin(2 * half_len + 1, 1 / maximum, window=("kaiser", 5.0)) * up).astype(np.float64)


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    entries = {}
    for identifier, (source, target) in CONVERSIONS.items():
        divisor = math.gcd(source, target)
        up, down = target // divisor, source // divisor
        coefficients = design(up, down)
        path = OUTPUT / f"{identifier}.npy"
        np.save(path, coefficients, allow_pickle=False)
        half_len = (coefficients.size - 1) // 2
        entries[identifier] = {
            "input_rate_hz": source,
            "output_rate_hz": target,
            "up": up,
            "down": down,
            "num_taps": int(coefficients.size),
            "half_len": half_len,
            "design_id": DESIGN_ID,
            "kaiser_beta": 5.0,
            "dtype": "float64",
            "coefficient_sha256": hash_bytes(path.read_bytes()),
            "group_delay_output_samples": half_len // down,
            "group_delay_seconds": half_len / (source * up),
            "startup_transient_output_span": (coefficients.size - 1) // down,
        }
    manifest = {
        "context_contract_id": "BIDMC_CONTEXT_V1",
        "design_id": DESIGN_ID,
        "numpy_version": np.__version__,
        "scipy_version": scipy.__version__,
        "conversions": entries,
    }
    (OUTPUT / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print("BIDMC context resampler coefficients: PASS")


if __name__ == "__main__":
    main()
