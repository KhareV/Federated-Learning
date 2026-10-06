#!/usr/bin/env python3
# ruff: noqa: E501
"""CLERK-LIVE-001 clean CONNECTED clone: a brand-new `git clone` of the remote at the exact connected target SHA, a fresh Python 3.11 venv,
fresh `npm ci` installs, a FRESH Chrome profile and a fresh real Clerk session. Only the publishable key, the secret key and the temporary
test-user credentials are supplied (as external FILE PATHS); nothing else is copied in (no source, env file, cookies, browser profile, DB, build).
  python3 scripts/run_capstone_clerk_connected_clean_clone.py --target-sha <40-hex> --evidence-dir <empty dir outside the repo> --base-dir <scratch> --env-file <outside git> --users-file <outside git>
  python3 scripts/run_capstone_clerk_connected_clean_clone.py --record-target <40-hex>
There is no copy-in or rescue path: any failed stage stops the attempt (evidence attempt_N_FAIL_*.json)."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from scripts.capstone_release_lib import (
    SHA40,
    check_python_env,
    pre_install_audit,
    sha256_file,
    verify_checkout,
)

DEV_ROOT = Path(__file__).resolve().parents[1]
PATH = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
HARNESS_REL = "scripts/run_capstone_clerk_connected_clean_clone.py"
SECRET_VAR = "CLERK_SECRET_KEY"


class Stop(Exception):
    def __init__(self, stage: str, code: str, contaminated: bool = False) -> None:
        super().__init__(f"{stage}:{code}")
        self.stage, self.code, self.contaminated = stage, code, contaminated


def read_secret(path: Path) -> str:
    for line in path.read_text().splitlines():
        if line.startswith(SECRET_VAR + "="):
            return line.partition("=")[2].strip().strip('"').strip("'")
    return ""


class Attempt:
    def __init__(self, a: argparse.Namespace) -> None:
        self.a, self.target = a, a.target_sha
        self.evidence = Path(a.evidence_dir).resolve()
        self.evidence.mkdir(parents=True, exist_ok=True)
        if any(self.evidence.iterdir()):
            sys.exit("evidence directory must be empty")
        if DEV_ROOT in self.evidence.parents or self.evidence == DEV_ROOT:
            sys.exit("evidence directory must be outside the development checkout")
        for f in (a.env_file, a.users_file):
            if DEV_ROOT in Path(f).resolve().parents:
                sys.exit("credential files must live outside the repository")
        self.root = Path(tempfile.mkdtemp(prefix="clerkclean_", dir=a.base_dir)).resolve()
        self.clone, self.home, self.tmp = self.root / "nhm-capstone", self.root / "home", self.root / "tmp"
        self.home.mkdir()
        self.tmp.mkdir()
        self.raw = self.evidence.parent / f"{self.evidence.name}_raw"
        self.raw.mkdir(exist_ok=True)
        self.env = {"HOME": str(self.home), "PATH": PATH, "PYTHONNOUSERSITE": "1", "LANG": "en_US.UTF-8", "TMPDIR": str(self.tmp)}
        self.clone_env = {**self.env, "PYTHONPATH": "src:."}
        self.steps: list[dict[str, Any]] = []
        self.secret = read_secret(Path(a.env_file))

    def run(self, cid: str, argv: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None, ambient: bool = False, timeout: int = 7200) -> subprocess.CompletedProcess[str]:
        t0 = time.time()
        r = subprocess.run(argv, cwd=cwd or self.clone, env=dict(os.environ) if ambient else (env or self.clone_env), capture_output=True, text=True, timeout=timeout)
        out = (r.stdout + "\n--- stderr ---\n" + r.stderr)
        if self.secret:
            out = out.replace(self.secret, "<REDACTED>")
        (self.raw / f"{cid}.out").write_text(out)
        rec = {"id": cid, "argv": [x.replace(str(self.root), "<ROOT>") for x in argv], "returncode": r.returncode, "seconds": round(time.time() - t0, 1)}
        self.steps.append(rec)
        print(f"[{r.returncode}] {cid} ({rec['seconds']}s)", flush=True)
        return r

    def git(self, *x: str) -> str:
        return subprocess.run(["git", *x], cwd=self.clone, env=self.env, capture_output=True, text=True, check=True).stdout.strip()

    def write(self, name: str, payload: dict[str, Any]) -> None:
        text = json.dumps({"release_target_sha": self.target, **payload}, indent=1, sort_keys=True, default=str) + "\n"
        assert not self.secret or self.secret not in text, "SECRET_IN_EVIDENCE"
        (self.evidence / name).write_text(text)

    def stages(self) -> None:
        if self.run("clone", ["git", "clone", self.a.remote, str(self.clone)], cwd=self.root, ambient=True).returncode:
            raise Stop("clone", "GIT_CLONE_FAILED")
        if self.run("checkout", ["git", "-C", str(self.clone), "checkout", "--detach", self.target], env=self.env).returncode:
            raise Stop("clone", "CHECKOUT_FAILED")
        head = self.git("rev-parse", "HEAD")
        chk = verify_checkout(head, self.target)
        if not chk["ok"]:
            raise Stop("clone", "WRONG_CHECKOUT_SHA")
        tracked = self.git("ls-files").splitlines()
        audit = pre_install_audit(self.clone, tracked)
        status = self.git("status", "--porcelain")
        reachable = subprocess.run(["git", "merge-base", "--is-ancestor", self.target, "origin/main"], cwd=self.clone, env=self.env).returncode == 0
        harness_ok = (self.clone / HARNESS_REL).exists() and sha256_file(DEV_ROOT / HARNESS_REL) == sha256_file(self.clone / HARNESS_REL)
        self.facts = {"checkout_sha": head, "checkout_matches_target": chk["ok"], "pre_install_audit": audit, "tree_clean_after_checkout": status == "", "target_reachable_from_remote_main": reachable, "tracked_files": len(tracked), "harness_matches_clone": harness_ok, "clone_inside_development_checkout": DEV_ROOT in self.clone.parents}
        if not audit["ok"] or status or not reachable or not harness_ok:
            raise Stop("clone", "CLONE_NOT_CLEAN_OR_NOT_FROZEN_HARNESS", contaminated=not audit["ok"])
        for cid, argv in (("venv", ["python3.11", "-m", "venv", ".venv"]), ("pip_dev", [".venv/bin/python", "-m", "pip", "install", "-r", "requirements-dev.lock"]), ("pip_auth", [".venv/bin/python", "-m", "pip", "install", "-r", "requirements-capstone-auth.lock"]),
                          ("pip_check", [".venv/bin/python", "-m", "pip", "check"]), ("npm_clerk", ["npm", "ci", "--prefix", "frontend/clerk-sdk"]), ("npm_app", ["npm", "ci", "--prefix", "frontend"])):
            if self.run(cid, argv, env=self.env if cid == "venv" else self.clone_env).returncode:
                raise Stop("install", f"{cid.upper()}_FAILED")
            if cid == "venv" and not check_python_env(self.clone / ".venv/bin/python", self.clone, DEV_ROOT)["ok"]:
                raise Stop("install", "PYTHON_ENV_NOT_FRESH_IN_CLONE")
        v = self.run("verifier", [".venv/bin/python", "-m", "scripts.verify_clerk_connected"])
        t = self.run("targeted", [".venv/bin/python", "-m", "pytest", "tests/test_clerk_connected_launcher.py", "tests/test_clerk_connected_lib.py", "-q", "-p", "no:cacheprovider"])
        if v.returncode or t.returncode:
            raise Stop("verify", "VERIFIER_OR_TARGETED_TESTS_FAILED")
        e2e_dir = self.evidence / "clean_connected_clone_e2e"
        e = self.run("e2e", [".venv/bin/python", "-m", "scripts.run_capstone_clerk_connected_e2e", "--env-file", self.a.env_file, "--users-file", self.a.users_file, "--out", str(e2e_dir), "--raw", str(self.raw / "e2e_raw")], timeout=5400)
        post = self.git("status", "--porcelain").splitlines()
        modified = [ln for ln in post if not ln.startswith("??")]
        secret_in_clone = [str(p.relative_to(self.clone)) for p in self.clone.rglob("*") if p.is_file() and ".venv" not in p.parts and "node_modules" not in p.parts and ".git" not in p.parts and self.secret and self.secret.encode() in p.read_bytes()] if self.secret else []
        statuses = {p.name: json.loads(p.read_text()).get("status") for p in sorted(e2e_dir.glob("*.json")) if p.name != "_raw_digest.json"} if e2e_dir.exists() else {}
        ok = e.returncode == 0 and statuses and all(s == "PASS" for s in statuses.values()) and not modified and not secret_in_clone
        self.write("clean_connected_clone.json", {"status": "PASS" if ok else "FAIL", "label": "CLONE", "clone_source": "remote git repository (git clone at the exact SHA)", **self.facts, "commands": [{k: s[k] for k in ("id", "returncode", "seconds")} for s in self.steps],
                                                  "python_venv_created_by_run": True, "development_venv_used": False, "npm_installs": ["frontend/clerk-sdk", "frontend"], "fresh_browser_profile": True, "browser_profile_note": "the E2E creates a new temporary Chrome profile for every browser run and deletes it",
                                                  "developer_browser_session_copied": False, "developer_clerk_cookie_copied": False, "developer_db_copied": False, "developer_env_copied": False, "credentials_supplied_externally": True, "credentials_supplied_as": "external file paths outside the repository (publishable key, secret key, test-user credentials)",
                                                  "secret_in_clone_tree": bool(secret_in_clone), "tracked_modified_after_execution": modified, "e2e_evidence_statuses": statuses, "e2e_returncode": e.returncode, "real_clerk_session": True, "manual_steps": "none",
                                                  "network": "installation and Clerk authentication require Internet access"})
        if not ok:
            raise Stop("e2e", "CONNECTED_E2E_OR_CLONE_AUDIT_FAILED")

    def fail(self, stop: Stop) -> None:
        n = 1 + len(list(self.evidence.glob("attempt_*_FAIL_*.json")))
        (self.evidence / f"attempt_{n}_FAIL_{stop.stage}.json").write_text(json.dumps({"release_target_sha": self.target, "stage": stop.stage, "failure_code": stop.code, "contaminated": stop.contaminated, "clone_status": "CONTAMINATED_DISCARDED" if stop.contaminated else "FAILED_DISCARDED", "discarded": True,
                                                                                         "steps": [{k: s[k] for k in ("id", "returncode")} for s in self.steps]}, indent=1, sort_keys=True) + "\n")
        print(f"FAIL {stop.stage}:{stop.code}", flush=True)


def record_target(sha: str) -> int:
    if not SHA40.match(sha):
        sys.exit("target must be a full 40-hex SHA")
    g = lambda *x: subprocess.run(["git", *x], cwd=DEV_ROOT, check=True, capture_output=True, text=True).stdout.strip()  # noqa: E731
    subprocess.run(["git", "fetch", "origin"], cwd=DEV_ROOT, check=True, capture_output=True)
    facts = {"connected_target_sha": sha, "local_head": g("rev-parse", "HEAD"), "origin_main": g("rev-parse", "origin/main"), "working_tree_clean": g("status", "--porcelain") == "", "pushed": g("rev-parse", "origin/main") == sha,
             "release_vehicle": "the exact Git repository state at connected_target_sha (no archive)", "commit_subject": g("log", "-1", "--format=%s", sha)}
    facts["ok"] = facts["local_head"] == sha == facts["origin_main"] and facts["working_tree_clean"]
    print(json.dumps(facts, indent=1, sort_keys=True))
    return 0 if facts["ok"] else 1


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for n in ("--target-sha", "--evidence-dir", "--base-dir", "--remote", "--env-file", "--users-file", "--record-target"):
        p.add_argument(n)
    a = p.parse_args()
    if a.record_target:
        return record_target(a.record_target)
    if not (a.target_sha and a.evidence_dir and a.base_dir and a.env_file and a.users_file):
        p.error("--target-sha --evidence-dir --base-dir --env-file --users-file are required")
    if not SHA40.match(a.target_sha):
        p.error("--target-sha must be a full 40-hex commit SHA")
    a.remote = a.remote or subprocess.run(["git", "remote", "get-url", "origin"], cwd=DEV_ROOT, capture_output=True, text=True, check=True).stdout.strip()
    for var in ("PYTHONPATH", "NODE_PATH", "VIRTUAL_ENV", SECRET_VAR, "VITE_CLERK_PUBLISHABLE_KEY", "NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY"):
        os.environ.pop(var, None)
    att = Attempt(a)
    try:
        att.stages()
    except Stop as stop:
        att.fail(stop)
        return 1
    print("CLEAN CONNECTED CLONE PASS", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
