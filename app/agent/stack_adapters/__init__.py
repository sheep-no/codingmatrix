"""Technology-specific adapters for the constrained synthesis control plane."""

from .adapters import (
    ExpressStackAdapter,
    FastAPIStackAdapter,
    GoStackAdapter,
    SpringStackAdapter,
)
from .base import (
    BaseStackAdapter,
    ScaffoldResult,
    StackAdapter,
    StackArtifactRequest,
    StackChangeRequest,
    SymbolIndex,
    SymbolRecord,
    UnsupportedStackError,
)
from .registry import DEFAULT_STACK_ADAPTERS, StackAdapterRegistry

__all__ = [
    "BaseStackAdapter",
    "DEFAULT_STACK_ADAPTERS",
    "ExpressStackAdapter",
    "FastAPIStackAdapter",
    "GoStackAdapter",
    "ScaffoldResult",
    "SpringStackAdapter",
    "StackAdapter",
    "StackAdapterRegistry",
    "StackArtifactRequest",
    "StackChangeRequest",
    "SymbolIndex",
    "SymbolRecord",
    "UnsupportedStackError",
]
