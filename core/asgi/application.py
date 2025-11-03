from __future__ import annotations

import importlib
import importlib.util
import os
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, Dict, List, Optional, Tuple

from settings.base import settings
from core.asgi.middleware import ASGIMiddlewareLoader, ASGIMiddlewareLoaderError

_cached_modules: Dict[str, ModuleType] = {}
_cached_file_specs: Dict[str, ModuleType] = {}

class ASGIEntryError(Exception):
    pass

class ModuleLoadError(ASGIEntryError):
    pass

class EntryPointExtractor:
    def __init__(self, cwd: Optional[str] = None):
        self.cwd = Path(cwd or os.getcwd())

    def _parse_entry_point(self, entry: str) -> Tuple[str, Optional[str]]:
        entry = entry.strip()
        if ":" in entry:
            module_part, var_part = entry.split(":", 1)
        elif "." in entry and not entry.endswith(".py"):
            module_part, var_part = entry.rsplit(".", 1)
        else:
            module_part, var_part = entry, None
        module_part = module_part.strip()
        var_part = var_part.strip() if var_part else None
        return module_part, var_part

    def extract(self) -> Optional[Tuple[str, Optional[str]]]:
        env_ep = os.environ.get("ENTRY_POINT")
        if env_ep:
            return self._parse_entry_point(env_ep)
        ep = getattr(settings, "ENTRY_POINT", None)
        if ep:
            return self._parse_entry_point(str(ep))
        return None

class ASGI:
    @staticmethod
    def _is_file_path(module_str: str) -> bool:
        p = Path(module_str)
        return p.exists() and p.suffix in {".py", ""}

    @staticmethod
    def _load_module_from_file(path: str) -> ModuleType:
        abs_path = str(Path(path).resolve())
        if abs_path in _cached_file_specs:
            return _cached_file_specs[abs_path]
        spec = importlib.util.spec_from_file_location(Path(abs_path).stem, abs_path)
        if spec is None or spec.loader is None:
            raise ModuleLoadError(f"cannot create spec for file {abs_path!r}")
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)  # type: ignore[attr-defined]
        except Exception as exc:
            raise ModuleLoadError(f"failed executing file {abs_path!r}: {exc}") from exc
        _cached_file_specs[abs_path] = module
        sys.modules[module.__name__] = module
        return module

    @staticmethod
    def _import_module(module_str: str) -> ModuleType:
        if module_str in _cached_modules:
            return _cached_modules[module_str]
        if ASGI._is_file_path(module_str):
            module = ASGI._load_module_from_file(module_str)
            _cached_modules[module_str] = module
            return module
        try:
            module = importlib.import_module(module_str)
            _cached_modules[module_str] = module
            return module
        except Exception as exc:
            raise ModuleLoadError(f"could not import module {module_str!r}: {exc}") from exc

    @staticmethod
    def _get_attr(module: ModuleType, attr: Optional[str]) -> Any:
        if not attr:
            return module
        if hasattr(module, attr):
            return getattr(module, attr)
        raise ASGIEntryError(f"attribute {attr!r} not found in module {module.__name__}")

    @staticmethod
    def _apply_middlewares_with_loader(app: Any, loader: ASGIMiddlewareLoader) -> Tuple[Any, Dict[str, Any]]:
        diag: Dict[str, Any] = {}
        if hasattr(loader, "build_middleware_stack"):
            try:
                new_app = loader.build_middleware_stack(app)
                diag["method"] = "build_middleware_stack"
                diag["result"] = "ok"
                return new_app, diag
            except Exception as exc:
                diag["method"] = "build_middleware_stack"
                diag["error"] = str(exc)
                raise ASGIMiddlewareLoaderError(f"build_middleware_stack failed: {exc}") from exc
        if hasattr(loader, "resolve_factories") and hasattr(loader, "load_specs"):
            try:
                resolved = loader.resolve_factories()
                for spec, factory in resolved:
                    options = getattr(spec, "options", {}) if hasattr(spec, "options") else {}
                    try:
                        app = factory(app, **(options or {}))
                    except TypeError:
                        app = factory(app)
                diag["method"] = "resolve_factories"
                diag["result"] = "ok"
                return app, diag
            except Exception as exc:
                diag["method"] = "resolve_factories"
                diag["error"] = str(exc)
                raise
        if hasattr(loader, "load_asgi_middlewares"):
            try:
                middlewares = loader.load_asgi_middlewares()
                for m in middlewares:
                    if callable(m):
                        try:
                            app = m(app)
                        except TypeError:
                            app = m(app)
                    else:
                        raise ASGIMiddlewareLoaderError(f"middleware {m!r} is not callable")
                diag["method"] = "load_asgi_middlewares"
                diag["result"] = "ok"
                return app, diag
            except Exception as exc:
                diag["method"] = "load_asgi_middlewares"
                diag["error"] = str(exc)
                raise
        raise ASGIMiddlewareLoaderError("ASGIMiddlewareLoader has no supported API")

    @staticmethod
    def application() -> Any:
        ep = EntryPointExtractor().extract()
        if not ep:
            raise ASGIEntryError("no ENTRY_POINT found in env or settings")
        module_part, var_part = ep
        try:
            module = ASGI._import_module(module_part)
        except ModuleLoadError:
            if ASGI._is_file_path(module_part):
                try:
                    module = ASGI._load_module_from_file(module_part)
                except ModuleLoadError as exc:
                    raise ModuleLoadError(f"could not load entry module from file {module_part!r}: {exc}") from exc
            else:
                raise
        try:
            app_obj = ASGI._get_attr(module, var_part)
        except ASGIEntryError as exc:
            raise ASGIEntryError(f"failed to retrieve application object: {exc}") from exc
        loader = ASGIMiddlewareLoader(settings_obj=settings)
        try:
            app_obj, diag = ASGI._apply_middlewares_with_loader(app_obj, loader)
        except ASGIMiddlewareLoaderError as exc:
            raise ASGIEntryError(f"failed applying ASGI middlewares: {exc}") from exc
        return app_obj
