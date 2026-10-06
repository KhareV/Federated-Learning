# ruff: noqa: E501
"""UFL-LITE-002 evidence builder (records facts; defines no pass criteria): tests | demo.
tests -> test_report.json (frontend vitest per-test, svelte-check, build; Python targeted + full; ruff; pip). demo -> demo_regression.json (offline DemoAuth journey)."""

from __future__ import annotations

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

ROOT = Path(__file__).resolve().parents[1]
EVD = Path(os.environ.get("UFL_EVD", ROOT / "reports/ufl_lite/ufl_lite_002"))
FLAKE = "tests/test_capstone_monitoring_websocket.py::test_monitoring_completes_with_zero_subscribers"
CLEAN_ENV_DROP = ("VITE_CLERK", "NEXT_PUBLIC_CLERK", "CLERK_")


def wr(name: str, payload: dict[str, Any]) -> None:
    EVD.mkdir(parents=True, exist_ok=True)
    (EVD / name).write_text(json.dumps(payload, indent=1, sort_keys=True, default=str) + "\n")


def clean_env() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if not k.startswith(CLEAN_ENV_DROP)}


def tests() -> None:
    work = Path(os.environ.get("UFL_WORK", tempfile.mkdtemp(prefix="ufl2-tests-")))
    work.mkdir(parents=True, exist_ok=True)
    env = {**clean_env(), "PYTHONPATH": "src:."}
    fe = ROOT / "frontend"
    rep: dict[str, Any] = {"commands": {}}

    def sh(cmd: list[str], log: str, cwd: Path = ROOT) -> tuple[int, str, float]:
        t0 = time.time()
        r = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=7200)
        (work / log).write_text(r.stdout + r.stderr)
        return r.returncode, r.stdout + r.stderr, round(time.time() - t0, 1)

    def counts(text: str) -> dict[str, int]:
        last = [ln for ln in text.splitlines() if re.search(r" in [\d.]+s", ln)]
        return {k: int(v) for v, k in re.findall(r"(\d+) (passed|failed|skipped|deselected|errors?)", last[-1] if last else "")}

    def junit(path: Path) -> dict[str, str]:
        return {f"{c.get('classname')}::{c.get('name')}": ("failed" if (c.find("failure") is not None or c.find("error") is not None) else "skipped" if c.find("skipped") is not None else "passed") for c in ET.parse(path).getroot().iter("testcase")}

    out = work / "vitest.json"
    rc, _t, secs = sh(["npx", "vitest", "run", "--reporter=json", f"--outputFile={out}"], "vitest.log", fe)
    data = json.loads(out.read_text())
    vt = {a["fullName"]: a["status"] for f in data["testResults"] for a in f["assertionResults"]}
    rep["frontend"] = {"vitest_returncode": rc, "passed": data["numPassedTests"], "failed": data["numFailedTests"], "skipped": data["numPendingTests"], "tests": vt, "seconds_machine_specific": secs}
    rc, text, _ = sh(["npm", "run", "check"], "svelte_check.log", fe)
    m = re.search(r"COMPLETED \d+ FILES (\d+) ERRORS (\d+) WARNINGS", text)
    rep["frontend"]["svelte_check"] = {"returncode": rc, "errors": int(m.group(1)) if m else None, "warnings": int(m.group(2)) if m else None}
    rc, text, _ = sh(["npm", "run", "build"], "build.log", fe)
    rep["frontend"]["build_returncode"] = rc
    rc, text, secs = sh([sys.executable, "-m", "pytest", "tests/test_ufl_lite_presentation.py", "tests/test_ufl_lite_contract.py", "tests/test_capstone_federation_ui.py", "tests/test_capstone_full_demo.py", "tests/test_capstone_lifecycle.py", "-q", "-p", "no:cacheprovider", f"--junitxml={work / 't.xml'}"], "targeted.log")
    rep["targeted_python"] = {"returncode": rc, "counts": counts(text), "tests": junit(work / "t.xml"), "seconds_machine_specific": secs}
    attempts = []
    for i in range(5):
        r = subprocess.run([sys.executable, "-m", "pytest", FLAKE, "-q", "-p", "no:cacheprovider"], cwd=ROOT, env=env, capture_output=True, text=True, timeout=180)
        attempts.append({"attempt": i + 1, "passed": r.returncode == 0, "known_signature": "AssertionError: assert (789 > 100 and False)" in r.stdout + r.stderr})
        if r.returncode == 0:
            break
    rep["inherited_flake"] = {"status": "PASS_INHERITED_FLAKE_POLICY" if any(a["passed"] for a in attempts) and all(a["passed"] or a["known_signature"] for a in attempts) else "FAIL", "attempts": attempts}
    rc, text, secs = sh([sys.executable, "-m", "pytest", "tests", "-q", "-p", "no:cacheprovider", f"--deselect={FLAKE}", f"--junitxml={work / 'full.xml'}"], "full.log")
    full = junit(work / "full.xml")
    rep["full_python"] = {"returncode": rc, "counts": counts(text), "failed": sorted(k for k, v in full.items() if v == "failed"), "seconds_machine_specific": secs}
    rc, text, _ = sh([str(Path(sys.executable).parent / "ruff"), "check", "."], "ruff.log")
    rep["commands"]["ruff"] = {"returncode": rc, "output": text.strip()[-200:]}
    rc, text, _ = sh([sys.executable, "-m", "pip", "check"], "pip.log")
    rep["commands"]["pip_check"] = {"returncode": rc, "output": text.strip()[-200:]}
    rep["ci_queried"] = False
    rep["ci_triggered"] = False
    wr("test_report.json", rep)
    print(json.dumps({"vitest": [rep["frontend"]["passed"], rep["frontend"]["failed"]], "check": rep["frontend"]["svelte_check"], "targeted": rep["targeted_python"]["counts"], "full": rep["full_python"]["counts"]}))


def demo() -> None:
    out = Path(tempfile.mkdtemp(prefix="ufl2-demo-"))
    t0 = time.monotonic()
    env = {**clean_env(), "PYTHONPATH": "src:.", "CAP010_OUT": str(out)}
    r = subprocess.run([sys.executable, "-m", "scripts.run_capstone_full_demo_e2e", "run", "1"], cwd=ROOT, capture_output=True, text=True, env=env, timeout=3600)
    run = json.loads((out / "full_browser_demo_run_1.json").read_text()) if (out / "full_browser_demo_run_1.json").exists() else {}
    steps = {s["step"]: s for s in run.get("browser", {}).get("steps", [])}
    net = run.get("browser", {}).get("network", {})
    canonical = json.loads((ROOT / "reports/capstone/cap_010/full_browser_demo_run_1.json").read_text())["semantic_sha256"]
    cand = [c.get("state_digest") for c in run.get("semantic_projection", {}).get("candidates", [])]
    fed = steps.get("federation", {})
    wr("demo_regression.json", {"status": "PASS" if r.returncode == 0 and run.get("driver_exit") == 0 and run.get("semantic_sha256") == canonical else "FAIL", "demo_auth_works": r.returncode == 0 and run.get("driver_exit") == 0, "semantic_sha256": run.get("semantic_sha256"), "cap_010_canonical_digest": canonical,
                                "equals_canonical": run.get("semantic_sha256") == canonical, "candidate_state_digests": cand, "clerk_global_in_browser": steps.get("sign-in", {}).get("clerkGlobal"), "external_requests": net.get("external"), "blocked_external_requests": net.get("blockedExternal"),
                                "clerk_origins_contacted": [h for h in net.get("origins", []) if "clerk" in h], "federation_run": {"updates": fed.get("final", {}).get("updates"), "maxClientsSubmittedAtOnce": fed.get("maxClientsSubmittedAtOnce")},
                                "owner_binding_in_demo": "ABSENT (DEMO provider never qualifies; asserted by frontend tests and the unchanged semantic digest)", "elapsed_s_machine_specific": round(time.monotonic() - t0, 1)})
    print(json.dumps({"demo": json.loads((EVD / "demo_regression.json").read_text())["status"]}))


if __name__ == "__main__":
    {"tests": tests, "demo": demo}[sys.argv[1]]()
