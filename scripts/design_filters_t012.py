#!/usr/bin/env python3
"""T012: deterministically (re)generate the committed PREPROC_V1 ECG/PPG causal SOS bandpass
filter coefficient packages.

Design is fixed by the locked v2.2 physiological bandpass convention only -- never tuned
against TRAIN/VALIDATION/INTERNAL_TEST/INCART/NSTDB results. Coefficients are committed as
versioned artifacts (preprocessing/coefficients/); production code loads them from disk, it
never designs a filter at runtime.

ECG: 4th-order Butterworth, 0.5-40 Hz, fs=250 Hz.
PPG: 4th-order Butterworth, 0.5-8 Hz, fs=100 Hz.
Both are bandpass, so the resulting digital transfer function has total order 8 (2x the
Butterworth prototype order) -- recorded explicitly as both `butterworth_prototype_order` and
`sos_sections`/`total_order` to avoid an apparent 4-vs-8 contradiction in provenance.
"""

from __future__ import annotations

import json
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
MANIFEST_PATH = COEFFICIENT_DIR / "manifest.json"

BUTTERWORTH_PROTOTYPE_ORDER = 4

FILTERS = {
    "PREPROC_V1_ECG_FILTER_V1": {
        "signal": "ECG",
        "fs_hz": 250.0,
        "band_hz": (0.5, 40.0),
    },
    "PREPROC_V1_PPG_FILTER_V1": {
        "signal": "PPG",
        "fs_hz": 100.0,
        "band_hz": (0.5, 8.0),
    },
}


def design_sos(fs_hz: float, band_hz: tuple[float, float]) -> np.ndarray:
    """Fixed deterministic design: N=4 Butterworth bandpass, SOS form. Not tuned on data."""
    sos = sig.butter(
        N=BUTTERWORTH_PROTOTYPE_ORDER, Wn=band_hz, btype="bandpass", fs=fs_hz, output="sos"
    )
    return sos.astype(np.float64)


def build_filter_entries() -> dict[str, Any]:
    entries: dict[str, Any] = {}
    for filter_id, params in FILTERS.items():
        sos = design_sos(params["fs_hz"], params["band_hz"])
        _, poles, _ = sig.sos2zpk(sos)
        max_pole_magnitude = float(np.max(np.abs(poles))) if len(poles) else 0.0

        coefficient_path = COEFFICIENT_DIR / f"{filter_id}.npy"
        COEFFICIENT_DIR.mkdir(parents=True, exist_ok=True)
        np.save(coefficient_path, sos, allow_pickle=False)
        coefficient_bytes = coefficient_path.read_bytes()

        entries[filter_id] = {
            "signal": params["signal"],
            "fs_hz": params["fs_hz"],
            "band_hz": list(params["band_hz"]),
            "filter_type": "butterworth_bandpass",
            "butterworth_prototype_order": BUTTERWORTH_PROTOTYPE_ORDER,
            "total_order": 2 * BUTTERWORTH_PROTOTYPE_ORDER,
            "design_api": 'scipy.signal.butter(..., output="sos")',
            "form": "SOS",
            "sos_sections": int(sos.shape[0]),
            "sos_shape": list(sos.shape),
            "dtype": "float64",
            "coefficient_path": str(coefficient_path.relative_to(ROOT)),
            "coefficient_sha256": hash_bytes(coefficient_bytes),
            "max_pole_magnitude": max_pole_magnitude,
            "stable": max_pole_magnitude < 1.0,
            "state_initialization": "ZERO_SOS_STATE_AT_SEGMENT_START",
            "implementation": "STATEFUL_CAUSAL_SOSFILT",
        }
    return entries


def main() -> None:
    filters = build_filter_entries()
    for filter_id, entry in filters.items():
        if not entry["stable"]:
            raise RuntimeError(f"PREPROCESSING_CAUSALITY_FAILURE: {filter_id} is unstable")

    if MANIFEST_PATH.exists():
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    else:
        manifest = {}
    manifest["filters"] = {
        "scipy_version": scipy.__version__,
        "numpy_version": np.__version__,
        "entries": filters,
    }
    temporary = MANIFEST_PATH.with_suffix(f"{MANIFEST_PATH.suffix}.tmp")
    temporary.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(MANIFEST_PATH)
    print(f"filters designed: {list(filters)}")


if __name__ == "__main__":
    main()
