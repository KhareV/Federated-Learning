"""V2-012 post-export tests: canonical artifact, parity, benchmark method adherence, verifier,
tamper, immutability, scope, registry transition."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest
import torch

import deployment.gateway_v2 as gw
from models.gateway_artifact_v2_verify import verify_gateway_artifact_v2
from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/model_v2/v2_012"


def _load(name: str) -> dict:
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def _manifest() -> dict:
    return json.loads((ROOT / gw.MANIFEST_PATH).read_text())


def test_canonical_artifact_identity_and_contract() -> None:
    manifest = _manifest()
    artifact = ROOT / gw.ARTIFACT_PATH
    assert hash_file(artifact) == manifest["artifact"]["sha256"]
    assert artifact.stat().st_size == manifest["artifact"]["bytes"]
    assert manifest["status"] == "FROZEN_RESEARCH_GATEWAY"
    assert manifest["artifact"]["format"] == "TORCHSCRIPT_SCRIPT"
    assert manifest["artifact"]["precision"] == "FP32" and manifest["int8"] == "NOT_EVALUATED"
    module = gw.load_artifact(artifact)
    assert gw.trainable_parameter_count(module) == 57553
    sig = gw.artifact_signature(module)
    assert sig["output_shape_batch_1"] == [1, 1] and sig["output_semantics"] == (
        "RAW_PRE_SIGMOID_LOGIT")
    assert hash_file(ROOT / "artifacts/deployment/MODEL_V1_GATEWAY_FP32.ts") == (
        "2b3768a7c075d02b19a8db425107970358630e8e4b9cef3ab458fc7c7fcd46a4")


def test_export_audit_single_candidate_no_alternative_formats() -> None:
    audit = _load("export_audit.json")
    assert audit["candidates_attempted"] == 1 and audit["export_api"] == "torch.jit.script"
    assert not (audit["trace_attempted"] or audit["onnx_attempted"] or audit["int8_attempted"])
    assert audit["format_selected_before_any_benchmark"] is True
    assert audit["trainable_parameter_count"] == 57553 and audit["status"] == "PASS"


def test_export_reproducibility_reported_honestly() -> None:
    repro = _load("artifact_reproducibility.json")
    assert repro["status"] == "PASS"
    assert repro["semantic_reproducibility"] is True
    assert repro["fixture_and_corpus_logits_identical_across_exports"] is True
    if not repro["byte_reproducible"]:
        assert repro["archive_difference_explanation"]
        for comparison in repro["comparisons"].values():
            assert comparison["differing_archive_members"]
            assert comparison["state_values_identical"] and comparison["jit_code_identical"]


def test_fixture_and_corpus_parity() -> None:
    fixture = _load("canonical_fixture_parity.json")
    assert fixture["status"] == "PASS" and fixture["rows"] == 3
    assert fixture["fixture_inputs_or_outputs_modified"] is False
    summary = _load("synthetic_corpus_parity_summary.json")
    assert summary["rows"] == 1000 and summary["all_finite"] and summary["allclose"]
    assert summary["shape_mismatches"] == 0
    assert summary["threshold_decision_disagreements"] == 0
    assert summary["tolerance"] == {"atol": 1e-6, "rtol": 1e-6}
    assert summary["no_scientific_metrics_reported"] is True
    assert not any(k in summary for k in ("AUPRC", "AUROC", "F1", "sensitivity", "accuracy"))
    with (OUT / "synthetic_corpus_parity.csv").open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 1000
    assert all(r["native_prediction"] == r["gateway_prediction"] for r in rows)
    assert max(float(r["abs_delta"]) for r in rows) == summary["max_abs_logit_delta"]


def test_calibration_wrapper_parity() -> None:
    data = _load("calibration_wrapper_parity.json")
    assert data["status"] == "PASS"
    assert data["wrapper_vs_helper_threshold_disagreements"] == 0
    assert data["formulas_duplicated_in_exporter"] is False
    assert data["temperature_or_threshold_baked_into_weights"] is False


def test_benchmark_followed_the_predeclared_method() -> None:
    summary = _load("benchmark_summary.json")
    assert len(summary["runs"]) == 3
    for run in summary["runs"]:
        assert run["warmup_count"] == 100 and run["measured_count"] == 1000
        assert run["p50_ms"] > 0 and run["p95_ms"] >= run["p50_ms"]
    assert summary["canonical"] == gw.aggregate_runs(summary["runs"])
    assert summary["canonical"]["fastest_run_selected"] is False
    assert summary["performance_target_invented"] is False
    assert summary["threads"] == {"intraop": 1, "interop": 1}
    with (OUT / "benchmark_latency_samples.csv").open(newline="") as handle:
        samples = list(csv.DictReader(handle))
    v2 = [s for s in samples if s["gateway"] == "v2"]
    assert len(v2) == 3000 and len(samples) == 6000
    memory = _load("memory_benchmark.json")
    assert memory["semantics"] == "peak/high-water process RSS during benchmark process"
    assert memory["canonical_peak_high_water_process_RSS_bytes"] == max(
        memory["benchmark_process_peak_RSS_bytes_per_run"])


def test_matched_v1_comparison_is_descriptive_only() -> None:
    data = _load("matched_v1_v2_gateway_benchmark.json")
    assert data["v1_available"] is True and data["v1_artifact_sha256_matches_frozen_lock"]
    assert "not used for model choice" in data["policy"]
    assert data["v2_trainable_parameters"] == 57553 and data["v1_trainable_parameters"] == 13185
    assert len(data["v1_runs"]) == 3 and len(data["v2_runs"]) == 3


def test_verifier_passes_and_all_tampers_detected() -> None:
    assert verify_gateway_artifact_v2(ROOT)["status"] == "PASS"
    tamper = _load("tamper_test_results.json")
    assert tamper["status"] == "PASS" and tamper["all_detected"] is True
    assert tamper["canonical_artifacts_unmodified"] is True and tamper["mutation_count"] >= 20
    assert _load("gateway_verification.json")["status"] == "PASS"


def test_wrapper_runs_on_canonical_artifact_with_manifest_verification() -> None:
    runtime = gw.GatewayV2Runtime(ROOT)
    window = gw.load_parity_corpus(ROOT)[8:9]
    result = runtime.infer(window)
    with torch.inference_mode():
        from models.model_v2_final_freeze import load_model_v2_final

        native, _ = load_model_v2_final(ROOT)
        assert result.raw_logit == pytest.approx(float(native(torch.from_numpy(window))[0, 0]),
                                                 abs=1e-6)
    assert result.model_id == "MODEL_V2_FINAL" and result.calibration_id == "CAL_V2"


def test_integrity_audits_pass() -> None:
    for name in ("method_immutability_audit", "protected_artifact_audit", "scope_audit"):
        assert _load(f"{name}.json")["status"] == "PASS"
    scope = _load("scope_audit.json")
    for key in ("training", "api_changed", "frontend_changed", "runtime_default_changed",
                "alert_policy_changed", "gateway_artifact_v1_changed",
                "int8_or_quantization_attempted"):
        assert scope[key] is False
    assert scope["firewall_prefix_hits"] == [] and scope["new_neural_fits"] == 0
    for key in ("train_waveform_access", "validation_access", "calibration_waveform_access",
                "internal_test_access", "incart_access", "nstdb_access", "bidmc_access",
                "wearable_access", "hardware_work"):
        assert scope[key] == 0
    assert all(scope["one_shot_guards_unchanged_since_entry"].values())


def test_status_preserved_in_manifest_and_run_manifest() -> None:
    sem = _manifest()["status_semantics"]
    assert sem == {"MODEL_V2_RUNTIME_ACCEPTED": "ACCEPTED",
                   "official_validation_promotion": "MODEL_V2_NOT_PROMOTED_RELEASE_CI",
                   "operational_lineage": "MODEL_V1"}
    run = _load("run_manifest.json")
    assert run["status"] == "PASS" and run["operational_lineage"] == "MODEL_V1"
    assert run["new_neural_fits"] == 0 and run["cumulative_neural_fits"] == 71


def test_registry_transition_and_preserved_statuses() -> None:
    def rows(path: str, key: str) -> dict[str, dict[str, str]]:
        with (ROOT / path).open(newline="", encoding="utf-8") as handle:
            return {r[key]: r for r in csv.DictReader(handle)}

    tasks = rows("manifests/model_v2/task_registry_v1.csv", "task_id")
    gates = rows("manifests/model_v2/gate_registry_v1.csv", "gate_id")
    comps = rows("manifests/model_v2/component_registry_v1.csv", "component_id")
    assert tasks["V2-012"]["status"] == "PASS" and gates["V2G11"]["status"] == "PASS"
    assert tasks["V2-013"]["status"] == "NOT_STARTED" and gates["V2G12"]["status"] == "NOT_STARTED"
    assert comps["GATEWAY_ARTIFACT_V2"]["status"] == "FROZEN_RESEARCH_GATEWAY"
    assert comps["MODEL_V2_RUNTIME_ACCEPTED"]["status"] == "ACCEPTED"
    assert comps["MODEL_V2_FINAL"]["status"] == "FROZEN" and comps["CAL_V2"]["status"] == "FROZEN"
    assert comps["EXPLAINABILITY_V2"]["status"] == "FROZEN_EXPLAINABILITY"
    with (ROOT / "manifests/freeze_registry_v1.csv").open(newline="") as handle:
        assert len(list(csv.DictReader(handle))) == 15  # canonical registry untouched


def test_artifact_hashes_self_consistent() -> None:
    for rel, digest in _load("artifact_hashes.json")["artifacts"].items():
        assert hash_file(ROOT / rel) == digest, rel
