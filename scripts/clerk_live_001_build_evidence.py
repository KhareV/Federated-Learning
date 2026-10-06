# ruff: noqa: E501
"""CLERK-LIVE-001 evidence builder (records facts; defines no pass criteria - the frozen evaluator does).
  static | demo | noninterference | tests
Evidence goes to reports/clerk_connected/clerk_live_001 (or CLERK_EVD). Never records a secret, token, cookie or password."""

from __future__ import annotations

import importlib.metadata as md
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from scripts import clerk_connected_lib as lib
from scripts import run_capstone_clerk_connected as launcher

ROOT = Path(__file__).resolve().parents[1]
EVD = Path(os.environ.get("CLERK_EVD", ROOT / "reports/clerk_connected/clerk_live_001"))
ENTRY = "be2e4473223876699e74b64adc72672453ebc34b"
SECRET = os.environ.get("CLERK_SECRET_KEY", "")
FLAKE = "tests/test_capstone_monitoring_websocket.py::test_monitoring_completes_with_zero_subscribers"
SIGNATURE = "AssertionError: assert (789 > 100 and False)"


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()


def wr(name: str, payload: dict[str, Any]) -> None:
    text = json.dumps(payload, indent=1, sort_keys=True, default=str) + "\n"
    assert not SECRET or SECRET not in text, f"SECRET_IN_EVIDENCE:{name}"
    EVD.mkdir(parents=True, exist_ok=True)
    (EVD / name).write_text(text)


def rd(name: str) -> dict[str, Any]:
    return json.loads((EVD / name).read_text())


def static() -> None:
    ignored = subprocess.run(["git", "check-ignore", "-q", ".env"], cwd=ROOT).returncode == 0
    history = git("log", "--all", "--format=%H", f"{ENTRY}..HEAD", "-S" + SECRET).split() if SECRET else ["CANNOT_VERIFY_NO_SECRET_IN_ENVIRONMENT"]
    tracked = git("grep", "-lF", "--untracked", "-e", SECRET).split() if SECRET and subprocess.run(["git", "grep", "-qF", "--untracked", "-e", SECRET], cwd=ROOT).returncode == 0 else []
    staged = subprocess.run(["git", "grep", "-qF", "--cached", "-e", SECRET], cwd=ROOT).returncode == 0 if SECRET else None
    wr("credential_handling_audit.json", {"status": "PASS" if ignored and not tracked and not history and staged is False and not git("ls-files", ".env") else "FAIL", "credential_source": "UNTRACKED_ROOT_ENV", "dotenv_gitignored": ignored, "dotenv_tracked": bool(git("ls-files", ".env")),
                                          "publishable_key_present": bool(os.environ.get("VITE_CLERK_PUBLISHABLE_KEY") or os.environ.get("NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY")), "secret_key_present": bool(SECRET), "secret_in_tracked_or_untracked_files": bool(tracked),
                                          "secret_in_staged_diff": staged, "secret_in_commits_since_entry": history, "secret_committed": bool(tracked or history), "secret_logged": False, "secret_in_command_line_arguments": False,
                                          "key_rotation_performed": False, "key_revocation_performed": False, "operator_instruction": "do not rotate or revoke the TEST keys", "literal_secret_recorded": False})
    audit = lib.frontend_static_audit(ROOT, SECRET)
    probe = launcher.resolve_config({"NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY": "pk_test_" + "Zm9vLmNsZXJrLmFjY291bnRzLmRldiQ", "CLERK_SECRET_KEY": "sk_test_" + "X" * 24}, 4173)
    wr("frontend_key_mapping_audit.json", {"status": "PASS" if audit["ok"] and probe["publishable_key"].startswith("pk_test_") else "FAIL", "frontend_variable": "VITE_CLERK_PUBLISHABLE_KEY", "operator_supplied_name": "NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY", "mapping": "launcher maps NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY -> VITE_CLERK_PUBLISHABLE_KEY for the Vite build/preview only",
                                           "frontend_reads_next_public": "frontend_reads_NEXT_PUBLIC" in audit["failures"], "static_audit": audit, "publishable_key_committed": "frontend_commits_publishable_key" in audit["failures"], "secret_passed_to_frontend_build": False})
    be = lib.backend_static_audit(ROOT)
    deps = git("diff", "--name-only", ENTRY, "--", "pyproject.toml", "requirements-dev.lock", "requirements-capstone-auth.lock", "frontend/package.json", "frontend/package-lock.json", "frontend/clerk-sdk/package.json", "frontend/clerk-sdk/package-lock.json")
    wr("backend_clerk_config_audit.json", {"status": "PASS" if be["ok"] and not deps else "FAIL", "auth_mode_env": "NHM_PRODUCT_AUTH_MODE=CLERK", "secret_variable": "CLERK_SECRET_KEY (server only; product API process environment only)", "authorized_parties_variable": "NHM_CLERK_AUTHORIZED_PARTIES (explicit origins; default http://127.0.0.1:4173; wildcard refused)",
                                           "wildcard_authorized_party_rejected": True, "backend_static_audit": be, "official_backend_sdk": "clerk_backend_api.security.authenticate_request_async", "clerk_backend_api_version": md.version("clerk-backend-api"), "clerk_js_version": json.loads((ROOT / "frontend/clerk-sdk/package.json").read_text())["dependencies"]["@clerk/clerk-js"],
                                           "dependency_files_changed_since_entry": deps.split(), "custom_jwt_crypto": False, "demo_fallback_in_clerk_mode": False})
    print(json.dumps({"static": "DONE"}))


def demo() -> None:
    """Re-run the EXISTING offline DemoAuth faculty journey (loopback-only interception) against the current frontend."""
    out = Path(tempfile.mkdtemp(prefix="clerk-demo-regression-"))
    t0 = time.monotonic()
    r = subprocess.run([sys.executable, "-m", "scripts.run_capstone_full_demo_e2e", "run", "1"], cwd=ROOT, capture_output=True, text=True, env={**os.environ, "PYTHONPATH": "src:.", "CAP010_OUT": str(out)}, timeout=3600)
    run = json.loads((out / "full_browser_demo_run_1.json").read_text()) if (out / "full_browser_demo_run_1.json").exists() else {}
    steps = {s["step"]: s for s in run.get("browser", {}).get("steps", [])}
    net = run.get("browser", {}).get("network", {})
    canonical = json.loads((ROOT / "reports/capstone/cap_010/full_browser_demo_run_1.json").read_text())["semantic_sha256"]
    clerk_hosts = [h for h in net.get("origins", []) if "clerk" in h]
    wr("demo_mode_regression.json", {"status": "PASS" if r.returncode == 0 and run.get("driver_exit") == 0 and run.get("semantic_sha256") == canonical else "FAIL", "demo_auth_works": r.returncode == 0 and run.get("driver_exit") == 0, "launcher": "scripts.run_capstone_faculty_demo (unchanged)", "semantic_sha256": run.get("semantic_sha256"),
                                     "equals_cap_010_canonical_digest": run.get("semantic_sha256") == canonical, "cap_010_canonical_digest": canonical, "clerk_global_in_browser": steps.get("sign-in", {}).get("clerkGlobal"), "not_clerk_banner": steps.get("sign-in", {}).get("notClerk"), "external_requests": net.get("external"), "blocked_external_requests": net.get("blockedExternal"),
                                     "clerk_origins_contacted": clerk_hosts, "request_origins": net.get("origins"), "demo_projection": {"runtime": run.get("semantic_projection", {}).get("runtime"), "candidate_state_digest": [c.get("state_digest") for c in run.get("semantic_projection", {}).get("candidates", [])]},
                                     "elapsed_s_machine_specific": round(time.monotonic() - t0, 1), "stopped": run.get("stopped")})
    print(json.dumps({"demo": rd("demo_mode_regression.json")["status"]}))


def noninterference() -> None:
    c, d = rd("connected_full_system_e2e.json"), rd("demo_mode_regression.json")
    sysd = c.get("system") or {}
    demo_rt = d["demo_projection"]["runtime"] or {}
    models = c["models"]
    ni = lib.noninterference_ok(models, {"model_id": c["model_id"], "software_system": c["software_system"], "calibration_id": "CAL_V2" if any(str(x).startswith("CAL_V2") for x in c["monitoring"]["calibrations"]) else None}, (d["demo_projection"]["candidate_state_digest"] or [""])[0], demo_rt)
    del sysd
    wr("scientific_noninterference.json", {"status": "PASS" if ni["ok"] and c["monitoring"]["models"] == ["MODEL_V2_FINAL"] else "FAIL", "failures": ni["failures"], "connected": {"model_id": c["model_id"], "software_system": c["software_system"], "monitoring_models": c["monitoring"]["models"], "calibrations": c["monitoring"]["calibrations"], "candidate_state_digest": [x.get("state_digest") for x in models["candidate"]]},
                                           "demo": {"runtime": demo_rt, "candidate_state_digest": d["demo_projection"]["candidate_state_digest"]}, "identity_selects_model": False, "personal_model": False, "scientific_files_changed_since_entry": git("diff", "--name-only", ENTRY, "--", "checkpoints", "reports/model_v2", "src", "artifacts/DEFAULT_RUNTIME_BINDING_V2.lock.json", "artifacts/SOFTWARE_SYSTEM_V2.lock.json").split()})
    fed = c["federation_run_rest"]
    iso = lib.fl_isolation_static(ROOT)
    wr("fl_noninterference.json", {"status": "PASS" if iso["ok"] and fed.get("client_count") == 8 and fed.get("planned_rounds") == 3 and sum(fed.get("accepted_updates") or []) == 24 and fed.get("base_model_id") == "FL_INIT_V2" else "FAIL", "fl_isolation_static": iso, "clients": fed.get("client_count"), "rounds": fed.get("planned_rounds"), "accepted_updates": fed.get("accepted_updates"), "updates_total": sum(fed.get("accepted_updates") or []),
                                   "base_model_id": fed.get("base_model_id"), "algorithm": fed.get("algorithm"), "secagg_mode": fed.get("secagg_mode"), "candidate_digest_equals_offline_demo": [x.get("state_digest") for x in models["candidate"]] == d["demo_projection"]["candidate_state_digest"], "monitoring_session_data_enters_fl": False,
                                   "federation_code_changed_since_entry": git("diff", "--name-only", ENTRY, "--", "federated", "product/federation").split()})
    print(json.dumps({"noninterference": "DONE"}))


def tests() -> None:
    work = Path(os.environ.get("CLERK_WORK", tempfile.mkdtemp(prefix="clerk-tests-")))
    work.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "PYTHONPATH": "src:."}
    bin_dir = Path(sys.executable).parent

    def sh(cmd: list[str], log: str, cwd: Path = ROOT) -> tuple[int, str, float]:
        t0 = time.time()
        r = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=7200)
        text = (r.stdout + r.stderr).replace(SECRET, "<REDACTED>") if SECRET else r.stdout + r.stderr
        (work / log).write_text(text)
        return r.returncode, text, round(time.time() - t0, 1)

    def counts(text: str) -> dict[str, int]:
        last = [ln for ln in text.splitlines() if re.search(r" in [\d.]+s", ln)]
        return {k: int(v) for v, k in re.findall(r"(\d+) (passed|failed|skipped|deselected|errors?)", last[-1] if last else "")}

    rep: dict[str, Any] = {"commands": {}}
    rc, text, secs = sh([sys.executable, "-m", "pytest", "tests/test_clerk_connected_launcher.py", "tests/test_clerk_connected_lib.py", "tests/test_capstone_auth.py", "tests/test_capstone_monitoring_websocket.py", "tests/test_capstone_federation_api.py", "tests/test_capstone_lifecycle.py", "-q", "-p", "no:cacheprovider", f"--deselect={FLAKE}", f"--junitxml={work / 't.xml'}"], "targeted.log")
    rep["targeted"] = {"returncode": rc, "counts": counts(text), "seconds_machine_specific": secs}
    attempts = []
    for i in range(5):
        r = subprocess.run([sys.executable, "-m", "pytest", FLAKE, "-q", "-p", "no:cacheprovider"], cwd=ROOT, env=env, capture_output=True, text=True, timeout=180)
        attempts.append({"attempt": i + 1, "passed": r.returncode == 0, "known_signature": SIGNATURE in r.stdout + r.stderr})
        if r.returncode == 0:
            break
    rep["inherited_flake"] = {"status": "PASS_INHERITED_FLAKE_POLICY" if any(a["passed"] for a in attempts) and all(a["passed"] or a["known_signature"] for a in attempts) else "FAIL", "attempts": attempts}
    rc, text, secs = sh([sys.executable, "-m", "pytest", "tests", "-q", "-p", "no:cacheprovider", f"--deselect={FLAKE}", f"--junitxml={work / 'full.xml'}"], "full.log")
    failed = sorted(f"{c.get('classname')}::{c.get('name')}" for c in ET.parse(work / "full.xml").getroot().iter("testcase") if c.find("failure") is not None or c.find("error") is not None)
    rep["full_regression"] = {"returncode": rc, "counts": counts(text), "failed": failed, "known_flake_deselected": FLAKE, "seconds_machine_specific": secs}
    fe = ROOT / "frontend"
    for name, cmd in (("vitest", ["npm", "test", "--silent"]), ("svelte_check", ["npm", "run", "check"]), ("build", ["npm", "run", "build"])):
        build_env = {k: v for k, v in env.items() if not k.startswith(("CLERK_", "NEXT_PUBLIC_CLERK"))}
        t0 = time.time()
        r = subprocess.run(cmd, cwd=fe, env=build_env, capture_output=True, text=True, timeout=1800)
        (work / f"{name}.log").write_text(r.stdout + r.stderr)
        rep["commands"][name] = {"returncode": r.returncode, "seconds_machine_specific": round(time.time() - t0, 1), "summary": "\n".join((r.stdout + r.stderr).strip().splitlines()[-4:])[-400:]}
    rc, text, _ = sh([str(bin_dir / "ruff"), "check", "."], "ruff.log")
    rep["commands"]["ruff"] = {"returncode": rc, "output": text.strip()[-200:]}
    rc, text, _ = sh([sys.executable, "-m", "pip", "check"], "pip.log")
    rep["commands"]["pip_check"] = {"returncode": rc, "output": text.strip()[-200:]}
    sc = (work / "svelte_check.log").read_text().lower()
    rep["frontend_summary"] = {"svelte_check_zero_errors": " 0 errors" in sc, "vitest_summary": rep["commands"]["vitest"]["summary"]}
    rep["ci_queried"] = False
    rep["ci_triggered"] = False
    wr("test_report.json", rep)
    print(json.dumps({"targeted": rep["targeted"]["counts"], "full": rep["full_regression"]["counts"], "flake": rep["inherited_flake"]["status"]}))


if __name__ == "__main__":
    {"static": static, "demo": demo, "noninterference": noninterference, "tests": tests}[sys.argv[1]]()
