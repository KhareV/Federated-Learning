"""Auth provider factory. The provider comes ONLY from ``NHM_PRODUCT_AUTH_MODE`` (CLERK | DEMO);
there is no implicit default and no fallback between providers: an unset/invalid mode, a DEMO mode
without the exact acknowledgement, or an incomplete Clerk configuration raises ``AuthConfigError``
and the product refuses to start."""

from __future__ import annotations

from collections.abc import Mapping

from product.auth.base import AuthProvider, AuthProviderType, resolve_auth_mode
from product.auth.clerk import ClerkAuthProvider
from product.auth.demo import DemoAuthProvider


def build_auth_provider(env: Mapping[str, str]) -> AuthProvider:
    mode = resolve_auth_mode(env)  # raises AuthConfigError; never defaults
    if mode is AuthProviderType.DEMO:
        return DemoAuthProvider.from_env(env)
    return ClerkAuthProvider.from_env(env)
