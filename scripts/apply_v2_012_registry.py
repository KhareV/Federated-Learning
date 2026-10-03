#!/usr/bin/env python3
"""V2-012 registry/gate transition (run only after every acceptance condition passed).
Byte-level edits so the CRLF line endings of the V2 registries are preserved."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/model_v2/v2_012"


def edit(path: Path, old: str, new: str) -> None:
    data = path.read_bytes().decode("utf-8")
    if data.count(old) != 1:
        raise RuntimeError(f"REGISTRY_PATTERN_COUNT:{path.name}:{data.count(old)}")
    path.write_bytes(data.replace(old, new).encode("utf-8"))


def main() -> None:
    for name in ("gateway_verification", "tamper_test_results", "method_immutability_audit",
                 "protected_artifact_audit", "scope_audit", "synthetic_corpus_parity_summary",
                 "canonical_fixture_parity", "calibration_wrapper_parity", "benchmark_summary"):
        if json.loads((OUT / f"{name}.json").read_text())["status"] != "PASS":
            raise RuntimeError(f"V2_012_ACCEPTANCE_NOT_MET:{name}")
    manifest = json.loads((ROOT / "artifacts/deployment/GATEWAY_ARTIFACT_V2.manifest.json"
                           ).read_text())
    bench = manifest["benchmark"]
    corpus = manifest["synthetic_corpus_parity"]
    result = (
        " RESULT (executed): GATEWAY_ARTIFACT_V2 exported once as FP32 TorchScript "
        "(torch.jit.script; format fixed by the GATEWAY_ARTIFACT_V1 precedent before any "
        f"benchmark; no trace/ONNX/INT8 alternative), {manifest['artifact']['bytes']} bytes, "
        f"57553 trainable parameters, raw pre-sigmoid logit output (CAL_V2 applied by the "
        "wrapper via canonical helpers). Canonical V2-008 fixture and a predeclared 1000-window "
        f"synthetic parity corpus: allclose at atol=rtol=1e-6 (max abs logit delta "
        f"{corpus['max_abs_logit_delta']:.3e}), {corpus['threshold_decision_disagreements']} "
        "threshold disagreements. CPU benchmark (3 fresh-process repetitions x 1000 batch-1 "
        f"calls after 100 warm-ups; median-of-3): p50 {bench['canonical_p50_ms']:.4f} ms, p95 "
        f"{bench['canonical_p95_ms']:.4f} ms, "
        f"{bench['canonical_throughput_windows_per_second']:.0f} windows/s, peak/high-water "
        f"process RSS {bench['peak_high_water_process_RSS_bytes']} bytes (same-host engineering "
        "numbers, no invented target). Research-only frozen V2 CPU gateway artifact: "
        "MODEL_V2_RUNTIME_ACCEPTED=ACCEPTED, official promotion "
        "MODEL_V2_NOT_PROMOTED_RELEASE_CI and operational lineage MODEL_V1 unchanged; no API, "
        "runtime-default or frontend change; zero held-out data access; zero new fits "
        "(cumulative 71/90). See reports/model_v2/v2_012/.\""
    )
    task = ROOT / "manifests/model_v2/task_registry_v1.csv"
    text = task.read_bytes().decode("utf-8")
    line = next(r for r in text.split("\r\n") if r.startswith("V2-012,"))
    marker = ",V2G11,NOT_STARTED,,,"
    assert marker in line and line.endswith('"')
    head, notes = line.split(marker, 1)
    edit(task, line, f"{head},V2G11,PASS,,,{notes[:-1]}{result}")

    gate = ROOT / "manifests/model_v2/gate_registry_v1.csv"
    gtext = gate.read_bytes().decode("utf-8")
    gline = next(r for r in gtext.split("\r\n") if r.startswith("V2G11,"))
    assert gline.endswith(",NOT_STARTED,")
    passed = gline[: -len("NOT_STARTED,")] + "PASS,reports/model_v2/v2_012/run_manifest.json"
    edit(gate, gline, passed)

    comp = ROOT / "manifests/model_v2/component_registry_v1.csv"
    ctext = comp.read_bytes().decode("utf-8")
    cline = next(r for r in ctext.split("\r\n") if r.startswith("GATEWAY_ARTIFACT_V2,"))
    assert ",V2-012,NOT_STARTED,," in cline
    new = (
        "GATEWAY_ARTIFACT_V2,DEPLOYMENT_LOCK,V2-012,FROZEN_RESEARCH_GATEWAY,,"
        "artifacts/deployment/GATEWAY_ARTIFACT_V2.manifest.json,"
        '"Research-only frozen V2 CPU gateway artifact: FP32 TorchScript (torch.jit.script) of '
        "MODEL_V2_FINAL returning the raw pre-sigmoid logit; CAL_V2 applied by the wrapper via "
        "the canonical helpers, never baked into weights. Verified by canonical-fixture and "
        "1000-window synthetic parity (atol=rtol=1e-6, zero threshold disagreements) and a "
        "same-host CPU benchmark. Additive to, and never mutating, GATEWAY_ARTIFACT_V1/F14; not "
        "a canonical Fxx row. Does not change MODEL_V2_RUNTIME_ACCEPTED=ACCEPTED, the official "
        "promotion outcome (MODEL_V2_NOT_PROMOTED_RELEASE_CI) or the MODEL_V1 operational "
        'lineage; no API/runtime/frontend binding (V2-013 remains NOT_STARTED)."'
    )
    edit(comp, cline, new)
    print("V2-012 registry transition applied")


if __name__ == "__main__":
    main()
