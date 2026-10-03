#!/usr/bin/env python3
"""V2-013 final evidence assembly. Run after every canonical result, the chunked regression and
the lock freeze. Writes post-run protected/method audits, reproducibility, provenance,
regression_audit, run_manifest and, LAST, artifact_hashes (avoids stale pins)."""

from __future__ import annotations

import json
import platform
import subprocess
import sys

from nhm.hashing import hash_file
from scripts._v2_013_lib import OUT, ROOT

RUN_LOG_FILES = {"pytest_collected_nodes.txt", "pytest_chunk_manifest.csv",
                 "pytest_chunk_results.csv"}
AMENDMENT_ALLOWED = {"scripts/run_v2_013_v1_isolation.py"}


def _sh(*args: str) -> str:
    return subprocess.run(args, cwd=ROOT, capture_output=True, text=True, check=False
                          ).stdout.strip()


def _write(name: str, data: dict) -> None:
    (OUT / name).write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load(name: str) -> dict:
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def method_immutability() -> dict:
    frozen = _load("method_freeze.json")["method_file_sha256"]
    changed = sorted(p for p, d in frozen.items() if hash_file(ROOT / p) != d)
    method_commit = _sh(
        "git", "log", "--format=%H", "-n", "1", "--", "scripts/freeze_v2_013_method.py")
    amendments = {}
    for path in changed:
        amendments[path] = _sh("git", "diff", method_commit, "--", path)
    unexpected = sorted(set(changed) - AMENDMENT_ALLOWED)
    data = {
        "method_commit": method_commit, "files_changed_since_method_freeze": changed,
        "unexpected_changes": unexpected, "disclosed_amendments": amendments,
        "amendment_reason": (
            "The V1-default regression check counted the NEW additive file "
            "fusion/alert_policy_v2_binding.py as a modified V1 file because its git pathspec "
            "covers the fusion/ directory. The pathspec filter was scoped to "
            "--diff-filter=MDRT (modified/deleted/renamed/type-changed). No pass criterion for "
            "any V1 file was loosened, and no model, calibration, policy, signal-processing or "
            "replay behavior changed."),
        "status": "PASS" if not unexpected else "FAIL",
    }
    _write("method_immutability_audit.json", data)
    return data


def protected_post() -> dict:
    baseline = _load("protected_baseline.json")["artifacts"]
    drift = sorted(p for p, d in baseline.items() if hash_file(ROOT / p) != d)
    data = {"checked": len(baseline), "drifted": drift,
            "status": "PASS" if not drift else "FAIL"}
    _write("protected_artifact_post_audit.json", data)
    return data


def reproducibility() -> dict:
    digest = _load("replay_semantic_digest.json")
    manifest = _load("replay_fixture_manifest.json")
    bundle = ROOT / "frontend/static/replay/WEARABLE_SIM_V2_REPLAY_V1.json"
    data = {
        "two_fresh_process_runs_identical": digest["run_1_equals_run_2"],
        "frontend_path_equals_direct_http": digest["frontend_path_equals_direct_http"],
        "live_speed_equals_accelerated": _load("replay_mode_invariance.json")[
            "semantic_outputs_identical"],
        "bundle_sha256_matches_manifest": hash_file(bundle) == manifest["bundle_sha256"],
        "semantic_digest": digest["digests"]["run_1_frontend_path"],
        "status": "PASS",
    }
    data["status"] = "PASS" if all(v for k, v in data.items() if k != "semantic_digest"
                                   and k != "status") else "FAIL"
    _write("reproducibility.json", data)
    return data


def _run(*args: str, cwd=ROOT) -> dict:
    result = subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=False)
    return {"command": " ".join(args), "exit_code": result.returncode,
            "tail": (result.stdout + result.stderr).strip().splitlines()[-2:]}


def regression() -> dict:
    chunked = _load("pre_export_regression.json")
    frontend = ROOT / "frontend"
    checks = {
        "ruff": _run(sys.executable, "-m", "ruff", "check", "src", "tests", "scripts",
                     "simulation", "deployment", "fusion", "api", "datasets", "features",
                     "models", "training", "evaluation", "preprocessing"),
        "pip_check": _run(sys.executable, "-m", "pip", "check"),
        "frontend_unit": _run("npm", "--prefix", str(frontend), "run", "test"),
        "frontend_check": _run("npm", "--prefix", str(frontend), "run", "check"),
        "frontend_build": _run("npm", "--prefix", str(frontend), "run", "build"),
    }
    ok = chunked.get("status") == "PASS" and all(c["exit_code"] == 0 for c in checks.values())
    data = {"chunked_python_regression": chunked, "checks": checks,
            "browser_e2e_note": "no browser-automation stack exists in the repository; the "
            "real-HTTP vitest component E2E (frontend_e2e_evidence.json) is the E2E gate",
            "ci": "deferred; GitHub Actions never triggered, queried or polled",
            "status": "PASS" if ok else "FAIL"}
    _write("regression_audit.json", data)
    return data


def provenance() -> dict:
    data = {
        "entry_sha": "40e127308b50bb4d5943826639d467203b9b4b29",
        "head_at_finalization": _sh("git", "rev-parse", "HEAD"),
        "python": sys.version.split()[0], "platform": platform.platform(),
        "node": _sh("node", "--version"),
        "ruff": _sh(sys.executable, "-m", "ruff", "--version"),
        "frontend_vitest": "frontend/package.json pinned",
        "neural_fits": 0, "cumulative_v2_neural_fits": 71,
        "protected_partitions_accessed": [],
        "simulation_claim_boundary": "engineering evidence from virtual participants only",
    }
    _write("provenance.json", data)
    return data


def main() -> None:
    reg = regression()
    parts = {"method": method_immutability(), "protected": protected_post(),
             "repro": reproducibility()}
    provenance()
    if reg.get("status") != "PASS" or any(p["status"] != "PASS" for p in parts.values()):
        states = {k: v["status"] for k, v in parts.items()}
        sys.exit(f"V2_013_FINALIZE_FAILED:{reg.get('status')}:{states}")
    _write("run_manifest.json", {
        "checkpoint_id": "V2-013", "owner_task": "V2-013", "gate": "V2G12",
        "API_RUNTIME_V2": "FROZEN_RESEARCH_RUNTIME",
        "WEARABLE_SIM_V1_TO_V2_SOFTWARE_PATH": "VERIFIED_ENGINEERING_INTEGRATION",
        "V2_SOFTWARE_REPLAY": "FROZEN_COMPLETE",
        "MODEL_V2_RUNTIME_ACCEPTED": "ACCEPTED", "operational_default": "MODEL_V1",
        "official_validation_disposition": "MODEL_V2_NOT_PROMOTED_RELEASE_CI",
        "cumulative_v2_neural_fits": 71, "v2_014": "NOT_STARTED/RESERVED",
        "next_phase": "V2-FL-001 (not started)", "ci": "deferred; Actions not queried",
        "status": "PASS"})
    files = sorted(p.name for p in OUT.iterdir() if p.is_file())
    _write("artifact_hashes.json", {"artifacts": {
        f"reports/model_v2/v2_013/{n}": hash_file(OUT / n)
        for n in files if n not in RUN_LOG_FILES and n != "artifact_hashes.json"
        and not n.startswith("_")}})
    print("V2-013 evidence finalized")


if __name__ == "__main__":
    main()
