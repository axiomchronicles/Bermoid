import importlib
import importlib.util
import os
import threading
from types import ModuleType
from typing import Any

from exceptions.config import ImproperlyConfigured

class LazySettings:

    _wrapped: ModuleType | None = None
    _lock = threading.Lock()

    def __init__(self, default_settings_path: str | None = None):
        self.default_settings_path = default_settings_path
        self._explicit_settings_path = None

    # ---- Public API ----
    def configure(self, settings_path: str):
        """Manually configure settings from a specific file."""
        with self._lock:
            if self._wrapped is not None:
                raise RuntimeError("Settings already configured. Use `reload()` to reset.")
            self._explicit_settings_path = settings_path
            self._setup()

    def is_configured(self) -> bool:
        return self._wrapped is not None

    def reload(self):
        """Reload settings module (useful for development)."""
        with self._lock:
            self._wrapped = None
            self._setup(force=True)

    # ---- Internals ----
    def _setup(self, force=False):
        """Load the actual settings module."""
        if self._wrapped is not None and not force:
            return

        settings_path = (
            self._explicit_settings_path
            or os.environ.get("BERMOID_SETTINGS_MODULE")
            or self.default_settings_path
            or "./settings.py"
        )

        if not os.path.exists(settings_path):
            raise ImproperlyConfigured(
                f"Cannot find settings file: {settings_path!r}. "
                f"Set BERMOID_SETTINGS_MODULE or pass path explicitly."
            )

        spec = importlib.util.spec_from_file_location("bermoid_user_settings", settings_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        env = getattr(module, "ENVIRONMENT", None)
        if env:
            env_path = os.path.join(os.path.dirname(settings_path), f"{env}.py")
            if os.path.exists(env_path):
                env_spec = importlib.util.spec_from_file_location(f"bermoid_{env}_settings", env_path)
                env_module = importlib.util.module_from_spec(env_spec)
                env_spec.loader.exec_module(env_module)
                for key in dir(env_module):
                    if key.isupper():
                        setattr(module, key, getattr(env_module, key))

        self._wrapped = module

    # ---- Attribute Access ----
    def __getattr__(self, name: str) -> Any:
        if self._wrapped is None:
            self._setup()

        try:
            return getattr(self._wrapped, name)
        except AttributeError:
            raise ImproperlyConfigured(f"Missing setting: '{name}' in your settings module.")

    def __setattr__(self, name, value):
        # Allow normal attributes to be set before configuration
        if name in {"_wrapped", "_lock", "_explicit_settings_path", "default_settings_path"}:
            super().__setattr__(name, value)
        elif self._wrapped is None:
            super().__setattr__(name, value)
        else:
            raise TypeError("Settings are read-only once configured.")

    def __repr__(self):
        if self._wrapped is None:
            return "<BermoidSettings [Lazy - not configured]>"
        return f"<BermoidSettings from {self._wrapped.__file__}>"


settings = LazySettings()
