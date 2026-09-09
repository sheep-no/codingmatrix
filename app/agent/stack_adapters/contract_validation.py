"""Stack-owned contract validation boundary for generated artifacts."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import PurePosixPath


ContractRule = Callable[[str, str], Iterable[str]]


def contracts_from_openapi(context: object) -> dict[str, list[dict[str, str]]]:
    """Project generated OpenAPI facts into the stack-neutral route shape."""
    get_spec = getattr(context, "get_spec", None)
    openapi = get_spec("openapi") if callable(get_spec) else None
    if not isinstance(openapi, Mapping):
        return {}
    paths = openapi.get("paths")
    if not isinstance(paths, Mapping):
        return {}
    routes: list[dict[str, str]] = []
    for path, operations in paths.items():
        if not isinstance(path, str) or not isinstance(operations, Mapping):
            continue
        for method, operation in operations.items():
            if method.lower() not in {"get", "post", "put", "patch", "delete", "head", "options"}:
                continue
            operation = operation if isinstance(operation, Mapping) else {}
            routes.append({
                "method": method.upper(),
                "path": path,
                "operation_id": str(operation.get("operationId", "")),
            })
    return {"routes": routes} if routes else {}


@dataclass(frozen=True)
class StackContractRule:
    """A validation callback with explicit stack and file applicability."""

    name: str
    stack_ids: frozenset[str]
    extensions: frozenset[str] = frozenset()
    roles: frozenset[str] = frozenset()
    callback: ContractRule | None = None

    def matches(self, file_path: str, role: str | None = None) -> bool:
        suffix = PurePosixPath(file_path).suffix.lower()
        if self.extensions and suffix not in self.extensions:
            return False
        return not self.roles or role in self.roles


class StackContractValidator:
    """Aggregate stack rules without coupling the scheduler to a framework."""

    def __init__(
        self,
        rules: Iterable[ContractRule | StackContractRule] = (),
        *,
        stack_id: str | None = None,
    ) -> None:
        self._rules = tuple(rules)
        self._stack_id = stack_id

    def validate(
        self,
        file_path: str,
        content: str,
        *,
        stack_id: str | None = None,
        role: str | None = None,
    ) -> tuple[str, ...]:
        diagnostics: list[str] = []
        active_stack = stack_id or self._stack_id
        for rule in self._rules:
            if isinstance(rule, StackContractRule):
                if active_stack not in rule.stack_ids or not rule.matches(file_path, role):
                    continue
                if rule.callback is None:
                    continue
                callback = rule.callback
            else:
                callback = rule
            diagnostics.extend(str(item) for item in callback(file_path, content))
        return tuple(diagnostics)


__all__ = [
    "ContractRule",
    "StackContractRule",
    "StackContractValidator",
    "contracts_from_openapi",
]
