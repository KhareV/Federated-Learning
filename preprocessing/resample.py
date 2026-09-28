"""Stateful causal rational/polyphase FIR resampler -- PREPROC_V1_RESAMPLER_V1.

No sample output at timestamp t may depend on an input sample acquired after t. This module
implements a bounded-memory streaming polyphase filter; it never calls a centered/offline
convenience resampler (scipy.signal.resample / resample_poly / filtfilt / sosfiltfilt are all
forbidden here -- see tests/test_resampler_forbidden_apis.py for the static audit) and never
buffers more history than its own FIR support requires.

Coefficients are loaded from the committed, versioned artifacts under
preprocessing/coefficients/ (scripts/design_resampler_t011.py generates them); this module
never designs a filter at runtime and never tunes coefficients against any data.

Owns: resampling only. Gap repair/reset policy is T012's job (this module only exposes
`reset()` for T012 to call after a long gap); causal ECG/PPG bandpass filtering, quality,
windowing, and normalization are all out of scope here.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from nhm.hashing import hash_bytes

COEFFICIENT_DIR = Path(__file__).resolve().parent / "coefficients"
PREPROC_ID = "PREPROC_V1"
TIMESTAMP_MAPPING_ID = "CAUSAL_OUTPUT_GRID_V1"
STATE_INITIALIZATION = "ZERO_FIR_HISTORY_AT_SEGMENT_START"
TAIL_POLICY = "NO_FUTURE_ZERO_PADDING"
GAP_HANDLING = "DEFERRED_T012"


class NoncontiguousSourceInputError(ValueError):
    """NONCONTIGUOUS_SOURCE_INPUT: a process() call's source_start_index does not exactly
    continue the previously processed source stream. T011 never silently bridges a gap;
    T012 decides how/whether to repair or reset around one."""


@dataclass(frozen=True)
class ResamplerSpec:
    resampler_id: str
    input_rate_hz: int
    output_rate_hz: int
    up: int
    down: int
    coefficients: np.ndarray
    coefficient_sha256: str
    design_id: str
    group_delay_output_samples: int
    group_delay_seconds: float
    startup_transient_output_span: int
    preproc_id: str = PREPROC_ID
    timestamp_mapping_id: str = TIMESTAMP_MAPPING_ID

    @property
    def num_taps(self) -> int:
        return int(self.coefficients.shape[0])


def load_resampler_spec(
    resampler_id: str, coefficient_dir: Path = COEFFICIENT_DIR
) -> ResamplerSpec:
    """Load a committed coefficient artifact and verify its hash against the recorded
    manifest entry -- never regenerates or redesigns at load time."""
    manifest = json.loads((coefficient_dir / "manifest.json").read_text(encoding="utf-8"))
    if resampler_id not in manifest["conversions"]:
        raise KeyError(f"unknown resampler_id {resampler_id!r}; not in coefficient manifest")
    entry = manifest["conversions"][resampler_id]

    coefficient_path = coefficient_dir / f"{resampler_id}.npy"
    coefficient_bytes = coefficient_path.read_bytes()
    actual_hash = hash_bytes(coefficient_bytes)
    if actual_hash != entry["coefficient_sha256"]:
        raise ValueError(
            f"COEFFICIENT_HASH_MISMATCH: {resampler_id} manifest expected "
            f"{entry['coefficient_sha256']}, recomputed {actual_hash}"
        )

    coefficients = np.load(coefficient_path, allow_pickle=False)
    if coefficients.dtype != np.float64:
        raise ValueError(
            f"{resampler_id}: expected float64 coefficients, got {coefficients.dtype}"
        )
    coefficients = coefficients.copy()
    coefficients.flags.writeable = False

    return ResamplerSpec(
        resampler_id=resampler_id,
        input_rate_hz=entry["input_rate_hz"],
        output_rate_hz=entry["output_rate_hz"],
        up=entry["up"],
        down=entry["down"],
        coefficients=coefficients,
        coefficient_sha256=actual_hash,
        design_id=entry["design_id"],
        group_delay_output_samples=entry["group_delay_output_samples"],
        group_delay_seconds=entry["group_delay_seconds"],
        startup_transient_output_span=entry["startup_transient_output_span"],
    )


def _polyphase_components(coefficients: np.ndarray, up: int) -> list[np.ndarray]:
    """phases[p][i] = h[p + i*up]; multiplies x[n_max(m) - i] for an output with phase p."""
    return [np.ascontiguousarray(coefficients[p::up]) for p in range(up)]


@dataclass(frozen=True)
class ResampledChunk:
    output_indices: np.ndarray
    values: np.ndarray
    output_time_seconds: np.ndarray
    timestamps_us: np.ndarray | None


class StatefulRationalResampler:
    """Bounded-memory causal streaming rational resampler for one ResamplerSpec.

    `process()` may be called with any chunk size, any number of times, and must produce
    results identical to a single call over the concatenated input (chunk equivalence) and
    identical earlier outputs regardless of what is appended later (future-append causality).
    """

    def __init__(
        self, spec: ResamplerSpec, *, segment_start_timestamp_us: int | None = None
    ) -> None:
        self.spec = spec
        self._phases = _polyphase_components(spec.coefficients, spec.up)
        self._history_length = max(len(phase) for phase in self._phases)
        self._segment_start_timestamp_us = segment_start_timestamp_us
        self._reset_state()

    def _reset_state(self) -> None:
        self._history = np.zeros(self._history_length, dtype=np.float64)
        self._origin_source_index: int | None = None
        self._next_expected_source_index: int | None = None
        self._latest_source_index: int | None = None
        self._next_output_index = 0
        self._input_samples_seen = 0

    def reset(self, *, segment_start_timestamp_us: int | None = None) -> None:
        """Reinitialize to a fresh segment: zero FIR history, output index back to 0. For
        T012's long-gap handling -- T011 does not decide when a reset is warranted."""
        self._reset_state()
        self._segment_start_timestamp_us = segment_start_timestamp_us

    def process(
        self, samples: Sequence[float] | np.ndarray, source_start_index: int
    ) -> ResampledChunk:
        samples_array = np.asarray(samples, dtype=np.float64)
        if samples_array.ndim != 1:
            raise ValueError("samples must be 1-D")
        if samples_array.size and not np.all(np.isfinite(samples_array)):
            raise ValueError("NONFINITE_SOURCE_SAMPLE: samples must be finite")

        if self._origin_source_index is None:
            self._origin_source_index = source_start_index
            self._next_expected_source_index = source_start_index

        if source_start_index != self._next_expected_source_index:
            raise NoncontiguousSourceInputError(
                "NONCONTIGUOUS_SOURCE_INPUT: expected source_start_index="
                f"{self._next_expected_source_index}, got {source_start_index}"
            )

        up = self.spec.up
        down = self.spec.down
        output_indices: list[int] = []
        output_values: list[float] = []

        for offset in range(samples_array.size):
            self._history[:-1] = self._history[1:]
            self._history[-1] = samples_array[offset]
            self._latest_source_index = source_start_index + offset
            reversed_recent = self._history[::-1]

            while self._next_output_index * down < (self._latest_source_index + 1) * up:
                m = self._next_output_index
                phase = m * down % up
                taps = self._phases[phase]
                value = float(np.dot(taps, reversed_recent[: len(taps)]))
                output_indices.append(m)
                output_values.append(value)
                self._next_output_index += 1

        self._next_expected_source_index = source_start_index + samples_array.size
        self._input_samples_seen += samples_array.size

        indices_array = np.asarray(output_indices, dtype=np.int64)
        values_array = np.asarray(output_values, dtype=np.float64)
        output_time_seconds = indices_array.astype(np.float64) / self.spec.output_rate_hz

        timestamps_us = None
        if self._segment_start_timestamp_us is not None:
            period_us = round(1_000_000 / self.spec.output_rate_hz)
            timestamps_us = self._segment_start_timestamp_us + indices_array * period_us

        return ResampledChunk(
            output_indices=indices_array,
            values=values_array,
            output_time_seconds=output_time_seconds,
            timestamps_us=timestamps_us,
        )

    def state_metadata(self) -> dict[str, Any]:
        next_phase = (self._next_output_index * self.spec.down) % self.spec.up
        return {
            "resampler_id": self.spec.resampler_id,
            "preproc_id": self.spec.preproc_id,
            "input_rate_hz": self.spec.input_rate_hz,
            "output_rate_hz": self.spec.output_rate_hz,
            "up": self.spec.up,
            "down": self.spec.down,
            "coefficient_sha256": self.spec.coefficient_sha256,
            "group_delay_seconds": self.spec.group_delay_seconds,
            "group_delay_output_samples": self.spec.group_delay_output_samples,
            "input_samples_seen": self._input_samples_seen,
            "next_expected_source_index": self._next_expected_source_index,
            "output_samples_emitted": self._next_output_index,
            "next_output_index": self._next_output_index,
            "next_output_phase": next_phase,
            "retained_history_length": self._history_length,
            "state_initialization": STATE_INITIALIZATION,
            "timestamp_mapping_id": self.spec.timestamp_mapping_id,
            "tail_policy": TAIL_POLICY,
            "gap_handling": GAP_HANDLING,
        }


def expected_output_count(n_samples: int, up: int, down: int) -> int:
    """Number of causal outputs available from a continuous prefix of `n_samples` source
    samples starting at index 0, with no future tail padding.

    Derived directly from the causal availability rule (T011 Section 10): output m is valid
    iff floor(m*down/up) <= n_samples - 1, i.e. m*down < n_samples*up, i.e.
    m < n_samples*up/down. The largest valid m is therefore ceil(n_samples*up/down) - 1, and
    the count is ceil(n_samples*up/down).

    Note: the count formula given in the T011 execution instructions ("floor((N-1)*up/down)
    + 1") is off by one for many (N, up, down) -- verified by exhaustive brute-force
    comparison against the literal inequality above for N up to several thousand for both
    required ratios. The ceiling form here is the one that actually matches that inequality
    and the streaming implementation's real output count; it is what this module tests
    against.
    """
    if n_samples <= 0:
        return 0
    return (n_samples * up + down - 1) // down
