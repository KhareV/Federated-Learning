# ruff: noqa: E501
"""CAPSTONE_DEMO_PREFLIGHT_V1 -- verifies identities, artifacts and the local environment BEFORE any service starts.

It never trains, infers, bootstraps, calibrates, runs FL/SecAgg or creates a candidate, and it never installs a
package: a missing dependency is reported with the exact setup command instead.
"""

from __future__ import annotations

import csv
import importlib
import json
import socket
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
REQUIRED_IMPORTS = ("fastapi", "uvicorn", "httpx", "pydantic", "numpy", "torch", "yaml", "websockets")
MIN_PYTHON = (3, 11)
BUILD_STAMP = "frontend/build/.nhm_build_stamp.json"


def frontend_source_digest() -> str:
    import hashlib

    digest = hashlib.sha256()
    for path in sorted((FRONTEND / "src").rglob("*")):
        if path.is_file():
            digest.update(str(path.relative_to(FRONTEND)).encode())
            digest.update(path.read_bytes())
    for name in ("package.json", "package-lock.json", "svelte.config.js", "vite.config.ts"):
        digest.update((FRONTEND / name).read_bytes())
    return digest.hexdigest()


def port_free(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket() as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def _registry(name: str, key: str) -> dict[str, str]:
    with (ROOT / f"manifests/capstone/{name}_registry_v1.csv").open(newline="") as handle:
        return {r[key]: r["status"] for r in csv.DictReader(handle)}


# ---- default verifiers (injectable so tests can prove each failure path) -----------------------------------
def v_prior_locks() -> dict[str, Any]:
    from scripts.cap_010_protected_audit import all_locks

    locks = all_locks()
    bad = sorted(k for k, v in locks.items() if not v["verified"])
    return {"ok": not bad, "detail": f"{len(locks)} locks/chains" if not bad else f"FAILED:{bad}"}


def v_phase_state() -> dict[str, Any]:
    t, g = _registry("task", "task_id"), _registry("gate", "gate_id")
    ok = t.get("CAP-009") == "PASS" and g.get("CAPG8") == "PASS" and t.get("CAP-010") in {"IN_PROGRESS", "PASS"} and t.get("CAP-011") == "NOT_STARTED"
    return {"ok": ok, "detail": f"CAP-009={t.get('CAP-009')} CAPG8={g.get('CAPG8')} CAP-010={t.get('CAP-010')} CAP-011={t.get('CAP-011')}"}


def v_runtime_binding() -> dict[str, Any]:
    from scripts.verify_default_runtime_binding_v2 import verify

    result = verify()
    default = (ROOT / "artifacts/DEFAULT_RUNTIME_BINDING_V2.lock.json").read_text()
    forbidden = "CAPSTONE_FL_CANDIDATE" in default
    return {"ok": result["status"] == "PASS" and not forbidden, "detail": "SOFTWARE_SYSTEM_V2 + DEFAULT_RUNTIME_BINDING_V2 verified; no candidate binding"}


def v_product_import() -> dict[str, Any]:
    module = importlib.import_module("api.product_app_v1_3")
    return {"ok": module.IMPLEMENTATION_ID == "CAPSTONE_PRODUCT_API_V1_3", "detail": module.IMPLEMENTATION_ID}


def v_ui() -> dict[str, Any]:
    from scripts.verify_capstone_ui_v1_2 import verify

    return {"ok": verify()["status"] == "PASS", "detail": "CAPSTONE_UI_V1_2 verified"}


def v_catalog() -> dict[str, Any]:
    from scripts.verify_capstone_research_evidence_catalog import verify

    return {"ok": verify()["status"] == "PASS", "detail": "CAPSTONE_RESEARCH_EVIDENCE_CATALOG_V1 verified"}


def v_python() -> dict[str, Any]:
    ok = sys.version_info >= MIN_PYTHON
    return {"ok": ok, "detail": f"python {sys.version_info.major}.{sys.version_info.minor}"}


def v_imports() -> dict[str, Any]:
    missing = []
    for name in REQUIRED_IMPORTS:
        try:
            importlib.import_module(name)
        except ImportError:
            missing.append(name)
    return {"ok": not missing, "detail": "all required imports present" if not missing else f"MISSING:{missing} -- install the locked environment (requirements-dev.lock) BEFORE the demo"}


def v_frontend_deps() -> dict[str, Any]:
    app = (FRONTEND / "node_modules").is_dir()
    clerk = (FRONTEND / "clerk-sdk/node_modules/@clerk/clerk-js").is_dir()
    node = subprocess.run(["node", "--version"], capture_output=True, text=True).returncode == 0 if _which("node") else False
    ok = app and clerk and node
    hint = "" if ok else " -- setup: (cd frontend/clerk-sdk && npm ci) and (cd frontend && npm ci); the launcher never installs packages"
    return {"ok": ok, "detail": f"frontend node_modules={app} clerk-sdk={clerk} node={node}{hint}"}


def v_frontend_build() -> dict[str, Any]:
    stamp = ROOT / BUILD_STAMP
    if not (FRONTEND / "build/index.html").is_file() or not stamp.is_file():
        return {"ok": False, "detail": "FRONTEND_BUILD_MISSING -- run the launcher with --build (npm run build)"}
    current = frontend_source_digest()
    recorded = json.loads(stamp.read_text()).get("frontend_source_sha256")
    return {"ok": recorded == current, "detail": "build matches the current frontend source" if recorded == current else "STALE_FRONTEND_BUILD -- run the launcher with --build"}


def _which(cmd: str) -> bool:
    import shutil

    return shutil.which(cmd) is not None


DEFAULT_VERIFIERS: dict[str, Callable[[], dict[str, Any]]] = {
    "python_version": v_python, "required_imports": v_imports, "prior_locks_and_amendments": v_prior_locks, "phase_state": v_phase_state,
    "runtime_binding": v_runtime_binding, "product_api_import": v_product_import, "ui_successor": v_ui, "research_catalog": v_catalog,
    "frontend_dependencies": v_frontend_deps, "frontend_build": v_frontend_build,
}


def run_preflight(*, ports: dict[str, int], acknowledged: bool, workspace_ok: bool = True, workspace_detail: str = "",
                  verifiers: dict[str, Callable[[], dict[str, Any]]] | None = None, skip_build_check: bool = False) -> dict[str, Any]:
    """Return {passed, checks}. Never raises for a failed check; a verifier exception is a failed check."""
    checks: dict[str, dict[str, Any]] = {"demo_auth_acknowledgement": {"ok": acknowledged, "detail": "explicit --acknowledge-demo-auth" if acknowledged else "DEMO_AUTH_ACKNOWLEDGEMENT_REQUIRED"},
                                         "workspace": {"ok": workspace_ok, "detail": workspace_detail or "workspace valid"}}
    for service, port in ports.items():
        free = port_free(port)
        checks[f"port_{service}"] = {"ok": free, "detail": f"{port} available" if free else f"PORT_IN_USE:{service}:{port}"}
    for name, verifier in (verifiers or DEFAULT_VERIFIERS).items():
        if name == "frontend_build" and skip_build_check:
            checks[name] = {"ok": True, "detail": "will be rebuilt by --build"}
            continue
        try:
            checks[name] = verifier()
        except Exception as error:
            checks[name] = {"ok": False, "detail": f"{type(error).__name__}:{str(error)[:200]}"}
    return {"passed": all(c["ok"] for c in checks.values()), "checks": checks,
            "science_executed": {"training": 0, "inference": 0, "bootstrap": 0, "calibration": 0, "fl": 0, "secagg": 0, "candidates": 0}}
