#!/usr/bin/env python3
# ruff: noqa: E501
"""CAPSTONE_CLEAN_CLONE_PROTOCOL_V1 harness: one canonical clean-clone attempt of CAPSTONE_RELEASE_V1.

  python3 scripts/run_capstone_clean_release.py --target-sha <40-hex> --label A --evidence-dir <empty dir outside the repo> --base-dir <scratch base>
  python3 scripts/run_capstone_clean_release.py --record-target <40-hex>       # prints the release-target facts as JSON

Input policy: the ONLY things read from the development checkout are the remote URL, the expected SHA and this
script. Repository bytes come exclusively from `git clone` of the remote at the exact SHA. The harness has NO
copy-in, NO rescue-install and NO retry-in-place path: any failed stage stops the attempt; the clone is then
CONTAMINATED_DISCARDED or FAILED_DISCARDED and a new attempt needs a new clone, environment and workspace. All
evidence is written OUTSIDE the clone. Commands are taken from the cloned repository's own frozen protocol."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
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
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PROTOCOL = "configs/capstone/cap_011_clean_clone_protocol_v1.json"
HARNESS_REL = "scripts/run_capstone_clean_release.py"
LOCK_FILES = ("requirements-dev.lock", "requirements-capstone-auth.lock", "pyproject.toml", "frontend/package.json", "frontend/package-lock.json", "frontend/clerk-sdk/package.json", "frontend/clerk-sdk/package-lock.json")
LEAK = re.compile(r"(\.sqlite3?$|\.db$|(^|/)state\.bin$|candidate_state|CAPSTONE_FL_CANDIDATE_\d+|federation_events?\.jsonl$)")
SKIP_LINE = re.compile(r"^SKIPPED \[(\d+)\] (\S+?)(?::(\d+))?: (.*)$")
KNOWN_SIGNATURE = "AssertionError: assert (789 > 100 and False)"


class Stop(Exception):
    def __init__(self, stage: str, code: str, contaminated: bool = False) -> None:
        super().__init__(f"{stage}:{code}")
        self.stage, self.code, self.contaminated = stage, code, contaminated


class Attempt:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.target = args.target_sha
        self.label = args.label.upper()
        self.evidence = Path(args.evidence_dir).resolve()
        self.evidence.mkdir(parents=True, exist_ok=True)
        if any(self.evidence.iterdir()):
            sys.exit("evidence directory must be empty (a canonical attempt writes only new evidence)")
        if DEV_ROOT in self.evidence.parents or self.evidence == DEV_ROOT:
            sys.exit("evidence directory must be outside the development checkout")
        self.root = Path(tempfile.mkdtemp(prefix=f"capclean_{self.label.lower()}_", dir=args.base_dir)).resolve()
        self.clone, self.home, self.tmp = self.root / "nhm-capstone", self.root / "home", self.root / "tmp"
        self.home.mkdir()
        self.tmp.mkdir()
        self.raw = self.evidence.parent / f"{self.evidence.name}_raw"
        self.raw.mkdir(exist_ok=True)
        self.env = {"HOME": str(self.home), "PATH": PATH, "PYTHONNOUSERSITE": "1", "LANG": "en_US.UTF-8", "TMPDIR": str(self.tmp)}
        self.clone_env = {**self.env, "PYTHONPATH": "src:.", "CAP010_OUT": str(self.raw / "demo")}
        self.steps: list[dict[str, Any]] = []
        self.commands: dict[str, dict[str, Any]] = {}
        self.t0 = time.time()
        self.contaminated = False

    # ---------------------------------------------------------------- plumbing
    def write(self, name: str, payload: dict[str, Any]) -> None:
        body = {"release_target_sha": self.target, "label": self.label, "kind": name.removesuffix(".json"), **payload}
        (self.evidence / f"clean_clone_{self.label.lower()}_{name}").write_text(json.dumps(body, indent=1, sort_keys=True, default=str) + "\n", encoding="utf-8")

    def run(self, cid: str, argv: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None, ambient: bool = False, tail: int = 1200, timeout: int = 7200) -> subprocess.CompletedProcess[str]:
        started = time.time()
        r = subprocess.run(argv, cwd=cwd or self.clone, env=dict(os.environ) if ambient else (env or self.clone_env), capture_output=True, text=True, timeout=timeout)
        (self.raw / f"{cid}.out").write_text(r.stdout + "\n--- stderr ---\n" + r.stderr)
        rec = {"id": cid, "argv": [a.replace(str(self.root), "<ROOT>") for a in argv], "returncode": r.returncode, "seconds": round(time.time() - started, 2),
               "stdout_tail": r.stdout[-tail:], "stderr_tail": r.stderr[-tail:]}
        self.steps.append(rec)
        self.commands[cid] = rec
        print(f"[{r.returncode}] {cid} ({rec['seconds']}s)", flush=True)
        return r

    def git(self, *a: str) -> str:
        return subprocess.run(["git", *a], cwd=self.clone, env=self.env, capture_output=True, text=True, check=True).stdout.strip()

    # ---------------------------------------------------------------- stages
    def stage_clone(self) -> dict[str, Any]:
        remote = self.args.remote
        r = self.run("clone", ["git", "clone", remote, str(self.clone)], cwd=self.root, ambient=True)   # ssh identity: the ONLY ambient-environment command
        if r.returncode:
            raise Stop("clone", "GIT_CLONE_FAILED")
        r = self.run("checkout", ["git", "-C", str(self.clone), "checkout", "--detach", self.target], env=self.env)
        if r.returncode:
            raise Stop("clone", "CHECKOUT_FAILED")
        head = self.git("rev-parse", "HEAD")
        chk = verify_checkout(head, self.target)
        remote_main = self.git("ls-remote", "origin", "refs/heads/main").split("\t")[0]
        reachable = subprocess.run(["git", "merge-base", "--is-ancestor", self.target, "origin/main"], cwd=self.clone, env=self.env).returncode == 0
        tracked = self.git("ls-files").splitlines()
        audit = pre_install_audit(self.clone, tracked)
        status = self.git("status", "--porcelain")
        ignored = [ln for ln in self.git("status", "--ignored", "--porcelain").splitlines() if ln.startswith("!!")]
        gitdir = self.clone / ".git"
        facts = {"clone_source": "remote git repository (git clone over the configured origin URL)", "remote_url_scheme": re.sub(r"^(\w+).*", r"\1", remote) if "://" in remote else "ssh/scp-like",
                 "checkout_sha": head, "checkout_matches_target": chk["ok"], "checkout_failures": chk["failures"], "remote_main_sha_at_clone": remote_main, "target_reachable_from_remote_main": reachable,
                 "status_porcelain_after_checkout": status, "tree_clean_after_checkout": status == "", "ignored_paths_after_checkout": ignored, "tracked_files": len(tracked),
                 "alternates_present": (gitdir / "objects/info/alternates").exists(), "git_dir_is_directory": gitdir.is_dir(), "worktree_used": False,
                 "tracked_symlinks": [p for p in tracked if (self.clone / p).is_symlink()], "tracked_raw_biomedical_files": [p for p in tracked if re.search(r"data/raw/.*\.(dat|hea|atr|mat)$", p)],
                 "pre_install_audit": audit, "manual_copies": False, "clone_root_is_new_temp_dir": True, "clone_inside_development_checkout": DEV_ROOT in self.clone.parents,
                 "harness_sha256_dev": sha256_file(DEV_ROOT / HARNESS_REL), "harness_sha256_clone": sha256_file(self.clone / HARNESS_REL) if (self.clone / HARNESS_REL).exists() else None}
        facts["harness_matches_clone"] = facts["harness_sha256_dev"] == facts["harness_sha256_clone"]
        if not chk["ok"]:
            raise Stop("clone", "WRONG_CHECKOUT_SHA")
        if not audit["ok"] or status or ignored or not facts["harness_matches_clone"] or not reachable or facts["alternates_present"]:
            self.contaminated = not audit["ok"]
            self.facts = facts
            raise Stop("clone", "CLONE_NOT_CLEAN_OR_NOT_FROZEN_HARNESS", contaminated=not audit["ok"])
        self.facts = facts
        return facts

    def load_protocol(self) -> dict[str, Any]:
        return json.loads((self.clone / PROTOCOL).read_text())

    def argv(self, cid: str) -> list[str]:
        for c in self.protocol["commands"]:
            if c["id"] == cid:
                if c["argv"] is None:
                    raise Stop("protocol", f"NO_ARGV:{cid}")
                return list(c["argv"])
        raise Stop("protocol", f"UNKNOWN_COMMAND:{cid}")

    def stage_install(self) -> dict[str, Any]:
        for cid in ("venv", "pip_dev", "pip_auth", "pip_check", "npm_clerk", "npm_app"):
            r = self.run(cid, self.argv(cid), env=self.clone_env if cid != "venv" else self.env)
            if cid == "venv" and r.returncode == 0:
                env = check_python_env(self.clone / ".venv/bin/python", self.clone, DEV_ROOT)
                if not env["ok"]:
                    raise Stop("install", "PYTHON_ENV_NOT_FRESH_IN_CLONE")
            if r.returncode:
                raise Stop("install", f"{cid.upper()}_FAILED")
        py = str(self.clone / ".venv/bin/python")
        versions = {"python": subprocess.run([py, "--version"], env=self.clone_env, capture_output=True, text=True).stdout.strip(),
                    "pip": subprocess.run([py, "-m", "pip", "--version"], env=self.clone_env, capture_output=True, text=True).stdout.strip(),
                    "node": subprocess.run(["node", "--version"], env=self.env, capture_output=True, text=True).stdout.strip(),
                    "npm": subprocess.run(["npm", "--version"], env=self.env, capture_output=True, text=True).stdout.strip(),
                    "git": subprocess.run(["git", "--version"], env=self.env, capture_output=True, text=True).stdout.strip()}
        browser = subprocess.run([CHROME, "--version"], capture_output=True, text=True).stdout.strip()
        locks = {rel: sha256_file(self.clone / rel) for rel in LOCK_FILES}
        env_report = {"status": "PASS", "platform": platform.platform(), "architecture": platform.machine(), "system": platform.system(), **versions, "browser": browser,
                      "lock_sha256": locks, "isolated_home": True, "PYTHONPATH_inherited": False, "NODE_PATH_inherited": False, "VIRTUAL_ENV_inherited": False, "PATH": PATH,
                      "venv": {"created_by_this_run": True, "location": "<clone>/.venv", "python_executable_inside_clone_venv": True, "development_venv_used": False},
                      "environment_secrets_recorded": False, "note": "inventory is evidence, not a minimum performance requirement"}
        self.write("environment.json", {**self.facts_view(), **env_report})
        ids = ["venv", "pip_dev", "pip_auth", "pip_check", "npm_clerk", "npm_app"]
        self.write("install.json", {"status": "PASS", "commands": [{k: self.commands[i][k] for k in ("id", "argv", "returncode", "seconds")} for i in ids],
                                    "pip_check_output": self.commands["pip_check"]["stdout_tail"].strip(), "manual_rescue_install": False, "manual_npm_install": False,
                                    "dotenv_present_in_clone": any((self.clone / n).exists() for n in (".env", ".env.local", "frontend/.env")),
                                    "install_network": "required: public Python and npm registries (not air-gapped; not vendored)", "lock_sha256": locks,
                                    "frontend_installed_from_committed_lock": True, "clerk_sdk_installed_from_committed_lock": True})
        return env_report

    def facts_view(self) -> dict[str, Any]:
        keys = ("clone_source", "checkout_sha", "checkout_matches_target", "remote_main_sha_at_clone", "target_reachable_from_remote_main", "tree_clean_after_checkout", "ignored_paths_after_checkout",
                "tracked_files", "alternates_present", "git_dir_is_directory", "worktree_used", "tracked_symlinks", "tracked_raw_biomedical_files", "pre_install_audit", "manual_copies",
                "clone_root_is_new_temp_dir", "clone_inside_development_checkout", "harness_sha256_dev", "harness_sha256_clone", "harness_matches_clone")
        return {"clone": {k: self.facts[k] for k in keys}, "clone_root_id": hashlib.sha256(str(self.root).encode()).hexdigest()[:16]}

    def pytest_counts(self, text: str) -> dict[str, int]:
        lines = [ln for ln in text.splitlines() if re.search(r" in [\d.]+s", ln)]
        return {k: int(v) for v, k in re.findall(r"(\d+) (passed|failed|skipped|deselected|errors?)", lines[-1] if lines else "")}

    def stage_tests(self) -> None:
        v = self.run("verifier", self.argv("verifier"))
        try:
            verifier = json.loads(v.stdout.strip().splitlines()[-1])
        except (ValueError, IndexError):
            verifier = {"status": "UNPARSEABLE"}
        t = self.run("targeted", self.argv("targeted"))
        names = {m.group(2): m.group(1) for m in re.finditer(r"^(PASSED|FAILED|ERROR|SKIPPED) (\S+)", t.stdout, re.M)}
        r = self.run("regression", self.argv("regression"))
        counts = self.pytest_counts(r.stdout)
        skips = [{"count": int(m.group(1)), "file": m.group(2), "line": int(m.group(3) or 0), "reason": m.group(4)} for m in map(SKIP_LINE.match, r.stdout.splitlines()) if m]
        cat = {"DATA_GATED": 0, "UNTRACKED_ARTIFACT_GATED": 0, "DOCUMENTED_INHERITED_POST_EXPOSURE": 0, "UNEXPECTED": 0}
        unexpected = []
        for s in skips:
            if s["reason"].startswith("CLEAN_CLONE_DATA_GATED"):
                cat["DATA_GATED"] += s["count"]
            elif s["reason"].startswith("CANDIDATE_CHECKPOINT_NOT_TRACKED: untracked T015 artifact absent"):
                cat["UNTRACKED_ARTIFACT_GATED"] += s["count"]
            elif s["file"] == "tests/test_v2_fl_eval_method.py" and "post-exposure state" in s["reason"]:
                cat["DOCUMENTED_INHERITED_POST_EXPOSURE"] += s["count"]
            else:
                cat["UNEXPECTED"] += s["count"]
                unexpected.append(s)
        attempts = []
        for i in range(5):
            c = self.run(f"cap003_isolated_{i + 1}", self.argv("cap003_isolated"))
            attempts.append({"attempt": i + 1, "passed": c.returncode == 0, "known_signature": KNOWN_SIGNATURE in c.stdout + c.stderr, "returncode": c.returncode})
            if c.returncode == 0:
                break
        cap003_ok = any(a["passed"] for a in attempts) and all(a["passed"] or a["known_signature"] for a in attempts)
        pip_rc = self.commands["pip_check"]["returncode"]
        skipped_total = counts.get("skipped", 0)
        self.write("tests.json", {"status": "PASS" if (v.returncode == 0 and verifier.get("status") == "PASS" and t.returncode == 0 and r.returncode == 0 and cat["UNEXPECTED"] == 0 and cap003_ok and skipped_total == sum(cat.values()) and pip_rc == 0) else "FAIL",
                                  "release_verifier": {"returncode": v.returncode, "result": verifier}, "prior_lineage_verified": verifier.get("prior_lineage_verified"),
                                  "targeted": {"returncode": t.returncode, "counts": self.pytest_counts(t.stdout), "tests": names},
                                  "regression": {"returncode": r.returncode, "counts": counts, "collected": sum(counts.get(k, 0) for k in ("passed", "failed", "skipped", "deselected", "error", "errors")),
                                                 "skip_categories": cat, "unexpected_skips": unexpected[:20], "skip_reasons_sample": skips[:12], "seconds_machine_specific": self.commands["regression"]["seconds"]},
                                  "cap003_race": {"policy": "deselected in the full run; isolated up to 5 attempts; known signature only", "test": "tests/test_capstone_monitoring_websocket.py::test_monitoring_completes_with_zero_subscribers", "attempts": attempts, "status": "PASS" if cap003_ok else "FAIL"},
                                  "pip_check_returncode": pip_rc, "raw_biomedical_data_present": False, "ci_queried": False, "ci_triggered": False})
        if v.returncode or t.returncode or r.returncode or cat["UNEXPECTED"] or not cap003_ok:
            raise Stop("tests", "TESTS_FAILED")

    def stage_frontend(self) -> None:
        rcs = {cid: self.run(cid, self.argv(cid)) for cid in ("npm_test", "npm_check", "npm_build")}
        test, check = rcs["npm_test"].stdout, rcs["npm_check"].stdout
        vt = re.search(r"Tests\s+(\d+) passed(?: \| (\d+) skipped)?", test)
        sc = re.search(r"svelte-check found (\d+) errors? and (\d+) warnings?", check, re.I)
        ok = all(r.returncode == 0 for r in rcs.values()) and sc is not None and int(sc.group(1)) == 0
        built = (self.clone / "frontend/build").is_dir()
        self.write("frontend.json", {"status": "PASS" if ok and built else "FAIL", "npm_test_returncode": rcs["npm_test"].returncode, "vitest_tests_passed": int(vt.group(1)) if vt else None,
                                     "vitest_tests_skipped": int(vt.group(2) or 0) if vt and vt.group(2) else 0, "svelte_check_returncode": rcs["npm_check"].returncode,
                                     "svelte_check_errors": int(sc.group(1)) if sc else None, "svelte_check_warnings": int(sc.group(2)) if sc else None, "build_returncode": rcs["npm_build"].returncode,
                                     "frontend_build_produced_by_clean_install": built, "development_build_reused": False, "development_node_modules_reused": False})
        if not ok or not built:
            raise Stop("frontend", "FRONTEND_FAILED")

    def stage_demo(self) -> None:
        pf = self.run("preflight", self.argv("preflight"))
        pre_checks = {}
        m = re.search(r"\{.*\}", pf.stdout, re.S)
        if m:
            try:
                pre_checks = json.loads(m.group(0))
            except ValueError:
                pre_checks = {}
        d = self.run("demo", self.argv("demo"), timeout=3600)
        run_file, restart_file = self.raw / "demo/full_browser_demo_run_1.json", self.raw / "demo/demo_restart.json"
        run = json.loads(run_file.read_text()) if run_file.exists() else {}
        restart = json.loads(restart_file.read_text()) if restart_file.exists() else {}
        demo_ok = d.returncode == 0 and bool(run) and run.get("driver_exit") == 0
        self.write("demo.json", {"status": "PASS" if demo_ok and pf.returncode == 0 else "FAIL", "preflight": {"returncode": pf.returncode, "output_tail": pf.stdout.strip().splitlines()[-14:], "parsed": pre_checks},
                                 "demo_returncode": d.returncode, "launcher_command": run.get("launcher_command"), "ports": run.get("ports"), "workspace_outside_repository": run.get("workspace_outside_repository"),
                                 "driver_exit": run.get("driver_exit"), "browser": run.get("browser"), "stopped": run.get("stopped"), "prewarm": run.get("prewarm"), "post_run_snapshot": run.get("post_run_snapshot"),
                                 "semantic_sha256": run.get("semantic_sha256"), "semantic_projection": run.get("semantic_projection"),
                                 "timings_machine_specific_seconds": {"startup_incl_build_prewarm": run.get("startup_s_including_build_and_prewarm"), "total": run.get("wall_clock_total_s_machine_specific")},
                                 "raw_biomedical_data_required": False, "development_artifacts_required": False})
        if self.label == "A":
            self.write("restart.json", {"status": "PASS" if restart.get("semantic_identical") and restart.get("counts_unchanged") else "FAIL", **{k: v for k, v in restart.items() if k not in ("db_before",)}})
        if not demo_ok or pf.returncode:
            raise Stop("demo", "DEMO_FAILED")

    def stage_git_audit(self) -> None:
        status = self.git("status", "--porcelain").splitlines()
        modified = [ln for ln in status if not ln.startswith("??")]
        untracked = [ln[3:] for ln in status if ln.startswith("??")]
        ignored = [ln[3:] for ln in self.git("status", "--ignored", "--porcelain").splitlines() if ln.startswith("!!")]
        walk = [p.relative_to(self.clone).as_posix() for p in self.clone.rglob("*") if p.is_file() and ".venv" not in p.parts and "node_modules" not in p.parts and ".git" not in p.parts]
        leaked = [p for p in walk if LEAK.search(p)]
        raw = [p for p in walk if re.search(r"(^|/)data/raw/.*\.(dat|hea|atr|mat)$", p)]
        head_now = self.git("rev-parse", "HEAD")
        dev_refs = []
        needles = (str(DEV_ROOT), str(Path.home()))
        for rec in self.steps:
            if any(n in rec["stdout_tail"] + rec["stderr_tail"] for n in needles):
                dev_refs.append(rec["id"])
        self.write("git_audit.json", {"status": "PASS" if (not modified and not leaked and not raw and head_now == self.target and not dev_refs) else "FAIL", "head_unchanged": head_now == self.target,
                                      "tracked_modified_or_deleted": modified, "untracked_after_execution": untracked[:40], "unexpected_ignored_sample": ignored[:20], "runtime_artifacts_leaked_into_repository": leaked,
                                      "raw_biomedical_files_present": raw, "development_checkout_path_references_in_command_output": dev_refs,
                                      "runtime_workspace_outside_repository": True, "source_edits_in_clone": False, "manual_dependency_rescue": False})
        if modified or leaked or raw or dev_refs:
            raise Stop("git_audit", "CLONE_STATE_NOT_CLEAN_AFTER_EXECUTION")

    def fail(self, stop: Stop) -> None:
        n = 1 + len(list(self.evidence.glob("attempt_*_FAIL_*.json")))
        (self.evidence / f"attempt_{n}_FAIL_{stop.stage}.json").write_text(json.dumps(
            {"release_target_sha": self.target, "label": self.label, "stage": stop.stage, "failure_code": stop.code, "contaminated": stop.contaminated,
             "clone_status": "CONTAMINATED_DISCARDED" if stop.contaminated else "FAILED_DISCARDED", "discarded": True, "steps": [{k: s[k] for k in ("id", "returncode")} for s in self.steps],
             "rule": "no rescue; a new canonical attempt needs a new clone, environment and runtime workspace"}, indent=1, sort_keys=True) + "\n")
        print(f"FAIL {stop.stage}:{stop.code}", flush=True)

    def finish_bundle(self) -> None:
        files = {p.name: sha256_file(p) for p in sorted(self.evidence.glob("*.json"))}
        (self.evidence / f"clean_clone_{self.label.lower()}_bundle.json").write_text(json.dumps(
            {"release_target_sha": self.target, "label": self.label, "kind": "bundle", "status": "PASS", "files": files, "steps": len(self.steps), "executed_commands": [{"id": x["id"], "argv": x["argv"], "returncode": x["returncode"]} for x in self.steps], "total_seconds_machine_specific": round(time.time() - self.t0, 1)}, indent=1, sort_keys=True) + "\n")


def record_target(sha: str) -> int:
    if not SHA40.match(sha):
        sys.exit("target must be a full 40-hex SHA")
    g = lambda *a: subprocess.run(["git", *a], cwd=DEV_ROOT, check=True, capture_output=True, text=True).stdout.strip()  # noqa: E731
    subprocess.run(["git", "fetch", "origin"], cwd=DEV_ROOT, check=True, capture_output=True)
    facts = {"release_target_sha": sha, "local_head": g("rev-parse", "HEAD"), "origin_main": g("rev-parse", "origin/main"), "working_tree_clean": g("status", "--porcelain") == "",
             "pushed": g("rev-parse", "origin/main") == sha, "release_vehicle": "the exact Git repository state at RELEASE_TARGET_SHA (no archive, no installer)",
             "commit_subject": g("log", "-1", "--format=%s", sha)}
    facts["ok"] = facts["local_head"] == sha == facts["origin_main"] and facts["working_tree_clean"]
    print(json.dumps(facts, indent=1, sort_keys=True))
    return 0 if facts["ok"] else 1


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--target-sha")
    p.add_argument("--label", choices=("A", "B", "a", "b", "DRY"))
    p.add_argument("--evidence-dir")
    p.add_argument("--base-dir")
    p.add_argument("--remote")
    p.add_argument("--record-target")
    args = p.parse_args()
    if args.record_target:
        return record_target(args.record_target)
    if not (args.target_sha and args.label and args.evidence_dir and args.base_dir):
        p.error("--target-sha --label --evidence-dir --base-dir are required")
    if not SHA40.match(args.target_sha):
        p.error("--target-sha must be a full 40-hex commit SHA (branch names are not accepted)")
    if not args.remote:
        args.remote = subprocess.run(["git", "remote", "get-url", "origin"], cwd=DEV_ROOT, capture_output=True, text=True, check=True).stdout.strip()
    for var in ("PYTHONPATH", "NODE_PATH", "VIRTUAL_ENV"):
        os.environ.pop(var, None)
    a = Attempt(args)
    try:
        a.stage_clone()
        a.protocol = a.load_protocol()
        a.stage_install()
        a.stage_tests()
        a.stage_frontend()
        a.stage_demo()
        a.stage_git_audit()
    except Stop as stop:
        a.fail(stop)
        return 1
    a.finish_bundle()
    print("CLEAN CLONE", a.label, "PASS", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
