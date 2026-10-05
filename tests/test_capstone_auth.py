# ruff: noqa: E501
"""CAP-004: authentication providers, factory rules, resolver, and the no-credentials guarantees."""

from __future__ import annotations

import ast
import asyncio
import base64
import json
import time
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from starlette.requests import Request

from product.auth import base as auth_base
from product.auth.base import AuthConfigError, AuthIdentity, AuthProvider, AuthProviderType
from product.auth.clerk import (
    SESSION_TOKEN_ONLY,
    ClerkAuthProvider,
    ClerkConfig,
)
from product.auth.demo import DEMO_BANNER, DemoAuthProvider
from product.auth.errors import AuthenticationFailed
from product.auth.factory import build_auth_provider
from product.auth.resolver import extract_credential, make_identity_resolver
from product.contracts import ROOT, load_contract
from tests.capstone_persistent_support import BASE, make_persistent_app

ACK = load_contract("auth_policy")["demo_provider"]["acknowledgement_value"]
DEMO_ENV = {"NHM_PRODUCT_AUTH_MODE": "DEMO", "NHM_PRODUCT_DEMO_AUTH_ACK": ACK}
PARTY = "http://localhost:5173"


def _keypair() -> tuple[str, str]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                serialization.NoEncryption()).decode()
    public = key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    return private, public


PRIVATE, PUBLIC = _keypair()
OTHER_PRIVATE, _ = _keypair()


def _token(private: str = PRIVATE, **claims) -> str:
    import jwt
    now = int(time.time())
    body = {"sub": "user_2abc", "sid": "sess_2xyz", "azp": PARTY, "iat": now, "nbf": now - 5,
            "exp": now + 300, "iss": "https://example.clerk.accounts.dev", **claims}
    return jwt.encode(body, private, algorithm="RS256")


def _provider(parties: tuple[str, ...] = (PARTY,)) -> ClerkAuthProvider:
    return ClerkAuthProvider(ClerkConfig(authorized_parties=parties, jwt_key=PUBLIC))


def _run(coro):
    return asyncio.run(coro)


# ---- factory: no silent default, exact acknowledgement, no fallback ----------------------------
@pytest.mark.parametrize("env", [{}, {"NHM_PRODUCT_AUTH_MODE": ""},
                                 {"NHM_PRODUCT_AUTH_MODE": "ANONYMOUS"},
                                 {"NHM_PRODUCT_AUTH_MODE": "demo", "NHM_PRODUCT_DEMO_AUTH_ACK": ACK}])
def test_unset_or_invalid_auth_mode_refuses_to_start(env: dict) -> None:
    with pytest.raises(AuthConfigError):
        build_auth_provider(env)


@pytest.mark.parametrize("ack", [None, "", "true", "yes", ACK.lower(), ACK + " ", "I_UNDERSTAND"])
def test_demo_mode_requires_the_exact_acknowledgement(ack) -> None:
    env = {"NHM_PRODUCT_AUTH_MODE": "DEMO"}
    if ack is not None:
        env["NHM_PRODUCT_DEMO_AUTH_ACK"] = ack
    with pytest.raises(AuthConfigError, match="ACKNOWLEDGEMENT"):
        build_auth_provider(env)


def test_explicit_valid_demo_mode_builds_the_demo_provider() -> None:
    provider = build_auth_provider(DEMO_ENV)
    assert isinstance(provider, DemoAuthProvider) and isinstance(provider, AuthProvider)
    assert provider.provider_type is AuthProviderType.DEMO
    assert provider.describe().demo_mode is True and provider.describe().ui_banner == DEMO_BANNER
    assert "not Clerk" in DEMO_BANNER


def test_demo_identity_is_prefixed_flagged_and_credential_free() -> None:
    identity = _run(build_auth_provider(DEMO_ENV).authenticate(None))
    assert identity.user_id == "demo:faculty" and identity.demo_mode is True
    assert identity.auth_provider is AuthProviderType.DEMO and identity.display_name
    same = _run(build_auth_provider(DEMO_ENV).authenticate("whatever-token"))
    assert same == identity  # the explicit demo identity does not depend on any credential
    custom = _run(build_auth_provider({**DEMO_ENV, "NHM_PRODUCT_DEMO_USER_ID": "demo:alice",
                                       "NHM_PRODUCT_DEMO_DISPLAY_NAME": "Alice"}).authenticate(None))
    assert (custom.user_id, custom.display_name) == ("demo:alice", "Alice")
    with pytest.raises(AuthConfigError, match="DEMO_PREFIX"):
        build_auth_provider({**DEMO_ENV, "NHM_PRODUCT_DEMO_USER_ID": "alice"})
    assert not {"password", "token", "secret", "credential"} & set(
        AuthIdentity.model_fields) and "token" not in json.dumps(identity.model_dump())


def test_clerk_mode_with_incomplete_config_fails_and_never_falls_back_to_demo() -> None:
    for env in ({"NHM_PRODUCT_AUTH_MODE": "CLERK"},
                {"NHM_PRODUCT_AUTH_MODE": "CLERK", "CLERK_JWT_KEY": PUBLIC},
                {"NHM_PRODUCT_AUTH_MODE": "CLERK", "NHM_CLERK_AUTHORIZED_PARTIES": PARTY},
                {"NHM_PRODUCT_AUTH_MODE": "CLERK", "CLERK_JWT_KEY": PUBLIC,
                 "NHM_CLERK_AUTHORIZED_PARTIES": "*"},
                # a demo acknowledgement present alongside CLERK must not matter
                {"NHM_PRODUCT_AUTH_MODE": "CLERK", "NHM_PRODUCT_DEMO_AUTH_ACK": ACK}):
        with pytest.raises(AuthConfigError):
            build_auth_provider(env)
    ok = build_auth_provider({"NHM_PRODUCT_AUTH_MODE": "CLERK", "CLERK_JWT_KEY": PUBLIC,
                              "NHM_CLERK_AUTHORIZED_PARTIES": f"{PARTY}, http://127.0.0.1:5173"})
    assert isinstance(ok, ClerkAuthProvider) and not isinstance(ok, DemoAuthProvider)
    assert ok.provider_type is AuthProviderType.CLERK and ok.describe().demo_mode is False


# ---- Clerk: the OFFICIAL SDK verifies; nothing custom ------------------------------------------
def test_clerk_provider_uses_the_official_sdk_function_by_default() -> None:
    import clerk_backend_api.security as sdk
    provider = _provider()
    assert provider._sdk_authenticate is sdk.authenticate_request_async
    assert SESSION_TOKEN_ONLY == ["session_token"]


def test_a_validly_signed_session_token_yields_the_verified_identity() -> None:
    identity = _run(_provider().authenticate(_token(email="x@example.org")))
    assert identity.user_id == "user_2abc" and identity.auth_session_id == "sess_2xyz"
    assert identity.auth_provider is AuthProviderType.CLERK and identity.demo_mode is False
    assert identity.email == "x@example.org"


@pytest.mark.parametrize("make", [
    lambda: _token(exp=int(time.time()) - 3600),  # expired
    lambda: _token(OTHER_PRIVATE),  # signed by a different key
    lambda: _token(azp="https://evil.example"),  # not an authorized party
    lambda: _token(azp=None),  # no azp claim at all
    lambda: "",  # missing
    lambda: "not.a.jwt",
])
def test_invalid_or_unverifiable_credentials_are_rejected(make) -> None:
    with pytest.raises(AuthenticationFailed):
        _run(_provider().authenticate(make()))


def test_unsigned_and_tampered_tokens_are_rejected_not_trusted() -> None:
    header = base64.urlsafe_b64encode(b'{"alg":"none","typ":"JWT"}').rstrip(b"=").decode()
    body = base64.urlsafe_b64encode(json.dumps(
        {"sub": "user_evil", "sid": "s", "azp": PARTY, "exp": int(time.time()) + 300}
    ).encode()).rstrip(b"=").decode()
    with pytest.raises(AuthenticationFailed):
        _run(_provider().authenticate(f"{header}.{body}."))  # alg=none, no signature
    good = _token()
    head, _, sig = good.rpartition(".")
    first, _, _ = head.partition(".")
    forged = base64.urlsafe_b64encode(json.dumps(
        {"sub": "user_admin", "sid": "sess_2xyz", "azp": PARTY,
         "exp": int(time.time()) + 300}).encode()).rstrip(b"=").decode()
    with pytest.raises(AuthenticationFailed):  # decoded payload is edited but the signature is old
        _run(_provider().authenticate(f"{first}.{forged}.{sig}"))


@pytest.mark.parametrize("token", ["ak_live_abcdef", "mt_abcdef", "oat_abcdef", "m2m_abcdef"])
def test_only_session_tokens_are_accepted_machine_and_api_tokens_are_not(token: str) -> None:
    with pytest.raises(AuthenticationFailed):
        _run(_provider().authenticate(token))


def test_the_sdk_boundary_receives_session_only_authorized_parties_and_the_key() -> None:
    seen: dict = {}

    class State:
        is_signed_in = True
        payload = {"sub": "user_abc", "sid": "sess_abc", "role": "member"}  # noqa: RUF012
        reason = None

    async def fake_sdk(request, options):
        seen["options"] = options
        seen["authorization"] = request.headers["Authorization"]
        return State()

    provider = ClerkAuthProvider(
        ClerkConfig(authorized_parties=(PARTY, "http://127.0.0.1:5173"), jwt_key=PUBLIC,
                    secret_key="sk_test_placeholder"), sdk_authenticate=fake_sdk)
    identity = _run(provider.authenticate("TOKEN123"))
    options = seen["options"]
    assert options.accepts_token == ["session_token"]
    assert options.authorized_parties == [PARTY, "http://127.0.0.1:5173"]
    assert options.jwt_key == PUBLIC and options.secret_key == "sk_test_placeholder"
    assert seen["authorization"] == "Bearer TOKEN123"
    assert (identity.user_id, identity.auth_session_id, identity.roles) == (
        "user_abc", "sess_abc", ("member",))


def test_the_sdk_is_not_called_without_a_credential_and_signed_out_is_rejected() -> None:
    calls = []

    class Out:
        is_signed_in = False
        payload = None

        class reason:
            value = ("token-expired", "x")

    async def fake_sdk(request, options):
        calls.append(1)
        return Out()

    provider = ClerkAuthProvider(ClerkConfig(authorized_parties=(PARTY,), jwt_key=PUBLIC),
                                 sdk_authenticate=fake_sdk)
    with pytest.raises(AuthenticationFailed):
        _run(provider.authenticate(None))
    assert calls == []
    with pytest.raises(AuthenticationFailed):
        _run(provider.authenticate("tok"))
    assert calls == [1]


def test_a_clerk_subject_can_never_use_the_demo_prefix_or_miss_its_session() -> None:
    class State:
        is_signed_in = True
        reason = None

        def __init__(self, payload):
            self.payload = payload

    def provider_for(payload):
        async def fake_sdk(request, options):
            return State(payload)
        return ClerkAuthProvider(ClerkConfig(authorized_parties=(PARTY,), jwt_key=PUBLIC),
                                 sdk_authenticate=fake_sdk)

    for payload in ({"sub": "demo:evil", "sid": "s"}, {"sub": "user_a"}, {"sid": "s"},
                    {"sub": "", "sid": "s"}):
        with pytest.raises(AuthenticationFailed):
            _run(provider_for(payload).authenticate("tok"))


def test_there_is_no_custom_jwt_or_crypto_code_in_the_auth_package() -> None:
    banned_imports = {"jwt", "jose", "hmac", "hashlib", "base64", "cryptography", "rsa", "jwcrypto"}
    for path in (ROOT / "product/auth").rglob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            names = set()
            if isinstance(node, ast.ImportFrom):
                names = {(node.module or "").split(".")[0]}
            elif isinstance(node, ast.Import):
                names = {a.name.split(".")[0] for a in node.names}
            assert not names & banned_imports, (path, names & banned_imports)
        text = path.read_text()
        for token in ("jwt.decode", "b64decode", "verify_signature", "algorithms="):
            assert token not in text, (path, token)
    clerk = (ROOT / "product/auth/clerk.py").read_text()
    assert "from clerk_backend_api.security import" in clerk
    assert "authenticate_request_async" in clerk


# ---- resolver (REST + WebSocket) ---------------------------------------------------------------
def _request(headers: dict[str, str]) -> Request:
    scope = {"type": "http", "headers": [(k.lower().encode(), v.encode())
                                         for k, v in headers.items()], "method": "GET",
             "path": "/", "query_string": b""}
    return Request(scope)


def test_credential_extraction_supports_bearer_and_the_clerk_session_cookie() -> None:
    assert extract_credential(_request({"Authorization": "Bearer abc"})) == "abc"
    assert extract_credential(_request({"Authorization": "bearer abc"})) == "abc"
    assert extract_credential(_request({"Authorization": "Basic abc"})) is None
    assert extract_credential(_request({"Cookie": "__session=cookie-token; other=1"})) == (
        "cookie-token")
    assert extract_credential(_request({"Cookie": "other=1"})) is None
    assert extract_credential(_request({})) is None


def test_the_resolver_returns_none_on_failure_and_never_substitutes_an_identity() -> None:
    resolver = make_identity_resolver(_provider())
    assert _run(resolver(_request({}))) is None
    assert _run(resolver(_request({"Authorization": "Bearer garbage"}))) is None
    assert _run(resolver(_request({"Authorization": f"Bearer {_token(OTHER_PRIVATE)}"}))) is None
    good = _run(resolver(_request({"Authorization": f"Bearer {_token()}"})))
    assert good is not None and good.user_id == "user_2abc"
    cookie = _run(resolver(_request({"Cookie": f"__session={_token()}"})))
    assert cookie is not None and cookie.user_id == "user_2abc"


def test_a_clerk_app_rejects_bad_tokens_over_rest_and_websocket_without_any_fallback(
        tmp_path) -> None:
    from starlette.websockets import WebSocketDisconnect
    resolver = make_identity_resolver(_provider())
    app, _ = make_persistent_app(tmp_path / "c.sqlite3", resolver=resolver)
    with TestClient(app) as client:
        assert client.get(f"{BASE}/me").status_code == 401
        assert client.get(f"{BASE}/me", headers={"Authorization": "Bearer nope"}).status_code == 401
        ok = client.get(f"{BASE}/me", headers={"Authorization": f"Bearer {_token()}"})
        assert ok.status_code == 200 and ok.json()["auth_provider"] == "CLERK"
        assert ok.json()["demo_mode"] is False and not ok.json()["user_id"].startswith("demo:")
        with client.websocket_connect(f"{BASE}/sessions/S/live") as ws, pytest.raises(
                WebSocketDisconnect) as excinfo:
            ws.receive_json()
        assert excinfo.value.code == 4401


# ---- identity never reaches the scientific stack -----------------------------------------------
def test_identity_fields_cannot_select_any_model_or_scientific_configuration() -> None:
    selectors = set(load_contract("product_api")["forbidden_request_field_names"]) | {
        "algorithm", "fl_algorithm", "candidate_id", "gateway", "preprocess"}
    assert not selectors & set(AuthIdentity.model_fields)
    assert load_contract("auth_policy")["ml_independence"]["identity_affects_ml"] is False
    code = []
    for path in (ROOT / "product/auth").rglob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Name | ast.Attribute | ast.arg | ast.alias):
                code.append(ast.unparse(node))
    joined = " ".join(code)  # identifiers only: docstrings may legitimately say "never selects X"
    for token in ("MODEL_V2", "CAL_V2", "threshold", "checkpoint", "gateway"):
        assert token not in joined, token


def test_no_credential_is_ever_written_to_the_database(tmp_path) -> None:
    secret = "SUPER-SECRET-TOKEN-VALUE-123"

    class Provider:
        provider_type = AuthProviderType.CLERK

        async def authenticate(self, credential):
            if credential != secret:
                raise AuthenticationFailed("BAD")
            return AuthIdentity(user_id="user_1", display_name="N", email="n@x.org",
                                auth_provider=AuthProviderType.CLERK, auth_session_id="sid_1",
                                roles=(), demo_mode=False)

    app, store = make_persistent_app(tmp_path / "s.sqlite3",
                                     resolver=make_identity_resolver(Provider()))
    with TestClient(app) as client:
        headers = {"Authorization": f"Bearer {secret}", "Cookie": f"__session={secret}"}
        assert client.get(f"{BASE}/me", headers=headers).status_code == 200
        client.post(f"{BASE}/devices/simulated", json={}, headers=headers)
    dump = "\n".join(store._connection.iterdump())
    assert secret not in dump and "Bearer" not in dump
    user = store.get_user("user_1")
    assert set(user) == {"user_id", "auth_provider", "display_name", "email", "demo_mode",
                         "created_at_us"}
    assert user["auth_provider"] == "CLERK" and user["demo_mode"] == 0


def test_the_environment_example_contains_names_only() -> None:
    text = (ROOT / ".env.example").read_text()
    assigned = [line for line in text.splitlines() if "=" in line and not line.startswith("#")]
    assert assigned and all(line.split("=", 1)[1] == "" for line in assigned)
    assert "CLERK_SECRET_KEY" in text and "NHM_PRODUCT_AUTH_MODE" in text
    gitignore = (ROOT / ".gitignore").read_text()
    assert ".env" in gitignore and "!.env.example" in gitignore
    assert auth_base.ENV_AUTH_MODE == "NHM_PRODUCT_AUTH_MODE"
    assert Path(ROOT / "product/auth/clerk.py").read_text().count("sk_") == 0
