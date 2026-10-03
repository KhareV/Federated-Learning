#!/usr/bin/env python3
"""V2-011 registry/gate transition (run only after every acceptance condition passed).
Byte-level edits so the CRLF line endings of the V2 registries are preserved."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/model_v2/v2_011"


def edit(path: Path, old: str, new: str) -> None:
    data = path.read_bytes().decode("utf-8")
    if data.count(old) != 1:
        raise RuntimeError(f"REGISTRY_PATTERN_COUNT:{path.name}:{data.count(old)}")
    path.write_bytes(data.replace(old, new).encode("utf-8"))


def main() -> None:
    for name in ("tamper_test_results", "reproducibility", "scope_audit",
                 "method_immutability_audit", "protected_artifact_audit"):
        if json.loads((OUT / f"{name}.json").read_text())["status"] != "PASS":
            raise RuntimeError(f"V2_011_ACCEPTANCE_NOT_MET:{name}")
    report = json.loads((OUT / "explainability_v2.json").read_text())
    if not report["all_completeness_pass"]:
        raise RuntimeError("V2_011_ACCEPTANCE_NOT_MET:completeness")
    ids = {c["case_type"]: c["example_id"][:12] for c in report["cases"]}
    result = (
        " RESULT (executed): EXPLAINABILITY_V2 frozen for MODEL_V2_FINAL. Four deterministic "
        f"confidence-extreme cases from the frozen V2-010 INTERNAL_TEST table (TP {ids['TP']}, "
        f"TN {ids['TN']}, FP {ids['FP']}, FN {ids['FN']}); 64-point Gauss-Legendre signed "
        "Integrated Gradients on the raw pre-sigmoid logit from the zero normalized-input "
        "baseline; all four completeness checks passed; repeat runs identical; model unmutated. "
        "Prediction-table error analysis ranks patients by Brier; TRAIN-defined HR bins reused; "
        "threshold band fixed at +/-0.05; one controlled C031-derived V2 noise-type run "
        "(720 windows x 3 noise types x 6 SNRs = 18 cells; no V1 rerun). V2-010 statistics "
        "independently reconstructed from first principles. MODEL_V2_RUNTIME_ACCEPTED=ACCEPTED, "
        "official promotion (MODEL_V2_NOT_PROMOTED_RELEASE_CI) and operational lineage "
        "(MODEL_V1) unchanged; zero new neural fits (cumulative 71/90). See "
        "reports/model_v2/v2_011/.\""
    )
    task = ROOT / "manifests/model_v2/task_registry_v1.csv"
    text = task.read_bytes().decode("utf-8")
    line = next(r for r in text.split("\r\n") if r.startswith("V2-011,"))
    marker = ",V2G10,NOT_STARTED,,,"
    assert marker in line and not line.endswith('"')
    head, notes = line.split(marker, 1)
    new_line = f'{head},V2G10,PASS,,,"{notes}{result}'
    edit(task, line, new_line)

    gate = ROOT / "manifests/model_v2/gate_registry_v1.csv"
    gtext = gate.read_bytes().decode("utf-8")
    gline = next(r for r in gtext.split("\r\n") if r.startswith("V2G10,"))
    assert gline.endswith(",NOT_STARTED,")
    new_gate = gline[: -len("NOT_STARTED,")] + "PASS,reports/model_v2/v2_011/run_manifest.json"
    edit(gate, gline, new_gate)
    component = ROOT / "manifests/model_v2/component_registry_v1.csv"
    row = (
        "EXPLAINABILITY_V2,EXPLAINABILITY_METHOD_LOCK,V2-011,FROZEN_EXPLAINABILITY,,"
        "artifacts/EXPLAINABILITY_V2_METHOD.lock.json,"
        '"Additive, non-canonical (no Fxx row) locked explainability/error-analysis method for '
        "MODEL_V2_FINAL: signed 64-point Gauss-Legendre Integrated Gradients on the pre-sigmoid "
        "logit from the zero normalized-input baseline, four deterministic TP/TN/FP/FN cases, "
        "Brier-ranked patient slices, TRAIN-defined HR bins, fixed +/-0.05 threshold band, and "
        "one controlled C031-derived noise-type run. Engineering diagnostic only; not causal, "
        "not clinical, and not a runtime switch. Does not change MODEL_V2_FINAL, CAL_V2, "
        "MODEL_V2_RUNTIME_ACCEPTED=ACCEPTED, the official promotion outcome, or the MODEL_V1 "
        'operational lineage. EXPLAINABILITY_V1 is untouched."\r\n'
    )
    data = component.read_bytes().decode("utf-8")
    assert data.endswith("\r\n") and "EXPLAINABILITY_V2," not in data
    component.write_bytes((data + row).encode("utf-8"))
    print("V2-011 registry transition applied")


if __name__ == "__main__":
    main()
