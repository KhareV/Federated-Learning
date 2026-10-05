"""SOFTWARE_SYSTEM_V2 default research-software runtime (V2-REL-001): thin ADDITIVE wrapper.

* `create_default_app()`  -> MODEL_V2_FINAL -> GATEWAY_ARTIFACT_V2 -> CAL_V2 ->
  ALERT_POLICY_V1_MODEL_V2_BINDING -> API_SCHEMA_V1 (the DEFAULT launch path).
* `create_rollback_v1_app()` -> the V1 stack (MODEL_V1 / GATEWAY_ARTIFACT_V1 / CAL_V1 /
  ALERT_POLICY_V1), an explicit OPERATOR-ONLY launch profile. Never a request parameter.

Both factories first verify a frozen binding lock FAIL-CLOSED (every bound file hash, the exact
stack identity, no mixed V1/V2 combination, no public model selector). The default factory reuses
api.app_v2.create_research_app / api.runtime_v2.ResearchRuntimeV2 unchanged (API_RUNTIME_V2_1 is
not mutated). This module does NOT import api.app at import time (api.app instantiates the V1
runtime on import), never imports SimulationTruth and exposes no model selector. API_SCHEMA_V1,
POST /v1/infer-window and the 400/422/500 semantics are unchanged.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.routing import APIRoute

from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOCK = "artifacts/DEFAULT_RUNTIME_BINDING_V2.lock.json"
ROLLBACK_LOCK = "artifacts/ROLLBACK_RUNTIME_BINDING_V1.lock.json"
ROUTE_PATH = "/v1/infer-window"
DOC_ROUTES = {"/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"}

STACKS: dict[str, dict[str, str]] = {
    "default": {"model_id": "MODEL_V2_FINAL", "gateway_artifact_id": "GATEWAY_ARTIFACT_V2",
                "calibration_id": "CAL_V2",
                "alert_policy_binding_id": "ALERT_POLICY_V1_MODEL_V2_BINDING",
                "alert_policy_id": "ALERT_POLICY_V1", "preprocess_id": "PREPROC_V1",
                "api_contract_version": "API_SCHEMA_V1"},
    "rollback": {"model_id": "MODEL_V1", "gateway_artifact_id": "GATEWAY_ARTIFACT_V1",
                 "calibration_id": "CAL_V1", "alert_policy_binding_id": "ALERT_POLICY_V1",
                 "alert_policy_id": "ALERT_POLICY_V1", "preprocess_id": "PREPROC_V1",
                 "api_contract_version": "API_SCHEMA_V1"},
}


class DefaultBindingError(RuntimeError):
    """Raised (fail closed) when a binding lock, a bound file or the stack identity is wrong."""


def assert_stack_identity(profile: str, identity: dict[str, Any]) -> None:
    """Exact-stack check; any V1/V2 mixture (e.g. MODEL_V2 + CAL_V1) is rejected."""
    expected = STACKS[profile]
    for key, value in expected.items():
        if identity.get(key) != value:
            raise DefaultBindingError(
                f"DEFAULT_BINDING_STACK_MISMATCH:{profile}:{key}:{identity.get(key)!r}")
    other = STACKS["rollback" if profile == "default" else "default"]
    mixed = [k for k in ("model_id", "gateway_artifact_id", "calibration_id")
             if identity.get(k) == other[k]]
    if mixed:
        raise DefaultBindingError(f"DEFAULT_BINDING_MIXED_STACK:{mixed}")


def assert_no_public_selector(app: FastAPI) -> None:
    """The only application route is POST /v1/infer-window with a BODY-only signature."""
    for route in app.routes:
        if not isinstance(route, APIRoute):
            if getattr(route, "path", None) not in DOC_ROUTES:
                raise DefaultBindingError(f"DEFAULT_BINDING_UNEXPECTED_ROUTE:{route.path}")
            continue
        if route.path != ROUTE_PATH or set(route.methods) != {"POST"}:
            raise DefaultBindingError(f"DEFAULT_BINDING_UNEXPECTED_ROUTE:{route.path}")
        dependant = route.dependant
        if dependant.query_params or dependant.path_params or dependant.header_params \
                or dependant.cookie_params:
            raise DefaultBindingError("DEFAULT_BINDING_PUBLIC_SELECTOR_PARAMETER")


def verify_binding(root: Path, lock_relative: str, profile: str) -> dict[str, Any]:
    path = root / lock_relative
    if not path.exists():
        raise DefaultBindingError(f"DEFAULT_BINDING_LOCK_MISSING:{lock_relative}")
    lock = json.loads(path.read_text(encoding="utf-8"))
    expected_id = ("DEFAULT_RUNTIME_BINDING_V2" if profile == "default"
                   else "ROLLBACK_RUNTIME_BINDING_V1")
    if lock.get("lock_id") != expected_id:
        raise DefaultBindingError("DEFAULT_BINDING_WRONG_LOCK_ID")
    if lock.get("public_model_selector") is not False:
        raise DefaultBindingError("DEFAULT_BINDING_PUBLIC_SELECTOR_CLAIM")
    for relative, digest in lock["bound_artifacts"].items():
        target = root / relative
        if not target.exists():
            raise DefaultBindingError(f"DEFAULT_BINDING_MISSING:{relative}")
        if hash_file(target) != digest:
            raise DefaultBindingError(f"DEFAULT_BINDING_TAMPER:{relative}")
    assert_stack_identity(profile, lock["identity"])
    return lock


def _live_identity_default(runtime: Any, root: Path) -> dict[str, Any]:
    from deployment.gateway_v2 import ARTIFACT_ID

    cal = json.loads((root / "artifacts/CAL_V2.json").read_text(encoding="utf-8"))
    binding = json.loads(
        (root / "artifacts/ALERT_POLICY_V1_MODEL_V2_BINDING.lock.json").read_text())
    return {"model_id": runtime.bound_model_id, "gateway_artifact_id": ARTIFACT_ID,
            "calibration_id": runtime.policy.calibration_id,
            "alert_policy_binding_id": binding["lock_id"],
            "alert_policy_id": runtime.policy.policy_id,
            "preprocess_id": runtime.preprocess_id, "api_contract_version": "API_SCHEMA_V1",
            "threshold": runtime.policy.threshold, "cal_threshold": cal["threshold"],
            "policy_model_id": runtime.policy.model_id}


def create_default_app(root: Path = ROOT) -> FastAPI:
    """uvicorn factory: `uvicorn --factory api.app_default:create_default_app`. Nothing is built
    at import time."""
    lock = verify_binding(root, DEFAULT_LOCK, "default")
    from api.app_v2 import create_research_app
    from api.runtime_v2 import ResearchRuntimeV2

    runtime = ResearchRuntimeV2(root)
    live = _live_identity_default(runtime, root)
    assert_stack_identity("default", live)
    if live["policy_model_id"] != "MODEL_V2_FINAL" or live["threshold"] != live["cal_threshold"] \
            or live["threshold"] != lock["identity_values"]["threshold"]:
        raise DefaultBindingError("DEFAULT_BINDING_POLICY_MISBOUND")
    if runtime.gateway.artifact_sha != lock["identity_values"]["gateway_artifact_sha256"]:
        raise DefaultBindingError("DEFAULT_BINDING_GATEWAY_SHA_MISMATCH")
    app = create_research_app(runtime=runtime)
    app.title = "NHM Research Runtime API (SOFTWARE_SYSTEM_V2 default binding)"
    app.description = (
        "Research-prototype-only typed inference API for AAMI_SVF_WINDOW_V1 observed ECG windows, "
        "bound to the DEFAULT_RUNTIME_BINDING_V2 research-software default (MODEL_V2_FINAL, "
        "GATEWAY_ARTIFACT_V2, source-domain CAL_V2). Never a diagnosis; non-clinical.")
    app.state.default_binding_id = lock["lock_id"]
    app.state.profile = "default"
    assert_no_public_selector(app)
    return app


def create_rollback_v1_app(root: Path = ROOT) -> FastAPI:
    """Operator-only V1 rollback: `uvicorn --factory api.app_default:create_rollback_v1_app`."""
    lock = verify_binding(root, ROLLBACK_LOCK, "rollback")
    import api.app as v1_module  # imported only in the explicit rollback process

    app = v1_module.app
    runtime = app.state.runtime
    live = {"model_id": runtime.policy.model_id, "gateway_artifact_id": "GATEWAY_ARTIFACT_V1",
            "calibration_id": runtime.policy.calibration_id,
            "alert_policy_binding_id": runtime.policy.policy_id,
            "alert_policy_id": runtime.policy.policy_id, "preprocess_id": runtime.preprocess_id,
            "api_contract_version": "API_SCHEMA_V1"}
    assert_stack_identity("rollback", live)
    if runtime.gateway.artifact_sha != lock["identity_values"]["gateway_artifact_sha256"]:
        raise DefaultBindingError("ROLLBACK_BINDING_GATEWAY_SHA_MISMATCH")
    app.state.default_binding_id = lock["lock_id"]
    app.state.profile = "rollback-v1"
    assert_no_public_selector(app)
    return app
