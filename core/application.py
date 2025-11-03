from __future__ import annotations

import asyncio
import inspect
import json
import logging
import traceback
from dataclasses import dataclass
from typing import (
    Any,
    Awaitable,
    Callable,
    Dict,
    List,
    Optional,
    Pattern,
    Tuple,
    Type,
    TypeVar,
    Union,
)

from enum import Enum

from pydantic import BaseModel, ValidationError

from _types import Scope, Receive, Send, Lifespan, StatefulLifespan
from wrappers.request import Request
from wrappers.response import Response
from wrappers.websocket import WebSocket, WebSocketDisconnect, WebSocketState

from core import routing
from core.converter import Converter

from exceptions.http import HTTPException
from exceptions.config import ImproperlyConfigured

logger = logging.getLogger(__name__)
T = TypeVar("T")
_converter = Converter()


class RequestStage(Enum):
    BEFORE = "before"
    AFTER = "after"


class Depends:
    def __init__(self, dependency: Callable[..., Any]):
        self.dependency = dependency


class DependencyResolver:
    def __init__(self):
        self._call_stack: List[Callable] = []

    async def resolve(self, dependency: Callable[..., Any], request: Request, cache: Dict[Callable, Any]) -> Any:
        if dependency in cache:
            return cache[dependency]
        if dependency in self._call_stack:
            raise RuntimeError("Circular dependency detected")
        self._call_stack.append(dependency)
        try:
            sig = inspect.signature(dependency)
            kwargs = {}
            for name, param in sig.parameters.items():
                if isinstance(param.default, Depends):
                    sub_dep = param.default.dependency
                    val = await self._maybe_await(self.resolve(sub_dep, request, cache))
                    kwargs[name] = val
                elif param.annotation is Request or param.annotation is Request.__class__:
                    kwargs[name] = request
                elif param.annotation is not inspect._empty and issubclass_safe(param.annotation, BaseModel):
                    body = await self._get_body_as_json(request)
                    model = param.annotation
                    kwargs[name] = model.parse_obj(body)
                elif name in request.path_params:
                    kwargs[name] = request.path_params[name]
                elif param.default is not inspect._empty:
                    kwargs[name] = param.default
            result = dependency(**kwargs) if not inspect.iscoroutinefunction(dependency) else await dependency(**kwargs)
            cache[dependency] = result
            return result
        finally:
            self._call_stack.pop()

    async def _maybe_await(self, value: Any) -> Any:
        if inspect.isawaitable(value):
            return await value
        return value

    async def _get_body_as_json(self, request: Request) -> Any:
        try:
            if hasattr(request, "json"):
                return await request.json()
            if hasattr(request, "body"):
                raw = await request.body()
                if not raw:
                    return {}
                return json.loads(raw.decode("utf-8"))
        except Exception:
            return {}


def issubclass_safe(a: Any, b: Any) -> bool:
    try:
        return inspect.isclass(a) and issubclass(a, b)
    except Exception:
        return False


@dataclass(frozen=True)
class RouteEntry:
    path_def: str
    methods: List[str]
    handler: Callable[..., Awaitable[Any]]
    compiled: Pattern
    response_model: Optional[Type]
    param_casts: Dict[str, Callable[[str], Any]]


@dataclass(frozen=True)
class WebSocketEntry:
    path_def: str
    compiled: Pattern
    handler: Callable[..., Awaitable[Any]]
    param_casts: Dict[str, Callable[[str], Any]]


class RouteRegistry:
    def __init__(self, converter: Converter):
        self._routes: List[RouteEntry] = []
        self._websockets: List[WebSocketEntry] = []
        self._converter = converter

    def load_from_routing_module(self, routing_module) -> None:
        raw_routes = getattr(routing_module, "get_registered_routes", None)
        raw_routes = raw_routes() if callable(raw_routes) else getattr(routing_module, "routes", [])
        for entry in raw_routes:
            try:
                path_def = entry[0]
                methods = list(entry[1]) if entry[1] is not None else ["GET"]
                handler = entry[2]
                regex_or_compiled = entry[3]
                param_casts = {}
                compiled = None
                if isinstance(regex_or_compiled, Pattern):
                    compiled = regex_or_compiled
                elif isinstance(regex_or_compiled, tuple) and len(regex_or_compiled) >= 2:
                    compiled = regex_or_compiled[1]
                    if len(regex_or_compiled) >= 3 and isinstance(regex_or_compiled[2], dict):
                        param_casts = regex_or_compiled[2]
                else:
                    _, compiled, param_casts = self._converter._compile_pattern(path_def, True, "")
                response_model = entry[4] if len(entry) > 4 else None
                self._routes.append(RouteEntry(path_def, [m.upper() for m in methods], handler, compiled, response_model, param_casts))
            except Exception:
                logger.exception("failed loading route %s", entry)
        raw_ws = getattr(routing_module, "get_registered_websockets", None)
        raw_ws = raw_ws() if callable(raw_ws) else getattr(routing_module, "websockets", [])
        for entry in raw_ws:
            try:
                path_def = entry[0]
                handler = entry[1]
                regex_or_compiled = entry[2] if len(entry) > 2 else None
                param_casts = {}
                if isinstance(regex_or_compiled, Pattern):
                    compiled = regex_or_compiled
                elif isinstance(regex_or_compiled, tuple) and len(regex_or_compiled) >= 2:
                    compiled = regex_or_compiled[1]
                    if len(regex_or_compiled) >= 3 and isinstance(regex_or_compiled[2], dict):
                        param_casts = regex_or_compiled[2]
                else:
                    _, compiled, param_casts = self._converter._compile_pattern(path_def, False, "")
                self._websockets.append(WebSocketEntry(path_def, compiled, handler, param_casts))
            except Exception:
                logger.exception("failed loading websocket %s", entry)

    def match_route(self, path: str, method: str) -> Tuple[Optional[RouteEntry], Optional[Dict[str, Any]], Optional[List[str]]]:
        allowed = set()
        for r in self._routes:
            m = r.compiled.match(path)
            if not m:
                continue
            if r.methods and method.upper() not in r.methods:
                allowed.update(r.methods)
                continue
            params = {}
            for k, v in m.groupdict().items():
                if k in r.param_casts:
                    try:
                        params[k] = r.param_casts[k](v)
                    except Exception:
                        params[k] = v
                else:
                    if isinstance(v, str) and v.isdigit():
                        params[k] = int(v)
                    else:
                        try:
                            params[k] = float(v)
                        except Exception:
                            params[k] = v
            return r, params, None
        return None, None, sorted(allowed) if allowed else None

    def match_websocket(self, path: str) -> Tuple[Optional[WebSocketEntry], Optional[Dict[str, Any]]]:
        for w in self._websockets:
            m = w.compiled.match(path)
            if not m:
                continue
            params = {}
            for k, v in m.groupdict().items():
                if k in w.param_casts:
                    try:
                        params[k] = w.param_casts[k](v)
                    except Exception:
                        params[k] = v
                else:
                    params[k] = v
            return w, params
        return None, None


MiddlewareCallable = Callable[[Request, Callable[[Request], Awaitable[Response]]], Awaitable[Response]]


class MiddlewareManager:
    def __init__(self):
        self._stack: List[Tuple[MiddlewareCallable, int]] = []
        self._sorted = True

    def add(self, middleware: MiddlewareCallable, order: int = 0) -> None:
        self._stack.append((middleware, int(order)))
        self._sorted = False

    def build_chain(self, endpoint_callable: Callable[[Request], Awaitable[Response]]) -> Callable[[Request], Awaitable[Response]]:
        if not self._sorted:
            self._stack.sort(key=lambda x: x[1])
            self._sorted = True
        stack = [mw for mw, _ in self._stack]

        async def call_chain(request: Request) -> Response:
            idx = -1
            async def call_next(req: Request) -> Response:
                nonlocal idx
                idx += 1
                if idx >= len(stack):
                    return await endpoint_callable(req)
                return await stack[idx](req, call_next)
            return await call_next(request)
        return call_chain


class StageHandlerManager:
    def __init__(self):
        self.before: List[Callable[[Request], Awaitable[Any]]] = []
        self.after: List[Callable[[Request, Response], Awaitable[Any]]] = []

    def add_before(self, func: Callable[[Request], Awaitable[Any]]) -> None:
        self.before.append(func)

    def add_after(self, func: Callable[[Request, Response], Awaitable[Any]]) -> None:
        self.after.append(func)


class ExceptionManager:
    def __init__(self):
        self._handlers: Dict[Type[Exception], Callable[[Request, Exception], Awaitable[Response]]] = {}

    def register(self, exc_type: Type[Exception], handler: Callable[[Request, Exception], Awaitable[Response]]) -> None:
        self._handlers[exc_type] = handler

    async def handle(self, exc: Exception, request: Request) -> Response:
        for etype, handler in self._handlers.items():
            if isinstance(exc, etype):
                try:
                    return await handler(request, exc)
                except Exception:
                    logger.exception("exception handler failed")
                    return Response(content="Internal Server Error", status_code=500, content_type="text/plain")
        if isinstance(exc, HTTPException):
            content = exc.detail if getattr(exc, "detail", None) is not None else exc.status_code
            if isinstance(content, (dict, list)):
                return Response(content=json.dumps(content), status_code=exc.status_code, content_type="application/json")
            return Response(content=str(content), status_code=exc.status_code, content_type="text/plain")
        logger.exception("unhandled exception")
        return Response(content="Internal Server Error", status_code=500, content_type="text/plain")


class LifespanManager:
    def __init__(self):
        self.startup: List[Callable[..., Awaitable[Any]]] = []
        self.shutdown: List[Callable[..., Awaitable[Any]]] = []

    def add_startup(self, handler: Callable[..., Awaitable[Any]]) -> None:
        self.startup.append(handler)

    def add_shutdown(self, handler: Callable[..., Awaitable[Any]]) -> None:
        self.shutdown.append(handler)

    async def run_startup(self) -> None:
        for h in self.startup:
            await h()

    async def run_shutdown(self) -> None:
        for h in self.shutdown:
            await h()


class Bermoid:
    def __init__(self):
        self.logger = logger
        self.registry = RouteRegistry(_converter)
        self.registry.load_from_routing_module(routing)
        self.middleware = MiddlewareManager()
        self.stage_handlers = StageHandlerManager()
        self.exceptions = ExceptionManager()
        self.lifespan = LifespanManager()
        self.deps = DependencyResolver()
        self.request_transformers: List[Callable[[Request], Awaitable[Request]]] = []
        self.response_transformers: List[Callable[[Response], Awaitable[Response]]] = []
        self.debug = False

    def add_middleware(self, middleware: MiddlewareCallable, order: int = 0) -> None:
        self.middleware.add(middleware, order)

    def add_startup(self, handler: Callable[..., Awaitable[Any]]) -> None:
        self.lifespan.add_startup(handler)

    def add_shutdown(self, handler: Callable[..., Awaitable[Any]]) -> None:
        self.lifespan.add_shutdown(handler)

    def before_request(self, handler: Callable[[Request], Awaitable[Any]]) -> Callable[[Request], Awaitable[Any]]:
        self.stage_handlers.add_before(handler)
        return handler

    def after_request(self, handler: Callable[[Request, Response], Awaitable[Any]]) -> Callable[[Request, Response], Awaitable[Any]]:
        self.stage_handlers.add_after(handler)
        return handler

    def register_exception(self, exc_type: Type[Exception], handler: Callable[[Request, Exception], Awaitable[Response]]) -> None:
        self.exceptions.register(exc_type, handler)

    def register_request_transformer(self, transformer: Callable[[Request], Awaitable[Request]]) -> None:
        self.request_transformers.append(transformer)

    def register_response_transformer(self, transformer: Callable[[Response], Awaitable[Response]]) -> None:
        self.response_transformers.append(transformer)

    async def _invoke_handler(self, handler: Callable[..., Awaitable[Any]], request: Request, param_casts: Dict[str, Callable]) -> Any:
        sig = inspect.signature(handler)
        kwargs = {}
        dep_cache: Dict[Callable, Any] = {}
        for name, param in sig.parameters.items():
            ann = param.annotation
            default = param.default
            if default is not inspect._empty and isinstance(default, Depends):
                value = await self.deps.resolve(default.dependency, request, dep_cache)
                kwargs[name] = value
                continue
            if ann is Request or ann is Request.__class__:
                kwargs[name] = request
                continue
            if ann is inspect._empty and name in request.path_params:
                kwargs[name] = request.path_params[name]
                continue
            if issubclass_safe(ann, BaseModel):
                body = await self._get_body_for_request(request)
                try:
                    kwargs[name] = ann.parse_obj(body)
                except ValidationError as ve:
                    raise HTTPException(status_code=422, detail=ve.errors())
                continue
            if name in request.path_params:
                kwargs[name] = request.path_params[name]
                continue
            if default is not inspect._empty:
                kwargs[name] = default
        result = handler(**kwargs) if not inspect.iscoroutinefunction(handler) else await handler(**kwargs)
        return result

    async def _get_body_for_request(self, request: Request) -> Any:
        try:
            if hasattr(request, "json"):
                return await request.json()
            if hasattr(request, "body"):
                raw = await request.body()
                if not raw:
                    return {}
                return json.loads(raw.decode("utf-8"))
        except Exception:
            return {}

    async def handle_request(self, scope: Scope, receive: Receive, send: Send) -> None:
        request = Request(scope, receive)
        request.context.setdefault("_app", self)
        path = scope.get("path", "/")
        method = scope.get("method", "GET").upper()
        try:
            for before in self.stage_handlers.before:
                await before(request)
            route, params, allowed = self.registry.match_route(path, method)
            if route is None:
                if allowed:
                    resp = Response(content="Method Not Allowed", status_code=405, content_type="text/plain", headers={"allow": ", ".join(allowed)})
                else:
                    resp = Response(content="Not Found", status_code=404, content_type="text/plain")
            else:
                request.path_params = params or {}
                for t in self.request_transformers:
                    request = await t(request)
                async def endpoint_callable(req: Request) -> Response:
                    raw = await self._invoke_handler(route.handler, req, route.param_casts)
                    resp = await self._normalize_response(raw)
                    if route.response_model and issubclass_safe(route.response_model, BaseModel):
                        if isinstance(resp, Response):
                            try:
                                body = json.loads(await resp.body()) if hasattr(resp, "body") else None
                                model = route.response_model.parse_obj(body) if body is not None else None
                                if model is not None:
                                    return Response(content=model.json(), status_code=resp.status_code, content_type="application/json", headers=getattr(resp, "headers", None))
                            except Exception:
                                raise HTTPException(status_code=500, detail="Response validation failed")
                    for t in self.response_transformers:
                        resp = await t(resp)
                    return resp
                chain = self.middleware.build_chain(endpoint_callable)
                resp = await chain(request)
            for after in self.stage_handlers.after:
                await after(request, resp)
        except Exception as exc:
            resp = await self.exceptions.handle(exc, request)
        await resp(scope, receive, send)

    async def _normalize_response(self, value: Any) -> Response:
        if isinstance(value, Response):
            return value
        if isinstance(value, tuple) and len(value) == 2 and isinstance(value[1], int):
            body, status = value
            if isinstance(body, (dict, list)):
                return Response(content=json.dumps(body), status_code=status, content_type="application/json")
            if isinstance(body, str) and body.startswith("<"):
                return Response(content=body, status_code=status, content_type="text/html")
            return Response(content=str(body), status_code=status, content_type="text/plain")
        if isinstance(value, (dict, list)):
            return Response(content=json.dumps(value), content_type="application/json")
        if isinstance(value, str):
            if value.startswith("<"):
                return Response(content=value, content_type="text/html")
            return Response(content=value, content_type="text/plain")
        if isinstance(value, BaseModel):
            return Response(content=value.json(), content_type="application/json")
        raise TypeError("Unsupported response type")

    async def _websocket_handler(self, scope: Scope, receive: Receive, send: Send) -> None:
        ws = WebSocket(scope, receive, send)
        try:
            entry, params = self.registry.match_websocket(ws.path)
            if entry is None:
                await ws.close(code=1000, reason="No route")
                return
            ws.path_params = params or {}
            for k, v in list(ws.path_params.items()):
                if k in entry.param_casts:
                    try:
                        ws.path_params[k] = entry.param_casts[k](v)
                    except Exception:
                        ws.path_params[k] = v
            result = await entry.handler(ws, **ws.path_params)
            if not isinstance(result, WebSocket):
                raise TypeError("Websocket handler must return WebSocket")
        except WebSocketDisconnect:
            if ws.client_state == WebSocketState.CONNECTED:
                await ws.close()
        except Exception:
            logger.exception("websocket error")
            if ws.client_state == WebSocketState.CONNECTED:
                await ws.close(code=1011, reason="Unexpected error")

    async def _lifespan(self, scope: Scope, receive: Receive, send: Send) -> None:
        started = False
        try:
            event = await receive()
            if event.get("type") == "lifespan.startup":
                await self.lifespan.run_startup()
                await send({"type": "lifespan.startup.complete"})
                started = True
                await receive()
            else:
                await send({"type": "lifespan.startup.failed", "message": "Unexpected event"})
        except BaseException:
            tb = traceback.format_exc()
            if started:
                await send({"type": "lifespan.shutdown.failed", "message": tb})
            else:
                await send({"type": "lifespan.startup.failed", "message": tb})
            raise
        else:
            await self.lifespan.run_shutdown()
            await send({"type": "lifespan.shutdown.complete"})

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        scope["app"] = self
        typ = scope.get("type")
        if typ == "http":
            await self.handle_request(scope, receive, send)
        elif typ == "websocket":
            await self._websocket_handler(scope, receive, send)
        elif typ == "lifespan":
            await self._lifespan(scope, receive, send)
        else:
            raise RuntimeError("unknown scope type")
