from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from functools import cached_property
from typing import Dict, Optional, Pattern, Tuple


@dataclass(frozen=True)
class UserAgentInfo:
    browser: str
    browser_version: str
    engine: str
    os: str
    os_version: str
    device: str
    is_mobile: bool
    is_bot: bool

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


class UserAgentParser:
    """
    Small, fast, production-ready User-Agent parser focused on the fields
    commonly needed by analytics and routing logic.

    Usage:
        parser = UserAgentParser(ua_string)
        info = parser.parse()            # returns UserAgentInfo (cached)
        info_dict = parser.to_dict()
    """

    # Precompiled browser patterns ordered by detection priority
    _BROWSER_PATTERNS: Dict[str, Pattern] = {
        "Edge": re.compile(r"(?:Edg|Edge)\/(?P<ver>[\d.]+)"),
        "Chrome": re.compile(r"Chrome\/(?P<ver>[\d.]+)"),
        "Firefox": re.compile(r"Firefox\/(?P<ver>[\d.]+)"),
        "Safari": re.compile(r"Version\/(?P<ver>[\d.]+).*Safari"),
        "Opera": re.compile(r"Opera\/(?P<ver>[\d.]+)|OPR\/(?P<ver2>[\d.]+)"),
        "IE": re.compile(r"MSIE\s(?P<ver>[\d.]+)|rv:(?P<ver2>[\d.]+)"),
    }

    # Engine keywords (simple contains check is adequate and cheap)
    _ENGINES = ("Blink", "WebKit", "Gecko", "Trident")

    # OS patterns
    _OS_PATTERNS: Dict[str, Pattern] = {
        "Windows": re.compile(r"Windows NT (?P<ver>[\d.]+)"),
        "Android": re.compile(r"Android (?P<ver>[\d.]+)"),
        "iOS": re.compile(r"OS (?P<ver>[\d_]+) like Mac OS X"),
        "Mac": re.compile(r"Mac OS X (?P<ver>[\d_]+)"),
        "Linux": re.compile(r"Linux"),
    }

    # Device heuristics
    _DEVICE_PATTERNS: Dict[str, Pattern] = {
        "iPhone": re.compile(r"iPhone"),
        "iPad": re.compile(r"iPad"),
        "Tablet": re.compile(r"Tablet"),
        "Mobile": re.compile(r"Mobile"),
        "Desktop": re.compile(r"Windows|Macintosh|X11|Linux"),
    }

    # Bot detector (compiled once)
    _BOT_PATTERN: Pattern = re.compile(
        r"bot|crawler|spider|googlebot|bingbot|slurp|duckduckbot|yandexbot|bingpreview",
        re.IGNORECASE,
    )

    def __init__(self, user_agent: Optional[str]) -> None:
        self._raw = (user_agent or "").strip()
        # cache a lowercase copy for fast contains checks
        self._lower = self._raw.lower()

    # -- Public API -------------------------------------------------

    def parse(self) -> UserAgentInfo:
        """Return a cached UserAgentInfo instance for this UA string."""
        return self._info

    def to_dict(self) -> Dict[str, object]:
        """Shallow serializable dict for logging / storage."""
        return self._info.to_dict()

    # -- Internal cached parsing -----------------------------------

    @cached_property
    def _info(self) -> UserAgentInfo:
        browser, browser_ver = self._detect_browser()
        engine = self._detect_engine()
        os_name, os_ver = self._detect_os()
        device = self._detect_device()
        is_mobile = self._detect_mobile(device)
        is_bot = bool(self._BOT_PATTERN.search(self._raw))
        return UserAgentInfo(
            browser=browser,
            browser_version=browser_ver,
            engine=engine,
            os=os_name,
            os_version=os_ver,
            device=device,
            is_mobile=is_mobile,
            is_bot=is_bot,
        )

    # -- Detection helpers -----------------------------------------

    def _detect_browser(self) -> Tuple[str, str]:
        ua = self._raw
        for name, pattern in self._BROWSER_PATTERNS.items():
            m = pattern.search(ua)
            if not m:
                continue
            # prefer named group 'ver', fallback to any group
            ver = ""
            if "ver" in m.groupdict() and m.group("ver"):
                ver = m.group("ver")
            else:
                # pick the first non-empty capture group
                groups = m.groups()
                for g in groups:
                    if g:
                        ver = g
                        break
            return name, ver or ""
        return "Unknown", ""

    def _detect_engine(self) -> str:
        low = self._lower
        for eng in self._ENGINES:
            if eng.lower() in low:
                return eng
        # heuristics: Chrome implies Blink/WebKit, Safari => WebKit
        if "chrome" in low or "chromium" in low:
            return "Blink"
        if "safari" in low:
            return "WebKit"
        return "Unknown"

    def _detect_os(self) -> Tuple[str, str]:
        ua = self._raw
        for name, pattern in self._OS_PATTERNS.items():
            m = pattern.search(ua)
            if not m:
                continue
            ver = ""
            # some OS patterns have no version capture (Linux)
            if m.lastindex:
                # normalize underscores to dots for iOS/Mac groups
                group = m.group(1) or ""
                ver = group.replace("_", ".")
            return name, ver
        return "Unknown", ""

    def _detect_device(self) -> str:
        ua = self._raw
        for name, pattern in self._DEVICE_PATTERNS.items():
            if pattern.search(ua):
                return name
        return "Unknown"

    def _detect_mobile(self, device: str) -> bool:
        # device heuristics + keyword fallback
        if device in ("iPhone", "iPad", "Mobile", "Tablet"):
            return True
        return "mobile" in self._lower

    # -- Convenience magic methods -------------------------------

    def __repr__(self) -> str:
        info = self._info
        return (
            f"<UserAgentParser browser={info.browser!r} "
            f"os={info.os!r} device={info.device!r} bot={info.is_bot}>"
        )

    def __str__(self) -> str:
        return self._raw
