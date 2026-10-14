"""Verified identity for browser live streams without credentials in WebSocket URLs."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from starlette.requests import HTTPConnection
from starlette.websockets import WebSocket

from product.auth.base import AuthIdentity

AUTH_SUBPROTOCOL = "nhm-auth-v1"
IdentityResolver = Callable[[HTTPConnection], Awaitable[AuthIdentity | None]]


async def authenticate_live_websocket(
        websocket: WebSocket, resolver: IdentityResolver) -> AuthIdentity | None:
    """Prefer a verified first-frame Bearer token; retain cookie auth for older clients.

    Browser WebSockets cannot set Authorization. The subprotocol is only a marker, not
    a credential; the token is sent in a frame and never placed in a URL or protocol.
    """
    frame_auth = AUTH_SUBPROTOCOL in websocket.scope.get("subprotocols", ())
    await websocket.accept(subprotocol=AUTH_SUBPROTOCOL if frame_auth else None)
    if not frame_auth:
        return await resolver(websocket)
    try:
        frame = await asyncio.wait_for(websocket.receive_json(), timeout=10.0)
    except (TimeoutError, ValueError):
        return None
    token = (frame.get("token") if isinstance(frame, dict)
             and frame.get("type") == "authenticate" else None)
    if not isinstance(token, str) or not token or len(token) > 8192 or not token.isascii():
        return None
    scope = dict(websocket.scope)
    scope["headers"] = [(name, value) for name, value in scope["headers"]
                        if name.lower() != b"authorization"] + [
                            (b"authorization", f"Bearer {token}".encode("ascii"))]
    return await resolver(HTTPConnection(scope))
