"""CAP003_TEST_IDENTITY_ONLY -- a static engineering identity resolver for tests and the CAP-003
canonical harness. It is NOT an auth provider, is never installed as a product default, and is NOT
the later DemoAuth implementation (CAP-004 owns real providers). It lives under scripts/ on purpose,
never under product/. Ownership checks stay fully active: each test user is a distinct identity.
"""

from __future__ import annotations

from starlette.requests import HTTPConnection

from product.auth.base import AuthIdentity, AuthProviderType

CLASSIFICATION = "CAP003_TEST_IDENTITY_ONLY"
HEADER = "x-cap003-test-user"


async def cap003_test_identity_resolver(connection: HTTPConnection) -> AuthIdentity | None:
    suffix = connection.headers.get(HEADER)
    if not suffix:
        return None
    return AuthIdentity(
        user_id=f"demo:cap003-{suffix}", display_name=CLASSIFICATION,
        auth_provider=AuthProviderType.DEMO, auth_session_id=CLASSIFICATION, demo_mode=True)


def headers_for(suffix: str) -> dict[str, str]:
    return {HEADER: suffix}
