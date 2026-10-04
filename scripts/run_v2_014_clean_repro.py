#!/usr/bin/env python3
"""V2-014 canonical clean-clone reproducibility orchestrator (MODEL_V2_COMPLETE_REPRO_PROTOCOL_V1).

Creates a BRAND-NEW `git clone` of the configured remote in a newly created temporary root,
checks out the exact target commit, builds a fresh Python 3.11 venv and `npm ci` environment
strictly from the committed locks under an isolated HOME (PYTHONPATH/NODE_PATH unset, no inherited
virtualenv), runs the in-clone checks (scripts/v2_014_clone_checks.py) and writes ALL evidence to an
EXTERNAL directory. It never copies a file into the clone, never rescue-installs a dependency and
never edits the clone: any failure aborts the clone as a failed proof (a successor commit and a NEW
clone are required).

  python3 scripts/run_v2_014_clean_repro.py --target-sha <sha> --evidence-dir <external dir>
         --base-dir <scratch base> --label clone1 --mode full
  --mode final : second, final-commit verification clone (lighter scope, protocol section 48)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

PATH = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
ENTRY = "3d0e9d4a81a486c5aa05d3073e2fabcbd51f445b"
IGNORED_ALLOWED = (".venv/", "frontend/node_modules/", "frontend/build/", "frontend/.svelte-kit/",
                   ".pytest_cache/", ".ruff_cache/", "src/nhm_research.egg-info/")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Harness:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.evidence = Path(args.evidence_dir)
        self.evidence.mkdir(parents=True, exist_ok=True)
        if any(self.evidence.iterdir()):
            sys.exit("evidence directory must be empty (new canonical run)")
        self.root = Path(tempfile.mkdtemp(prefix=f"v2014_{args.label}_", dir=args.base_dir))
        self.clone = self.root / "clone"
        self.home = self.root / "home"
        self.tmp = self.root / "tmp"
        self.home.mkdir()
        self.tmp.mkdir()
        self.steps: list[dict[str, Any]] = []
        self.env = {"HOME": str(self.home), "PATH": PATH, "PYTHONNOUSERSITE": "1",
                    "LANG": "en_US.UTF-8", "TMPDIR": str(self.tmp)}
        self.raw = self.evidence.parent / f"{self.evidence.name}_raw"
        self.failed = False

    # ------------------------------------------------------------------ plumbing
    def run(self, name: str, cmd: list[str], cwd: Path | None = None, *, isolated: bool = True,
            tail: int = 1500, stdin_none: bool = True) -> subprocess.CompletedProcess:
        started = time.time()
        env = self.env if isolated else dict(os.environ)
        result = subprocess.run(cmd, cwd=cwd or self.clone, env=env, capture_output=True,
                                text=True)
        record = {"step": name, "command": " ".join(cmd), "cwd": str(cwd or self.clone).replace(
            str(self.root), "<ROOT>"), "exit_code": result.returncode,
            "seconds": round(time.time() - started, 2),
            "stdout_tail": result.stdout[-tail:], "stderr_tail": result.stderr[-tail:]}
        self.steps.append(record)
        with (self.evidence / "steps.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
        print(f"[{record['exit_code']}] {name} ({record['seconds']}s)", flush=True)
        if result.returncode != 0:
            self.failed = True
        return result

    def py(self, name: str, *args: str, out: str | None = None) -> subprocess.CompletedProcess:
        cmd = [str(self.clone / ".venv/bin/python"), *args]
        return self.run(name, cmd)

    def check(self, check: str, *extra: str, name: str | None = None) -> bool:
        filename = name or check
        out = self.evidence / f"{filename}.json"
        result = self.py(f"check:{filename}", "-m", "scripts.v2_014_clone_checks", check,
                         "--out", str(out), *extra)
        return result.returncode == 0 and out.exists()

    def load(self, name: str) -> dict[str, Any]:
        return json.loads((self.evidence / f"{name}.json").read_text())

    def write(self, name: str, data: Any) -> None:
        (self.evidence / name).write_text(json.dumps(data, indent=2, sort_keys=True) + "\n",
                                          encoding="utf-8")

    # ------------------------------------------------------------------ stages
    def clone_and_audit(self) -> None:
        remote = self.args.remote
        # git needs the user's SSH identity to reach the remote: this ONE operation uses the
        # ambient environment; every later command runs under the isolated HOME.
        self.run("git clone (fresh, from remote)", ["git", "clone", remote, str(self.clone)],
                 cwd=self.root, isolated=False)
        if self.failed:
            return
        self.run("git checkout target", ["git", "checkout", "--detach", self.args.target_sha])
        head = self.git("rev-parse", "HEAD").strip()
        status = self.git("status", "--porcelain").strip()
        remote_url = self.git("remote", "get-url", "origin").strip()
        gitdir = self.clone / ".git"
        alternates = (gitdir / "objects/info/alternates").exists()
        tracked = self.git("ls-files").splitlines()
        symlinks = [p for p in tracked if (self.clone / p).is_symlink()]
        raw = [p for p in tracked if re.search(r"data/raw/.*\.(dat|hea|atr|mat|csv)$", p)]
        audit = {
            "label": self.args.label, "remote": remote_url, "target_sha": self.args.target_sha,
            "checkout_sha": head, "checkout_matches_target": head == self.args.target_sha,
            "git_dir_is_directory_not_worktree_file": gitdir.is_dir(),
            "objects_alternates_present": alternates, "fresh_clone_is_not_worktree": gitdir.is_dir()
            and not alternates,
            "status_porcelain_after_checkout": status, "tree_clean": status == "",
            "git_log_1": self.git("log", "-1", "--format=%H %an %ad %s").strip(),
            "tracked_files": len(tracked), "tracked_symlinks": symlinks,
            "tracked_raw_biomedical_files": raw,
            "clone_root_is_new_temp_dir": True, "worktree_used": False,
            "developer_files_copied": False, "raw_datasets_copied": False,
            "isolated_home": True, "PYTHONPATH_set": "PYTHONPATH" in self.env,
            "NODE_PATH_set": "NODE_PATH" in self.env,
            "VIRTUAL_ENV_set": "VIRTUAL_ENV" in self.env, "PATH": PATH,
            "data_dirs_present_after_clone": sorted(
                p.name for p in (self.clone / "data").iterdir()) if (
                    self.clone / "data").exists() else []}
        audit["status"] = "PASS" if (audit["checkout_matches_target"] and audit["tree_clean"]
                                     and audit["fresh_clone_is_not_worktree"] and not symlinks
                                     and not raw) else "FAIL"
        self.write("clone_audit.json", audit)
        if audit["status"] != "PASS":
            self.failed = True

    def git(self, *args: str) -> str:
        return subprocess.run(["git", *args], cwd=self.clone, env=self.env, capture_output=True,
                              text=True, check=True).stdout

    def environment(self) -> None:
        py = self.args.python
        info = {
            "platform": platform.platform(), "architecture": platform.machine(),
            "host_python_for_venv": subprocess.run([py, "--version"], env=self.env,
                                                   capture_output=True, text=True).stdout.strip(),
            "PATH": PATH, "HOME": "<isolated temp HOME>", "PYTHONPATH": None, "NODE_PATH": None,
            "PYTHONNOUSERSITE": "1"}
        for name, cmd in (("node", ["node", "--version"]), ("npm", ["npm", "--version"])):
            info[name] = subprocess.run(cmd, env=self.env, capture_output=True,
                                        text=True).stdout.strip()
        self.write("environment_audit.json", info)
        self.run("python venv (fresh)", [py, "-m", "venv", ".venv"])
        self.run("pip install -r requirements-dev.lock",
                 [".venv/bin/python", "-m", "pip", "install", "-r", "requirements-dev.lock"],
                 tail=800)
        self.run("pip install --no-deps -e .",
                 [".venv/bin/python", "-m", "pip", "install", "--no-deps", "-e", "."], tail=400)
        check = self.run("pip check", [".venv/bin/python", "-m", "pip", "check"])
        freeze = self.run("pip freeze", [".venv/bin/python", "-m", "pip", "freeze"], tail=100)
        version = self.run("python/pip versions", [".venv/bin/python", "-m", "pip", "--version"])
        pyv = self.run("python version", [".venv/bin/python", "--version"])
        (self.evidence / "pip_freeze.txt").write_text(freeze.stdout, encoding="utf-8")
        deps = {
            "python": pyv.stdout.strip() or pyv.stderr.strip(), "pip": version.stdout.strip(),
            "requirements_dev_lock_sha256": sha256(self.clone / "requirements-dev.lock"),
            "pyproject_sha256": sha256(self.clone / "pyproject.toml"),
            "package_lock_sha256": sha256(self.clone / "frontend/package-lock.json"),
            "package_json_sha256": sha256(self.clone / "frontend/package.json"),
            "pip_check_exit": check.returncode, "pip_check_output": check.stdout.strip(),
            "pip_freeze_sha256": hashlib.sha256(freeze.stdout.encode()).hexdigest(),
            "pip_freeze_lines": len(freeze.stdout.splitlines()),
            "manual_rescue_install": False,
            "note": "resolved package list is evidence only; it does not replace the committed "
            "locks", "venv_location": "<clone>/.venv (created by this run)"}
        deps["status"] = "PASS" if check.returncode == 0 and "No broken" in check.stdout else "FAIL"
        self.write("dependency_audit_python.json", deps)

    def frontend(self) -> None:
        fe = self.clone / "frontend"
        ci = self.run("npm ci", ["npm", "ci"], cwd=fe, tail=600)
        ls = self.run("npm ls --depth=0", ["npm", "ls", "--depth=0"], cwd=fe, tail=3000)
        test = self.run("npm test", ["npm", "test"], cwd=fe, tail=2500)
        check = self.run("npm run check", ["npm", "run", "check"], cwd=fe, tail=1200)
        build = self.run("npm run build", ["npm", "run", "build"], cwd=fe, tail=800)
        tests = re.search(r"Tests\s+(\d+) passed(?: \| (\d+) skipped)?", test.stdout)
        files = re.search(r"Test Files\s+(\d+) passed", test.stdout)
        errors = re.search(r"svelte-check found (\d+) errors and (\d+) warnings", check.stdout)
        types_node = fe / "node_modules/@types/node/package.json"
        parents = [str(p) for p in self.root.parents if (p / "node_modules").exists()]
        report = {
            "node": subprocess.run(["node", "--version"], env=self.env, capture_output=True,
                                   text=True).stdout.strip(),
            "npm": subprocess.run(["npm", "--version"], env=self.env, capture_output=True,
                                  text=True).stdout.strip(),
            "package_lock_sha256": sha256(fe / "package-lock.json"),
            "npm_ci_exit": ci.returncode, "manual_npm_install": False,
            "npm_ls_top_level": ls.stdout[-3000:], "npm_ls_exit": ls.returncode,
            "vitest_exit": test.returncode,
            "vitest_files_passed": int(files.group(1)) if files else None,
            "vitest_tests_passed": int(tests.group(1)) if tests else None,
            "vitest_tests_skipped": int(tests.group(2) or 0) if tests else None,
            "svelte_check_exit": check.returncode,
            "svelte_check_errors": int(errors.group(1)) if errors else None,
            "svelte_check_warnings": int(errors.group(2)) if errors else None,
            "build_exit": build.returncode,
            "types_node_installed_locally": types_node.exists(),
            "parent_node_modules_ancestors": parents,
            "copied_node_modules": False}
        report["status"] = "PASS" if (
            ci.returncode == 0 and test.returncode == 0 and check.returncode == 0
            and build.returncode == 0 and report["svelte_check_errors"] == 0
            and report["types_node_installed_locally"] and not parents) else "FAIL"
        self.write("frontend_report.json", report)
        if report["status"] != "PASS":
            self.failed = True

    def provenance(self, label: str) -> dict[str, Any]:
        status = self.git("status", "--porcelain").splitlines()
        ignored = [line[3:] for line in self.git("status", "--ignored", "--porcelain").splitlines()
                   if line.startswith("!! ")]
        stray_ignored = [p for p in ignored if not p.startswith(IGNORED_ALLOWED)
                         and "__pycache__" not in p]
        symlinks = [str(p.relative_to(self.clone)) for p in self.clone.rglob("*")
                    if p.is_symlink() and ".venv" not in p.parts and "node_modules" not in p.parts]
        raw_files = [str(p.relative_to(self.clone)) for p in (self.clone / "data").rglob("*")
                     if p.is_file() and p.suffix in {".dat", ".hea", ".atr", ".mat", ".npy"}]
        data = {"stage": label, "git_status_porcelain": status, "untracked_or_modified": status,
                "ignored_generated_paths_sample": ignored[:40],
                "unexpected_ignored_paths": stray_ignored, "symlinks_outside_env_dirs": symlinks,
                "raw_biomedical_or_cache_files_present": raw_files,
                "venv_inside_clone_created_by_this_run": True}
        data["status"] = "PASS" if (not status and not stray_ignored and not symlinks
                                    and not raw_files) else "FAIL"
        return data

    # ------------------------------------------------------------------ full scope
    def scope_full(self) -> None:
        self.frontend()  # npm ci first: the V2-013 replay builds and serves the frontend
        self.write("provenance_pre_checks.json", self.provenance("after_install_before_checks"))
        self.check("inventory")
        self.check("artifacts")
        for label in ("p1", "p2"):
            self.check("model-v2", name=f"model_v2_{label}")
        self.compare_fresh("model_v2_p1", "model_v2_p2",
                           ("fixed_vector_logits", "state_digest_sha256", "checkpoint_sha256"),
                           "model_v2_fresh_process_equivalence")
        self.check("fixed-vectors")
        self.check("cal-v2")
        self.check("gateway")
        for kind in ("v2013", "flatline"):
            target = self.raw / f"replay_{kind}"
            self.py(f"replay run {kind}", "-m", "scripts.run_v2_014_replay", kind, str(target))
            self.check("replay-compare", "--kind", kind, "--dir", str(target),
                       name=f"replay_{kind}")
        for label in ("p1", "p2"):
            self.check("fl-init", name=f"fl_init_{label}")
        self.compare_fresh("fl_init_p1", "fl_init_p2", ("round_0_state_sha256",),
                           "fl_init_fresh_process_equivalence")
        self.check("fl-dev")
        self.check("fl-heldout")
        self.check("secagg-data-free")
        self.check("synthetic-fl", "--dir", str(self.raw / "synthetic_fl"))
        self.check("lifecycle")

    def compare_fresh(self, a: str, b: str, keys: tuple[str, ...], name: str) -> None:
        da, db = self.load(a), self.load(b)
        same = {k: da.get(k) == db.get(k) for k in keys}
        self.write(f"{name}.json", {"keys": same, "run_1": a, "run_2": b,
                                    "status": "PASS" if all(same.values()) else "FAIL"})
        if not all(same.values()):
            self.failed = True

    def scope_final(self) -> None:
        self.frontend()
        self.write("provenance_pre_checks.json", self.provenance("after_install_before_checks"))
        self.check("inventory")
        self.check("artifacts")
        self.py("V2-014 evidence verifier", "-m", "scripts.verify_v2_014_evidence",
                "--out", str(self.evidence / "evidence_verifier.json"))
        self.check("model-v2")
        self.check("fixed-vectors")
        self.check("gateway")
        self.check("fl-init")
        self.check("synthetic-fl", "--dir", str(self.raw / "synthetic_fl"))
        self.check("lifecycle")

    def finish(self) -> int:
        regression_ok = self.check("regression", "--monolithic")
        self.check("lint")
        final_status = self.git("status", "--porcelain").splitlines()
        diff = subprocess.run(["git", "diff", "--exit-code"], cwd=self.clone, env=self.env,
                              capture_output=True, text=True)
        cached = subprocess.run(["git", "diff", "--cached", "--exit-code"], cwd=self.clone,
                                env=self.env, capture_output=True, text=True)
        ignored = [line[3:] for line in self.git("status", "--ignored", "--porcelain").splitlines()
                   if line.startswith("!! ")]
        untracked = [line[3:] for line in final_status if line.startswith("?? ")]
        modified = [line for line in final_status if not line.startswith("?? ")]
        generated_ok = all(p.startswith("reports/model_v2/v2_fl_eval_001/verification/")
                           for p in untracked)
        final = {"tracked_modified": modified, "git_diff_exit": diff.returncode,
                 "git_diff_cached_exit": cached.returncode,
                 "untracked_generated_by_documented_commands": untracked,
                 "untracked_all_documented_generated": generated_ok,
                 "ignored_generated_paths_sample": ignored[:40],
                 "source_edits_in_clone": False, "manual_dependency_rescue": False,
                 "status": "PASS" if (not modified and diff.returncode == 0
                                      and cached.returncode == 0 and generated_ok) else "FAIL"}
        self.write("clone_final_status.json", final)
        if final["status"] != "PASS":
            self.failed = True
        del regression_ok
        return self.write_manifests()

    def write_manifests(self) -> int:
        def maybe(name: str) -> dict[str, Any]:
            path = self.evidence / f"{name}.json"
            return json.loads(path.read_text()) if path.exists() else {}

        statuses = {p.stem: json.loads(p.read_text()).get("status") for p in sorted(
            self.evidence.glob("*.json")) if p.name not in ("steps.jsonl",)
                    and isinstance(json.loads(p.read_text()), dict)}
        failed = {k: v for k, v in statuses.items() if v not in ("PASS", None)}
        deps = maybe("dependency_audit_python")
        fe = maybe("frontend_report")
        inv, art = maybe("inventory"), maybe("artifacts")
        synth, gw = maybe("synthetic_fl"), maybe("gateway")
        reg, init = maybe("regression"), maybe("fl_init_p1") or maybe("fl_init")
        env = maybe("environment_audit")
        steps_failed = [s["step"] for s in self.steps if s["exit_code"] != 0]
        manifest = {
            "phase_id": "V2-014", "gate": "V2G13", "label": self.args.label,
            "mode": self.args.mode, "entry_sha": ENTRY, "clone_target_sha": self.args.target_sha,
            "clone_identifier": hashlib.sha256(str(self.root).encode()).hexdigest()[:16],
            "platform": env.get("platform"), "architecture": env.get("architecture"),
            "python": deps.get("python"), "pip": deps.get("pip"), "node": fe.get("node"),
            "npm": fe.get("npm"),
            "requirements_lock_sha256": deps.get("requirements_dev_lock_sha256"),
            "package_lock_sha256": fe.get("package_lock_sha256"),
            "component_lock_inventory_sha256": inv.get("component_lock_inventory_sha256"),
            "checkpoint_inventory_sha256": art.get("checkpoint_inventory_sha256"),
            "prediction_table_inventory_sha256": art.get("prediction_table_inventory_sha256"),
            "gateway_canonical_sha256": gw.get("canonical_sha256"),
            "FL_INIT_V2_sha256": init.get("round_0_state_sha256"),
            "v2_fl_005_cohort_manifest_sha256": synth.get("cohort_manifest_sha256"),
            "v2_fl_005_final_state_sha256": synth.get("final_state_sha256"),
            "v2_fl_005_replay_digest": synth.get("semantic_digest"),
            "python_test_node_list_sha256": reg.get("node_list_sha256"),
            "python_test_nodes": reg.get("collected_node_count"),
            "python_data_gated_skipped": reg.get("DATA_GATED_SKIPPED"),
            "frontend_tests_passed": fe.get("vitest_tests_passed"),
            "frontend_status": fe.get("status"),
            "CI_queried": False, "CI_triggered": False,
            "real_waveform_datasets_accessed": False, "manual_source_copy": False,
            "manual_data_copy": False, "manual_dependency_rescue": False,
            "check_statuses": statuses, "failed_checks": failed, "failed_steps": steps_failed,
            "result": "PASS" if not failed and not steps_failed and not self.failed else "FAIL"}
        self.write("reproducibility_manifest.json", manifest)
        files = {}
        for path in sorted(self.evidence.rglob("*")):
            if path.is_file() and path.name != "evidence_manifest.json":
                files[str(path.relative_to(self.evidence))] = sha256(path)
        self.write("evidence_manifest.json", {"files": files, "file_count": len(files),
                                              "result": manifest["result"]})
        print(json.dumps({"result": manifest["result"], "failed": failed,
                          "failed_steps": steps_failed}))
        return 0 if manifest["result"] == "PASS" else 1

    def cleanup_note(self) -> None:
        self.write("clone_location.json", {"root_removed_after_run": False,
                                           "note": "clone retained for audit; not reused"})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--target-sha", required=True)
    parser.add_argument("--evidence-dir", required=True)
    parser.add_argument("--base-dir", required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--mode", choices=("full", "final"), default="full")
    parser.add_argument("--remote")
    parser.add_argument("--python", default="python3.11")
    args = parser.parse_args()
    if not args.remote:
        args.remote = subprocess.run(["git", "remote", "get-url", "origin"], capture_output=True,
                                     text=True, check=True).stdout.strip()
    for var in ("PYTHONPATH", "NODE_PATH", "VIRTUAL_ENV"):
        os.environ.pop(var, None)
    harness = Harness(args)
    harness.clone_and_audit()
    if harness.failed:
        sys.exit(harness.write_manifests() or 1)
    harness.environment()
    if harness.failed:
        sys.exit(harness.write_manifests() or 1)
    if args.mode == "full":
        harness.scope_full()
    else:
        harness.scope_final()
    sys.exit(harness.finish())


if __name__ == "__main__":
    if shutil.which("git") is None:
        sys.exit("git required")
    main()
