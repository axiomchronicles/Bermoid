"""
Settings management system
"""
import os
import importlib.util
from typing import Any, Dict, Optional
from pathlib import Path


class Settings:
    """
    Settings container
    """

    # Default settings
    DEBUG = False
    SECRET_KEY = "default-secret-key-change-in-production"
    ALLOWED_HOSTS = ["*"]

    # Application
    INSTALLED_APPS = []
    ROOT_URLCONF = None

    # Middleware
    MIDDLEWARE = []

    # Database (placeholder for future)
    DATABASES = {}

    # Static/Media files
    STATIC_URL = "/static/"
    STATIC_ROOT = None
    MEDIA_URL = "/media/"
    MEDIA_ROOT = None

    # Templates
    TEMPLATES = []

    # Security
    CORS_ALLOW_ALL_ORIGINS = False
    CORS_ALLOWED_ORIGINS = []

    # Lifespan
    STARTUP_HANDLERS = []
    SHUTDOWN_HANDLERS = []

    def __init__(self, settings_module: Optional[str] = None):
        if settings_module:
            self.load_from_module(settings_module)

    def load_from_module(self, module_path: str):
        """
        Load settings from Python module

        Args:
            module_path: Path to settings module (e.g., 'myproject.settings')
        """
        # Try to import as module path first
        try:
            module = importlib.import_module(module_path)
        except ImportError:
            # Try as file path
            if os.path.exists(module_path):
                spec = importlib.util.spec_from_file_location("settings", module_path)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
            else:
                raise ImportError(f"Cannot import settings module: {module_path}")

        # Copy settings
        for key in dir(module):
            if key.isupper():
                setattr(self, key, getattr(module, key))

    def __getitem__(self, key: str) -> Any:
        """Dict-style access"""
        return getattr(self, key)

    def __setitem__(self, key: str, value: Any):
        """Dict-style setting"""
        setattr(self, key, value)

    def get(self, key: str, default: Any = None) -> Any:
        """Get with default"""
        return getattr(self, key, default)


# Global settings instance
_settings: Optional[Settings] = None


def configure(settings_module: Optional[str] = None, **kwargs):
    """
    Configure global settings

    Args:
        settings_module: Path to settings module
        **kwargs: Direct settings override
    """
    global _settings

    _settings = Settings(settings_module)

    # Apply overrides
    for key, value in kwargs.items():
        setattr(_settings, key, value)


def get_settings() -> Settings:
    """
    Get global settings instance
    """
    if _settings is None:
        raise RuntimeError("Settings not configured. Call configure() first.")
    return _settings