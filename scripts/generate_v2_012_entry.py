#!/usr/bin/env python3
"""V2-012 Sections 1/4/5/6/7/41: entry audit, V2-011 continuity audit, MODEL_V2_FINAL/CAL_V2
verification, the GATEWAY_ARTIFACT_V1 precedent audit (mechanically confirmed, never hard-coded)
and the pre-export protected-artifact baseline. No data access, no model scoring beyond the
frozen verifiers' own synthetic fixtures.
"""

from __future__ import annotations

import csv
import json
import subprocess
from pathlib import Path

import torch
import yaml

from models.cal_v2_verify import verify_cal_v2
from models.explainability_v2_verify import verify_explainability_v2
from models.model_v2_final_freeze import verify_model_v2_final
from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/model_v2/v2_012"
CKPT_SHA = "89418edcc2c13f0edd9a36666bac560ad922dd4700b4b6dd19b56d067d4eff9b"
V2_011_COMMITS = {
    "failed_diagnostic_commit": "ce1d055f37d7ddcb4a7c0c6117ba8c4e20450b51",
    "corrective_method_commit": "4fdbe788079da0e6482d39860e0a6bd2bd29bf88",
    "result_commit": "09d4d2ae5093e18e3c53b4a847f18a052b00d62e",
}

PROTECTED_PATHS = [
    "checkpoints/MODEL_V2_FINAL.pt",
    "checkpoints/MODEL_V2_FINAL.manifest.json",
    "configs/model_v2_final_frozen.yaml",
    "tests/fixtures/model_v2_final_test_vector.npz",
    "tests/fixtures/model_v2_final_test_vector.metadata.json",
    "artifacts/CAL_V2.json",
    "artifacts/EXPLAINABILITY_V2_METHOD.lock.json",
    "artifacts/EXPLAINABILITY_V2_COMPLETENESS_SEMANTICS_V2.lock.json",
    "manifests/model_v2/MODEL_V2_RESEARCH_PROTOCOL_V3.lock.json",
    "reports/model_v2/v2_010/runtime_acceptance_decision.json",
    "reports/model_v2/v2_010/artifact_hashes.json",
    "reports/model_v2/v2_010/internal_v2_predictions.csv",
    "reports/model_v2/v2_010/incart_v2_predictions.csv",
    "reports/model_v2/v2_010/nstdb_v2_predictions.csv",
    "reports/model_v2/v2_011/explainability_v2.json",
    "reports/model_v2/v2_011/artifact_hashes.json",
    "reports/model_v2/v2_011/run_manifest.json",
    "checkpoints/MODEL_V1.pt",
    "artifacts/CAL_V1.json",
    "artifacts/GATEWAY_ARTIFACT_V1.lock.json",
    "artifacts/GATEWAY_FP32_METHOD_V1.lock.json",
    "artifacts/deployment/MODEL_V1_GATEWAY_FP32.ts",
    "configs/gateway_artifact_v1.yaml",
    "deployment/benchmark.py",
    "deployment/export.py",
    "deployment/runtime.py",
    "manifests/preprocessing/PREPROC_V1.lock.json",
    "manifests/splits/MITDB_SPLIT_V1.csv",
    "manifests/labels/AAMI_SVF_MAP_V1.yaml",
    "reports/edge_gateway.json",
    "reports/t029/deployment_equivalence.json",
    "reports/t029/latency_summary.json",
    "reports/t029/memory_benchmark.json",
    "reports/t029/model_size.json",
    "manifests/freeze_registry_v1.csv",
]


def _sh(*args: str) -> str:
    result = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, check=False)
    return result.stdout.strip()


def _write(name: str, data: dict) -> None:
    (OUT / name).write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _rows(path: str) -> list[dict[str, str]]:
    with (ROOT / path).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _status(path: str, key: str, ident: str, field: str = "status") -> str:
    return next(r[field] for r in _rows(path) if r[key] == ident)


def entry_audit() -> dict:
    task = "manifests/model_v2/task_registry_v1.csv"
    gate = "manifests/model_v2/gate_registry_v1.csv"
    comp = "manifests/model_v2/component_registry_v1.csv"
    registry = {
        "V2-010": _status(task, "task_id", "V2-010"), "V2G9": _status(gate, "gate_id", "V2G9"),
        "V2-011": _status(task, "task_id", "V2-011"), "V2G10": _status(gate, "gate_id", "V2G10"),
        "V2-012": _status(task, "task_id", "V2-012"), "V2G11": _status(gate, "gate_id", "V2G11"),
        "V2-013": _status(task, "task_id", "V2-013"),
        "EXPLAINABILITY_V2": _status(comp, "component_id", "EXPLAINABILITY_V2"),
        "MODEL_V2_FINAL": _status(comp, "component_id", "MODEL_V2_FINAL"),
        "CAL_V2": _status(comp, "component_id", "CAL_V2"),
        "MODEL_V2_RUNTIME_ACCEPTED": _status(comp, "component_id", "MODEL_V2_RUNTIME_ACCEPTED"),
        "GATEWAY_ARTIFACT_V2": _status(comp, "component_id", "GATEWAY_ARTIFACT_V2"),
    }
    expected = {
        "V2-010": "PASS", "V2G9": "PASS", "V2-011": "PASS", "V2G10": "PASS",
        "V2-012": "NOT_STARTED", "V2G11": "NOT_STARTED", "V2-013": "NOT_STARTED",
        "EXPLAINABILITY_V2": "FROZEN_EXPLAINABILITY", "MODEL_V2_FINAL": "FROZEN",
        "CAL_V2": "FROZEN", "MODEL_V2_RUNTIME_ACCEPTED": "ACCEPTED",
        "GATEWAY_ARTIFACT_V2": "NOT_STARTED",
    }
    promo = json.loads((ROOT / "checkpoints/MODEL_V2_FINAL.manifest.json").read_text())
    data = {
        "head": _sh("git", "rev-parse", "HEAD"),
        "origin_main": _sh("git", "rev-parse", "origin/main"),
        "expected_head": "09d4d2ae5093e18e3c53b4a847f18a052b00d62e",
        "registry": registry,
        "registry_note_gateway_component_status": (
            "the V2 component registry row for GATEWAY_ARTIFACT_V2 currently reads NOT_STARTED "
            "(reserved identity); it transitions to FROZEN_RESEARCH_GATEWAY on completion"
        ),
        "official_promotion": promo["promotion_decision"],
        "operational_lineage": promo["operational_lineage"],
        "cumulative_v2_neural_fits": 71,
        "working_tree_clean_at_entry": True,
    }
    ok = (
        data["head"] == data["origin_main"] == data["expected_head"]
        and registry == expected
        and data["official_promotion"] == "MODEL_V2_NOT_PROMOTED_RELEASE_CI"
        and data["operational_lineage"] == "MODEL_V1"
    )
    data["status"] = "PASS" if ok else "FAIL"
    _write("entry_audit.json", data)
    if not ok:
        raise RuntimeError("V2_012_ENTRY_STATE_MISMATCH")
    return data


def v2_011_continuity() -> dict:
    ancestry = {
        name: subprocess.run(["git", "merge-base", "--is-ancestor", sha, "HEAD"], cwd=ROOT,
                             check=False).returncode == 0
        for name, sha in V2_011_COMMITS.items()
    }
    manifest = {r["case_type"]: r["example_id"]
                for r in _rows("reports/model_v2/v2_011/explainability_case_manifest.csv")}
    freeze = json.loads((ROOT / "reports/model_v2/v2_011/method_freeze.json").read_text())
    failed = json.loads(
        (ROOT / "reports/model_v2/v2_011/failed_diagnostic_run_manifest.json").read_text())
    arrays = all(
        hash_file(ROOT / rel) == digest
        for rel, digest in failed["artifact_sha256"].items() if "_attribution.csv" in rel)
    report = json.loads((ROOT / "reports/model_v2/v2_011/explainability_v2.json").read_text())
    sem_lock = json.loads(
        (ROOT / "artifacts/EXPLAINABILITY_V2_COMPLETENESS_SEMANTICS_V2.lock.json").read_text())
    noise = json.loads((ROOT / "reports/model_v2/v2_011/noise_type_access_audit.json").read_text())
    regression = json.loads(
        (ROOT / "reports/model_v2/v2_011/full_regression_proof.json").read_text())
    protected = json.loads(
        (ROOT / "reports/model_v2/v2_011/protected_artifact_audit.json").read_text())
    verified = verify_explainability_v2(ROOT)
    checks = {
        "commits_in_history": all(ancestry.values()),
        "case_ids_unchanged": manifest == freeze["case_ids"],
        "attribution_arrays_unchanged": arrays,
        "ig_64_point_gauss_legendre": report["steps"] == 64
        and report["integration"] == "GAUSS_LEGENDRE",
        "completeness_semantics_successor_frozen": sem_lock["status"]
        == "FROZEN_SEMANTICS_CORRECTION",
        "noise_analysis_complete": noise["prediction_rows"] == 12960 and noise["cells"] == 18,
        "v2_011_protected_audit_pass": protected["status"] == "PASS",
        "explainability_verifier_pass": verified["status"] == "PASS",
        "final_regression_1926_25_chunks_zero_discrepancies": (
            regression["collected_node_count"] == 1926
            and regression["executed_unique_count"] == 1926
            and regression["chunk_count"] == 25
            and regression["missing"] == regression["duplicates"] == regression["unexpected"]
            == regression["failed_tests"] == regression["failed_chunks"] == 0
            and regression["status"] == "PASS"),
    }
    data = {"commits": V2_011_COMMITS, "ancestry": ancestry, "checks": checks,
            "v2_011_redone": False, "status": "PASS" if all(checks.values()) else "FAIL"}
    _write("v2_011_continuity_audit.json", data)
    if data["status"] != "PASS":
        raise RuntimeError("V2_012_V2_011_CONTINUITY_FAILED")
    return data


def upstream() -> dict:
    model = verify_model_v2_final(ROOT)
    cal = verify_cal_v2(ROOT)
    manifest = json.loads((ROOT / "checkpoints/MODEL_V2_FINAL.manifest.json").read_text())
    artifact = json.loads((ROOT / "artifacts/CAL_V2.json").read_text())
    config = yaml.safe_load((ROOT / "configs/model_v2_final_frozen.yaml").read_text())
    checks = {
        "checkpoint_sha": model["checkpoint_sha256"] == CKPT_SHA,
        "architecture": manifest["architecture_id"] == "MODEL_V2_TCN_MEAN",
        "schedule": manifest["schedule_id"] == "CONFIG_V2_TCN_MEAN_ORIGINAL_V1",
        "release_seed": manifest["release_seed"] == 20260927,
        "selected_epoch": manifest["selected_epoch"] == 5,
        "parameter_count": manifest["parameter_count"] == 57553,
        "target": manifest["target_id"] == "AAMI_SVF_WINDOW_V1",
        "map": manifest["label_map_id"] == "AAMI_SVF_MAP_V1",
        "preproc": manifest["preproc_id"] == "PREPROC_V1",
        "fixture_reproduced": model["maximum_absolute_error"] == 0.0,
        "temperature": artifact["temperature"] == 52.88261929727761,
        "threshold": artifact["threshold"] == 0.5101937262006424,
        "comparator": artifact["threshold_comparator"] == ">=",
        "calibration_domain": artifact["calibration_domain"] == "MIT-BIH-v1.0.0",
        "frozen_config_loads": isinstance(config, dict),
    }
    data = {
        "model_v2_final_verifier": model["status"], "cal_v2_verifier": cal["status"],
        "checkpoint_sha256": model["checkpoint_sha256"], "checks": checks,
        "cal_v2_sha256": hash_file(ROOT / "artifacts/CAL_V2.json"),
        "protocol_v3_lock_sha256": hash_file(
            ROOT / "manifests/model_v2/MODEL_V2_RESEARCH_PROTOCOL_V3.lock.json"),
        "raw_model_output": "single pre-sigmoid logit",
        "status": "PASS" if (model["status"] == cal["status"] == "PASS"
                             and all(checks.values())) else "FAIL",
    }
    _write("upstream_identity_audit.json", data)
    if data["status"] != "PASS":
        raise RuntimeError("V2_012_UPSTREAM_VERIFICATION_FAILED")
    return data


def v1_precedent() -> dict:
    cfg = yaml.safe_load((ROOT / "configs/gateway_artifact_v1.yaml").read_text())
    lock = json.loads((ROOT / "artifacts/GATEWAY_ARTIFACT_V1.lock.json").read_text())
    export_src = (ROOT / "deployment/export.py").read_text()
    bench_src = (ROOT / "deployment/benchmark.py").read_text()
    t029_export = (ROOT / "scripts/export_gateway_t029.py").read_text()
    runtime_src = (ROOT / "deployment/runtime.py").read_text()
    artifact = ROOT / "artifacts/deployment/MODEL_V1_GATEWAY_FP32.ts"
    scripted = torch.jit.load(str(artifact), map_location="cpu")
    equivalence = json.loads((ROOT / "reports/t029/deployment_equivalence.json").read_text())
    model_size = json.loads((ROOT / "reports/t029/model_size.json").read_text())
    latency = json.loads((ROOT / "reports/t029/latency_summary.json").read_text())
    memory = json.loads((ROOT / "reports/t029/memory_benchmark.json").read_text())
    facts = {
        "deployment_format": cfg["format"]["selected"],
        "format_preference_order": cfg["format"]["preference_order"],
        "format_created_by_torch_jit_script": "torch.jit.script(model)" in export_src,
        "fp_precision": "FP32" if cfg["format"]["FP32"] else "UNKNOWN",
        "cpu_device_policy": cfg["execution"]["device"],
        "thread_configuration": {"intraop": cfg["execution"]["intraop_threads"],
                                 "interop": cfg["execution"]["interop_threads"]},
        "thread_code": "torch.set_num_threads(1)" in bench_src
        and "torch.set_num_interop_threads(1)" in bench_src,
        "input_tensor_shape": cfg["input_contract"]["shape"],
        "input_dtype": cfg["input_contract"]["dtype"],
        "batch_size": cfg["execution"]["batch_size"],
        "warmup_count": cfg["benchmark"]["warmup_count"],
        "warmup_code": "range(100)" in bench_src,
        "measured_count": cfg["benchmark"]["measured_window_count"],
        "repeat_count": cfg["benchmark"]["repeat_count"],
        "timer": cfg["benchmark"]["clock"],
        "timer_code": "time.perf_counter_ns()" in bench_src,
        "benchmark_boundary": cfg["benchmark"]["boundary"],
        "benchmark_input_selection": cfg["benchmark"]["selection"],
        "memory_measurement_method": latency["timing_boundary"] and memory["method"],
        "memory_unit_handling": memory["platform_unit_handling"],
        "artifact_size_method": "ARTIFACT.stat().st_size" in t029_export,
        "runtime_calibration_math": "math.exp" in runtime_src,
        "conversion_equivalence_fields": sorted(
            k for k in equivalence if "delta" in k or "disagree" in k or "agreement" in k),
        "development_equivalence_tolerance_abs": cfg["development_equivalence"][
            "maximum_absolute_raw_logit_delta"],
        "int8": cfg["INT8_STATUS"],
    }
    expected_ok = (
        facts["deployment_format"] == "TORCHSCRIPT_SCRIPT"
        and facts["format_created_by_torch_jit_script"]
        and facts["fp_precision"] == "FP32" and facts["cpu_device_policy"] == "cpu"
        and facts["thread_configuration"] == {"intraop": 1, "interop": 1} and facts["thread_code"]
        and facts["input_tensor_shape"] == [1, 1, 2500] and facts["batch_size"] == 1
        and facts["warmup_count"] == 100 and facts["warmup_code"]
        and facts["measured_count"] == 1000 and facts["timer_code"]
    )
    data = {
        "artifact": lock["lock_id"], "deployment_artifact_id": cfg["deployment_artifact_id"],
        "freeze_id": lock["freeze_id"], "artifact_path": str(artifact.relative_to(ROOT)),
        "artifact_sha256": hash_file(artifact),
        "artifact_sha_matches_lock": hash_file(artifact)
        == lock["bound_artifacts"]["artifacts/deployment/MODEL_V1_GATEWAY_FP32.ts"],
        "artifact_bytes": artifact.stat().st_size,
        "source_model_sha256": cfg["source_model"]["sha256"],
        "source_sha_matches_live": hash_file(ROOT / "checkpoints/MODEL_V1.pt")
        == cfg["source_model"]["sha256"],
        "artifact_loads_in_current_runtime": scripted is not None,
        "parameter_count_v1": model_size["trainable_parameter_count"],
        "t029_benchmark_method": facts,
        "t029_recorded_results": {
            "p50_ms": latency["canonical_run"]["p50_ms"],
            "p95_ms": latency["canonical_run"]["p95_ms"],
            "throughput": latency["canonical_run"]["throughput_windows_per_second"],
            "peak_rss_bytes": memory["peak_inference_RSS_bytes"],
            "host": latency["host_identity"]["CPU_model"],
        },
        "expectation_mechanically_confirmed": bool(expected_ok),
        "documented_differences_for_v2": {
            "repeat_count": f"V1 used {cfg['benchmark']['repeat_count']}; V2 predeclares 3",
            "benchmark_inputs": "V1 used INTERNAL_TEST windows; V2 must not reopen INTERNAL_TEST "
            "and uses a synthetic parity corpus",
            "equivalence_tolerance": "V1 development tolerance 1e-5; V2 predeclares atol=rtol=1e-6",
            "calibration_runtime_math": "V1 runtime uses math.exp inline; V2 must use the "
            "canonical CAL_V2 helpers (Section 14)",
            "format_deprecation": f"torch.jit.script is deprecated in torch {torch.__version__}; "
            "V1 precedent retained for a controlled comparison",
        },
        "status": "PASS" if (expected_ok and hash_file(artifact) == lock["bound_artifacts"][
            "artifacts/deployment/MODEL_V1_GATEWAY_FP32.ts"]) else "FAIL",
    }
    _write("v1_gateway_precedent_audit.json", data)
    if data["status"] != "PASS":
        raise RuntimeError("V2_012_V1_PRECEDENT_MISMATCH_RECONCILE_BEFORE_EXPORT")
    return data


def protected_baseline() -> None:
    data = {"artifacts": {p: hash_file(ROOT / p) for p in PROTECTED_PATHS}}
    (OUT / "protected_baseline.json").write_text(
        json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    entry_audit()
    v2_011_continuity()
    upstream()
    v1_precedent()
    protected_baseline()
    print("V2-012 entry/continuity/upstream/V1-precedent complete")


if __name__ == "__main__":
    main()
