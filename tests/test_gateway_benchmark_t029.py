from __future__ import annotations

import csv
import json
import math
from pathlib import Path

import pytest

from deployment.benchmark import latency_summary
from scripts.verify_t029 import verify_bindings

ROOT = Path(__file__).resolve().parents[1]


def test_latency_statistics_and_throughput_formula() -> None:
    samples = list(range(1_000_000, 2_000_000, 1000))
    report = latency_summary(samples)
    assert report["N"] == 1000
    assert report["p50_ms"] > 0
    assert report["p95_ms"] >= report["p50_ms"]
    assert report["throughput_windows_per_second"] == pytest.approx(
        1000 / report["total_timed_seconds"]
    )
    assert all(math.isfinite(float(value)) for value in report.values())


def test_latency_rejects_wrong_count() -> None:
    with pytest.raises(ValueError, match="1000"):
        latency_summary([1] * 999)


def test_canonical_resource_and_equivalence_evidence() -> None:
    equivalence = json.loads((ROOT / "reports/t029/deployment_equivalence.json").read_text())
    assert equivalence["rows_compared"] == 2157
    assert equivalence["duplicates"] == 0
    assert equivalence["extra"] == 0
    assert equivalence["missing"] == 0
    assert equivalence["maximum_absolute_raw_logit_delta"] <= 1e-5
    assert equivalence["decision_agreement_fraction"] == 1.0
    assert all(value == 0.0 for value in equivalence["metric_absolute_deltas"].values())

    with (ROOT / "reports/t029/latency_samples.csv").open(newline="") as handle:
        samples = list(csv.DictReader(handle))
    assert len(samples) == 1000
    assert all(row["finite_output"] == "True" for row in samples)

    latency = json.loads((ROOT / "reports/t029/latency_summary.json").read_text())
    assert latency["warmup_count"] == 100
    assert latency["canonical_run"]["N"] == 1000
    assert latency["verification_repeat"]["N"] == 1000
    assert latency["canonical_run"]["p95_ms"] >= latency["canonical_run"]["p50_ms"]

    memory = json.loads((ROOT / "reports/t029/memory_benchmark.json").read_text())
    assert memory["status"] == "PASS"
    assert memory["peak_inference_RSS_bytes"] >= memory["pre_inference_RSS_bytes"]


def test_f14_binding_detects_tamper(tmp_path: Path) -> None:
    source = tmp_path / "config.yaml"
    source.write_text("locked: true\n")
    from nhm.hashing import hash_file

    lock: dict[str, object] = {"bound_artifacts": {"config.yaml": hash_file(source)}}
    verify_bindings(lock, tmp_path, "F14")
    source.write_text("locked: false\n")
    with pytest.raises(RuntimeError, match="F14_TAMPER"):
        verify_bindings(lock, tmp_path, "F14")
