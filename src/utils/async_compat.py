"""Async compatibility helpers for sync/async adapter edges."""

from __future__ import annotations

import inspect
from typing import Any


async def maybe_await(result: Any) -> Any:
    """Await value when awaitable, otherwise return as-is.

    Useful for test doubles or adapter objects that may expose async variants
    of normally sync SQLAlchemy APIs (e.g. ``session.add``).
    """
    if inspect.isawaitable(result):
        return await result
    return result
