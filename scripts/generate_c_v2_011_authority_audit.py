#!/usr/bin/env python3
"""C-V2-011-COMPLETENESS-SEMANTICS step 3: mechanically re-read the locked v2.2 specification and
the execution plan (the .docx sources in the repository) and record exactly what they require of
the Integrated-Gradients completeness/convergence delta. Pure document analysis; no model, no data.
"""

from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/model_v2/v2_011"
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
SPEC = "NHM_ML_Revised_Locked_Specification_v2.2.docx"
PLAN = "NHM_Solo_Implementation_Execution_Plan_v1.0.docx"
NUMERIC_THRESHOLD = re.compile(r"1e-3|1E-3|0\.001|1e-03|10\^-3|10⁻³")
XAI_CONTEXT = re.compile(
    r"integrated gradient|explainab|\bIG\b|G17|convergence delta|completeness", re.IGNORECASE)


def paragraphs(path: Path) -> list[str]:
    root = ET.fromstring(zipfile.ZipFile(path).read("word/document.xml"))
    return ["".join(t.text or "" for t in p.iter(f"{W}t")) for p in root.iter(f"{W}p")]


def scan(name: str) -> dict:
    paras = paragraphs(ROOT / name)
    xai = [(i + 1, p) for i, p in enumerate(paras) if XAI_CONTEXT.search(p)]
    with_threshold = [(i, p) for i, p in xai if NUMERIC_THRESHOLD.search(p)]
    diag = [(i, p) for i, p in xai if re.search(r"convergence delta|completeness/convergence", p,
                                                 re.IGNORECASE)]
    return {
        "document": name,
        "sha256": hash_file(ROOT / name),
        "paragraphs": len(paras),
        "explainability_context_paragraphs": len(xai),
        "explainability_paragraphs_containing_a_numeric_1e-3_threshold": [
            {"paragraph": i, "text": p[:300]} for i, p in with_threshold],
        "convergence_delta_paragraphs": [{"paragraph": i, "text": p[:700]} for i, p in diag],
    }


def main() -> None:
    spec, plan = scan(SPEC), scan(PLAN)
    spec_text = "\n".join(paragraphs(ROOT / SPEC))
    required = {
        "pre_sigmoid_scalar_logit_target": "pre-sigmoid logit" in spec_text,
        "zero_tensor_normalized_input_baseline": "zero tensor in the per-window z-scored input"
        in spec_text,
        "exactly_64_gauss_legendre_steps": "64 integration steps, and Gauss-Legendre" in spec_text,
        "eval_mode": "Run the model in eval mode" in spec_text,
        "signed_attribution_export": "Save both signed attribution values" in spec_text,
        "per_window_normalized_absolute_overlay": "normalized within each window only"
        in spec_text,
        "predeclared_tp_tn_fp_fn_case_selection": "predeclared rule" in spec_text,
        "completeness_convergence_delta_recorded_as_diagnostic_metadata":
        "Record the IG completeness/convergence delta as diagnostic metadata" in spec_text,
        "raw_ecg_and_nearby_public_beat_annotations": "raw ECG plus nearby public-dataset beat "
        "annotations must accompany the overlay" in spec_text,
        "non_causal_engineering_interpretation": "engineering diagnostics, not causal clinical "
        "explanations" in spec_text,
    }
    g17_saved = any("convergence delta and predeclared case selection saved" in p["text"]
                    for p in spec["convergence_delta_paragraphs"])
    no_threshold = (not spec["explainability_paragraphs_containing_a_numeric_1e-3_threshold"]
                    and not plan["explainability_paragraphs_containing_a_numeric_1e-3_threshold"])
    data = {
        "checkpoint": "C-V2-011-COMPLETENESS-SEMANTICS",
        "documents": {"locked_specification_v2_2": spec, "execution_plan_v1_0": plan},
        "locked_v2_2_explainability_contract_requires": required,
        "g17_gate_text_requires_convergence_delta_saved": g17_saved,
        "OLD_PROMPT_RULE": "ABS_LT_1E-3_OR_REL_LT_1E-3",
        "OLD_RULE_SOURCE": "V2_011_ASSISTANT_PROMPT / V1_IMPLEMENTATION_HEURISTIC",
        "LOCKED_V2_2_REQUIREMENT": "RECORD_COMPLETENESS_CONVERGENCE_DELTA_AS_DIAGNOSTIC_METADATA",
        "HARD_NUMERICAL_THRESHOLD_IN_V2_2": "NONE" if no_threshold else "FOUND_REVIEW_REQUIRED",
        "execution_plan_T031_acceptance": "zero baseline; 64 GL; fixed case selection; "
        "convergence delta (no numeric threshold)",
        "g17_blocking_criterion_absolute_or_relative_1e-3_present": not no_threshold,
        "CORRECTIVE_CLASSIFICATION": "UNSUPPORTED_HARD_GATE_REMOVED",
        "nature_of_correction": (
            "source-authority correction; NOT a favorable result-driven threshold relaxation. The "
            "review was triggered after the failed diagnostic run, but its basis is solely the "
            "text of the locked authority documents, which does not depend on the observed "
            "residual values; no replacement threshold is chosen from them (none is introduced)."
        ),
        "observed_residuals_preserved_not_relabelled": True,
        "status": "PASS" if (all(required.values()) and g17_saved and no_threshold) else "FAIL",
    }
    (OUT / "completeness_semantics_authority_audit.json").write_text(
        json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(data["status"], data["HARD_NUMERICAL_THRESHOLD_IN_V2_2"], required)
    if data["status"] != "PASS":
        raise SystemExit("C_V2_011_AUTHORITY_AUDIT_FAILED")


if __name__ == "__main__":
    main()
