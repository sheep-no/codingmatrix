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
from .contract_validation import ContractRule, StackContractRule, StackContractValidator
from .repair_strategies import (
    RepairFunction,
    RepairContext,
    RepairPredicate,
    fastapi_crud_repair_applies,
    spring_crud_repair_applies,
    flask_crud_repair_applies,
    express_crud_repair_applies,
    nestjs_crud_repair_applies,
    go_crud_repair_applies,
    pygame_snake_repair_applies,
    repair_contract_digest,
    StackRepairStrategy,
    StackRepairStrategyRegistry,
)

__all__ = [
    "DEFAULT_STACK_ADAPTERS",
    "BaseStackAdapter",
    "ContractRule",
    "ExpressStackAdapter",
    "FastAPIStackAdapter",
    "GoStackAdapter",
    "RepairContext",
    "RepairFunction",
    "RepairPredicate",
    "ScaffoldResult",
    "SpringStackAdapter",
    "StackAdapter",
    "StackAdapterRegistry",
    "StackArtifactRequest",
    "StackChangeRequest",
    "StackContractRule",
    "StackContractValidator",
    "StackRepairStrategy",
    "StackRepairStrategyRegistry",
    "SymbolIndex",
    "SymbolRecord",
    "UnsupportedStackError",
    "express_crud_repair_applies",
    "fastapi_crud_repair_applies",
    "flask_crud_repair_applies",
    "go_crud_repair_applies",
    "nestjs_crud_repair_applies",
    "pygame_snake_repair_applies",
    "repair_contract_digest",
    "spring_crud_repair_applies",
]
