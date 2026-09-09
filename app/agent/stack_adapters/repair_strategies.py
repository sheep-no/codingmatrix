"""Registry for deterministic, technology-specific repair strategies."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
import hashlib
import json
from typing import Any


RepairFunction = Callable[[str], str | None]
RepairPredicate = Callable[["RepairContext"], bool]


def repair_contract_digest(requirement: str, file_entries: Iterable[str]) -> str:
    """Return the stable input identity used by deterministic repair evidence."""
    payload = {"requirement": requirement, "files": tuple(file_entries)}
    encoded = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def fastapi_crud_repair_applies(context: "RepairContext") -> bool:
    """Match the frozen-file FastAPI CRUD repair scope."""
    requirement = context.requirement.lower()
    frozen_files = _context_files(context)
    if "app.py" in frozen_files and "app/main.py" not in frozen_files:
        return False
    return all(marker in requirement for marker in ("repair the existing", "python", "fastapi", "crud"))


def spring_crud_repair_applies(context: "RepairContext") -> bool:
    requirement = context.requirement.lower()
    planned_types = {path.rsplit("/", 1)[-1][:-5] for path in _context_files(context) if path.endswith(".java")}
    return "java" in requirement and "spring" in requirement and (
        "/api/v1/todos" in requirement
        or {"Todo", "TodoController", "TodoRepository"}.issubset(planned_types)
    )


def flask_crud_repair_applies(context: "RepairContext") -> bool:
    requirement = context.requirement.lower()
    files = _context_files(context)
    if "app/main.py" in files:
        return False
    return all(marker in requirement for marker in ("repair the existing", "python", "flask", "crud"))


def express_crud_repair_applies(context: "RepairContext") -> bool:
    requirement = context.requirement.lower()
    return all(marker in requirement for marker in ("typescript", "express", "crud")) and "src/app.ts" in _context_files(context)


def nestjs_crud_repair_applies(context: "RepairContext") -> bool:
    requirement = context.requirement.lower()
    return all(marker in requirement for marker in ("typescript", "nestjs", "crud")) and "src/main.ts" in _context_files(context)


def go_crud_repair_applies(context: "RepairContext") -> bool:
    requirement = context.requirement.lower()
    return "go" in requirement and "crud" in requirement and "cmd/server/main.go" in _context_files(context)


def pygame_snake_repair_applies(context: "RepairContext") -> bool:
    requirement = context.requirement.lower()
    required = {"main.py", "game/rules.py", "game/renderer.py", "game/input_loop.py", "tests/test_game.py"}
    return "pygame" in requirement and "snake" in requirement and required.issubset(_context_files(context))


def _context_files(context: "RepairContext") -> set[str]:
    if context.file_entries:
        return set(context.file_entries)
    project_context = context.project_context or {}
    return {
        str(path).replace("\\", "/")
        for path in project_context.get("allowed_files", ())
    }


@dataclass(frozen=True)
class StackRepairCandidate:
    """Deterministic repair with traceable selection evidence."""

    strategy: str
    file_path: str
    content: str
    trigger_reason: str
    input_contract_digest: str
    candidate_version: str


@dataclass(frozen=True)
class RepairContext:
    """Immutable project facts available to strategy selection."""

    requirement: str = ""
    file_entries: tuple[str, ...] = ()
    project_context: dict[str, Any] | None = None


@dataclass(frozen=True)
class StackRepairStrategy:
    name: str
    repair: RepairFunction
    applies: RepairPredicate | None = None


class StackRepairStrategyRegistry:
    """Select the first applicable deterministic strategy in stable order."""

    def __init__(self, strategies: Iterable[StackRepairStrategy] = ()) -> None:
        self._strategies = tuple(strategies)
        names = [strategy.name for strategy in self._strategies]
        if len(names) != len(set(names)):
            raise ValueError("repair strategy names must be unique")

    def select(
        self,
        file_path: str,
        context: RepairContext | None = None,
    ) -> tuple[StackRepairStrategy, str] | None:
        for strategy in self._strategies:
            if strategy.applies is not None and not strategy.applies(context or RepairContext()):
                continue
            content = strategy.repair(file_path)
            if content is not None:
                return strategy, content
        return None

    def names(self) -> tuple[str, ...]:
        return tuple(strategy.name for strategy in self._strategies)


__all__ = [
    "RepairFunction",
    "RepairPredicate",
    "RepairContext",
    "repair_contract_digest",
    "fastapi_crud_repair_applies",
    "spring_crud_repair_applies",
    "flask_crud_repair_applies",
    "express_crud_repair_applies",
    "nestjs_crud_repair_applies",
    "go_crud_repair_applies",
    "pygame_snake_repair_applies",
    "StackRepairCandidate",
    "StackRepairStrategy",
    "StackRepairStrategyRegistry",
]
