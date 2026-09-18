"""Request-scoped ModelGateway binding for budgeted Core model calls.

The Core generation path installs a scope around each file's generation task so
that model calls made by shared specialist clients run through the gateway under
that file's execution budget. The scope travels in a ContextVar, which keeps
concurrent file generation tasks isolated even though the engineer instances and
their LLM clients are shared.
"""

from __future__ import annotations

import contextvars
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterator, Optional


@dataclass(frozen=True)
class ModelCallScope:
    """Gateway binding and budget for model calls inside one generation task."""

    gateway: Any
    budget: Any
    task_id: str
    stage_id: str
    file_path: Optional[str] = None
    file_elapsed_seconds: float = 0.0


_current_scope: "contextvars.ContextVar[Optional[ModelCallScope]]" = contextvars.ContextVar(
    "model_call_scope", default=None
)


def current_model_call_scope() -> Optional[ModelCallScope]:
    """Return the active model call scope, or None when the caller is unbudgeted."""
    return _current_scope.get()


@contextmanager
def model_call_scope(scope: ModelCallScope) -> Iterator[ModelCallScope]:
    token = _current_scope.set(scope)
    try:
        yield scope
    finally:
        _current_scope.reset(token)
