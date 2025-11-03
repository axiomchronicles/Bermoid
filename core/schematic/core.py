from __future__ import annotations

import secrets
import inspect
import re
import asyncio
from typing import (
    Callable,
    Any,
    List,
    Type,
    Dict,
    Optional,
    TypeVar,
    Tuple,
    Awaitable,
    Pattern,
)

from core.schematic import routing

T = TypeVar("T")


class SchematicError(Exception):
    pass


class Schematic:
    __slots__ = (
        "name",
        "routes",
        "websockets",
        "middlewares",
        "schematic_id",
    )

    def __init__(self, name: str):
        self.name = name
        self.routes: List[
            Tuple[str, List[str], Callable[..., Awaitable[T]], bool, Optional[Type[T]], Optional[str]]
        ] = []
        self.websockets: List[Tuple[str, Callable[..., Awaitable[T]]]] = []
        self.middlewares: List[Dict[str, Any]] = []
        self.schematic_id = secrets.token_hex(11)
        self.middleware(self._schematicIdMiddleware)
        self._include_registered_routes()

    def _ensure_async(self, fn: Callable[..., Any]) -> None:
        if not (inspect.iscoroutinefunction(fn) or inspect.isasyncgenfunction(fn)):
            raise SchematicError("Registered functions must be asynchronous.")

    def _validate_path(self, path: str) -> None:
        if not path.startswith("/"):
            raise SchematicError("Paths must start with '/'.")
        if "//" in path:
            raise SchematicError("Invalid path: consecutive slashes are not allowed.")

    def _validate_methods(self, methods: Optional[List[str]]) -> List[str]:
        allowed = {"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS", "TRACE"}
        if not methods:
            return ["GET"]
        for method in methods:
            if method.upper() not in allowed:
                raise SchematicError(f"Invalid HTTP method: {method}")
        return [m.upper() for m in methods]

    def rule(
        self,
        path: str,
        methods: Optional[List[str]] = None,
        response_model: Optional[Type[T]] = None,
        endpoint: Optional[str] = None,
        strict_slashes: bool = True,
    ) -> Callable[..., Awaitable[T]]:
        self._validate_path(path)
        methods = self._validate_methods(methods)

        def decorator(handler: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
            self._ensure_async(handler)
            self.routes.append((path, methods, handler, strict_slashes, response_model, endpoint))
            return handler

        return decorator

    def add_rule(
        self,
        path: str,
        handler: Callable[..., Awaitable[T]],
        methods: Optional[List[str]] = None,
        response_model: Optional[Type[T]] = None,
        endpoint: Optional[str] = None,
        strict_slashes: bool = True,
    ) -> None:
        self._validate_path(path)
        self._ensure_async(handler)
        methods = self._validate_methods(methods)
        self.routes.append((path, methods, handler, strict_slashes, response_model, endpoint))

    def websocket(self, path: str) -> Callable[..., Awaitable[T]]:
        self._validate_path(path)

        def decorator(handler: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
            self._ensure_async(handler)
            self.websockets.append((path, handler))
            return handler

        return decorator

    def add_websocket_rule(self, path: str, handler: Callable[..., Awaitable[T]]) -> None:
        self._validate_path(path)
        self._ensure_async(handler)
        self.websockets.append((path, handler))

    def middleware(
        self,
        middleware: Callable[..., Awaitable[T]],
        order: int = 0,
        conditions: Optional[List[Callable[..., bool]]] = None,
        group: Optional[str] = None,
        active: bool = True,
        excludes: Optional[List[str]] = None,
    ) -> None:
        if not asyncio.iscoroutinefunction(middleware):
            raise SchematicError("Middleware must be asynchronous.")
        self.middlewares.append(
            {
                "middleware": middleware,
                "order": order,
                "conditions": conditions or [],
                "group": group,
                "active": active,
                "excludes": excludes or [],
            }
        )
        self.middlewares.sort(key=lambda x: x["order"])

    def _include_registered_routes(self) -> None:
        for route in routing.routes:
            path, methods, handler, strict_slashes, response_model, endpoint = route
            self.routes.append((path, methods, handler, strict_slashes, response_model, endpoint))

    async def _schematicIdMiddleware(self, request, response):
        response.headers["schematic-instance-id"] = self.schematic_id
        return response

    def get_schematic(self) -> "Schematic":
        return self
