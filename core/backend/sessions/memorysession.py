import secrets
import base64
import os
import asyncio

from typing import Dict, Any
from datetime import datetime, timedelta

from settings import settings
from utils.module_loading import import_string


_settings: Dict[str, Any] = getattr(settings, "SESSION_CONFIG_SETTINGS", {}) or {}


class InMemorySessionBeforeStage:
    """
    In-memory session handler for development or lightweight apps.
    Not recommended for multi-worker or distributed environments.
    """

    def __init__(self) -> None:
        self.sessions: Dict[str, Any] = {}
        self.session_lifetime: timedelta = timedelta(
            minutes=_settings.get("session_lifetime", 30)
        )

        # ✅ Ensure secret_key is always a string (safe for encoders)
        raw_key = _settings.get("secret_key")
        if isinstance(raw_key, bytes):
            self.secret_key = base64.urlsafe_b64encode(raw_key).decode("utf-8")
        elif isinstance(raw_key, str):
            self.secret_key = raw_key
        else:
            self.secret_key = base64.urlsafe_b64encode(os.urandom(32)).decode("utf-8")

        self.cookie_name: str = _settings.get("cookie_name", "X-SESSION-ID")
        self.lock = asyncio.Lock()
        self._cleanup_counter = 0  # To avoid frequent cleanups

    async def __call__(self, request: Any) -> Any:
        """
        Middleware entry point.
        Creates or retrieves session and attaches to request.scope.
        """
        async with self.lock:
            session_id = request.cookies.get(self.cookie_name)

            if not session_id or session_id not in self.sessions:
                session_id = self._generate_session_id()
                storage_path = self._get_storage_backend()

                func = import_string(storage_path)
                # ✅ Now safe to pass as string
                self.sessions[session_id] = func(session_id, self.secret_key)
                self.sessions[session_id]._created_at = datetime.now()
                self.sessions[session_id]._updated_at = datetime.now()
            else:
                session = self.sessions[session_id]
                session._updated_at = datetime.now()

            # Attach to request
            request.scope["session"] = self.sessions[session_id]

            # Lazy cleanup every 50 hits
            self._cleanup_counter += 1
            if self._cleanup_counter % 50 == 0:
                self._cleanup_sessions()

    def _get_storage_backend(self) -> str:
        for item in getattr(settings, "STORAGE_BACKEND", []):
            if "sessions" in item and "memory" in item["sessions"]:
                return item["sessions"]["memory"]

        raise ValueError(
            "SESSION_BACKEND not configured properly. "
            "Expected settings.STORAGE_BACKEND with {'sessions': {'memory': '<path>'}}"
        )

    def _generate_session_id(self) -> str:
        """Generate a secure, random session ID."""
        return base64.urlsafe_b64encode(secrets.token_bytes(64)).decode("utf-8")

    def _cleanup_sessions(self) -> None:
        """Remove expired sessions."""
        now = datetime.now()
        expired = [
            sid
            for sid, session in self.sessions.items()
            if getattr(session, "_updated_at", now) + self.session_lifetime < now
        ]
        for sid in expired:
            self.sessions.pop(sid, None)

    def invalidate_session(self, session_id: str) -> None:
        """Manually remove a session."""
        self.sessions.pop(session_id, None)
