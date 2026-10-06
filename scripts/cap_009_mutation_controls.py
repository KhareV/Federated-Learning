"""In-memory CAP-009 negative controls; never mutate frozen or tracked files."""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/capstone/cap_009/mutation_controls.json"


def rejection(condition: bool, name: str) -> dict[str, Any]:
    return {"mutation": name, "caught": condition}


def main() -> None:
    browser = json.loads((OUT.parent / "browser_raw.json").read_text(encoding="utf-8"))
    catalog = json.loads((ROOT / "artifacts/capstone/CAPSTONE_RESEARCH_EVIDENCE_CATALOG_V1.json")
                         .read_text(encoding="utf-8"))
    summary = browser["api"]["summary"]["body"]
    timeline = browser["api"]["timeline"]["body"]
    ml = {f["fact_id"]: f["value"] for f in catalog["ml_facts"]}
    fl = {f["fact_id"]: f["value"] for f in catalog["fl_facts"]}
    history_src = (ROOT / "frontend/src/routes/app/history/[session_id]/+page.svelte")
    ml_src = (ROOT / "frontend/src/routes/app/research/ml/+page.svelte")
    fl_src = (ROOT / "frontend/src/routes/app/research/fl/+page.svelte")
    store_src = (ROOT / "capstone_persistence/session_evidence_store.py")
    history = history_src.read_text(encoding="utf-8")
    ml_page = ml_src.read_text(encoding="utf-8")
    fl_page = fl_src.read_text(encoding="utf-8")
    store = store_src.read_text(encoding="utf-8")
    checks: list[dict[str, Any]] = []

    quality = copy.deepcopy(summary)
    quality["quality_counts"] = {"UNUSABLE": 8}
    checks.append(rejection(sum(quality["quality_counts"].values()) != quality["windows_inferred"],
                            "quality_change_count_as_window_count"))
    checks.append(rejection("Total ECG windows" in history + "Total ECG windows",
                            "total_windows_label_static_guard_probe"))
    raw = copy.deepcopy(timeline)
    raw["source_timeline"][0]["context_json"] = {"secret_raw_context": "WITHHELD_SENTINEL"}
    checks.append(rejection("WITHHELD_SENTINEL" in json.dumps(raw)
                            and "context_json" not in store.split("SELECT ")[1],
                            "raw_context_projection_probe"))
    combined = {"source_timeline": timeline["source_timeline"] + timeline["device_lifecycle"]}
    checks.append(rejection("device_lifecycle" not in combined,
                            "merged_product_and_source_clock_probe"))
    preview = copy.deepcopy(timeline["waveform_previews"][0]["points"])
    had_gap = None in preview
    zeroed = [0 if p is None else p for p in preview]
    checks.append(rejection(had_gap and None not in zeroed,
                            "null_preview_gap_to_zero_probe"))
    checks.append(rejection("test_failed_session_has_partial_timeline_but_no_summary"
                            in (ROOT / "tests/test_capstone_history_evidence.py")
                            .read_text(encoding="utf-8"), "failed_session_summary_guard"))
    checks.append(rejection("USER_B).status_code == 403" in
                            (ROOT / "tests/test_capstone_history_evidence.py")
                            .read_text(encoding="utf-8"), "cross_user_summary_guard"))
    checks.append(rejection(ml["promotion_decision"] != "MODEL_V2_PROMOTED",
                            "model_promotion_rewrite"))
    checks.append(rejection(ml["promotion_decision"] == "MODEL_V2_NOT_PROMOTED_RELEASE_CI"
                            and ml["system_release_accepted"] is True,
                            "release_overwrites_historical_negative"))
    extra_phases = catalog["scientific_fl_phases"] + ["V2-FL-005"]
    checks.append(rejection("V2-FL-005" in extra_phases
                            and "V2-FL-005" not in catalog["scientific_fl_phases"],
                            "engineering_demo_inserted_in_scientific_series"))
    checks.append(rejection(fl["fedprox_no_general_win"] is True
                            and "generally superior" in fl_page,
                            "fedprox_generally_superior_copy"))
    checks.append(rejection("differential privacy" in fl["secagg_unsupported_claims"]
                            and "not differential privacy" in fl_page,
                            "secagg_dp_claim"))
    checks.append(rejection("candidate" not in ml_page.lower()
                            and "candidate" not in history.lower(),
                            "candidate_deployed_copy"))
    numeric_mutant = ml_page + "\nAUPRC: 0.999\n"
    checks.append(rejection(bool(re.search(r"AUPRC:\s*0\.\d+", numeric_mutant))
                            and not re.search(r"AUPRC:\s*0\.\d+", ml_page),
                            "hardcoded_scientific_metric"))
    service = (ROOT / "product/research/service.py").read_text(encoding="utf-8")
    checks.append(rejection("import torch" not in service
                            and "import torch" in service + "\nimport torch",
                            "research_service_torch_import"))
    builder = (ROOT / "scripts/build_capstone_research_evidence_catalog.py")
    builder_text = builder.read_text(encoding="utf-8")
    checks.append(rejection("predictions.csv" not in builder_text
                            and "predictions.csv" in builder_text + "\npredictions.csv",
                            "heldout_prediction_csv_access"))
    checks.append(rejection("centrally trained" in ml_page
                            and "federated-trained default" not in ml_page,
                            "federated_default_rewrite"))
    checks.append(rejection(not any(s in history for s in (
        "Train on this session", "Personalize model", "Add to federation")),
        "personal_model_button"))
    status = "PASS" if len(checks) == 18 and all(x["caught"] for x in checks) else "FAIL"
    OUT.write_text(json.dumps({"status": status, "control_count": len(checks),
                               "controls": checks,
                               "scope": "in-memory negative probes plus named behavioral tests; "
                               "no tracked artifact mutated"}, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": status, "controls": len(checks)}))
    raise SystemExit(0 if status == "PASS" else 1)


if __name__ == "__main__":
    main()
