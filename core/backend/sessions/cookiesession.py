import secrets
import base64

from typing import Dict, Any, Optional
from datetime import datetime, timedelta

from core import signing
from wrappers.request import Request
from wrappers.response import Response
from utils.module_loading import import_string
from settings import settings


_settings: Dict[str, Any] = settings.SESSION_CONFIG_SETTINGS or {}


class BeforeSessionStage:
    def __init__(self) -> None:
        self.sessions: Dict[str, Any] = {}
        self.serializer = signing
        self.session_lifetime: timedelta = timedelta(
            minutes=_settings.get('session_lifetime', 30)
        )
        self.cookie_name: str = _settings.get('cookie_name', 'sessionid')

    async def __call__(self, request: Request) -> Any:
        # Load or create session
        session_id = self._get_session_id(request.cookies.get(self.cookie_name))
        if session_id is None:
            session_id = self._generate_session_id()

        # Locate storage backend
        storage = None
        for item in getattr(settings, 'STORAGE_BACKEND', []):
            if "sessions" in item and "cookie" in item["sessions"]:
                storage = item["sessions"]["cookie"]
                break

        if not storage:
            raise ValueError(
                "SESSION_BACKEND not configured correctly! "
                "Expected settings.STORAGE_BACKEND with 'sessions' -> 'cookie'."
            )

        func = import_string(storage)
        request.scope['session'] = self.sessions.setdefault(session_id, func(session_id))

        # Housekeeping
        self._cleanup_sessions()
        await self._regenerate_expired_session(request)

    def _generate_session_id(self) -> str:
        return base64.urlsafe_b64encode(secrets.token_bytes(64)).decode('utf-8')

    def _get_session_id(self, signed_session_id: Optional[str]) -> Optional[str]:
        if not signed_session_id:
            return None
        try:
            return self.serializer.loads(
                signed_session_id,
                settings.SECRET_KEY,
                max_age=_settings.get('max_age', 86400),  # default 1 day
            )
        except signing.BadSignature:
            return None

    def _cleanup_sessions(self) -> None:
        now = datetime.now()
        expired_sessions = [
            sid for sid, session in self.sessions.items()
            if hasattr(session, "_created_at") and (now - session._created_at > self.session_lifetime)
        ]
        for sid in expired_sessions:
            self.sessions.pop(sid, None)

    async def _regenerate_expired_session(self, request: Request) -> None:
        signed_session_id = request.cookies.get('expired_session')
        if not signed_session_id:
            return
        session_id = self._get_session_id(signed_session_id)
        if session_id and session_id in self.sessions:
            old_session = self.sessions.pop(session_id)
            self.sessions[old_session._session_id] = old_session

    def update_cookie_name(self, cookie_name: str) -> None:
        self.cookie_name = cookie_name


class AfterSessionStage:
    def __init__(self, sessions: Optional[Dict[str, Any]] = None) -> None:
        self.serializer = signing
        self.sessions = sessions or {}
        self.max_age: int = _settings.get('max_age', 86400)
        self.secure: bool = _settings.get('secure', False)
        self.httponly: bool = _settings.get('httponly', True)
        self.samesite: str = _settings.get('samesite', 'Lax')
        self.cookie_name: str = _settings.get('cookie_name', 'sessionid')
        self.domain: Optional[str] = getattr(settings, 'SESSION_COOKIE_DOMAIN', None)

    async def __call__(self, request: Request, response: Response) -> Any:
        session = request.scope.get('session')
        if session and hasattr(session, '_session_id'):
            await self._set_cookie(response, session._session_id)
            await self._regenerate_expired_session(request, response)
        return response

    async def _set_cookie(self, response: Response, session_id: str) -> None:
        signed_session_id = self.serializer.dumps(session_id, settings.SECRET_KEY)
        await response.set_cookie(
            self.cookie_name,
            signed_session_id,
            max_age=self.max_age,
            secure=self.secure,
            httponly=self.httponly,
            samesite=self.samesite,
            domain=self.domain,
        )

    async def _regenerate_expired_session(self, request: Request, response: Response) -> None:
        signed_session_id = request.cookies.get('expired_session')
        if not signed_session_id:
            return
        session_id = self._get_session_id(signed_session_id)
        if session_id and session_id in self.sessions:
            old_session = self.sessions.pop(session_id)
            self.sessions[old_session._session_id] = old_session
            await response.set_cookie('expired_session', '', max_age=0)
            await self._set_cookie(response, old_session._session_id)

    def _get_session_id(self, signed_session_id: Optional[str]) -> Optional[str]:
        if not signed_session_id:
            return None
        try:
            return self.serializer.loads(
                signed_session_id,
                settings.SECRET_KEY,
                max_age=self.max_age,
            )
        except signing.BadSignature:
            return None
