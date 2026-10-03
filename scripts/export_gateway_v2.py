#!/usr/bin/env python3
"""V2-012: the single canonical GATEWAY_ARTIFACT_V2 export (torch.jit.script, FP32, CPU), fresh-
process reload, two-workspace export reproduction, canonical-fixture parity, 1000-window synthetic
parity and CAL_V2 wrapper parity. One candidate only; no trace/ONNX/INT8 alternatives, no format
search. Runs strictly after METHOD_COMMIT.
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import torch

from deployment import gateway_v2 as gw
from models.model_v2_final_freeze import load_model_v2_final, verify_model_v2_final
from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/model_v2/v2_012"
ARTIFACT = ROOT / gw.ARTIFACT_PATH
FIXTURE = ROOT / "tests/fixtures/model_v2_final_test_vector.npz"
ENV = {"PYTHONPATH": "src:."}


def write_json(name: str, data: dict) -> None:
    (OUT / name).write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _child(*args: str) -> subprocess.CompletedProcess:
    import os

    return subprocess.run([sys.executable, str(Path(__file__).resolve()), *args], cwd=ROOT,
                          check=True, capture_output=True, text=True, env={**os.environ, **ENV})


def parity_child(artifact: Path, out_dir: Path) -> None:
    """Runs in a FRESH process: loads the artifact from disk only."""
    torch.set_num_threads(1)
    module = gw.load_artifact(artifact)
    with np.load(FIXTURE, allow_pickle=False) as fixture:
        inputs = fixture["normalized_inputs_float32"]
    windows = gw.load_parity_corpus(ROOT)
    with torch.inference_mode():
        fixture_logits = module(torch.from_numpy(inputs)).numpy()
        corpus_logits = np.concatenate(
            [module(torch.from_numpy(windows[i : i + 1])).numpy() for i in range(len(windows))])
    out_dir.mkdir(parents=True, exist_ok=True)
    np.save(out_dir / "fixture_logits.npy", fixture_logits)
    np.save(out_dir / "corpus_logits.npy", corpus_logits)
    print(json.dumps({
        "loaded": True,
        "parameter_count": gw.trainable_parameter_count(module),
        "signature": gw.artifact_signature(module),
        "jit_code_sha256": __import__("hashlib").sha256(module.code.encode()).hexdigest(),
        "torch_version": torch.__version__,
    }, sort_keys=True))


def export_temp(output: Path) -> None:
    result = gw.export_gateway_artifact(ROOT, output)
    print(json.dumps(result, sort_keys=True))


def native_logits() -> tuple[np.ndarray, np.ndarray]:
    torch.set_num_threads(1)
    model, _ = load_model_v2_final(ROOT)
    model.eval()
    with np.load(FIXTURE, allow_pickle=False) as fixture:
        inputs, expected = fixture["normalized_inputs_float32"], fixture["expected_logits_float32"]
    windows = gw.load_parity_corpus(ROOT)
    with torch.inference_mode():
        fixture_native = model(torch.from_numpy(inputs)).numpy()
        corpus_native = np.concatenate(
            [model(torch.from_numpy(windows[i : i + 1])).numpy() for i in range(len(windows))])
    assert np.array_equal(fixture_native.shape, expected.shape)
    return fixture_native, corpus_native


def canonical() -> None:
    if not (OUT / "method_freeze.json").exists():
        raise RuntimeError("V2_012_METHOD_MUST_BE_FROZEN_BEFORE_EXPORT")
    if ARTIFACT.exists():
        raise RuntimeError("V2_012_CANONICAL_ARTIFACT_ALREADY_EXISTS")
    verified = verify_model_v2_final(ROOT)

    export = gw.export_gateway_artifact(ROOT, ARTIFACT)
    module = gw.load_artifact(ARTIFACT)
    export_audit = {
        **export,
        "artifact_path": gw.ARTIFACT_PATH,
        "export_api": "torch.jit.script",
        "candidates_attempted": 1,
        "trace_attempted": False, "onnx_attempted": False, "int8_attempted": False,
        "format_selected_before_any_benchmark": True,
        "source_model_verifier": verified["status"],
        "trainable_parameter_count": gw.trainable_parameter_count(module),
        "signature": gw.artifact_signature(module),
        "source_checkpoint_bytes": (ROOT / "checkpoints/MODEL_V2_FINAL.pt").stat().st_size,
        "python_version": sys.version.split()[0],
        "jit_code_sha256": __import__("hashlib").sha256(module.code.encode()).hexdigest(),
        "status": "PASS" if gw.trainable_parameter_count(module) == 57553 else "FAIL",
    }
    write_json("export_audit.json", export_audit)
    if export_audit["status"] != "PASS":
        raise RuntimeError("V2_012_EXPORT_PARAMETER_COUNT_MISMATCH")

    # --- fresh-process reload + parity (canonical artifact) -------------------------------
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        info = json.loads(_child("parity-child", "--artifact", str(ARTIFACT),
                                 "--out", str(tmp_path / "canon")).stdout)
        fixture_gateway = np.load(tmp_path / "canon/fixture_logits.npy")
        corpus_gateway = np.load(tmp_path / "canon/corpus_logits.npy")

        # --- export reproduction: two fresh workspaces/processes ----------------------------
        exports = []
        for name in ("workspace_a", "workspace_b"):
            target = tmp_path / name / "MODEL_V2_GATEWAY_FP32.ts"
            reproduced = json.loads(_child("export-temp", "--output", str(target)).stdout)
            reload_info = json.loads(_child("parity-child", "--artifact", str(target),
                                            "--out", str(tmp_path / f"{name}_parity")).stdout)
            exports.append((target, reproduced, reload_info, tmp_path / f"{name}_parity"))
        comparisons = {
            "canonical_vs_workspace_a": gw.compare_artifact_files(ARTIFACT, exports[0][0]),
            "workspace_a_vs_workspace_b": gw.compare_artifact_files(exports[0][0], exports[1][0]),
        }
        parity_identical = all(
            np.array_equal(np.load(d / "fixture_logits.npy"), fixture_gateway)
            and np.array_equal(np.load(d / "corpus_logits.npy"), corpus_gateway)
            for _, _, _, d in exports)
        signatures_identical = all(
            r[2]["signature"] == info["signature"] and r[2]["jit_code_sha256"]
            == info["jit_code_sha256"] and r[2]["parameter_count"] == info["parameter_count"]
            for r in exports)
        byte_reproducible = all(c["byte_reproducible"] for c in comparisons.values())
        semantic = all(c["semantic_reproducibility"] for c in comparisons.values()) and (
            parity_identical and signatures_identical)
        write_json("artifact_reproducibility.json", {
            "canonical_artifact_sha256": hash_file(ARTIFACT),
            "workspace_artifact_sha256": [hash_file(e[0]) for e in exports],
            "byte_reproducible": byte_reproducible,
            "semantic_reproducibility": semantic,
            "comparisons": comparisons,
            "fixture_and_corpus_logits_identical_across_exports": parity_identical,
            "signatures_and_jit_code_identical": signatures_identical,
            "archive_difference_explanation": None if byte_reproducible else (
                "serialization bytes differ only in the listed archive members; state values, "
                "JIT code, signatures and all logits are identical"),
            "committed_canonical_artifact_has_one_fixed_sha": True,
            "status": "PASS" if (semantic or byte_reproducible) else "FAIL",
        })

    # --- parity against native -------------------------------------------------------------
    fixture_native, corpus_native = native_logits()
    with np.load(FIXTURE, allow_pickle=False) as fixture:
        expected = fixture["expected_logits_float32"]
    cal = json.loads((ROOT / "artifacts/CAL_V2.json").read_text())
    fixture_cmp = gw.compare_logits(fixture_native, fixture_gateway)
    fixture_vs_frozen = gw.compare_logits(expected, fixture_gateway)
    write_json("canonical_fixture_parity.json", {
        "fixture": "MODEL_V2_FINAL_SYNTHETIC_TEST_VECTOR_V1",
        "fixture_sha256": hash_file(FIXTURE),
        "rows": fixture_cmp["rows"],
        "native_logits": fixture_native.reshape(-1).astype(float).tolist(),
        "gateway_logits": fixture_gateway.reshape(-1).astype(float).tolist(),
        "frozen_expected_logits": expected.reshape(-1).astype(float).tolist(),
        "per_vector_abs_delta": np.abs(
            fixture_native.astype(np.float64) - fixture_gateway.astype(np.float64)
        ).reshape(-1).tolist(),
        "native_vs_gateway": fixture_cmp,
        "frozen_expected_vs_gateway": fixture_vs_frozen,
        "allclose": bool(fixture_cmp["allclose"] and fixture_vs_frozen["allclose"]),
        "tolerance": {"atol": gw.ATOL, "rtol": gw.RTOL},
        "fixture_inputs_or_outputs_modified": False,
        "status": "PASS" if (fixture_cmp["allclose"] and fixture_vs_frozen["allclose"]) else "FAIL",
    })

    comparison = gw.compare_logits(corpus_native, corpus_gateway)
    calib = gw.calibration_parity(corpus_native, corpus_gateway, cal)
    native_cal = gw.calibrate_logits(corpus_native, cal)
    gateway_cal = gw.calibrate_logits(corpus_gateway, cal)
    rows = []
    for i in range(gw.CORPUS_ROWS):
        n, g = float(corpus_native[i, 0]), float(corpus_gateway[i, 0])
        rows.append({
            "index": i,
            "native_logit": format(n, ".17g"), "gateway_logit": format(g, ".17g"),
            "abs_delta": format(abs(n - g), ".17g"),
            "rel_delta": format(abs(n - g) / max(abs(n), np.finfo(np.float64).tiny), ".17g"),
            "native_raw_probability": format(float(native_cal["raw_probability"][i]), ".17g"),
            "gateway_raw_probability": format(float(gateway_cal["raw_probability"][i]), ".17g"),
            "native_calibrated_probability": format(
                float(native_cal["calibrated_probability"][i]), ".17g"),
            "gateway_calibrated_probability": format(
                float(gateway_cal["calibrated_probability"][i]), ".17g"),
            "native_prediction": int(native_cal["prediction"][i]),
            "gateway_prediction": int(gateway_cal["prediction"][i]),
        })
    csv_path = OUT / "synthetic_corpus_parity.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    passed = (comparison["rows"] == 1000 and comparison["allclose"]
              and comparison["shape_mismatches"] == 0 and comparison["nonfinite_outputs"] == 0
              and calib["threshold_decision_disagreements"] == 0)
    write_json("synthetic_corpus_parity_summary.json", {
        "corpus": gw.CORPUS_ID,
        "corpus_sha256": hash_file(ROOT / gw.PARITY_CORPUS_PATH),
        "rows": comparison["rows"],
        "all_finite": comparison["nonfinite_outputs"] == 0,
        "shape_mismatches": comparison["shape_mismatches"],
        "allclose": comparison["allclose"],
        "tolerance": {"atol": gw.ATOL, "rtol": gw.RTOL},
        "max_abs_logit_delta": comparison["max_abs_delta"],
        "max_rel_logit_delta": comparison["max_rel_delta"],
        "max_raw_probability_delta": calib["max_raw_probability_delta"],
        "max_calibrated_probability_delta": calib["max_calibrated_probability_delta"],
        "threshold_decision_disagreements": calib["threshold_decision_disagreements"],
        "comparison_batch_size": 1,
        "no_scientific_metrics_reported": True,
        "csv_sha256": hash_file(csv_path),
        "status": "PASS" if passed else "FAIL",
    })

    # --- CAL_V2 wrapper (per-window runtime) equals the canonical helper --------------------
    runtime = gw.GatewayV2Runtime(ROOT, verify="export_audit")
    windows = gw.load_parity_corpus(ROOT)
    mismatch_prob, mismatch_pred, max_prob = 0, 0, 0.0
    for i in range(gw.CORPUS_ROWS):
        result = runtime.infer(windows[i : i + 1])
        max_prob = max(max_prob, abs(result.source_domain_calibrated_probability
                                     - float(gateway_cal["calibrated_probability"][i])))
        mismatch_pred += int(result.thresholded_prediction != int(gateway_cal["prediction"][i]))
        mismatch_prob += int(abs(result.raw_logit - float(corpus_gateway[i, 0])) > 0.0)
    write_json("calibration_wrapper_parity.json", {
        "calibration_id": "CAL_V2",
        "temperature": cal["temperature"], "threshold": cal["threshold"],
        "comparator": cal["threshold_comparator"],
        "helpers_used": ["source_domain_calibrated_probability", "raw_probability_from_logit",
                         "apply_operating_threshold"],
        "formulas_duplicated_in_exporter": False,
        "native_vs_gateway": calib,
        "wrapper_vs_helper_max_calibrated_probability_delta": max_prob,
        "wrapper_vs_helper_threshold_disagreements": mismatch_pred,
        "wrapper_vs_artifact_raw_logit_mismatches": mismatch_prob,
        "wrapper_fields": ["raw_logit", "raw_probability", "source_domain_calibrated_probability",
                           "threshold", "thresholded_prediction", "model_id",
                           "gateway_artifact_id", "calibration_id", "calibration_domain",
                           "target_id", "preproc_id"],
        "temperature_or_threshold_baked_into_weights": False,
        "status": "PASS" if (calib["threshold_decision_disagreements"] == 0
                             and mismatch_pred == 0) else "FAIL",
    })
    print(json.dumps({"export": export_audit["status"], "artifact_sha256": hash_file(ARTIFACT),
                      "corpus_parity": passed, "byte_reproducible": byte_reproducible}))
    if not passed:
        raise RuntimeError("V2_012_PARITY_FAILURE")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("canonical", "parity-child", "export-temp"))
    parser.add_argument("--artifact", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.mode == "parity-child":
        parity_child(args.artifact, args.out)
    elif args.mode == "export-temp":
        export_temp(args.output)
    else:
        canonical()


if __name__ == "__main__":
    main()
