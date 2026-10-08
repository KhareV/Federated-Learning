"""Local additive Observatory product API launcher (same auth/runtime configuration as V1_3)."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Mapping

from api.product_app_observatory_v1 import create_product_app_observatory_v1
from api.product_app_v1_1 import DEFAULT_DEV_ORIGINS, DEFAULT_INFERENCE_URL
from capstone_persistence.store import DEFAULT_DB_PATH, ENV_DB_PATH, CapstoneSqliteStore
from product.auth.base import AuthConfigError
from product.auth.factory import build_auth_provider
from product.auth.resolver import make_identity_resolver
from product.devices.scenarios import TimingMode
from product.federation.artifact_store import DEFAULT_ROOT as FED_ROOT
from product.federation.artifact_store import ENV_ROOT as ENV_FED_ROOT
from product.models.candidate_artifacts import DEFAULT_ROOT as CAND_ROOT
from product.models.candidate_artifacts import ENV_ROOT as ENV_CAND_ROOT
from scripts.run_capstone_product_v1_2 import crash_hook


def build_app_from_env(env: Mapping[str, str]):
    provider = build_auth_provider(env)
    origins = tuple(part.strip() for part in env.get("NHM_PRODUCT_ALLOWED_ORIGINS", "").split(",")
                    if part.strip())
    try:
        mode = TimingMode(env.get("NHM_PRODUCT_TIMING_MODE", TimingMode.ACCELERATED.value))
    except ValueError as error:
        raise AuthConfigError("INVALID_TIMING_MODE") from error
    store = CapstoneSqliteStore(env.get(ENV_DB_PATH, DEFAULT_DB_PATH))
    return create_product_app_observatory_v1(
        store=store, identity_resolver=make_identity_resolver(provider),
        auth_description=provider.describe(),
        inference_base_url=env.get("NHM_PRODUCT_INFERENCE_URL", DEFAULT_INFERENCE_URL),
        allowed_origins=origins or DEFAULT_DEV_ORIGINS, timing_mode=mode,
        federation_artifact_root=env.get(ENV_FED_ROOT, str(FED_ROOT)),
        candidate_root=env.get(ENV_CAND_ROOT, str(CAND_ROOT)),
        checkpoint_hook=crash_hook(env),
        auto_resume=env.get("NHM_FEDERATION_AUTO_RESUME", "1") != "0",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8002)
    args = parser.parse_args()
    try:
        app = build_app_from_env(os.environ)
    except AuthConfigError as error:
        print(f"REFUSING TO START: {error}", file=sys.stderr, flush=True)
        raise SystemExit(2) from error
    import uvicorn

    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
