from __future__ import annotations

import json
import inspect
import pathlib
import warnings
import traceback
import xml.etree.ElementTree as ET

from enum import Enum
from functools import wraps
from inspect import signature
from collections import defaultdict

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
    Union,
    Mapping
)

from _types import Scope, Receive, Send, Lifespan, StatefulLifespan, ASGIApp
from wrappers.request import Request
from wrappers.response import Response
from wrappers.parser import RequestParser
from wrappers.responses import HTMLResponse
from wrappers.websocket import WebSocket, WebSocketDisconnect, WebSocketState

from core.routing import core as routing
from core.schematic.core import Schematic
from core.converter import Converter
from core.http_exceptions import exception_dict

from settings.base import settings
from settings.handler import StageHandler
from utils.module_loading import import_string

from exceptions.http import HTTPException
from exceptions.config import ImproperlyConfigured
from exceptions.http.core import InternalServerError
from exceptions.http.handler import handle_exception

T = TypeVar("T")

class RequestStage(Enum):
    BEFORE: str = 'before'
    AFTER: str = 'after'

class ColoursCode:
    BG_YELLOW = "\033[35m"
    BLUE = "\033[34m"
    GREEN = "\033[32m"
    RED = "\033[31m"
    YELLOW = "\033[33m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"
    BOLD = "\033[1m"
    RESET = "\033[0m" 

class Bermoid:
    def __init__(
        self
        ) -> None:

        self.routes: List[
            Tuple[
                str,
                List[str],
                Callable[..., Awaitable[T]],
                List[str],
                Pattern,
                Type[T],
                str,
                Dict[str, Any],
            ]
        ] = []
        self.websockets: List[
            Tuple[
                str,
                Callable[..., Awaitable[T]]
            ]
        ] = []
        self._middlewares: List[Callable[..., Awaitable[T]]] = []
        self.middleware_order: List[Tuple[Callable[..., Awaitable[T]], int]] = []
        self.request_transformers: List[Callable[..., Awaitable[Request]]] = []
        self.response_transformers: List[
            Callable[..., Awaitable[Response]]
        ] = []
        self.messages: List[Callable[..., Awaitable[T]]] = []
        self.middleware_groups: Dict[str, List[Callable[..., Awaitable[T]]]] = {}
        self.middleware_activation: Dict[Callable[..., Awaitable[T]], bool] = {}
        self.middleware_dependencies: Dict[Callable[..., Awaitable[T]], List[Callable[..., Awaitable[T]]]] = defaultdict(list)
        self.middleware_exclusions: Dict[Callable[..., Awaitable[T]], List[Callable[..., Awaitable[T]]]] = defaultdict(list)
        self.before_request_handlers: List[Callable[..., Awaitable[T]]] = []
        self.after_request_handlers: List[Callable[..., Awaitable[T]]] = []
        self.startup_handlers: List[Callable[..., Awaitable[Lifespan]]] = []
        self.shutdown_handlers: List[Callable[..., Awaitable[Lifespan]]] = []
        self.grouped_request_stages: Dict[str, Dict[str, List[Callable]]] = {}
        self.error_handlers: Dict[str, Dict[str, List[Callable]]] = {}
        self.excluded_stages: Dict[str, List[Callable]] = {}
        # self.config: Callable[..., Awaitable[T, Config, Union[str, dict, bytes, Any]]] = None,
        self.request_stage_handlers: Dict[str, List[Tuple[Callable[..., Awaitable[None]], int, Optional[Callable]]]] = {
            RequestStage.BEFORE.value: [], 
            RequestStage.AFTER.value: []
        }
        self.on_startup: Optional[Union[Callable[..., Awaitable[Any]], List[Callable[..., Awaitable[Any]]]]] = None,
        self.on_shutdown: Optional[Union[Callable[..., Awaitable[Any]], List[Callable[..., Awaitable[Any]]]]] = None,

        self.debug: bool = settings.DEBUG or False
        self.schematic_id: Optional[str] = None
        self.schematic: Callable[..., Awaitable[T]] = None
        self.exception_handlers: Optional[
            Mapping[
                Any,
                Callable[
                    [Request, Exception],
                    Union[Response, Awaitable[Response]],
                ],
            ]
        ] = None

        self._load_lifespan_handlers()
        self._load_exception_handler()
        StageHandler().process_stage_handlers(self)

    async def _execute_request_stage_handlers(
        self,
        stage: Union[Callable[..., Awaitable[T]], str],
        *args: Optional[Union[Callable[..., Awaitable[T]], str]],
        context: Dict[str, Any],
        **kwargs
    ) -> Any:
        handlers = self.request_stage_handlers[stage] + self.grouped_request_stages.get(stage, [])
        if stage in self.excluded_stages:
            handlers = [handler for handler in handlers if handler not in self.excluded_stages[stage]]
        for handler, _, condition in handlers:
            try:
                if not condition or (condition and condition(*args, **kwargs)):
                    func_args = list(signature(handler).parameters.keys())
                    handler_args = args + (context,) if 'context' in func_args else args
                    result = await handler(*handler_args, **kwargs)
                    if result:
                        return result
            except Exception as e:
                if self.debug:
                    await handle_exception(e, *args)
                    print(f"Error in {stage} request stage handler: {e}")
                else:
                    return await self._error_validator(500)
        return None

    def include(
        self,
        schematic: Dict[str, Schematic[ASGIApp]],
        include_middlewares: Optional[bool] = False
    ) -> None:
        for url_prefix, schematic_instance in schematic.items():
            self._process_routes(schematic_instance, url_prefix)
            if include_middlewares:
                self._add_middlewares(schematic_instance)
            self._process_schematic_instance(schematic_instance, url_prefix)

    def _process_routes(self, schematic_instance: Schematic[ASGIApp], url_prefix: str) -> None:
        for route in schematic_instance.routes:
            path, methods, handler, strict_slashes, response_model, endpoint = route

            if path.endswith('/'):
                path = ''  # Simulating the root_path

            converted_path, path_regex = Converter()._regex_converter(url_prefix + path, strict_slashes)

            self.routes.append(
                (
                    converted_path,
                    methods,
                    handler,
                    path_regex,
                    response_model,
                    endpoint,
                )
            )

    def _add_middlewares(self, schematic_instance: Schematic[ASGIApp]) -> None:
        self._middlewares.extend(schematic_instance.middlewares)

    def _process_schematic_instance(self, schematic_instance: Schematic[ASGIApp], url_prefix: str) -> None:
        if schematic_instance.schematic_id is not None:
            self._update_schematic_info(schematic_instance)
            self._print_schematic_info(schematic_instance, url_prefix)

        self._process_websockets(schematic_instance, url_prefix)

    def _update_schematic_info(self, schematic_instance: Schematic[ASGIApp]) -> None:
        self.schematic_id = schematic_instance.schematic_id
        self.schematic = schematic_instance.get_schematic()

    def _print_schematic_info(self, schematic_instance: Schematic[ASGIApp], url_prefix: str) -> None:
        schematic_name = schematic_instance.name
        url_prefix_info = (
            f"at {ColoursCode.BOLD}{ColoursCode.GREEN}{url_prefix}{ColoursCode.RESET} url-prefix"
            if url_prefix
            else "with no specific URL prefix"
        )

        serving_message = (
            f"\n Serving Schematic {ColoursCode.BOLD}{ColoursCode.GREEN}'{schematic_name}'{ColoursCode.RESET} Instance {url_prefix_info}."
        )
        instance_id_message = f"Instance-ID: {ColoursCode.BOLD}{ColoursCode.GREEN}{self.schematic_id}{ColoursCode.RESET}"

        print(serving_message)
        print(instance_id_message)

        paths = [route[0] for route in schematic_instance.routes]
        if paths:
            print(
                f"{ColoursCode.CYAN}Routes{ColoursCode.RESET}: {ColoursCode.GREEN}{paths}{ColoursCode.RESET} \n"
            )
        else:
            print(
                f"{ColoursCode.RED}No HTTP routes found for this schematic.{ColoursCode.RESET} \n"
            )

    def _process_websockets(self, schematic_instance: Schematic[ASGIApp], url_prefix: str) -> None:
        if schematic_instance.websockets:
            print(f"{ColoursCode.BOLD}WebSocket Routes:{ColoursCode.RESET}")

            for path, handler in schematic_instance.websockets:
                full_path = url_prefix + path
                self.websockets.append(
                    (
                        full_path,
                        Converter()._regex_converter(full_path, False)[1],
                        handler
                    )
                )
                print(f"  - Path: {ColoursCode.GREEN}{full_path}{ColoursCode.RESET}")
                print(f"    Handler: {handler.__name__}")
            
            print()
        else:
            print(f"{ColoursCode.RED}No WebSocket routes found for this schematic.{ColoursCode.RESET}\n")

    async def apply_middlewares(
        self, request: Request, response: Response
    ) -> Response:
        executed_middlewares = set()

        for middleware_entry in self._middlewares:
            middleware = middleware_entry["middleware"]
            conditions = middleware_entry.get("conditions")
            group = middleware_entry.get("group")
            excludes = middleware_entry.get("excludes")

            if group and middleware not in self.middleware_groups[group]:
                continue

            if not self.middleware_activation.get(middleware, True):
                continue

            if conditions:
                if not all(cond(request) for cond in conditions):
                    continue

            if excludes:
                exclusions = self.middleware_exclusions[excludes]
                if any(exc in executed_middlewares for exc in exclusions):
                    continue

            response = await middleware(request, response)
            executed_middlewares.add(middleware)

        return response
    
    def _helper_route_setup(self):
        routes_to_add = []

        for route in routing._routes:
            path, methods, handler, strict_slashes, response_model, endpoint = route
            route_tuple = (
                path,
                tuple(methods),
                handler,
                strict_slashes,
                response_model,
                endpoint,
            )

            if route_tuple not in self.routes:
                routes_to_add.append(route_tuple)

        self.routes.extend(routes_to_add)
    
    async def handle_request(
        self,
        scope: Dict[str, Scope],
        receive: Callable[..., Awaitable[Receive]],
        send: Callable[..., Awaitable[Send]],
    ) -> None:
        path = scope.get("path", "/")
        method = scope.get("method", "GET")
        request = Request(scope, receive)
        response = None
        context: Dict[str, List[Callable[..., Awaitable[T]]]] = {}

        try:
            self._helper_route_setup()
            allowed_methods = set()

            if not self.routes:
                if self.debug:
                    template = pathlib.Path(__file__).parent / "_template" / "default_welcome.html"
                    response = HTMLResponse(content=template.read_text(), status=200)
                else:
                    response = Response("<h1>Welcome to Aquilify, Your installation successful.</h1><p>You have debug=False in you Aquilify settings, change it to True in use of development for better experiance.")
            for (
                route_pattern,
                methods,
                handler,
                path_regex,
                response_model,
                endpoint,
            ) in self.routes:
                match = path_regex.match(path)
                if match:
                    if not methods or method.upper() in map(str.upper, methods):
                        path_params = match.groupdict()
                        processed_path_params = {key: self._convert_value(value) for key, value in path_params.items()}
                        request.path_params = processed_path_params

                        await self._execute_request_stage_handlers(RequestStage.BEFORE.value, request, context=context)

                        await self._context_processer(request)
                        scope['context'] = request.context ## context manager ..., Awaitable

                        for transformer in self.request_transformers:
                            request = await transformer(request)

                        handler_params = inspect.signature(handler).parameters

                        if 'request' in handler_params:
                            parser = RequestParser()

                            if 'parser' in handler_params:
                                response = await handler(request, parser=parser, **request.path_params)
                            else:
                                if request.path_params:
                                    valid_path_params = {key: value for key, value in request.path_params.items() if key in handler_params}
                                    response = await handler(request, **valid_path_params)
                                else:
                                    response = await handler(request)
                        else:
                            handler_kwargs = {param.name: request.path_params[param.name] for param in handler_params.values() if param.name in request.path_params}

                            if handler_kwargs and not request.path_params:
                                raise ValueError("Handler kwargs provided without request.path_params")

                            response = await handler(**handler_kwargs)

                        response = await self._process_response(response, handler.__name__)

                        if response_model:
                            response = self._validate_and_serialize_response(
                                response, response_model
                            )

                        break

                    else:
                        allowed_methods.update(methods)

            if response is None:
                if allowed_methods:
                    response = await self._error_validator(405, request, allowed_methods)
                else:
                    response = await self._error_validator(404, request)

            for transformer in self.response_transformers:
                response = await transformer(response)

            response = await self.apply_middlewares(request, response)
            if not isinstance(response, (Response, Awaitable)):
                print(response)
                raise ValueError("Middleware must return a Response object or Awaitable[Response]")
            
            await self._execute_request_stage_handlers(RequestStage.AFTER.value, request, response, context=context)

        except Exception as e:
            response = await self._process_exception(e, request)

        await response(scope, receive, send)

    async def _context_processer(self, request: Request):
        request.context['_request'] = request
        request.context['_app'] = self

    async def _process_exception(self, e, request) -> Response:
        """Centralized exception handler."""
        reversed_exception_dict = {v: k for k, v in exception_dict.items()}
        try:
            # Map known HTTPException -> proper response
            if type(e) in reversed_exception_dict:
                status_code = reversed_exception_dict[type(e)]
                return await self._error_validator(status_code, request)

            # Otherwise, debug mode: show dev traceback
            if self.debug:
                try:
                    return await handle_exception(e, request)
                except Exception as inner_error:
                    print(f"[ERROR] Exception while running handle_exception: {inner_error}")
                    print(traceback.format_exc())
                    return Response(
                        f"Internal Error in exception handler: {inner_error}",
                        content_type="text/plain",
                        status_code=500,
                    )

            # Custom exception handlers
            elif self.exception_handlers:
                try:
                    return await self.exception_handlers(e, request)
                except Exception as inner_error:
                    print(f"[ERROR] Exception in custom handler: {inner_error}")
                    print(traceback.format_exc())
                    return Response(
                        f"Internal Error in custom handler: {inner_error}",
                        content_type="text/plain",
                        status_code=500,
                    )

            # Fallback
            else:
                return await self._error_validator(500, request)

        except Exception as final_error:
            print(f"[FATAL] Failed to process exception: {final_error}")
            print(traceback.format_exc())
            return Response(
                "A fatal internal error occurred.",
                content_type="text/plain",
                status_code=500,
            )
    
    def _convert_value(self, value):
        if isinstance(value, int):
            return int(value)
        elif isinstance(value, str):
            if value.isdigit():
                return int(value)
            try:
                return float(value)
            except ValueError:
                return value
        return str(value)

    async def _process_response(self, response, caller_function) -> Response:
        caller_function_name = caller_function
        if isinstance(response, str):
            if response.startswith("<"):
                try:
                    ET.fromstring(response)
                    response = Response(response, content_type='application/xml')
                except ET.ParseError:
                    response = Response(response, content_type='text/html')
            else:
                response = Response(response, content_type='text/plain')
        elif isinstance(response, dict):
            response = Response(content=json.dumps(response), content_type='application/json')
        elif isinstance(response, tuple) and len(response) == 2 and isinstance(response[1], int):
            if isinstance(response[0], str):
                if response[0].startswith("<"):
                    try:
                        ET.fromstring(response[0])
                        response = Response(response[0], content_type='application/xml', status_code=response[1])
                    except ET.ParseError:
                        response = Response(response[0], content_type='text/html', status_code=response[1])
                else:
                    response = Response(response[0], content_type='text/plain', status_code=response[1])
            elif isinstance(response[0], dict):
                response = Response(content=json.dumps(response[0]), content_type='application/json', status_code=response[1])
            elif isinstance(response[0], list):
                def handle_nested(item):
                    return item if isinstance(item, (str, bytes)) else json.dumps(item)

                processed_list = [handle_nested(item) for item in response[0]]
                
                if all(isinstance(item, (str, bytes)) for item in processed_list):
                    response = Response(content=json.dumps(processed_list), content_type='application/json', status_code=response[1])
                else:
                    response = InternalServerError("Unable to process the list structure")
        elif isinstance(response, list):
            def handle_nested(item):
                return item if isinstance(item, (str, bytes)) else json.dumps(item)

            processed_list = [handle_nested(item) for item in response]
            
            if all(isinstance(item, (str, bytes)) for item in processed_list):
                response = Response(content=json.dumps(processed_list), content_type='application/json')
            else:
                response = InternalServerError("Unable to process the list structure")
        elif not isinstance(response, Response):
            received_type = type(response).__name__
            expected_types = ", ".join([typ.__name__ for typ in [str, dict, Response]])
            raise TypeError(f"Function '{caller_function_name}': Invalid response type: Received {received_type}. Expected types are {expected_types}.")
        return response

    async def _error_validator(self, error_code, *args):
        if error_code in self.error_handlers:
            if error_code == 500:
                error_handler = self.error_handlers[error_code]
                response = await error_handler() if not args else await error_handler(*args)
            else:
                error_handler = self.error_handlers[error_code]
                response = await error_handler(*args) if args else await error_handler()

            if isinstance(response, str):
                return Response(content=response, content_type="text/plain", status_code=error_code)
            elif isinstance(response, dict):
                return Response(content=json.dumps(response), status_code=error_code, content_type='application/json')
            elif isinstance(response, Response):
                return response
            else:
                received_type = type(response).__name__
                expected_types = ", ".join([typ.__name__ for typ in [str, dict, Response]])
                raise HTTPException(f"Invalid response type: Received {received_type}. Expected types are {expected_types}")
        
        if error_code in exception_dict:
            if error_code == 404:
                return exception_dict[404]()
            elif error_code == 405:
                return exception_dict[405]()
            else:
                return exception_dict[error_code]()
        else:
            raise TypeError('Unsupported error type! : {}'.format(error_code))

    def _validate_and_serialize_response(
        self, response: Response, response_model: Type[T]
    ) -> Response:
        if not isinstance(response, response_model):
            raise ValueError(
                f"Response does not match the expected model {response_model.__name__}"
            )
        return Response(content=response.dict(), content_type="application/json")

    async def _websocket_handler(
        self,
        scope: Dict[str, Scope],
        receive: Callable[..., Awaitable[Receive]],
        send: Callable[..., Awaitable[Send]],
    ) -> None:
        ws = WebSocket(scope, receive, send)
        try:
            await self._websocket_routes(ws)
            await self._helper_websocket_routes(ws)
        except WebSocketDisconnect as e:
            await ws.close(code=e.code, reason=e.reason)
        except RuntimeError as e:
            if ws.client_state != WebSocketState.CONNECTED:
                await ws.close(code=403, reason="Connection rejected")
            else:
                await ws.close(code=1011, reason="Unexpected condition")
        except Exception as e:
            await ws.send_text(f"Error: {str(e)}")
            if ws.application_state != WebSocketState.CONNECTED:
                await ws.close(code=1006, reason="Connection closed unexpectedly")
            else:
                await ws.close(code=1011, reason="Unexpected condition")

    async def _websocket_routes(self, ws: WebSocket) -> None:
        for path, path_regex, handler in self.websockets:
            match = path_regex.match(ws.path)
            if match:
                ws.path_params = match.groupdict()
                response = await handler(ws, **ws.path_params)
                if not isinstance(response, WebSocket):
                    received_type = type(response).__name__
                    expected_types = ", ".join([typ.__name__ for typ in [WebSocket]])
                    raise TypeError(f"Invalid response type: Received {received_type}. Expected types are {expected_types}.")
                return response
            
    async def _helper_websocket_routes(self, ws: WebSocket) -> None:
        for path, path_regex, handler in routing._websockets:
            match = path_regex.match(ws.path)
            if match:
                ws.path_params = match.groupdict()
                response = await handler(ws, **ws.path_params)
                if not isinstance(response, WebSocket):
                    received_type = type(response).__name__
                    expected_types = ", ".join([typ.__name__ for typ in [WebSocket]])
                    raise TypeError(f"Invalid response type: Received {received_type}. Expected types are {expected_types}.")
                return response
            
    def _load_exception_handler(self) -> Optional[
        Mapping[
            Any,
            Callable[
                [Request, Exception],
                Union[Response, Awaitable[Response]],
            ],
        ]
    ]:
        exception_handler = getattr(settings, "EXCEPTION_HANDLER", None)

        # Nothing configured
        if not exception_handler:
            self.exception_handlers = None
            return self.exception_handlers

        try:
            # If a string path was provided, import it
            if isinstance(exception_handler, str):
                _handler = import_string(exception_handler)
            # If the setting is a callable (function or class), use it directly
            elif callable(exception_handler):
                _handler = exception_handler
            else:
                raise ImproperlyConfigured(
                    "Invalid EXCEPTION_HANDLER type: expected a string import path or a callable."
                )

            # If a class was provided, instantiate it (instance must be callable)
            if inspect.isclass(_handler):
                instance = _handler()
                if not callable(instance):
                    raise TypeError("Exception handler class must return a callable instance.")
                self.exception_handlers = instance

            # If it's a function/coroutine, ensure it's awaitable by the ASGI flow.
            else:
                # If it's an async function / async generator function, use directly
                if inspect.iscoroutinefunction(_handler) or inspect.isasyncgenfunction(_handler):
                    self.exception_handlers = _handler
                else:
                    # It's a sync callable — wrap it into an async wrapper so callers can `await` it
                    def _sync_wrapper_factory(func):
                        async def _async_wrapper(exc: Exception, request: Request):
                            return func(exc, request)
                        return _async_wrapper

                    self.exception_handlers = _sync_wrapper_factory(_handler)

            return self.exception_handlers

        except ImportError as import_error:
            raise ImproperlyConfigured(
                f"Error importing EXCEPTION_HANDLER '{exception_handler}': {import_error}"
            )
        except ImproperlyConfigured:
            # Let ImproperlyConfigured bubble up with its original message
            raise
        except Exception as e:
            raise ImproperlyConfigured(
                f"An unexpected error occurred while loading EXCEPTION_HANDLER '{exception_handler}': {e}"
            )

        
    async def __call__(
        self, scope: Dict[str, Scope], receive: Callable[..., Awaitable[Receive]], send: Callable[..., Awaitable[Send]]
    ) -> None:
        scope['app'] = self
        if self.schematic is not None:
            scope['schematic'] = self.schematic
        if scope['type'] == 'http':
            await self._http(scope, receive, send)
        elif scope['type'] == 'websocket':
            await self._websocket_handler(scope, receive, send)
        elif scope['type'] == 'lifespan':
            await self._lifespan(scope, receive, send)

    async def _http(
        self,
        scope: Dict[str, Scope],
        receive: Callable[..., Awaitable[Receive]],
        send: Callable[..., Awaitable[Send]]
    ) -> None:
        """HTTP handler with robust error fallback."""
        try:
            await self.handle_request(scope, receive, send)
        except Exception as e:
            try:
                request = Request(scope, receive, send)
                response = await self._process_exception(e, request)
            except Exception as final_e:
                print(f"[CRITICAL] Exception while handling request: {final_e}")
                print(traceback.format_exc())
                response = Response(
                    "Internal Server Error",
                    content_type="text/plain",
                    status_code=500,
                )
            await response(scope, receive, send)

    async def _lifespan(
        self,
        scope: Dict[str, Scope],
        receive: Callable[..., Awaitable[Receive]],
        send: Send
    ) -> Lifespan:
        
        started = False
        event: StatefulLifespan = await receive() 
        try:
            if event['type'] == 'lifespan.startup':
                await self._startup_handlers()
                await send({"type": "lifespan.startup.complete"})
                started = True
                await receive()
        except BaseException:
            exc_text = traceback.format_exc()
            if started:
                await send({"type": "lifespan.shutdown.failed", "message": exc_text})
            else:
                await send({"type": "lifespan.startup.failed", "message": exc_text})
            raise
        else:
            await self._shutdown_handlers()
            await send({"type": "lifespan.shutdown.complete"})

    async def _startup_handlers(self) -> None:
        for handler in self.startup_handlers:
            if not (inspect.iscoroutinefunction(handler) or inspect.isasyncgenfunction(handler)):
                raise TypeError("ASGI can only register asynchronous lifespan functions.")
            await handler()

    async def _shutdown_handlers(self) -> None:
        for handler in self.shutdown_handlers:
            if not (inspect.iscoroutinefunction(handler) or inspect.isasyncgenfunction(handler)):
                raise TypeError("ASGI can only register asynchronous lifespan functions.")
            await handler()

    def _check_events(self, on_startup: Lifespan, on_shutdown: Lifespan):
        if on_startup:
            if isinstance(on_startup, list):
                self.startup_handlers.extend(on_startup)
            else:
                self.startup_handlers.append(on_startup)

        if on_shutdown:
            if isinstance(on_shutdown, list):
                self.shutdown_handlers.extend(on_shutdown)
            else:
                self.shutdown_handlers.append(on_shutdown)

    def _load_lifespan_handlers(self):
        lifespans = settings.LIFESPAN_EVENTS or []
        if lifespans:

            for index, lifespan in enumerate(lifespans):
                origin = lifespan.get('origin')
                if not origin:
                    raise ImproperlyConfigured(f"Lifespan event at index {index} is missing 'origin' key.")
                
                if not (inspect.iscoroutinefunction(origin) or inspect.isasyncgenfunction(origin)):
                    raise TypeError(f"Lifespan event at index {index} must be an asynchronous function.")
                
                event_type = lifespan.get('event')
                if event_type == 'startup':
                    self.startup_handlers.append(origin)
                elif event_type == 'shutdown':
                    self.shutdown_handlers.append(origin)
                else:
                    raise ImproperlyConfigured(f"Lifespan event at index {index} has invalid 'event' type: {event_type}. Expected 'startup' or 'shutdown'.")