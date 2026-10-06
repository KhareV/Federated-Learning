#!/usr/bin/env python3
# ruff: noqa: E501
"""FINAL-EVAL-REPAIR-002 clean-clone verification of the frozen UFL_LITE_ACCEPTANCE_TARGET_SHA.
  Proof A (clean clone): brand-new `git clone` at the exact SHA, fresh Python 3.11 venv, fresh `npm ci`, clean tree, frozen verifiers + targeted tests.
  Proof B (connected): the frozen FINAL-EVAL-REPAIR-002 real-Clerk E2E run INSIDE that clone with a fresh Chrome profile and fresh Clerk sessions.
Credentials are supplied only as external FILE PATHS; nothing else is copied in. There is no rescue path: any failed stage stops the attempt.
  python3 scripts/final_eval_repair_002_clean_clone.py --target-sha <40-hex> --evidence-dir <empty dir outside the repo> --base-dir <scratch> --env-file <outside git> --users-file <outside git>"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

from scripts.capstone_release_lib import (
    SHA40,
    check_python_env,
    pre_install_audit,
    sha256_file,
    verify_checkout,
)
from scripts.run_capstone_clerk_connected_clean_clone import DEV_ROOT, SECRET_VAR, Attempt, Stop

HARNESS_REL = "scripts/final_eval_repair_clean_clone.py"


class FerAttempt(Attempt):
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
        lock_present = (self.clone / "artifacts/final_eval_repair/FINAL_EVAL_REPAIR_002_PROTOCOL_V1.lock.json").exists()
        if not audit["ok"] or status or not reachable or not harness_ok or not lock_present:
            raise Stop("clone", "CLONE_NOT_CLEAN_OR_NOT_FROZEN_HARNESS", contaminated=not audit["ok"])
        venv_fresh = False
        for cid, argv in (("venv", ["python3.11", "-m", "venv", ".venv"]), ("pip_dev", [".venv/bin/python", "-m", "pip", "install", "-r", "requirements-dev.lock"]), ("pip_auth", [".venv/bin/python", "-m", "pip", "install", "-r", "requirements-capstone-auth.lock"]),
                          ("pip_check", [".venv/bin/python", "-m", "pip", "check"]), ("npm_clerk", ["npm", "ci", "--prefix", "frontend/clerk-sdk"]), ("npm_app", ["npm", "ci", "--prefix", "frontend"])):
            if self.run(cid, argv, env=self.env if cid == "venv" else self.clone_env).returncode:
                raise Stop("install", f"{cid.upper()}_FAILED")
            if cid == "venv":
                venv_fresh = check_python_env(self.clone / ".venv/bin/python", self.clone, DEV_ROOT)["ok"]
                if not venv_fresh:
                    raise Stop("install", "PYTHON_ENV_NOT_FRESH_IN_CLONE")
        v1 = self.run("verifier_clerk", [".venv/bin/python", "-m", "scripts.verify_clerk_connected"])
        v2 = self.run("verifier_ui16", [".venv/bin/python", "-m", "scripts.verify_capstone_ui_v1_6"])
        t = self.run("targeted", [".venv/bin/python", "-m", "pytest", "tests/test_final_eval_repair_002_presentation.py", "tests/test_final_eval_repair_presentation.py", "tests/test_ufl_lite_003_machinery.py", "tests/test_ufl_lite_presentation.py", "-q", "-p", "no:cacheprovider"])
        proof_a_ok = not (v1.returncode or v2.returncode or t.returncode)
        proof_a = {"status": "PASS" if proof_a_ok else "FAIL", "checkout_sha": head, "checkout_matches_target": chk["ok"], "pre_install_audit_ok": audit["ok"], "tree_clean_after_checkout": status == "", "target_reachable_from_remote_main": reachable, "tracked_files": len(tracked), "harness_matches_clone": harness_ok,
                   "fresh_venv_created_by_run": venv_fresh, "npm_installs": ["frontend/clerk-sdk", "frontend"], "frozen_verifiers": {"verify_clerk_connected": v1.returncode == 0, "verify_capstone_ui_v1_6": v2.returncode == 0}, "targeted_tests_returncode": t.returncode}
        if not proof_a_ok:
            self.write("clean_clone.json", {"status": "FAIL", "proof_a_clean_clone": proof_a})
            raise Stop("verify", "VERIFIERS_OR_TARGETED_TESTS_FAILED")
        e = self.run("e2e", [".venv/bin/python", "-m", "scripts.final_eval_repair_002_e2e", "--env-file", self.a.env_file, "--users-file", self.a.users_file, "--out", str(self.evidence), "--raw", str(self.raw / "e2e_raw"), "--label", "CLEAN_CLONE"], timeout=5400)
        post = self.git("status", "--porcelain").splitlines()
        modified = [ln for ln in post if not ln.startswith("??")]
        secret_in_clone = [str(p.relative_to(self.clone)) for p in self.clone.rglob("*") if p.is_file() and ".venv" not in p.parts and "node_modules" not in p.parts and ".git" not in p.parts and self.secret and self.secret.encode() in p.read_bytes()] if self.secret else []
        crawl = json.loads((self.evidence / "route_crawl_final.json").read_text()) if (self.evidence / "route_crawl_final.json").exists() else {}
        owner = json.loads((self.evidence / "connected_owner_binding_regression.json").read_text()) if (self.evidence / "connected_owner_binding_regression.json").exists() else {}
        sec = json.loads((self.evidence / "secret_audit.json").read_text()) if (self.evidence / "secret_audit.json").exists() else {}
        pv = self.run("presentation_verifier", [".venv/bin/python", "-m", "scripts.final_eval_repair_presentation"])
        pv2 = self.run("provenance_verifier", [".venv/bin/python", "-m", "scripts.final_eval_repair_002_provenance"])
        have_browser = (self.evidence / "landing_browser_audit.json").exists() and (self.evidence / "product_browser_audit.json").exists()
        proof_b_ok = e.returncode == 0 and pv.returncode == 0 and pv2.returncode == 0 and have_browser and crawl.get("analysis", {}).get("all_pass") is True and owner.get("all_pass") is True and sec.get("clean") is True and not secret_in_clone
        ok = proof_b_ok and not modified
        self.write("clean_clone.json", {"status": "PASS" if ok else "FAIL", "target_sha": self.target, "clone_source": "remote git repository (git clone at the exact SHA)", "proof_a_clean_clone": proof_a, "proof_b_browser_in_clone": {"status": "PASS" if proof_b_ok else "FAIL", "e2e_returncode": e.returncode, "crawl_all_pass": crawl.get("analysis", {}).get("all_pass"), "browser_audits_present": have_browser, "provenance_verifier_returncode": pv2.returncode, "owner_binding_all_pass": owner.get("all_pass"), "secrets_clean": sec.get("clean"), "presentation_verifier_returncode": pv.returncode, "real_clerk_session": True, "fresh_browser_profile": True},
                                         "commands": [{k: s[k] for k in ("id", "returncode", "seconds")} for s in self.steps], "developer_env_or_db_or_cookie_copied": False, "credentials_supplied_as": "external file paths outside the repository", "secret_in_clone_tree": bool(secret_in_clone),
                                         "tracked_modified_after_execution": modified, "manual_steps": "none", "network": "installation and Clerk authentication require Internet access"})
        if not ok:
            raise Stop("e2e", "CONNECTED_E2E_OR_CLONE_AUDIT_FAILED")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for n in ("--target-sha", "--evidence-dir", "--base-dir", "--remote", "--env-file", "--users-file"):
        p.add_argument(n)
    a = p.parse_args()
    if not (a.target_sha and a.evidence_dir and a.base_dir and a.env_file and a.users_file) or not SHA40.match(a.target_sha):
        p.error("--target-sha (40-hex) --evidence-dir --base-dir --env-file --users-file are required")
    a.remote = a.remote or subprocess.run(["git", "remote", "get-url", "origin"], cwd=DEV_ROOT, capture_output=True, text=True, check=True).stdout.strip()
    for var in ("PYTHONPATH", "NODE_PATH", "VIRTUAL_ENV", SECRET_VAR, "VITE_CLERK_PUBLISHABLE_KEY", "NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY"):
        os.environ.pop(var, None)
    att = FerAttempt(a)
    try:
        att.stages()
    except Stop as stop:
        att.fail(stop)
        return 1
    print("FINAL-EVAL-REPAIR-002 CLEAN CLONE PASS", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
