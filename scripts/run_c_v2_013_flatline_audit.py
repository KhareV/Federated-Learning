#!/usr/bin/env python3
"""C-V2-013-QUALITY-FLATLINE-AUDIT diagnosis. Synthetic fixtures only; no model inference, no
dataset access, no scientific artifact is modified. Writes
reports/model_v2/c_v2_013_quality_flatline."""

from __future__ import annotations

import dataclasses
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import yaml

from nhm.hashing import hash_file
from preprocessing.ecg import ECGPreprocessingPipeline
from preprocessing.freeze import verify_preproc_freeze
from preprocessing.quality import (
    FLATLINE_RELATIVE_EPSILON,
    evaluate_ecg_quality,
)
from simulation import profile_v2013 as prof
from simulation.stream_runtime_v2013 import WearableStreamRuntime

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/model_v2/c_v2_013_quality_flatline"


def _write(name: str, data: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _stats(x: np.ndarray) -> dict:
    x = np.asarray(x, dtype=np.float64)
    rms = float(np.sqrt(np.mean(x**2)))
    std = float(np.std(x))
    return {"std": std, "rms": rms, "range": float(x.max() - x.min()),
            "std_over_rms": (std / rms) if rms > 0 else None}


def contract_and_f06() -> dict:
    cfg = yaml.safe_load((ROOT / "configs/quality_v1.yaml").read_text())
    lock = json.loads((ROOT / "manifests/preprocessing/PREPROC_V1.lock.json").read_text())
    pins = lock["artifact_sha256"]
    f06 = verify_preproc_freeze(ROOT)
    live = {p: hash_file(ROOT / p) for p in ("configs/quality_v1.yaml",
                                              "preprocessing/quality.py")}
    callers = subprocess.run(
        ["git", "grep", "-l", "evaluate_ecg_quality", "--", "*.py"], cwd=ROOT,
        capture_output=True, text=True, check=False).stdout.split()
    data = {
        "quality_id": cfg["quality_id"], "spec_version": cfg["spec_version"],
        "flatline_rule": cfg["flatline"],
        "reason_code": cfg["hard_failure_rules"]["flatline"],
        "state_precedence": cfg["state_precedence"],
        "parameter": FLATLINE_RELATIVE_EPSILON,
        "parameter_is_numerical_epsilon_not_data_derived": cfg["flatline"][
            "parameter_provenance"] == "NUMERICAL_EPSILON_NOT_DATA_TUNED",
        "exact_condition": "signal.size==2500 and all finite and (rms==0.0 or "
        "np.std(signal,ddof=0)/rms <= 1e-12)  [preprocessing/quality.py::is_flatline]",
        "evaluated_on": "the complete 2500-sample window of the FILTERED, resampled 250 Hz ECG "
        "(ECGPreprocessingPipeline output); every production caller passes filtered[start:end]",
        "callers_of_evaluate_ecg_quality": sorted(callers),
        "frozen_pin_vs_live_hash": {p: {"pinned": pins[p], "live": h, "match": pins[p] == h}
                                    for p, h in live.items()},
        "f06_verifier_result": {k: f06[k] for k in f06 if k in ("status", "checked", "drift")}
        or f06,
        "quality_runtime_invocation_v2013": "simulation/stream_runtime_v2013.py::_window passes "
        "the filtered window (NaN->0 only for already-flagged missing slots) with gap/clip flags",
    }
    data["drift"] = not all(v["match"] for v in data["frozen_pin_vs_live_hash"].values())
    _write("frozen_contract_audit.json", data)
    _write("f06_verification.json", {
        "drift": data["drift"], "verifier": data["f06_verifier_result"],
        "pins": data["frozen_pin_vs_live_hash"]})
    return data


def direct_tests() -> dict:
    t = np.arange(2500) / 250.0
    ecg = np.sin(2 * np.pi * 1.2 * t) * (1 + 0.3 * np.sin(2 * np.pi * 7 * t))
    eps = FLATLINE_RELATIVE_EPSILON
    cases = {
        "A_exact_zero": (np.zeros(2500), True),
        "B_constant_positive_0.37": (np.full(2500, 0.37), True),
        "C_constant_negative_-1.9": (np.full(2500, -1.9), True),
        "D_constant_1e-9": (np.full(2500, 1e-9), True),
        "D_constant_1e3": (np.full(2500, 1e3), True),
        "D_constant_1e9": (np.full(2500, 1e9), True),
        "E_near_flat_rel_1e-13_below": (3.0 * (1 + 1e-13 * np.sign(np.sin(t * 9))), True),
        "E_near_flat_rel_1e-12_boundary_below": (
            5.0 * (1 + 0.5e-12 * np.sign(np.sin(t * 9))), True),
        "F_perturbed_rel_1e-10_above": (3.0 * (1 + 1e-10 * np.sign(np.sin(t * 9))), False),
        "F_perturbed_rel_1e-6_above": (3.0 * (1 + 1e-6 * np.sign(np.sin(t * 9))), False),
        "G_normal_ecg_control": (ecg, False),
    }
    rows, ok = {}, True
    for name, (signal, expect_flat) in cases.items():
        result = evaluate_ecg_quality(signal)
        flagged = "FLATLINE" in [r.value for r in result.reasons]
        passed = flagged == expect_flat and (
            result.state.value == ("UNUSABLE" if expect_flat else "VALID"))
        ok &= passed
        rows[name] = {"expected_flatline": expect_flat, "state": result.state.value,
                      "reasons": [r.value for r in result.reasons], "stats": _stats(signal),
                      "epsilon": eps, "pass": passed}
    data = {"cases": rows, "all_match_frozen_contract": ok,
            "no_threshold_invented_or_tuned": True, "status": "PASS" if ok else "FAIL"}
    _write("direct_quality_flatline_test.json", data)
    return data


def historical_tests() -> dict:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
         "tests/test_quality_v1.py", "tests/test_bidmc_context_quality.py", "-k",
         "flat or quality"],
        cwd=ROOT, capture_output=True, text=True, check=False)
    src = (ROOT / "tests/test_quality_v1.py").read_text()
    t013 = (ROOT / "scripts/run_quality_tests_t013.py").read_text()
    data = {
        "pytest_exit_code": proc.returncode, "tail": proc.stdout.strip().splitlines()[-1],
        "tests_and_scripts_inspected": [
            "tests/test_quality_v1.py::test_quality_precedence_and_required_states",
            "tests/test_quality_v1.py::test_flatline_check_is_scale_safe_for_near_constant_signal",
            "scripts/run_quality_tests_t013.py (T013 evidence generator)"],
        "what_they_exercise": {
            "production_evaluator_called": "evaluate_ecg_quality(np.ones(2500)) in both "
            "test_quality_precedence_and_required_states and run_quality_tests_t013.py",
            "complete_2500_sample_window": True,
            "exact_constant": "np.ones(2500) only (a constant ONE; no zero, negative or scaled "
            "constants through evaluate_ecg_quality)",
            "asserts_state_unusable": True,
            "asserts_flatline_reason_code": "FLATLINE" in src and "QualityReason.FLATLINE" in src,
            "near_flat_cases": "helper is_flatline only: 2.0 +/- 1e-14 ramp is flat",
            "above_criterion_negative_control": False,
            "input_representation": "directly constructed synthetic arrays; never the output of "
            "ECGPreprocessingPipeline (the representation every production caller supplies)",
            "t013_script_assertions_state_only": "UNUSABLE_FLATLINE" in t013,
        },
        "mocking_detected": "unittest.mock" in src or "monkeypatch" in src,
        "conclusion": (
            "The historical tests do call the real production evaluator and prove the written "
            "rule on direct synthetic input, so the F06 claim 'flatline rule implemented, tested "
            "and frozen' is TRUE as stated. They never feed a constant SOURCE through the frozen "
            "resampler/band-pass, so they could not reveal that a constant nonzero source is not "
            "flat in the filtered representation, and they do not assert the FLATLINE reason code "
            "through evaluate_ecg_quality."),
    }
    _write("historical_t013_test_audit.json", data)
    return data


def _pipeline_filtered(counts_mv: np.ndarray) -> np.ndarray:
    pipe = ECGPreprocessingPipeline(360, "MITDB_360_TO_250_V1")
    out, chunk = [], 360
    for s in range(0, counts_mv.size, chunk):
        e = min(s + chunk, counts_mv.size)
        res = pipe.process(counts_mv[s:e], np.arange(s, e, dtype=np.int64),
                           source_timestamps_us=np.arange(s, e, dtype=np.int64) * 1_000_000 // 360
                           if s == 0 else None)
        out.extend(c.filtered_values for c in res.chunks)
    return np.concatenate(out)


def pipeline_decay() -> dict:
    """What does a constant SOURCE look like after the frozen causal pipeline, and when (if ever)
    does a complete 10 s filtered window satisfy the frozen flatline condition?"""
    seconds = 1400
    n = seconds * 360
    sig = np.full(n, 0.12)  # constant 0.12 mV from t=0 (a source flatline from stream start)
    filt = _pipeline_filtered(sig)
    rows, first_flat = [], None
    for end_s in list(range(10, 60, 10)) + list(range(60, seconds, 20)):
        w = filt[(end_s - 10) * 250:end_s * 250]
        if w.size != 2500:
            continue
        q = evaluate_ecg_quality(w)
        flagged = "FLATLINE" in [r.value for r in q.reasons]
        if flagged and first_flat is None:
            first_flat = end_s
        rows.append({"window_end_s": end_s, **_stats(w), "state": q.state.value,
                     "flatline": flagged})
    data = {"source": "constant 0.12 mV at 360 Hz from stream start, frozen "
            "ECGPreprocessingPipeline(360, MITDB_360_TO_250_V1)",
            "first_window_end_s_flagged_FLATLINE": first_flat,
            "sampled_windows": rows[:14] + rows[-4:]}
    return data


def full_pipeline() -> dict:
    results = []
    for duration in (10.0, 15.0, 30.0, 60.0, 120.0):
        start = 20.0
        total = int(start + duration + 25)
        profile = dataclasses.replace(
            prof.LIVE_EXCERPT_PROFILE, profile_id=f"FLAT_{int(duration)}",
            duration_s=total,
            faults=(prof.FaultSegment(start, start + duration, "ECG_FLATLINE"),),
            context=(prof.ContextSegment(0.0, float(total), "VALID"),))
        records = list(prof.iter_observed_records(profile))
        raw = np.array([r.ecg_raw for r in records], dtype=np.float64) / prof.SIM_ECG_COUNTS_PER_MV
        runtime = WearableStreamRuntime(session_id="FLAT", model_id="MODEL_V2_FINAL",
                                        replay_id="FLAT")
        events = []
        for i in range(0, len(records), 360):
            events.extend(runtime.ingest(records[i:i + 360]))
        events.extend(runtime.finish())
        for ev in events:
            edge = ev["timestamp_us"] / 1e6
            lo, hi = int((edge - 10) * 360), int(edge * 360)
            inside = start <= edge - 10 and edge <= start + duration
            overlaps = edge > start and edge - 10 < start + duration
            results.append({
                "fault_interval_s": [start, start + duration], "window_end_s": edge,
                "window_fully_inside_flat_source": inside, "window_overlaps_fault": overlaps,
                "raw_std": float(np.std(raw[lo:hi])), "raw_range": float(np.ptp(raw[lo:hi])),
                "post_processing": _stats(np.asarray(ev["ecg"]["samples"])),
                "quality": ev["ecg_quality"],
                "reasons": ev["diagnostics"]["quality_reasons"]})
    inside_rows = [r for r in results if r["window_fully_inside_flat_source"]]
    data = {"windows": results,
            "complete_flat_source_windows": len(inside_rows),
            "complete_flat_source_windows_flagged_UNUSABLE_FLATLINE": sum(
                r["quality"] == "UNUSABLE" and "FLATLINE" in r["reasons"] for r in inside_rows)}
    return data


def _stream(records: list) -> list[dict]:
    runtime = WearableStreamRuntime(session_id="FLAT0", model_id="MODEL_V2_FINAL",
                                    replay_id="FLAT0")
    events: list[dict] = []
    for i in range(0, len(records), 360):
        events.extend(runtime.ingest(records[i:i + 360]))
    events.extend(runtime.finish())
    return events


def zero_source_scenarios() -> dict:
    """Exact-zero SOURCE (ADC reads 0): the only constant that stays exactly constant through the
    frozen resampler/band-pass. (a) zero from stream start; (b) zero injected mid-stream."""
    base = dataclasses.replace(prof.LIVE_EXCERPT_PROFILE, duration_s=470, faults=(),
                               profile_id="ZERO_SCEN",
                               context=(prof.ContextSegment(0.0, 470.0, "VALID"),))
    records = list(prof.iter_observed_records(base))

    def with_zero(a_s: float, b_s: float) -> list:
        lo, hi = round(a_s * 360), round(b_s * 360)
        return [dataclasses.replace(r, ecg_raw=0) if lo <= r.sample_index < hi else r
                for r in records]

    out = {}
    for name, (a, b) in {"from_start_0_to_40s": (0.0, 40.0),
                         "mid_stream_50_to_450s": (50.0, 450.0)}.items():
        rows = []
        for ev in _stream(with_zero(a, b)):
            edge = ev["timestamp_us"] / 1e6
            rows.append({"window_end_s": edge,
                         "fully_inside_zero_source": a <= edge - 10 and edge <= b,
                         "post_std_over_rms": _stats(np.asarray(ev["ecg"]["samples"]))[
                             "std_over_rms"],
                         "post_rms": _stats(np.asarray(ev["ecg"]["samples"]))["rms"],
                         "quality": ev["ecg_quality"],
                         "reasons": ev["diagnostics"]["quality_reasons"]})
        inside = [r for r in rows if r["fully_inside_zero_source"]]
        flagged = [r for r in inside if "FLATLINE" in r["reasons"]]
        out[name] = {"zero_interval_s": [a, b], "complete_windows_inside": len(inside),
                     "flagged_UNUSABLE_FLATLINE": len(flagged),
                     "first_flagged_window_end_s": flagged[0]["window_end_s"] if flagged else None,
                     "windows": rows}
    return out


def main() -> None:
    contract = contract_and_f06()
    direct = direct_tests()
    historical = historical_tests()
    decay = pipeline_decay()
    full = full_pipeline()
    _write("pipeline_filtered_flatline_decay.json", decay)
    _write("full_pipeline_flatline_reproduction.json", full)
    zero = zero_source_scenarios()
    _write("zero_source_flatline_scenarios.json", zero)
    print(json.dumps({"drift": contract["drift"], "direct": direct["status"],
                      "historical_exit": historical["pytest_exit_code"],
                      "first_flat_end_s": decay["first_window_end_s_flagged_FLATLINE"],
                      "flat_windows": full["complete_flat_source_windows"],
                      "flat_flagged": full[
                          "complete_flat_source_windows_flagged_UNUSABLE_FLATLINE"],
                      "zero": {k: [v["complete_windows_inside"], v["flagged_UNUSABLE_FLATLINE"],
                                   v["first_flagged_window_end_s"]] for k, v in zero.items()}}))


if __name__ == "__main__":
    main()
