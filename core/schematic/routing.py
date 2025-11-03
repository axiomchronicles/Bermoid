import inspect
import re
from typing import (
    Optional,
    List,
    Type,
    Callable,
    Awaitable,
    TypeVar,
    Tuple,
    Pattern,
    Dict,
    Any,
)

T = TypeVar("T")

routes: List[
    Tuple[str, List[str], Callable[..., Awaitable[T]], bool, Optional[Type[T]], Optional[str]]
] = []

websockets: List[Tuple[str, Callable[..., Awaitable[T]]]] = []


class RoutingError(Exception):
    pass


def _ensure_async(fn: Callable[..., Any]) -> None:
    if not (inspect.iscoroutinefunction(fn) or inspect.isasyncgenfunction(fn)):
        raise RoutingError("Registered functions must be asynchronous.")


def _validate_path(path: str) -> None:
    if not path.startswith("/"):
        raise RoutingError("Paths must start with '/'.")
    if "//" in path:
        raise RoutingError("Invalid path: consecutive slashes are not allowed.")


def _validate_methods(methods: Optional[List[str]]) -> List[str]:
    allowed = {"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS", "TRACE"}
    if not methods:
        return ["GET"]
    for m in methods:
        if m.upper() not in allowed:
            raise RoutingError(f"Invalid HTTP method: {m}")
    return [m.upper() for m in methods]


def rule(
    path: str,
    endpoint: Callable[..., Awaitable[Any]],
    methods: Optional[List[str]] = None,
    response_model: Optional[Type[T]] = None,
    strict_slashes: bool = True,
    name: Optional[str] = None,
) -> Tuple[str, List[str], Callable[..., Awaitable[T]], bool, Optional[Type[T]], Optional[str]]:
    _validate_path(path)
    _ensure_async(endpoint)
    methods = _validate_methods(methods)
    route = (path, methods, endpoint, strict_slashes, response_model, name)
    routes.append(route)
    return route


def rule_all(
    path: str,
    endpoint: Callable[..., Awaitable[Any]],
    response_model: Optional[Type[T]] = None,
    strict_slashes: bool = True,
    name: Optional[str] = None,
) -> Tuple[str, List[str], Callable[..., Awaitable[T]], bool, Optional[Type[T]], Optional[str]]:
    _validate_path(path)
    _ensure_async(endpoint)
    methods = ["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS", "TRACE"]
    route = (path, methods, endpoint, strict_slashes, response_model, name)
    routes.append(route)
    return route


def re_rule(
    path_regex: str,
    endpoint: Callable[..., Awaitable[Any]],
    methods: Optional[List[str]] = None,
    response_model: Optional[Type[T]] = None,
    name: Optional[str] = None,
) -> Tuple[str, List[str], Callable[..., Awaitable[T]], bool, Optional[Type[T]], Optional[str]]:
    _ensure_async(endpoint)
    try:
        pattern = re.compile(path_regex)
    except re.error:
        raise RoutingError(f"Invalid regex pattern: {path_regex}")
    methods = _validate_methods(methods)
    route = (pattern, methods, endpoint, False, response_model, name)
    routes.append(route)
    return route


def websocket(
    path: str,
    endpoint: Callable[..., Awaitable[T]],
) -> Tuple[str, Callable[..., Awaitable[T]]]:
    _validate_path(path)
    _ensure_async(endpoint)
    ws = (path, endpoint)
    websockets.append(ws)
    return ws
