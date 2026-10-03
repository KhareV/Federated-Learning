#!/usr/bin/env python3
"""C-V2-013-QUALITY-FLATLINE-AUDIT: classification, protected/preserved-evidence audit,
regression summary, run manifest and (last) artifact hashes."""

from __future__ import annotations

import json
import subprocess
import sys

from nhm.hashing import hash_file
from scripts._v2_013_lib import ROOT

OUT = ROOT / "reports/model_v2/c_v2_013_quality_flatline"
V2_013 = ROOT / "reports/model_v2/v2_013"
RUN_LOGS = {"pytest_collected_nodes.txt", "pytest_chunk_manifest.csv", "pytest_chunk_results.csv"}


def _load(name: str) -> dict:
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def _write(name: str, data: dict) -> None:
    (OUT / name).write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _run(*args: str, cwd=ROOT) -> dict:
    result = subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=False)
    return {"command": " ".join(args), "exit_code": result.returncode}


def main() -> None:
    contract = _load("frozen_contract_audit.json")
    direct = _load("direct_quality_flatline_test.json")
    full = _load("full_pipeline_flatline_reproduction.json")
    zero = _load("zero_source_flatline_scenarios.json")
    decay = _load("pipeline_filtered_flatline_decay.json")
    summary = _load("replay/flatline_replay_summary.json")
    assert not contract["drift"] and direct["status"] == "PASS"
    assert summary["status"] == "PASS"
    mid_first = zero["mid_stream_50_to_450s"]["first_flagged_window_end_s"]
    classification = {
        "branch": "A",
        "branch_text": "QUALITY_V1 is correct; the V2-013 simulator 'flatline' (constant NONZERO "
                       "source) was not a flatline in the representation QUALITY_V1 evaluates",
        "exact_cause": (
            "QUALITY_V1 evaluates the FILTERED 250 Hz window. For a constant nonzero source the "
            "frozen stateful 360->250 Hz polyphase resampler emits a persistent periodic ripple "
            "(relative ~1e-5; 13 distinct values per cycle), which the causal band-pass passes "
            "while removing the DC level; the filtered window therefore has std/rms ~ 1.0, far "
            "above the frozen 1e-12 criterion, and is never flagged (0 of "
            f"{full['complete_flat_source_windows']} complete flat-source windows flagged, up to "
            "a 1400 s constant source). Only an exactly-zero source stays exactly zero through "
            "the chain (rms == 0 -> FLATLINE)."),
        "v2_013_handoff_wording_correction": (
            "The V2-013 sentence 'QUALITY_V1 doesn't flag a flatline fault' overstated the "
            "finding: QUALITY_V1 flags exact/numerical flatline of the filtered window "
            "(direct tests 11/11 PASS); what it does not flag is a stuck NONZERO source."),
        "mid_stream_zero_latency": (
            "A zero source injected mid-stream is flagged only once the band-pass transient has "
            f"fully underflowed: first flagged window ends at {mid_first} s for zeros starting at "
            "50 s (roughly 315 s of zeros precede that window). Zero from stream start is "
            "flagged on every complete window."),
        "frozen_limitation_for_independent_replanning": (
            "The frozen QUALITY_V1 + PREPROC_V1 composition cannot hard-fail a stuck-at-nonzero "
            "ECG source. Closing that would be a Class C quality/preprocessing change (e.g. a "
            "pre-filter flatline guard) and was deliberately NOT made here."),
        "f06_drift": contract["drift"], "quality_semantics_changed": False,
        "scientific_example_impact_audit_required": False,
        "separate_defect_found_and_fixed": (
            "simulation/stream_runtime_v2013.py crashed (zero-size array max) when a chunk "
            "produced no resampler output (e.g. a 1-sample tail chunk). Guarded additively; the "
            "original 93-window V2-013 bundle is reproduced byte-for-byte; successor lock "
            "API_RUNTIME_V2_1."),
        "filtered_decay_probe_first_flagged_end_s_constant_nonzero": decay[
            "first_window_end_s_flagged_FLATLINE"],
        "status": "PASS",
    }
    _write("classification.json", classification)
    if "--classify-only" in sys.argv:
        return
    pre = json.loads((V2_013 / "artifact_hashes.json").read_text())["artifacts"]
    drift = sorted(p for p, d in pre.items() if hash_file(ROOT / p) != d)
    baseline = json.loads((V2_013 / "protected_baseline.json").read_text())["artifacts"]
    pdrift = sorted(p for p, d in baseline.items() if hash_file(ROOT / p) != d)
    _write("preservation_audit.json", {
        "v2_013_evidence_files_checked": len(pre), "v2_013_evidence_drift": drift,
        "protected_artifacts_checked": len(baseline), "protected_drift": pdrift,
        "v2_013_replay_digest_preserved": json.loads(
            (V2_013 / "replay_semantic_digest.json").read_text())["digests"][
                "run_1_frontend_path"][:8] == "7ef39ae9",
        "status": "PASS" if not drift and not pdrift else "FAIL"})
    chunked = _load("pre_export_regression.json")
    checks = {
        "ruff": _run(sys.executable, "-m", "ruff", "check", "src", "tests", "scripts",
                     "simulation", "deployment", "fusion", "api", "datasets", "features",
                     "models", "training", "evaluation", "preprocessing"),
        "pip_check": _run(sys.executable, "-m", "pip", "check"),
        "frontend_unit": _run("npm", "--prefix", "frontend", "run", "test"),
        "frontend_check": _run("npm", "--prefix", "frontend", "run", "check"),
        "frontend_build": _run("npm", "--prefix", "frontend", "run", "build"),
    }
    ok = chunked["status"] == "PASS" and all(c["exit_code"] == 0 for c in checks.values())
    _write("regression_audit.json", {"chunked_python_regression": chunked, "checks": checks,
                                     "ci": "deferred; Actions never triggered/queried",
                                     "status": "PASS" if ok else "FAIL"})
    if not ok or _load("preservation_audit.json")["status"] != "PASS":
        sys.exit("C_V2_013_FINALIZE_FAILED")
    _write("run_manifest.json", {
        "checkpoint_id": "C-V2-013-QUALITY-FLATLINE-AUDIT", "classification": "A",
        "result": "PASS", "v2_013": "PASS (unchanged)", "v2g12": "PASS (unchanged)",
        "api_runtime": "API_RUNTIME_V2_1 (successor of API_RUNTIME_V2, preserved)",
        "scientific_downstream_valid": True, "cumulative_v2_neural_fits": 71,
        "v2_fl_001_started": False, "ci_queried": False, "status": "PASS"})
    files = sorted(p.name for p in OUT.iterdir() if p.is_file())
    sub = sorted(f"replay/{p.name}" for p in (OUT / "replay").iterdir() if p.is_file())
    _write("artifact_hashes.json", {"artifacts": {
        f"reports/model_v2/c_v2_013_quality_flatline/{n}": hash_file(OUT / n)
        for n in [*files, *sub] if n.split("/")[-1] not in RUN_LOGS
        and n != "artifact_hashes.json"}})
    print("C-V2-013 evidence finalized")


if __name__ == "__main__":
    main()
