import re
import threading
from typing import Any, Callable, Dict, Optional, Pattern, Tuple


class ConverterError(Exception):
    pass


class Converter:
    _param_pattern = re.compile(r"{([a-zA-Z_][a-zA-Z0-9_]*)(?::([^}]+))?}")

    _default_converters: Dict[str, Tuple[str, Callable[[str], Any]]] = {
        "str": (r"[^/]+", str),
        "int": (r"\d+", int),
        "float": (r"[0-9]*\.?[0-9]+", float),
        "path": (r".*?", str),
        "uuid": (
            r"[0-9a-fA-F]{8}-"
            r"[0-9a-fA-F]{4}-"
            r"[0-9a-fA-F]{4}-"
            r"[0-9a-fA-F]{4}-"
            r"[0-9a-fA-F]{12}",
            str,
        ),
    }

    _compiled_cache: Dict[str, Tuple[str, Pattern, Dict[str, Callable]]] = {}
    _lock = threading.RLock()

    def __init__(self) -> None:
        self._custom_converters: Dict[str, Tuple[str, Callable]] = {}

    def register_type(self, name: str, regex: str, cast: Callable[[str], Any] = str) -> None:
        if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", name):
            raise ConverterError(f"Invalid converter name: {name!r}")
        if "{" in regex or "}" in regex:
            raise ConverterError("Regex pattern cannot contain braces '{' or '}'.")
        self._custom_converters[name] = (regex, cast)

    def _validate_path(self, path: str) -> None:
        if not path.startswith("/"):
            raise ConverterError("Path must start with '/'.")
        if "//" in path:
            raise ConverterError("Invalid path: consecutive slashes are not allowed.")

    def _normalize_path(self, path: str, strict_slashes: bool) -> str:
        if not strict_slashes and not path.endswith("/"):
            return path + "/?"
        return path

    def _get_converter(self, type_name: Optional[str]) -> Tuple[str, Callable[[str], Any]]:
        if not type_name:
            return self._default_converters["str"]
        return (
            self._custom_converters.get(type_name)
            or self._default_converters.get(type_name)
            or (type_name, str)  # allow direct regex string as type
        )

    def _replace_param(
        self, match: re.Match[str], prefix: str, param_casts: Dict[str, Callable[[str], Any]]
    ) -> str:
        name, type_expr = match.groups()
        if not name.isidentifier():
            raise ConverterError(f"Invalid parameter name: {name}")
        regex, cast = self._get_converter(type_expr)
        param_casts[name] = cast
        return f"{prefix}(?P<{name}>{regex})"

    def _compile_pattern(
        self,
        path: str,
        strict_slashes: bool = True,
        prefix: str = "",
    ) -> Tuple[str, Pattern, Dict[str, Callable]]:
        self._validate_path(path)
        cache_key = f"{path}|{strict_slashes}|{prefix}"

        with self._lock:
            if cache_key in self._compiled_cache:
                return self._compiled_cache[cache_key]

        normalized_path = self._normalize_path(path, strict_slashes)
        param_casts: Dict[str, Callable] = {}

        try:
            pattern_str = self._param_pattern.sub(
                lambda m: self._replace_param(m, prefix, param_casts),
                normalized_path,
            )
            pattern_str = f"^{pattern_str}$"
            compiled = re.compile(pattern_str)
        except re.error as exc:
            raise ConverterError(f"Invalid regex pattern in path: {exc}")

        with self._lock:
            self._compiled_cache[cache_key] = (pattern_str, compiled, param_casts)
        return pattern_str, compiled, param_casts

    def _regex_converter(
        self,
        path: str,
        strict_slashes: bool = True,
        prefix: str = "",
    ) -> Tuple[str, Pattern]:
        pattern, compiled, _ = self._compile_pattern(path, strict_slashes, prefix)
        return pattern, compiled

    def parse(
        self,
        route_path: str,
        request_path: str,
        strict_slashes: bool = True,
    ) -> Optional[Dict[str, Any]]:
        """
        Parse and extract parameters from a given request path using the compiled route pattern.
        Automatically casts parameters to the correct types.
        """
        _, regex, param_casts = self._compile_pattern(route_path, strict_slashes)
        match = regex.match(request_path)
        if not match:
            return None

        raw_params = match.groupdict()
        casted_params = {}

        for name, value in raw_params.items():
            cast_func = param_casts.get(name, str)
            try:
                casted_params[name] = cast_func(value)
            except (ValueError, TypeError):
                raise ConverterError(f"Failed to cast parameter '{name}' to its type.")
        return casted_params
