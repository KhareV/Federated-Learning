"""DEMO_AUTH_PROVIDER_V1 -- the explicit offline faculty identity.

It exists ONLY when the operator configured BOTH ``NHM_PRODUCT_AUTH_MODE=DEMO`` and the exact
acknowledgement ``NHM_PRODUCT_DEMO_AUTH_ACK`` (enforced by ``product.auth.base.resolve_auth_mode``
before this class is ever built). It is never described as Clerk authentication, stores no password,
token or secret, and its identity is permanently marked ``demo_mode = true`` with a ``demo:``
user id.
The identity never selects a model, calibration, threshold or any scientific configuration.
"""

from __future__ import annotations

from collections.abc import Mapping

from product.auth.base import (
    DEMO_USER_PREFIX,
    AuthConfigError,
    AuthIdentity,
    AuthProviderDescription,
    AuthProviderType,
)

ENV_DEMO_USER_ID = "NHM_PRODUCT_DEMO_USER_ID"
ENV_DEMO_DISPLAY_NAME = "NHM_PRODUCT_DEMO_DISPLAY_NAME"
DEFAULT_DEMO_USER_ID = "demo:faculty"
DEFAULT_DEMO_DISPLAY_NAME = "Faculty Demo User"
DEMO_SESSION_ID = "DEMO_OFFLINE_SESSION"
DEMO_BANNER = "OFFLINE DEMO IDENTITY - not Clerk authentication"


class DemoAuthProvider:
    def __init__(self, user_id: str = DEFAULT_DEMO_USER_ID,
                 display_name: str = DEFAULT_DEMO_DISPLAY_NAME) -> None:
        if not user_id.startswith(DEMO_USER_PREFIX) or len(user_id) <= len(DEMO_USER_PREFIX):
            raise AuthConfigError("DEMO_USER_ID_MUST_USE_THE_DEMO_PREFIX")
        self._user_id, self._display_name = user_id, display_name

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> DemoAuthProvider:
        """Call ONLY after resolve_auth_mode(env) accepted DEMO + the acknowledgement."""
        return cls(env.get(ENV_DEMO_USER_ID, DEFAULT_DEMO_USER_ID),
                   env.get(ENV_DEMO_DISPLAY_NAME, DEFAULT_DEMO_DISPLAY_NAME))

    @property
    def provider_type(self) -> AuthProviderType:
        return AuthProviderType.DEMO

    def describe(self) -> AuthProviderDescription:
        return AuthProviderDescription(provider=AuthProviderType.DEMO, demo_mode=True,
                                       ui_banner=DEMO_BANNER)

    async def authenticate(self, credential: str | None) -> AuthIdentity:
        del credential  # the explicit demo identity does not depend on any credential
        return AuthIdentity(
            user_id=self._user_id, display_name=self._display_name, email=None,
            auth_provider=AuthProviderType.DEMO, auth_session_id=DEMO_SESSION_ID, roles=(),
            demo_mode=True)
