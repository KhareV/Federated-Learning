# ruff: noqa: E501
"""Launcher for the CAP-007 product API (CAPSTONE_PRODUCT_API_V1_2).

    NHM_PRODUCT_AUTH_MODE=DEMO NHM_PRODUCT_DEMO_AUTH_ACK=I_UNDERSTAND_THIS_IS_NOT_CLERK \
      PYTHONPATH=src:. python -m scripts.run_capstone_product_v1_2 --port 8002

Same environment as ``scripts.run_capstone_product`` plus: NHM_FEDERATION_ARTIFACT_ROOT (default
data/capstone/federation), NHM_FL_CANDIDATE_ROOT (default data/capstone/fl_candidates),
NHM_FEDERATION_AUTO_RESUME (default 1). TEST-ONLY crash injection for the restart/resume evidence:
NHM_FEDERATION_CRASH_AFTER_ROUND=<n> is honoured ONLY together with
NHM_FEDERATION_FAULT_INJECTION_ACK=TEST_ONLY_NOT_FOR_PRODUCTION and exits the process hard (os._exit)
right after that round's checkpoint is durable.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Mapping

from api.product_app_v1_1 import DEFAULT_DEV_ORIGINS, DEFAULT_INFERENCE_URL
from api.product_app_v1_2 import create_product_app_v1_2
from capstone_persistence.store import DEFAULT_DB_PATH, ENV_DB_PATH, CapstoneSqliteStore
from product.auth.base import AuthConfigError
from product.auth.factory import build_auth_provider
from product.auth.resolver import make_identity_resolver
from product.devices.scenarios import TimingMode
from product.federation.artifact_store import DEFAULT_ROOT as FED_ROOT
from product.federation.artifact_store import ENV_ROOT as ENV_FED_ROOT
from product.models.candidate_artifacts import DEFAULT_ROOT as CAND_ROOT
from product.models.candidate_artifacts import ENV_ROOT as ENV_CAND_ROOT

ENV_INFERENCE_URL = "NHM_PRODUCT_INFERENCE_URL"
ENV_ALLOWED_ORIGINS = "NHM_PRODUCT_ALLOWED_ORIGINS"
ENV_TIMING_MODE = "NHM_PRODUCT_TIMING_MODE"
ENV_AUTO_RESUME = "NHM_FEDERATION_AUTO_RESUME"
ENV_CRASH_AFTER = "NHM_FEDERATION_CRASH_AFTER_ROUND"
ENV_FAULT_ACK = "NHM_FEDERATION_FAULT_INJECTION_ACK"
FAULT_ACK = "TEST_ONLY_NOT_FOR_PRODUCTION"


def crash_hook(env: Mapping[str, str]):
    if ENV_CRASH_AFTER not in env:
        return None
    if env.get(ENV_FAULT_ACK) != FAULT_ACK:
        raise AuthConfigError("FAULT_INJECTION_REQUIRES_THE_TEST_ONLY_ACKNOWLEDGEMENT")
    after = int(env[ENV_CRASH_AFTER])

    def hook(run_id: str, round_id: int) -> None:
        if round_id == after:
            print(f"FAULT INJECTION: exiting after round {round_id} of {run_id}", flush=True)
            os._exit(86)
    return hook


def build_app_from_env(env: Mapping[str, str]):
    provider = build_auth_provider(env)
    origins = tuple(o.strip() for o in env.get(ENV_ALLOWED_ORIGINS, "").split(",") if o.strip())
    try:
        mode = TimingMode(env.get(ENV_TIMING_MODE, TimingMode.ACCELERATED.value))
    except ValueError as error:
        raise AuthConfigError(f"INVALID_TIMING_MODE:{env.get(ENV_TIMING_MODE)}") from error
    store = CapstoneSqliteStore(env.get(ENV_DB_PATH, DEFAULT_DB_PATH))
    return create_product_app_v1_2(
        store=store, identity_resolver=make_identity_resolver(provider),
        auth_description=provider.describe(),
        inference_base_url=env.get(ENV_INFERENCE_URL, DEFAULT_INFERENCE_URL),
        allowed_origins=origins or DEFAULT_DEV_ORIGINS, timing_mode=mode,
        federation_artifact_root=env.get(ENV_FED_ROOT, str(FED_ROOT)),
        candidate_root=env.get(ENV_CAND_ROOT, str(CAND_ROOT)),
        checkpoint_hook=crash_hook(env), auto_resume=env.get(ENV_AUTO_RESUME, "1") != "0")


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
