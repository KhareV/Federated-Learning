"""CLERK_AUTH_PROVIDER_V1 -- Clerk session authentication through the OFFICIAL Python backend SDK.

No cryptography or JWT parsing is implemented here. The credential is handed to
``clerk_backend_api.security.authenticate_request_async``, which verifies the signature (networkless
with ``CLERK_JWT_KEY`` when configured, else via the secret key), expiry and authorized parties. The
provider accepts ONLY Clerk session tokens (``accepts_token=['session_token']``): API keys, M2M and
OAuth access tokens are refused as user sessions. The identity is built exclusively from the
VERIFIED claims (``sub`` -> user_id, ``sid`` -> auth_session_id); a decoded-but-unverified
payload is never trusted. Clerk failures never fall back to any other provider. No secret is
stored or logged.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any

from clerk_backend_api.security import AuthenticateRequestOptions, authenticate_request_async
from pydantic import ValidationError

from product.auth.base import (
    AuthConfigError,
    AuthIdentity,
    AuthProviderDescription,
    AuthProviderType,
)
from product.auth.errors import AuthenticationFailed

ENV_SECRET_KEY = "CLERK_SECRET_KEY"
ENV_JWT_KEY = "CLERK_JWT_KEY"
ENV_PUBLISHABLE_KEY = "CLERK_PUBLISHABLE_KEY"
ENV_AUTHORIZED_PARTIES = "NHM_CLERK_AUTHORIZED_PARTIES"
SESSION_TOKEN_ONLY = ["session_token"]

SdkAuthenticate = Callable[[Any, AuthenticateRequestOptions], Awaitable[Any]]


@dataclass(frozen=True)
class ClerkConfig:
    authorized_parties: tuple[str, ...]
    secret_key: str | None = None
    jwt_key: str | None = None
    publishable_key: str | None = None

    def __post_init__(self) -> None:
        if not self.secret_key and not self.jwt_key:
            raise AuthConfigError("CLERK_REQUIRES_CLERK_JWT_KEY_OR_CLERK_SECRET_KEY")
        if not self.authorized_parties:
            raise AuthConfigError("CLERK_REQUIRES_NHM_CLERK_AUTHORIZED_PARTIES")
        if any(party in ("*", "") for party in self.authorized_parties):
            raise AuthConfigError("CLERK_AUTHORIZED_PARTIES_MUST_BE_EXPLICIT_ORIGINS")

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> ClerkConfig:
        parties = tuple(p.strip() for p in env.get(ENV_AUTHORIZED_PARTIES, "").split(",")
                        if p.strip())
        return cls(authorized_parties=parties, secret_key=env.get(ENV_SECRET_KEY) or None,
                   jwt_key=env.get(ENV_JWT_KEY) or None,
                   publishable_key=env.get(ENV_PUBLISHABLE_KEY) or None)


class _BearerRequest:
    """The minimal ``Requestish`` the SDK needs: a headers mapping."""

    def __init__(self, token: str) -> None:
        self.headers = {"Authorization": f"Bearer {token}"}


class ClerkAuthProvider:
    def __init__(self, config: ClerkConfig, *,
                 sdk_authenticate: SdkAuthenticate = authenticate_request_async) -> None:
        self._config = config
        self._sdk_authenticate = sdk_authenticate  # the official SDK is the default boundary

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> ClerkAuthProvider:
        return cls(ClerkConfig.from_env(env))

    @property
    def provider_type(self) -> AuthProviderType:
        return AuthProviderType.CLERK

    def describe(self) -> AuthProviderDescription:
        return AuthProviderDescription(provider=AuthProviderType.CLERK, demo_mode=False,
                                       ui_banner=None)

    def _options(self) -> AuthenticateRequestOptions:
        return AuthenticateRequestOptions(
            secret_key=self._config.secret_key, jwt_key=self._config.jwt_key,
            authorized_parties=list(self._config.authorized_parties),
            accepts_token=list(SESSION_TOKEN_ONLY))

    async def authenticate(self, credential: str | None) -> AuthIdentity:
        if not credential:
            raise AuthenticationFailed("MISSING_CREDENTIAL")
        state = await self._sdk_authenticate(_BearerRequest(credential), self._options())
        if not getattr(state, "is_signed_in", False) or not isinstance(
                getattr(state, "payload", None), dict):
            reason = getattr(getattr(state, "reason", None), "value", None)
            raise AuthenticationFailed(f"NOT_SIGNED_IN:{reason}")
        claims = state.payload
        subject, session = claims.get("sub"), claims.get("sid")
        if not (isinstance(subject, str) and subject and isinstance(session, str) and session):
            raise AuthenticationFailed("VERIFIED_CLAIMS_LACK_SUBJECT_OR_SESSION")
        role = claims.get("role")
        email = claims.get("email")
        try:
            return AuthIdentity(
                user_id=subject, display_name=None,
                email=email if isinstance(email, str) else None,
                auth_provider=AuthProviderType.CLERK, auth_session_id=session,
                roles=(role,) if isinstance(role, str) and role else (), demo_mode=False)
        except ValidationError as error:
            raise AuthenticationFailed("IDENTITY_REJECTED_BY_THE_AUTH_CONTRACT") from error
