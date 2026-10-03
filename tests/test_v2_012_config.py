"""V2-012 pre-export tests: entry/precedent audits, the deterministic synthetic parity corpus,
equivalence/tolerance behaviour, CAL_V2 wrapper semantics, stub-artifact runtime and verifier
checks, benchmark mechanics, scope, and frozen-config bindings -- no canonical export or
benchmark number exists when these run."""

from __future__ import annotations

import ast
import json
import shutil
from pathlib import Path

import numpy as np
import pytest
import torch
import yaml

import deployment.gateway_v2 as gw
from deployment.benchmark import latency_summary, max_rss_bytes
from models.gateway_artifact_v2_verify import (
    GatewayArtifactV2VerifyError,
    check_manifest_constants,
    verify_gateway_artifact_v2,
)
from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
V2_012 = ROOT / "reports/model_v2/v2_012"
CFG = yaml.safe_load((ROOT / "configs/model_v2/gateway_artifact_v2.yaml").read_text())


def _load(name: str) -> dict:
    return json.loads((V2_012 / name).read_text(encoding="utf-8"))


# ---- audits ----------------------------------------------------------------------------


def test_entry_continuity_upstream_audits_pass() -> None:
    entry = _load("entry_audit.json")
    assert entry["status"] == "PASS" and entry["head"] == entry["origin_main"]
    assert entry["registry"]["V2-012"] == "NOT_STARTED"  # state recorded AT ENTRY
    cont = _load("v2_011_continuity_audit.json")
    assert cont["status"] == "PASS" and all(cont["checks"].values()) and not cont["v2_011_redone"]
    up = _load("upstream_identity_audit.json")
    assert up["status"] == "PASS" and all(up["checks"].values())


def test_v1_precedent_mechanically_confirmed() -> None:
    audit = _load("v1_gateway_precedent_audit.json")
    assert audit["status"] == "PASS" and audit["expectation_mechanically_confirmed"] is True
    m = audit["t029_benchmark_method"]
    assert m["deployment_format"] == "TORCHSCRIPT_SCRIPT" and m["fp_precision"] == "FP32"
    assert m["thread_configuration"] == {"intraop": 1, "interop": 1}
    assert m["warmup_count"] == 100 and m["measured_count"] == 1000
    assert m["timer"] == "time.perf_counter_ns"
    assert audit["artifact_sha_matches_lock"] and audit["source_sha_matches_live"]
    assert set(audit["documented_differences_for_v2"]) >= {
        "repeat_count", "benchmark_inputs", "equivalence_tolerance", "calibration_runtime_math"}


# ---- parity corpus -----------------------------------------------------------------------


def test_parity_corpus_deterministic_closed_and_synthetic() -> None:
    a, b = gw.generate_parity_corpus(), gw.generate_parity_corpus()
    assert a.shape == (1000, 1, 2500) and a.dtype == np.float32 and np.array_equal(a, b)
    assert np.isfinite(a).all()
    edge = a[:8, 0, :]
    assert not edge[0].any() and (edge[1] == 1).all() and (edge[2] == -1).all()
    assert edge[3][0] == -3 and edge[3][-1] == 3 and edge[4][0] == 3 and edge[4][-1] == -3
    assert np.count_nonzero(edge[7]) == 1 and edge[7][1250] == 1.0
    assert np.abs(a[8:]).max() <= 6.0
    rng = np.random.Generator(np.random.PCG64(20260927))
    expected = np.clip(rng.standard_normal((992, 2500)), -6, 6).astype(np.float32)
    assert np.array_equal(a[8:, 0, :], expected)
    assert 0.9 < float(a[8:].std()) < 1.1  # not re-standardized per window
    assert not np.allclose(a[8:, 0, :].std(axis=1), 1.0, atol=1e-6)


def test_frozen_corpus_file_matches_generator_and_config() -> None:
    windows = gw.load_parity_corpus(ROOT)
    assert np.array_equal(windows, gw.generate_parity_corpus())
    assert hash_file(ROOT / gw.PARITY_CORPUS_PATH) == CFG["parity_corpus"]["npz_sha256"]
    assert gw.corpus_content_sha256(windows) == CFG["parity_corpus"]["windows_content_sha256"]
    with np.load(ROOT / gw.PARITY_CORPUS_PATH, allow_pickle=False) as data:
        assert int(data["seed_int64"][0]) == 20260927
        assert list(data["shape_int64"]) == [1000, 1, 2500]
        assert bytes(data["dtype_utf8"][0]).decode() == "float32"
        assert bytes(data["windows_content_sha256_utf8"][0]).decode() == (
            CFG["parity_corpus"]["windows_content_sha256"])
    manifest = _load("parity_corpus_manifest.json")
    assert manifest["status"] == "PASS" and manifest["scientific_metrics_reported"] is False
    assert manifest["frozen_before_deployment_output_inspection"] is True


# ---- equivalence / tolerance / calibration wrapper ---------------------------------------------


def test_tolerance_is_frozen_and_behaves_at_boundary() -> None:
    assert (gw.ATOL, gw.RTOL) == (1e-6, 1e-6)
    assert CFG["equivalence"]["atol"] == 1e-6 and CFG["equivalence"]["rtol"] == 1e-6
    native = np.zeros(10)
    assert gw.compare_logits(native, native + 5e-7)["allclose"] is True
    assert gw.compare_logits(native, native + 5e-6)["allclose"] is False
    big = np.full(10, 100.0)
    assert gw.compare_logits(big, big + 5e-5)["allclose"] is True   # rtol 1e-6 * 100 = 1e-4
    out = gw.compare_logits(np.array([1.0, 2.0]), np.array([1.0, 2.5]))
    assert out["max_abs_delta"] == pytest.approx(0.5)
    assert out["max_rel_delta"] == pytest.approx(0.25)


def test_compare_logits_detects_shape_and_nonfinite() -> None:
    assert gw.compare_logits(np.zeros(3), np.zeros(4))["shape_mismatches"] == 1
    bad = gw.compare_logits(np.zeros(3), np.array([0.0, np.nan, 0.0]))
    assert bad["allclose"] is False and bad["nonfinite_outputs"] == 1


def test_calibration_helper_matches_cal_v2_and_detects_threshold_disagreement() -> None:
    cal = json.loads((ROOT / "artifacts/CAL_V2.json").read_text())
    logits = np.array([-5.0, 0.0, 5.0])
    out = gw.calibrate_logits(logits, cal)
    assert np.allclose(out["raw_probability"], 1 / (1 + np.exp(-logits)))
    scaled = logits / cal["temperature"]
    assert np.allclose(out["calibrated_probability"], 1 / (1 + np.exp(-scaled)))
    assert list(out["prediction"]) == [int(p >= cal["threshold"]) for p in
                                        out["calibrated_probability"]]
    boundary = cal["temperature"] * float(np.log(cal["threshold"] / (1 - cal["threshold"])))
    parity = gw.calibration_parity(np.array([boundary - 1e-3]), np.array([boundary + 1e-3]), cal)
    assert parity["threshold_decision_disagreements"] == 1
    assert gw.calibration_parity(logits, logits, cal)["threshold_decision_disagreements"] == 0


def test_exporter_does_not_duplicate_calibration_formulas() -> None:
    for rel in ("scripts/export_gateway_v2.py", "deployment/gateway_v2.py"):
        source = (ROOT / rel).read_text()
        assert "np.exp" not in source and "math.exp" not in source
        assert "1.0 / (1.0" not in source and "expit" not in source
    wrapper = (ROOT / "deployment/gateway_v2.py").read_text()
    assert "source_domain_calibrated_probability(" in wrapper
    assert "apply_operating_threshold(" in wrapper and "raw_probability_from_logit(" in wrapper


# ---- scriptability / stub artifact runtime -------------------------------------------------------


class _Stub(torch.nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.linear = torch.nn.Linear(2500, 1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.linear(x.reshape(x.shape[0], -1))


def _stub_root(tmp_path: Path, mode: str = "export_audit") -> tuple[Path, Path]:
    torch.manual_seed(0)
    artifact = tmp_path / gw.ARTIFACT_PATH
    artifact.parent.mkdir(parents=True)
    torch.jit.save(torch.jit.script(_Stub().eval()), str(artifact))
    for rel in ("checkpoints/MODEL_V2_FINAL.pt", "artifacts/CAL_V2.json"):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, tmp_path / rel)
    (tmp_path / "reports/model_v2/v2_012").mkdir(parents=True)
    (tmp_path / gw.EXPORT_AUDIT_PATH).write_text(
        json.dumps({"artifact_sha256": hash_file(artifact)}))
    return tmp_path, artifact


def test_real_model_is_scriptable_without_alternative_format() -> None:
    from models.model_v2_final_freeze import load_model_v2_final

    model, _ = load_model_v2_final(ROOT)
    scripted = torch.jit.script(model.eval())
    x = torch.zeros(1, 1, 2500)
    with torch.inference_mode():
        assert torch.equal(scripted(x), model(x))


def test_runtime_input_contract_rejection(tmp_path: Path) -> None:
    root, _ = _stub_root(tmp_path)
    runtime = gw.GatewayV2Runtime(root, verify="export_audit")
    good = np.zeros((1, 1, 2500), dtype=np.float32)
    result = runtime.infer(good)
    assert result.model_id == "MODEL_V2_FINAL"
    assert result.gateway_artifact_id == "GATEWAY_ARTIFACT_V2"
    assert result.calibration_id == "CAL_V2" and result.preproc_id == "PREPROC_V1"
    assert result.calibration_domain == "MIT-BIH-v1.0.0"
    assert result.target_id == "AAMI_SVF_WINDOW_V1"
    assert np.isfinite(result.raw_logit) and result.above_threshold == bool(
        result.thresholded_prediction)
    with pytest.raises(TypeError):
        runtime.infer(good.astype(np.float64))
    with pytest.raises(ValueError):
        runtime.infer(np.zeros((2, 1, 2500), dtype=np.float32))
    with pytest.raises(ValueError):
        runtime.infer(np.zeros((1, 2500), dtype=np.float32))
    with pytest.raises(ValueError):
        runtime.infer(np.full((1, 1, 2500), np.nan, dtype=np.float32))


def test_runtime_wrapper_equals_canonical_helper(tmp_path: Path) -> None:
    root, _ = _stub_root(tmp_path)
    runtime = gw.GatewayV2Runtime(root, verify="export_audit")
    window = np.random.default_rng(1).standard_normal((1, 1, 2500)).astype(np.float32)
    result = runtime.infer(window)
    cal = json.loads((root / "artifacts/CAL_V2.json").read_text())
    helper = gw.calibrate_logits(np.array([result.raw_logit]), cal)
    assert result.source_domain_calibrated_probability == float(helper["calibrated_probability"][0])
    assert result.thresholded_prediction == int(helper["prediction"][0])
    assert result.raw_probability == float(helper["raw_probability"][0])


def test_runtime_rejects_artifact_hash_mismatch(tmp_path: Path) -> None:
    root, artifact = _stub_root(tmp_path)
    with artifact.open("ab") as handle:
        handle.write(b"\x00")
    with pytest.raises(gw.GatewayV2Error, match="ARTIFACT_HASH_MISMATCH"):
        gw.GatewayV2Runtime(root, verify="export_audit")


def test_runtime_manifest_mode_rejects_each_mismatch(tmp_path: Path) -> None:
    root, artifact = _stub_root(tmp_path)
    good = {
        "artifact_id": "GATEWAY_ARTIFACT_V2",
        "artifact": {"sha256": hash_file(artifact)},
        "source_model": {"sha256": hash_file(root / "checkpoints/MODEL_V2_FINAL.pt")},
        "calibration": {"sha256": hash_file(root / "artifacts/CAL_V2.json")},
    }
    path = root / gw.MANIFEST_PATH

    def write(manifest: dict) -> None:
        path.write_text(json.dumps(manifest))

    write(good)
    assert gw.GatewayV2Runtime(root).artifact_sha == hash_file(artifact)
    cases = {
        "WRONG_ARTIFACT_ID": {**good, "artifact_id": "GATEWAY_ARTIFACT_V1"},
        "ARTIFACT_HASH_MISMATCH": {**good, "artifact": {"sha256": "0" * 64}},
        "SOURCE_CHECKPOINT_MISMATCH": {**good, "source_model": {"sha256": "0" * 64}},
        "CAL_V2_MISMATCH": {**good, "calibration": {"sha256": "0" * 64}},
    }
    for code, manifest in cases.items():
        write(manifest)
        with pytest.raises(gw.GatewayV2Error, match=code):
            gw.GatewayV2Runtime(root)
    with pytest.raises(gw.GatewayV2Error, match="UNKNOWN_VERIFY_MODE"):
        gw.GatewayV2Runtime(root, verify="none")


def test_artifact_comparison_reports_byte_and_semantic_identity(tmp_path: Path) -> None:
    torch.manual_seed(0)
    model = _Stub().eval()
    a, b = tmp_path / "a.ts", tmp_path / "b.ts"
    torch.jit.save(torch.jit.script(model), str(a))
    torch.jit.save(torch.jit.script(model), str(b))
    out = gw.compare_artifact_files(a, b)
    assert out["semantic_reproducibility"] is True and out["state_values_identical"] is True
    other = _Stub().eval()
    c = tmp_path / "c.ts"
    torch.jit.save(torch.jit.script(other), str(c))
    assert gw.compare_artifact_files(a, c)["state_values_identical"] is False


# ---- manifest constants (every required mutation is rejected) ----------------------------


def _good_manifest() -> dict:
    return {
        "artifact_id": "GATEWAY_ARTIFACT_V2", "deployment_artifact_id": "GATEWAY_FP32_V2",
        "status": "FROZEN_RESEARCH_GATEWAY", "owner_task": "V2-012",
        "artifact": {"format": "TORCHSCRIPT_SCRIPT", "precision": "FP32"},
        "int8": "NOT_EVALUATED", "input_shape": ["N", 1, 2500], "input_dtype": "float32",
        "output_semantics": "RAW_PRE_SIGMOID_LOGIT",
        "source_model": {"id": "MODEL_V2_FINAL", "architecture_id": "MODEL_V2_TCN_MEAN",
                         "parameter_count": 57553},
        "gateway_parameter_count": 57553, "target_id": "AAMI_SVF_WINDOW_V1",
        "map_id": "AAMI_SVF_MAP_V1", "preprocessing": {"id": "PREPROC_V1"},
        "equivalence": {"atol": 1e-6, "rtol": 1e-6},
        "synthetic_corpus_parity": {"rows": 1000, "allclose": True,
                                    "threshold_decision_disagreements": 0},
        "fixture_parity": {"rows": 3, "allclose": True},
        "status_semantics": {"operational_lineage": "MODEL_V1",
                             "official_validation_promotion": "MODEL_V2_NOT_PROMOTED_RELEASE_CI",
                             "MODEL_V2_RUNTIME_ACCEPTED": "ACCEPTED"},
        "benchmark": {"repetitions": 3, "measured_per_run": 1000, "warmup": 100},
    }


def _mutate(path: tuple, value) -> dict:
    manifest = _good_manifest()
    node = manifest
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value
    return manifest


def test_good_manifest_constants_pass() -> None:
    check_manifest_constants(_good_manifest())


@pytest.mark.parametrize("path,value", [
    (("artifact_id",), "GATEWAY_ARTIFACT_V1"),
    (("deployment_artifact_id",), "GATEWAY_FP32_V1"),
    (("status",), "NOT_FROZEN"),
    (("artifact", "format"), "ONNX"),
    (("artifact", "format"), "TORCHSCRIPT_TRACE"),
    (("artifact", "precision"), "INT8"),
    (("int8",), "ATTEMPTED"),
    (("input_shape",), ["N", 1, 2000]),
    (("input_dtype",), "float64"),
    (("output_semantics",), "CALIBRATED_PROBABILITY"),
    (("source_model", "id"), "MODEL_V1"),
    (("source_model", "architecture_id"), "MODEL_V2_TCN_MEANMAX"),
    (("source_model", "parameter_count"), 57577),
    (("gateway_parameter_count",), 13185),
    (("target_id",), "OTHER_TARGET"),
    (("map_id",), "OTHER_MAP"),
    (("preprocessing", "id"), "PREPROC_V2"),
    (("equivalence", "atol"), 1e-5),
    (("equivalence", "rtol"), 1e-3),
    (("synthetic_corpus_parity", "threshold_decision_disagreements"), 1),
    (("synthetic_corpus_parity", "allclose"), False),
    (("synthetic_corpus_parity", "rows"), 999),
    (("fixture_parity", "allclose"), False),
    (("status_semantics", "operational_lineage"), "MODEL_V2_FINAL"),
    (("status_semantics", "official_validation_promotion"), "PROMOTED"),
    (("status_semantics", "MODEL_V2_RUNTIME_ACCEPTED"), "NOT_ACCEPTED"),
    (("benchmark", "repetitions"), 1),
    (("benchmark", "measured_per_run"), 999),
    (("benchmark", "warmup"), 10),
])
def test_manifest_constant_mutations_rejected(path: tuple, value) -> None:
    with pytest.raises(GatewayArtifactV2VerifyError):
        check_manifest_constants(_mutate(path, value))


def test_verifier_fails_closed_without_artifact(tmp_path: Path) -> None:
    with pytest.raises((GatewayArtifactV2VerifyError, FileNotFoundError, OSError, RuntimeError)):
        verify_gateway_artifact_v2(tmp_path)


# ---- benchmark mechanics -----------------------------------------------------------------------


class _CountingRuntime:
    def __init__(self) -> None:
        self.calls = 0

    def infer(self, window: np.ndarray):
        self.calls += 1

        class R:
            raw_logit = 0.5
            above_threshold = False

        return R()


def test_benchmark_excludes_warmup_and_measures_exactly_1000() -> None:
    runtime = _CountingRuntime()
    latencies = gw.run_timed_loop(runtime, np.zeros((1000, 1, 2500), dtype=np.float32))
    assert runtime.calls == 1100 and len(latencies) == 1000
    assert all(v > 0 for v in latencies)
    assert (gw.WARMUP, gw.MEASURED, gw.REPETITIONS) == (100, 1000, 3)
    with pytest.raises(gw.GatewayV2Error):
        gw.run_timed_loop(runtime, np.zeros((999, 1, 2500), dtype=np.float32))


def test_latency_percentile_and_throughput_math() -> None:
    values = [(i + 1) * 1000 for i in range(1000)]  # 1..1000 microseconds in ns
    summary = gw.percentile_summary(values)
    ms = np.asarray(values) / 1e6
    assert summary["p50_ms"] == pytest.approx(float(np.percentile(ms, 50)))
    assert summary["p95_ms"] == pytest.approx(float(np.percentile(ms, 95)))
    total_s = sum(values) / 1e9
    assert summary["throughput_windows_per_second"] == pytest.approx(1000 / total_s)
    assert summary == latency_summary(values)
    with pytest.raises(ValueError):
        gw.percentile_summary(values[:-1])


def test_predeclared_aggregation_median_of_three_and_max_rss() -> None:
    runs = [
        {"p50_ms": 0.30, "p95_ms": 0.50, "throughput_windows_per_second": 3000.0,
         "benchmark_process_peak_RSS_bytes": 100},
        {"p50_ms": 0.10, "p95_ms": 0.90, "throughput_windows_per_second": 9000.0,
         "benchmark_process_peak_RSS_bytes": 300},
        {"p50_ms": 0.20, "p95_ms": 0.70, "throughput_windows_per_second": 5000.0,
         "benchmark_process_peak_RSS_bytes": 200},
    ]
    agg = gw.aggregate_runs(runs)
    assert agg["canonical_p50_ms"] == 0.20 and agg["canonical_p95_ms"] == 0.70
    assert agg["canonical_throughput_windows_per_second"] == 5000.0
    assert agg["peak_high_water_process_RSS_bytes"] == 300
    assert agg["fastest_run_selected"] is False
    with pytest.raises(gw.GatewayV2Error):
        gw.aggregate_runs(runs[:2])


def test_rss_unit_normalization(monkeypatch) -> None:
    import deployment.benchmark as bench

    class Usage:
        ru_maxrss = 2048

    monkeypatch.setattr(bench.resource, "getrusage", lambda _: Usage())
    monkeypatch.setattr(bench.sys, "platform", "darwin")
    assert max_rss_bytes() == 2048
    monkeypatch.setattr(bench.sys, "platform", "linux")
    assert max_rss_bytes() == 2048 * 1024


def test_benchmark_config_frozen_and_free_of_results() -> None:
    cfg = _load("benchmark_config.json")
    assert cfg["warmup_count"] == 100 and cfg["measured_count_per_run"] == 1000
    assert cfg["repetitions"] == 3 and cfg["clock"] == "time.perf_counter_ns"
    assert cfg["aggregation"]["fastest_run_selected"] is False
    assert cfg["frozen_before_any_measurement"] is True
    assert cfg["observed_results_included"] is False
    text = json.dumps(cfg)
    assert "canonical_p50" not in text and "throughput_windows_per_second" not in text
    assert CFG["benchmark"]["performance_target_invented"] is False
    assert CFG["memory"]["wording"] == "peak/high-water process RSS during benchmark process"


# ---- frozen method / scope --------------------------------------------------------------------


def test_config_bindings_match_live_artifacts() -> None:
    assert CFG["source_model"]["checkpoint_sha256"] == hash_file(
        ROOT / "checkpoints/MODEL_V2_FINAL.pt")
    assert CFG["source_model"]["manifest_sha256"] == hash_file(
        ROOT / "checkpoints/MODEL_V2_FINAL.manifest.json")
    assert CFG["calibration"]["sha256"] == hash_file(ROOT / "artifacts/CAL_V2.json")
    assert CFG["canonical_fixture"]["sha256"] == hash_file(
        ROOT / "tests/fixtures/model_v2_final_test_vector.npz")
    assert CFG["matched_v1_comparison"]["v1_artifact_sha256"] == hash_file(
        ROOT / "artifacts/deployment/MODEL_V1_GATEWAY_FP32.ts")
    assert CFG["format"]["selected"] == "TORCHSCRIPT_SCRIPT"
    assert CFG["format"]["precision"] == "FP32"
    assert CFG["format"]["trace_allowed"] is False and CFG["format"]["onnx_allowed"] is False
    assert CFG["INT8_STATUS"] == "NOT_EVALUATED" and CFG["quantization_search"] is False
    assert CFG["calibration"]["baked_into_model_weights"] is False
    assert CFG["output_contract"]["semantics"] == "RAW_PRE_SIGMOID_LOGIT"
    assert CFG["status_semantics"]["operational_lineage"] == "MODEL_V1"


def test_method_freeze_records_no_artifact_and_no_results() -> None:
    data = _load("method_freeze.json")
    assert data["status"] == "PASS"
    assert data["gateway_artifact_absent_at_freeze"] is True
    assert data["benchmark_or_export_result_absent_at_freeze"] is True
    assert data["v2_012_registry_status_at_freeze"] == "NOT_STARTED"
    assert data["operational_lineage"] == "MODEL_V1"


FORBIDDEN_IMPORT_PREFIXES = (
    "datasets", "evaluation.internal_test", "evaluation.external_incart", "evaluation.noise",
    "evaluation.c031", "wfdb", "api", "frontend", "federated", "training",
)


@pytest.mark.parametrize("rel", [
    "deployment/gateway_v2.py", "models/gateway_artifact_v2_verify.py",
    "scripts/export_gateway_v2.py", "scripts/run_gateway_v2_benchmark.py",
    "scripts/build_gateway_manifest_v2.py", "scripts/freeze_v2_012_method.py",
])
def test_method_code_cannot_reach_held_out_data(rel: str) -> None:
    tree = ast.parse((ROOT / rel).read_text())
    imported = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
    bad = [m for m in imported if m.startswith(FORBIDDEN_IMPORT_PREFIXES)]
    assert bad == [], bad
