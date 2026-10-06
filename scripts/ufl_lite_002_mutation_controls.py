# ruff: noqa: E501
"""UFL-LITE-002 mutation controls (18): each applies a mutation to a TEMPORARY copy / synthetic input, must fail a NAMED static check, and leaves the working tree byte-identical."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from scripts import ufl_lite_002_lib as plib
from scripts import ufl_lite_lib as lib

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(os.environ.get("UFL_EVD", ROOT / "reports/ufl_lite/ufl_lite_002"))
BASE = lib.load_baseline(ROOT)


def tmp_files(rels: tuple[str, ...], rel: str, edit):
    d = Path(tempfile.mkdtemp(prefix="uflmut2_"))
    try:
        for p in rels:
            (d / p).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / p, d / p)
        edit(d / rel)
        return d
    except Exception:
        shutil.rmtree(d, ignore_errors=True)
        raise


def sub(old: str, new: str):
    def edit(path: Path) -> None:
        t = path.read_text()
        assert old in t, old
        path.write_text(t.replace(old, new, 1))
    return edit


def audit(fn_name: str, rel: str, edit, files: tuple[str, ...] | None = None):
    d = tmp_files(files or (*plib.PRESENTATION, plib.CLIENTS), rel, edit)
    try:
        r = getattr(plib, fn_name)(d)
        return (not r["ok"] if isinstance(r, dict) else not r), f"{fn_name}:{r['failures'] if isinstance(r, dict) else r}"[:110]
    finally:
        shutil.rmtree(d, ignore_errors=True)


def group_mutation(group: str, rel: str):
    d = Path(tempfile.mkdtemp(prefix="uflmut2_"))
    try:
        for p in BASE["protected_hashes"][group]:
            (d / p).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / p, d / p)
        clean = lib.hash_drift(d, BASE, group)
        (d / rel).write_text((d / rel).read_text() + "\n# mutated\n")
        return (clean == [] and lib.hash_drift(d, BASE, group) == [rel]), f"hash_drift:{group}:{rel}"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def ui_shadow(mutate, expect: str):
    msg = plib.shadow_ui14(mutate)
    return (msg is not None and expect in msg), f"verify_capstone_ui_v1_4:{msg}"[:110]


MUTATIONS = (
    ("BINDING_APPEARS_IN_DEMO_MODE", lambda: audit("helper_audit", plib.HELPER, sub("authProvider === 'CLERK' && ", ""))),
    ("BINDING_APPEARS_ON_REPLAY", lambda: audit("helper_audit", plib.HELPER, sub(" && runType === 'LIVE_RUN'", ""))),
    ("GLOBAL_CLIENTS_PAGE_SHOWS_MY_EDGE_CLIENT", lambda: audit("global_page_ok", plib.CLIENTS, lambda p: p.write_text(p.read_text() + "\n<b>MY EDGE CLIENT</b>\n"))),
    ("SITE_01_ACCIDENTALLY_OWNER_BOUND", lambda: audit("helper_audit", plib.HELPER, sub("'SIM_FL_SITE_00'", "'SIM_FL_SITE_01'"))),
    ("TWO_CLIENTS_SHOW_MY_EDGE_CLIENT", lambda: audit("grid_audit", plib.GRID, sub("{:else if role === 'SYNTHETIC_PEER'}<span class=\"peer\" data-testid=\"peer-label\">SYNTHETIC PEER</span>", "{:else if role === 'SYNTHETIC_PEER'}<span class=\"mine\">★ MY EDGE CLIENT</span>"))),
    ("SITE_00_TECHNICAL_ID_RENAMED", lambda: audit("grid_audit", plib.GRID, sub("<b>{id}</b>", "<b>MY_EDGE_CLIENT</b>"))),
    ("USER_ID_OR_EMAIL_ENTERS_BINDING_INPUT", lambda: audit("helper_audit", plib.HELPER, sub("ownerBoundClientId(authProvider: AuthProviderName | null | undefined, runType:", "ownerBoundClientId(authProvider: AuthProviderName | null | undefined, userEmail: string, runType:"))),
    ("LOCAL_EXAMPLE_COUNT_HARDCODED", lambda: audit("live_audit", plib.LIVE, sub("{mine?.localExamples ?? '--'}", "93"))),
    ("UPDATE_COUNT_FABRICATED", lambda: audit("live_audit", plib.LIVE, sub("Object.keys(mine.updateDigests).length", "plannedRounds"))),
    ("CONTRIBUTION_PERCENTAGE_ADDED", lambda: audit("text_audit", plib.LIVE, lambda p: p.write_text(p.read_text() + "\n<p>contribution 12.5%</p>\n"))),
    ("CLIENT_COUNT_BECOMES_9", lambda: ((not lib.cohort_ok([*lib.CLIENT_IDS, "SIM_FL_SITE_08"])["ok"]), "cohort_ok:client_count_not_8")),
    ("CANDIDATE_DIGEST_CHANGES", lambda: ((not lib.candidate_digest_ok("0" * 64)), "candidate_digest_ok")),
    ("FEDERATION_RUNTIME_FILE_CHANGES", lambda: group_mutation("reused_unchanged", "product/federation/service.py")),
    ("API_SCHEMA_CHANGES", lambda: group_mutation("reused_unchanged", "api/product_app_v1_3.py")),
    ("SQLITE_SCHEMA_CHANGES", lambda: group_mutation("reused_unchanged", "capstone_persistence/federation_store.py")),
    ("CLERK_AUTH_CHANGES", lambda: group_mutation("auth", "product/auth/clerk.py")),
    ("PREDECESSOR_UI_LOCK_CHANGES", lambda: ui_shadow(lambda s: (s / "artifacts/capstone/CAPSTONE_UI_V1_3.lock.json").write_text("{}\n"), "PREDECESSOR_DRIFT")),
    ("UNBOUND_FRONTEND_DRIFT_ESCAPES_UI_LOCK", lambda: ui_shadow(lambda s: (s / "frontend/src/lib/product/federation/unbound_extra.ts").write_text("export const x = 1;\n"), "UNBOUND_OR_MISSING")),
)


def main() -> int:
    before = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True).stdout
    results = []
    for name, fn in MUTATIONS:
        try:
            caught, failing = fn()
        except Exception as error:   # an exception is not a catch
            caught, failing = False, f"EXCEPTION:{type(error).__name__}:{error}"[:120]
        after = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True).stdout
        results.append({"mutation": name, "caught": bool(caught), "failing_check": failing, "restored": after == before, "applied_to": "temporary copy / synthetic input"})
        print(name, caught, failing[:70], flush=True)
    payload = {"controls": results, "all_caught": all(r["caught"] for r in results), "all_restored": all(r["restored"] for r in results), "count": len(results)}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "mutation_controls.json").write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n")
    print(json.dumps({k: payload[k] for k in ("count", "all_caught", "all_restored")}))
    return 0 if payload["all_caught"] and payload["all_restored"] else 1


if __name__ == "__main__":
    sys.exit(main())
