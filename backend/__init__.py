"""Client backend package (lazy exports so `import backend.links...` does not require aiohttp)."""

from __future__ import annotations

from typing import Any

__all__ = ["HOST", "PORT", "create_app", "create_ssl_context"]


def __getattr__(name: str) -> Any:
    if name == "create_app":
        from .main import create_app

        return create_app
    if name in ("HOST", "PORT", "create_ssl_context"):
        from . import config

        return getattr(config, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
