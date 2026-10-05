"""Production identity resolver for REST and WebSocket (``HTTPConnection``): extracts the
credential,
delegates verification to the configured AuthProvider and returns an AuthIdentity or None. It never
selects a model or any scientific configuration."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from starlette.requests import HTTPConnection

from product.auth.base import AuthIdentity, AuthProvider
from product.auth.errors import AuthenticationFailed

SESSION_COOKIE_PREFIX = "__session"


def extract_credential(connection: HTTPConnection) -> str | None:
    header = connection.headers.get("authorization")
    if header:
        scheme, _, token = header.partition(" ")
        return token.strip() if scheme.lower() == "bearer" and token.strip() else None
    for name, value in connection.cookies.items():  # Clerk's official session-cookie transport
        if name.startswith(SESSION_COOKIE_PREFIX) and value:
            return value
    return None


def make_identity_resolver(
        provider: AuthProvider) -> Callable[[HTTPConnection], Awaitable[AuthIdentity | None]]:
    async def resolve(connection: HTTPConnection) -> AuthIdentity | None:
        try:
            return await provider.authenticate(extract_credential(connection))
        except AuthenticationFailed:
            return None

    return resolve
