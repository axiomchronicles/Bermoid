from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple, Union, Literal
from importlib import import_module
from settings.base import settings
import inspect

MiddlewareInput = Union[str, Callable[..., Any], Dict[str, Any]]
Stage = Literal['pre', 'post', 'both']

class ASGIMiddlewareLoaderError(Exception):
    pass

class ASGIMiddlewareResolveError(ASGIMiddlewareLoaderError):
    pass

@dataclass(frozen=True)
class _MiddlewareSpec:
    name: Optional[str]
    dotted: Optional[str]
    factory: Optional[Callable[..., Any]]
    stage: Stage = 'both'
    order: int = 0
    options: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if (self.factory is None) and (not self.dotted):
            raise ASGIMiddlewareResolveError("middleware spec must provide either a callable or a dotted path")
        if self.stage not in ('pre', 'post', 'both'):
            raise ASGIMiddlewareResolveError(f"invalid stage {self.stage!r}")
        try:
            object.__setattr__(self, "order", int(self.order))
        except Exception:
            raise ASGIMiddlewareResolveError(f"order must be int-like, got {self.order!r}")

class ASGIMiddlewareLoader:
    def __init__(self, settings_obj: Optional[Any] = None):
        self.settings = settings_obj or settings
        self._cache: Dict[str, Callable[..., Any]] = {}
        self.diagnostics: List[Dict[str, Any]] = []

    def _iter_raw(self) -> Iterable[MiddlewareInput]:
        raw = getattr(self.settings, 'ASGI_MIDDLEWARES', []) or []
        if not isinstance(raw, (list, tuple)):
            raise ASGIMiddlewareLoaderError("ASGI_MIDDLEWARES must be a list or tuple")
        for item in raw:
            yield item

    def _normalize(self, item: MiddlewareInput) -> _MiddlewareSpec:
        if callable(item):
            return _MiddlewareSpec(name=getattr(item, "__name__", None), dotted=None, factory=item)
        if isinstance(item, str):
            return _MiddlewareSpec(name=item, dotted=item, factory=None)
        if isinstance(item, dict):
            dotted = item.get('dotted') or item.get('path') or item.get('import')
            factory = item.get('callable') or item.get('factory')
            name = item.get('name') or (dotted if dotted else getattr(factory, "__name__", None))
            stage = item.get('stage', 'both')
            order = item.get('order', 0)
            options = dict(item.get('options', {}) or {})
            return _MiddlewareSpec(name=name, dotted=dotted, factory=factory, stage=stage, order=order, options=options)
        raise ASGIMiddlewareLoaderError(f"unsupported middleware entry type: {type(item)!r}")

    def _resolve_dotted(self, dotted: str) -> Callable[..., Any]:
        if dotted in self._cache:
            return self._cache[dotted]
        try:
            module_path, attr = dotted.rsplit('.', 1)
        except ValueError:
            raise ASGIMiddlewareResolveError(f"invalid dotted path: {dotted!r}")
        try:
            module = import_module(module_path)
        except Exception as exc:
            raise ASGIMiddlewareResolveError(f"cannot import module {module_path!r}: {exc}") from exc
        try:
            obj = getattr(module, attr)
        except AttributeError as exc:
            raise ASGIMiddlewareResolveError(f"{module_path!r} has no attribute {attr!r}") from exc
        if not callable(obj):
            raise ASGIMiddlewareResolveError(f"resolved object {dotted!r} is not callable")
        self._cache[dotted] = obj
        return obj

    def load_specs(self) -> List[_MiddlewareSpec]:
        specs: List[_MiddlewareSpec] = []
        self.diagnostics.clear()
        for raw in self._iter_raw():
            try:
                spec = self._normalize(raw)
                specs.append(spec)
                self.diagnostics.append({'entry': raw, 'status': 'ok', 'spec': spec})
            except Exception as exc:
                self.diagnostics.append({'entry': raw, 'status': 'error', 'error': str(exc)})
                raise ASGIMiddlewareLoaderError(f"invalid middleware entry {raw!r}: {exc}") from exc
        return specs

    def resolve_factories(self) -> List[Tuple[_MiddlewareSpec, Callable[..., Any]]]:
        specs = self.load_specs()
        resolved: List[Tuple[_MiddlewareSpec, Callable[..., Any]]] = []
        for spec in specs:
            try:
                if spec.factory is not None:
                    resolved.append((spec, spec.factory))
                    continue
                factory = self._resolve_dotted(spec.dotted)  # type: ignore[arg-type]
                resolved.append((spec, factory))
            except Exception as exc:
                self.diagnostics.append({'spec': spec, 'status': 'resolve_error', 'error': str(exc)})
                raise
        return resolved

    @staticmethod
    def _call_accepts_kwargs(fn: Callable[..., Any]) -> bool:
        try:
            sig = inspect.signature(fn)
            for p in sig.parameters.values():
                if p.kind == inspect.Parameter.VAR_KEYWORD:
                    return True
            return False
        except Exception:
            return True

    @staticmethod
    def _wrap_with_options(factory: Callable[..., Any], app: Any, options: Dict[str, Any]) -> Any:
        if options:
            if ASGIMiddlewareLoader._call_accepts_kwargs(factory):
                return factory(app, **options)
            try:
                return factory(app)
            except TypeError:
                return factory(app, **options)
        else:
            return factory(app)

    def build_middleware_stack(self, app: Any) -> Any:
        resolved = self.resolve_factories()
        pre_both = [t for t in resolved if t[0].stage in ('pre', 'both')]
        post = [t for t in resolved if t[0].stage == 'post']
        pre_both.sort(key=lambda x: x[0].order)
        post.sort(key=lambda x: x[0].order)
        for spec, factory in pre_both:
            try:
                app = self._wrap_with_options(factory, app, spec.options)
                self.diagnostics.append({'spec': spec, 'applied': True, 'stage': 'pre/both'})
            except Exception as exc:
                self.diagnostics.append({'spec': spec, 'applied': False, 'stage': 'pre/both', 'error': str(exc)})
                raise ASGIMiddlewareLoaderError(f"error applying middleware {spec.name or spec.dotted}: {exc}") from exc
        for spec, factory in post:
            try:
                app = self._wrap_with_options(factory, app, spec.options)
                self.diagnostics.append({'spec': spec, 'applied': True, 'stage': 'post'})
            except Exception as exc:
                self.diagnostics.append({'spec': spec, 'applied': False, 'stage': 'post', 'error': str(exc)})
                raise ASGIMiddlewareLoaderError(f"error applying middleware {spec.name or spec.dotted}: {exc}") from exc
        return app

    def get_diagnostics(self) -> List[Dict[str, Any]]:
        return list(self.diagnostics)
