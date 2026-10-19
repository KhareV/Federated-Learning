# ruff: noqa: E501
"""One-command preflight for a live demonstration. Read-only: it connects, reads and counts, and writes nothing.

    PYTHONPATH=src:. python -m scripts.demo_preflight [--workspace DIR] [--env-file .env]

Every check prints PASS / WARN / FAIL with its reason; the exit code is 1 only when something FAILs. WARN means "the demo can run, but know this". The checks target what has actually gone wrong
in rehearsal: ports still held by an earlier site, the Clerk host unreachable (use ``--demo`` offline authentication then), a wrong or unreachable MongoDB, generated demo data sharing the real device
database, a missing or altered V2 checkpoint, missing frozen evidence, and a temporary workspace that will lose every run at the next restart."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import shutil
import socket
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PORTS = (4173, 8001, 8002)
EVIDENCE = ("reports/final_showcase/recorded_run/recorded_verified_run.json", "reports/fl10/eval/modeA/evaluation_results.json", "docs/final_showcase/results_traceability.md",
            "reports/model_v2/v2_fl_eval_001/historical_frozen_centralized_references.json")
MIN_FREE_BYTES = 2 * 1024**3


@dataclass(frozen=True)
class Check:
    name: str
    status: str            # PASS | WARN | FAIL
    detail: str


def _p(name: str, detail: str) -> Check:
    return Check(name, "PASS", detail)


def _w(name: str, detail: str) -> Check:
    return Check(name, "WARN", detail)


def _f(name: str, detail: str) -> Check:
    return Check(name, "FAIL", detail)


def check_python(version: tuple[int, int] | None = None) -> Check:
    v = version or sys.version_info[:2]
    return _p("python", f"{v[0]}.{v[1]}") if tuple(v) == (3, 11) else _f("python", f"{v[0]}.{v[1]} (the locked environment is Python 3.11)")


def check_node(which: Callable[[str], str | None] = shutil.which, root: Path = ROOT) -> Check:
    if which("node") is None:
        return _f("node", "node is not on PATH (the frontend is built and served with it)")
    return _p("node", "found") if (root / "frontend/node_modules").is_dir() else _w("node", "found, but frontend/node_modules is missing: run `cd frontend && npm ci`")


def check_ports(ports: tuple[int, ...] = PORTS, in_use: Callable[[int], bool] | None = None) -> Check:
    def busy(port: int) -> bool:
        with socket.socket() as s:
            s.settimeout(0.5)
            return s.connect_ex(("127.0.0.1", port)) == 0

    held = [p for p in ports if (in_use or busy)(p)]
    return _f("ports", f"{held} already in use (is an earlier site still running?)") if held else _p("ports", f"{', '.join(map(str, ports))} are free")


def check_env(env: Mapping[str, str]) -> Check:
    missing = [k for k in ("CLERK_PUBLISHABLE_KEY", "CLERK_SECRET_KEY") if not env.get(k) and not (k == "CLERK_PUBLISHABLE_KEY" and env.get("VITE_CLERK_PUBLISHABLE_KEY"))]
    return _f("clerk keys", f"missing {missing}; use `python -m scripts.run_nhm --demo` for offline demonstration authentication") if missing else _p("clerk keys", "present (values are never printed)")


def clerk_host(publishable_key: str) -> str | None:
    """The Clerk frontend host encoded in a publishable key (pk_test_<base64 of host$>)."""
    try:
        encoded = publishable_key.split("_", 2)[2]
        return base64.b64decode(encoded + "=" * (-len(encoded) % 4)).decode().rstrip("$") or None
    except (IndexError, ValueError, UnicodeDecodeError):
        return None


def check_clerk(env: Mapping[str, str], connect: Callable[[tuple[str, int], float], Any] = socket.create_connection) -> Check:
    key = env.get("CLERK_PUBLISHABLE_KEY") or env.get("VITE_CLERK_PUBLISHABLE_KEY") or ""
    host = clerk_host(key)
    if host is None:
        return _w("clerk reachable", "no publishable key to derive the host from")
    try:
        connect((host, 443), 4.0).close()
    except OSError as error:
        return _w("clerk reachable", f"{host}:443 not reachable ({type(error).__name__}): sign-in will fail; use `python -m scripts.run_nhm --demo` (offline authentication)")
    return _p("clerk reachable", f"{host}:443")


def check_mongo(env: Mapping[str, str], factory: Callable[..., Any] | None = None) -> Check:
    if env.get("NHM_HARDWARE_MONGO_ENABLED", "").lower() != "true":
        return _p("mongodb", "hardware source disabled (simulated sources only)")
    try:
        client = (factory or _mongo_client)(env["NHM_HARDWARE_MONGO_URI"])
        client.admin.command("ping")
        client.close()
    except Exception as error:
        return _w("mongodb", f"hardware source enabled but not reachable ({type(error).__name__}): the Monitor hardware source and History import will be unavailable")
    database, demo = env.get("NHM_HARDWARE_MONGO_DATABASE", "?"), env.get("NHM_HARDWARE_DEMO_DATABASE")
    if demo and demo != database:
        return _p("mongodb", f"reachable; real telemetry in `{database}`, generated demo collections in `{demo}`")
    return _w("mongodb", f"reachable; generated demo collections share `{database}` with real device telemetry: set NHM_HARDWARE_DEMO_DATABASE (for example nhm_demo) to separate them")


def _mongo_client(uri: str) -> Any:
    from pymongo import MongoClient

    return MongoClient(uri, serverSelectionTimeoutMS=4000, connectTimeoutMS=4000)


def check_checkpoint(root: Path = ROOT) -> Check:
    try:
        manifest = json.loads((root / "checkpoints/MODEL_V2_FINAL.manifest.json").read_text())
        actual = hashlib.sha256((root / "checkpoints/MODEL_V2_FINAL.pt").read_bytes()).hexdigest()
    except OSError as error:
        return _f("MODEL_V2_FINAL", f"checkpoint or manifest unreadable ({type(error).__name__})")
    return _p("MODEL_V2_FINAL", f"digest {actual[:12]}… matches its manifest") if actual == manifest["checkpoint"]["sha256"] else _f("MODEL_V2_FINAL", "checkpoint digest differs from its manifest")


def check_evidence(root: Path = ROOT) -> Check:
    missing = [p for p in EVIDENCE if not (root / p).is_file()]
    return _f("frozen evidence", f"missing {missing}") if missing else _p("frozen evidence", f"{len(EVIDENCE)} key evidence files present (the Observatory reads them; the clean-clone tests verify their digests)")


def check_workspace(path: Path | None, sentinel: str = "CAPSTONE_DEMO_WORKSPACE_V1.json") -> Check:
    if path is None:
        return _w("workspace", "default: a fresh temporary workspace per launch, so every run and History entry is lost at the next restart. Launch with `--durable` to keep one")
    if not (path / sentinel).exists():
        return _w("workspace", f"{path} does not exist yet: `--durable` creates it on first launch, then resumes it")
    runs = len(list(path.glob("federation/**/FL10RUN-*/meta.json"))) + len(list(path.glob("federation/**/hardware_demo/HDFLRUN-*/run.json")))
    return _p("workspace", f"{path} (will resume; {runs} stored run{'' if runs == 1 else 's'})")


def check_library(env: Mapping[str, str]) -> Check:
    from studio.candidates import default_root

    root = default_root(env)
    count = len(list(root.glob("*/*/candidate.json"))) if root.is_dir() else 0
    return _p("candidate library", f"{root} ({count} stored candidate{'' if count == 1 else 's'}; kept across restarts)")


def check_disk(path: Path | None = None, usage: Callable[[Path], Any] = shutil.disk_usage) -> Check:
    free = usage(path or Path.home()).free
    return _w("disk", f"{free / 1024**3:.1f} GB free (a long session writes a few hundred MB)") if free < MIN_FREE_BYTES else _p("disk", f"{free / 1024**3:.0f} GB free")


def run_checks(env: Mapping[str, str], workspace: Path | None, root: Path = ROOT) -> list[Check]:
    return [check_python(), check_node(root=root), check_ports(), check_env(env), check_clerk(env), check_mongo(env), check_checkpoint(root), check_evidence(root), check_workspace(workspace), check_library(env), check_disk()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--workspace", help="the durable workspace directory you will launch with (--durable); omit if launching with the default temporary workspace")
    parser.add_argument("--env-file", default=str(ROOT / ".env"))
    args = parser.parse_args(argv)
    from scripts.run_capstone_clerk_connected import parse_env_file

    env = {**(parse_env_file(Path(args.env_file)) if Path(args.env_file).is_file() else {}), **os.environ}
    checks = run_checks(env, Path(args.workspace).expanduser() if args.workspace else None)
    for c in checks:
        print(f"{c.status:4}  {c.name:18} {c.detail}")
    failed = [c for c in checks if c.status == "FAIL"]
    warned = [c for c in checks if c.status == "WARN"]
    print(f"\n{'NOT READY' if failed else 'READY'}: {len(checks) - len(failed) - len(warned)} pass, {len(warned)} warn, {len(failed)} fail")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
