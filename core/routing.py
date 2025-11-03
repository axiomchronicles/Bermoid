import re
import inspect
import importlib
import logging
import threading
from dataclasses import dataclass
from enum import Enum
from importlib import import_module
from typing import Any, Awaitable, Callable, Dict, List, Optional, Pattern, Tuple, Type, TypeVar, Union

from _types import ASGIApp, Routes, WebSocketRoutes
from core.converter import Converter, ConverterError
from core.schematic.core import Schematic
from exceptions.config import ImproperlyConfigured

T = TypeVar("T")

logger = logging.getLogger(__name__)
_lock = threading.RLock()
_converter = Converter()

class HTTPMethod(Enum):
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"
    HEAD = "HEAD"
    OPTIONS = "OPTIONS"
    PATCH = "PATCH"
    TRACE = "TRACE"

    @classmethod
    def normalize_list(cls, methods: Optional[List[str]]) -> List[str]:
        if not methods:
            return [cls.GET.value]
        normalized: List[str] = []
        for m in methods:
            try:
                normalized.append(cls[m.upper()].value)
            except KeyError:
                raise ImproperlyConfigured(f"Invalid HTTP method: {m}")
        return normalized

@dataclass(frozen=True)
class Route:
    path: str
    methods: Tuple[str, ...]
    handler: Callable[..., Awaitable[Any]]
    regex: Pattern
    response_model: Optional[Type[T]]
    endpoint: Any
    param_casts: Dict[str, Callable[[str], Any]]

@dataclass(frozen=True)
class WebsocketRoute:
    path: str
    regex: Pattern
    handler: Callable[..., Awaitable[Any]]
    param_casts: Dict[str, Callable[[str], Any]]

@dataclass(frozen=True)
class Link:
    path: str
    endpoint: Any
    name: Optional[str]

_routes: List[Route] = []
_links: List[Link] = []
_websockets: List[WebsocketRoute] = []
_handlers_set: set = set()

class DuplicateHandler:
    @staticmethod
    def _ensure_unique_handler(handler: Callable[..., Awaitable[Any]]) -> None:
        with _lock:
            if handler in _handlers_set:
                raise ImproperlyConfigured("Duplicate handler already registered.")
            _handlers_set.add(handler)

    @staticmethod
    def route_exists(path: str, endpoint: Callable[..., Awaitable[Any]]) -> bool:
        with _lock:
            return any(r.path == path and r.endpoint == endpoint for r in _routes)

    @staticmethod
    def websocket_exists(path: str, endpoint: Callable[..., Awaitable[Any]]) -> bool:
        with _lock:
            return any(w.path == path and w.handler == endpoint for w in _websockets)

    @staticmethod
    def regex_route_exists(pattern: str, endpoint: Callable[..., Awaitable[Any]]) -> bool:
        with _lock:
            return any(r.regex.pattern == pattern and r.endpoint == endpoint for r in _routes)

class RoutingHelpers:
    @staticmethod
    def _include_routes(prefix: str, includes: List[Tuple]) -> None:
        for item in includes:
            if len(item) != 7:
                logger.debug("Skipping invalid include item (expected 7-tuple): %s", item)
                continue
            sub_path, sub_methods, sub_handler, sub_strict_slashes, sub_response_model, sub_endpoint, sub_name = item
            if not (inspect.iscoroutinefunction(sub_handler) or inspect.isasyncgenfunction(sub_handler)):
                raise ImproperlyConfigured("Included route handler must be async.")
            methods = tuple(HTTPMethod.normalize_list(sub_methods))
            try:
                pattern_str, compiled_regex, param_casts = _converter._compile_pattern(prefix + sub_path, sub_strict_slashes, '')
            except ConverterError as exc:
                raise ImproperlyConfigured(f"Invalid route pattern for '{prefix + sub_path}': {exc}") from exc

            with _lock:
                if DuplicateHandler.route_exists(pattern_str, sub_handler):
                    raise ImproperlyConfigured(f"Duplicate route: {pattern_str} -> {sub_handler}")
                _routes.append(Route(pattern_str, methods, sub_handler, compiled_regex, sub_response_model, sub_endpoint, param_casts))
                _links.append(Link(prefix + sub_path, sub_endpoint, sub_name))

    @staticmethod
    def _include_websockets(prefix: str, includes: List[Tuple]) -> None:
        for item in includes:
            if len(item) != 2:
                logger.debug("Skipping invalid websocket include item (expected 2-tuple): %s", item)
                continue
            sub_path, sub_handler = item
            if not (inspect.iscoroutinefunction(sub_handler) or inspect.isasyncgenfunction(sub_handler)):
                raise ImproperlyConfigured("Included websocket handler must be async.")
            try:
                pattern_str, compiled_regex, param_casts = _converter._compile_pattern(prefix + sub_path, False, '')
            except ConverterError as exc:
                raise ImproperlyConfigured(f"Invalid websocket pattern for '{prefix + sub_path}': {exc}") from exc

            with _lock:
                if DuplicateHandler.websocket_exists(pattern_str, sub_handler):
                    raise ImproperlyConfigured(f"Duplicate websocket route: {pattern_str} -> {sub_handler}")
                _websockets.append(WebsocketRoute(pattern_str, compiled_regex, sub_handler, param_casts))

class HTTPRouting:
    @staticmethod
    def rule(path: str, endpoint: Optional[Callable[..., Awaitable[Any]]] = None, **kwargs: Any) -> Optional[Tuple]:
        if not path.startswith("/"):
            raise ImproperlyConfigured("Path must start with '/'.")

        include_routes = kwargs.pop("include", None)
        if include_routes:
            RoutingHelpers._include_routes(path, include_routes)
            return None

        if endpoint is None or not (inspect.iscoroutinefunction(endpoint) or inspect.isasyncgenfunction(endpoint)):
            raise ImproperlyConfigured("Endpoint must be an async callable.")

        methods = tuple(HTTPMethod.normalize_list(kwargs.pop("methods", None)))
        strict_slashes = kwargs.pop("strict_slashes", True)
        response_model = kwargs.pop("response_model", None)
        name = kwargs.get("name")

        try:
            converted_path, compiled_regex, param_casts = _converter._compile_pattern(path, strict_slashes, '')
        except ConverterError as exc:
            raise ImproperlyConfigured(f"Invalid route pattern for '{path}': {exc}") from exc

        with _lock:
            if DuplicateHandler.route_exists(converted_path, endpoint):
                raise ImproperlyConfigured("Duplicate route endpoint detected.")
            _routes.append(Route(converted_path, methods, endpoint, compiled_regex, response_model, endpoint, param_casts))
            _links.append(Link(path, endpoint, name))

        return (path, list(methods), endpoint, strict_slashes, response_model, endpoint, name)

    @staticmethod
    def re_rule(path_regex: str, endpoint: Callable[..., Awaitable[Any]], **kwargs: Any) -> Tuple:
        if not (inspect.iscoroutinefunction(endpoint) or inspect.isasyncgenfunction(endpoint)):
            raise ImproperlyConfigured("Endpoint must be an async callable.")

        methods = tuple(HTTPMethod.normalize_list(kwargs.pop("methods", None)))
        response_model = kwargs.pop("response_model", None)
        strict_slashes = kwargs.get("strict_slashes", False)

        # treat path_regex as a raw regex; compile via converter only for consistency of param casts
        try:
            # If user passed a precompiled pattern we accept it, otherwise compile and leave param_casts empty
            if isinstance(path_regex, Pattern):
                compiled = path_regex
                param_casts: Dict[str, Callable[[str], Any]] = {}
                pattern_str = compiled.pattern
            else:
                pattern_str, compiled, param_casts = _converter._compile_pattern(path_regex, strict_slashes, '')
        except ConverterError as exc:
            raise ImproperlyConfigured(f"Invalid regex route pattern '{path_regex}': {exc}") from exc

        with _lock:
            if DuplicateHandler.regex_route_exists(pattern_str, endpoint):
                raise ImproperlyConfigured("Duplicate regex route endpoint detected.")
            _routes.append(Route(pattern_str, methods, endpoint, compiled, response_model, endpoint, param_casts))
            _links.append(Link(pattern_str, endpoint, kwargs.get("name")))

        return (pattern_str, list(methods), endpoint, strict_slashes, response_model, endpoint, kwargs.get("name"))

    @staticmethod
    def rule_all(path: str, response_model: Optional[Type[T]] = None, endpoint: Callable[..., Awaitable[T]] = None, strict_slashes: bool = True, name: Optional[str] = None) -> Tuple:
        if not (inspect.iscoroutinefunction(endpoint) or inspect.isasyncgenfunction(endpoint)):
            raise TypeError("ASGI supports only async functions as endpoints.")

        if not path.startswith("/"):
            raise ImproperlyConfigured("Path must start with '/'.")

        DuplicateHandler._ensure_unique_handler(endpoint)

        try:
            converted_path, compiled_regex, param_casts = _converter._compile_pattern(path, strict_slashes, '')
        except ConverterError as exc:
            raise ImproperlyConfigured(f"Invalid route pattern for '{path}': {exc}") from exc

        with _lock:
            allowed = tuple(m.value for m in HTTPMethod)
            _routes.append(Route(converted_path, allowed, endpoint, compiled_regex, response_model, endpoint, param_casts))
            _links.append(Link(path, endpoint, name))

        return (path, list(allowed), endpoint, strict_slashes, response_model, endpoint, name)

class WebsocketRouting:
    @staticmethod
    def websocket(path: str, endpoint: Optional[Callable[..., Awaitable[T]]] = None, **kwargs: Any) -> Optional[Tuple]:
        if not path.startswith("/"):
            raise ImproperlyConfigured("Websocket path must start with '/'.")

        include_ws = kwargs.get("include")
        if include_ws:
            RoutingHelpers._include_websockets(path, include_ws)
            return None

        if endpoint is None or not (inspect.iscoroutinefunction(endpoint) or inspect.isasyncgenfunction(endpoint)):
            raise ImproperlyConfigured("Websocket endpoint must be an async callable.")

        try:
            full_path, compiled_regex, param_casts = _converter._compile_pattern(path, False, '')
        except ConverterError as exc:
            raise ImproperlyConfigured(f"Invalid websocket pattern for '{path}': {exc}") from exc

        with _lock:
            if DuplicateHandler.websocket_exists(full_path, endpoint):
                raise ImproperlyConfigured("Duplicate websocket endpoint detected.")
            _websockets.append(WebsocketRoute(full_path, compiled_regex, endpoint, param_casts))

        return (path, endpoint)

class _SchematicInstance:
    def __init__(self) -> None:
        self.schematic = None
        self.schematic_id = None

    def _process_routes(self, schematic_instance: ASGIApp, url_prefix: str) -> None:
        for route in schematic_instance.routes:
            path, methods, handler, strict_slashes, response_model, endpoint = route
            path = '' if path.endswith('/') else path
            try:
                converted_path, compiled_regex, param_casts = _converter._compile_pattern(url_prefix + path, strict_slashes, '')
            except ConverterError as exc:
                raise ImproperlyConfigured(f"Invalid route pattern for '{url_prefix + path}': {exc}") from exc

            with _lock:
                _routes.append(Route(converted_path, tuple(methods), handler, compiled_regex, response_model, endpoint, param_casts))
                _links.append(Link(url_prefix + path, endpoint, schematic_instance.name))

    def _process_schematic_instance(self, schematic_instance: ASGIApp, url_prefix: str) -> None:
        if getattr(schematic_instance, "schematic_id", None) is not None:
            self.schematic_id = schematic_instance.schematic_id
            self.schematic = schematic_instance.get_schematic()
            self._log_schematic_info(schematic_instance, url_prefix)
        self._process_websockets(schematic_instance, url_prefix)

    def _log_schematic_info(self, schematic_instance: ASGIApp, url_prefix: str) -> None:
        name = schematic_instance.name
        prefix_info = f"at {url_prefix} url-prefix" if url_prefix else "with no specific URL prefix"
        logger.info("Serving Schematic '%s' %s. Instance-ID: %s", name, prefix_info, self.schematic_id)
        paths = [r.path for r in schematic_instance.routes]
        if paths:
            logger.info("Routes: %s", paths)
        else:
            logger.warning("No HTTP routes found for schematic '%s'.", name)

    def _process_websockets(self, schematic_instance: ASGIApp, url_prefix: str) -> None:
        if schematic_instance.websockets:
            logger.info("WebSocket routes for schematic '%s':", schematic_instance.name)
            for path, handler in schematic_instance.websockets:
                full_path = url_prefix + path
                try:
                    pattern_str, compiled_regex, param_casts = _converter._compile_pattern(full_path, False, '')
                except ConverterError as exc:
                    raise ImproperlyConfigured(f"Invalid websocket pattern for '{full_path}': {exc}") from exc

                with _lock:
                    _websockets.append(WebsocketRoute(pattern_str, compiled_regex, handler, param_casts))
                logger.info("  - Path: %s Handler: %s", full_path, getattr(handler, "__name__", repr(handler)))
        else:
            logger.warning("No WebSocket routes found for schematic '%s'.", schematic_instance.name)

_schematic = _SchematicInstance()

def link(path: str, instance: Union[str, Type[Schematic]]) -> None:
    try:
        if isinstance(instance, str):
            module_name, class_name = instance.rsplit('.', 1)
            module = import_module(module_name)
            schematic_cls = getattr(module, class_name)
            schematic_instance = schematic_cls
        else:
            schematic_instance = instance

        if not isinstance(schematic_instance, Schematic):
            raise TypeError(f"{instance!r} is not a valid Schematic ASGIApp instance or class")

        _schematic._process_routes(schematic_instance, path)
        _schematic._process_schematic_instance(schematic_instance, path)
    except (ValueError, AttributeError, ModuleNotFoundError, ImportError) as exc:
        raise ImportError(f"Failed to import or load schematic {instance!r}: {exc}") from exc
    except TypeError:
        raise

class DynamicModuleLoader:
    class ModuleImportError(Exception): pass
    class RoutingVariableError(Exception): pass

    def _module_loader(self, dotted_path: str) -> Any:
        try:
            return importlib.import_module(dotted_path)
        except ImportError as exc:
            raise self.ModuleImportError(f"Unable to import module {dotted_path}: {exc}") from exc

    def _routing_avrs(self, module: Any, namespace: str = '') -> List[Any]:
        name = f"{namespace}ROUTER"
        routing_var = getattr(module, name, None)
        if routing_var is None or not isinstance(routing_var, list):
            raise self.RoutingVariableError(f"Module {module.__name__} must expose a list named '{name}'")
        return routing_var

    def _include(self, dotted_path: str, namespace: str = '') -> Optional[List[Any]]:
        try:
            module = self._module_loader(dotted_path)
            return self._routing_avrs(module, namespace)
        except (self.ModuleImportError, self.RoutingVariableError) as exc:
            logger.error("Include error for '%s': %s", dotted_path, exc)
            return None

def include(args: str, namespace: str = '') -> Optional[List[Any]]:
    return DynamicModuleLoader()._include(args, namespace)

def get_registered_routes() -> List[Route]:
    with _lock:
        return list(_routes)

def get_registered_websockets() -> List[WebsocketRoute]:
    with _lock:
        return list(_websockets)

def get_links() -> List[Link]:
    with _lock:
        return list(_links)

def reset_registry() -> None:
    with _lock:
        _routes.clear()
        _websockets.clear()
        _links.clear()
        _handlers_set.clear()
        logger.debug("Route registry reset.")
