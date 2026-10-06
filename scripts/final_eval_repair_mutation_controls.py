# ruff: noqa: E501
"""FINAL-EVAL-REPAIR-001 mutation controls (35, frozen names in the protocol): each mutates a DISPOSABLE shadow copy, must be caught by a NAMED guard (while the unmutated shadow passes it), and leaves the working tree byte-identical."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from scripts import final_eval_repair_lib as lib
from scripts import final_eval_repair_presentation as pres
from scripts import ufl_lite_lib as ufl

ROOT = lib.ROOT
OUT = Path(os.environ.get("FER_EVD", ROOT / "reports/final_eval_repair/fer_001"))
BASE = ufl.load_baseline(ROOT)
ABOUT, LANDING, CLIENTS, PART = "frontend/src/routes/app/about/+page.svelte", "frontend/src/routes/+page.svelte", "frontend/src/routes/app/federation/clients/+page.svelte", "frontend/src/lib/product/federation/participation.ts"
TSPOL, JSPOL, RUNBOOK, TRUTH = "frontend/src/lib/product/route-policy.ts", "configs/final_eval_repair/legacy_route_policy_v1.json", "docs/capstone/CLERK_CONNECTED_RUNBOOK_V1_1.md", "configs/final_eval_repair/evaluator_truth_v1.json"
FILLER = "\n\nThis closing note is intentionally a neutral transitional sentence that carries no qualification whatsoever at all. "


def make_shadow() -> Path:
    d = Path(tempfile.mkdtemp(prefix="fermut_"))
    shutil.copytree(ROOT / "frontend/src", d / "frontend/src")
    for rel in (JSPOL, TRUTH, RUNBOOK, "api/product_app_v1_3.py", ufl.BASELINE, "configs/final_eval_repair/fer_001_protocol_v1.json"):
        (d / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / rel, d / rel)
    return d


def sub(rel: str, old: str, new: str):
    def edit(d: Path) -> None:
        t = (d / rel).read_text()
        assert old in t, (rel, old)
        (d / rel).write_text(t.replace(old, new, 1))
    return edit


def append(rel: str, text: str):
    def edit(d: Path) -> None:
        (d / rel).write_text((d / rel).read_text() + text)
    return edit


def drop_route(route: str):
    def edit(d: Path) -> None:
        t = (d / TSPOL).read_text()
        (d / TSPOL).write_text("".join(ln for ln in t.splitlines(True) if not ln.lstrip().startswith(f"'{route}':")))
        doc = json.loads((d / JSPOL).read_text())
        doc["routes"] = [r for r in doc["routes"] if r["pattern"] != route] if route == "/trends" else [r if r["pattern"] != route else {**{k: v for k, v in r.items() if k != "redirect_to"}, "class": "INTERNAL_DYNAMIC"} for r in doc["routes"]]
        (d / JSPOL).write_text(json.dumps(doc))
    return edit


def both(edits):
    def edit(d: Path) -> None:
        for e in edits:
            e(d)
    return edit


def redirect_to(route: str, target: str):
    def edit(d: Path) -> None:
        doc = json.loads((d / JSPOL).read_text())
        for r in doc["routes"]:
            if r["pattern"] == route:
                r["redirect_to"] = target
        (d / JSPOL).write_text(json.dumps(doc))
        t = (d / TSPOL).read_text()
        import re

        (d / TSPOL).write_text(re.sub(rf"'{route}': '[^']*'", f"'{route}': '{target}'", t, count=1))
    return edit


def classify(route: str, cls: str, target: str):
    def edit(d: Path) -> None:
        doc = json.loads((d / JSPOL).read_text())
        for r in doc["routes"]:
            if r["pattern"] == route:
                r["class"], r["redirect_to"] = cls, target
        (d / JSPOL).write_text(json.dumps(doc))
    return edit


def add_route(d: Path) -> None:
    p = d / "frontend/src/routes/app/newpage/+page.svelte"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("<h1>New</h1>\n")


def truth_edit(key: str, value):
    def edit(d: Path) -> None:
        doc = json.loads((d / TRUTH).read_text())
        doc["facts"][key] = value
        (d / TRUTH).write_text(json.dumps(doc))
    return edit


def strip_all(rel: str, needle: str):
    def edit(d: Path) -> None:
        (d / rel).write_text((d / rel).read_text().replace(needle, "REDACTED"))
    return edit


def guard(part: str, edit):
    """(unmutated shadow passes `part`) and (mutated shadow fails `part`)."""
    d = make_shadow()
    try:
        clean = pres.verify_all(d)["parts"][part]["ok"]
        edit(d)
        r = pres.verify_all(d)["parts"][part]
        return (clean and not r["ok"]), f"{part}:{json.dumps({k: v for k, v in r.items() if k != 'ok'})[:90]}"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def hash_group(group: str, rel: str):
    d = Path(tempfile.mkdtemp(prefix="fermut_"))
    try:
        for p in BASE["protected_hashes"][group]:
            (d / p).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / p, d / p)
        clean = ufl.hash_drift(d, BASE, group)
        with (d / rel).open("ab") as h:
            h.write(b"\n# mutated\n")
        return (clean == [] and ufl.hash_drift(d, BASE, group) == [rel]), f"hash_drift:{group}:{rel}"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def ui5_shadow(mutate, expect: str):
    import scripts.verify_capstone_ui_v1_5 as v

    shadow = Path(tempfile.mkdtemp(prefix="fermut_ui_"))
    saved = (v.ROOT, v.LOCK_PATH, v.PREDECESSOR, v.frontend_files)
    try:
        for p in v.frontend_files():
            (shadow / p).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / p, shadow / p)
        (shadow / "artifacts/capstone").mkdir(parents=True, exist_ok=True)
        for rel in ("CAPSTONE_UI_V1_4.lock.json", "CAPSTONE_UI_V1_5.lock.json"):
            shutil.copyfile(ROOT / "artifacts/capstone" / rel, shadow / "artifacts/capstone" / rel)
        mutate(shadow)
        v.ROOT, v.LOCK_PATH, v.PREDECESSOR = shadow, shadow / "artifacts/capstone/CAPSTONE_UI_V1_5.lock.json", shadow / "artifacts/capstone/CAPSTONE_UI_V1_4.lock.json"
        v.frontend_files = lambda: sorted(str(p.relative_to(shadow)) for p in (shadow / "frontend").rglob("*") if p.is_file())
        try:
            v.verify()
            return False, "verify_capstone_ui_v1_5:NOT_CAUGHT"
        except RuntimeError as error:
            return expect in str(error), f"verify_capstone_ui_v1_5:{error}"[:110]
    finally:
        v.ROOT, v.LOCK_PATH, v.PREDECESSOR, v.frontend_files = saved
        shutil.rmtree(shadow, ignore_errors=True)


def _tamper_v14(shadow: Path) -> None:
    (shadow / "artifacts/capstone/CAPSTONE_UI_V1_4.lock.json").write_text("{}\n")


CONTROLS = {
    "ABOUT_RESTORED_NOT_YET_ENABLED": lambda: guard("about", sub(ABOUT, "engineering federation runtime is enabled", "federation product runtime is not yet enabled")),
    "LANDING_PRELOADER_NOT_YET_ENABLED": lambda: guard("landing", sub(LANDING, "FEDERATION RUNTIME / ENGINEERING ENABLED", "FEDERATION RUNTIME / NOT YET ENABLED")),
    "LANDING_PARAGRAPH_DISABLED_WORDING": lambda: guard("landing", sub(LANDING, "In NHM the engineering federation runtime is enabled", "and the federation product runtime is not yet enabled")),
    "FL_OVERVIEW_RENDERS_OLD_CONTENT": lambda: guard("routes", drop_route("/fl/overview")),
    "FL_PERSONAL_MODELS_RENDERS_PERSONALIZATION": lambda: guard("routes", drop_route("/fl/personal-models")),
    "AI_INSIGHTS_RENDERS_FABRICATED_METRICS": lambda: guard("routes", drop_route("/ai/insights")),
    "OVERVIEW_RENDERS_OBSOLETE_WORKBENCH": lambda: guard("routes", drop_route("/overview")),
    "LEGACY_ROUTE_OMITTED_FROM_POLICY": lambda: guard("routes", drop_route("/trends")),
    "CURRENT_ROUTE_CLASSIFIED_LEGACY": lambda: guard("routes", classify("/app/models", "LEGACY_REDIRECT", "/app")),
    "REDIRECT_LOOP": lambda: guard("routes", redirect_to("/overview", "/overview")),
    "REDIRECT_TO_EXTERNAL_ORIGIN": lambda: guard("routes", redirect_to("/overview", "https://evil.example/app")),
    "RUNBOOK_OMITS_MY_EDGE_CLIENT": lambda: guard("runbook", strip_all(RUNBOOK, "MY EDGE CLIENT")),
    "RUNBOOK_CLAIMS_PHYSIOLOGY_TRAINS_FL": lambda: guard("runbook", append(RUNBOOK, FILLER + "Your physiology trains the global federated model.")),
    "RUNBOOK_CLAIMS_PERSONAL_MODEL": lambda: guard("runbook", append(RUNBOOK, FILLER + "NHM trains a personal model for each signed-in user.")),
    "DEMO_GAINS_OWNER_BINDING": lambda: guard("unbound", sub(PART, "authProvider === 'CLERK' && ", "")),
    "REPLAY_GAINS_OWNER_BINDING": lambda: guard("unbound", sub(PART, " && runType === 'LIVE_RUN'", "")),
    "GLOBAL_CLIENTS_GAINS_OWNER_BINDING": lambda: guard("unbound", append(CLIENTS, "\n<b>MY EDGE CLIENT</b>\n")),
    "FEDERATION_RUNTIME_TRUTH_DISABLED": lambda: guard("truth", truth_edit("federation_runtime", "DISABLED")),
    "MODEL_V2_FINAL_CHANGED": lambda: hash_group("scientific", "checkpoints/MODEL_V2_FINAL.pt"),
    "CAL_V2_CHANGED": lambda: hash_group("scientific", "artifacts/CAL_V2.json"),
    "CANDIDATE_DIGEST_CHANGED": lambda: guard("truth", truth_edit("canonical_candidate_digest", "0" * 64)),
    "BACKEND_FILE_DRIFT": lambda: hash_group("reused_unchanged", "product/edge/local_training_buffer.py"),
    "API_DRIFT": lambda: hash_group("reused_unchanged", "api/product_app_v1_3.py"),
    "DB_DRIFT": lambda: hash_group("reused_unchanged", "capstone_persistence/federation_store.py"),
    "FL_RUNTIME_DRIFT": lambda: hash_group("reused_unchanged", "product/federation/service.py"),
    "AUTH_DRIFT": lambda: hash_group("auth", "product/auth/clerk.py"),
    "PREDECESSOR_UI_LOCK_DRIFT": lambda: ui5_shadow(_tamper_v14, "PREDECESSOR_DRIFT"),
    "UI_V1_5_UNBOUND_FILE": lambda: ui5_shadow(lambda s: (s / "frontend/src/lib/product/unbound_extra.ts").write_text("export const x = 1;\n"), "UNBOUND_OR_MISSING"),
    "LASTORIA_REFERENCE_RESTORED": lambda: guard("landing", append(LANDING, "\n<!-- x -->\n<Signature text=\"NHM\" />\n")),
    "HOSPITAL_INSTITUTION_CLAIM_INTRODUCED": lambda: guard("about", sub(ABOUT, "<li>Monitoring states", "<li>NHM federates real hospitals across institutions.</li>\n\t\t<li>Monitoring states")),
    "PRODUCTION_CLAIM_INTRODUCED": lambda: guard("about", sub(ABOUT, "<li>Monitoring states", "<li>NHM is a production system for patients.</li>\n\t\t<li>Monitoring states")),
    "PERSONALIZED_FL_CLAIM_INTRODUCED": lambda: guard("about", sub(ABOUT, "<li>Monitoring states", "<li>NHM provides personalized federated learning for every user.</li>\n\t\t<li>Monitoring states")),
    "CANDIDATE_CALLED_DEPLOYED": lambda: guard("about", sub(ABOUT, "<li>Monitoring states", "<li>The federated candidate is deployed to live monitoring.</li>\n\t\t<li>Monitoring states")),
    "SECAGG_CALLED_DP_OR_ANONYMITY": lambda: guard("about", sub(ABOUT, "<li>Monitoring states", "<li>SecAgg+ gives differential privacy and anonymity.</li>\n\t\t<li>Monitoring states")),
    "CURRENT_ROUTE_UNCLASSIFIED": lambda: guard("routes", add_route),
}


def main() -> int:
    names = json.loads((ROOT / "configs/final_eval_repair/fer_001_protocol_v1.json").read_text())["mutation_controls"]
    assert list(CONTROLS) == names, "MUTATION_NAMES_DIVERGE_FROM_FROZEN_PROTOCOL"
    before = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True).stdout
    results = []
    for name in names:
        try:
            caught, failing = CONTROLS[name]()
        except Exception as error:   # an exception is not a catch
            caught, failing = False, f"EXCEPTION:{type(error).__name__}:{error}"[:120]
        after = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True).stdout
        results.append({"mutation": name, "caught": bool(caught), "failing_check": failing, "restored": after == before, "applied_to": "disposable shadow copy"})
        print(name, caught, failing[:70], flush=True)
    payload = {"controls": results, "all_caught": all(r["caught"] for r in results), "all_restored": all(r["restored"] for r in results), "count": len(results)}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "mutation_controls.json").write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n")
    print(json.dumps({k: payload[k] for k in ("count", "all_caught", "all_restored")}))
    return 0 if payload["all_caught"] and payload["all_restored"] else 1


if __name__ == "__main__":
    sys.exit(main())
