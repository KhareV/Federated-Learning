# ruff: noqa: E501
"""UFL-LITE-003 mutation controls (35): each mutates a COPY of the sanitized real-Clerk observations / evidence / source tree, must fail a NAMED analyzer or frozen check
(while the unmutated input passes it), and leaves the working tree byte-identical."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from scripts import ufl_lite_002_lib as plib
from scripts import ufl_lite_003_lib as an
from scripts import ufl_lite_lib as lib
from scripts.run_capstone_clerk_connected_e2e import scan_tree

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(os.environ.get("UFL_EVD", ROOT / "reports/ufl_lite/ufl_lite_003"))
BASE = lib.load_baseline(ROOT)
PY = sys.executable


def observation_control(name: str):
    o = json.loads((OUT / "owner_e2e_observations.json").read_text())
    clean = an.analyze_all(o["A"], o["B"], o["A_return"], BASE)
    a, b, a2, group = an.mutate(name, o["A"], o["B"], o["A_return"])
    mutated = an.analyze_all(a, b, a2, BASE)
    failing = sorted(k for k, v in mutated[group].items() if not v)
    return (all(clean[group].values()) and bool(failing)), f"{group}:{failing}"[:110]


def eval_check(check: str, edit):
    """Run a frozen evaluator check against a temporary copy of the evidence directory."""
    d = Path(tempfile.mkdtemp(prefix="uflmut3_"))
    try:
        shutil.copytree(OUT, d / "evd")
        env = {**os.environ, "UFL_EVD": str(d / "evd"), "PYTHONPATH": "src:."}
        run = lambda: subprocess.run([PY, "-c", f"from scripts.ufl_lite_003_evaluate_gate import build_checks; print(bool(build_checks()[{check!r}]()))"], cwd=ROOT, env=env, capture_output=True, text=True).stdout.strip()  # noqa: E731
        clean = run()
        edit(d / "evd")
        mutated = run()
        return (clean == "True" and mutated == "False"), f"evaluator:{check}:{clean}->{mutated}"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def patch_json(rel: str, fn):
    def edit(evd: Path) -> None:
        p = evd / rel
        data = json.loads(p.read_text())
        fn(data)
        p.write_text(json.dumps(data))
    return edit


def secret_in_evidence():
    d = Path(tempfile.mkdtemp(prefix="uflmut3_"))
    try:
        (d / "owner_e2e_analysis.json").write_text(json.dumps({"note": "sk" + "_test_FAKEFAKEFAKEFAKE"}))
        return bool(scan_tree(d, "sk" + "_test_")), "scan_tree:secret_prefix"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def group_mutation(group: str, rel: str):
    d = Path(tempfile.mkdtemp(prefix="uflmut3_"))
    try:
        for p in BASE["protected_hashes"][group]:
            (d / p).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / p, d / p)
        clean = lib.hash_drift(d, BASE, group)
        (d / rel).write_text((d / rel).read_text() + "\n# mutated\n")
        return (clean == [] and lib.hash_drift(d, BASE, group) == [rel]), f"hash_drift:{group}:{rel}"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def ui_shadow(mutate):
    msg = plib.shadow_ui14(mutate)
    return msg is not None, f"verify_capstone_ui_v1_4:{msg}"[:110]


def _tamper_lock(shadow: Path) -> None:
    p = shadow / "artifacts/capstone/CAPSTONE_UI_V1_4.lock.json"
    lock = json.loads(p.read_text())
    lock["status"] = "TAMPERED"
    p.write_text(json.dumps(lock))


STATIC = {
    "SECRET_IN_EVIDENCE": secret_in_evidence,
    "CLERK_TRAFFIC_IN_DEMO_REGRESSION": lambda: eval_check("demo_regression", patch_json("demo_regression.json", lambda d: d.update(clerk_origins_contacted=["clerk.accounts.dev"]))),
    "DEMO_SEMANTIC_DIGEST_CHANGED": lambda: eval_check("demo_digest", patch_json("demo_regression.json", lambda d: d.update(semantic_sha256="0" * 64))),
    "PRODUCT_BACKEND_CODE_CHANGED": lambda: group_mutation("reused_unchanged", "product/federation/service.py"),
    "FRONTEND_FEATURE_CODE_CHANGED": lambda: ui_shadow(lambda s: (s / plib.GRID).write_text((s / plib.GRID).read_text() + "\n<!-- drift -->\n")),
    "CLEAN_CLONE_TARGET_SHA_MISMATCH": lambda: eval_check("clean_clone_target_matches", patch_json("clean_clone/clean_clone.json", lambda d: d.update(target_sha="0" * 40))),
    "UI_V1_4_LOCK_CHANGED": lambda: ui_shadow(_tamper_lock),
}


def main() -> int:
    names = json.loads((ROOT / "configs/ufl_lite/uflg2_protocol_v1.json").read_text())["mutation_controls"]
    before = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True).stdout
    results = []
    for name in names:
        try:
            caught, failing = STATIC[name]() if name in STATIC else observation_control(name)
        except Exception as error:   # an exception is not a catch
            caught, failing = False, f"EXCEPTION:{type(error).__name__}:{error}"[:120]
        after = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True).stdout
        results.append({"mutation": name, "caught": bool(caught), "failing_check": failing, "restored": after == before, "applied_to": "copy of sanitized observations / evidence / source tree"})
        print(name, caught, failing[:70], flush=True)
    payload = {"controls": results, "all_caught": all(r["caught"] for r in results), "all_restored": all(r["restored"] for r in results), "count": len(results)}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "mutation_controls.json").write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n")
    print(json.dumps({k: payload[k] for k in ("count", "all_caught", "all_restored")}))
    return 0 if payload["all_caught"] and payload["all_restored"] else 1


if __name__ == "__main__":
    sys.exit(main())
