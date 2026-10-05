#!/usr/bin/env python3
"""Documented launcher for the NHM research-software API (V2-REL-001).

    python -m scripts.run_nhm_default        DEFAULT: SOFTWARE_SYSTEM_V2 / MODEL_V2_FINAL
    python -m scripts.run_nhm_default --profile rollback-v1
                                             explicit operator-only V1 rollback

The default profile verifies DEFAULT_RUNTIME_BINDING_V2 fail-closed and serves MODEL_V2_FINAL ->
GATEWAY_ARTIFACT_V2 -> CAL_V2 -> ALERT_POLICY_V1_MODEL_V2_BINDING over API_SCHEMA_V1
(POST /v1/infer-window). The rollback profile verifies ROLLBACK_RUNTIME_BINDING_V1 and serves the
V1 stack. The profile is an operational launch decision only, never an API request parameter.
Research prototype; non-diagnostic; not a clinical or physical-wearable system.
"""

from __future__ import annotations

import argparse

FACTORIES = {"default": "api.app_default:create_default_app",
             "rollback-v1": "api.app_default:create_rollback_v1_app"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--profile", choices=sorted(FACTORIES), default="default")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--log-level", default="warning")
    args = parser.parse_args()
    import uvicorn

    print(f"NHM research runtime profile={args.profile} factory={FACTORIES[args.profile]} "
          f"http://{args.host}:{args.port}", flush=True)
    uvicorn.run(FACTORIES[args.profile], factory=True, host=args.host, port=args.port,
                log_level=args.log_level)


if __name__ == "__main__":
    main()
