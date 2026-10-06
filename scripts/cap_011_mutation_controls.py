# ruff: noqa: E501
"""CAP-011 mutation / negative controls (20). Every mutation is applied to a TEMPORARY copy or a synthetic temporary git
repository, must fail a NAMED check of the frozen release layer, and leaves the working tree byte-identical (verified with
git status). Writes reports/capstone/cap_011/mutation_controls.json (or CAP011_OUT)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from scripts.capstone_release_lib import (
    MANIFEST_PATH,
    audit_release_text,
    check_python_env,
    pre_install_audit,
    verify_checkout,
    verify_clone_result,
    verify_final_diff,
    verify_manifest,
)

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(os.environ.get("CAP011_OUT", ROOT / "reports/capstone/cap_011"))
GUIDE = (ROOT / "docs/capstone/CAPSTONE_RELEASE_GUIDE_V1.md").read_text(encoding="utf-8")
MANIFEST = json.loads((ROOT / MANIFEST_PATH).read_text(encoding="utf-8"))
SHA = "a" * 40
OTHER = "b" * 40


def claim(sentence: str) -> tuple[bool, str]:
    result = audit_release_text(GUIDE + "\n\n" + sentence + "\n")
    return (not result["ok"]), "guide_claims"


def manifest_dict(mut) -> tuple[bool, str]:
    m = json.loads(json.dumps(MANIFEST))
    mut(m)
    r = verify_manifest(m, ROOT)
    return (not r["ok"]), ",".join(r["failures"])


def tmp_hash(rel: str) -> tuple[bool, str]:
    """Copy every manifest-bound file to a temp tree, change one, expect the manifest verifier to name it."""
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        for group in ("key_artifacts", "dependency_locks"):
            for p in MANIFEST[group]:
                (root / p).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / p, root / p)
        baseline = verify_manifest(MANIFEST, root)
        if not baseline["ok"]:
            return False, "baseline_not_ok"
        target = root / rel
        target.write_bytes(target.read_bytes() + b"\n ")
        r = verify_manifest(MANIFEST, root)
        return (not r["ok"] and any(rel in f for f in r["failures"])), ",".join(r["failures"])


def repo(files: dict[str, str]) -> Path:
    d = Path(tempfile.mkdtemp(prefix="capmut_"))
    for args in (["init", "-q"], ["config", "user.email", "m@x"], ["config", "user.name", "m"]):
        subprocess.run(["git", *args], cwd=d, check=True, capture_output=True)
    for rel, body in files.items():
        (d / rel).parent.mkdir(parents=True, exist_ok=True)
        (d / rel).write_text(body)
    subprocess.run(["git", "add", "-A"], cwd=d, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "base"], cwd=d, check=True, capture_output=True)
    return d


def contaminated(rel: str, body: str = "x", kind: str = "") -> tuple[bool, str]:
    d = repo({"README.md": "r", "frontend/package.json": "{}", "src/a.py": "x = 1"})
    try:
        p = d / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)
        tracked = subprocess.run(["git", "ls-files"], cwd=d, capture_output=True, text=True).stdout.split()
        r = pre_install_audit(d, tracked)
        return (not r["ok"] and (not kind or any(v["kind"] == kind for v in r["violations"]))), ",".join(sorted({v["kind"] for v in r["violations"]}))
    finally:
        shutil.rmtree(d, ignore_errors=True)


def wrong_python() -> tuple[bool, str]:
    with tempfile.TemporaryDirectory() as d:
        dev = Path(d) / "dev"
        clone = Path(d) / "clone"
        (dev / ".venv/bin").mkdir(parents=True)
        (clone / ".venv/bin").mkdir(parents=True)
        (dev / ".venv/bin/python").write_text("")
        ok_case = check_python_env(clone / ".venv/bin/python", clone, dev)
        bad = check_python_env(dev / ".venv/bin/python", clone, dev)
        return (ok_case["ok"] and not bad["ok"]), ",".join(bad["failures"])


def final_modifies_executable() -> tuple[bool, str]:
    d = repo({"frontend/src/a.svelte": "a", "reports/capstone/cap_011/x.json": "{}"})
    try:
        base = subprocess.run(["git", "rev-parse", "HEAD"], cwd=d, capture_output=True, text=True).stdout.strip()
        (d / "reports/capstone/cap_011/y.json").write_text("{}")
        subprocess.run(["git", "add", "-A"], cwd=d, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "evidence"], cwd=d, check=True, capture_output=True)
        evidence_only = verify_final_diff(d, base, subprocess.run(["git", "rev-parse", "HEAD"], cwd=d, capture_output=True, text=True).stdout.strip())
        (d / "frontend/src/a.svelte").write_text("b")
        subprocess.run(["git", "add", "-A"], cwd=d, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "bad"], cwd=d, check=True, capture_output=True)
        bad = verify_final_diff(d, base, subprocess.run(["git", "rev-parse", "HEAD"], cwd=d, capture_output=True, text=True).stdout.strip())
        return (evidence_only["ok"] and not bad["ok"]), ",".join(bad["disallowed"])
    finally:
        shutil.rmtree(d, ignore_errors=True)


def set_(path: tuple[str, ...], value):
    def apply(m):
        node = m
        for key in path[:-1]:
            node = node[key]
        node[path[-1]] = value
    return apply


MUTATIONS = (
    ("RELEASE_CLAIMS_PHYSICAL_WEARABLE_VALIDATED", lambda: claim("The release includes validated physical wearable integration.")),
    ("RELEASE_CLAIMS_CLINICAL_READINESS", lambda: claim("The release is ready for clinical use and clinical diagnosis.")),
    ("RELEASE_CLAIMS_AIR_GAPPED_INSTALLATION", lambda: claim("The installation is air-gapped and fully vendored.")),
    ("RELEASE_CLAIMS_RAW_DATA_SCIENTIFIC_REPRODUCTION", lambda: claim("The release reproduces the raw-data scientific results from a clean clone.")),
    ("RELEASE_MARKS_CANDIDATE_DEPLOYED", lambda: manifest_dict(set_(("candidate", "production_deployed"), True))),
    ("RELEASE_CHANGES_DEFAULT_MODEL_TO_CANDIDATE", lambda: manifest_dict(set_(("released_monitoring", "default_model"), "CAPSTONE_FL_CANDIDATE_0001"))),
    ("RELEASE_CHANGES_MODEL_V2_FINAL_HASH", lambda: tmp_hash("checkpoints/MODEL_V2_FINAL.pt")),
    ("RELEASE_CHANGES_CAL_V2_HASH", lambda: tmp_hash("artifacts/CAL_V2.json")),
    ("RELEASE_CHANGES_UI_V1_2_LOCK", lambda: tmp_hash("artifacts/capstone/CAPSTONE_UI_V1_2.lock.json")),
    ("RELEASE_CHANGES_RESEARCH_CATALOG_HASH", lambda: tmp_hash("artifacts/capstone/CAPSTONE_RESEARCH_EVIDENCE_CATALOG_V1.lock.json")),
    ("CLEAN_CLONE_CHECKS_OUT_WRONG_SHA", lambda: ((not verify_checkout(OTHER, SHA)["ok"]), ",".join(verify_checkout(OTHER, SHA)["failures"]))),
    ("CLEAN_CLONE_IMPORTS_MANUAL_SOURCE_FILE", lambda: contaminated("src/injected.py", "x = 2", "untracked_file_manual_injection")),
    ("CLEAN_CLONE_REUSES_DEVELOPER_VENV", wrong_python),
    ("CLEAN_CLONE_REUSES_DEVELOPER_NODE_MODULES", lambda: contaminated("frontend/node_modules/x/index.js", "1", "copied_node_modules")),
    ("CLEAN_CLONE_REUSES_DEVELOPER_FRONTEND_BUILD", lambda: contaminated("frontend/build/index.html", "<html>", "copied_frontend_build")),
    ("CLEAN_CLONE_USES_DEVELOPER_DOTENV", lambda: contaminated(".env", "SECRET=1", "developer_dotenv")),
    ("CLEAN_CLONE_IMPORTS_DEVELOPER_SQLITE_OR_CANDIDATE", lambda: (contaminated("state/product.sqlite3", "x", "copied_runtime_state")[0] and contaminated("artifacts/candidates/CAPSTONE_FL_CANDIDATE_0001/state.bin", "x")[0], "copied_runtime_state,copied_candidate_artifact")),
    ("CLEAN_CLONE_COPIES_RAW_BIOMEDICAL_DATA", lambda: contaminated("data/raw/mitdb/1.0.0/100.dat", "x", "copied_raw_data")),
    ("CLEAN_CLONE_RESULT_HAS_WRONG_TARGET_SHA", lambda: ((not verify_clone_result({"release_target_sha": OTHER, "label": "A", "status": "PASS", "kind": "demo"}, SHA)["ok"]) and (not verify_clone_result({"label": "A"}, SHA)["ok"]), "release_target_sha_mismatch")),
    ("FINAL_RESULT_COMMIT_MODIFIES_A_RELEASE_EXECUTABLE", final_modifies_executable),
)


def main() -> int:
    before = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True).stdout
    results = []
    for name, fn in MUTATIONS:
        try:
            caught, failing = fn()
        except Exception as error:   # an exception is not a catch
            caught, failing = False, f"EXCEPTION:{type(error).__name__}"
        after = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True).stdout
        results.append({"mutation": name, "caught": bool(caught), "failing_check": failing[:200], "restored": after == before, "applied_to": "temporary copy / synthetic repository"})
        print(name, caught, failing[:80], flush=True)
    payload = {"controls": results, "all_caught": all(r["caught"] for r in results), "all_restored": all(r["restored"] for r in results), "count": len(results)}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "mutation_controls.json").write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n")
    print(json.dumps({k: payload[k] for k in ("count", "all_caught", "all_restored")}))
    return 0 if payload["all_caught"] and payload["all_restored"] else 1


if __name__ == "__main__":
    sys.exit(main())
