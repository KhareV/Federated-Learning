#!/usr/bin/env python3
"""T012: run the synthetic ECG/PPG filter causality proofs and emit
reports/preprocessing/filter_causality.json -- the canonical T012 filter evidence artifact.

Verifies F05 before/after (T012 must never mutate the frozen split). Offline, synthetic
signals only.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import scipy.signal as sig

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from evaluation.leakage_audit import verify_frozen_split  # noqa: E402
from nhm.hashing import hash_file  # noqa: E402
from preprocessing.filters import StatefulSOSFilter, load_filter_spec  # noqa: E402

REPORT_PATH = ROOT / "reports/preprocessing/filter_causality.json"
FILTER_IDS = ["PREPROC_V1_ECG_FILTER_V1", "PREPROC_V1_PPG_FILTER_V1"]
TOLERANCE_ATOL = 1e-12


def _status(max_error: float) -> dict[str, Any]:
    return {
        "status": "PASS" if max_error <= TOLERANCE_ATOL else "FAIL",
        "max_absolute_error": max_error,
    }


def _check_pole_stability(spec) -> dict[str, Any]:
    _, poles, _ = sig.sos2zpk(np.array(spec.sos))
    max_pole = float(np.max(np.abs(poles))) if len(poles) else 0.0
    return {"status": "PASS" if max_pole < 1.0 else "FAIL", "max_pole_magnitude": max_pole}


def _check_one_shot_reference(spec) -> dict[str, Any]:
    rng = np.random.default_rng(1)
    x = rng.standard_normal(2000)
    streaming = StatefulSOSFilter(spec).process(x)
    reference, _ = sig.sosfilt(np.array(spec.sos), x, zi=np.zeros((spec.sos_sections, 2)))
    return _status(float(np.max(np.abs(streaming - reference))))


def _check_future_append(spec) -> dict[str, Any]:
    rng = np.random.default_rng(2)
    prefix = rng.standard_normal(500)
    baseline = StatefulSOSFilter(spec).process(prefix)
    max_error = 0.0
    for suffix in (np.full(300, 1e6), rng.standard_normal(300) * 1e6):
        full = np.concatenate([prefix, suffix])
        full_output = StatefulSOSFilter(spec).process(full)
        error = float(np.max(np.abs(full_output[: len(baseline)] - baseline)))
        max_error = max(max_error, error)
    return _status(max_error)


def _fill(n: int, cycle: list[int]) -> list[int]:
    sizes, remaining, index = [], n, 0
    while remaining > 0:
        size = min(cycle[index % len(cycle)], remaining)
        sizes.append(size)
        remaining -= size
        index += 1
    return sizes


def _check_chunk_equivalence(spec) -> dict[str, Any]:
    rng = np.random.default_rng(3)
    n = 900
    x = rng.standard_normal(n)
    baseline = StatefulSOSFilter(spec).process(x)

    max_error = 0.0
    for sizes in (
        [1] * n,
        _fill(n, [4]),
        _fill(n, [7, 11, 13, 17, 19, 23]),
    ):
        filt = StatefulSOSFilter(spec)
        parts, index = [], 0
        for size in sizes:
            parts.append(filt.process(x[index : index + size]))
            index += size
        chunked = np.concatenate(parts)
        max_error = max(max_error, float(np.max(np.abs(chunked - baseline))))
    return _status(max_error)


def _check_impulse_causality(spec) -> dict[str, Any]:
    x = np.zeros(300)
    x[100] = 1.0
    y = StatefulSOSFilter(spec).process(x)
    pre_impulse_max = float(np.max(np.abs(y[:100])))
    return {
        "status": "PASS" if pre_impulse_max == 0.0 else "FAIL",
        "pre_impulse_max_abs": pre_impulse_max,
    }


def _check_reset(spec) -> dict[str, Any]:
    rng = np.random.default_rng(4)
    filt = StatefulSOSFilter(spec)
    filt.process(rng.standard_normal(400) * 1e6)
    filt.reset()
    quiet = np.full(200, 0.001)
    y_reset = filt.process(quiet)
    y_fresh = StatefulSOSFilter(spec).process(quiet)
    return _status(float(np.max(np.abs(y_reset - y_fresh))))


def _forbidden_api_audit() -> dict[str, Any]:
    forbidden = ["filtfilt(", "sosfiltfilt(", "signal.resample(", "signal.resample_poly("]
    hits: dict[str, list[str]] = {}
    for relative in ("preprocessing/ecg.py", "preprocessing/ppg.py", "preprocessing/filters.py"):
        source = (ROOT / relative).read_text(encoding="utf-8")
        found = [name for name in forbidden if name in source]
        if found:
            hits[relative] = found
    return {"status": "PASS" if not hits else "FAIL", "hits": hits}


def build_report() -> dict[str, Any]:
    split_before = verify_frozen_split(ROOT)
    split_hash_before = hash_file(ROOT / "manifests/splits/MITDB_SPLIT_V1.csv")

    filters: dict[str, Any] = {}
    for filter_id in FILTER_IDS:
        spec = load_filter_spec(filter_id)
        pole_stability = _check_pole_stability(spec)
        one_shot_reference = _check_one_shot_reference(spec)
        future_append = _check_future_append(spec)
        chunk_equivalence = _check_chunk_equivalence(spec)
        impulse_causality = _check_impulse_causality(spec)
        reset_check = _check_reset(spec)
        filters[filter_id] = {
            "signal": spec.signal,
            "sample_rate_hz": spec.fs_hz,
            "band_hz": list(spec.band_hz),
            "butterworth_prototype_order": spec.butterworth_prototype_order,
            "total_order": spec.total_order,
            "sos_sections": spec.sos_sections,
            "coefficient_sha256": spec.coefficient_sha256,
            "stable_poles_status": pole_stability["status"],
            "future_append_status": future_append["status"],
            "chunk_equivalence_status": chunk_equivalence["status"],
            "impulse_causality_status": impulse_causality["status"],
            "one_shot_causal_reference_status": one_shot_reference["status"],
            "reset_status": reset_check["status"],
            "stable_poles_detail": pole_stability,
            "future_append_detail": future_append,
            "chunk_equivalence_detail": chunk_equivalence,
            "impulse_causality_detail": impulse_causality,
            "one_shot_causal_reference_detail": one_shot_reference,
            "reset_detail": reset_check,
        }

    forbidden_api_audit = _forbidden_api_audit()
    split_hash_after = hash_file(ROOT / "manifests/splits/MITDB_SPLIT_V1.csv")
    split_after = verify_frozen_split(ROOT)
    split_unchanged = split_hash_before == split_hash_after

    all_statuses = [
        filters[fid][key]
        for fid in FILTER_IDS
        for key in (
            "stable_poles_status", "future_append_status", "chunk_equivalence_status",
            "impulse_causality_status", "one_shot_causal_reference_status", "reset_status",
        )
    ]
    overall_status = (
        "PASS"
        if all(status == "PASS" for status in all_statuses)
        and forbidden_api_audit["status"] == "PASS"
        and split_before["status"] == "PASS"
        and split_after["status"] == "PASS"
        and split_unchanged
        else "FAIL"
    )

    return {
        "task_id": "T012",
        "filters": filters,
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
    print(f"T012 filter causality: {report['overall_status']}")
    if report["overall_status"] != "PASS":
        raise RuntimeError(f"filter causality checks failed: {report}")


if __name__ == "__main__":
    main()
