# ruff: noqa: E501
"""CAPSTONE_CLERK_CONNECTED_V1 launcher: the SAME three services as the offline faculty launcher, configured for real Clerk
(TEST/development instance) authentication. Credentials come from the ENVIRONMENT only (or an explicit --env-file outside Git);
the secret is passed to the product API process environment ONLY, never to the frontend build/preview, never printed and never
placed in an argument list. There is NO fallback to DemoAuth: absent/invalid configuration refuses to start.

  NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=<pk_test_...> CLERK_SECRET_KEY=<sk_test_...> python -m scripts.run_capstone_clerk_connected [--build]

NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY (the operator-supplied name) is mapped internally to the Vite-native VITE_CLERK_PUBLISHABLE_KEY;
the frontend never reads NEXT_PUBLIC_*. Connected mode needs INTERNET access to Clerk; the offline DemoAuth faculty mode is separate."""

from __future__ import annotations

import argparse
import json
import os
import re
import signal
import subprocess
import sys
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import httpx

from scripts.capstone_demo_preflight import DEFAULT_VERIFIERS, port_free
from scripts.capstone_demo_workspace import Workspace, WorkspaceError
from scripts.run_capstone_faculty_demo import (
    BUILD_STAMP,
    DEFAULT_PORTS,
    EXIT,
    FRONTEND,
    HOST,
    ROOT,
    DemoOrchestrator,
    ServiceSpec,
    frontend_source_digest,
    probe_frontend,
    probe_inference,
)

ENV_PK_VITE, ENV_PK_NEXT, ENV_PK_BACKEND, ENV_SECRET, ENV_PARTIES = "VITE_CLERK_PUBLISHABLE_KEY", "NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY", "CLERK_PUBLISHABLE_KEY", "CLERK_SECRET_KEY", "NHM_CLERK_AUTHORIZED_PARTIES"
SECRET_VARS = (ENV_SECRET, "CLERK_JWT_KEY")
ORIGIN = re.compile(r"^https?://[A-Za-z0-9.\-]+(:\d{1,5})?$")
PK_TEST = re.compile(r"^pk_test_[A-Za-z0-9+/=_\-]{8,}$")
SK_TEST = re.compile(r"^sk_test_[A-Za-z0-9]{8,}$")
CLERK_EXTRA_EXIT = 8


class ConnectedConfigError(RuntimeError):
    pass


def parse_env_file(path: Path) -> dict[str, str]:
    """Minimal KEY=VALUE reader (no shell evaluation, no expansion). The file must be outside tracked paths."""
    out: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        out[key.strip()] = value.strip().strip('"').strip("'")
    return out


def resolve_config(env: Mapping[str, str], frontend_port: int, extra_origins: list[str] | None = None) -> dict[str, Any]:
    """Validate and normalise the connected configuration. Returns the product/frontend environment overlays; never prints secrets."""
    publishable = (env.get(ENV_PK_VITE) or env.get(ENV_PK_NEXT) or "").strip()
    secret = (env.get(ENV_SECRET) or "").strip()
    if not publishable:
        raise ConnectedConfigError("CLERK_PUBLISHABLE_KEY_ABSENT (set VITE_CLERK_PUBLISHABLE_KEY or NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY)")
    if not secret:
        raise ConnectedConfigError("CLERK_SECRET_KEY_ABSENT")
    if not PK_TEST.match(publishable):
        raise ConnectedConfigError("PUBLISHABLE_KEY_IS_NOT_A_CLERK_TEST_KEY (pk_test_ expected; this integration verifies a TEST/development instance only)")
    if not SK_TEST.match(secret):
        raise ConnectedConfigError("SECRET_KEY_IS_NOT_A_CLERK_TEST_KEY (sk_test_ expected)")
    if env.get(ENV_PK_VITE) and env.get(ENV_PK_NEXT) and env[ENV_PK_VITE].strip() != env[ENV_PK_NEXT].strip():
        raise ConnectedConfigError("PUBLISHABLE_KEY_VARIABLES_DISAGREE")
    raw_parties = env.get(ENV_PARTIES, "").strip()
    parties = [p.strip() for p in raw_parties.split(",") if p.strip()] if raw_parties else [f"http://{HOST}:{frontend_port}", *(extra_origins or [])]
    if not parties or any(p == "*" or not ORIGIN.match(p) for p in parties):
        raise ConnectedConfigError("AUTHORIZED_PARTIES_MUST_BE_EXPLICIT_ORIGINS (no wildcard)")
    if f"http://{HOST}:{frontend_port}" not in parties and not raw_parties:
        raise ConnectedConfigError("AUTHORIZED_PARTIES_MISSING_FRONTEND_ORIGIN")
    return {"publishable_key": publishable, "secret_key": secret, "authorized_parties": parties}


def clerk_probe_product(port: int) -> tuple[bool, str]:
    try:
        r = httpx.get(f"http://{HOST}:{port}/product/v1/system", timeout=2.0)
        body = r.json()
    except (httpx.HTTPError, ValueError):
        return False, "not ready"
    want = {"product_api_implementation": "CAPSTONE_PRODUCT_API_V1_3", "software_system": "SOFTWARE_SYSTEM_V2", "model_id": "MODEL_V2_FINAL", "persistence_mode": "SQLITE", "auth_provider": "CLERK",
            "demo_mode": False, "federation_runtime": "ENABLED_ENGINEERING", "hardware_mode": "SIMULATED_ONLY"}
    bad = {k: body.get(k) for k, v in want.items() if body.get(k) != v}
    return (r.status_code == 200 and not bad), json.dumps(bad) if bad else "CLERK"


def build_services(ws: Workspace, ports: dict[str, int], cfg: dict[str, Any], base_env: Mapping[str, str], python: str = sys.executable) -> list[ServiceSpec]:
    clean = {k: v for k, v in base_env.items() if not k.startswith(("CLERK_", "VITE_CLERK", "NEXT_PUBLIC_CLERK", "NHM_CLERK", "NHM_PRODUCT_DEMO"))}
    clean["PYTHONPATH"] = "src:."
    product_env = {**clean, "NHM_PRODUCT_AUTH_MODE": "CLERK", ENV_SECRET: cfg["secret_key"], ENV_PK_BACKEND: cfg["publishable_key"], ENV_PARTIES: ",".join(cfg["authorized_parties"]),
                   "NHM_PRODUCT_DB_PATH": str(ws.db), "NHM_FEDERATION_ARTIFACT_ROOT": str(ws.federation), "NHM_FL_CANDIDATE_ROOT": str(ws.candidates),
                   "NHM_PRODUCT_INFERENCE_URL": f"http://{HOST}:{ports['inference']}", "NHM_PRODUCT_TIMING_MODE": "ACCELERATED"}
    frontend_env = {**clean, "NHM_PRODUCT_API_PORT": str(ports["product"]), ENV_PK_VITE: cfg["publishable_key"]}     # NO secret, NO NEXT_PUBLIC_*
    return [
        ServiceSpec("inference", [python, "-m", "scripts.run_nhm_default", "--profile", "default", "--host", HOST, "--port", str(ports["inference"])], clean, ROOT, ws.logs / "inference.log", lambda: probe_inference(ports["inference"]), ports["inference"]),
        ServiceSpec("product", [python, "-m", "scripts.run_capstone_product_v1_3", "--host", HOST, "--port", str(ports["product"])], product_env, ROOT, ws.logs / "product.log", lambda: clerk_probe_product(ports["product"]), ports["product"]),
        ServiceSpec("frontend", ["npm", "run", "preview", "--", "--port", str(ports["frontend"]), "--strictPort", "--host", HOST], frontend_env, FRONTEND, ws.logs / "frontend.log", lambda: probe_frontend(ports["frontend"]), ports["frontend"]),
    ]


def build_frontend(cfg: dict[str, Any], base_env: Mapping[str, str], say=print) -> float:
    """`npm run build` with ONLY the publishable key supplied (VITE_ mapping); the secret never reaches the build environment."""
    started = time.monotonic()
    say("building the existing frontend with the Clerk publishable key (VITE_CLERK_PUBLISHABLE_KEY)")
    env = {k: v for k, v in base_env.items() if not k.startswith(("CLERK_", "VITE_CLERK", "NEXT_PUBLIC_CLERK", "NHM_CLERK"))}
    env[ENV_PK_VITE] = cfg["publishable_key"]
    r = subprocess.run(["npm", "run", "build"], cwd=FRONTEND, capture_output=True, text=True, env=env)
    if r.returncode != 0:
        raise RuntimeError("FRONTEND_BUILD_FAILED:" + (r.stdout + r.stderr)[-300:].replace(cfg["secret_key"], "<REDACTED>"))
    (ROOT / BUILD_STAMP).write_text(json.dumps({"frontend_source_sha256": frontend_source_digest(), "clerk_publishable_key_mapped": True}) + "\n")
    return round(time.monotonic() - started, 3)


def ready_block(ports: dict[str, int], ws: Workspace, parties: list[str]) -> str:
    return "\n".join(["NHM CLERK-CONNECTED SYSTEM READY", "", f"Frontend:   http://{HOST}:{ports['frontend']}/sign-in", "Inference:  SOFTWARE_SYSTEM_V2 / MODEL_V2_FINAL",
                      "Product:    CAPSTONE_PRODUCT_API_V1_3", "Auth:       CLERK (real TEST instance; requires Internet access to Clerk; NO DemoAuth fallback)", f"Origins:    {', '.join(parties)}",
                      "Hardware:   SIMULATED ONLY", "FL:         ENGINEERING FEDERATION (8 logical synthetic clients, one laptop)", f"Workspace:  {ws.path}", "Stop:       Ctrl+C"])


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="NHM Clerk-connected launcher (real Clerk TEST instance)")
    p.add_argument("--workspace")
    p.add_argument("--mode", choices=("fresh", "resume"), default="fresh")
    p.add_argument("--inference-port", type=int, default=DEFAULT_PORTS["inference"])
    p.add_argument("--product-port", type=int, default=DEFAULT_PORTS["product"])
    p.add_argument("--frontend-port", type=int, default=DEFAULT_PORTS["frontend"])
    p.add_argument("--also-localhost-origin", action="store_true", help="additionally authorise http://localhost:<frontend-port>")
    p.add_argument("--env-file", help="optional KEY=VALUE credentials file (never committed); the environment takes precedence")
    p.add_argument("--build", action="store_true", help="run `npm run build` with the Clerk publishable key mapped to VITE_CLERK_PUBLISHABLE_KEY")
    p.add_argument("--preflight-only", action="store_true")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    ports = {"inference": args.inference_port, "product": args.product_port, "frontend": args.frontend_port}
    env: dict[str, str] = dict(os.environ)
    if args.env_file:
        env = {**parse_env_file(Path(args.env_file)), **env}
    extra = [f"http://localhost:{args.frontend_port}"] if args.also_localhost_origin else []
    try:
        cfg = resolve_config(env, args.frontend_port, extra)
    except ConnectedConfigError as error:
        print(f"REFUSING TO START: {error}", file=sys.stderr)
        return EXIT["REFUSED"]
    busy = [f"PORT_IN_USE:{n}:{p}" for n, p in ports.items() if not port_free(p)]
    if busy:
        print("REFUSING TO START: " + " ".join(busy), file=sys.stderr)
        return EXIT["PORT_IN_USE"]
    pre = {name: v() for name, v in DEFAULT_VERIFIERS.items() if not (name == "frontend_build" and args.build)}
    print(json.dumps({"preflight": {k: v["ok"] for k, v in pre.items()}, "auth": "CLERK", "authorized_parties": cfg["authorized_parties"], "secret_key_present": True, "publishable_key_present": True}))
    if not all(v["ok"] for v in pre.values()):
        for name, c in pre.items():
            if not c["ok"]:
                print(f"PREFLIGHT_FAILED:{name}:{c['detail']}", file=sys.stderr)
        return EXIT["PREFLIGHT_FAILED"]
    if args.preflight_only:
        return EXIT["OK"]
    try:
        ws = Workspace.open_resume(args.workspace) if args.mode == "resume" else Workspace.create_fresh(args.workspace)
    except WorkspaceError as error:
        print(f"REFUSING TO START: {error}", file=sys.stderr)
        return EXIT["WORKSPACE"]
    if args.build:
        build_frontend(cfg, env)
    orch = DemoOrchestrator(build_services(ws, ports, cfg, env), say=lambda m: print(m, flush=True))

    def on_signal(signum: int, _frame: Any) -> None:
        orch.stop_requested = True

    signal.signal(signal.SIGINT, on_signal)
    signal.signal(signal.SIGTERM, on_signal)
    if not orch.start_and_wait_ready():
        return EXIT["READY_TIMEOUT"] if (orch.failed or "").startswith("READY_TIMEOUT") else EXIT["SERVICE_FAILURE"]
    (ws.path / "status.json").write_text(json.dumps({"ports": ports, "workspace": str(ws.path), "pids": orch.launched_pids, "auth": "CLERK", "authorized_parties": cfg["authorized_parties"], "timing": "ACCELERATED"}, indent=1, sort_keys=True) + "\n")
    print(ready_block(ports, ws, cfg["authorized_parties"]), flush=True)
    code = orch.supervise()
    orphans = orch.orphans()
    (ws.path / "shutdown.json").write_text(json.dumps({"exit_code": code, "orphans": orphans}, indent=1) + "\n")
    return code


if __name__ == "__main__":
    sys.exit(main())
