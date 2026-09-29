"""Generic stateful causal SOS bandpass filter -- shared base for the ECG/PPG filter wrappers
in preprocessing/ecg.py and preprocessing/ppg.py.

Loads committed, versioned, hash-verified SOS coefficient artifacts (never designs a filter
at runtime -- see scripts/design_filters_t012.py). Production filtering uses
scipy.signal.sosfilt with explicit retained state (`zi`); scipy.signal.filtfilt and
scipy.signal.sosfiltfilt are forbidden anywhere in this module or its callers (statically
audited by tests/test_ecg_filter.py / tests/test_ppg_filter.py).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import scipy.signal as sig

from nhm.hashing import hash_bytes

COEFFICIENT_DIR = Path(__file__).resolve().parent / "coefficients"
PREPROC_ID = "PREPROC_V1"
STATE_INITIALIZATION = "ZERO_SOS_STATE_AT_SEGMENT_START"


@dataclass(frozen=True)
class FilterSpec:
    filter_id: str
    signal: str
    fs_hz: float
    band_hz: tuple[float, float]
    butterworth_prototype_order: int
    total_order: int
    sos: np.ndarray
    coefficient_sha256: str
    preproc_id: str = PREPROC_ID
    state_initialization: str = STATE_INITIALIZATION

    @property
    def sos_sections(self) -> int:
        return int(self.sos.shape[0])


def load_filter_spec(filter_id: str, coefficient_dir: Path = COEFFICIENT_DIR) -> FilterSpec:
    """Load a committed SOS coefficient artifact and verify its hash against the manifest --
    never regenerates or redesigns at load time."""
    manifest = json.loads((coefficient_dir / "manifest.json").read_text(encoding="utf-8"))
    entries = manifest.get("filters", {}).get("entries", {})
    if filter_id not in entries:
        raise KeyError(f"unknown filter_id {filter_id!r}; not in coefficient manifest")
    entry = entries[filter_id]

    coefficient_path = coefficient_dir / f"{filter_id}.npy"
    coefficient_bytes = coefficient_path.read_bytes()
    actual_hash = hash_bytes(coefficient_bytes)
    if actual_hash != entry["coefficient_sha256"]:
        raise ValueError(
            f"COEFFICIENT_HASH_MISMATCH: {filter_id} manifest expected "
            f"{entry['coefficient_sha256']}, recomputed {actual_hash}"
        )

    sos = np.load(coefficient_path, allow_pickle=False)
    if sos.dtype != np.float64:
        raise ValueError(f"{filter_id}: expected float64 SOS coefficients, got {sos.dtype}")
    sos = sos.copy()
    sos.flags.writeable = False

    return FilterSpec(
        filter_id=filter_id,
        signal=entry["signal"],
        fs_hz=entry["fs_hz"],
        band_hz=tuple(entry["band_hz"]),
        butterworth_prototype_order=entry["butterworth_prototype_order"],
        total_order=entry["total_order"],
        sos=sos,
        coefficient_sha256=actual_hash,
    )


class StatefulSOSFilter:
    """Bounded-memory causal streaming SOS filter for one FilterSpec. `process()` may be
    called with any chunk size any number of times; results are identical to a single call
    over the concatenated input (chunk equivalence) and earlier outputs never change based on
    later input (future-append causality) -- both properties inherited directly from
    scipy.signal.sosfilt's own chunk-additive `zi` state, which this class manages
    explicitly rather than leaving implicit."""

    def __init__(self, spec: FilterSpec) -> None:
        self.spec = spec
        # scipy.signal.sosfilt requires a writable `sos` buffer (it uses it as internal
        # scratch space); spec.sos is intentionally read-only so it is safe to share across
        # instances, so each filter keeps its own private writable copy here.
        self._sos = np.array(spec.sos, dtype=np.float64, copy=True)
        self._segment_id = 0
        self._samples_seen = 0
        self._zi = self._zero_state()

    def _zero_state(self) -> np.ndarray:
        """True zero initial conditions -- not scipy's `sosfilt_zi` steady-state-for-a-step
        initial conditions, which would inject non-causal knowledge of a future constant
        input. Shape matches `sosfilt`'s own `zi` convention: (n_sections, 2)."""
        return np.zeros((self.spec.sos.shape[0], 2), dtype=np.float64)

    def reset(self, *, segment_id: int | None = None) -> None:
        """Reinitialize to zero SOS state at a fresh segment start (T012's GAP_POLICY_V1
        calls this after a long gap; no pre-gap filter history may leak across)."""
        self._zi = self._zero_state()
        self._samples_seen = 0
        self._segment_id = segment_id if segment_id is not None else self._segment_id + 1

    def process(self, samples: np.ndarray) -> np.ndarray:
        samples = np.asarray(samples, dtype=np.float64)
        if samples.ndim != 1:
            raise ValueError("samples must be 1-D")
        if samples.size == 0:
            return samples
        if not np.all(np.isfinite(samples)):
            raise ValueError("NONFINITE_FILTER_INPUT: samples must be finite")
        filtered, self._zi = sig.sosfilt(self._sos, samples, zi=self._zi)
        self._samples_seen += samples.size
        return filtered

    def state_metadata(self) -> dict[str, Any]:
        return {
            "filter_id": self.spec.filter_id,
            "preproc_id": self.spec.preproc_id,
            "sample_rate_hz": self.spec.fs_hz,
            "filter_band_hz": list(self.spec.band_hz),
            "prototype_order": self.spec.butterworth_prototype_order,
            "sos_sha256": self.spec.coefficient_sha256,
            "samples_seen": self._samples_seen,
            "segment_id": self._segment_id,
            "state_initialization": self.spec.state_initialization,
            "sos_section_count": self.spec.sos_sections,
        }
