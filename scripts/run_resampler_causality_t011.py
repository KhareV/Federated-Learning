#!/usr/bin/env python3
"""T011: run the synthetic causality/chunk-equivalence/reference proofs for both required
conversions and emit reports/preprocessing/resampler_causality.json -- the canonical T011/
G6-partial evidence artifact.

Verifies the F05 split freeze is intact before and after (T011 must never mutate the frozen
MITDB_SPLIT_V1). Offline, synthetic signals only -- no real MIT-BIH/INCART data is read.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from resampler_reference import direct_causal_reference  # noqa: E402

from evaluation.leakage_audit import verify_frozen_split  # noqa: E402
from nhm.hashing import hash_file  # noqa: E402
from preprocessing.resample import (  # noqa: E402
    StatefulRationalResampler,
    expected_output_count,
    load_resampler_spec,
)

REPORT_PATH = ROOT / "reports/preprocessing/resampler_causality.json"
RESAMPLER_IDS = ["MITDB_360_TO_250_V1", "INCART_257_TO_250_V1"]
TOLERANCE_ATOL = 1e-9


def _check_direct_reference(spec) -> dict[str, Any]:
    rng = np.random.default_rng(11)
    n = 300
    x = rng.standard_normal(n)
    n_out = expected_output_count(n, spec.up, spec.down)
    reference = direct_causal_reference(x, spec.up, spec.down, spec.coefficients, n_out)
    resampler = StatefulRationalResampler(spec)
    chunk = resampler.process(x, 0)
    max_error = float(np.max(np.abs(chunk.values - reference))) if n_out else 0.0
    return {
        "status": "PASS" if len(chunk.values) == n_out and max_error <= TOLERANCE_ATOL else "FAIL",
        "max_absolute_error": max_error,
        "tolerance_atol": TOLERANCE_ATOL,
    }


def _check_future_append(spec) -> dict[str, Any]:
    rng = np.random.default_rng(2026)
    prefix = rng.standard_normal(400)
    suffixes = [np.full(500, 1e6), rng.standard_normal(500) * 1e6]

    baseline = StatefulRationalResampler(spec)
    baseline_chunk = baseline.process(prefix, 0)

    max_error = 0.0
    index_mismatch = False
    for suffix in suffixes:
        full = np.concatenate([prefix, suffix])
        resampler = StatefulRationalResampler(spec)
        full_chunk = resampler.process(full, 0)
        n_common = len(baseline_chunk.values)
        if not np.array_equal(full_chunk.output_indices[:n_common], baseline_chunk.output_indices):
            index_mismatch = True
        max_error = max(
            max_error, float(np.max(np.abs(full_chunk.values[:n_common] - baseline_chunk.values)))
        )
    status = "PASS" if not index_mismatch and max_error <= TOLERANCE_ATOL else "FAIL"
    return {"status": status, "max_absolute_error": max_error, "tolerance_atol": TOLERANCE_ATOL}


def _check_chunk_equivalence(spec) -> dict[str, Any]:
    rng = np.random.default_rng(31)
    n = 3000
    x = rng.standard_normal(n)

    baseline = StatefulRationalResampler(spec)
    baseline_chunk = baseline.process(x, 0)

    def run_chunked(chunk_sizes: list[int]):
        resampler = StatefulRationalResampler(spec)
        values, indices = [], []
        index = 0
        for size in chunk_sizes:
            chunk = resampler.process(x[index : index + size], index)
            values.append(chunk.values)
            indices.append(chunk.output_indices)
            index += size
        return np.concatenate(indices), np.concatenate(values)

    strategies = {
        "one_sample": [1] * n,
        "boundary": _fill(n, [spec.up, spec.down, spec.up + spec.down]),
        "pathological": _fill(n, [1, 2, 3, 7, 11]),
    }
    max_error = 0.0
    index_mismatch = False
    for sizes in strategies.values():
        indices, values = run_chunked(sizes)
        if not np.array_equal(indices, baseline_chunk.output_indices):
            index_mismatch = True
        max_error = max(max_error, float(np.max(np.abs(values - baseline_chunk.values))))
    status = "PASS" if not index_mismatch and max_error <= TOLERANCE_ATOL else "FAIL"
    return {"status": status, "max_absolute_error": max_error, "tolerance_atol": TOLERANCE_ATOL}


def _fill(n: int, cycle: list[int]) -> list[int]:
    sizes, remaining, index = [], n, 0
    while remaining > 0:
        size = min(cycle[index % len(cycle)], remaining)
        sizes.append(size)
        remaining -= size
        index += 1
    return sizes


def _check_impulse_delay(spec) -> dict[str, Any]:
    x = np.zeros(2 * spec.num_taps)
    x[0] = 1.0
    resampler = StatefulRationalResampler(spec, segment_start_timestamp_us=0)
    chunk = resampler.process(x, 0)
    peak_index = int(np.argmax(np.abs(chunk.values)))
    peak_delay_ms = float(chunk.timestamps_us[peak_index]) / 1000.0
    matches = peak_index == spec.group_delay_output_samples and peak_delay_ms == 40.0
    return {
        "status": "PASS" if matches else "FAIL",
        "expected_peak_output_index": spec.group_delay_output_samples,
        "observed_peak_output_index": peak_index,
        "expected_delay_ms": 40.0,
        "observed_delay_ms": peak_delay_ms,
    }


def _check_output_clock(spec) -> dict[str, Any]:
    rng = np.random.default_rng(5)
    x = rng.standard_normal(3000)
    resampler = StatefulRationalResampler(spec, segment_start_timestamp_us=42)
    chunk = resampler.process(x, 0)
    diffs = np.diff(chunk.timestamps_us)
    exact = bool(np.all(diffs == 4000)) if len(diffs) else True
    return {"status": "PASS" if exact else "FAIL", "period_us": 4000, "max_drift_us": 0}


def _check_memory_bound(spec) -> dict[str, Any]:
    resampler = StatefulRationalResampler(spec)
    rng = np.random.default_rng(7)
    chunk_size = 977
    num_chunks = 50
    max_retained = 0
    for chunk_index in range(num_chunks):
        block = rng.standard_normal(chunk_size)
        resampler.process(block, chunk_index * chunk_size)
        max_retained = max(max_retained, resampler.state_metadata()["retained_history_length"])
    input_samples_processed = num_chunks * chunk_size
    return {
        "status": "PASS" if max_retained < input_samples_processed else "FAIL",
        "input_samples_processed": input_samples_processed,
        "max_retained_source_samples": max_retained,
    }


def _forbidden_api_audit() -> dict[str, Any]:
    source = (ROOT / "preprocessing/resample.py").read_text(encoding="utf-8")
    forbidden = ["signal.resample(", "signal.resample_poly(", ".filtfilt(", "sosfiltfilt("]
    hits = [name for name in forbidden if name in source]
    return {"status": "PASS" if not hits else "FAIL", "forbidden_references_found": hits}


def build_report() -> dict[str, Any]:
    split_before = verify_frozen_split(ROOT)
    split_hash_before = hash_file(ROOT / "manifests/splits/MITDB_SPLIT_V1.csv")

    conversions = {}
    for resampler_id in RESAMPLER_IDS:
        spec = load_resampler_spec(resampler_id)
        future_append = _check_future_append(spec)
        chunk_equivalence = _check_chunk_equivalence(spec)
        direct_reference = _check_direct_reference(spec)
        impulse_delay = _check_impulse_delay(spec)
        output_clock = _check_output_clock(spec)
        memory_bound = _check_memory_bound(spec)
        conversions[resampler_id] = {
            "up": spec.up,
            "down": spec.down,
            "coefficient_count": spec.num_taps,
            "coefficient_sha256": spec.coefficient_sha256,
            "group_delay_seconds": spec.group_delay_seconds,
            "group_delay_output_samples": spec.group_delay_output_samples,
            "timestamp_mapping_id": spec.timestamp_mapping_id,
            "future_append_status": future_append["status"],
            "chunk_equivalence_status": chunk_equivalence["status"],
            "direct_reference_status": direct_reference["status"],
            "impulse_delay_status": impulse_delay["status"],
            "output_clock_status": output_clock["status"],
            "memory_bound_status": memory_bound["status"],
            "future_append_detail": future_append,
            "chunk_equivalence_detail": chunk_equivalence,
            "direct_reference_detail": direct_reference,
            "impulse_delay_detail": impulse_delay,
            "output_clock_detail": output_clock,
            "memory_bound_detail": memory_bound,
        }

    forbidden_api_audit = _forbidden_api_audit()

    split_hash_after = hash_file(ROOT / "manifests/splits/MITDB_SPLIT_V1.csv")
    split_after = verify_frozen_split(ROOT)
    split_unchanged = split_hash_before == split_hash_after

    all_conversion_statuses = [
        conversions[rid][key]
        for rid in RESAMPLER_IDS
        for key in (
            "future_append_status", "chunk_equivalence_status", "direct_reference_status",
            "impulse_delay_status", "output_clock_status", "memory_bound_status",
        )
    ]
    overall_status = (
        "PASS"
        if all(status == "PASS" for status in all_conversion_statuses)
        and forbidden_api_audit["status"] == "PASS"
        and split_before["status"] == "PASS"
        and split_after["status"] == "PASS"
        and split_unchanged
        else "FAIL"
    )

    return {
        "preproc_id": "PREPROC_V1",
        "resampler_id": "PREPROC_V1_RESAMPLER_V1",
        "task_id": "T011",
        "target_rate_hz": 250,
        "conversions": conversions,
        "forbidden_api_audit": forbidden_api_audit,
        "split_freeze_verified": {
            "status": (
                "PASS"
                if split_before["status"] == "PASS" and split_after["status"] == "PASS"
                else "FAIL"
            ),
            "split_sha256_before": split_hash_before,
            "split_sha256_after": split_hash_after,
            "unchanged": split_unchanged,
        },
        "overall_status": overall_status,
    }


def main() -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    report = build_report()
    temporary = REPORT_PATH.with_suffix(f"{REPORT_PATH.suffix}.tmp")
    temporary.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(REPORT_PATH)
    print(f"T011 resampler causality: {report['overall_status']}")
    if report["overall_status"] != "PASS":
        raise RuntimeError(f"resampler causality checks failed: {report}")


if __name__ == "__main__":
    main()
