"""GATEWAY_ARTIFACT_V2: CPU FP32 TorchScript gateway for MODEL_V2_FINAL (research-only).

Deployment-format equivalence and resource measurement only. The deployable model artifact
returns the RAW pre-sigmoid logit; CAL_V2 is applied downstream by the wrapper using the
canonical evaluation.calibration helpers (temperature/threshold are never baked into weights).
Format is fixed by the GATEWAY_ARTIFACT_V1 precedent (torch.jit.script, FP32) before any
benchmark; there is no benchmark-driven representation selection.
"""

from __future__ import annotations

import json
import math
import platform
import subprocess
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import torch

from deployment.benchmark import configure_cpu_threads, latency_summary, max_rss_bytes
from evaluation.calibration import (
    apply_operating_threshold,
    raw_probability_from_logit,
    source_domain_calibrated_probability,
)
from nhm.hashing import hash_file

ARTIFACT_ID = "GATEWAY_ARTIFACT_V2"
DEPLOYMENT_ARTIFACT_ID = "GATEWAY_FP32_V2"
INPUT_ID = "GATEWAY_MODEL_INPUT_V2"
MODEL_ID = "MODEL_V2_FINAL"
CALIBRATION_ID = "CAL_V2"
FORMAT = "TORCHSCRIPT_SCRIPT"
PRECISION = "FP32"
OUTPUT_SEMANTICS = "RAW_PRE_SIGMOID_LOGIT"
FROZEN_STATUS = "FROZEN_RESEARCH_GATEWAY"
ARTIFACT_PATH = "artifacts/deployment/MODEL_V2_GATEWAY_FP32.ts"
MANIFEST_PATH = "artifacts/deployment/GATEWAY_ARTIFACT_V2.manifest.json"
EXPORT_AUDIT_PATH = "reports/model_v2/v2_012/export_audit.json"
PARITY_CORPUS_PATH = "tests/fixtures/gateway_parity_corpus_v2_v1.npz"
CORPUS_ID = "GATEWAY_PARITY_CORPUS_V2_V1"
CORPUS_SEED = 20260927
CORPUS_ROWS = 1000
WINDOW_SAMPLES = 2500
CLIP = 6.0
ATOL = 1e-6
RTOL = 1e-6
WARMUP = 100
MEASURED = 1000
REPETITIONS = 3
IMPULSE_AMPLITUDE = 1.0
SINE_CYCLES = 10
TWO_SINE_CYCLES = (5, 37)


class GatewayV2Error(RuntimeError):
    """Raised for any GATEWAY_ARTIFACT_V2 contract violation."""


# ---------------------------------------------------------------------------
# Parity corpus (deterministic, synthetic, no patient data)
# ---------------------------------------------------------------------------


def generate_parity_corpus() -> np.ndarray:
    n = np.arange(WINDOW_SAMPLES, dtype=np.float64)
    edge = [
        np.zeros(WINDOW_SAMPLES),
        np.ones(WINDOW_SAMPLES),
        -np.ones(WINDOW_SAMPLES),
        np.linspace(-3.0, 3.0, WINDOW_SAMPLES),
        np.linspace(3.0, -3.0, WINDOW_SAMPLES),
        np.sin(2.0 * np.pi * SINE_CYCLES * n / WINDOW_SAMPLES),
        np.sin(2.0 * np.pi * TWO_SINE_CYCLES[0] * n / WINDOW_SAMPLES)
        + np.sin(2.0 * np.pi * TWO_SINE_CYCLES[1] * n / WINDOW_SAMPLES),
        np.zeros(WINDOW_SAMPLES),
    ]
    edge[7][WINDOW_SAMPLES // 2] = IMPULSE_AMPLITUDE
    rng = np.random.Generator(np.random.PCG64(CORPUS_SEED))
    noise = np.clip(rng.standard_normal((CORPUS_ROWS - 8, WINDOW_SAMPLES)), -CLIP, CLIP)
    windows = np.concatenate([np.stack(edge), noise]).astype(np.float32)
    return np.ascontiguousarray(windows[:, None, :])


def corpus_content_sha256(windows: np.ndarray) -> str:
    import hashlib

    return hashlib.sha256(np.ascontiguousarray(windows, dtype=np.float32).tobytes()).hexdigest()


def corpus_arrays(windows: np.ndarray) -> dict[str, np.ndarray]:
    return {
        "windows_float32": windows,
        "seed_int64": np.asarray([CORPUS_SEED], dtype=np.int64),
        "shape_int64": np.asarray(windows.shape, dtype=np.int64),
        "dtype_utf8": np.asarray(["float32"], dtype="S8"),
        "corpus_id_utf8": np.asarray([CORPUS_ID], dtype="S32"),
        "windows_content_sha256_utf8": np.asarray([corpus_content_sha256(windows)], dtype="S64"),
        "generator_utf8": np.asarray(["numpy.random.Generator(PCG64)"], dtype="S40"),
    }


def load_parity_corpus(root: Path) -> np.ndarray:
    with np.load(root / PARITY_CORPUS_PATH, allow_pickle=False) as data:
        windows = data["windows_float32"]
    if windows.shape != (CORPUS_ROWS, 1, WINDOW_SAMPLES) or windows.dtype != np.float32:
        raise GatewayV2Error("GATEWAY_PARITY_CORPUS_SHAPE_OR_DTYPE_MISMATCH")
    return windows


# ---------------------------------------------------------------------------
# Equivalence and calibration-wrapper math
# ---------------------------------------------------------------------------


def compare_logits(native: np.ndarray, gateway: np.ndarray) -> dict[str, Any]:
    native = np.asarray(native, dtype=np.float64).reshape(-1)
    gateway = np.asarray(gateway, dtype=np.float64).reshape(-1)
    shape_mismatch = native.shape != gateway.shape
    if shape_mismatch:
        return {"rows": int(native.size), "shape_mismatches": 1, "nonfinite_outputs": 0,
                "allclose": False, "max_abs_delta": None, "max_rel_delta": None}
    finite = bool(np.isfinite(native).all() and np.isfinite(gateway).all())
    delta = np.abs(native - gateway)
    denominator = np.maximum(np.abs(native), np.finfo(np.float64).tiny)
    return {
        "rows": int(native.size),
        "shape_mismatches": 0,
        "nonfinite_outputs": int((~np.isfinite(gateway)).sum() + (~np.isfinite(native)).sum()),
        "allclose": bool(finite and np.allclose(native, gateway, atol=ATOL, rtol=RTOL)),
        "max_abs_delta": float(delta.max(initial=0.0)),
        "max_rel_delta": float((delta / denominator).max(initial=0.0)),
    }


def calibrate_logits(logits: np.ndarray, cal: dict[str, Any]) -> dict[str, np.ndarray]:
    """The single canonical CAL_V2 application (no duplicated formulas)."""
    logits = np.asarray(logits, dtype=np.float64).reshape(-1)
    probability = source_domain_calibrated_probability(logits, cal)
    return {
        "raw_probability": raw_probability_from_logit(logits),
        "calibrated_probability": probability,
        "prediction": apply_operating_threshold(probability, cal),
    }


def calibration_parity(native: np.ndarray, gateway: np.ndarray, cal: dict[str, Any]) -> dict:
    a, b = calibrate_logits(native, cal), calibrate_logits(gateway, cal)
    return {
        "max_raw_probability_delta": float(
            np.abs(a["raw_probability"] - b["raw_probability"]).max()),
        "max_calibrated_probability_delta": float(
            np.abs(a["calibrated_probability"] - b["calibrated_probability"]).max()),
        "threshold_decision_disagreements": int((a["prediction"] != b["prediction"]).sum()),
    }


# ---------------------------------------------------------------------------
# Export (torch.jit.script only; no format search)
# ---------------------------------------------------------------------------


def export_gateway_artifact(root: Path, output: Path) -> dict[str, Any]:
    from models.model_v2_final_freeze import load_model_v2_final

    torch.set_num_threads(1)
    model, meta = load_model_v2_final(root)
    model.eval()
    if any(p.dtype != torch.float32 for p in model.parameters()):
        raise GatewayV2Error("GATEWAY_V2_SOURCE_NOT_FP32")
    scripted = torch.jit.script(model)
    output.parent.mkdir(parents=True, exist_ok=True)
    torch.jit.save(scripted, str(output))
    return {
        "artifact_path": str(output),
        "artifact_sha256": hash_file(output),
        "artifact_bytes": output.stat().st_size,
        "source_checkpoint_sha256": meta["checkpoint_sha256"],
        "format": FORMAT,
        "precision": PRECISION,
        "torch_version": torch.__version__,
    }


def load_artifact(path: Path) -> torch.jit.ScriptModule:
    return torch.jit.load(str(path), map_location="cpu").eval()


def trainable_parameter_count(module: torch.nn.Module) -> int:
    return sum(p.numel() for p in module.parameters() if p.requires_grad)


def artifact_signature(module: torch.jit.ScriptModule) -> dict[str, Any]:
    with torch.inference_mode():
        one = module(torch.zeros(1, 1, WINDOW_SAMPLES))
        three = module(torch.zeros(3, 1, WINDOW_SAMPLES))
    return {
        "input": "float32[N,1,2500]",
        "output_shape_batch_1": list(one.shape),
        "output_shape_batch_3": list(three.shape),
        "output_dtype": str(one.dtype),
        "output_semantics": OUTPUT_SEMANTICS,
    }


def archive_members(path: Path) -> dict[str, str]:
    import hashlib

    with zipfile.ZipFile(path) as archive:
        return {i.filename: hashlib.sha256(archive.read(i)).hexdigest() for i in archive.infolist()}


def compare_artifact_files(a: Path, b: Path) -> dict[str, Any]:
    same_bytes = hash_file(a) == hash_file(b)
    ma, mb = archive_members(a), archive_members(b)
    # archive member names embed a per-save prefix; compare by suffix after the first '/'
    def norm(members: dict[str, str]) -> dict[str, str]:
        return {name.split("/", 1)[1] if "/" in name else name: digest
                for name, digest in members.items()}

    na, nb = norm(ma), norm(mb)
    differing = sorted(k for k in set(na) | set(nb) if na.get(k) != nb.get(k))
    sa, sb = load_artifact(a), load_artifact(b)
    state_equal = set(sa.state_dict()) == set(sb.state_dict()) and all(
        torch.equal(sa.state_dict()[k], sb.state_dict()[k]) for k in sa.state_dict())
    code_equal = sa.code == sb.code
    return {
        "byte_reproducible": same_bytes,
        "archive_member_count": [len(ma), len(mb)],
        "differing_archive_members": differing,
        "state_values_identical": bool(state_equal),
        "jit_code_identical": bool(code_equal),
        "semantic_reproducibility": bool(state_equal and code_equal),
    }


# ---------------------------------------------------------------------------
# Wrapper runtime (not an API endpoint)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GatewayV2Result:
    raw_logit: float
    raw_probability: float
    source_domain_calibrated_probability: float
    threshold: float
    thresholded_prediction: int
    model_id: str
    gateway_artifact_id: str
    calibration_id: str
    calibration_domain: str
    target_id: str
    preproc_id: str

    @property
    def above_threshold(self) -> bool:
        return bool(self.thresholded_prediction)

    @property
    def calibrated_probability(self) -> float:
        return self.source_domain_calibrated_probability


class GatewayV2Runtime:
    """Strict batch-one CPU runtime; preprocessing remains upstream.

    verify="manifest" (default): artifact SHA/identity checked against the frozen manifest.
    verify="export_audit": pre-manifest mode used only while the benchmark runs.
    """

    def __init__(self, root: Path, artifact_path: Path | None = None, *,
                 verify: str = "manifest") -> None:
        self.root = root
        self.artifact_path = artifact_path or root / ARTIFACT_PATH
        self.artifact_sha = hash_file(self.artifact_path)
        source_sha = hash_file(root / "checkpoints/MODEL_V2_FINAL.pt")
        cal_sha = hash_file(root / "artifacts/CAL_V2.json")
        if verify == "manifest":
            manifest = json.loads((root / MANIFEST_PATH).read_text(encoding="utf-8"))
            if manifest.get("artifact_id") != ARTIFACT_ID:
                raise GatewayV2Error("GATEWAY_V2_WRONG_ARTIFACT_ID")
            if manifest["artifact"]["sha256"] != self.artifact_sha:
                raise GatewayV2Error("GATEWAY_V2_ARTIFACT_HASH_MISMATCH")
            if manifest["source_model"]["sha256"] != source_sha:
                raise GatewayV2Error("GATEWAY_V2_SOURCE_CHECKPOINT_MISMATCH")
            if manifest["calibration"]["sha256"] != cal_sha:
                raise GatewayV2Error("GATEWAY_V2_CAL_V2_MISMATCH")
        elif verify == "export_audit":
            audit = json.loads((root / EXPORT_AUDIT_PATH).read_text(encoding="utf-8"))
            if audit["artifact_sha256"] != self.artifact_sha:
                raise GatewayV2Error("GATEWAY_V2_ARTIFACT_HASH_MISMATCH")
        else:
            raise GatewayV2Error("GATEWAY_V2_UNKNOWN_VERIFY_MODE")
        self.calibration = json.loads((root / "artifacts/CAL_V2.json").read_text())
        self.model = load_artifact(self.artifact_path)
        self.model_sha = source_sha
        self.target_id = str(self.calibration["target_id"])
        self.preproc_id = "PREPROC_V1"

    @staticmethod
    def validate_input(window: np.ndarray) -> np.ndarray:
        array = np.asarray(window)
        if array.dtype != np.float32:
            raise TypeError("GATEWAY_MODEL_INPUT_V2 requires float32")
        if array.shape != (1, 1, WINDOW_SAMPLES):
            raise ValueError("GATEWAY_MODEL_INPUT_V2 requires shape [1,1,2500]")
        if not np.isfinite(array).all():
            raise ValueError("GATEWAY_MODEL_INPUT_V2 requires finite values")
        return np.ascontiguousarray(array)

    def infer(self, window: np.ndarray) -> GatewayV2Result:
        array = self.validate_input(window)
        with torch.inference_mode():
            logit = float(self.model(torch.from_numpy(array)).cpu().numpy()[0, 0])
        if not math.isfinite(logit):
            raise GatewayV2Error("GATEWAY_V2_NONFINITE_LOGIT")
        out = calibrate_logits(np.asarray([logit]), self.calibration)
        return GatewayV2Result(
            raw_logit=logit,
            raw_probability=float(out["raw_probability"][0]),
            source_domain_calibrated_probability=float(out["calibrated_probability"][0]),
            threshold=float(self.calibration["threshold"]),
            thresholded_prediction=int(out["prediction"][0]),
            model_id=MODEL_ID,
            gateway_artifact_id=ARTIFACT_ID,
            calibration_id=CALIBRATION_ID,
            calibration_domain=str(self.calibration["calibration_domain"]),
            target_id=self.target_id,
            preproc_id=self.preproc_id,
        )


# ---------------------------------------------------------------------------
# Benchmark helpers
# ---------------------------------------------------------------------------


def percentile_summary(latencies_ns: list[int]) -> dict[str, float | int]:
    """Canonical latency math (shared with the V1 T029 helper)."""
    return latency_summary(latencies_ns)


def median_aggregate(values: list[float]) -> float:
    return float(np.median(np.asarray(values, dtype=np.float64)))


def aggregate_runs(runs: list[dict[str, Any]]) -> dict[str, Any]:
    """Predeclared rule: median of exactly 3 run-level values; RSS = max across the runs."""
    if len(runs) != REPETITIONS:
        raise GatewayV2Error("GATEWAY_V2_BENCHMARK_REQUIRES_EXACTLY_3_REPETITIONS")
    return {
        "canonical_p50_ms": median_aggregate([r["p50_ms"] for r in runs]),
        "canonical_p95_ms": median_aggregate([r["p95_ms"] for r in runs]),
        "canonical_throughput_windows_per_second": median_aggregate(
            [r["throughput_windows_per_second"] for r in runs]),
        "peak_high_water_process_RSS_bytes": int(max(r["benchmark_process_peak_RSS_bytes"]
                                                     for r in runs)),
        "aggregation_rule": "median of 3 run-level p50/p95/throughput; max RSS across 3 processes",
        "fastest_run_selected": False,
    }


def run_timed_loop(runtime: Any, windows: np.ndarray) -> list[int]:
    """100 warm-up calls (excluded) then exactly 1000 measured batch-1 calls."""
    if windows.shape != (MEASURED, 1, WINDOW_SAMPLES):
        raise GatewayV2Error("GATEWAY_V2_BENCHMARK_INPUT_CLOSURE")
    for index in range(WARMUP):
        runtime.infer(windows[index % MEASURED : index % MEASURED + 1])
    latencies: list[int] = []
    for index in range(MEASURED):
        window = windows[index : index + 1]
        start = time.perf_counter_ns()
        result = runtime.infer(window)
        latencies.append(time.perf_counter_ns() - start)
        if not math.isfinite(result.raw_logit):
            raise GatewayV2Error("GATEWAY_V2_NONFINITE_BENCHMARK_OUTPUT")
    return latencies


def memory_child_v2(root: Path, window_path: Path) -> dict[str, Any]:
    configure_cpu_threads()
    baseline = max_rss_bytes()
    runtime = GatewayV2Runtime(root, verify="export_audit")
    post_load = max_rss_bytes()
    window = np.load(window_path, allow_pickle=False).astype(np.float32, copy=False)
    runtime.infer(window)
    pre_inference = max_rss_bytes()
    runtime.infer(window)
    peak = max_rss_bytes()
    return {
        "method": "fresh child process resource.getrusage(RUSAGE_SELF).ru_maxrss",
        "semantics": "peak/high-water process RSS during benchmark process",
        "platform_unit_handling": "macOS ru_maxrss treated as bytes; Linux as KiB",
        "baseline_process_RSS_bytes": baseline,
        "post_model_load_RSS_bytes": post_load,
        "pre_inference_RSS_bytes": pre_inference,
        "peak_inference_RSS_bytes": peak,
        "peak_minus_baseline_bytes": peak - baseline,
    }


def _command(*args: str) -> str | None:
    try:
        return subprocess.run(args, check=True, capture_output=True, text=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def host_identity() -> dict[str, Any]:
    import os

    return {
        "OS": platform.system(),
        "OS_version": platform.mac_ver()[0] or platform.release(),
        "architecture": platform.machine(),
        "CPU_model": _command("sysctl", "-n", "machdep.cpu.brand_string")
        or _command("sysctl", "-n", "hw.model") or "unavailable",
        "physical_cores": int(_command("sysctl", "-n", "hw.physicalcpu") or 0),
        "logical_cores": os.cpu_count(),
        "total_RAM_bytes": int(_command("sysctl", "-n", "hw.memsize") or 0),
        "Python": platform.python_version(),
        "PyTorch": torch.__version__,
        "NumPy": np.__version__,
        "device": "CPU",
        "torch_intraop_threads": torch.get_num_threads(),
        "torch_interop_threads": torch.get_num_interop_threads(),
        "hardware_required": False,
        "portability_claim": "none; valid only for this host and process policy",
    }
