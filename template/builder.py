import os
import inspect
import typing
import jinja2
from enum import Enum
from typing import Type, Optional, List, Callable, Dict, Any, Union, Sequence
from wrappers.request import Request
from settings.base import settings
from template.jinja2 import Jinja2Template
from utils.module_loading import import_string
from exceptions.config import ImproperlyConfigured
from template.xenarx.xenarx_template import XenarxTemplateResponse

class AvailableTemplates(Enum):
    XENARX = "template.xenarx.XenarxTemplate"
    JINJA2 = "template.jinja2.Jinja2Template"

class TemplateBuilder:
    @staticmethod
    def get_template_backend() -> str:
        templates = getattr(settings, "TEMPLATES", None)
        if not templates:
            raise ImproperlyConfigured("TEMPLATES setting not found")

        _settings = templates[0]
        return _settings.get("BACKEND") or _settings.get("backend")

    @staticmethod
    def validate_template_backend(backend: str) -> None:
        if backend not in AvailableTemplates._value2member_map_:
            raise ValueError(f"Template {backend} not supported by Bermoids!")

    @staticmethod
    def import_template_module(backend: str) -> Type:
        try:
            return import_string(backend)
        except ImportError as e:
            raise ImproperlyConfigured(f"Error importing template module {backend}: {e}")

    @staticmethod
    def build_template() -> Type:
        backend = TemplateBuilder.get_template_backend()
        TemplateBuilder.validate_template_backend(backend)
        return TemplateBuilder.import_template_module(backend)

class TemplateFactory:
    @staticmethod
    def create_template() -> Union[XenarxTemplateResponse, Jinja2Template]:
        template_cls = TemplateBuilder.build_template()
        _settings = getattr(settings, "TEMPLATES", [])[0]
        options = _settings.get("OPTIONS", {})
        directory = _settings.get("DIRS", [])

        context_processors = options.get("context_processors", [])
        extensions = options.get("extensions", [])
        autoscape = options.get("autoscape", True)
        cache_size = options.get("cache_size", 400)
        env = options.get("environment")

        if issubclass(template_cls, XenarxTemplateResponse):
            return XenarxTemplateResponse(
                context_processors=context_processors,
                directory=directory,
                extensions=extensions
            )

        elif issubclass(template_cls, Jinja2Template):
            return Jinja2Template(
                context_processors=context_processors,
                directory=directory,
                env=env,
                extensions=extensions,
                cache_size=cache_size,
                autoscape=autoscape
            )

        raise ImproperlyConfigured(f"Invalid template engine: {template_cls}")