# ruff: noqa: E501
"""UFL-LITE-002 entry/final protection audit. The connected-auth successor is additive: every file tracked at entry must be
byte-identical at final except the ufl_lite control registries; every new file must live in an explicit UFL-LITE-002
namespace. The completed capstone release (tag capstone-release-v1 -> 3ad1b07...) must not move. No secret value is ever read into
a report: only booleans are recorded."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from scripts.cap_001_protected_audit import named_components, tracked_hashes
from scripts.cap_011_protected_audit import all_locks

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/ufl_lite/ufl_lite_002"
EXPECTED_ENTRY = "6871e0891ad697dab3f122afaba2d331a279ec8c"
CLERK_TAG, CLERK_TARGET = "capstone-clerk-connected-v1", "4cb20ec1093f3a8697827abfffc1e5c1fd787055"
RELEASE_TARGET = "3ad1b07408a0c3556fbc5039f1a7a4fee824db96"
TAG = "capstone-release-v1"
ADDITIVE_PREFIXES = (
    "manifests/ufl_lite/", "configs/ufl_lite/", "frontend/src/lib/product/federation/participation.ts", "frontend/src/lib/product/federation/__tests__/participation", "artifacts/capstone/CAPSTONE_UI_V1_4", "artifacts/capstone/CAPSTONE_FRONTEND_PRODUCT_PROTOCOL_V1.amendment_", "artifacts/capstone/CAPSTONE_FEDERATION_UX_PROTOCOL_V1.amendment_", "artifacts/capstone/CAPSTONE_HISTORY_EVIDENCE_PROTOCOL_V1.amendment_", "artifacts/capstone/CAPSTONE_FACULTY_DEMO_PROTOCOL_V1.amendment_", "artifacts/capstone/CLERK_LIVE_001_PROTOCOL_V1.amendment_", "scripts/freeze_capstone_ui_v1_4.py", "scripts/verify_capstone_ui_v1_4.py", "configs/ufl_lite/", "docs/ufl_lite/", "artifacts/ufl_lite/", "reports/ufl_lite/", "scripts/ufl_lite_", "tests/test_ufl_lite_",
)
# The ONLY pre-existing files UFL-LITE-002 may change: the three presentation files and the successor-aware historical UI verifiers /
# CAP-010 + CAP-008 frontend guards (pure SUCCESSOR_COMPATIBILITY_ONLY amendments). Everything else must be byte-identical.
MODIFIABLE: tuple[str, ...] = (
    "manifests/ufl_lite/task_registry_v1.csv", "manifests/ufl_lite/gate_registry_v1.csv", "frontend/src/lib/components/product/federation/ClientGrid.svelte", "frontend/src/routes/app/federation/live/+page.svelte", "frontend/src/routes/app/federation/rounds/+page.svelte",
    "scripts/verify_capstone_ui_v1.py", "scripts/verify_capstone_ui_v1_1.py", "scripts/verify_capstone_ui_v1_2.py", "scripts/verify_capstone_ui_v1_3.py",
    "tests/test_capstone_full_demo.py", "tests/test_capstone_federation_ui.py", "frontend/src/lib/product/federation/__tests__/components.test.ts",
)
PROTECTED_PREFIXES = ("api/", "product/", "capstone_persistence/", "federated/", "privacy/", "simulation/", "src/", "checkpoints/", "frontend/", "reports/model_v2/", "reports/capstone/", "reports/clerk_connected/", "release/", "scripts/run_capstone", "scripts/clerk_")
SECRET_ENV = "CLERK_SECRET_KEY"


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()


def statuses() -> dict[str, dict[str, str]]:
    import csv

    out = {}
    for name, key in (("task", "task_id"), ("gate", "gate_id")):
        with (ROOT / f"manifests/capstone/{name}_registry_v1.csv").open(newline="", encoding="utf-8") as h:
            out[name] = {r[key]: r["status"] for r in csv.DictReader(h)}
    return out


def clerk_tag_target() -> str:
    return subprocess.run(["git", "ls-remote", "origin", f"refs/tags/{CLERK_TAG}^{{}}"], cwd=ROOT, capture_output=True, text=True).stdout.split("\t")[0]


def uflg0_ok() -> bool:
    import csv

    from scripts.ufl_lite_001_evaluate_gate import _lock_ok

    with (ROOT / "manifests/ufl_lite/task_registry_v1.csv").open(newline="", encoding="utf-8") as h:
        t = {r["task_id"]: r["status"] for r in csv.DictReader(h)}.get("UFL-LITE-001") == "PASS"
    with (ROOT / "manifests/ufl_lite/gate_registry_v1.csv").open(newline="", encoding="utf-8") as h:
        g = {r["gate_id"]: r["status"] for r in csv.DictReader(h)}.get("UFLG0") == "PASS"
    return t and g and _lock_ok()


def clerk_lineage_ok() -> bool:
    import csv

    from scripts.verify_clerk_connected import verify

    with (ROOT / "manifests/clerk_connected/task_registry_v1.csv").open(newline="", encoding="utf-8") as h:
        ok_task = {r["task_id"]: r["status"] for r in csv.DictReader(h)}.get("CLERK-LIVE-001") == "PASS"
    with (ROOT / "manifests/clerk_connected/gate_registry_v1.csv").open(newline="", encoding="utf-8") as h:
        ok_gate = {r["gate_id"]: r["status"] for r in csv.DictReader(h)}.get("CLERKG0") == "PASS"
    return ok_task and ok_gate and verify()["status"] == "PASS"


def tag_target() -> str:
    return subprocess.run(["git", "ls-remote", "origin", f"refs/tags/{TAG}^{{}}"], cwd=ROOT, capture_output=True, text=True).stdout.split("\t")[0]


def secret_in_tracked() -> bool:
    """True if the EXACT secret value occurs in any tracked or untracked-unignored file or in the staged diff (value never recorded)."""
    secret = os.environ.get(SECRET_ENV, "")
    if not secret:
        return False
    for args in (("grep", "-lF", "--untracked", "-e", secret), ("grep", "-lF", "--cached", "-e", secret)):
        if subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True).stdout.strip():
            return True
    return False


def ui13_ok() -> bool:
    """The newest registered UI successor must verify (V1_4 once it exists, else V1_3)."""
    if (ROOT / "artifacts/capstone/CAPSTONE_UI_V1_4.lock.json").exists():
        from scripts.verify_capstone_ui_v1_4 import verify
    else:
        from scripts.verify_capstone_ui_v1_3 import verify

    return verify()["status"] == "PASS"


def entry() -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    head, origin = git("rev-parse", "HEAD"), git("rev-parse", "origin/main")
    dirty = [ln for ln in git("status", "--porcelain").splitlines() if "ufl_lite" not in ln and "ufl_lite_002" not in ln]
    if origin != head or dirty:
        raise RuntimeError("CLERK_ENTRY_STATE_CONFLICT")
    intervening = git("log", "--format=%h %s", f"{EXPECTED_ENTRY}..HEAD").splitlines()
    st = statuses()
    exp_t = {f"CAP-{i:03d}": "PASS" for i in range(1, 12)}
    exp_g = {f"CAPG{i}": "PASS" for i in range(11)}
    if any(st["task"].get(k) != v for k, v in exp_t.items()) or any(st["gate"].get(k) != v for k, v in exp_g.items()) or "CAP-012" in st["task"]:
        raise RuntimeError("CLERK_PRIOR_STATUS_CONFLICT")
    if tag_target() != RELEASE_TARGET:
        raise RuntimeError("CAPSTONE_RELEASE_TAG_MOVED")
    if not uflg0_ok():
        raise RuntimeError("UFLG0_NOT_PASS_OR_LOCK_BROKEN")
    if clerk_tag_target() != CLERK_TARGET or not clerk_lineage_ok():
        raise RuntimeError("CLERK_CONNECTED_LINEAGE_OR_TAG_BROKEN")
    locks = all_locks()
    if not all(v["verified"] for v in locks.values()):
        raise RuntimeError("CLERK_PRIOR_LOCK_FAILURE")
    ignored = subprocess.run(["git", "check-ignore", "-q", ".env"], cwd=ROOT).returncode == 0
    files, comps = tracked_hashes(), named_components()
    audit = {"phase": "UFL-LITE-002", "gate": "CLERKG0", "entry_sha": head, "origin_main_sha": origin, "expected_entry_sha": EXPECTED_ENTRY, "entry_is_expected": head == EXPECTED_ENTRY, "intervening_commits": intervening,
             "working_tree_clean_before_entry": True, "capstone_prior_tasks": exp_t, "capstone_prior_gates": exp_g, "cap_012_absent": True, "prior_locks_verified": True, "locks": sorted(locks),
             "capstone_release_target_sha": RELEASE_TARGET, "capstone_release_tag": TAG, "capstone_release_tag_points_to_target": True, "clerk_connected_tag": CLERK_TAG, "clerk_connected_target": CLERK_TARGET, "clerk_connected_tag_points_to_target": True, "clerk_live_001_pass_and_lock_verified": True, "uflg0_pass_and_lock_verified": True, "capstone_release_decision_untouched": True,
             "protected_tracked_file_count": len(files), "dotenv_ignored_by_git": ignored, "dotenv_tracked": bool(git("ls-files", ".env")), "secret_value_in_tracked_or_staged_files": secret_in_tracked(),
             "ci_queried": False, "ci_triggered": False, "key_rotation_performed": False, "key_revocation_performed": False, "remote": git("remote", "get-url", "origin")}
    if audit["dotenv_tracked"] or audit["secret_value_in_tracked_or_staged_files"] or not ignored:
        raise RuntimeError("CLERK_CREDENTIAL_HYGIENE_FAILURE")
    snap = {"entry_sha": head, "tracked_file_count": len(files), "tracked_files_sha256": files, "named_components": comps, "frontend": {p: d for p, d in files.items() if p.startswith("frontend/")}}
    for name, value in (("entry_audit.json", audit), ("protected_artifact_entry.json", snap), ("prior_lock_verification.json", locks)):
        (OUT / name).write_text(json.dumps(value, sort_keys=True, indent=1, default=str) + "\n", encoding="utf-8")
    return {"entry_sha": head, "tracked": len(files), "locks_ok": all(v["verified"] for v in locks.values())}


def final() -> int:
    base = json.loads((OUT / "protected_artifact_entry.json").read_text())
    now, before = tracked_hashes(), base["tracked_files_sha256"]
    changed = sorted(p for p, h in before.items() if p in now and now[p] != h)
    removed = sorted(p for p in before if p not in now)
    added = sorted(p for p in now if p not in before)
    illegal = [p for p in changed if p not in MODIFIABLE]
    non_additive = [p for p in added if not p.startswith(ADDITIVE_PREFIXES)]
    comps = named_components()
    drift = sorted(k for k, v in comps.items() if base["named_components"][k]["sha256"] != v["sha256"])
    locks = all_locks()
    result = {"entry_sha": base["entry_sha"], "head_sha": git("rev-parse", "HEAD"), "modified_since_entry": changed, "modified_outside_allowed": illegal, "removed_since_entry": removed, "added_count": len(added),
              "added_outside_additive_namespace": non_additive, "named_component_drift": drift, "protected_tree_modified": [p for p in changed + removed if p.startswith(PROTECTED_PREFIXES) and p not in MODIFIABLE],
              "frontend_drift": [p for p, h in base["frontend"].items() if now.get(p) != h and p not in MODIFIABLE], "authorised_modifications": [p for p in changed if p in MODIFIABLE], "locks_verified": {k: v["verified"] for k, v in locks.items()}, "capstone_release_tag_unchanged": tag_target() == RELEASE_TARGET, "clerk_connected_tag_unchanged": clerk_tag_target() == CLERK_TARGET, "clerk_lineage_ok": clerk_lineage_ok(), "uflg0_ok": uflg0_ok(), "ui_v1_3_verified": ui13_ok()}
    result["protected_artifact_drift"] = bool(illegal or removed or non_additive or drift or result["protected_tree_modified"] or result["frontend_drift"] or not all(v["verified"] for v in locks.values()) or not result["capstone_release_tag_unchanged"] or not result["clerk_connected_tag_unchanged"] or not result["clerk_lineage_ok"] or not result["uflg0_ok"] or not result["ui_v1_3_verified"])
    (OUT / "protected_artifact_final.json").write_text(json.dumps(result, indent=1, sort_keys=True) + "\n")
    print(json.dumps({k: result[k] for k in ("protected_artifact_drift", "modified_outside_allowed", "added_outside_additive_namespace", "capstone_release_tag_unchanged")}))
    return 1 if result["protected_artifact_drift"] else 0


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "entry":
        print(json.dumps(entry()))
    elif mode == "final":
        sys.exit(final())
    else:
        sys.exit("usage: entry|final")
