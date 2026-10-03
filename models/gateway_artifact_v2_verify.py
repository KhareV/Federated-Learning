"""GATEWAY_ARTIFACT_V2 fail-closed verifier. Recomputes every hash and re-runs native-vs-gateway
parity from the files on disk; never trusts a stored PASS field."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import torch
import yaml

from deployment import gateway_v2 as gw
from models.cal_v2_verify import verify_cal_v2
from models.model_v2_final_freeze import load_model_v2_final, verify_model_v2_final
from nhm.hashing import hash_file

CONFIG_PATH = "configs/model_v2/gateway_artifact_v2.yaml"
REPORT_DIR = "reports/model_v2/v2_012"
FIXTURE_PATH = "tests/fixtures/model_v2_final_test_vector.npz"


class GatewayArtifactV2VerifyError(RuntimeError):
    """Raised when any GATEWAY_ARTIFACT_V2 binding or invariant differs."""


def _need(condition: bool, code: str, detail: str = "") -> None:
    if not condition:
        raise GatewayArtifactV2VerifyError(f"{code}:{detail}" if detail else code)


def _json(root: Path, rel: str) -> dict[str, Any]:
    path = root / rel
    _need(path.exists(), "GATEWAY_V2_FILE_MISSING", rel)
    return json.loads(path.read_text(encoding="utf-8"))


def _hash(root: Path, rel: str) -> str:
    path = root / rel
    _need(path.exists(), "GATEWAY_V2_FILE_MISSING", rel)
    return hash_file(path)


def check_manifest_constants(manifest: dict[str, Any]) -> None:
    """Pure checks of the identity/semantic fields (testable without any file)."""
    _need(manifest.get("artifact_id") == gw.ARTIFACT_ID, "GATEWAY_V2_WRONG_ARTIFACT_ID")
    _need(manifest.get("deployment_artifact_id") == gw.DEPLOYMENT_ARTIFACT_ID,
          "GATEWAY_V2_WRONG_DEPLOYMENT_ARTIFACT_ID")
    _need(manifest.get("status") == gw.FROZEN_STATUS, "GATEWAY_V2_WRONG_STATUS")
    _need(manifest.get("owner_task") == "V2-012", "GATEWAY_V2_WRONG_OWNER")
    art = manifest.get("artifact", {})
    _need(art.get("format") == gw.FORMAT, "GATEWAY_V2_WRONG_FORMAT")
    _need(art.get("precision") == gw.PRECISION, "GATEWAY_V2_WRONG_PRECISION")
    _need(manifest.get("int8") == "NOT_EVALUATED", "GATEWAY_V2_INT8_METADATA")
    _need(manifest.get("input_shape") == ["N", 1, gw.WINDOW_SAMPLES]
          and manifest.get("input_dtype") == "float32", "GATEWAY_V2_WRONG_INPUT_SHAPE")
    _need(manifest.get("output_semantics") == gw.OUTPUT_SEMANTICS, "GATEWAY_V2_WRONG_OUTPUT")
    src = manifest.get("source_model", {})
    _need(src.get("id") == gw.MODEL_ID, "GATEWAY_V2_WRONG_MODEL_ID")
    _need(src.get("architecture_id") == "MODEL_V2_TCN_MEAN", "GATEWAY_V2_WRONG_ARCHITECTURE")
    _need(src.get("parameter_count") == 57553
          and manifest.get("gateway_parameter_count") == 57553, "GATEWAY_V2_WRONG_PARAMETER_COUNT")
    _need(manifest.get("target_id") == "AAMI_SVF_WINDOW_V1", "GATEWAY_V2_WRONG_TARGET")
    _need(manifest.get("map_id") == "AAMI_SVF_MAP_V1", "GATEWAY_V2_WRONG_MAP")
    _need(manifest.get("preprocessing", {}).get("id") == "PREPROC_V1", "GATEWAY_V2_WRONG_PREPROC")
    eq = manifest.get("equivalence", {})
    _need(eq.get("atol") == gw.ATOL and eq.get("rtol") == gw.RTOL,
          "GATEWAY_V2_WRONG_TOLERANCE")
    corpus = manifest.get("synthetic_corpus_parity", {})
    _need(corpus.get("rows") == gw.CORPUS_ROWS and corpus.get("allclose") is True,
          "GATEWAY_V2_CORPUS_PARITY_MISSING")
    _need(corpus.get("threshold_decision_disagreements") == 0,
          "GATEWAY_V2_THRESHOLD_DISAGREEMENTS")
    fixture = manifest.get("fixture_parity", {})
    _need(fixture.get("allclose") is True and fixture.get("rows") == 3,
          "GATEWAY_V2_FIXTURE_PARITY_MISSING")
    sem = manifest.get("status_semantics", {})
    _need(sem.get("operational_lineage") == "MODEL_V1", "GATEWAY_V2_LINEAGE_CHANGED")
    _need(sem.get("official_validation_promotion") == "MODEL_V2_NOT_PROMOTED_RELEASE_CI",
          "GATEWAY_V2_PROMOTION_STATUS_CHANGED")
    _need(sem.get("MODEL_V2_RUNTIME_ACCEPTED") == "ACCEPTED",
          "GATEWAY_V2_RUNTIME_ACCEPTANCE_CHANGED")
    _need(manifest.get("benchmark", {}).get("repetitions") == gw.REPETITIONS
          and manifest.get("benchmark", {}).get("measured_per_run") == gw.MEASURED
          and manifest.get("benchmark", {}).get("warmup") == gw.WARMUP,
          "GATEWAY_V2_BENCHMARK_METHOD_FIELDS")


def verify_gateway_artifact_v2(root: Path) -> dict[str, Any]:
    checks: dict[str, bool] = {}
    verify_model_v2_final(root)
    verify_cal_v2(root)
    checks["upstream_verified"] = True

    manifest = _json(root, gw.MANIFEST_PATH)
    config = yaml.safe_load((root / CONFIG_PATH).read_text(encoding="utf-8"))
    check_manifest_constants(manifest)
    checks["manifest_constants"] = True

    # --- config is the frozen method; manifest must agree with it -------------------------
    fmt = config["format"]
    _need(fmt["selected"] == gw.FORMAT and fmt["precision"] == gw.PRECISION
          and config["INT8_STATUS"] == "NOT_EVALUATED", "GATEWAY_V2_CONFIG_FORMAT")
    _need(config["equivalence"]["atol"] == gw.ATOL and config["equivalence"]["rtol"] == gw.RTOL,
          "GATEWAY_V2_WRONG_TOLERANCE")
    _need(config["output_contract"]["semantics"] == gw.OUTPUT_SEMANTICS, "GATEWAY_V2_CONFIG_OUTPUT")
    _need(config["status_semantics"]["operational_lineage"] == "MODEL_V1",
          "GATEWAY_V2_LINEAGE_CHANGED")
    _need(manifest["benchmark"]["config_sha256"] == _hash(root, CONFIG_PATH),
          "GATEWAY_V2_CONFIG_HASH_MISMATCH")
    checks["config"] = True

    # --- hashes recomputed from disk --------------------------------------------------
    artifact_rel = manifest["artifact"]["path"]
    _need(artifact_rel == gw.ARTIFACT_PATH, "GATEWAY_V2_ARTIFACT_PATH")
    artifact = root / artifact_rel
    _need(artifact.exists(), "GATEWAY_V2_ARTIFACT_MISSING")
    _need(hash_file(artifact) == manifest["artifact"]["sha256"],
          "GATEWAY_V2_ARTIFACT_HASH_MISMATCH")
    _need(artifact.stat().st_size == manifest["artifact"]["bytes"], "GATEWAY_V2_ARTIFACT_SIZE")
    live = {
        "checkpoint": _hash(root, "checkpoints/MODEL_V2_FINAL.pt"),
        "model_manifest": _hash(root, "checkpoints/MODEL_V2_FINAL.manifest.json"),
        "model_config": _hash(root, "configs/model_v2_final_frozen.yaml"),
        "cal": _hash(root, "artifacts/CAL_V2.json"),
        "preproc": _hash(root, "manifests/preprocessing/PREPROC_V1.lock.json"),
        "protocol": _hash(root, "manifests/model_v2/MODEL_V2_RESEARCH_PROTOCOL_V3.lock.json"),
    }
    src = manifest["source_model"]
    _need(src["sha256"] == live["checkpoint"] == config["source_model"]["checkpoint_sha256"],
          "GATEWAY_V2_SOURCE_CHECKPOINT_MISMATCH")
    _need(src["manifest_sha256"] == live["model_manifest"], "GATEWAY_V2_SOURCE_MANIFEST_MISMATCH")
    _need(src["config_sha256"] == live["model_config"], "GATEWAY_V2_SOURCE_CONFIG_MISMATCH")
    _need(manifest["calibration"]["sha256"] == live["cal"] == config["calibration"]["sha256"],
          "GATEWAY_V2_CAL_V2_MISMATCH")
    _need(manifest["calibration"]["id"] == gw.CALIBRATION_ID, "GATEWAY_V2_CAL_V2_MISMATCH")
    _need(manifest["preprocessing"]["lock_sha256"] == live["preproc"],
          "GATEWAY_V2_PREPROC_MISMATCH")
    _need(manifest["protocol_v3_lock_sha256"] == live["protocol"],
          "GATEWAY_V2_PROTOCOL_V3_MISMATCH")
    cal = _json(root, "artifacts/CAL_V2.json")
    _need(manifest["target_id"] == cal["target_id"] and manifest["map_id"] == cal["map_id"],
          "GATEWAY_V2_TARGET_MAP_MISMATCH")
    checks["hash_bindings"] = True

    # --- parity corpus: file hash AND deterministic regeneration ------------------------
    corpus_meta = manifest["parity_corpus"]
    _need(_hash(root, gw.PARITY_CORPUS_PATH) == corpus_meta["sha256"]
          == config["parity_corpus"]["npz_sha256"], "GATEWAY_V2_PARITY_CORPUS_MISMATCH")
    windows = gw.load_parity_corpus(root)
    regenerated = gw.generate_parity_corpus()
    _need(np.array_equal(windows, regenerated)
          and gw.corpus_content_sha256(windows) == corpus_meta["windows_content_sha256"]
          == config["parity_corpus"]["windows_content_sha256"],
          "GATEWAY_V2_PARITY_CORPUS_MISMATCH", "content")
    _need(_hash(root, FIXTURE_PATH) == config["canonical_fixture"]["sha256"],
          "GATEWAY_V2_FIXTURE_MISMATCH")
    checks["parity_corpus"] = True

    # --- artifact internals ------------------------------------------------------------
    module = gw.load_artifact(artifact)
    _need(gw.trainable_parameter_count(module) == 57553, "GATEWAY_V2_WRONG_PARAMETER_COUNT")
    _need(all(p.dtype == torch.float32 for p in module.parameters())
          and all(b.dtype in (torch.float32, torch.int64) for b in module.buffers()),
          "GATEWAY_V2_WRONG_PRECISION")
    signature = gw.artifact_signature(module)
    _need(signature["output_shape_batch_1"] == [1, 1]
          and signature["output_shape_batch_3"] == [3, 1]
          and signature["output_dtype"] == "torch.float32", "GATEWAY_V2_WRONG_OUTPUT")
    payload = torch.load(root / "checkpoints/MODEL_V2_FINAL.pt", map_location="cpu",
                         weights_only=False)["state_dict"]
    state = module.state_dict()
    _need(set(state) == set(payload) and all(torch.equal(state[k], payload[k]) for k in payload),
          "GATEWAY_V2_STATE_MISMATCH")
    checks["artifact_internals"] = True

    # --- recomputed parity -----------------------------------------------------------------
    native, _ = load_model_v2_final(root)
    native.eval()
    with np.load(root / FIXTURE_PATH, allow_pickle=False) as fixture:
        inputs, expected = fixture["normalized_inputs_float32"], fixture["expected_logits_float32"]
    with torch.inference_mode():
        fixture_gateway = module(torch.from_numpy(inputs)).numpy()
        fixture_native = native(torch.from_numpy(inputs)).numpy()
    _need(np.allclose(expected, fixture_gateway, atol=gw.ATOL, rtol=gw.RTOL)
          and np.allclose(fixture_native, fixture_gateway, atol=gw.ATOL, rtol=gw.RTOL),
          "GATEWAY_V2_FIXTURE_PARITY_FAILED")
    runtime_native, runtime_gateway = [], []
    with torch.inference_mode():
        for i in range(gw.CORPUS_ROWS):
            x = torch.from_numpy(windows[i : i + 1])
            runtime_native.append(float(native(x).numpy()[0, 0]))
            runtime_gateway.append(float(module(x).numpy()[0, 0]))
    comparison = gw.compare_logits(np.asarray(runtime_native), np.asarray(runtime_gateway))
    _need(comparison["rows"] == 1000 and comparison["allclose"]
          and comparison["shape_mismatches"] == 0 and comparison["nonfinite_outputs"] == 0,
          "GATEWAY_V2_CORPUS_PARITY_FAILED")
    calibration = gw.calibration_parity(
        np.asarray(runtime_native), np.asarray(runtime_gateway), cal)
    _need(calibration["threshold_decision_disagreements"] == 0,
          "GATEWAY_V2_THRESHOLD_DISAGREEMENTS")
    recorded = manifest["synthetic_corpus_parity"]
    _need(abs(recorded["max_abs_logit_delta"] - comparison["max_abs_delta"]) <= 1e-12
          and recorded["threshold_decision_disagreements"] == 0,
          "GATEWAY_V2_PARITY_RESULT_MISMATCH")
    for key, rel in (("summary_sha256", f"{REPORT_DIR}/synthetic_corpus_parity_summary.json"),
                     ("csv_sha256", f"{REPORT_DIR}/synthetic_corpus_parity.csv")):
        _need(recorded[key] == _hash(root, rel), "GATEWAY_V2_PARITY_RESULT_MISMATCH", key)
    _need(manifest["fixture_parity"]["file_sha256"]
          == _hash(root, f"{REPORT_DIR}/canonical_fixture_parity.json"),
          "GATEWAY_V2_PARITY_RESULT_MISMATCH", "fixture")
    summary = _json(root, f"{REPORT_DIR}/synthetic_corpus_parity_summary.json")
    _need(summary["threshold_decision_disagreements"] == 0 and summary["rows"] == 1000
          and summary["allclose"] is True and summary["tolerance"] == {"atol": 1e-6, "rtol": 1e-6},
          "GATEWAY_V2_PARITY_RESULT_MISMATCH", "summary")
    checks["parity_recomputed"] = True

    # --- wrapper semantics -----------------------------------------------------------------
    runtime = gw.GatewayV2Runtime(root)
    result = runtime.infer(windows[3:4])
    _need(result.model_id == gw.MODEL_ID and result.gateway_artifact_id == gw.ARTIFACT_ID
          and result.calibration_id == gw.CALIBRATION_ID and result.preproc_id == "PREPROC_V1"
          and result.threshold == cal["threshold"], "GATEWAY_V2_WRAPPER_SEMANTICS")
    checks["wrapper"] = True

    # --- benchmark records present and well-formed ----------------------------------------
    bench = manifest["benchmark"]
    summary_rel = f"{REPORT_DIR}/benchmark_summary.json"
    _need(bench["summary_sha256"] == _hash(root, summary_rel), "GATEWAY_V2_BENCHMARK_MISMATCH")
    bsum = _json(root, summary_rel)
    _need(len(bsum["runs"]) == gw.REPETITIONS and all(
        r["measured_count"] == gw.MEASURED and r["warmup_count"] == gw.WARMUP
        for r in bsum["runs"]), "GATEWAY_V2_BENCHMARK_MISMATCH", "runs")
    expected_agg = gw.aggregate_runs(bsum["runs"])
    _need(bsum["canonical"] == expected_agg and bench["canonical_p50_ms"]
          == expected_agg["canonical_p50_ms"], "GATEWAY_V2_BENCHMARK_MISMATCH", "aggregation")
    memory = _json(root, f"{REPORT_DIR}/memory_benchmark.json")
    _need(memory["semantics"] == "peak/high-water process RSS during benchmark process",
          "GATEWAY_V2_MEMORY_SEMANTICS")
    checks["benchmark_records"] = True
    return {"status": "PASS", "checks": checks}


__all__ = ["GatewayArtifactV2VerifyError", "check_manifest_constants", "verify_gateway_artifact_v2"]
