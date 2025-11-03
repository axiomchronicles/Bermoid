from __future__ import annotations

import importlib
import importlib.util
import inspect
import os
from pathlib import Path
from types import ModuleType
from typing import Any, Dict, Optional, Tuple, Union

from settings.base import settings

_cached_modules: Dict[str, ModuleType] = {}
_cached_file_specs: Dict[str, ModuleType] = {}

class RouterError(RuntimeError):
    pass

class RouterNotFoundError(RouterError):
    pass

class RouterAttributeError(RouterError):
    pass

class RouterLoadError(RouterError):
    pass

class Router:
    _diagnostics: Dict[str, Any] = {}

    @staticmethod
    def _parse_spec(spec: str) -> Tuple[str, Optional[str]]:
        spec = spec.strip()
        if ":" in spec:
            module_part, attr = spec.split(":", 1)
        elif "." in spec and not Path(spec).exists():
            module_part, attr = spec.rsplit(".", 1)
        else:
            module_part, attr = spec, None
        module_part = module_part.strip()
        attr = attr.strip() if attr else None
        return module_part, attr

    @staticmethod
    def _is_file_path(s: str) -> bool:
        p = Path(s)
        return p.exists() and p.suffix in {".py", ""}

    @staticmethod
    def _load_module_from_file(path: str) -> ModuleType:
        abs_path = str(Path(path).resolve())
        if abs_path in _cached_file_specs:
            Router._diagnostics.setdefault("cache", []).append({"file": abs_path, "action": "hit"})
            return _cached_file_specs[abs_path]
        spec = importlib.util.spec_from_file_location(Path(abs_path).stem, abs_path)
        if spec is None or spec.loader is None:
            raise RouterLoadError(f"cannot create module spec for file {abs_path!r}")
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)  # type: ignore[attr-defined]
        except Exception as exc:
            raise RouterLoadError(f"failed executing file {abs_path!r}: {exc}") from exc
        _cached_file_specs[abs_path] = module
        _cached_modules[module.__name__] = module
        Router._diagnostics.setdefault("loaded_files", []).append(abs_path)
        return module

    @staticmethod
    def _import_module(module_str: str) -> ModuleType:
        if module_str in _cached_modules:
            Router._diagnostics.setdefault("cache", []).append({"module": module_str, "action": "hit"})
            return _cached_modules[module_str]
        try:
            module = importlib.import_module(module_str)
            _cached_modules[module_str] = module
            Router._diagnostics.setdefault("loaded_modules", []).append(module_str)
            return module
        except Exception as exc:
            raise RouterLoadError(f"could not import module {module_str!r}: {exc}") from exc

    @staticmethod
    def _get_obj_from_module(module: ModuleType, attr: Optional[str]) -> Any:
        if attr is None:
            return module
        if hasattr(module, attr):
            return getattr(module, attr)
        raise RouterAttributeError(f"attribute {attr!r} not found in module {module.__name__}")

    @staticmethod
    def _maybe_call_factory(obj: Any) -> Any:
        if not callable(obj):
            return obj
        try:
            sig = inspect.signature(obj)
            if not sig.parameters:
                return obj()
            if len(sig.parameters) == 1:
                name, param = next(iter(sig.parameters.items()))
                if param.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD):
                    return obj(settings)
            if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()):
                return obj(settings=settings)
        except Exception:
            pass
        try:
            return obj()
        except Exception as exc:
            raise RouterLoadError(f"router factory callable raised: {exc}") from exc

    @classmethod
    def finalize(cls) -> Any:
        cls._diagnostics.clear()
        ep = os.environ.get("ENTRY_ROUTER")
        if not ep:
            ep = getattr(settings, "ENTRY_ROUTER", None)
        spec_str = (ep or getattr(settings, "ROUTER_MODULE", None) or "routing.py")
        cls._diagnostics["requested_spec"] = spec_str
        module_part, attr = cls._parse_spec(str(spec_str))
        module: ModuleType
        try:
            if cls._is_file_path(module_part) or Path(module_part).suffix == ".py":
                module = cls._load_module_from_file(module_part)
            else:
                module = cls._import_module(module_part)
        except RouterLoadError as exc:
            raise RouterNotFoundError(f"failed loading router module {module_part!r}: {exc}") from exc
        try:
            candidate = cls._get_obj_from_module(module, attr)
        except RouterAttributeError as exc:
            raise RouterAttributeError(f"router attribute not found: {exc}") from exc
        try:
            router = cls._maybe_call_factory(candidate)
        except RouterLoadError:
            raise
        cls._diagnostics["resolved_from"] = getattr(module, "__name__", module_part)
        cls._diagnostics["attribute"] = attr
        cls._diagnostics["router_type"] = type(router).__name__
        return router

    @classmethod
    def get_diagnostics(cls) -> Dict[str, Any]:
        return dict(cls._diagnostics)
