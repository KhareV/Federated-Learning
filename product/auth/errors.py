"""Authentication errors (CAP-004). Messages never contain credentials."""

from __future__ import annotations


class AuthenticationFailed(Exception):
    """The presented credential is missing, invalid or not an accepted session credential."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason
