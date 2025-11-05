from typing import Any
from settings import settings
from utils.module_loading import import_string


class StageHandler:
    """
    Handles middleware (stage) loading and registration.
    Uses the global 'settings' object instead of dynamically importing settings.py.
    """

    def load_middleware_from_path(self, middleware_path: str) -> Any:
        """
        Dynamically load a middleware class or callable from its import path.
        """
        try:
            middleware = import_string(middleware_path)

            if isinstance(middleware, type):
                return middleware()  # Instantiate class
            return middleware  # If it’s already a function or instance

        except Exception as e:
            raise ImportError(f"Error loading middleware '{middleware_path}': {e}")

    def process_stage_handlers(self, instance: Any) -> None:
        """
        Processes and registers all middleware defined in settings.STAGE_HANDLERS.
        """
        STAGE_HANDLERS = getattr(settings, "STAGE_HANDLERS", None)

        if not STAGE_HANDLERS:
            raise AttributeError("STAGE_HANDLERS not found in settings.")

        for handler in STAGE_HANDLERS:
            middleware_path = handler.get("origin")
            stage = handler.get("stage")

            if not middleware_path:
                raise ValueError("Missing 'origin' in STAGE_HANDLERS entry.")
            if stage not in ("before", "after"):
                raise ValueError(f"Invalid stage '{stage}'. Must be 'before' or 'after'.")

            try:
                middleware_class = self.load_middleware_from_path(middleware_path)

                # Register middleware for the stage
                instance.request_stage_handlers.setdefault(stage, []).append(
                    (
                        middleware_class,
                        handler.get("order", 0),
                        handler.get("conditions", None),
                    )
                )

                # Grouped stage (optional)
                if handler.get("group"):
                    instance.grouped_request_stages \
                        .setdefault(handler["group"], {}) \
                        .setdefault(stage, []).append(middleware_class)

                # Excluded stage (optional)
                if handler.get("exclude"):
                    instance.excluded_stages \
                        .setdefault(handler["exclude"], set()) \
                        .add(middleware_class)

                # Inheritance from group
                if handler.get("inherit"):
                    instance._inherit_from_group(stage, handler.get("group"), handler.get("inherit"))

            except ImportError as e:
                raise ImportError(f"Error processing middleware '{middleware_path}': {e}")
