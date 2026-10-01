"""Process-local, in-memory session state for stateful ALERT_POLICY_V1 behavior.

Each `session_id` gets its own `AlertEpisodeManager` and its own lock; same-session requests
serialize around that lock, different sessions never contend with each other. This is a
research-runtime limitation, documented rather than hidden: state is process-local only (no
database, no distributed/multi-worker consistency), and a process restart resets every
session's episode state -- there is no durable-session or cross-restart continuity claim.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field

from fusion.episode_manager import AlertEpisodeManager, AlertPolicy


@dataclass
class SessionState:
    episode_manager: AlertEpisodeManager
    lock: threading.Lock = field(default_factory=threading.Lock)
    last_accepted_timestamp_us: int | None = None


class SessionRuntimeStore:
    """Keyed exactly by session_id. No cross-session counter leakage: each session's
    `AlertEpisodeManager` is a wholly separate instance."""

    def __init__(self, policy: AlertPolicy) -> None:
        self._policy = policy
        self._sessions: dict[str, SessionState] = {}
        self._directory_lock = threading.Lock()

    def get_or_create(self, session_id: str) -> SessionState:
        with self._directory_lock:
            state = self._sessions.get(session_id)
            if state is None:
                state = SessionState(episode_manager=AlertEpisodeManager(self._policy))
                self._sessions[session_id] = state
            return state

    def reset(self, session_id: str) -> None:
        """Internal-only (no public HTTP endpoint in T032): drop a session's state so its
        next request starts a fresh episode-manager instance."""
        with self._directory_lock:
            self._sessions.pop(session_id, None)

    def session_count(self) -> int:
        with self._directory_lock:
            return len(self._sessions)
