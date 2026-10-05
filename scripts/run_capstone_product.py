# ruff: noqa: E501
"""Launcher for the CAP-004 product API (CAPSTONE_PRODUCT_API_V1_1).

    NHM_PRODUCT_AUTH_MODE=DEMO NHM_PRODUCT_DEMO_AUTH_ACK=I_UNDERSTAND_THIS_IS_NOT_CLERK \
      PYTHONPATH=src:. python -m scripts.run_capstone_product --port 8002

The auth provider comes ONLY from NHM_PRODUCT_AUTH_MODE (CLERK | DEMO); an unset/invalid mode, a DEMO
mode without the exact acknowledgement or an incomplete Clerk configuration makes the process exit
non-zero BEFORE it listens. Database: NHM_PRODUCT_DB_PATH (default data/capstone/product.sqlite3).
Inference: NHM_PRODUCT_INFERENCE_URL (the released service, default http://127.0.0.1:8001).
CORS: NHM_PRODUCT_ALLOWED_ORIGINS (comma separated, explicit origins only).
Timing (engineering): NHM_PRODUCT_TIMING_MODE=ACCELERATED (default) | LIVE_SPEED.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Mapping

from api.product_app_v1_1 import (
    DEFAULT_DEV_ORIGINS,
    DEFAULT_INFERENCE_URL,
    create_product_app_v1_1,
)
from product.auth.base import AuthConfigError
from product.auth.factory import build_auth_provider
from product.auth.resolver import make_identity_resolver
from product.devices.scenarios import TimingMode
from product.persistence.store import DEFAULT_DB_PATH, ENV_DB_PATH, CapstoneSqliteStore

ENV_INFERENCE_URL = "NHM_PRODUCT_INFERENCE_URL"
ENV_ALLOWED_ORIGINS = "NHM_PRODUCT_ALLOWED_ORIGINS"
ENV_TIMING_MODE = "NHM_PRODUCT_TIMING_MODE"  # engineering: ACCELERATED (default) | LIVE_SPEED


def build_app_from_env(env: Mapping[str, str]):
    provider = build_auth_provider(env)  # raises AuthConfigError: no silent default, no fallback
    origins = tuple(o.strip() for o in env.get(ENV_ALLOWED_ORIGINS, "").split(",") if o.strip())
    try:
        mode = TimingMode(env.get(ENV_TIMING_MODE, TimingMode.ACCELERATED.value))
    except ValueError as error:
        raise AuthConfigError(f"INVALID_TIMING_MODE:{env.get(ENV_TIMING_MODE)}") from error
    store = CapstoneSqliteStore(env.get(ENV_DB_PATH, DEFAULT_DB_PATH))
    return create_product_app_v1_1(
        store=store, identity_resolver=make_identity_resolver(provider),
        auth_description=provider.describe(),
        inference_base_url=env.get(ENV_INFERENCE_URL, DEFAULT_INFERENCE_URL),
        allowed_origins=origins or DEFAULT_DEV_ORIGINS, timing_mode=mode)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8002)
    parser.add_argument("--log-level", default="warning")
    args = parser.parse_args()
    try:
        app = build_app_from_env(os.environ)
    except AuthConfigError as error:
        print(f"REFUSING TO START: {error}", file=sys.stderr, flush=True)
        raise SystemExit(2) from error
    import uvicorn

    print(f"NHM capstone product API {app.version} http://{args.host}:{args.port}", flush=True)
    uvicorn.run(app, host=args.host, port=args.port, log_level=args.log_level)


if __name__ == "__main__":
    main()
