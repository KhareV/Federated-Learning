# ruff: noqa: E501
"""FINAL-EVAL-REPAIR-002 mutation controls (38, frozen names in the protocol): each mutates a DISPOSABLE shadow copy, must be caught by a NAMED guard (while the unmutated shadow passes it), and leaves the working tree byte-identical."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from scripts import final_eval_repair_002_provenance as prov
from scripts import final_eval_repair_lib as lib
from scripts import final_eval_repair_mutation_controls as m1
from scripts import ufl_lite_lib as ufl

ROOT = lib.ROOT
OUT = Path(os.environ.get("FER2_EVD", ROOT / "reports/final_eval_repair/fer_002"))
BASE = ufl.load_baseline(ROOT)
NG, PW, LAND, GLOBE, BOOT = "frontend/src/lib/components/landing/NeuralGraph.svelte", "frontend/src/lib/components/landing/ProductWorkstation.svelte", "frontend/src/routes/+page.svelte", "frontend/src/lib/components/magic/globe/globe.svelte", "frontend/src/routes/app/+layout.svelte"


def make_shadow() -> Path:
    d = Path(tempfile.mkdtemp(prefix="fer2mut_"))
    shutil.copytree(ROOT / "frontend/src", d / "frontend/src")
    shutil.copytree(ROOT / "configs/final_eval_repair", d / "configs/final_eval_repair")
    for rel in ("docs/capstone/CLERK_CONNECTED_RUNBOOK_V1_1.md", "api/product_app_v1_3.py", ufl.BASELINE):
        (d / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / rel, d / rel)
    return d


def sub(rel: str, old: str, new: str):
    def edit(d: Path) -> None:
        t = (d / rel).read_text()
        assert old in t, (rel, old)
        (d / rel).write_text(t.replace(old, new, 1))
    return edit


def inject(rel: str, text: str):
    def edit(d: Path) -> None:
        (d / rel).write_text((d / rel).read_text() + f"\n<p>{text}</p>\n")
    return edit


def guard(check, edit):
    """check(root) -> (ok, detail). The unmutated shadow must pass; the mutated shadow must FAIL."""
    d = make_shadow()
    try:
        clean, _ = check(d)
        edit(d)
        ok, detail = check(d)
        return (clean and not ok), detail
    finally:
        shutil.rmtree(d, ignore_errors=True)


def claim_check(root: Path):
    r = prov.verify_all(root)
    bad = r["parts"]["claims_scan"]["uncovered"][:1] or r["parts"]["provenance"]["problems"][:1]
    return r["ok"], f"verify:{json.dumps(bad)[:90]}"


def a11y_check(root: Path):
    r = prov.a11y_static_ok(root)
    return r["ok"], f"a11y:{[k for k, v in r['checks'].items() if not v]}"


def hash_group(group: str, rel: str):
    d = Path(tempfile.mkdtemp(prefix="fer2mut_"))
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


def ui6_shadow(mutate, expect: str):
    import scripts.verify_capstone_ui_v1_6 as v

    shadow = Path(tempfile.mkdtemp(prefix="fer2mut_ui_"))
    saved = (v.ROOT, v.LOCK_PATH, v.PREDECESSOR, v.frontend_files)
    try:
        for p in v.frontend_files():
            (shadow / p).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / p, shadow / p)
        (shadow / "artifacts/capstone").mkdir(parents=True, exist_ok=True)
        for rel in ("CAPSTONE_UI_V1_5.lock.json", "CAPSTONE_UI_V1_6.lock.json"):
            shutil.copyfile(ROOT / "artifacts/capstone" / rel, shadow / "artifacts/capstone" / rel)
        mutate(shadow)
        v.ROOT, v.LOCK_PATH, v.PREDECESSOR = shadow, shadow / "artifacts/capstone/CAPSTONE_UI_V1_6.lock.json", shadow / "artifacts/capstone/CAPSTONE_UI_V1_5.lock.json"
        v.frontend_files = lambda: sorted(str(p.relative_to(shadow)) for p in (shadow / "frontend").rglob("*") if p.is_file())
        try:
            v.verify()
            return False, "verify_capstone_ui_v1_6:NOT_CAUGHT"
        except RuntimeError as error:
            return expect in str(error), f"verify_capstone_ui_v1_6:{error}"[:110]
    finally:
        v.ROOT, v.LOCK_PATH, v.PREDECESSOR, v.frontend_files = saved
        shutil.rmtree(shadow, ignore_errors=True)


def _tamper_v15(shadow: Path) -> None:
    (shadow / "artifacts/capstone/CAPSTONE_UI_V1_5.lock.json").write_text("{}\n")


def _drop_qualification(d: Path) -> None:
    sub(LAND, "Simulated wearable, accelerated timing; released", "Released")(d)


CONTROLS = {
    "RESTORE_99_8_COVERAGE": lambda: guard(claim_check, sub(NG, "<small>Illustrative</small>", "<small>99.8% Coverage</small>")),
    "RESTORE_99_8_BLIND_INTERVALS": lambda: guard(claim_check, sub(NG, "No measured percentage is claimed.", "Illustrates the 99.8% unmonitored blind intervals between sporadic clinic visits.")),
    "RESTORE_LIVE_EDGE_SYNAPSE_GRAPH": lambda: guard(claim_check, sub(NG, "ILLUSTRATIVE SIGNAL-FLOW GRAPH</span>", "LIVE EDGE SYNAPSE GRAPH</span>")),
    "RESTORE_REALTIME_FEATURE_VECTORS": lambda: guard(claim_check, sub(NG, "Hover any node for a conceptual description of a feature path. All values are illustrative - not live telemetry.", "Hover any node to inspect real-time feature vectors and cross-modal correlation paths.")),
    "INTRODUCE_STATIC_91_CONFIDENCE": lambda: guard(claim_check, inject(NG, "Model confidence 91%")),
    "INTRODUCE_STATIC_0_08_ANOMALY_SCORE": lambda: guard(claim_check, inject(NG, "Anomaly score 0.08")),
    "INTRODUCE_CURRENT_SPO2_98": lambda: guard(claim_check, inject(PW, "Current SpO₂: 98%")),
    "INTRODUCE_NORMAL_ECG": lambda: guard(claim_check, inject(PW, "Normal ECG")),
    "INTRODUCE_LIVE_PATIENT_DATA": lambda: guard(claim_check, inject(PW, "Live patient data")),
    "INTRODUCE_REAL_WEARABLE_STREAM": lambda: guard(claim_check, inject(PW, "Real wearable stream")),
    "INTRODUCE_ON_DEVICE_INFERENCE": lambda: guard(claim_check, inject(PW, "On-device inference")),
    "INTRODUCE_EDGE_MODEL_ON_WEARABLE": lambda: guard(claim_check, inject(PW, "Edge model running on wearable")),
    "INTRODUCE_UNSOURCED_PERCENT_ACCURACY": lambda: guard(claim_check, inject(NG, "Model accuracy 97%")),
    "INTRODUCE_UNSOURCED_PERCENT_COVERAGE": lambda: guard(claim_check, inject(NG, "Coverage 99%")),
    "INTRODUCE_CLINICAL_MONITORING": lambda: guard(claim_check, inject(PW, "Clinical monitoring")),
    "REMOVE_ILLUSTRATIVE_QUALIFICATION": lambda: guard(claim_check, sub(PW, "Resting scenario (72 BPM, synthetic)", "Resting (72 BPM)")),
    "REMOVE_LANDING_SKIP_LINK": lambda: guard(a11y_check, sub(LAND, '<a class="skip-link" href="#top">Skip to main content</a>', "")),
    "UNNAME_LANDING_NAV": lambda: guard(a11y_check, sub(LAND, '<nav class="nav" aria-label="NHM landing navigation">', '<nav class="nav">')),
    "NEURALGRAPH_RAF_IGNORES_REDUCED_MOTION": lambda: guard(a11y_check, sub(NG, "if (!reducedMotion) animId", "animId")),
    "GLOBE_IGNORES_REDUCED_MOTION": lambda: guard(a11y_check, lambda d: (d / GLOBE).write_text((d / GLOBE).read_text().replace("prefers-reduced-motion", "prefers-color-scheme"))),
    "LOADER_LOSES_HEADING": lambda: guard(a11y_check, sub(BOOT, "<h1>Opening the NHM workspace…</h1>", "<p>Opening the NHM workspace…</p>")),
    "PROVENANCE_QUALIFICATION_REMOVED": lambda: guard(claim_check, _drop_qualification),
    "ABOUT_RESTORED_NOT_YET_ENABLED": lambda: m1.CONTROLS["ABOUT_RESTORED_NOT_YET_ENABLED"](),
    "LANDING_PRELOADER_NOT_YET_ENABLED": lambda: m1.CONTROLS["LANDING_PRELOADER_NOT_YET_ENABLED"](),
    "FL_OVERVIEW_RENDERS_OLD_CONTENT": lambda: m1.CONTROLS["FL_OVERVIEW_RENDERS_OLD_CONTENT"](),
    "DEMO_GAINS_OWNER_BINDING": lambda: m1.CONTROLS["DEMO_GAINS_OWNER_BINDING"](),
    "RUNBOOK_OMITS_MY_EDGE_CLIENT": lambda: m1.CONTROLS["RUNBOOK_OMITS_MY_EDGE_CLIENT"](),
    "LASTORIA_REFERENCE_RESTORED": lambda: m1.CONTROLS["LASTORIA_REFERENCE_RESTORED"](),
    "BACKEND_FILE_DRIFT": lambda: hash_group("reused_unchanged", "product/edge/local_training_buffer.py"),
    "API_DRIFT": lambda: hash_group("reused_unchanged", "api/product_app_v1_3.py"),
    "DB_DRIFT": lambda: hash_group("reused_unchanged", "capstone_persistence/federation_store.py"),
    "FL_RUNTIME_DRIFT": lambda: hash_group("reused_unchanged", "product/federation/service.py"),
    "AUTH_DRIFT": lambda: hash_group("auth", "product/auth/clerk.py"),
    "MODEL_V2_FINAL_CHANGED": lambda: hash_group("scientific", "checkpoints/MODEL_V2_FINAL.pt"),
    "CAL_V2_CHANGED": lambda: hash_group("scientific", "artifacts/CAL_V2.json"),
    "CANDIDATE_DIGEST_CHANGED": lambda: m1.CONTROLS["CANDIDATE_DIGEST_CHANGED"](),
    "PREDECESSOR_UI_LOCK_DRIFT": lambda: ui6_shadow(_tamper_v15, "PREDECESSOR_DRIFT"),
    "UI_V1_6_UNBOUND_FILE": lambda: ui6_shadow(lambda s: (s / "frontend/src/lib/product/unbound_extra.ts").write_text("export const x = 1;\n"), "UNBOUND_OR_MISSING"),
}


def main() -> int:
    names = json.loads((ROOT / "configs/final_eval_repair/fer_002_protocol_v1.json").read_text())["mutation_controls"]
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
