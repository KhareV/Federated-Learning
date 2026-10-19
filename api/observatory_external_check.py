# ruff: noqa: E501
"""PTBXL_EXTERNAL_CHECK_V1 for the Observatory: a read-only, hash-verified view of the frozen external-check report (`reports/ptbxl/external_check_v1.json`).

Nothing is computed here: values are read from the stored report and reshaped for display. The protocol file's SHA-256 must equal the one recorded in the report (the protocol was written before any score existed);
a mismatch fails closed. Additive: one GET route, no frozen route is touched."""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request

from product.api.errors import ProductError, ProductErrorCode

ROOT = Path(__file__).resolve().parents[1]
REPORT = "reports/ptbxl/external_check_v1.json"
CLASSIFICATION = "FROZEN_EXTENSION_EVIDENCE"
LABEL = "FROZEN EXTENSION EVIDENCE · REAL UNSEEN ECG · RECORD-LEVEL TARGET · NOT AAMI-SVF · NOT CLINICAL"
CLAIM_BOUNDARY = ("Extension outside the locked AAMI_SVF_WINDOW_V1 scope: the dataset has no beat annotations, so the target is record-level (a cardiologist statement or an extra-beat field says the record contains premature beats). "
                  "No model was trained, selected, calibrated or evaluated on this dataset before; fixed 0.5 rule, no calibration; no clinical, diagnostic or device claim.")
LIMITATIONS = [
    "Record-level labels from cardiologist statements and an extra-beat field, not beat annotations; the two label sources agree on only about half of the premature-beat records, so three label rules are reported.",
    "One population (hospital recordings of one dataset) and lead II only: one external check, not general validity.",
    "No threshold, calibration or model was selected from these results; AUPRC depends on prevalence, so lift is shown next to it.",
    "Intervals are 95 % patient-cluster bootstrap intervals; the synthetic-adapted models are single federated runs.",
]
SET_NAMES = ("primary (folds 9-10)", "replication (folds 1-8)")


class ExternalCheckError(RuntimeError):
    pass


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def view(root: Path = ROOT) -> dict[str, Any]:
    path = root / REPORT
    if not path.is_file():
        raise ExternalCheckError("EXTERNAL_CHECK_REPORT_MISSING")
    report = json.loads(path.read_text())
    protocol_path = root / report["protocol"]["file"]
    if not protocol_path.is_file() or _sha(protocol_path) != report["protocol"]["sha256"]:
        raise ExternalCheckError("EXTERNAL_CHECK_PROTOCOL_HASH_MISMATCH")
    models = list(report["models"])

    def row(set_block: dict[str, Any], model: str) -> dict[str, Any]:
        pm = set_block["rule A"]["models"][model]
        boot = set_block["bootstrap rule A"]
        ci = boot["models"][model]
        paired = boot["paired_vs_central_V2"].get(model)
        return {"model": model, "AUROC": pm["AUROC"], "AUROC_ci": ci["AUROC"]["ci95"], "AUPRC": pm["AUPRC"], "AUPRC_ci": ci["AUPRC"]["ci95"], "lift": pm["lift"], "F1": pm["F1"], "F1_ci": ci["F1"]["ci95"],
                "sensitivity": pm["recall"], "specificity": pm["specificity"], "precision": pm["precision"],
                "paired_vs_central_V2": None if paired is None else {k: {"delta": paired[k]["delta_mean"], "ci95": paired[k]["ci95"], "share_better": paired[k]["share_better"]} for k in ("AUROC", "AUPRC")}}

    sets = []
    for name in SET_NAMES:
        block = report["sets"][name]
        a = block["rule A"]
        sets.append({"name": name, "records": a["records"], "positives": a["positives"], "patients": block["bootstrap rule A"]["patients"], "prevalence": a["positives"] / a["records"],
                     "bootstrap_replicates": block["bootstrap rule A"]["replicates"], "rows": [row(block, m) for m in models]})
    primary = report["sets"][SET_NAMES[0]]
    rules = []
    for key, title in (("rule A", "A · union of the two label sources (primary)"), ("rule B", "B · both sources agree (one-source records excluded)"), ("rule C", "C · cardiologist statements only"),
                       ("rule A, clean negatives (NORM + SR)", "A with clean negatives (normal sinus rhythm only)")):
        b = primary[key]
        rules.append({"rule": key, "title": title, "records": b["records"], "positives": b["positives"], "rows": [{"model": m, "AUROC": b["models"][m]["AUROC"], "AUPRC": b["models"][m]["AUPRC"], "lift": b["models"][m]["lift"]} for m in models]})
    err = report["error_analysis_central_V2_rule_A_primary"]
    groups = [{"group": k, "records": v["records"], "share_flagged": v["share_flagged"]} for k, v in err.items() if k != "positives by source" and v["share_flagged"] is not None]
    groups += [{"group": f"positives, {k}", "records": v["records"], "share_flagged": v["share_flagged"]} for k, v in err["positives by source"].items() if v["share_flagged"] is not None]
    agreement = report["sanity"]["label_source_agreement"]
    return {"classification": CLASSIFICATION, "label": LABEL, "claim_boundary": CLAIM_BOUNDARY, "target": report["target"], "records_scored": report["records_scored"], "exclusions": report["exclusions"],
            "threshold": report["threshold"], "calibration": report["calibration"], "report": {"path": REPORT, "sha256": _sha(path)}, "protocol": {"path": report["protocol"]["file"], "sha256": report["protocol"]["sha256"], "verified": True},
            "models": models, "sets": sets, "label_rules": rules, "error_analysis": groups, "label_agreement": {"both": agreement["both"], "statement_only": agreement["SCP statement only"], "extra_beats_only": agreement["extra_beats only"]},
            "limitations": LIMITATIONS}


def register(app: FastAPI, prefix: str, identity: Callable[[Request], Awaitable[str]]) -> None:
    @app.get(f"{prefix}/evidence/external-check")
    async def external_check(request: Request) -> dict[str, Any]:
        await identity(request)
        try:
            return await asyncio.to_thread(view)
        except (ExternalCheckError, KeyError, ValueError) as error:
            raise ProductError(ProductErrorCode.INTERNAL_PRODUCT_ERROR, f"EXTERNAL_CHECK_UNAVAILABLE:{error}") from error
