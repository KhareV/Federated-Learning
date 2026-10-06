# ruff: noqa: E501
"""UFL-LITE-002 static audits of the presentation implementation (pure; used by the frozen UFLG1 evaluator, tests and mutation controls)."""

from __future__ import annotations

import re
import shutil
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
HELPER = "frontend/src/lib/product/federation/participation.ts"
GRID = "frontend/src/lib/components/product/federation/ClientGrid.svelte"
LIVE = "frontend/src/routes/app/federation/live/+page.svelte"
ROUNDS = "frontend/src/routes/app/federation/rounds/+page.svelte"
CLIENTS = "frontend/src/routes/app/federation/clients/+page.svelte"
PRESENTATION = (HELPER, GRID, LIVE, ROUNDS)
FORBIDDEN_TEXT = re.compile(r"contribution|influence score|importance score|% of the model|personal model|personali[sz]ed|my ECG|my monitoring|consent|opt[- ]in|join federation|never leaves your physical device", re.I)
IDENTITY = re.compile(r"user_id|userId|\.email|display_?name|identity\.|session_?id|token|cookie|localStorage|sessionStorage|Clerk", re.I)


def read(root: Path, rel: str) -> str:
    return (root / rel).read_text(encoding="utf-8")


def helper_audit(root: Path = ROOT) -> dict[str, Any]:
    """The helper is pure, binds exactly SIM_FL_SITE_00, only for CLERK + LIVE_RUN, takes no identity."""
    t = re.sub(r"/\*[\s\S]*?\*/", "", re.sub(r"//.*$", "", read(root, HELPER), flags=re.M))
    failures = []
    if "OWNER_BOUND_CLIENT_ID = 'SIM_FL_SITE_00'" not in t:
        failures.append("owner_slot_not_SIM_FL_SITE_00")
    if "authProvider === 'CLERK'" not in t or "runType === 'LIVE_RUN'" not in t:
        failures.append("qualifying_rule_not_CLERK_AND_LIVE_RUN")
    sig = re.search(r"export function ownerBoundClientId\(([^)]*)\)", t)
    if not sig or [a.split(":")[0].strip() for a in sig.group(1).split(",")] != ["authProvider", "runType"]:
        failures.append("ownerBoundClientId_signature")
    sig2 = re.search(r"export function participationRole\(([^)]*)\)", t)
    if not sig2 or [a.split(":")[0].strip() for a in sig2.group(1).split(",")] != ["clientId", "ownerBound"]:
        failures.append("participationRole_signature")
    if IDENTITY.search(t.replace("'CLERK'", "")) or re.search(r"fetch\(|\$state|\$derived|from 'svelte|document|window", t):
        failures.append("helper_not_pure")
    return {"ok": not failures, "failures": failures}


def grid_audit(root: Path = ROOT) -> dict[str, Any]:
    t = read(root, GRID)
    failures = []
    if t.count("★ MY EDGE CLIENT") != 1 or "role === 'AUTHENTICATED_OWNER'" not in t:
        failures.append("owner_label_not_exactly_one_guarded_by_role")
    if t.count("SYNTHETIC PEER") != 1 or "role === 'SYNTHETIC_PEER'" not in t:
        failures.append("peer_label")
    if "<b>{id}</b>" not in t or "data-client={id}" not in t:
        failures.append("technical_id_not_displayed_unchanged")
    if "NOT YOUR PHYSIOLOGY" not in t or "SYNTHETIC ENGINEERING" not in t:
        failures.append("synthetic_qualification_missing")
    if "byId[id]?.localExamples" not in t:
        failures.append("local_examples_not_event_derived")
    if "ownerBoundClientId = null" not in t:
        failures.append("prop_default_not_null")
    return {"ok": not failures, "failures": failures}


def live_audit(root: Path = ROOT) -> dict[str, Any]:
    t = read(root, LIVE)
    failures = []
    if "ownerBoundClientId(product.authState.system?.auth_provider, v.runType ?? fed.run?.run_type)" not in t:
        failures.append("binding_not_derived_from_backend_auth_and_run_type")
    if "mine?.localExamples" not in t or "Object.values(mine.milestones).filter((m) => m === 1).length" not in t or "Object.keys(mine.updateDigests).length" not in t:
        failures.append("summary_not_event_derived")
    if "my-raw-examples-sent" not in t or "logical local buffer" not in t or "one demonstration machine" not in t:
        failures.append("locality_wording")
    if IDENTITY.search(re.sub(r"Clerk", "", t)):
        failures.append("live_page_reads_identity")
    return {"ok": not failures, "failures": failures}


def text_audit(root: Path = ROOT) -> dict[str, Any]:
    failures = [rel for rel in PRESENTATION if FORBIDDEN_TEXT.search(read(root, rel))]
    return {"ok": not failures, "failures": failures}


def global_page_ok(root: Path = ROOT) -> bool:
    return not re.search(r"MY EDGE CLIENT|ownerBound|participation|AUTHENTICATED_OWNER", read(root, CLIENTS))


def shadow_ui14(mutate) -> str | None:
    """Copy the frontend + UI locks to a temp tree, apply ``mutate(shadow)``, run the V1_4 verifier there; returns the failure message or None."""
    import json

    import scripts.verify_capstone_ui_v1_4 as v

    shadow = Path(tempfile.mkdtemp(prefix="ui14_"))
    saved = (v.ROOT, v.LOCK_PATH, v.PREDECESSOR, v.frontend_files)
    try:
        for p in v.frontend_files():
            (shadow / p).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / p, shadow / p)
        for rel in ("CAPSTONE_UI_V1_3.lock.json", "CAPSTONE_UI_V1_4.lock.json"):
            (shadow / "artifacts/capstone").mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / "artifacts/capstone" / rel, shadow / "artifacts/capstone" / rel)
        mutate(shadow)
        v.ROOT, v.LOCK_PATH, v.PREDECESSOR = shadow, shadow / "artifacts/capstone/CAPSTONE_UI_V1_4.lock.json", shadow / "artifacts/capstone/CAPSTONE_UI_V1_3.lock.json"
        v.frontend_files = lambda: sorted(str(p.relative_to(shadow)) for p in (shadow / "frontend").rglob("*") if p.is_file())
        try:
            v.verify()
            return None
        except RuntimeError as error:
            return str(error)
    finally:
        v.ROOT, v.LOCK_PATH, v.PREDECESSOR, v.frontend_files = saved
        shutil.rmtree(shadow, ignore_errors=True)
        _ = json
