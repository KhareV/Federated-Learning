"""Context-only causal BIDMC resampler specifications; PREPROC_V1 remains immutable."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from nhm.hashing import hash_bytes
from preprocessing.resample import ResamplerSpec, StatefulRationalResampler

CONTEXT_ID = "BIDMC_CONTEXT_V1"
COEFFICIENT_DIR = Path(__file__).resolve().parent / "context_coefficients"
MANIFEST_PATH = COEFFICIENT_DIR / "manifest.json"


def load_context_resampler_spec(resampler_id: str) -> ResamplerSpec:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if manifest["context_contract_id"] != CONTEXT_ID:
        raise ValueError("CONTEXT_CONTRACT_ID_MISMATCH")
    entry = manifest["conversions"].get(resampler_id)
    if entry is None:
        raise KeyError(f"unknown context resampler {resampler_id!r}")
    path = COEFFICIENT_DIR / f"{resampler_id}.npy"
    actual = hash_bytes(path.read_bytes())
    if actual != entry["coefficient_sha256"]:
        raise ValueError("CONTEXT_COEFFICIENT_HASH_MISMATCH")
    coefficients = np.load(path, allow_pickle=False)
    if coefficients.dtype != np.float64 or coefficients.shape != (entry["num_taps"],):
        raise ValueError("CONTEXT_COEFFICIENT_SHAPE_OR_DTYPE_MISMATCH")
    coefficients.flags.writeable = False
    return ResamplerSpec(
        resampler_id=resampler_id,
        input_rate_hz=entry["input_rate_hz"],
        output_rate_hz=entry["output_rate_hz"],
        up=entry["up"],
        down=entry["down"],
        coefficients=coefficients,
        coefficient_sha256=actual,
        design_id=entry["design_id"],
        group_delay_output_samples=entry["group_delay_output_samples"],
        group_delay_seconds=entry["group_delay_seconds"],
        startup_transient_output_span=entry["startup_transient_output_span"],
        preproc_id=CONTEXT_ID,
    )


def make_context_resampler(resampler_id: str) -> StatefulRationalResampler:
    return StatefulRationalResampler(load_context_resampler_spec(resampler_id))
