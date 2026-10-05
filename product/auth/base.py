"""CAPSTONE_AUTH_POLICY_V1 -- AuthProvider abstraction (interface only; no Clerk SDK).

Identity never reaches the ML stack: no identity or request field may select a model,
checkpoint, calibration, threshold or alert policy. Demo mode must be explicitly configured,
is never silently activated, is flagged as demo on every identity, and is never described as
Clerk authentication.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, model_validator

from product.contracts import load_contract

ENV_AUTH_MODE = "NHM_PRODUCT_AUTH_MODE"
ENV_DEMO_ACK = "NHM_PRODUCT_DEMO_AUTH_ACK"
DEMO_USER_PREFIX = "demo:"


class AuthProviderType(StrEnum):
    CLERK = "CLERK"
    DEMO = "DEMO"


class AuthConfigError(RuntimeError):
    """Auth mode is unset, invalid, or demo mode lacks its explicit acknowledgement."""


class AuthIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    user_id: str = Field(min_length=1)
    display_name: str | None = None
    email: str | None = None
    auth_provider: AuthProviderType
    auth_session_id: str = Field(min_length=1)
    roles: tuple[str, ...] = ()
    demo_mode: bool

    @model_validator(mode="after")
    def _demo_is_distinct(self) -> AuthIdentity:
        is_demo = self.auth_provider is AuthProviderType.DEMO
        if self.demo_mode != is_demo:
            raise ValueError("DEMO_MODE_FLAG_MUST_MATCH_PROVIDER")
        if is_demo and not self.user_id.startswith(DEMO_USER_PREFIX):
            raise ValueError("DEMO_USER_ID_MUST_USE_DEMO_PREFIX")
        if not is_demo and self.user_id.startswith(DEMO_USER_PREFIX):
            raise ValueError("NON_DEMO_USER_ID_MUST_NOT_USE_DEMO_PREFIX")
        return self


class AuthProviderDescription(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: AuthProviderType
    demo_mode: bool
    ui_banner: str | None = None


@runtime_checkable
class AuthProvider(Protocol):
    @property
    def provider_type(self) -> AuthProviderType: ...

    def describe(self) -> AuthProviderDescription: ...

    async def authenticate(self, credential: str | None) -> AuthIdentity: ...


def resolve_auth_mode(env: Mapping[str, str]) -> AuthProviderType:
    """Mode comes ONLY from explicit configuration; there is no silent default."""
    raw = env.get(ENV_AUTH_MODE)
    if raw is None:
        raise AuthConfigError("AUTH_MODE_NOT_CONFIGURED")
    try:
        mode = AuthProviderType(raw)
    except ValueError as error:
        raise AuthConfigError(f"AUTH_MODE_INVALID:{raw}") from error
    if mode is AuthProviderType.DEMO:
        expected = load_contract("auth_policy")["demo_provider"]["acknowledgement_value"]
        if env.get(ENV_DEMO_ACK) != expected:
            raise AuthConfigError("DEMO_AUTH_REQUIRES_EXPLICIT_ACKNOWLEDGEMENT")
    return mode


def can_access_owned(identity: AuthIdentity, owner_user_id: str) -> bool:
    """A user may access only their own devices, sessions, summaries and timelines."""
    return identity.user_id == owner_user_id
