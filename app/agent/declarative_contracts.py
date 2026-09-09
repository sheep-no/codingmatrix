"""Versioned, technology-neutral contract facts and comparison gate."""

from __future__ import annotations

from enum import Enum
from typing import Any, Mapping, Protocol, Tuple

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ComparisonOperator(str, Enum):
    EQUALS = "equals"
    CONTAINS_ALL = "contains_all"
    EXCLUDES_ALL = "excludes_all"


class ContractAssertion(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    fact: str = Field(min_length=1)
    operator: ComparisonOperator
    expected: Tuple[str, ...] = ()
    reference: str = ""


class ContractDeclaration(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: int = Field(default=1, ge=1)
    assertions: Tuple[ContractAssertion, ...] = ()

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any] | None) -> "ContractDeclaration":
        if not payload:
            return cls()
        declaration = payload.get("declaration", payload)
        if not isinstance(declaration, Mapping) or "assertions" not in declaration:
            return cls()
        return cls.model_validate(declaration)


class FactSet(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1)
    values: Tuple[str, ...] = ()


class ArtifactFacts(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: int = Field(default=1, ge=1)
    facts: Tuple[FactSet, ...] = ()

    @model_validator(mode="after")
    def validate_unique_names(self) -> "ArtifactFacts":
        names = [fact.name for fact in self.facts]
        if len(names) != len(set(names)):
            raise ValueError("artifact fact names must be unique")
        return self

    @classmethod
    def build(cls, values: Mapping[str, Tuple[str, ...] | list[str] | set[str]]) -> "ArtifactFacts":
        facts = tuple(
            FactSet(name=name, values=tuple(sorted({str(value) for value in items})))
            for name, items in sorted(values.items())
        )
        return cls(facts=facts)

    def values_for(self, name: str) -> Tuple[str, ...] | None:
        return next((fact.values for fact in self.facts if fact.name == name), None)


class SymbolContract(BaseModel):
    """Language-neutral imports, exports, and fixture requirements."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: int = Field(default=1, ge=1)
    artifact: str = Field(min_length=1)
    provides: Tuple[str, ...] = ()
    requires: Tuple[str, ...] = ()
    required_fixtures: Tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_symbols(self) -> "SymbolContract":
        for name, values in (
            ("provides", self.provides),
            ("requires", self.requires),
            ("required_fixtures", self.required_fixtures),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"{name} must contain unique symbols")
        return self

    @classmethod
    def build(
        cls,
        artifact: str,
        *,
        provides: Tuple[str, ...] | list[str] | set[str] = (),
        requires: Tuple[str, ...] | list[str] | set[str] = (),
        required_fixtures: Tuple[str, ...] | list[str] | set[str] = (),
    ) -> "SymbolContract":
        return cls(
            artifact=artifact,
            provides=tuple(sorted({str(value) for value in provides if str(value)})),
            requires=tuple(sorted({str(value) for value in requires if str(value)})),
            required_fixtures=tuple(sorted({str(value) for value in required_fixtures if str(value)})),
        )


def missing_symbols(
    contract: SymbolContract,
    provided: ArtifactFacts | Mapping[str, Any],
) -> Tuple[str, ...]:
    """Return unresolved required symbols without interpreting source syntax."""
    if isinstance(provided, ArtifactFacts):
        exported = set(provided.values_for("symbols") or ())
    else:
        exported = {str(value) for value in (provided.get("symbols", ()) or ())}
    return tuple(sorted(set(contract.requires) - exported))


class GateStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    UNSUPPORTED = "unsupported"


class GateDiagnostic(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    fact: str = Field(min_length=1)
    reference: str = ""
    expected: Tuple[str, ...] = ()
    actual: Tuple[str, ...] = ()


class ContractGateResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: GateStatus
    diagnostics: Tuple[GateDiagnostic, ...] = ()

    @property
    def passed(self) -> bool:
        return self.status is GateStatus.PASSED


class SourceAdapter(Protocol):
    def extract_contract_facts(self, content: str, file_path: str = "") -> Mapping[str, Tuple[str, ...]]: ...
    def parse_imports(self, content: str, file_path: str = "") -> list[Any]: ...
    def resolve_import_to_file(self, import_info: Any, current_file: str) -> list[str]: ...
    def is_project_module(self, module_name: str) -> bool: ...
    def source_diagnostics(self, content: str, file_path: str = "") -> Tuple[str, ...]: ...
    def repair_source(self, content: str, file_path: str, diagnostics: Tuple[str, ...]) -> str | None: ...


class CandidateValidation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    facts: ArtifactFacts
    gate: ContractGateResult
    diagnostics: Tuple[str, ...] = ()

    @property
    def passed(self) -> bool:
        return self.gate.passed and not self.diagnostics


def compare_contract(
    declaration: ContractDeclaration,
    facts: ArtifactFacts,
) -> ContractGateResult:
    """Compare declared operands without interpreting their technology semantics."""
    diagnostics: list[GateDiagnostic] = []
    unsupported = False
    for assertion in declaration.assertions:
        actual_values = facts.values_for(assertion.fact)
        if actual_values is None:
            unsupported = True
            diagnostics.append(GateDiagnostic(
                code="contract.fact_unsupported",
                message=f"no parser capability produced fact: {assertion.fact}",
                fact=assertion.fact,
                reference=assertion.reference,
                expected=assertion.expected,
            ))
            continue

        actual = set(actual_values)
        expected = set(assertion.expected)
        if assertion.operator is ComparisonOperator.EQUALS:
            matched = actual == expected
        elif assertion.operator is ComparisonOperator.CONTAINS_ALL:
            matched = expected <= actual
        else:
            matched = actual.isdisjoint(expected)
        if matched:
            continue
        diagnostics.append(GateDiagnostic(
            code="contract.assertion_failed",
            message=(
                f"contract assertion failed for {assertion.fact}: "
                f"{assertion.operator.value} {sorted(expected)}"
            ),
            fact=assertion.fact,
            reference=assertion.reference,
            expected=tuple(sorted(expected)),
            actual=tuple(sorted(actual)),
        ))

    if unsupported:
        status = GateStatus.UNSUPPORTED
    elif diagnostics:
        status = GateStatus.FAILED
    else:
        status = GateStatus.PASSED
    return ContractGateResult(status=status, diagnostics=tuple(diagnostics))


def validate_candidate(
    adapter: SourceAdapter,
    file_path: str,
    content: str,
    declaration: ContractDeclaration,
    planned_contents: Mapping[str, str],
) -> CandidateValidation:
    """Validate one candidate from parser facts, declarations, and the frozen set."""
    facts = ArtifactFacts.build(adapter.extract_contract_facts(content, file_path))
    gate = compare_contract(declaration, facts)
    diagnostics = list(adapter.source_diagnostics(content, file_path))
    diagnostics.extend(
        _dependency_diagnostics(adapter, file_path, content, planned_contents)
    )
    diagnostics.extend(item.message for item in gate.diagnostics)
    return CandidateValidation(
        facts=facts,
        gate=gate,
        diagnostics=tuple(dict.fromkeys(diagnostics)),
    )


def _dependency_diagnostics(
    adapter: SourceAdapter,
    file_path: str,
    content: str,
    planned_contents: Mapping[str, str],
) -> Tuple[str, ...]:
    planned_paths = set(planned_contents)
    diagnostics: list[str] = []
    for import_info in adapter.parse_imports(content, file_path):
        candidates = tuple(
            candidate.replace("\\", "/")
            for candidate in adapter.resolve_import_to_file(import_info, file_path)
        )
        targets = tuple(candidate for candidate in candidates if candidate in planned_paths)
        is_local = bool(getattr(import_info, "is_relative", False)) or bool(targets)
        module = str(getattr(import_info, "module", ""))
        if module and adapter.is_project_module(module):
            is_local = True
        if not is_local:
            continue
        if file_path in candidates:
            diagnostics.append(f"artifact imports itself: {file_path}")
            continue
        if not targets:
            diagnostics.append(f"local import outside frozen file set: {module}")
            continue
        imported_symbols = tuple(getattr(import_info, "symbols", ()))
        if not imported_symbols or "*" in imported_symbols:
            continue
        target = next((path for path in targets if planned_contents.get(path)), None)
        if target is None:
            continue
        target_facts = adapter.extract_contract_facts(planned_contents[target], target)
        symbol_contract = SymbolContract.build(
            file_path,
            requires=imported_symbols,
        )
        missing = missing_symbols(symbol_contract, target_facts)
        if missing:
            diagnostics.append(
                f"local dependency {target} does not export: {', '.join(missing)}"
            )
    return tuple(diagnostics)


__all__ = [
    "ArtifactFacts",
    "CandidateValidation",
    "ComparisonOperator",
    "ContractAssertion",
    "ContractDeclaration",
    "ContractGateResult",
    "FactSet",
    "GateDiagnostic",
    "GateStatus",
    "SymbolContract",
    "compare_contract",
    "missing_symbols",
    "validate_candidate",
]
