# ruff: noqa: E501
"""Upgrade shortlist: which stored engineering candidates could be put forward for REVIEW as a future custom model, and what is still missing.

This is a read-only evidence checklist, ``UPGRADE_SHORTLIST_POLICY_V1``. It never promotes, registers, deploys or switches a model: NHM has no deployment path, and the
released monitoring model stays MODEL_V2_FINAL + CAL_V2. A candidate is SHORTLISTED_FOR_REVIEW only when no criterion FAILS and it has evidence on real, unseen ECG; "review"
means a human governance decision outside this software, never an automatic upgrade. COMPARABLE_NOT_BETTER marks a candidate that matches the released model on real ECG but does not beat it.

There are TWO tracks. The **real-ECG upgrade track** (S1-S7) asks whether a candidate could replace the released model, and needs real, unseen ECG evidence. The **engineering reuse track** (E1-E3) asks whether a candidate is a better starting point for further sandbox work than the released model on its own evaluation cohort; it needs no real-ECG evidence and is never a case for deployment: its risks (synthetic-only evidence, assigned labels) are listed with every entry.

The criteria deliberately weigh REAL-ECG evidence above scores on the synthetic cohorts: a synthetic-cohort score measures agreement with the simulator, and the PTB-XL external
check found that federated adaptation to a synthetic cohort lowered real-ECG performance (reports/ptbxl/mitigation.json)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
POLICY_ID = "UPGRADE_SHORTLIST_POLICY_V1"
EXTERNAL_CHECK = Path("reports/ptbxl/external_check_v1.json")
PRIMARY_SET = "primary (folds 9-10)"
RELEASED_ROW = "MODEL_V2_FINAL (central)"
# stored candidate id -> its row in the PTB-XL external check (only imported research checkpoints were scored there)
EXTERNAL_ROWS = {
    "RESEARCH_FL_V2_FL001_R50": "V2-FL-001 round 50 (federated)",
    "RESEARCH_FL_V2_FL001_R38_BEST": "V2-FL-001 round 38 (best-validation)",
}
MIN_F1 = 0.5
MIN_GAIN = 0.02                                                                    # engineering track: AUROC and AUPRC must both beat the released model on the same cohort by this much
REFERENCE_EVIDENCE = Path("reports/verification/browser/fl_matrix/fl_round_verification.json")   # independently recomputed round-0 metrics of the pretrained V2 on every evaluation cohort

CRITERIA = [
    {"id": "S1", "title": "Scored on real, unseen ECG", "rule": "The candidate has a row in the PTB-XL external check (real 12-lead ECG that no model was trained, selected or evaluated on)."},
    {"id": "S2", "title": "Not distinguishably worse than the released V2 on real ECG", "rule": "Its real-ECG AUROC 95% interval reaches the released model's real-ECG AUROC."},
    {"id": "S3", "title": "Better than the released V2 on real ECG", "rule": "The lower end of its real-ECG AUROC interval is above the released model's real-ECG AUROC."},
    {"id": "S4", "title": "Trained on real-ECG labels", "rule": "Trained on real annotated ECG, not on synthetic or assigned labels (synthetic-cohort adaptation lowered real-ECG performance in the PTB-XL mitigation analysis)."},
    {"id": "S5", "title": "Usable at the fixed 0.5 threshold", "rule": f"F1 at the fixed 0.5 threshold on its evaluation cohort is at least {MIN_F1}; a model that calls everything positive fails."},
    {"id": "S6", "title": "Calibration evidence", "rule": "A calibration fitted on a separate partition exists for this candidate. NHM has none for any candidate, so this is not evidenced for all."},
    {"id": "S7", "title": "Governance sign-off", "rule": "A human release decision with a release manifest exists. NHM has no deployment path, so this is not evidenced for all."},
]

ENGINEERING_CRITERIA = [
    {"id": "E1", "title": "Beats the released V2 on its own evaluation cohort", "rule": f"AUROC and AUPRC on the cohort it was scored on are both at least {MIN_GAIN} above the released MODEL_V2_FINAL scored on that same cohort (independently recomputed round-0 metrics)."},
    {"id": "E2", "title": "Usable at the fixed 0.5 threshold", "rule": f"F1 at the fixed 0.5 threshold is at least {MIN_F1}; a model that calls everything positive fails."},
    {"id": "E3", "title": "Scored on a cohort with a reference", "rule": "The cohort it was scored on has a released-model reference, so the comparison is like for like."},
]
RISKS = {
    "R1": "Synthetic-only evidence: the score measures agreement with the simulator. The PTB-XL mitigation analysis found that adapting to a synthetic cohort lowered real-ECG performance, so this is not evidence of real-ECG benefit.",
    "R2": "Trained partly on assigned labels of a recording, so its score describes the pipeline, not the device or a person.",
    "R3": "Scored on the cohort family it was adapted to, which favours it over the released model.",
}


def _external(root: Path) -> dict[str, Any] | None:
    path = root / EXTERNAL_CHECK
    try:
        data = json.loads(path.read_text())
        primary = data["sets"][PRIMARY_SET]
        return {"point": primary["rule A"]["models"], "ci": primary["bootstrap rule A"]["models"], "target": data.get("target")}
    except (OSError, KeyError, ValueError):
        return None


def _reference(root: Path) -> dict[str, dict[str, Any]]:
    """The released V2's zero-shot AUROC/AUPRC on each evaluation cohort: the round-0 metrics of every pretrained-V2 run in the independently verified matrix (identical across runs, as they must be)."""
    from studio import cohorts

    try:
        data = json.loads((root / REFERENCE_EVIDENCE).read_text())
    except (OSError, ValueError):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for run in data.values():
        if run.get("init") != "MODEL_V2_FINAL" or "0" not in run.get("rounds", {}):
            continue
        metrics = run["rounds"]["0"].get("metrics") or {}
        if metrics.get("AUROC") is None or metrics.get("AUPRC") is None:
            continue
        cohort = run.get("cohort")
        try:
            cohort_id = cohorts.spec(cohort).evaluation_cohort_id
        except Exception:  # noqa: BLE001
            continue
        out[cohort_id] = {"AUROC": float(metrics["AUROC"]), "AUPRC": float(metrics["AUPRC"]), "cohort": cohort, "source": REFERENCE_EVIDENCE.as_posix()}
    return out


def _check(cid: str, status: str, detail: str) -> dict[str, str]:
    return {"id": cid, "status": status, "detail": detail}


def evaluate(entry: dict[str, Any], external: dict[str, Any] | None, reference: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    """The criteria table of ONE candidate record. Pure: the same record and evidence always give the same table."""
    checks: list[dict[str, str]] = []
    row = EXTERNAL_ROWS.get(entry["candidate_id"])
    cand_point = (external or {}).get("point", {}).get(row, {}) if row else {}
    cand_ci = (external or {}).get("ci", {}).get(row, {}).get("AUROC", {}).get("ci95") if row else None
    ref_point = (external or {}).get("point", {}).get(RELEASED_ROW, {}).get("AUROC")
    if row and cand_point and cand_ci and ref_point is not None:
        checks.append(_check("S1", "PASS", f"scored in the PTB-XL external check as '{row}': AUROC {cand_point['AUROC']:.3f}, 95% interval {cand_ci[0]:.3f}-{cand_ci[1]:.3f}"))
        checks.append(_check("S2", "PASS" if cand_ci[1] >= ref_point else "FAIL", f"released V2 real-ECG AUROC is {ref_point:.3f}; this interval's upper end is {cand_ci[1]:.3f}"))
        checks.append(_check("S3", "PASS" if cand_ci[0] > ref_point else "FAIL", f"released V2 real-ECG AUROC is {ref_point:.3f}; this interval's lower end is {cand_ci[0]:.3f}"))
    else:
        why = "no real unseen ECG score exists for this candidate"
        checks.append(_check("S1", "NOT_EVIDENCED", why))
        checks.append(_check("S2", "NOT_EVIDENCED", why))
        checks.append(_check("S3", "NOT_EVIDENCED", why))
    cohort = entry.get("cohort")
    if cohort == "REAL_ECG":
        checks.append(_check("S4", "PASS", "trained on real MIT-BIH annotated ECG in simulated sites"))
    else:
        assigned = entry.get("source_kind") == "RECORDED_HARDWARE"
        checks.append(_check("S4", "FAIL", "trained on assigned labels of a recording and synthetic peers" if assigned else "trained on a synthetic cohort whose labels come from the simulator"))
    f1 = (entry.get("metrics") or {}).get("F1")
    checks.append(_check("S5", "NOT_EVIDENCED", "no F1 snapshot stored") if not isinstance(f1, (int, float)) else _check("S5", "PASS" if f1 >= MIN_F1 else "FAIL", f"F1 at 0.5 is {f1:.3f} on {entry.get('evaluation_cohort_id') or 'its evaluation cohort'} (minimum {MIN_F1})"))
    checks.append(_check("S6", "NOT_EVIDENCED", "no calibration exists for this candidate"))
    checks.append(_check("S7", "NOT_EVIDENCED", "no release decision exists; NHM has no deployment path"))
    failing = [c["id"] for c in checks if c["status"] == "FAIL"]
    real_evidence = checks[0]["status"] == "PASS"
    metrics = entry.get("metrics") or {}
    ref = (reference or {}).get(entry.get("evaluation_cohort_id") or "")
    engineering: list[dict[str, str]] = []
    if ref is None:
        engineering.append(_check("E3", "NOT_EVIDENCED", f"no released-model reference exists for {entry.get('evaluation_cohort_id') or 'its evaluation cohort'}"))
        engineering.append(_check("E1", "NOT_EVIDENCED", "nothing to compare with"))
    else:
        engineering.append(_check("E3", "PASS", f"released V2 on {entry.get('evaluation_cohort_id')}: AUROC {ref['AUROC']:.3f}, AUPRC {ref['AUPRC']:.3f}"))
        auroc, auprc = metrics.get("AUROC"), metrics.get("AUPRC")
        if not isinstance(auroc, (int, float)) or not isinstance(auprc, (int, float)):
            engineering.append(_check("E1", "NOT_EVIDENCED", "no AUROC/AUPRC snapshot stored"))
        else:
            gain_roc, gain_pr = auroc - ref["AUROC"], auprc - ref["AUPRC"]
            engineering.append(_check("E1", "PASS" if gain_roc >= MIN_GAIN and gain_pr >= MIN_GAIN else "FAIL", f"AUROC {auroc:.3f} ({gain_roc:+.3f}) and AUPRC {auprc:.3f} ({gain_pr:+.3f}) against the released V2's {ref['AUROC']:.3f} / {ref['AUPRC']:.3f}; each gain must be at least {MIN_GAIN}"))
    f1_check = checks[4]
    engineering.append(_check("E2", f1_check["status"], f1_check["detail"]))
    engineering.sort(key=lambda c: c["id"])
    engineering_pass = all(c["status"] == "PASS" for c in engineering)
    risks = [] if cohort == "REAL_ECG" else ["R1", "R3"] + (["R2"] if entry.get("source_kind") == "RECORDED_HARDWARE" else [])
    tier = ("SHORTLISTED_FOR_REVIEW" if real_evidence and not failing else "COMPARABLE_NOT_BETTER" if real_evidence and failing == ["S3"]
            else "SHORTLISTED_FOR_SANDBOX_REUSE" if engineering_pass else "NOT_SHORTLISTED")
    return {"candidate_id": entry["candidate_id"], "label": entry.get("label"), "cohort": cohort, "source_kind": entry.get("source_kind"), "run_length": entry.get("run_length"), "round_id": entry.get("round_id"),
            "tier": tier, "engineering": engineering, "risks": [{"id": r, "text": RISKS[r]} for r in risks], "failing": failing, "passing": [c["id"] for c in checks if c["status"] == "PASS"], "not_evidenced": [c["id"] for c in checks if c["status"] == "NOT_EVIDENCED"], "checks": checks,
            "promoted": False, "deployed": False}


def build(entries: list[dict[str, Any]], root: Path = ROOT) -> dict[str, Any]:
    """The shortlist of one owner's stored candidates: shortlisted first, then fewest failures, then most passes. A rank is an order of evidence, not a score."""
    external = _external(root)
    reference = _reference(root)
    rows = [evaluate(e, external, reference) for e in entries]
    order = {"SHORTLISTED_FOR_REVIEW": 0, "SHORTLISTED_FOR_SANDBOX_REUSE": 1, "COMPARABLE_NOT_BETTER": 2, "NOT_SHORTLISTED": 3}
    rows.sort(key=lambda r: (order[r["tier"]], len(r["failing"]), -len(r["passing"]), r["candidate_id"]))
    for rank, row in enumerate(rows, start=1):
        row["rank"] = rank
    ref = (external or {}).get("point", {}).get(RELEASED_ROW, {})
    return {"policy_id": POLICY_ID, "criteria": CRITERIA, "engineering_criteria": ENGINEERING_CRITERIA, "references": reference, "released_model": {"model_id": "MODEL_V2_FINAL", "role": "released monitoring model (unchanged)", "real_ecg_auroc": ref.get("AUROC"),
                                                                           "ci95": ((external or {}).get("ci", {}).get(RELEASED_ROW, {}).get("AUROC") or {}).get("ci95")},
            "external_check": EXTERNAL_CHECK.as_posix() if external else None, "entries": rows,
            "note": "A shortlist is not an upgrade. Nothing here promotes, registers or deploys a model; the released monitoring model stays MODEL_V2_FINAL with CAL_V2. SHORTLISTED_FOR_REVIEW only means no criterion fails and real-ECG evidence exists; SHORTLISTED_FOR_SANDBOX_REUSE means it beats the released model on its own synthetic evaluation cohort and is a better starting point for further sandbox work, with its risks listed, and is never a case for deployment; COMPARABLE_NOT_BETTER means it matches the released model on real ECG without beating it, so there is no case for an upgrade; S6 and S7 stay open for every candidate until a human release decision outside NHM."}
