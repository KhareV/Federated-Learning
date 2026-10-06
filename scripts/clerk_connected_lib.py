# ruff: noqa: E501
"""CLERK-LIVE-001 pure checks shared by the frozen CLERKG0 evaluator, the targeted tests and the mutation controls.
No network, no Clerk, no scientific calculation. Secrets are only ever compared, never stored."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

JWT = re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.")
SECRET_PREFIX = "sk" + "_test_"            # split so this file never contains the literal prefix as a token
HISTORICAL_RELEASE_TARGET = "3ad1b07408a0c3556fbc5039f1a7a4fee824db96"


def find_secret(root: Path, secret: str, *, suffixes: tuple[str, ...] | None = None) -> list[str]:
    """Relative paths of files containing the EXACT secret value (value itself is never returned)."""
    hits = []
    if not secret:
        return hits
    needle = secret.encode()
    for p in root.rglob("*"):
        if p.is_file() and (suffixes is None or p.suffix in suffixes):
            try:
                if needle in p.read_bytes():
                    hits.append(str(p.relative_to(root)))
            except OSError:
                pass
    return hits


def secret_prefix_hits(root: Path) -> list[str]:
    return find_secret(root, SECRET_PREFIX)


def sqlite_secret_hits(db: Path, secret: str) -> list[str]:
    import sqlite3

    hits = []
    conn = sqlite3.connect(db)
    try:
        for (name,) in conn.execute("select name from sqlite_master where type='table'"):
            blob = repr(conn.execute(f'select * from "{name}"').fetchall())
            if (secret and secret in blob) or SECRET_PREFIX in blob or JWT.search(blob):
                hits.append(name)
    finally:
        conn.close()
    return hits


def frontend_static_audit(root: Path, secret: str = "") -> dict[str, Any]:
    """Frontend source: no secret, no NEXT_PUBLIC read, no committed publishable key, no Vite define of server variables."""
    failures = []
    files = [p for p in (root / "frontend/src").rglob("*") if p.is_file() and p.suffix in {".ts", ".svelte", ".js"} and "__tests__" not in p.parts]
    vite = root / "frontend/vite.config.ts"
    body = "\n".join(p.read_text(errors="ignore") for p in files) + (vite.read_text(errors="ignore") if vite.exists() else "")
    if secret and secret in body:
        failures.append("frontend_source_contains_secret")
    if re.search(r"sk_(test|live)_[A-Za-z0-9]{8,}", body):
        failures.append("frontend_source_contains_secret_shaped_literal")
    if "CLERK_SECRET_KEY" in body:
        failures.append("frontend_references_secret_variable")
    if "NEXT_PUBLIC" in body:
        failures.append("frontend_reads_NEXT_PUBLIC")
    if "VITE_CLERK_PUBLISHABLE_KEY" not in body:
        failures.append("frontend_does_not_read_VITE_variable")
    if re.search(r"pk_(test|live)_[A-Za-z0-9+/=]{20,}", body):
        failures.append("frontend_commits_publishable_key")
    if vite.exists() and "define:" in vite.read_text():
        failures.append("vite_define_present")
    return {"ok": not failures, "failures": failures}


def backend_static_audit(root: Path) -> dict[str, Any]:
    """Backend auth: official SDK only; no custom JWT/JWK/crypto verification and no unverified-claim trust."""
    failures = []
    forbidden = re.compile(r"^\s*(import|from)\s+(jwt|jose|jwcrypto|cryptography|authlib|rsa)\b", re.M)
    for rel in ("product/auth", "api"):
        for p in (root / rel).rglob("*.py"):
            text = p.read_text(errors="ignore")
            if forbidden.search(text):
                failures.append(f"custom_crypto_import:{p.relative_to(root)}")
            if re.search(r"base64\.(urlsafe_)?b64decode\([^)]*split\(['\"]\.['\"]\)", text):
                failures.append(f"manual_jwt_decode:{p.relative_to(root)}")
    clerk = root / "product/auth/clerk.py"
    if "authenticate_request_async" not in clerk.read_text():
        failures.append("official_sdk_not_used")
    return {"ok": not failures, "failures": failures}


def fl_isolation_static(root: Path) -> dict[str, Any]:
    """Monitoring/session/history/auth data must not feed federation: no federation module imports them."""
    failures = []
    banned = re.compile(r"^\s*(from|import)\s+(product\.history|product\.monitoring|capstone_persistence\.session_evidence_store|product\.auth|product\.sessions)\b", re.M)
    for p in (root / "product/federation").rglob("*.py"):
        if banned.search(p.read_text(errors="ignore")):
            failures.append(str(p.relative_to(root)))
    return {"ok": not failures, "failures": failures}


def ws_evidence_ok(w: dict[str, Any] | None, owned_key: str) -> bool:
    return bool(w and w.get("handshakeStatus") == 101 and not w.get("urlHasToken") and w.get("cookieSessionSent") is True and (w.get("framesReceived") or 0) > 0 and w.get(owned_key))


def unauth_ws_rejected(w: dict[str, Any] | None) -> bool:
    return bool(w and w.get("closeCode") == 4401 and (w.get("frames") or 0) == 0)


def ownership_ok(b_rest_ui: list[dict[str, Any]], probes: list[dict[str, Any]], b_ws: dict[str, Any]) -> dict[str, Any]:
    failures = []
    if not any(r.get("target") == "session" and r.get("status") == 403 for r in b_rest_ui):
        failures.append("b_reads_a_session_via_ui")
    for r in probes:
        want = 404 if "nonexistent" in r["label"] else 200 if "global" in r["label"] else 403
        if not r.get("rewritten") or not r.get("app_bearer_kept") or r.get("status") != want:
            failures.append(f"probe:{r['label']}:{r.get('status')}")
    for kind in ("monitoring", "federation"):
        if (b_ws.get(kind) or {}).get("closeCode") != 4403 or (b_ws.get(kind) or {}).get("frames"):
            failures.append(f"b_ws_{kind}")
    return {"ok": not failures, "failures": failures}


def identity_ok(system: dict[str, Any] | None, me: dict[str, Any] | None) -> dict[str, Any]:
    failures = []
    s, m = system or {}, me or {}
    if s.get("auth_provider") != "CLERK" or s.get("demo_mode") is not False:
        failures.append("system_not_clerk")
    if s.get("model_id") != "MODEL_V2_FINAL" or s.get("software_system") != "SOFTWARE_SYSTEM_V2" or s.get("product_api_implementation") != "CAPSTONE_PRODUCT_API_V1_3":
        failures.append("system_runtime_identity")
    if m.get("status") != 200 or m.get("auth_provider") != "CLERK" or m.get("demo_mode") is not False or not m.get("user_id_is_clerk_shaped") or m.get("user_id_is_demo"):
        failures.append("me_not_real_clerk")
    return {"ok": not failures, "failures": failures}


def candidate_ok(models_step: dict[str, Any]) -> dict[str, Any]:
    failures = []
    cands = models_step.get("candidate") or []
    if len(cands) != 1:
        failures.append("candidate_count")
    for c in cands:
        if c.get("production_deployed") is not False or c.get("governance_status") != "ACCEPTED_TO_SANDBOX" or c.get("sandbox_status") != "IN_SANDBOX":
            failures.append("candidate_not_sandbox_only")
    if models_step.get("released_default") != "MODEL_V2_FINAL" or models_step.get("controls"):
        failures.append("released_default_or_controls")
    return {"ok": not failures, "failures": failures}


def noninterference_ok(clerk_models: dict[str, Any], clerk_system: dict[str, Any], demo_candidate_digest: str, demo_runtime: dict[str, Any]) -> dict[str, Any]:
    """Authentication mode changes identity/ownership only: same runtime identity and byte-identical candidate state digest."""
    failures = []
    for key in ("model_id", "software_system", "calibration_id"):
        if key in demo_runtime and key in clerk_system and clerk_system[key] != demo_runtime[key]:
            failures.append(f"runtime_{key}")
    if clerk_system.get("model_id") != "MODEL_V2_FINAL":
        failures.append("model_not_released_default")
    digests = [c.get("state_digest") for c in (clerk_models.get("candidate") or [])]
    if digests != [demo_candidate_digest]:
        failures.append("candidate_state_digest_differs_from_demo")
    return {"ok": not failures, "failures": failures}


def tag_ok(actual_target: str) -> bool:
    return actual_target == HISTORICAL_RELEASE_TARGET


def demo_regression_ok(d: dict[str, Any]) -> dict[str, Any]:
    failures = []
    if not d.get("demo_auth_works"):
        failures.append("demo_auth_broken")
    if d.get("equals_cap_010_canonical_digest") is not True:
        failures.append("demo_semantic_digest_changed")
    if d.get("clerk_global_in_browser") is not False:
        failures.append("clerk_initialised_in_demo")
    if d.get("external_requests") != [] or d.get("blocked_external_requests") != [] or d.get("clerk_origins_contacted") != []:
        failures.append("external_or_clerk_traffic_in_demo")
    return {"ok": not failures, "failures": failures}
